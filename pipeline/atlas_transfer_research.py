"""Regional observed-activity transfer research on the repaired dataset.
Calendar support is not matched overpasses or cloud/observation completeness.
No production estimates, local allocation, satellite replacement or season claims.
"""
from pathlib import Path
import hashlib,json,math
import numpy as np
import pandas as pd
import h3
from scipy.optimize import nnls
from scipy.stats import spearmanr

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/'data/atlas/canonical_lk_2000_2024_v1'
OUT=ROOT/'data/atlas/transfer_research_v1'
TASK_SENSORS={'terra_to_modis':['Terra','Aqua'],'modis_to_snpp':['Terra','Aqua','Suomi-NPP'],
 'terra_chain_to_snpp':['Terra','Aqua','Suomi-NPP'],'noaa20_to_snpp_diagnostic':['NOAA-20','Suomi-NPP']}
CONFIGS=[{'name':'primary','resolution':8,'filter':'vegetation_all_confidence','gap_mask':'all_documented_global_gap_dates','window':'full'},
 {'name':'coarser_grid','resolution':7,'filter':'vegetation_all_confidence','gap_mask':'all_documented_global_gap_dates','window':'full'},
 {'name':'finer_grid','resolution':9,'filter':'vegetation_all_confidence','gap_mask':'all_documented_global_gap_dates','window':'full'},
 {'name':'native_confidence_screen','resolution':8,'filter':'vegetation_native_screen','gap_mask':'all_documented_global_gap_dates','window':'full'},
 {'name':'listed_missing_dates_only','resolution':8,'filter':'vegetation_all_confidence','gap_mask':'listed_missing_dates_only','window':'full'},
 {'name':'last5_fit_years','resolution':8,'filter':'vegetation_all_confidence','gap_mask':'all_documented_global_gap_dates','window':'last5'},
 {'name':'last8_fit_years','resolution':8,'filter':'vegetation_all_confidence','gap_mask':'all_documented_global_gap_dates','window':'last8'}]
POLICY={'research_id':'lk_observed_transfer_research_v1','scope':'Sri Lanka original study polygon; regional only',
 'target':'reference-sensor observed vegetation active-cell-days on common eligible UTC calendar dates',
 'primary_configuration':CONFIGS[0],'sensitivity_design':'one factor at a time; no resolution/filter chosen from outer test scores',
 'minimum_supported_days_per_month':20,'minimum_supported_calendar_fraction':0.8,'minimum_months_per_year':8,
 'meaning_of_support':'verified archive queries with selected global gap-date exclusions; not verified observing opportunities',
 'native_screen':'MODIS confidence_pct >=30; VIIRS n/h; filtering conventions, not equal sensor probabilities',
 'monthly_interval_method':'separate two-year calibration block; empirical scaled absolute-residual quantiles; nominal guarantees not asserted under temporal dependence',
 'union_constraint':'combined MODIS predictions are floored at contemporaneous observed Terra activity; the Terra-target seasonal baseline has the same floor',
 'baselines':['seasonal_daily_climatology (Terra floor when target is union MODIS)','uncalibrated_native_source_identity'],
 'year_split':'outer held-out whole years; model selection confined to fit years; separate calibration years never used for selection or refitting',
 'chronological_test':'fit/selection/calibration use years <=2021; test 2022–2024 contemporaneous sensor transfer, not forecasting',
 'annual_intervals':'withheld: two calibration years are insufficient for supported 80/90 percent annual uncertainty',
 'noaa20_status':'calendar-aligned diagnostic only; matched observing footprints/overpasses unverified, no gap filling enabled',
 'coverage_verified':False,'physical_fire_truth_validated':False,'production_export_enabled':False,'frontend_changed':False}
CANDIDATES=['global_ratio','seasonal_ratio','positive_affine']

def digest(raw):return hashlib.sha256(raw).hexdigest()

def load_inputs(path=None):
    path=Path(DATA if path is None else path);m=json.loads((path/'manifest.json').read_text())
    if m['observations']!=171244 or m['production_export_enabled'] is not False:raise ValueError('Unexpected observed-data checkpoint')
    for name,r in m['files'].items():
        raw=(path/name).read_bytes()
        if len(raw)!=r['bytes'] or digest(raw)!=r['sha256']:raise ValueError('Observed checkpoint file changed')
    p=pd.read_parquet(path/'observations.parquet');daily=pd.read_parquet(path/'daily_status.parquet')
    if not p.quality.eq('sp').all() or not daily.observing_coverage.eq('unverified').all():raise ValueError('Wrong source quality or unsupported coverage claim')
    return p,daily,m

def activity_sets(points,resolution,filter_name):
    p=points[points.type.eq(0)&points.satellite.isin(['Terra','Aqua','Suomi-NPP','NOAA-20'])].copy()
    if filter_name=='vegetation_native_screen':
        modis=p.satellite.isin(['Terra','Aqua']);p=p[(modis&p.confidence_pct.ge(30))|(~modis&p.confidence.isin(['n','h']))]
    elif filter_name!='vegetation_all_confidence':raise ValueError('Unknown native filter')
    p['cell']=[h3.latlng_to_cell(float(lat),float(lon),resolution) for lat,lon in zip(p.latitude,p.longitude)]
    # One observation of activity per sensor/cell/UTC day; no deduplication across days.
    unique=p[['acq_date','satellite','cell']].drop_duplicates()
    sets={}
    for (day,satellite),f in unique.groupby(['acq_date','satellite'],sort=False):sets[(day,satellite)]=set(f.cell)
    return sets,{'filtered_pixel_observations':len(p),'sensor_cell_days':len(unique),'resolution':resolution,'filter':filter_name}

def qualify_months(daily,sets,gap_mask):
    d=daily[daily.satellite.isin(['Terra','Aqua','Suomi-NPP','NOAA-20'])].copy()
    valid=d.recorded_detections.notna()&~d.upstream_lists_missing_standard_data
    if gap_mask=='all_documented_global_gap_dates':valid&=~d.documented_global_gap_on_date
    elif gap_mask!='listed_missing_dates_only':raise ValueError('Unknown gap mask')
    d['eligible_calendar_date']=valid
    states=d.pivot(index='date',columns='satellite',values='eligible_calendar_date').fillna(False)
    records=[]
    for task,sensors in TASK_SENSORS.items():
        for month in sorted({str(day)[:7] for day in states.index}):
            dates=[day for day in states.index if str(day).startswith(month)]
            eligible=[day for day in dates if all(bool(states.loc[day,s]) for s in sensors)]
            days_in_month=pd.Period(month,freq='M').days_in_month
            good=len(eligible)>=20 and len(eligible)/days_in_month>=.8
            t=a=combined=s=n20=duplicates=0
            for day in eligible:
                ts=sets.get((day,'Terra'),set());aa=sets.get((day,'Aqua'),set())
                t+=len(ts);a+=len(aa);combined+=len(ts|aa);duplicates+=len(ts&aa)
                s+=len(sets.get((day,'Suomi-NPP'),set()));n20+=len(sets.get((day,'NOAA-20'),set()))
            records.append({'task':task,'month':month,'year':int(month[:4]),'month_number':int(month[5:]),
                'days_in_month':days_in_month,'common_calendar_days':len(eligible),'calendar_fraction':len(eligible)/days_in_month,
                'eligible_month':good,'eligibility_reason':'calendar_support_pass' if good else 'insufficient_or_unsupported_common_calendar_dates',
                'terra':t if eligible else np.nan,'aqua':a if eligible else np.nan,'modis':combined if eligible else np.nan,
                'snpp':s if eligible else np.nan,'noaa20':n20 if eligible else np.nan,'terra_aqua_overlap_cell_days':duplicates if eligible else np.nan,
                'observing_opportunities_verified':False,'gap_mask':gap_mask})
    frame=pd.DataFrame(records)
    frame['eligible_year']=False
    # First incomplete reference/launch years remain outside primary annual-cohort definitions.
    for task in TASK_SENSORS:
        first=2003 if task=='terra_to_modis' else 2013 if task!='noaa20_to_snpp_diagnostic' else 2018
        counts=frame[frame.task.eq(task)&frame.eligible_month&frame.year.ge(first)].groupby('year').size()
        frame.loc[frame.task.eq(task)&frame.year.isin(counts[counts.ge(8)].index),'eligible_year']=True
    return frame

def fit_model(frame,xcol,ycol,kind):
    x=frame[xcol].to_numpy(float);y=frame[ycol].to_numpy(float);days=frame.common_calendar_days.to_numpy(float)
    if len(frame)<12 or not np.isfinite(x).all() or not np.isfinite(y).all() or y.sum()<=0:return None
    if kind=='seasonal_baseline':
        rate=y.sum()/days.sum();rates={m:(frame.loc[frame.month_number.eq(m),ycol].sum()+90*rate)/(frame.loc[frame.month_number.eq(m),'common_calendar_days'].sum()+90) for m in range(1,13)}
        return {'kind':kind,'rates':rates}
    if kind in ['global_ratio','seasonal_ratio']:
        if x.sum()<=0:return None
        ratio=y.sum()/x.sum();model={'kind':kind,'ratio':ratio}
        if kind=='seasonal_ratio':
            prior=max(1.,float(np.median(x[x>0]))*3)
            model['rates']={m:(frame.loc[frame.month_number.eq(m),ycol].sum()+prior*ratio)/(frame.loc[frame.month_number.eq(m),xcol].sum()+prior) for m in range(1,13)}
        return model
    if kind=='positive_affine':
        design=np.column_stack([np.ones(len(x)),x/days]);weights=np.sqrt(days)
        coefficients,_=nnls(design*weights[:,None],y/days*weights)
        return {'kind':kind,'intercept':float(coefficients[0]),'slope':float(coefficients[1])}
    raise ValueError('Unknown transfer candidate')

def predict_model(model,frame,xcol):
    if model is None:return None
    x=frame[xcol].to_numpy(float)
    if model['kind']=='seasonal_baseline':return np.array([model['rates'][int(m)] for m in frame.month_number])*frame.common_calendar_days.to_numpy(float)
    if model['kind']=='global_ratio':return x*model['ratio']
    if model['kind']=='seasonal_ratio':return x*np.array([model['rates'][int(m)] for m in frame.month_number])
    return model['intercept']*frame.common_calendar_days.to_numpy(float)+model['slope']*x

def task_columns(task):return ('terra','modis') if task=='terra_to_modis' else ('noaa20','snpp') if task=='noaa20_to_snpp_diagnostic' else ('modis','snpp')

def fit_candidate(frame,task,candidate):
    if task=='terra_chain_to_snpp':
        first,second=candidate.split('|');a=fit_model(frame,'terra','modis',first);b=fit_model(frame,'modis','snpp',second)
        return None if a is None or b is None else (a,b)
    x,y=task_columns(task);return fit_model(frame,x,y,candidate)

def predict_candidate(model,frame,task):
    if model is None:return None
    if task=='terra_chain_to_snpp':
        intermediate=np.maximum(predict_model(model[0],frame,'terra'),frame.terra.to_numpy(float));f=frame.copy();f['estimated_modis']=intermediate
        return predict_model(model[1],f,'estimated_modis')
    x,_=task_columns(task);prediction=predict_model(model,frame,x)
    return np.maximum(prediction,frame.terra.to_numpy(float)) if task=='terra_to_modis' else prediction

def select_candidate(fit,task):
    years=sorted(fit.year.unique());candidates=[f'{a}|{b}' for a in CANDIDATES for b in CANDIDATES] if task=='terra_chain_to_snpp' else CANDIDATES
    target='snpp' if task=='terra_chain_to_snpp' else task_columns(task)[1]
    scores=[]
    for order,candidate in enumerate(candidates):
        error=weight=0.;folds=0
        for year in years:
            train=fit[fit.year.ne(year)];test=fit[fit.year.eq(year)]
            model=fit_candidate(train,task,candidate);prediction=predict_candidate(model,test,task)
            if prediction is None:continue
            error+=float(np.abs(prediction-test[target].to_numpy(float)).sum());weight+=float(test[target].sum());folds+=1
        score=error/weight if weight>0 and folds==len(years) else np.inf
        scores.append((score,order,candidate))
    best=min(scores)
    return None if not np.isfinite(best[0]) else {'candidate':best[2],'inner_wape':best[0],'inner_years':years,'candidate_scores':{c:float(s) if np.isfinite(s) else None for s,_,c in scores}}

def empirical_radius(observed,prediction,level):
    scores=np.abs(np.asarray(observed,float)-np.asarray(prediction,float))/np.sqrt(1+np.asarray(prediction,float))
    n=len(scores);rank=math.ceil((n+1)*level)
    if n<18 or rank>n:return None
    return float(np.sort(scores)[rank-1])

def evaluate_split(frame,task,test_years,window='full',chronological=False):
    test=frame[frame.year.isin(test_years)].copy();train=frame[~frame.year.isin(test_years)]
    if chronological:train=train[train.year.lt(min(test_years))]
    train_years=sorted(train.year.unique());calibration_years=train_years[-2:];fit_years=train_years[:-2]
    if window!='full':fit_years=fit_years[-int(window.removeprefix('last')):]
    if len(fit_years)<4 or len(test)==0:return [],{'status':'insufficient_fit_years','test_years':list(map(int,test_years)),'fit_years':list(map(int,fit_years))}
    fit=train[train.year.isin(fit_years)];cal=train[train.year.isin(calibration_years)]
    if set(fit.year)&set(cal.year) or set(test.year)&(set(fit.year)|set(cal.year)):raise ValueError('Year split leakage')
    choice=select_candidate(fit,task)
    if choice is None:return [],{'status':'no_supported_transfer_candidate','test_years':list(map(int,test_years))}
    model=fit_candidate(fit,task,choice['candidate']);cal_pred=predict_candidate(model,cal,task);pred=predict_candidate(model,test,task)
    x,target=task_columns(task)
    if task=='terra_chain_to_snpp':x='terra';target='snpp'
    baseline=fit_model(fit,x,target,'seasonal_baseline');baseline_cal=predict_model(baseline,cal,x);baseline_test=predict_model(baseline,test,x)
    if task=='terra_to_modis':
        baseline_cal=np.maximum(baseline_cal,cal.terra.to_numpy(float));baseline_test=np.maximum(baseline_test,test.terra.to_numpy(float))
    records=[]
    for role,cp,tp in [('selected_transfer',cal_pred,pred),('seasonal_baseline',baseline_cal,baseline_test),('native_source_identity',cal[x].to_numpy(float),test[x].to_numpy(float))]:
        radii={str(int(level*100)):empirical_radius(cal[target].to_numpy(float),cp,level) for level in [.8,.9]}
        for pos,row in enumerate(test.itertuples()):
            point=float(tp[pos]);observed=float(getattr(row,target));r={'task':task,'month':row.month,'year':int(row.year),'evaluation':'chronological_2022_2024' if chronological else 'outer_heldout_year',
              'role':role,'model':choice['candidate'] if role=='selected_transfer' else role,'observed':observed,'prediction':point,'residual_observed_minus_prediction':observed-point,
              'common_calendar_days':int(row.common_calendar_days),'calendar_fraction':row.calendar_fraction,
              'fit_years_json':json.dumps(list(map(int,fit_years))),'calibration_years_json':json.dumps(list(map(int,calibration_years))),'test_years_json':json.dumps(list(map(int,test_years))),
              'inner_selection_wape':choice['inner_wape'] if role=='selected_transfer' else np.nan,'calibration_months':len(cal),'interval_status':'empirical_separate_calibration; no nominal coverage guarantee' if all(q is not None for q in radii.values()) else 'withheld_insufficient_calibration_support'}
            for level,q in radii.items():
                half=q*np.sqrt(1+point) if q is not None else np.nan
                r['lower_'+level]=max(0.,point-half) if q is not None else np.nan;r['upper_'+level]=point+half if q is not None else np.nan
            records.append(r)
    audit={'status':'evaluated','task':task,'test_years':list(map(int,test_years)),'fit_years':list(map(int,fit_years)),'calibration_years':list(map(int,calibration_years)),
       'selected_model':choice['candidate'],'candidate_inner_scores':choice['candidate_scores'],'calibration_months':len(cal)}
    return records,audit

def metrics(frame):
    y=frame.observed.to_numpy(float);p=frame.prediction.to_numpy(float);den=y.sum()
    r={'months':len(frame),'test_years':int(frame.year.nunique()),'observed_activity':float(den),'wape':float(np.abs(p-y).sum()/den) if den else None,
      'relative_bias':float((p-y).sum()/den) if den else None,'mae':float(np.abs(p-y).mean()),'rmse':float(np.sqrt(np.mean((p-y)**2)))}
    for level in ['80','90']:
        valid=frame['lower_'+level].notna()&frame['upper_'+level].notna();r['interval_months_'+level]=int(valid.sum())
        r['empirical_coverage_'+level]=float(((frame.loc[valid,'observed']>=frame.loc[valid,'lower_'+level])&(frame.loc[valid,'observed']<=frame.loc[valid,'upper_'+level])).mean()) if valid.any() else None
        r['mean_width_'+level]=float((frame.loc[valid,'upper_'+level]-frame.loc[valid,'lower_'+level]).mean()) if valid.any() else None
    return r

def annual_evaluation(predictions):
    rows=[]
    for keys,f in predictions.groupby(['configuration','task','evaluation','role','year'],sort=False):
        if f.month.nunique()!=12 or len(f)!=12:continue
        config,task,evaluation,role,year=keys
        rows.append({'configuration':config,'task':task,'evaluation':evaluation,'role':role,'year':int(year),'observed':float(f.observed.sum()),'prediction':float(f.prediction.sum()),
         'common_calendar_days':int(f.common_calendar_days.sum()),'annual_interval_status':'withheld; insufficient independent calibration years; monthly bounds not summed'})
    annual=pd.DataFrame(rows);summaries=[]
    if len(annual):
        for keys,f in annual.groupby(['configuration','task','evaluation','role'],sort=False):
            config,task,evaluation,role=keys;den=f.observed.sum();rank=float(spearmanr(f.observed,f.prediction).statistic) if len(f)>=3 and f.observed.nunique()>1 and f.prediction.nunique()>1 else None
            summaries.append({'configuration':config,'task':task,'evaluation':evaluation,'role':role,'full_12_month_years':len(f),
              'annual_common_support_wape':float((f.prediction-f.observed).abs().sum()/den) if den else None,'annual_relative_bias':float((f.prediction-f.observed).sum()/den) if den else None,
              'annual_rank_spearman':rank,'annual_interval_status':'withheld','scope':'sum on common supported calendar dates, not full physical-fire exposure'})
    return annual,pd.DataFrame(summaries)

def run(output=None,summary_path=None):
    output=Path(OUT if output is None else output);output.mkdir(parents=True,exist_ok=True);p,d,manifest=load_inputs();cache={};predictions=[];audits=[];qualifications=[];activity_stats=[]
    for config in CONFIGS:
        key=(config['resolution'],config['filter'])
        if key not in cache:cache[key]=activity_sets(p,*key)
        sets,stats=cache[key];q=qualify_months(d,sets,config['gap_mask']);q['configuration']=config['name'];qualifications.append(q);activity_stats.append({'configuration':config['name'],**stats})
        for task in TASK_SENSORS:
            data=q[q.task.eq(task)&q.eligible_month&q.eligible_year].copy();years=sorted(data.year.unique())
            for year in years:
                rows,audit=evaluate_split(data,task,[year],config['window']);predictions.extend([{**r,'configuration':config['name'],'resolution':config['resolution'],'native_filter':config['filter'],'gap_mask':config['gap_mask'],'training_window':config['window']} for r in rows]);audits.append({'configuration':config['name'],'task':task,'evaluation':'outer_heldout_year',**audit})
            rows,audit=evaluate_split(data,task,[2022,2023,2024],config['window'],True)
            predictions.extend([{**r,'configuration':config['name'],'resolution':config['resolution'],'native_filter':config['filter'],'gap_mask':config['gap_mask'],'training_window':config['window']} for r in rows]);audits.append({'configuration':config['name'],'task':task,'evaluation':'chronological_2022_2024',**audit})
        print('Evaluated configuration:',config['name'],flush=True)
    predictions=pd.DataFrame(predictions);qualification=pd.concat(qualifications,ignore_index=True)
    summaries=[]
    for keys,f in predictions.groupby(['configuration','task','evaluation','role'],sort=False):summaries.append(dict(zip(['configuration','task','evaluation','role'],keys))|metrics(f))
    summary=pd.DataFrame(summaries);annual,annual_summary=annual_evaluation(predictions)
    for name,frame in [('heldout_predictions.parquet',predictions),('monthly_metrics.parquet',summary),('annual_predictions.parquet',annual),('annual_metrics.parquet',annual_summary),('monthly_qualification.parquet',qualification),('activity_representation.parquet',pd.DataFrame(activity_stats))]:frame.to_parquet(output/name,index=False)
    (output/'split_audit.json').write_text(json.dumps(audits,indent=2,allow_nan=False)+'\n');(output/'method.json').write_text(json.dumps(POLICY,indent=2)+'\n')
    primary=summary[summary.configuration.eq('primary')&summary.evaluation.eq('outer_heldout_year')].copy()
    report={'research_id':POLICY['research_id'],'input_dataset_id':manifest['dataset_id'],'input_manifest_sha256':digest((DATA/'manifest.json').read_bytes()),
      'primary_results':primary.to_dict('records'),'new_results_do_not_replace_old_scores':True,'old_scores_status':'earlier dataset, not reused or certified here',
      'scope':'regional reference-sensor observed vegetation activity; matched calendar support only',
      'scientific_release_status':'not_enabled; coverage/overpass, uncertainty and local-allocation gates require review',
      'noaa20_gap_fill_enabled':False,'early_history_bands_enabled':False,'district_custom_area_transfer_validated':False,
      'coverage_verified':False,'production_export_enabled':False,'frontend_changed':False,'files':{}}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name!='manifest.json':raw=path.read_bytes();report['files'][path.name]={'bytes':len(raw),'sha256':digest(raw)}
    (output/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    if summary_path is not None:
        Path(summary_path).parent.mkdir(parents=True,exist_ok=True)
        Path(summary_path).write_text(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2,allow_nan=False)+'\n')
    print(primary[['task','role','months','wape','relative_bias','empirical_coverage_80','empirical_coverage_90']].to_string(index=False))
    return {'report':report,'predictions':predictions,'summary':summary,'annual':annual,'annual_summary':annual_summary,'qualification':qualification,'audits':audits,'output':output}

if __name__=='__main__':run(summary_path=ROOT/'docs/atlas_transfer_research_results.json')
