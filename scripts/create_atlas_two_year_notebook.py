"""Build the self-contained data-only expansion notebook from tested local helpers."""
from pathlib import Path
import base64,json,zlib,zipfile,hashlib
ROOT=Path(__file__).resolve().parent.parent
with zipfile.ZipFile(ROOT/'cindertrace_atlas_lk_2023_pilot.zip') as z:boundary=z.read('region.geojson')
encoded=base64.b64encode(zlib.compress(boundary)).decode();boundary_hash=hashlib.sha256(boundary).hexdigest()
cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(keepends=True)})
def code(s):cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':s.splitlines(keepends=True)})
md('''# CinderTrace — Sri Lanka 2022 and 2024 data checkpoint

The 2023 checkpoint was independently verified locally: 219 raw NASA responses, 13,366 matched observations and 48 matching monthly totals. Its ZIP SHA256 is `509afdf0418a01b248671addb4d7a221a02e0e5e275fb203aa6e170206d29077`.

This notebook extends **observed data**, without changing the frontend or generating harmonized values. It queries the mirror for the same polygon in 2022 and 2024, then independently retrieves NASA standard-product rows for advertised archive dates. It retains native confidence, quality, published type and satellite provenance. No observations are gap-filled or silently discarded.

## Run in order

1. Open in Colab or VS Code. Install dependencies; restart the kernel if the DuckDB version check asks you to.
2. Use the same free FIRMS MAP_KEY as before, entered only at the hidden prompt. No Earthdata password or additional upload is needed: the verified boundary is embedded.
3. Keep the same results folder when resuming. Each completed extraction/request is checksummed and cached. Expect roughly 500 small NASA requests across both years, depending on advertised NOAA-21 dates. A request failure stops the run, never becomes zero, and retains verified progress.
4. Save this executed notebook and the final ZIP for local verification. A discrepancy is a review item, not an automatic change to the original data.

**2022 scope:** Terra, Aqua, S-NPP and NOAA-20. **2024 scope:** those four plus NOAA-21. NASA availability is queried before planning dates. An unavailable standard stream or pre-archive dates stay explicitly unverified, with null authoritative counts. NRT mirror rows remain in the raw extract and separate diagnostics; they are never compared as standard rows or combined into a calibrated headline.

The 2024 daily grid includes February 29. Whole-year observing coverage remains unverified even when every supported query matches. Source notices describe global gaps; local impact needs observing evidence beyond hotspot detections.
''')
code('%pip -q install "duckdb>=1.5,<1.6" pandas pyarrow numpy shapely\n')
md('## 1. Set up durable output\nA fresh run folder is created the first time. Rerunning this notebook reuses its active folder. Change `NEW_RUN` to `True` only when deliberately starting a new snapshot. No Colab upload calls are used in VS Code.\n')
code('''from pathlib import Path
from datetime import datetime,timezone
from io import BytesIO
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from getpass import getpass
import base64,zlib,hashlib,json,sys,time,uuid,zipfile
import importlib.metadata as metadata
import pandas as pd
import numpy as np
import shapely
import duckdb
from IPython.display import display
assert tuple(map(int,duckdb.__version__.split('.')[:2]))==(1,5), 'Restart the kernel after installing DuckDB 1.5.x, then run from this cell.'
IN_COLAB='google.colab' in sys.modules
NEW_RUN=False
if IN_COLAB:
    from google.colab import drive
    drive.mount('/content/drive')
    BASE=Path('/content/drive/MyDrive/cindertrace_atlas/verification/lk_2022_2024')
else:
    BASE=Path.cwd()/'atlas_lk_2022_2024'
BASE.mkdir(parents=True,exist_ok=True)
active=BASE/'active_run.txt'
if NEW_RUN or not active.exists():
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    active.write_text(run_id)
RUN_ID=active.read_text().strip()
assert RUN_ID and '/' not in RUN_ID and '..' not in RUN_ID
OUT=BASE/RUN_ID;OUT.mkdir(exist_ok=True)
CACHE=OUT/'cache';CACHE.mkdir(exist_ok=True)
print('Run:',RUN_ID)
print('Results:',OUT)
''')
md('## 2. Verify the reference geometry\nThis is the exact Sri Lanka pilot polygon, not an administrative substitute.\n')
code(f'''BOUNDARY_SHA256={boundary_hash!r}
BOUNDARY_BYTES=zlib.decompress(base64.b64decode({encoded!r}))
assert hashlib.sha256(BOUNDARY_BYTES).hexdigest()==BOUNDARY_SHA256
REGION=shapely.geometry.shape(json.loads(BOUNDARY_BYTES)['features'][0]['geometry'])
assert REGION.is_valid
BBOX=(79.4,5.8,82.0,10.0)
x0,y0,x1,y1=REGION.bounds
assert BBOX[0]<=x0 and BBOX[1]<=y0 and BBOX[2]>=x1 and BBOX[3]>=y1
(OUT/'region.geojson').write_bytes(BOUNDARY_BYTES)
print('Same pilot polygon verified. Bounds:',REGION.bounds)
''')
md('## 3. Load comparison and year-planning helpers\nThese include the documented `N20` and `N21` codes. Unexpected platform codes remain errors. MODIS percentages and VIIRS confidence classes are never cross-mapped.\n')
code((ROOT/'pipeline/atlas_source_compare.py').read_text())
code((ROOT/'pipeline/atlas_two_year.py').read_text())
md('## 4. Private key and safe requests\nNo credential-bearing URL is printed or saved. Quota/network errors retain completed files; rerun after resolving the error.\n')
code('''MAP_KEY=getpass('NASA FIRMS MAP_KEY (hidden): ').strip()
assert MAP_KEY and MAP_KEY.replace('-','').isalnum(),'Enter a FIRMS MAP_KEY, not an Earthdata password.'
def fetch_bytes(url,private=False):
    last='network/timeout'
    for attempt in range(5):
        try:
            with urlopen(Request(url,headers={'User-Agent':'CinderTrace-data-checkpoint/2.0','X-Requested-With':'XMLHttpRequest'}),timeout=90) as response:
                payload=response.read()
            if private and MAP_KEY.encode() in payload:
                raise ValueError('Provider echoed a credential; response was not saved.')
            return payload
        except HTTPError as error:
            last='HTTP '+str(error.code)
            if error.code not in [429,500,502,503,504]:break
        except (URLError,TimeoutError,OSError):last='network/timeout'
        if attempt<4:time.sleep(min(2**(attempt+1),30))
    raise RuntimeError(f'Public data request failed ({last}). No zero was written. Check service/key/quota and rerun; verified progress is cached.') from None

def save_receipt(path,payload,request):
    receipt={'request':request,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
        'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    temporary=path.with_suffix(path.suffix+'.part');temporary.write_bytes(payload);temporary.replace(path)
    receipt_path=Path(str(path)+'.receipt.json');receipt_path.write_text(json.dumps(receipt,indent=2))
    return receipt

def cached_bytes(path,url,request,private=False):
    receipt_path=Path(str(path)+'.receipt.json')
    if path.exists() and receipt_path.exists():
        raw=path.read_bytes();receipt=json.loads(receipt_path.read_text())
        assert receipt['request']==request and receipt['bytes']==len(raw) and receipt['sha256']==hashlib.sha256(raw).hexdigest(), 'Cached input differs; preserve it and start a new run for review.'
        return raw,receipt
    raw=fetch_bytes(url,private=private)
    return raw,save_receipt(path,raw,request)
print('Private key entered. Request helpers ready.')
''')
md('## 5. Pin NASA archive availability and outage evidence\nArchive date availability is not cloud/overpass completeness. Source notices are retained as evidence. The inventory covers the retrieved S-NPP/Terra production tables and FIRMS missing standard dates, not every possible satellite issue. Recovery announcements are preserved in their original notice page; no exact recovery time is guessed.\n')
code('''availability_raw,availability_receipt=cached_bytes(OUT/'nasa_availability.csv',
    'https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/'+MAP_KEY+'/all',
    {'service':'NASA FIRMS data_availability','source':'all'},private=True)
AVAILABLE=availability_table(availability_raw)
PLANS,WINDOWS=plan_requests(AVAILABLE)
PLANS.to_parquet(OUT/'official_request_plan.parquet',index=False)
display(PLANS)
assert all(0<(pd.Timestamp(b)-pd.Timestamp(a)).days<=5 for _,_,a,b in WINDOWS)
print('Planned NASA requests:',len(WINDOWS))
PUBLIC={};PUBLIC_RECEIPTS={}
for label,url in PUBLIC_SOURCES.items():
    raw,receipt=cached_bytes(OUT/('source_'+label+('.json' if label=='missing' else '.html')),url,{'public_source':url})
    PUBLIC[label]=raw;PUBLIC_RECEIPTS[label]=receipt
GAPS,MISSING_DATES=parse_gap_evidence(PUBLIC)
GAPS.to_parquet(OUT/'documented_global_gaps.parquet',index=False)
MISSING_DATES.to_parquet(OUT/'upstream_missing_standard_dates.parquet',index=False)
print('Global production-gap intervals:',len(GAPS),'| listed standard missing dates:',len(MISSING_DATES))
print('Unlisted dates remain unverified; a global gap does not establish the exact lost local passes.')
''')
md('## 6. Extract the two mirror years\nEach extraction records schema, SQL, parameters, before/after source fingerprints and an independent direct count. Complete raw fields are retained, including any NRT rows. Only successful queries can emit a recorded zero. Source ETag is an object fingerprint, not a checksum. Cached extracts are checked locally; start a new run to examine a revised source snapshot.\n')
code('''con=duckdb.connect()
con.execute("SET memory_limit='2GB'");con.execute('SET threads=2')
con.execute('INSTALL httpfs');con.execute('LOAD httpfs');con.execute('INSTALL spatial');con.execute('LOAD spatial')
WHERE_SQL="""acq_date >= CAST(? AS DATE) AND acq_date < CAST(? AS DATE)
AND ST_Intersects(geometry,ST_MakeEnvelope(?,?,?,?)) AND ST_Covers(ST_GeomFromText(?),geometry)"""
EXTRACT_SQL=f"SELECT * EXCLUDE(geometry),ST_AsWKB(geometry) AS geometry_wkb,ST_X(geometry) AS audit_lon,ST_Y(geometry) AS audit_lat FROM read_parquet(?) WHERE {WHERE_SQL}"

def fingerprint(url):
    try:
        with urlopen(Request(url,method='HEAD',headers={'User-Agent':'CinderTrace-data-checkpoint/2.0'}),timeout=60) as response:
            result={k:response.headers.get(k) for k in ['ETag','Content-Length','Last-Modified']}
    except Exception:raise RuntimeError('Mirror object fingerprint request failed; rerun without inventing a snapshot.') from None
    assert result['ETag'] and result['Content-Length'],'Missing object fingerprint; stop for review.'
    return result

def validate_mirror(frame,year):
    required={'acq_datetime','acq_date','satellite','sensor','instrument','quality','confidence','confidence_pct','type','version','frp','daynight','scan','track','geometry_wkb','audit_lon','audit_lat'}
    assert required<=set(frame.columns),'Mirror schema changed.'
    times=pd.to_datetime(frame.acq_datetime,utc=True)
    assert times.dt.year.eq(year).all() and times.dt.date.eq(pd.to_datetime(frame.acq_date).dt.date).all()
    if 'year' in frame:assert frame.year.eq(year).all(),'Partition year differs from acquisition year.'
    assert frame.satellite.isin(YEAR_SATELLITES[year]).all() and frame.quality.isin(['sp','nrt']).all()
    assert frame.sensor.eq(frame.satellite.map({s:SOURCE_SENSOR[PLATFORM_SOURCE[s]] for s in YEAR_SATELLITES[year]})).all()
    geometry=shapely.from_wkb(frame.geometry_wkb.map(bytes).to_numpy())
    assert shapely.is_valid(geometry).all() and shapely.covers(REGION,geometry).all()
    assert np.allclose(shapely.get_x(geometry),frame.audit_lon,atol=1e-9,rtol=0) and np.allclose(shapely.get_y(geometry),frame.audit_lat,atol=1e-9,rtol=0)
    assert not frame.duplicated().any(),'Exact duplicate rows; retain the extract for investigation.'
    modis=frame.sensor.eq('MODIS')
    assert frame.loc[modis,'confidence_pct'].between(0,100).all()
    assert pd.to_numeric(frame.loc[modis,'confidence']).eq(frame.loc[modis,'confidence_pct']).all()
    assert frame.loc[~modis,'confidence'].isin(['l','n','h']).all() and frame.loc[~modis,'confidence_pct'].isna().all()
    assert frame.daynight.isin(['D','N']).all() and frame.loc[frame.quality.eq('sp'),'type'].isin([0,1,2,3]).all()
    assert np.isfinite(frame.frp).all() and frame.frp.ge(0).all()
    return frame

MIRRORS={};MIRROR_RECEIPTS={}
try:
    for year in YEAR_SATELLITES:
        path=OUT/f'mirror_{year}.parquet';receipt_path=OUT/f'mirror_{year}.receipt.json'
        if path.exists() and receipt_path.exists():
            receipt=json.loads(receipt_path.read_text());raw=path.read_bytes()
            assert receipt['year']==year and receipt['boundary_sha256']==BOUNDARY_SHA256
            assert receipt['sha256']==hashlib.sha256(raw).hexdigest() and receipt['bytes']==len(raw)
            frame=validate_mirror(pd.read_parquet(BytesIO(raw)),year)
            assert len(frame)==receipt['direct_count']==receipt['rows'] and receipt['source_before']==receipt['source_after']
        else:
            url=f'https://data.source.coop/portolan-mirrors/firms-catalog/detections/year={year}/detections.parquet'
            before=fingerprint(url)
            schema=con.execute('DESCRIBE SELECT * FROM read_parquet(?)',[url]).df()
            assert str(schema.set_index('column_name').loc['geometry','column_type']).startswith('GEOMETRY'),'Native geometry decoding failed.'
            assert not {'geometry_wkb','audit_lon','audit_lat'}&set(schema.column_name),'Audit column collision.'
            params=[url,f'{year}-01-01',f'{year+1}-01-01',*BBOX,REGION.wkt]
            frame=con.execute(EXTRACT_SQL,params).df();frame['geometry_wkb']=frame.geometry_wkb.map(bytes)
            direct=int(con.execute(f'SELECT count(*) FROM read_parquet(?) WHERE {WHERE_SQL}',params).fetchone()[0])
            after=fingerprint(url)
            assert before==after and len(frame)==direct,'Source/count changed; preserve this run and retry in a new run folder.'
            frame=validate_mirror(frame,year)
            temporary=path.with_suffix('.part.parquet');frame.to_parquet(temporary,index=False);temporary.replace(path)
            raw=path.read_bytes()
            receipt={'year':year,'source_url':url,'source_before':before,'source_after':after,'etag_is_not_checksum':True,
                'boundary_sha256':BOUNDARY_SHA256,'sql':EXTRACT_SQL,'parameters':params,'rows':len(frame),'direct_count':direct,
                'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'schema':schema.to_dict('records'),'retrieved_utc':datetime.now(timezone.utc).isoformat()}
            receipt_path.write_text(json.dumps(receipt,indent=2,default=str))
        MIRRORS[year]=frame;MIRROR_RECEIPTS[str(year)]=receipt
        print(year,'checked mirror rows:',len(frame));display(frame.groupby(['satellite','quality'],dropna=False).size().rename('recorded_detections').reset_index())
finally:con.close()
''')
md('## 7. Retrieve NASA standard observations\nFiles are cached per source and half-open UTC interval. Every response is parsed and clipped before its regional count is accepted. Previously cached bytes are reparsed on resume. Missing archive dates and NRT rows are not forced into the standard-product comparison.\n')
code('''OFFICIAL_PARTS={year:[] for year in YEAR_SATELLITES};REQUEST_RECEIPTS=[]
for index,(year,source,start,end) in enumerate(WINDOWS,1):
    request={'year':year,'source':source,'start_inclusive_utc':start,'end_exclusive_utc':end,'bbox':list(BBOX),'boundary_sha256':BOUNDARY_SHA256}
    stem=f'{source}_{start}_{end}';path=CACHE/(stem+'.csv')
    url='https://firms.modaps.eosdis.nasa.gov/api/area/csv/'+MAP_KEY+'/'+source+'/'+','.join(map(str,BBOX))+'/'+str((pd.Timestamp(end)-pd.Timestamp(start)).days)+'/'+start
    payload,receipt=cached_bytes(path,url,request,private=True)
    try:frame=parse_official_csv(payload,source,start,end,REGION)
    except ValueError as error:
        raise ValueError(f'Unverified NASA response for {source} {start} to {end}: {error}. Raw response retained but not counted; stop for review.') from None
    REQUEST_RECEIPTS.append({**receipt,'regional_rows':len(frame),'request_status':'csv_schema_and_scope_verified'})
    OFFICIAL_PARTS[year].append(frame)
    if index%15==0 or index==len(WINDOWS):print(f'Checked {index}/{len(WINDOWS)} requests; {sum(len(f) for parts in OFFICIAL_PARTS.values() for f in parts):,} regional standard observations.')
    time.sleep(0.25)
OFFICIALS={}
for year,parts in OFFICIAL_PARTS.items():
    assert parts,'No advertised standard sources for this year; review the availability response.'
    OFFICIALS[year]=stack_native(parts)
    OFFICIALS[year].to_parquet(OUT/f'official_{year}.parquet',index=False)
assert len(REQUEST_RECEIPTS)==len(WINDOWS)
print('All planned requests completed. Unsupported dates remain unqueried, not zero.')
''')
md('## 8. Reconcile native rows and retain unsupported observations\nComparison covers only standard mirror rows within the advertised NASA intervals. Every excluded mirror row is saved with a reason, including all NRT rows. A match on the supported interval does not certify an unsupported remainder. Different satellites are never substitutes for one another.\n')
code('''COMPARISONS={};EXCLUDED=[];source_results=[]
for year,mirror in MIRRORS.items():
    covered=pd.Series(False,index=mirror.index);times=pd.to_datetime(mirror.acq_datetime,utc=True)
    for plan in PLANS[PLANS.year.eq(year)].itertuples():
        sats=[s for s in YEAR_SATELLITES[year] if PLATFORM_SOURCE[s]==plan.source]
        mask=mirror.quality.eq('sp')&mirror.satellite.isin(sats)
        if plan.days:
            mask&=times.ge(pd.Timestamp(plan.start,tz='UTC'))&times.lt(pd.Timestamp(plan.end,tz='UTC'));covered|=mask
            official=OFFICIALS[year][OFFICIALS[year].satellite.isin(sats)]
            result=compare_native(mirror.loc[mask],official)
            source_results.append({'year':year,'source':plan.source,'archive_scope':plan.status,**{k:v for k,v in result.items() if k not in ['missing_in_mirror','extra_in_mirror','attribute_differences']}})
        else:source_results.append({'year':year,'source':plan.source,'archive_scope':plan.status,'status':'not_checked_archive_unavailable'})
    excluded=mirror.loc[~covered].copy()
    excluded['not_reconciled_reason']=np.where(excluded.quality.ne('sp'),'NRT_retained_not_compared_as_standard','outside_advertised_standard_archive_range')
    excluded.to_parquet(OUT/f'mirror_not_reconciled_{year}.parquet',index=False);EXCLUDED.append(excluded)
    result=compare_native(mirror.loc[covered],OFFICIALS[year])
    COMPARISONS[str(year)]={**result,'scope_completeness':'full_declared_year' if PLANS[PLANS.year.eq(year)].status.eq('full_year_advertised').all() else 'partial_by_advertised_archive_dates',
        'mirror_rows_not_reconciled':len(excluded),'mirror_nrt_rows':int(mirror.quality.eq('nrt').sum()),'scientific_coverage_verified':False}
    for key in ['missing_in_mirror','extra_in_mirror','attribute_differences']:
        pd.DataFrame(result[key]).to_parquet(OUT/f'{key}_{year}.parquet',index=False)
SOURCE_RESULTS=pd.DataFrame(source_results);SOURCE_RESULTS.to_parquet(OUT/'source_reconciliation.parquet',index=False)
display(SOURCE_RESULTS)
print(json.dumps({year:{k:v for k,v in report.items() if k not in ['missing_in_mirror','extra_in_mirror','attribute_differences']} for year,report in COMPARISONS.items()},indent=2))
''')
md('## 9. Daily, monthly and native filter diagnostics\nThe standard confidence grid is complete within each year/platform scope. NRT rows are preserved separately in the raw extract and unreconciled tables. Null authoritative counts mean dates were not queried; recorded zero requires a completed query. Outage flags are global evidence, not lost-fire estimates. No reference-equivalent seasons, transfer models or uncertainty bands are computed.\n')
code('''DAILY,MONTHLY,NATIVE_GRID=diagnostic_grids(MIRRORS,OFFICIALS,PLANS,GAPS,MISSING_DATES)
assert len(DAILY)==3290 and len(MONTHLY)==108 and len(NATIVE_GRID)==20112
assert len(DAILY[DAILY.date.eq('2024-02-29')])==5
assert NATIVE_GRID.recorded_detections.sum()==sum(int(m.quality.eq('sp').sum()) for m in MIRRORS.values())
DAILY.to_parquet(OUT/'daily_diagnostics.parquet',index=False)
MONTHLY.to_parquet(OUT/'monthly_diagnostics.parquet',index=False)
NATIVE_GRID.to_parquet(OUT/'native_standard_filter_grid.parquet',index=False)
conflicts=DAILY[DAILY.upstream_lists_missing_standard_data&DAILY.official_sp_detections.fillna(0).gt(0)]
conflicts.to_parquet(OUT/'missing_date_positive_record_review.parquet',index=False)
controls=[]
for event in GAPS.itertuples():
    for year,mirror in MIRRORS.items():
        times=pd.to_datetime(mirror.acq_datetime,utc=True)
        if event.start_utc.year!=year:continue
        controls.append({'year':year,'satellite':event.satellite,'start_utc':event.start_utc,'end_utc':event.end_utc,
            'mirror_standard_records_in_reported_window':int((mirror.satellite.eq(event.satellite)&mirror.quality.eq('sp')&times.ge(event.start_utc)&times.lt(event.end_utc)).sum()),
            'source_url':event.source_url,'interpretation':'global reported interval; local impact/recovery not established; no rows deleted'})
pd.DataFrame(controls).to_parquet(OUT/'outage_controls.parquet',index=False)
display(MONTHLY)
print('All raw/derived counts reconcile. Upstream missing-date entries with positive local standard rows needing review:',len(conflicts))
print('Recorded zeros remain recorded zeros; observing coverage and harmonization remain unverified.')
''')
md('## 10. Save the evidence bundle\nThe manifest hashes every included file, including raw NASA responses, availability/notice snapshots and mirror extracts. API credentials are excluded. Return this ZIP and the executed notebook; do not update the frontend or fit transfer models yet.\n')
code('''manifest={'run_id':RUN_ID,'years':[2022,2024],'scope':'Sri Lanka original pilot polygon; native observations, satellites/quality retained',
    'year_satellites':YEAR_SATELLITES,'boundary_sha256':BOUNDARY_SHA256,'bbox':list(BBOX),
    'preceding_2023_checkpoint_sha256':'509afdf0418a01b248671addb4d7a221a02e0e5e275fb203aa6e170206d29077',
    'availability_receipt':availability_receipt,'public_source_receipts':PUBLIC_RECEIPTS,'mirror_receipts':MIRROR_RECEIPTS,
    'official_request_plan':PLANS.to_dict('records'),'expected_requests':len(WINDOWS),'completed_requests':len(REQUEST_RECEIPTS),
    'request_receipts':REQUEST_RECEIPTS,'comparisons':COMPARISONS,
    'all_source_dates_advertised_full_year':bool(PLANS.status.eq('full_year_advertised').all()),
    'coverage_verified':False,'harmonization_applied':False,'production_export_enabled':False,'frontend_changed':False,
    'packages':{p:metadata.version(p) for p in ['duckdb','pandas','pyarrow','numpy','shapely']},
    'completed_utc':datetime.now(timezone.utc).isoformat(),'files':{}}
for path in sorted(OUT.rglob('*')):
    if not path.is_file() or path.name=='checkpoint_manifest.json':continue
    payload=path.read_bytes()
    assert MAP_KEY.encode() not in payload,'Credential found in output; stop before bundling.'
    manifest['files'][str(path.relative_to(OUT))]={'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
manifest_bytes=json.dumps(manifest,indent=2,default=str,allow_nan=False).encode()
assert MAP_KEY.encode() not in manifest_bytes
(OUT/'checkpoint_manifest.json').write_bytes(manifest_bytes)
ZIP_PATH=BASE/f'cindertrace_atlas_lk_2022_2024_{RUN_ID}.zip'
with zipfile.ZipFile(ZIP_PATH,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in sorted([*manifest['files'],'checkpoint_manifest.json']):archive.write(OUT/name,name)
print('Checkpoint:',ZIP_PATH)
print('SHA256:',hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest())
print('Save this executed notebook unchanged with the ZIP. A partial archive scope or mismatch remains explicit in the manifest.')
MAP_KEY=None
if IN_COLAB:
    from google.colab import files
    files.download(str(ZIP_PATH))
''')
for i,c in enumerate(cells):c['id']=f'atlas-2022-2024-{i:02d}'
notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'},'colab':{'name':'CinderTrace_Atlas_LK_2022_2024_Check.ipynb'}},'nbformat':4,'nbformat_minor':5}
path=ROOT/'notebooks/CinderTrace_Atlas_LK_2022_2024_Check.ipynb';path.write_text(json.dumps(notebook,indent=1)+'\n');print(path)
if __name__=='__main__':pass
