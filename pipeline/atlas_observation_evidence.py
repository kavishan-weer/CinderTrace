"""Small VIIRS standard-data observation evidence pilot; never fills archive zeros.
Public metadata discovery runs without credentials. Science screening requires
Earthdata-authorized files and is a pixel-centre diagnostic, not area completeness.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,time,urllib.request,urllib.parse,urllib.error
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'data/atlas/observation_evidence_pilot_v1'
PRODUCTS={
 'VNP14IMG':{'collection':'C2734202914-LPCLOUD','version':'002','satellite':'Suomi-NPP','kind':'fire'},
 'VJ114IMG':{'collection':'C2734197957-LPCLOUD','version':'002','satellite':'NOAA-20','kind':'fire'},
 'VNP03IMG':{'collection':'C2105092163-LAADS','version':'2','satellite':'Suomi-NPP','kind':'geolocation'},
 'VJ103IMG':{'collection':'C2105086226-LAADS','version':'2.1','satellite':'NOAA-20','kind':'geolocation'}}
DAYS={'2021-08-15':'recorded_zero_control_not_no_fire_truth',
 '2021-08-19':'positive_control', '2022-08-04':'listed_SNPP_missing_standard_date',
 '2022-08-12':'post_interruption_recovery_candidate',
 '2024-05-31':'listed_SNPP_missing_standard_date',
 '2024-06-05':'post_interruption_recovery_candidate'}
BOUNDARY_SHA='838db6bf67cb4d21df585d32483c64c9d56556d4fc216564bf4aa982c659382e'
SOURCES={
 'fire_guide':'https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.0.pdf',
 'snpp_geolocation':'https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP03IMG/',
 'noaa20_geolocation':'https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VJ103IMG',
 'cmr':'https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html'}
POLICY={'pilot_id':'lk_viirs_observation_evidence_v1','days':DAYS,'products':PRODUCTS,'sources':SOURCES,
 'sampling':'purposive schema/outage feasibility sample, not independent model validation',
 'standard_only':True,'h3_resolution':8,'candidate_time_windows_minutes':[30,60,90],
 'candidate_pairing':'all cross-sensor granule candidates within time windows; not assumed independent or one-to-one',
 'support':'pixel centres only; no footprint areas, cloud-free area fractions or complete coverage inferred',
 'screen':'fire-mask classes 5/7/8/9, nominal input QA bits 0–6, residual bowtie bit 22 absent; not an official replacement algorithm',
 'scope':'all native fire-mask classes, not vegetation-only model target; type attribution not independently available',
 'zero_rule':'missing catalogue, missing companion, failed download or screen is unavailable, never an observed zero',
 'replacement_enabled':False,'early_history_bands_enabled':False,'coverage_verified':False,'frontend_changed':False}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def acquisition(name):
    match=re.search(r'\.A(\d{7})\.(\d{4})\.',name)
    if not match:raise ValueError('Unrecognized acquisition filename')
    return '.'.join(match.groups())

def query(params,destination):
    url='https://cmr.earthdata.nasa.gov/search/granules.json?'+urllib.parse.urlencode(params)
    receipt=destination.with_suffix('.receipt.json')
    if destination.exists() and receipt.exists():
        raw=destination.read_bytes();r=json.loads(receipt.read_text())
        if r['url']!=url or r['sha256']!=sha(raw):raise ValueError('Changed metadata cache')
        return json.loads(raw),r
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'CinderTrace-observation-evidence/1.0'}),timeout=60) as response:
                raw=response.read();hits=response.headers.get('CMR-Hits')
            body=json.loads(raw)
            if not isinstance(body.get('feed',{}).get('entry'),list):raise ValueError('Unexpected CMR schema')
            r={'url':url,'sha256':sha(raw),'bytes':len(raw),'cmr_hits':int(hits) if hits is not None else None,'retrieved_utc':datetime.now(timezone.utc).isoformat()}
            destination.write_bytes(raw);receipt.write_text(json.dumps(r,indent=2)+'\n')
            return body,r
        except (urllib.error.URLError,TimeoutError):
            if attempt==3:raise
            time.sleep(min(2**attempt,4))

def normalize(entry,product,day):
    spec=PRODUCTS[product];name=entry['producer_granule_id']
    if entry.get('collection_concept_id')!=spec['collection'] or not name.startswith(product+'.'):raise ValueError('Wrong collection/product')
    urls=[l['href'] for l in entry.get('links',[]) if not l.get('inherited') and l.get('rel','').endswith('/data#') and l.get('href','').startswith('https://') and urllib.parse.urlsplit(l['href']).path.endswith('.nc')]
    if len(urls)!=1:raise ValueError('Expected one science NetCDF link')
    return {'id':entry['id'],'product':product,'satellite':spec['satellite'],'kind':spec['kind'],
     'name':name,'acquisition':acquisition(name),'date':day,'time_start':entry['time_start'],'time_end':entry['time_end'],
     'day_night':entry.get('day_night_flag','UNKNOWN'),'download_url':urls[0],
     'catalogue_size_mb':float(entry.get('granule_size',0)),'metadata_entry_sha256':sha(json.dumps(entry,sort_keys=True).encode()),
     'catalogue_footprint_only':True}

def join_companions(records):
    fire=[r for r in records if r['kind']=='fire'];result=[]
    for f in fire:
        g=[g for g in records if g['kind']=='geolocation' and g['satellite']==f['satellite'] and g['acquisition']==f['acquisition']]
        status='unique_catalogue_companion' if len(g)==1 else 'missing_companion' if not g else 'ambiguous_companion'
        if len(g)==1 and (pd.Timestamp(g[0]['time_start'])!=pd.Timestamp(f['time_start']) or pd.Timestamp(g[0]['time_end'])!=pd.Timestamp(f['time_end'])):status='time_extent_mismatch'
        result.append({'fire_id':f['id'],'geo_id':g[0]['id'] if len(g)==1 else None,'satellite':f['satellite'],'date':f['date'],'acquisition':f['acquisition'],'status':status})
    return result

def time_candidates(records):
    fire=[r for r in records if r['kind']=='fire'];rows=[]
    for a in fire:
        if a['satellite']!='Suomi-NPP':continue
        for b in fire:
            if b['satellite']!='NOAA-20' or a['date']!=b['date']:continue
            # Use separation of granule midpoints. Date-boundary candidates are out of this small pilot.
            am=pd.Timestamp(a['time_start'])+(pd.Timestamp(a['time_end'])-pd.Timestamp(a['time_start']))/2
            bm=pd.Timestamp(b['time_start'])+(pd.Timestamp(b['time_end'])-pd.Timestamp(b['time_start']))/2
            dt=abs((am-bm).total_seconds())/60
            if dt<=90:rows.append({'snpp_id':a['id'],'noaa20_id':b['id'],'date':a['date'],'midpoint_separation_minutes':dt,
             'within_30':dt<=30,'within_60':dt<=60,'within_90':True,'day_night_agrees':a['day_night']==b['day_night'] and a['day_night'] in ['DAY','NIGHT'],
             'status':'time_candidate_only_pixel_overlap_unverified'})
    return rows

def discover(boundary_path=None,output=None):
    out=Path(OUT if output is None else output);out.mkdir(parents=True,exist_ok=True);rawdir=out/'cmr';rawdir.mkdir(exist_ok=True)
    bp=Path(boundary_path or ROOT/'data/atlas/canonical_lk_2000_2024_v1/region.geojson');raw=bp.read_bytes()
    if sha(raw)!=BOUNDARY_SHA:raise ValueError('Boundary differs from verified study region')
    from shapely.geometry import shape
    region=shape(json.loads(raw)['features'][0]['geometry']);bbox=','.join(map(str,region.bounds));(out/'region.geojson').write_bytes(raw)
    records=[];counts=[]
    for day in DAYS:
        for product,spec in PRODUCTS.items():
            found=[];page=1;expected=None
            while True:
                params={'collection_concept_id':spec['collection'],'bounding_box':bbox,'temporal':day+'T00:00:00Z,'+day+'T23:59:59.999Z','page_size':200,'page_num':page}
                body,receipt=query(params,rawdir/f'{product}_{day}_{page}.json');entries=body['feed']['entry']
                if expected is None:expected=receipt['cmr_hits']
                elif receipt['cmr_hits']!=expected:raise ValueError('Catalogue changed during pagination; retry in a fresh output folder')
                found.extend(entries)
                if len(entries)<200:break
                page+=1
                if page>100:raise ValueError('Unexpected pilot catalogue size')
            if expected is not None and len(found)!=expected:raise ValueError('Incomplete CMR pagination')
            if len({e['id'] for e in found})!=len(found):raise ValueError('Duplicate CMR entries')
            # Temporal queries overlap intervals; retain granules whose start falls on the requested UTC day.
            found=[e for e in found if e['time_start'][:10]==day]
            normalized=[normalize(e,product,day) for e in found];records.extend(normalized)
            counts.append({'date':day,'role':DAYS[day],'product':product,'records':len(normalized),'status':'catalogue_listed' if normalized else 'no_catalogue_records_not_zero_observations'})
        print('Catalogued',day,flush=True)
    joins=join_companions(records);candidates=time_candidates(records)
    report={'policy':POLICY,'created_utc':datetime.now(timezone.utc).isoformat(),'boundary_sha256':sha(raw),'bbox':list(region.bounds),
     'records':records,'daily_catalogue':counts,'companions':joins,'time_candidates':candidates,
     'catalogue_size_mb':sum(r['catalogue_size_mb'] for r in records),
     'status':'metadata_only_science_screen_pending','science_files_verified':0,'usable_coverage_verified':False}
    (out/'inventory.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');(out/'method.json').write_text(json.dumps(POLICY,indent=2)+'\n')
    return report

class ScienceAccessRequired(RuntimeError):pass

def download(record,session,cache):
    """Resumable per file; stores no auth headers, cookies, tokens or passwords."""
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    filename=Path(urllib.parse.urlsplit(record['download_url']).path).name
    if filename!=record['name']+'.nc' and filename!=record['name']:raise ValueError('URL/name mismatch')
    target=cache/filename;rp=cache/(filename+'.receipt.json')
    if target.exists() and rp.exists():
        r=json.loads(rp.read_text());raw=target.read_bytes()
        if r['id']!=record['id'] or r['sha256']!=sha(raw) or r['bytes']!=len(raw):raise ValueError('Changed verified science cache')
        return target,r
    part=cache/(filename+'.part');reason='network'
    for attempt in range(4):
        try:
            with session.get(record['download_url'],stream=True,timeout=(30,180)) as response:
                if response.status_code!=200:
                    reason='HTTP '+str(response.status_code)
                    if response.status_code in (401,403):break
                    response.raise_for_status()
                expected=int(response.headers.get('Content-Length',0));digest=hashlib.sha256();n=0
                with part.open('wb') as handle:
                    for chunk in response.iter_content(1024*1024):
                        if chunk:handle.write(chunk);digest.update(chunk);n+=len(chunk)
                if expected and n!=expected:raise OSError('Incomplete content length')
            with part.open('rb') as f:signature=f.read(8)
            if signature!=b'\x89HDF\r\n\x1a\n':raise ValueError('Response is not NetCDF4/HDF5 science data')
            r={'id':record['id'],'product':record['product'],'acquisition':record['acquisition'],'bytes':n,'sha256':digest.hexdigest(),
             'retrieved_utc':datetime.now(timezone.utc).isoformat(),'http_status':200,'status':'content_length_and_signature_verified_not_provider_checksum'}
            part.replace(target);rp.write_text(json.dumps(r,indent=2)+'\n');return target,r
        except Exception as error:
            # Do not print request exceptions; they can contain provider credential redirects.
            reason=type(error).__name__
            if attempt<3:time.sleep(min(2**attempt,4))
        finally:
            if part.exists():part.unlink()
    if reason in ['HTTP 401','HTTP 403']:raise ScienceAccessRequired(f'{filename}: {reason}. Check Earthdata authorization for this provider; no zero written.')
    raise RuntimeError(f'{filename}: {reason}. No zero written. Verified prior files retained; review Earthdata/provider access.') from None

def variables(dataset,prefix=''):
    result={prefix+name:var for name,var in dataset.variables.items()}
    for name,group in dataset.groups.items():result.update(variables(group,prefix+name+'/'))
    return result

def find_variable(dataset,name):
    norm=lambda s:re.sub('[^a-z0-9]','',s.lower())
    hits=[(path,var) for path,var in variables(dataset).items() if norm(path.split('/')[-1])==norm(name)]
    if len(hits)!=1:raise ValueError('Missing or ambiguous science variable: '+name)
    return hits[0]

def screen_arrays(mask,qa,latitude,longitude,region):
    """Chunk kernel: preserve every local class; good centres are an explicit screen."""
    from shapely import intersects_xy
    m=np.ma.asarray(mask);q=np.ma.asarray(qa);lat=np.ma.asarray(latitude);lon=np.ma.asarray(longitude)
    if len(m.shape)!=2 or len({m.shape,q.shape,lat.shape,lon.shape})!=1:raise ValueError('Fire/geolocation grid mismatch')
    lat=np.ma.filled(lat.astype(float),np.nan);lon=np.ma.filled(lon.astype(float),np.nan)
    # Invalid/masked QA must never be converted to nominal (zero).
    goodgeo=np.isfinite(lat)&np.isfinite(lon)&(abs(lat)<=90)&(abs(lon)<=180)
    local=goodgeo&intersects_xy(region,lon,lat)
    mv=np.ma.filled(m.astype(float),np.nan);qv=np.ma.filled(q.astype(np.uint32),np.uint32(2**32-1))
    known=~np.ma.getmaskarray(m)&np.isfinite(mv)&np.isin(mv,np.arange(10))
    if (local&~known).any():raise ValueError('Unknown or missing local fire-mask class')
    nominal=(qv&127)==0;not_duplicate=(qv&(1<<22))==0
    clear=local&np.isin(mv,[5,7,8,9])&nominal&not_duplicate&~np.ma.getmaskarray(q)
    fires=clear&np.isin(mv,[7,8,9])
    return {'local':local,'mask':mv,'qa':qv,'qa_valid':~np.ma.getmaskarray(q),'clear':clear,'fires':fires,'latitude':lat,'longitude':lon}

def screen_file(fire_path,geo_path,record,region):
    from netCDF4 import Dataset
    import h3
    rows=[];summary={'fire_id':record['id'],'product':record['product'],'satellite':record['satellite'],'date':record['date'],
      'time_start':record['time_start'],'time_end':record['time_end'],'day_night':record['day_night'],
      'local_geolocated_centres':0,'nominal_clear_centres':0,'screened_fire_centres':0,'local_residual_bowtie_centres':0,
      'scope':'all native fire classes; no vegetation type attribution','status':'pixel_centre_screen_only_not_complete_coverage'}
    with Dataset(fire_path) as fire,Dataset(geo_path) as geo:
        fm,mask=find_variable(fire,'fire mask');fq,qa=find_variable(fire,'algorithm QA');gl,lat=find_variable(geo,'latitude');go,lon=find_variable(geo,'longitude')
        if len(mask.shape)!=2 or mask.shape!=lat.shape or mask.shape!=lon.shape or mask.shape!=qa.shape:raise ValueError('Companion grid shape mismatch')
        summary.update({'fire_mask_variable':fm,'qa_variable':fq,'latitude_variable':gl,'longitude_variable':go,'shape':list(mask.shape)})
        # Independent sparse-fire coordinates check the zero-based line/sample alignment.
        _,pl=find_variable(fire,'FP_line');_,ps=find_variable(fire,'FP_sample');_,plat=find_variable(fire,'FP_latitude');_,plon=find_variable(fire,'FP_longitude')
        alignment=[]
        for r,c,a,b in zip(pl[:100],ps[:100],plat[:100],plon[:100]):
            r=int(r);c=int(c)
            if r<0 or c<0 or r>=mask.shape[0] or c>=mask.shape[1]:raise ValueError('Invalid zero-based sparse-fire grid index')
            x=float(lat[r,c]);y=float(lon[r,c]);delta=max(abs(x-float(a)),abs(((y-float(b)+180)%360)-180))
            if not np.isfinite(delta) or delta>.01:raise ValueError('Sparse-fire geolocation does not align with companion grid')
            alignment.append(delta)
        summary['alignment_check_pixels']=len(alignment);summary['alignment_max_error_degrees']=max(alignment) if alignment else None
        summary['alignment_status']='sparse_fire_coordinates_agree' if alignment else 'no_sparse_fires_only_catalogue_time_and_shape_checks'
        for start in range(0,mask.shape[0],256):
            sl=slice(start,min(start+256,mask.shape[0]));x=screen_arrays(mask[sl,:],qa[sl,:],lat[sl,:],lon[sl,:],region)
            summary['local_geolocated_centres']+=int(x['local'].sum());summary['nominal_clear_centres']+=int(x['clear'].sum());summary['screened_fire_centres']+=int(x['fires'].sum())
            summary['local_residual_bowtie_centres']+=int((x['local']&x['qa_valid']&((x['qa']&(1<<22))!=0)).sum())
            for cls in range(10):summary['class_'+str(cls)]=summary.get('class_'+str(cls),0)+int((x['local']&(x['mask']==cls)).sum())
            ix=x['local'];la=x['latitude'][ix];lo=x['longitude'][ix]
            if not len(la):continue
            chunk=pd.DataFrame({'cell':[h3.latlng_to_cell(float(a),float(b),8) for a,b in zip(la,lo)],
              'local_centres':1,'clear_centres':x['clear'][ix].astype(int),'fire_centres':x['fires'][ix].astype(int)})
            rows.append(chunk.groupby('cell',as_index=False).sum())
    cells=pd.concat(rows).groupby('cell',as_index=False).sum() if rows else pd.DataFrame(columns=['cell','local_centres','clear_centres','fire_centres'])
    for name in ['fire_id','satellite','date','time_start','time_end']:cells[name]=summary[name]
    # Presence of a centre does not imply coverage of the full H3 cell.
    return summary,cells

def candidate_diagnostics(candidates,cells):
    rows=[]
    for c in candidates:
        base=dict(c);a=cells[cells.fire_id.eq(c['snpp_id'])];b=cells[cells.fire_id.eq(c['noaa20_id'])]
        if not len(a) or not len(b):
            base.update({'status':'one_or_both_screens_missing_or_no_regional_centres','common_clear_centre_cells':None,
              'snpp_active_cells_on_common_support':None,'noaa20_active_cells_on_common_support':None});rows.append(base);continue
        # Cell labels approximate spatial co-location; actual pixel footprints differ.
        common=a[a.clear_centres.gt(0)].merge(b[b.clear_centres.gt(0)],on='cell',suffixes=('_snpp','_noaa20'))
        base.update({'status':'coarse_cell_centre_overlap_diagnostic_not_matched_pixel_footprints',
         'common_clear_centre_cells':len(common),
         'snpp_active_cells_on_common_support':int(common.fire_centres_snpp.gt(0).sum()) if len(common) else None,
         'noaa20_active_cells_on_common_support':int(common.fire_centres_noaa20.gt(0).sum()) if len(common) else None})
        rows.append(base)
    return pd.DataFrame(rows)

def daily_screen_status(inventory,summaries):
    rows=[]
    for day in DAYS:
        for satellite in ['Suomi-NPP','NOAA-20']:
            planned=[r for r in inventory['records'] if r['kind']=='fire' and r['date']==day and r['satellite']==satellite]
            done=[r for r in summaries if r['date']==day and r['satellite']==satellite]
            all_done=bool(planned) and len(done)==len(planned)
            local=sum(r['local_geolocated_centres'] for r in done)
            supported=all_done and local>0
            rows.append({'date':day,'satellite':satellite,'catalogue_fire_granules':len(planned),'screened_granules':len(done),
                'status':'catalogue_absent_not_zero_observations' if not planned else 'incomplete_science_screen' if not all_done else 'no_local_centres_not_zero_activity' if not local else 'catalogued_granules_screened_coverage_unverified',
                'screened_fire_centres':sum(r['screened_fire_centres'] for r in done) if supported else None,
                'nominal_clear_centres':sum(r['nominal_clear_centres'] for r in done) if supported else None,
                'observing_coverage_verified':False})
    return pd.DataFrame(rows)

def run_science(inventory,session,cache,output):
    from shapely.geometry import shape
    out=Path(output);out.mkdir(parents=True,exist_ok=True);source=Path(inventory);inv=json.loads(source.read_text());region_raw=(source.parent/'region.geojson').read_bytes()
    if sha(region_raw)!=BOUNDARY_SHA:raise ValueError('Boundary changed')
    region=shape(json.loads(region_raw)['features'][0]['geometry']);lookup={r['id']:r for r in inv['records']};summaries=[];cells=[];receipts=[];failures=[]
    # Each completed swath is retained immediately, so later access/schema failures do not lose prior work.
    access_stopped=False
    for join in inv['companions']:
        if access_stopped:
            failures.append({**join,'status':'not_attempted_after_access_denial'});continue
        if join['status']!='unique_catalogue_companion':failures.append({**join,'status':'unavailable_companion'});continue
        f=lookup[join['fire_id']];g=lookup[join['geo_id']]
        try:
            fp,fr=download(f,session,cache);gp,gr=download(g,session,cache);receipts.extend([fr,gr])
            summary,cell=screen_file(fp,gp,f,region);summaries.append(summary);cells.append(cell)
            pd.DataFrame(summaries).to_parquet(out/'granule_screening.parquet',index=False)
            pd.concat(cells,ignore_index=True).to_parquet(out/'cell_centre_support.parquet',index=False)
            print('Screened',f['name'],flush=True)
        except Exception as error:
            # Error text may include authenticated URLs from a third-party library; retain safe type only.
            failures.append({**join,'status':'unavailable_science_screen','error_type':type(error).__name__})
            if isinstance(error,ScienceAccessRequired):access_stopped=True
            print('Unavailable screen:',f['name'],type(error).__name__,flush=True)
        finally:
            (out/'download_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n');(out/'failures.json').write_text(json.dumps(failures,indent=2)+'\n')
    combined=pd.concat(cells,ignore_index=True) if cells else pd.DataFrame(columns=['fire_id','cell','clear_centres','fire_centres'])
    pd.DataFrame(summaries,columns=None if summaries else ['fire_id','satellite','date','status']).to_parquet(out/'granule_screening.parquet',index=False)
    combined.to_parquet(out/'cell_centre_support.parquet',index=False)
    (out/'download_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    (out/'failures.json').write_text(json.dumps(failures,indent=2)+'\n')
    daily=daily_screen_status(inv,summaries)
    daily.to_parquet(out/'daily_screen_status.parquet',index=False)
    diagnostic=candidate_diagnostics(inv['time_candidates'],combined);diagnostic.to_parquet(out/'candidate_pair_diagnostics.parquet',index=False)
    decision={'pilot_id':POLICY['pilot_id'],'inventory_sha256':sha(source.read_bytes()),'planned_fire_granules':len(inv['companions']),
     'screened_fire_granules':len(summaries),'failed_or_unavailable':len(failures),'access_denial_stopped_downloads':access_stopped,'status':'exploratory_pixel_centre_evidence_only',
     'zero_months_restored':0,'replacement_validated':False,'gap_fill_enabled':False,'coverage_verified':False,
     'independent_uncertainty_validation_completed':False,'frontend_changed':False,
     'limitations':['Small purposive sample; no model tuning or validation scores','Granule times, not exact per-pixel observation times',
       'Coarse cell-centre overlap is not matched physical footprints or full regional area support','Candidate pairs may share granules; do not sum pair counts',
       'No vegetation type attribution: do not compare directly to vegetation-only transfer scores','Missing files and failed screens remain unavailable']}
    (out/'decision.json').write_text(json.dumps(decision,indent=2)+'\n');(out/'method.json').write_text(json.dumps(POLICY,indent=2)+'\n')
    decision['files']={}
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name not in ['manifest.json']:
            raw=path.read_bytes();decision['files'][path.name]={'bytes':len(raw),'sha256':sha(raw)}
    (out/'manifest.json').write_text(json.dumps(decision,indent=2,allow_nan=False)+'\n')
    return decision

if __name__=='__main__':
    result=discover();print(json.dumps({'records':len(result['records']),'size_mb':result['catalogue_size_mb'],'output':str(OUT)},indent=2))
