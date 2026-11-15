"""Resumable expanded VIIRS study. Temporary raw staging; no production exports.
Shared-reference support is diagnostic only. Outage predictors use NOAA-20 alone.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,math,tempfile,urllib.parse
import numpy as np
import pandas as pd
import h3
from scipy.optimize import linear_sum_assignment,nnls
from . import atlas_observation_evidence as e
from . import atlas_cached_pixel_audit as p

POLICY={'study_id':'lk_viirs_expanded_processing_v1','target':'screened vegetation H3-resolution-8 active-cell-days observed by S-NPP in the fixed Sri Lanka polygon',
 'scope':'regional observed-activity proxy, not true fires, complete coverage, monthly/annual estimates or custom-area calibration',
 'partitions':{'fit':[2018,2019,2020],'calibration':[2021,2022],'evaluation':[2023,2024]},
 'candidate_models':['global_ratio','seasonal_ratio','positive_affine'],'model_selection':'fit years only, leave one whole fit year out, WAPE; deterministic tie order',
 'primary_predictor':'NOAA-20 screened vegetation active cells; calendar month for seasonal candidate; no reference masks/counts/geometry in prediction inputs',
 'reference_scope':'Unique same-platform coordinate/time match to frozen standard archive supplies type. Ambiguous/unmatched/confidence-disagreeing records withhold vegetation totals.',
 'shared_support':'all temporal candidates get mutual-clear-centre diagnostics first; geometry admissibility before one-to-one maximum-cardinality minimum-time assignment; no fire counts used for pairing',
 'pair_sensitivities':{'minutes':[30,60,90],'view_cap_degrees':[None,40,60],'distance_metres':[250,500],'minimum_mutual_centres':1},
 'sampling_limits':'54 purposive calendar-stratified dates; earlier aggregate scores/pilot inspected; not blind external validation',
 'uncertainty':'separate calibration dates, scaled absolute residuals; minimum 12 dates, finite order statistic; exploratory date-level 80/90 intervals, no nominal guarantee under temporal dependence',
 'temporary_files':'Only new raw copies in a dedicated temporary directory are removed. Original pilot and derived caches are preserved.',
 'coverage_verified':False,'replacement_validated':False,'production_export_enabled':False,'frontend_changed':False}
FEATURE_COLUMNS=['date','partition','month_number','noaa20_input_available','noaa20_screened_vegetation_active_cells','noaa20_native_pixels','noaa20_nominal_clear_centres','noaa20_status']
LABEL_COLUMNS=['date','reference_available','snpp_screened_vegetation_active_cells','snpp_status']
NATIVE_COLUMNS=['fire_id','satellite','date','time_start','time_end','line','sample','latitude','longitude','confidence_class','screened_fire','sensor_zenith_degrees']

def write_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temporary.replace(path)
def records(frame):return json.loads(frame.to_json(orient='records',date_format='iso'))
def checkpoint_valid(folder,name,signature):
    path=folder/name
    if not path.exists():return False
    doc=json.loads(path.read_text());p.require(doc['signature']==signature,'Checkpoint inputs/method changed; use a fresh run folder')
    for file,receipt in doc['files'].items():
        target=folder/file;p.require(target.is_file() and target.stat().st_size==receipt['bytes'] and p.file_sha(target)==receipt['sha256'],'Changed checkpoint: '+file)
    return True

def checkpoint(folder,name,signature,files,**extra):
    doc={'signature':signature,'files':{file:{'bytes':(folder/file).stat().st_size,'sha256':p.file_sha(folder/file)} for file in files},**extra}
    write_json(folder/name,doc)

def cache_or_download(record,session,original_cache,temporary):
    name=Path(urllib.parse.urlsplit(record['download_url']).path).name
    original=Path(original_cache)/name;receipt_path=Path(original_cache)/(name+'.receipt.json')
    if original.exists():
        p.require(receipt_path.exists(),'Original cached file has no receipt; review it before reuse')
        r=json.loads(receipt_path.read_text());p.require(r['id']==record['id'] and original.stat().st_size==r['bytes'] and p.file_sha(original)==r['sha256'],'Original cache integrity mismatch')
        return original,{**r,'reused_original_cache':True}
    path,receipt=e.download(record,session,temporary)
    p.require(abs(receipt['bytes']-record['catalogue_size_mb']*1024**2)<2,'Downloaded size differs from frozen catalogue')
    return path,{**receipt,'reused_original_cache':False}

def process_granule(join,lookup,session,original_cache,scratch,derived,method_hash,region):
    f=lookup[join['fire_id']];g=lookup[join['geo_id']];folder=Path(derived)/e.sha(f['id'].encode())[:24];folder.mkdir(parents=True,exist_ok=True)
    signature={'method_hash':method_hash,'fire_metadata':f['metadata_entry_sha256'],'geo_metadata':g['metadata_entry_sha256']}
    if not checkpoint_valid(folder,'checkpoint.json',signature):
        # This context owns only the new transient copies, never user caches.
        with tempfile.TemporaryDirectory(prefix='cindertrace-raw-',dir=scratch) as tmp:
            fp,fr=cache_or_download(f,session,original_cache,tmp);gp,gr=cache_or_download(g,session,original_cache,tmp)
            summary,native,clear,bins=p.extract_granule(fp,gp,f,region)
            native.to_parquet(folder/'native.parquet',index=False);clear.to_parquet(folder/'clear.parquet',index=False);bins.to_parquet(folder/'bins.parquet',index=False)
            write_json(folder/'summary.json',summary);write_json(folder/'receipts.json',[fr,gr])
            checkpoint(folder,'checkpoint.json',signature,['native.parquet','clear.parquet','bins.parquet','summary.json','receipts.json'])
    return json.loads((folder/'summary.json').read_text()),pd.read_parquet(folder/'native.parquet'),folder/'clear.parquet',json.loads((folder/'receipts.json').read_text())

def attributed_native(native,archive):
    typed=p.archive_match(native,archive)
    confidence=archive.set_index('observation_id').confidence
    typed['archive_confidence']=typed.archive_observation_id.map(confidence)
    expected=typed.confidence_class.map({7:'l',8:'n',9:'h'}) if 'confidence_class' in typed else pd.Series(index=typed.index,dtype='str')
    typed['confidence_agrees']=typed.archive_confidence.eq(expected)&typed.archive_match_status.eq('unique_standard_observation')
    if len(typed):typed['cell']=[h3.latlng_to_cell(float(a),float(b),8) for a,b in zip(typed.latitude,typed.longitude)]
    else:typed['cell']=pd.Series(dtype='str')
    return typed

def sensor_daily_state(satellite,day,inventory,summaries,typed,archive):
    planned=[r for r in inventory['records'] if r['kind']=='fire' and r['date']==day and r['satellite']==satellite]
    done=[r for r in summaries if r['satellite']==satellite];n=typed[typed.satellite.eq(satellite)];a=archive[archive.satellite.eq(satellite)]
    if not planned:return {'available':False,'status':'catalogue_absent_not_zero_activity','activity':None,'native_pixels':None,'clear_centres':None}
    if len(done)!=len(planned):return {'available':False,'status':'incomplete_science_processing','activity':None,'native_pixels':None,'clear_centres':None}
    complete_match=len(n)==len(a) and n.archive_match_status.eq('unique_standard_observation').all() and n.confidence_agrees.all() and n.archive_observation_id.nunique()==len(a)
    if not complete_match:return {'available':False,'status':'archive_reconciliation_or_type_unavailable','activity':None,'native_pixels':len(n),'clear_centres':sum(r['clear_centres'] for r in done)}
    local=sum(r['local_centres'] for r in done);clear=sum(r['clear_centres'] for r in done)
    if not local or not clear:return {'available':False,'status':'no_nominal_clear_support_not_zero_activity','activity':None,'native_pixels':len(n),'clear_centres':clear}
    count=n[n.screened_fire&n.archive_type.eq(0)].cell.nunique()
    return {'available':True,'status':'recorded_screened_activity_coverage_unverified','activity':int(count),'native_pixels':len(n),'clear_centres':clear}

def daily_tables(slot,inventory,summaries,typed,archive):
    # Compute each sensor independently. Reference failures cannot change features.
    day=slot['date'];x=sensor_daily_state('NOAA-20',day,inventory,summaries,typed,archive);y=sensor_daily_state('Suomi-NPP',day,inventory,summaries,typed,archive)
    feature={'date':day,'partition':slot['partition'],'month_number':int(day[5:7]),'noaa20_input_available':x['available'],
     'noaa20_screened_vegetation_active_cells':x['activity'],'noaa20_native_pixels':x['native_pixels'],'noaa20_nominal_clear_centres':x['clear_centres'],'noaa20_status':x['status']}
    label={'date':day,'reference_available':y['available'],'snpp_screened_vegetation_active_cells':y['activity'],'snpp_status':y['status']}
    return pd.DataFrame([feature],columns=FEATURE_COLUMNS),pd.DataFrame([label],columns=LABEL_COLUMNS)

def pass_inventory(membership,summaries):
    s=pd.DataFrame(summaries);rows=[]
    for pid,f in membership.groupby('pass_id',sort=True):
        part=s[s.fire_id.isin(f.fire_id)] if len(s) else pd.DataFrame();complete=len(part)==len(f);start=min(pd.Timestamp(t) for t in f.time_start);end=max(pd.Timestamp(t) for t in f.time_end)
        rows.append({'pass_id':pid,'satellite':f.iloc[0].satellite,'date':f.iloc[0].date,'day_night':f.iloc[0].day_night,'midpoint_utc':(start+(end-start)/2).isoformat(),
          'complete_science_screen':complete,'local_centres':int(part.local_centres.sum()) if complete else None,'granules':len(f)})
    return pd.DataFrame(rows)

def select_geometry_pairs(passes,diagnostics,window,view,distance):
    selected=[]
    diag=diagnostics[diagnostics.distance_cap_metres.eq(distance)&(diagnostics.view_cap_degrees.isna() if view is None else diagnostics.view_cap_degrees.eq(view))]
    for (date,flag),group in passes.groupby(['date','day_night'],sort=True):
        if flag not in ['DAY','NIGHT']:continue
        a=group[group.satellite.eq('Suomi-NPP')].sort_values('pass_id');b=group[group.satellite.eq('NOAA-20')].sort_values('pass_id')
        if not len(a) or not len(b):continue
        lookup={(r.snpp_pass,r.noaa20_pass):r for r in diag.itertuples()};cost=np.full((len(a),len(b)+len(a)),1e6);cost[:,:len(b)]=1e9
        for ix,ar in enumerate(a.itertuples()):
            for iy,br in enumerate(b.itertuples()):
                row=lookup.get((ar.pass_id,br.pass_id))
                if row is not None and ar.complete_science_screen and br.complete_science_screen and row.separation_minutes<=window and row.mutual_nearest_clear_centre_pairs>=1:cost[ix,iy]=row.separation_minutes
        xs,ys=linear_sum_assignment(cost)
        for x,y in zip(xs,ys):
            if y>=len(b) or cost[x,y]>=1e6:continue
            selected.append({'date':date,'day_night':flag,'window_minutes':window,'view_cap_degrees':view,'distance_cap_metres':distance,
              'snpp_pass':a.iloc[x].pass_id,'noaa20_pass':b.iloc[y].pass_id,'separation_minutes':float(cost[x,y]),'selection_basis':'geometry_admissible_then_time_only_no_fire_counts'})
    return pd.DataFrame(selected,columns=['date','day_night','window_minutes','view_cap_degrees','distance_cap_metres','snpp_pass','noaa20_pass','separation_minutes','selection_basis'])

def geometry_audit(membership,passes,clear_paths):
    rows=[]
    def support(pid):
        return pd.concat([pd.read_parquet(clear_paths[id]) for id in membership[membership.pass_id.eq(pid)].fire_id],ignore_index=True)
    for ar in passes[passes.satellite.eq('Suomi-NPP')].itertuples():
        if not ar.complete_science_screen or not ar.local_centres or ar.day_night not in ['DAY','NIGHT']:continue
        for br in passes[passes.satellite.eq('NOAA-20')&passes.date.eq(ar.date)&passes.day_night.eq(ar.day_night)].itertuples():
            if not br.complete_science_screen or not br.local_centres:continue
            delta=abs((pd.Timestamp(ar.midpoint_utc)-pd.Timestamp(br.midpoint_utc)).total_seconds())/60
            if delta>90:continue
            d=p.pair_diagnostics(support(ar.pass_id),support(br.pass_id));d['date']=ar.date;d['day_night']=ar.day_night;d['snpp_pass']=ar.pass_id;d['noaa20_pass']=br.pass_id;d['separation_minutes']=delta;rows.append(d)
    cols=['view_cap_degrees','distance_cap_metres','mutual_nearest_clear_centre_pairs','separation_minutes','snpp_pass','noaa20_pass']
    diagnostics=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame(columns=cols)
    pairs=[]
    for window in [30,60,90]:
        for view in [None,40,60]:
            for distance in [250,500]:pairs.append(select_geometry_pairs(passes,diagnostics,window,view,distance))
    return diagnostics,pd.concat(pairs,ignore_index=True)

def process_date(slot,inputs,session,original_cache,scratch,work,method_hash):
    from shapely.geometry import shape
    day=slot['date'];inventory=inputs['inventory'];folder=Path(work)/'dates'/day;folder.mkdir(parents=True,exist_ok=True)
    signature={'method_hash':method_hash,'date':day}
    if checkpoint_valid(folder,'checkpoint.json',signature):
        old=json.loads((folder/'checkpoint.json').read_text())
        if old['all_planned_granules_processed']:return old
        # Withdraw the prior partial commit before replacing its derived tables.
        (folder/'checkpoint.json').unlink()
    region=shape(json.loads(inputs['boundary'])['features'][0]['geometry']);lookup={r['id']:r for r in inventory['records']}
    joins=[j for j in inventory['companions'] if j['date']==day];summaries=[];native=[];clear_paths={};receipts=[];failures=[];access_denied=False
    derived=Path(work)/'derived';derived.mkdir(exist_ok=True)
    for join in joins:
        try:
            p.require(join['status']=='unique_catalogue_companion','Missing/ambiguous companion')
            summary,n,path,r=process_granule(join,lookup,session,original_cache,scratch,derived,method_hash,region)
            summaries.append(summary);native.append(n);clear_paths[join['fire_id']]=path;receipts.extend(r)
            print('Processed',day,lookup[join['fire_id']]['name'],flush=True)
        except Exception as error:
            failures.append({'fire_id':join['fire_id'],'error_type':type(error).__name__,'reason':str(error)[:240]})
            if isinstance(error,e.ScienceAccessRequired):access_denied=True;break
        write_json(folder/'failures.json',failures)
    archive=pd.DataFrame(inputs['standard_observations']);archive['acq_datetime']=pd.to_datetime(archive.acq_datetime,utc=True);archive=archive[archive.acq_datetime.dt.strftime('%Y-%m-%d').eq(day)].reset_index(drop=True)
    n=pd.concat(native,ignore_index=True) if native else pd.DataFrame(columns=NATIVE_COLUMNS);typed=attributed_native(n,archive)
    features,labels=daily_tables(slot,inventory,summaries,typed,archive)
    # Write source-only features before diagnostic reference-conditioned matching.
    frames={'noaa20_features':features,'reference_labels':labels,'native_pixel_audit':typed,'granule_audit':pd.DataFrame(summaries)}
    membership=p.group_passes([r for r in inventory['records'] if r['date']==day]);passes=pass_inventory(membership,summaries)
    frames.update(pass_membership=membership,pass_inventory=passes)
    try:diag,pairs=geometry_audit(membership,passes,clear_paths)
    except Exception as error:
        diag=pd.DataFrame();pairs=pd.DataFrame();failures.append({'stage':'geometry_diagnostic','error_type':type(error).__name__,'reason':str(error)[:240]})
    frames.update(all_temporal_candidate_diagnostics=diag,geometry_qualified_pairs=pairs,unmatched_standard_observations=archive[~archive.observation_id.isin(typed.archive_observation_id.dropna())])
    for name,frame in frames.items():frame.to_parquet(folder/(name+'.parquet'),index=False)
    write_json(folder/'download_receipts.json',receipts);write_json(folder/'failures.json',failures)
    all_done=len(summaries)==len(joins);files=[name+'.parquet' for name in frames]+['download_receipts.json','failures.json']
    checkpoint(folder,'checkpoint.json',signature,files,all_planned_granules_processed=all_done and not failures,access_denied=access_denied,
      planned_fire_granules=len(joins),processed_fire_granules=len(summaries),date=day)
    return json.loads((folder/'checkpoint.json').read_text())

def run_batch(inputs,years,session,original_cache,scratch,work,method_hash):
    scratch=Path(scratch);scratch.mkdir(parents=True,exist_ok=True);Path(work).mkdir(parents=True,exist_ok=True);out=[]
    for slot in inputs['design']['dates']:
        if slot['year'] not in years:continue
        result=process_date(slot,inputs,session,original_cache,scratch,work,method_hash);out.append(result)
        print('Date checkpoint',slot['date'],'granules',result['processed_fire_granules'],'/',result['planned_fire_granules'],flush=True)
        if result['access_denied']:break
    return {'years':list(years),'dates_attempted':len(out),'access_denied':any(x['access_denied'] for x in out),'date_audits_complete':sum(x['all_planned_granules_processed'] for x in out)}

def fit_candidate(x,y,months,kind):
    x=np.asarray(x,float);y=np.asarray(y,float)
    if not len(y) or y.sum()<=0:return None
    if kind=='seasonal_baseline':
        overall=float(y.mean());return {'kind':kind,'rates':{m:float((y[np.asarray(months)==m].sum()+3*overall)/((np.asarray(months)==m).sum()+3)) for m in range(1,13)}}
    if kind in ['global_ratio','seasonal_ratio']:
        if x.sum()<=0:return None
        ratio=float(y.sum()/x.sum());model={'kind':kind,'ratio':ratio}
        if kind=='seasonal_ratio':
            prior=max(1.,float(np.median(x[x>0]))*3);model['rates']={m:float((y[np.asarray(months)==m].sum()+prior*ratio)/(x[np.asarray(months)==m].sum()+prior)) for m in range(1,13)}
        return model
    if kind=='positive_affine':
        a,b=nnls(np.column_stack([np.ones(len(x)),x]),y)[0];return {'kind':kind,'intercept':float(a),'slope':float(b)}
    raise ValueError('Unsupported candidate')

def predict(model,features):
    # Whitelist the source-only columns; no reference rows/availability read here.
    x=features.noaa20_screened_vegetation_active_cells.to_numpy(float);m=features.month_number.to_numpy(int)
    if model['kind']=='global_ratio':return x*model['ratio']
    if model['kind']=='seasonal_ratio':return x*np.array([model['rates'][int(v)] for v in m])
    if model['kind']=='seasonal_baseline':return np.array([model['rates'][int(v)] for v in m])
    return model['intercept']+model['slope']*x

def evaluate_outage_proxy(features,labels):
    p.require(set(features.columns)==set(FEATURE_COLUMNS),'Unexpected predictor schema; reference-derived fields prohibited')
    p.require(set(labels.columns)==set(LABEL_COLUMNS),'Unexpected reference schema')
    p.require(not features.date.duplicated().any() and not labels.date.duplicated().any(),'Repeated date unit')
    for frame,flag,column in [(features,'noaa20_input_available','noaa20_screened_vegetation_active_cells'),(labels,'reference_available','snpp_screened_vegetation_active_cells')]:
        values=pd.to_numeric(frame.loc[frame[flag],column],errors='raise').to_numpy(float);p.require(np.isfinite(values).all() and (values>=0).all(),'Available activity must have finite nonnegative values')
    f=features.merge(labels,on='date',how='left',validate='one_to_one');ycol='snpp_screened_vegetation_active_cells';xcol='noaa20_screened_vegetation_active_cells'
    both=f.noaa20_input_available&f.reference_available.fillna(False);fit=f[both&f.partition.eq('fit')].copy();cal=f[both&f.partition.eq('calibration')].copy()
    test_features=features[features.partition.eq('evaluation')&features.noaa20_input_available].copy();audit={'fit_dates':list(fit.date),'calibration_dates':list(cal.date),'evaluation_source_dates':list(test_features.date),'status':'insufficient_fit_support'}
    p.require(not (set(fit.date)&set(cal.date) or set(fit.date)&set(test_features.date) or set(cal.date)&set(test_features.date)),'Partition leakage')
    if test_features.empty:
        audit['status']='no_source_available_evaluation_dates';return pd.DataFrame(),pd.DataFrame(),audit
    if len(fit)<12 or pd.to_datetime(fit.date).dt.year.nunique()<3 or fit[ycol].sum()<=0:return pd.DataFrame(),pd.DataFrame(),audit
    years=pd.to_datetime(fit.date).dt.year;scores=[]
    for order,kind in enumerate(POLICY['candidate_models']):
        error=total=0.;supported=True
        for year in sorted(years.unique()):
            a=fit[years.ne(year)];b=fit[years.eq(year)];model=fit_candidate(a[xcol],a[ycol],a.month_number,kind)
            if model is None:supported=False;break
            error+=float(np.abs(predict(model,b[FEATURE_COLUMNS])-b[ycol]).sum());total+=float(b[ycol].sum())
        score=error/total if supported and total>0 else np.inf;scores.append((score,order,kind))
    best=min(scores)
    if not np.isfinite(best[0]):return pd.DataFrame(),pd.DataFrame(),audit
    kind=best[2];model=fit_candidate(fit[xcol],fit[ycol],fit.month_number,kind);baseline=fit_candidate(fit[xcol],fit[ycol],fit.month_number,'seasonal_baseline')
    audit.update(status='exploratory_research_evaluated',selected_model=kind,inner_wape=best[0],candidate_scores={k:float(s) if np.isfinite(s) else None for s,_,k in scores},model=model)
    test_labels=labels.set_index('date');rows=[]
    for role,obj in [('selected_transfer',model),('native_source_identity',None),('seasonal_baseline',baseline)]:
        cp=cal[xcol].to_numpy(float) if obj is None else predict(obj,cal[FEATURE_COLUMNS]);tp=test_features[xcol].to_numpy(float) if obj is None else predict(obj,test_features)
        residual=np.abs(cal[ycol].to_numpy(float)-cp)/np.sqrt(1+cp);radii={}
        for level in [80,90]:
            rank=math.ceil((len(residual)+1)*level/100);radii[level]=float(np.sort(residual)[rank-1]) if len(residual)>=12 and rank<=len(residual) else None
        for index,row in enumerate(test_features.itertuples()):
            label=test_labels.loc[row.date] if row.date in test_labels.index else None;available=label is not None and bool(label.reference_available);point=float(tp[index])
            result={'date':row.date,'role':role,'model':kind if role=='selected_transfer' else role,'prediction':point,'reference_available':available,'observed':float(label[ycol]) if available else None,'prediction_scope':POLICY['target']}
            for level,q in radii.items():
                half=q*np.sqrt(1+point) if q is not None else None;result['lower_'+str(level)]=max(0.,point-half) if half is not None else None;result['upper_'+str(level)]=point+half if half is not None else None
            result['interval_status']='exploratory_date_calibration' if all(v is not None for v in radii.values()) else 'withheld_insufficient_calibration_dates';rows.append(result)
    predictions=pd.DataFrame(rows);metrics=[]
    for role,group in predictions.groupby('role',sort=False):
        valid=group[group.reference_available];den=valid.observed.sum();error=(valid.prediction-valid.observed).abs();r={'role':role,'source_available_evaluation_dates':len(group),'scored_evaluation_dates':len(valid),'wape':float(error.sum()/den) if den>0 else None,'mae':float(error.mean()) if len(valid) else None}
        for level in [80,90]:
            a=valid[valid['lower_'+str(level)].notna()];r['interval_dates_'+str(level)]=len(a);r['coverage_'+str(level)]=float(a.observed.between(a['lower_'+str(level)],a['upper_'+str(level)]).mean()) if len(a) else None;r['mean_width_'+str(level)]=float((a['upper_'+str(level)]-a['lower_'+str(level)]).mean()) if len(a) else None
        metrics.append(r)
    return predictions,pd.DataFrame(metrics),audit

def finalize(inputs,work,output,method_hash):
    work=Path(work);output=Path(output);output.mkdir(parents=True,exist_ok=True);features=[];labels=[];dates=[];failures=[];receipts=[]
    combined={name:[] for name in ['native_pixel_audit','granule_audit','pass_membership','pass_inventory','all_temporal_candidate_diagnostics','geometry_qualified_pairs','unmatched_standard_observations']}
    for slot in inputs['design']['dates']:
        day=slot['date'];folder=work/'dates'/day;signature={'method_hash':method_hash,'date':day}
        if checkpoint_valid(folder,'checkpoint.json',signature):
            cp=json.loads((folder/'checkpoint.json').read_text());features.append(pd.read_parquet(folder/'noaa20_features.parquet'));labels.append(pd.read_parquet(folder/'reference_labels.parquet'));dates.append({**slot,'status':'processed' if cp['all_planned_granules_processed'] else 'partial','processed_fire_granules':cp['processed_fire_granules'],'planned_fire_granules':cp['planned_fire_granules']})
            failures.extend([{'date':day,**x} for x in json.loads((folder/'failures.json').read_text())]);receipts.extend(json.loads((folder/'download_receipts.json').read_text()))
            for name in combined:combined[name].append(pd.read_parquet(folder/(name+'.parquet')))
        else:
            dates.append({**slot,'status':'not_processed'});features.append(pd.DataFrame([{'date':day,'partition':slot['partition'],'month_number':int(day[5:7]),'noaa20_input_available':False,'noaa20_screened_vegetation_active_cells':None,'noaa20_native_pixels':None,'noaa20_nominal_clear_centres':None,'noaa20_status':'not_processed'}],columns=FEATURE_COLUMNS));labels.append(pd.DataFrame([{'date':day,'reference_available':False,'snpp_screened_vegetation_active_cells':None,'snpp_status':'not_processed'}],columns=LABEL_COLUMNS))
    features=pd.concat(features,ignore_index=True);labels=pd.concat(labels,ignore_index=True);predictions,metrics,audit=evaluate_outage_proxy(features,labels)
    frames={'noaa20_features':features,'reference_labels':labels,'evaluation_predictions':predictions,'evaluation_metrics':metrics,'date_status':pd.DataFrame(dates)}
    frames.update({name:pd.concat(chunks,ignore_index=True) if chunks else pd.DataFrame() for name,chunks in combined.items()})
    for name,frame in frames.items():frame.to_parquet(output/(name+'.parquet'),index=False)
    write_json(output/'split_and_model_audit.json',audit);write_json(output/'failures.json',failures);write_json(output/'download_receipts.json',receipts);write_json(output/'method.json',POLICY)
    report={'study_id':POLICY['study_id'],'method_hash':method_hash,'dates_planned':len(dates),'dates_processed':sum(x['status']=='processed' for x in dates),'date_failures':len(failures),
      'fit_source_dates_available':int((features.partition.eq('fit')&features.noaa20_input_available).sum()),'calibration_source_dates_available':int((features.partition.eq('calibration')&features.noaa20_input_available).sum()),'evaluation_source_dates_available':int((features.partition.eq('evaluation')&features.noaa20_input_available).sum()),
      'evaluation_dates_withheld':records(features[features.partition.eq('evaluation')&~features.noaa20_input_available][['date','noaa20_status']]),
      'status':'exploratory_research_only','model_evaluation_status':audit['status'],'metrics':records(metrics),'coverage_verified':False,'replacement_validated':False,'production_export_enabled':False,'frontend_changed':False,
      'limitations':['Sampled dates do not validate monthly/annual uncertainty or early history','Geometry matching is centre proximity, not physical footprint coverage','Reference-conditioned support never enters outage predictor features','Archive/type reconciliation and source availability can withhold dates','Actual outage covariate shift remains unverified','Earlier aggregate scores were inspected; not blind external validation']}
    write_json(output/'decision.json',report);checkpoint(output,'manifest.json',{'method_hash':method_hash},[path.name for path in output.iterdir() if path.is_file() and path.name!='manifest.json'])
    return report
