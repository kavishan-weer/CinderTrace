"""Reprocess verified pilot cache without network or credentials.
Nearest pixel centres are diagnostics, not physical footprint equivalence.
"""
from pathlib import Path
import hashlib,json,urllib.parse
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.optimize import linear_sum_assignment
from . import atlas_observation_evidence as e

POLICY={'audit_id':'lk_cached_pixel_pass_audit_v1','network_downloads':False,
 'pass_grouping':'same satellite/UTC date/catalogue day-night; successive intervals separated by at most six minutes; pilot edges may truncate passes',
 'pairing':'one-to-one maximum-cardinality minimum-midpoint-time assignment separately at 30/60/90 minutes; unknown/mixed day-night excluded',
 'matching':'mutual nearest nominal-clear pixel centres on sphere; 250/500 metre sensitivity; not footprint intersection or simultaneity',
 'view_screens_degrees':[None,40,60],'archive_match_metres':2,
 'archive_match':'same satellite and granule interval; mutual unique coordinate candidate within two metres; preserve ambiguous/unmatched states',
 'archive_type':'carried from uniquely matched standard observation, not independently validated burning type',
 'coverage_verified':False,'replacement_validated':False,'uncertainty_validated':False,'frontend_changed':False}
RADIUS=6371008.8

def require(ok,message):
    if not ok:raise ValueError(message)
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()
def xyz(lat,lon):
    a=np.radians(np.asarray(lat,float));b=np.radians(np.asarray(lon,float))
    return np.column_stack((np.cos(a)*np.cos(b),np.cos(a)*np.sin(b),np.sin(a)))
def chord(metres):return 2*np.sin(metres/(2*RADIUS))
def mutual_neighbours(a,b):
    if not len(a) or not len(b):return np.array([],int),np.array([],int),np.array([],float)
    aa=xyz(a.latitude,a.longitude);bb=xyz(b.latitude,b.longitude)
    da,ia=cKDTree(bb).query(aa);_,ib=cKDTree(aa).query(bb)
    ix=np.flatnonzero(ib[ia]==np.arange(len(aa)));iy=ia[ix]
    return ix,iy,2*RADIUS*np.arcsin(np.minimum(1,da[ix]/2))

def archive_match(native,archive):
    out=native.copy();out['archive_match_status']='unmatched';out['archive_observation_id']=None;out['archive_type']=pd.Series(pd.NA,index=out.index,dtype='Int64');out['archive_distance_metres']=np.nan
    proposals={};reverse={}
    for i,row in out.iterrows():
        start=pd.Timestamp(row.time_start);end=pd.Timestamp(row.time_end)
        a=archive[(archive.satellite==row.satellite)&(archive.acq_datetime>=start)&(archive.acq_datetime<end)]
        if not len(a):continue
        d=np.linalg.norm(xyz(a.latitude,a.longitude)-xyz([row.latitude],[row.longitude])[0],axis=1)
        candidates=list(a.index[d<=chord(POLICY['archive_match_metres'])]);proposals[i]=candidates
        for j in candidates:reverse.setdefault(j,[]).append(i)
    for i,choices in proposals.items():
        if not choices:continue
        if len(choices)!=1 or len(reverse[choices[0]])!=1:out.loc[i,'archive_match_status']='ambiguous';continue
        j=choices[0];a=archive.loc[j];out.loc[i,'archive_match_status']='unique_standard_observation';out.loc[i,'archive_observation_id']=a.observation_id;out.loc[i,'archive_type']=int(a.type)
        delta=np.linalg.norm(xyz([out.loc[i,'latitude']],[out.loc[i,'longitude']])-xyz([a.latitude],[a.longitude]))
        out.loc[i,'archive_distance_metres']=2*RADIUS*np.arcsin(min(1,delta/2))
    return out

def group_passes(records):
    rows=[];f=pd.DataFrame([r for r in records if r['kind']=='fire'])
    for (sat,date,flag),group in f.groupby(['satellite','date','day_night'],sort=True):
        rank=0;end=None
        for row in group.sort_values(['time_start','id']).to_dict('records'):
            start=pd.Timestamp(row['time_start']);stop=pd.Timestamp(row['time_end'])
            if end is None or start>end+pd.Timedelta(minutes=6):rank+=1
            pid=f'{sat}_{date}_{flag}_{rank:02d}'
            rows.append({'fire_id':row['id'],'pass_id':pid,'satellite':sat,'date':date,'day_night':flag,'time_start':row['time_start'],'time_end':row['time_end']})
            end=max(end,stop) if end is not None else stop
    return pd.DataFrame(rows)

def pair_passes(passes,window):
    matched=[];unmatched=[]
    for (day,flag),f in passes.groupby(['date','day_night'],sort=True):
        a=f[f.satellite.eq('Suomi-NPP')].sort_values('pass_id');b=f[f.satellite.eq('NOAA-20')].sort_values('pass_id')
        good=flag in ['DAY','NIGHT'];aids=list(a.pass_id);bids=list(b.pass_id);used=set();useda=set()
        if good and len(a) and len(b):
            at=np.array([pd.Timestamp(x).timestamp() for x in a.midpoint_utc]);bt=np.array([pd.Timestamp(x).timestamp() for x in b.midpoint_utc])
            delta=np.abs(at[:,None]-bt[None,:])/60
            eligible=(delta<=window)&a.complete_science_screen.to_numpy(bool)[:,None]&b.complete_science_screen.to_numpy(bool)[None,:]&a.local_centres.gt(0).to_numpy()[:,None]&b.local_centres.gt(0).to_numpy()[None,:]
            cost=np.concatenate([np.where(eligible,delta,1e9),np.full((len(a),len(a)),1e6)],axis=1)
            ai,bi=linear_sum_assignment(cost)
            for x,y in zip(ai,bi):
                if y>=len(b) or not eligible[x,y]:continue
                useda.add(aids[x]);used.add(bids[y]);matched.append({'window_minutes':window,'date':day,'day_night':flag,'snpp_pass':aids[x],'noaa20_pass':bids[y],'separation_minutes':float(delta[x,y])})
        for ids,usedids in [(aids,useda),(bids,used)]:
            for pid in ids:
                if pid not in usedids:unmatched.append({'window_minutes':window,'pass_id':pid,'date':day,'day_night':flag,'status':'no_eligible_one_to_one_partner'})
    return pd.DataFrame(matched,columns=['window_minutes','date','day_night','snpp_pass','noaa20_pass','separation_minutes']),pd.DataFrame(unmatched)

def degree_variable(dataset,name,shape):
    path,var=e.find_variable(dataset,name);require(var.shape==shape,'Geometry grid mismatch: '+name)
    units=str(getattr(var,'units','')).lower();require('degree' in units,'Unrecognized geometry units: '+name)
    return path,var

def extract_granule(fire_path,geo_path,record,region):
    from netCDF4 import Dataset
    native=[];support=[];bins=[];summary={'fire_id':record['id'],'satellite':record['satellite'],'date':record['date'],'time_start':record['time_start'],'time_end':record['time_end'],'day_night':record['day_night'],'local_centres':0,'clear_centres':0,'raw_fire_centres':0,'screened_fire_centres':0,'geometry_unavailable_centres':0}
    with Dataset(fire_path) as fire,Dataset(geo_path) as geo:
        _,mask=e.find_variable(fire,'fire mask');_,qa=e.find_variable(fire,'algorithm QA');_,lat=e.find_variable(geo,'latitude');_,lon=e.find_variable(geo,'longitude')
        require(mask.shape==qa.shape==lat.shape==lon.shape,'Native grid mismatch')
        _,view=degree_variable(geo,'sensor_zenith',mask.shape);_,solar=degree_variable(geo,'solar_zenith',mask.shape)
        # Sparse arrays are independently checked against every local fire-mask location.
        sparse={}
        for name in ['FP_line','FP_sample','FP_latitude','FP_longitude','FP_confidence','FP_ViewZenAng','FP_SolZenAng']:
            _,var=e.find_variable(fire,name);sparse[name]=np.ma.asarray(var[:])
        lengths={len(v) for v in sparse.values()};require(len(lengths)==1,'Sparse-array length mismatch')
        byindex={}
        for k,(r,c) in enumerate(zip(sparse['FP_line'],sparse['FP_sample'])):
            key=(int(r),int(c));require(key not in byindex,'Duplicate sparse fire index');byindex[key]=k
        seen=set()
        for start in range(0,mask.shape[0],256):
            sl=slice(start,min(start+256,mask.shape[0]));x=e.screen_arrays(mask[sl,:],qa[sl,:],lat[sl,:],lon[sl,:],region)
            v=np.ma.filled(np.ma.asarray(view[sl,:]).astype(float),np.nan);s=np.ma.filled(np.ma.asarray(solar[sl,:]).astype(float),np.nan)
            valid=np.isfinite(v)&np.isfinite(s)&(v>=0)&(v<=90)&(s>=0)&(s<=180)
            ix=x['local'];summary['local_centres']+=int(ix.sum());summary['clear_centres']+=int(x['clear'].sum());summary['screened_fire_centres']+=int(x['fires'].sum());summary['geometry_unavailable_centres']+=int((ix&~valid).sum())
            raw=ix&np.isin(x['mask'],[7,8,9]);summary['raw_fire_centres']+=int(raw.sum())
            for r,c in zip(*np.where(raw)):
                key=(start+int(r),int(c));require(key in byindex,'Fire mask location absent from sparse arrays');k=byindex[key];seen.add(key)
                delta=max(abs(float(sparse['FP_latitude'][k])-x['latitude'][r,c]),abs(float(sparse['FP_longitude'][k])-x['longitude'][r,c]))
                require(np.isfinite(delta) and delta<=.01,'Local sparse geolocation mismatch')
                require(int(sparse['FP_confidence'][k])==int(x['mask'][r,c]),'Sparse confidence differs from mask')
                bits=int(x['qa'][r,c]);goodqa=bool(x['qa_valid'][r,c]);native.append({'fire_id':record['id'],'satellite':record['satellite'],'date':record['date'],'time_start':record['time_start'],'time_end':record['time_end'],
                 'line':key[0],'sample':key[1],'latitude':float(sparse['FP_latitude'][k]),'longitude':float(sparse['FP_longitude'][k]),'confidence_class':int(x['mask'][r,c]),'qa':bits,'qa_valid':goodqa,'geolocation_latitude':float(x['latitude'][r,c]),'geolocation_longitude':float(x['longitude'][r,c]),'coordinate_difference_degrees':float(delta),
                 'screen_exclusion_reason':','.join((["masked_qa"] if not goodqa else [])+(["non_nominal_input"] if goodqa and bits&127 else [])+(["residual_bowtie"] if goodqa and bits&(1<<22) else [])) or 'retained',
                 'input_quality_nominal':goodqa and (bits&127)==0,'residual_bowtie':bool(bits&(1<<22)) if goodqa else None,'screened_fire':bool(x['fires'][r,c]),
                 'sensor_zenith_degrees':float(v[r,c]) if valid[r,c] else np.nan,'solar_zenith_degrees':float(s[r,c]) if valid[r,c] else np.nan,
                 'sparse_view_zenith_degrees':float(sparse['FP_ViewZenAng'][k]),'sparse_solar_zenith_degrees':float(sparse['FP_SolZenAng'][k]),'time_basis':'granule_interval_not_pixel_time'})
            # Retain all local nominal-clear centres, including unknown geometry,
            # in derived cache; pair screens explicitly require known geometry.
            take=x['clear'];rr,cc=np.where(take)
            if len(rr):support.append(pd.DataFrame({'latitude':x['latitude'][take].astype('float32'),'longitude':x['longitude'][take].astype('float32'),
              'line':(rr+start).astype('int32'),'sample':cc.astype('int16'),'fire':x['fires'][take],
              'sensor_zenith_degrees':np.where(valid[take],v[take],np.nan).astype('float32'),'solar_zenith_degrees':np.where(valid[take],s[take],np.nan).astype('float32')}))
            for label,lo,hi in [('0_20',0,20),('20_40',20,40),('40_60',40,60),('60_90',60,91)]:
                selected=ix&valid&(v>=lo)&(v<hi);bins.append({'fire_id':record['id'],'view_bin':label,'local_centres':int(selected.sum()),'clear_centres':int((selected&x['clear']).sum()),'screened_fire_centres':int((selected&x['fires']).sum())})
        # Check every sparse pixel inside the exact study geometry is represented.
        from shapely import intersects_xy
        inside=intersects_xy(region,np.asarray(sparse['FP_longitude'],float),np.asarray(sparse['FP_latitude'],float))
        expected={(int(sparse['FP_line'][k]),int(sparse['FP_sample'][k])) for k in np.flatnonzero(inside)}
        require(seen==expected,'Local sparse/mask fire sets differ')
    columns=['fire_id','satellite','date','time_start','time_end','line','sample','latitude','longitude','confidence_class','qa','qa_valid','geolocation_latitude','geolocation_longitude','coordinate_difference_degrees','screen_exclusion_reason','input_quality_nominal','residual_bowtie','screened_fire','sensor_zenith_degrees','solar_zenith_degrees','sparse_view_zenith_degrees','sparse_solar_zenith_degrees','time_basis']
    n=pd.DataFrame(native,columns=columns);p=pd.concat(support,ignore_index=True) if support else pd.DataFrame(columns=['latitude','longitude','line','sample','fire','sensor_zenith_degrees','solar_zenith_degrees'])
    b=pd.DataFrame(bins).groupby(['fire_id','view_bin'],as_index=False).sum() if bins else pd.DataFrame()
    return summary,n,p,b

def pair_diagnostics(a,b):
    results=[]
    for cap in POLICY['view_screens_degrees']:
        def screen(f):
            ok=f.sensor_zenith_degrees.notna()&f.solar_zenith_degrees.notna()
            if cap is not None:ok&=f.sensor_zenith_degrees.le(cap)
            return f[ok].reset_index(drop=True)
        aa=screen(a);bb=screen(b);ix,iy,d=mutual_neighbours(aa,bb)
        for radius in [250,500]:
            keep=d<=radius;matched=int(keep.sum());row={'view_cap_degrees':cap,'distance_cap_metres':radius,'snpp_eligible_clear_centres':len(aa),'noaa20_eligible_clear_centres':len(bb),
             'mutual_nearest_clear_centre_pairs':matched,'snpp_fire_centres_on_support':int(aa.iloc[ix[keep]].fire.sum()) if matched else None,
             'noaa20_fire_centres_on_support':int(bb.iloc[iy[keep]].fire.sum()) if matched else None,
             'median_separation_metres':float(np.median(d[keep])) if matched else None,'status':'point_centre_diagnostic_not_physical_footprint_match'}
            results.append(row)
    return pd.DataFrame(results)

def cached_science_files(inv,receipts,cache):
    cache=Path(cache);rmap={r['id']:r for r in receipts};paths={}
    for index,r in enumerate(inv['records'],1):
        require(r['id'] in rmap,'Missing expected science receipt');receipt=rmap[r['id']];name=Path(urllib.parse.urlsplit(r['download_url']).path).name
        require(name==r['name']+'.nc' or name==r['name'],'Cache filename mismatch');path=cache/name
        require(path.exists(),'Missing cached file: '+name+'; locate the original science_cache, no download attempted')
        require(path.stat().st_size==receipt['bytes'] and file_sha(path)==receipt['sha256'],'Cached science file differs: '+name)
        paths[r['id']]=path
        if index%8==0 or index==len(inv['records']):print('Verified cached science files',index,'/',len(inv['records']),flush=True)
    return paths

def run(inv,receipts,boundary,archive,previous_granules,cache,output,derived,method_hash):
    from shapely.geometry import shape
    require(e.sha(boundary)==e.BOUNDARY_SHA,'Boundary changed');region=shape(json.loads(boundary)['features'][0]['geometry'])
    paths=cached_science_files(inv,receipts,cache);output=Path(output);output.mkdir(parents=True,exist_ok=True);derived=Path(derived);derived.mkdir(parents=True,exist_ok=True)
    lookup={r['id']:r for r in inv['records']};rmap={r['id']:r for r in receipts};summaries=[];native=[];bins=[];failures=[];support_paths={}
    for join in inv['companions']:
        f=lookup[join['fire_id']];g=lookup[join['geo_id']];key=e.sha(f['id'].encode())[:20];folder=derived/key;folder.mkdir(exist_ok=True)
        signature={'method_sha256':method_hash,'fire_sha256':rmap[f['id']]['sha256'],'geo_sha256':rmap[g['id']]['sha256']};checkpoint=folder/'checkpoint.json'
        try:
            if checkpoint.exists():
                old=json.loads(checkpoint.read_text());require(old['signature']==signature,'Derived cache method/input changed; use a fresh derived folder')
                for name,h in old['hashes'].items():require(file_sha(folder/name)==h,'Derived cache changed')
                summary=json.loads((folder/'summary.json').read_text());n=pd.read_parquet(folder/'native.parquet');b=pd.read_parquet(folder/'bins.parquet')
            else:
                summary,n,p,b=extract_granule(paths[f['id']],paths[g['id']],f,region)
                n.to_parquet(folder/'native.parquet',index=False);p.to_parquet(folder/'clear_centres.parquet',index=False);b.to_parquet(folder/'bins.parquet',index=False);(folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
                checkpoint.write_text(json.dumps({'signature':signature,'hashes':{name:file_sha(folder/name) for name in ['native.parquet','clear_centres.parquet','bins.parquet','summary.json']}},indent=2)+'\n')
            previous=previous_granules[previous_granules.fire_id.eq(f['id'])].iloc[0]
            require(summary['local_centres']==previous.local_geolocated_centres and summary['clear_centres']==previous.nominal_clear_centres and summary['screened_fire_centres']==previous.screened_fire_centres,'Reprocessed screening differs from completed pilot')
            require(summary['raw_fire_centres']==previous[['class_7','class_8','class_9']].sum(),'Reprocessed native count differs')
            summaries.append(summary);native.append(n);bins.append(b);support_paths[f['id']]=folder/'clear_centres.parquet';print('Reprocessed',f['name'],flush=True)
        except Exception as error:
            failures.append({'fire_id':f['id'],'error_type':type(error).__name__,'reason':str(error)[:240]});print('Unavailable cached audit:',f['name'],type(error).__name__,flush=True)
        (output/'failures.json').write_text(json.dumps(failures,indent=2)+'\n')
    members=group_passes(inv['records']);summary=pd.DataFrame(summaries);pass_rows=[]
    for pid,group in members.groupby('pass_id',sort=True):
        local=summary[summary.fire_id.isin(group.fire_id)] if len(summary) else pd.DataFrame();start=min(pd.Timestamp(x) for x in group.time_start);end=max(pd.Timestamp(x) for x in group.time_end)
        pass_rows.append({'pass_id':pid,'satellite':group.iloc[0].satellite,'date':group.iloc[0].date,'day_night':group.iloc[0].day_night,'time_start':start.isoformat(),'time_end':end.isoformat(),'midpoint_utc':(start+(end-start)/2).isoformat(),
         'granules':len(group),'complete_science_screen':len(local)==len(group),'local_centres':int(local.local_centres.sum()) if len(local)==len(group) else None,'nominal_clear_centres':int(local.clear_centres.sum()) if len(local)==len(group) and local.local_centres.sum()>0 else None,'native_fire_centres':int(local.raw_fire_centres.sum()) if len(local)==len(group) and local.local_centres.sum()>0 else None,'screened_fire_centres':int(local.screened_fire_centres.sum()) if len(local)==len(group) and local.local_centres.sum()>0 else None})
    passes=pd.DataFrame(pass_rows);matched=[];unmatched=[];diagnostics=[];done_pairs={}
    def pass_support(pid):
        files=[support_paths[i] for i in members[members.pass_id.eq(pid)].fire_id if i in support_paths]
        return pd.concat([pd.read_parquet(p) for p in files],ignore_index=True) if files else pd.DataFrame(columns=['latitude','longitude','fire','sensor_zenith_degrees','solar_zenith_degrees'])
    for window in [30,60,90]:
        pairs,un=pair_passes(passes,window);matched.append(pairs);unmatched.append(un)
        for row in pairs.to_dict('records'):
            key=(row['snpp_pass'],row['noaa20_pass'])
            if key not in done_pairs:done_pairs[key]=pair_diagnostics(pass_support(key[0]),pass_support(key[1]));print('Compared pass centres',key,flush=True)
            d=done_pairs[key].copy()
            for name,value in row.items():d[name]=value
            diagnostics.append(d)
    native_frame=pd.concat(native,ignore_index=True) if native else pd.DataFrame(columns=['fire_id','satellite','latitude','longitude','time_start','time_end'])
    typed=archive_match(native_frame,archive).merge(members[['fire_id','pass_id']],on='fire_id',how='left',validate='many_to_one');frames={'native_fire_pixel_audit':typed,'granule_audit':summary,'view_geometry_bins':pd.concat(bins,ignore_index=True) if bins else pd.DataFrame(),
     'pass_membership':members,'pass_inventory':passes,'matched_passes':pd.concat(matched,ignore_index=True),'unmatched_passes':pd.concat(unmatched,ignore_index=True),
     'mutual_centre_diagnostics':pd.concat(diagnostics,ignore_index=True) if diagnostics else pd.DataFrame()}
    for name,frame in frames.items():frame.to_parquet(output/(name+'.parquet'),index=False)
    unmatched_archive=archive[~archive.observation_id.isin(typed.archive_observation_id.dropna())];unmatched_archive.to_parquet(output/'unmatched_standard_observations.parquet',index=False)
    report={'audit_id':POLICY['audit_id'],'input_science_files':len(paths),'granules_reprocessed':len(summary),'granules_failed':len(failures),'native_regional_fire_pixels':len(typed),
      'unique_archive_matches':int(typed.archive_match_status.eq('unique_standard_observation').sum()),'ambiguous_archive_matches':int(typed.archive_match_status.eq('ambiguous').sum()),'unmatched_standard_observations':len(unmatched_archive),
      'status':'exploratory_pass_and_point_audit_only','coverage_verified':False,'replacement_validated':False,'uncertainty_validated':False,'frontend_changed':False,'network_downloads':0,
      'limitations':['Only six purposively sampled dates','Point-centre proximity is not physical footprint coverage','Granule intervals, not exact pixel observation times','Type attribution carried from standard archive, not independent fire truth','Window/view/distance sensitivities are not independent validation samples']}
    (output/'decision.json').write_text(json.dumps(report,indent=2)+'\n');(output/'method.json').write_text(json.dumps(POLICY,indent=2)+'\n')
    (output/'manifest.json').write_text(json.dumps({'decision':report,'files':{p.name:{'bytes':p.stat().st_size,'sha256':file_sha(p)} for p in sorted(output.iterdir()) if p.is_file() and p.name!='manifest.json'}},indent=2)+'\n')
    return report
