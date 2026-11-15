"""Generate a new notebook; never overwrite executed checkpoints or frontend files."""
from pathlib import Path
import ast,base64,hashlib,json,zipfile,zlib
ROOT=Path(__file__).resolve().parent.parent
with zipfile.ZipFile(ROOT/'cindertrace_atlas_lk_2023_pilot.zip') as z:boundary=z.read('region.geojson')
parser=(ROOT/'pipeline/atlas_source_compare.py').read_text()
helper_module=(ROOT/'pipeline/atlas_two_year.py').read_text();helper_ast=ast.parse(helper_module)
keep={'PLATFORM_SOURCE','SOURCE_SENSOR','PUBLIC_SOURCES','EvidenceRows','evidence_rows','availability_table','stack_native'}
segments=['from html.parser import HTMLParser']
for node in helper_ast.body:
 name=getattr(node,'name',None)
 if isinstance(node,ast.Assign):name=next((t.id for t in node.targets if isinstance(t,ast.Name)),None)
 if name in keep:segments.append(ast.get_source_segment(helper_module,node))
helpers='\n\n'.join(segments)+'\n'
history='\n'.join(line for line in (ROOT/'pipeline/atlas_history.py').read_text().splitlines() if not line.startswith('from .'))+'\n'
helper_sha=hashlib.sha256((parser+helpers+history).encode()).hexdigest()
benchmark=json.loads((ROOT/'docs/atlas_canonical_benchmark.json').read_text())
benchmark_ref={k:benchmark[k] for k in ['dataset_id','observations','year_counts','source_checkpoints','boundary_sha256']}
cells=[]
def md(s):cells.append({'cell_type':'markdown','metadata':{},'source':s.splitlines(keepends=True)})
def code(s):cells.append({'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],'source':s.splitlines(keepends=True)})
md('''# CinderTrace — earlier Sri Lanka standard-data rebuild (2000–2021)

Build a **separate observed-standard history** using the verified source rules. NASA FIRMS standard responses are the canonical input. Mirror standard rows are comparison evidence; mirror NRT is retained only for audit, never appended to standard data or used as a gap filler.

**No frontend changes. No calibration, medians, seasons, trend claims, satellite replacement or uncertainty bands.** The existing verified 2022–2024 benchmark remains outside this notebook's target years and output folders.

## How to run

1. Run cells in order in Colab or VS Code. Restart the kernel after installation if the DuckDB version check requests it.
2. Enter your existing FIRMS MAP_KEY at the hidden prompt. No Earthdata password or input upload is needed; the original polygon is embedded.
3. The first batch is **2000, 2001 and 2002**. Each completed year is packaged immediately. Downloads and completion manifests are checksummed, so a later failure does not lose earlier years.
4. Save the executed notebook and return the three year ZIPs plus the small progress ZIP for review before processing more years.
5. To continue in the same runtime, rerun **Step 6** and **Step 7**; the next three incomplete years are selected automatically. After a new runtime, run all cells in order again with `NEW_RUN=False`. Keep the same results folder.

All 2000–2021 years are planned, but only three are processed per invocation. There are roughly 2,500 small NASA requests for the full history; the actual number is derived from pinned source availability. One-second pacing and resumable caches limit unnecessary requests. A quota/network failure stops cleanly; wait for the service/quota to recover and resume.

**Interpretation:** dates outside a supported archive/platform interval are unavailable, not zero. A partial month's full-month total stays null. The shared MODIS stream does not make Aqua available before its reported first light (July 4, 2002); that lower bound is recorded with its NASA source, not inferred from Sri Lanka's first hotspot. Observing coverage is unverified on positive and zero dates alike. Raw totals across changing satellites are not harmonized.
''')
code('%pip -q install "duckdb>=1.5,<1.6" pandas pyarrow numpy shapely\n')
md('## 1. Dedicated run folder and immutable run contract\nThis folder is separate from all prior checkpoints. Leave `NEW_RUN=False` when resuming. `BATCH_SIZE=3` limits the next processing invocation, not the full target history.\n')
code(f'''from pathlib import Path
from datetime import datetime,timezone
from io import BytesIO
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from getpass import getpass
import base64,zlib,hashlib,json,sys,time,uuid,zipfile,shutil
import importlib.metadata as metadata
import pandas as pd
import numpy as np
import shapely
import duckdb
from IPython.display import display
assert tuple(map(int,duckdb.__version__.split('.')[:2]))==(1,5),'Restart the kernel after installing DuckDB 1.5.x, then resume from this cell.'
IN_COLAB='google.colab' in sys.modules
NEW_RUN=False
BATCH_SIZE=3
REQUEST_PAUSE_SECONDS=1.0
BENCHMARK_REFERENCE={benchmark_ref!r}
HELPER_CODE_SHA256={helper_sha!r}
if IN_COLAB:
    from google.colab import drive
    drive.mount('/content/drive')
    BASE=Path('/content/drive/MyDrive/cindertrace_atlas/rebuild/lk_history_2000_2021')
else:
    BASE=Path.cwd()/'atlas_lk_history_2000_2021'
BASE.mkdir(parents=True,exist_ok=True)
active=BASE/'active_run.txt'
if NEW_RUN or not active.exists():active.write_text(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8])
RUN_ID=active.read_text().strip()
assert RUN_ID and '/' not in RUN_ID and '..' not in RUN_ID
OUT=BASE/RUN_ID;OUT.mkdir(exist_ok=True)
(OUT/'years').mkdir(exist_ok=True);(OUT/'snapshots').mkdir(exist_ok=True)
print('Run:',RUN_ID)
print('Results:',OUT)
print('Verified 2022–2024 benchmark is referenced only; no benchmark files will be written or re-downloaded.')
''')
md('## 2. Original polygon and tested data helpers\nThe geometry SHA256 must match the benchmark. Helpers retain native confidence and processing quality.\n')
code(f'''BOUNDARY_BYTES=zlib.decompress(base64.b64decode({base64.b64encode(zlib.compress(boundary)).decode()!r}))
BOUNDARY_SHA256={hashlib.sha256(boundary).hexdigest()!r}
assert hashlib.sha256(BOUNDARY_BYTES).hexdigest()==BOUNDARY_SHA256==BENCHMARK_REFERENCE['boundary_sha256']
REGION=shapely.geometry.shape(json.loads(BOUNDARY_BYTES)['features'][0]['geometry'])
BBOX=(79.4,5.8,82.0,10.0)
assert REGION.is_valid
x0,y0,x1,y1=REGION.bounds
assert BBOX[0]<=x0 and BBOX[1]<=y0 and BBOX[2]>=x1 and BBOX[3]>=y1
''')
code(parser);code(helpers);code(history)
code('''CONTRACT={'run_id':RUN_ID,'policy':HISTORY_POLICY,'target_years':HISTORY_YEARS,'bbox':list(BBOX),
          'boundary_sha256':BOUNDARY_SHA256,'helper_code_sha256':HELPER_CODE_SHA256,'benchmark_reference':BENCHMARK_REFERENCE,'audit_mirror':True}
contract_path=OUT/'run_contract.json'
if contract_path.exists():assert json.loads(contract_path.read_text())==CONTRACT,'Run contract changed; preserve this run and start a new one.'
else:contract_path.write_text(json.dumps(CONTRACT,indent=2))
(OUT/'region.geojson').write_bytes(BOUNDARY_BYTES)
assert max(HISTORY_YEARS)==2021 and not set(HISTORY_YEARS)&{2022,2023,2024}
print('History contract and reference polygon verified.')
''')
md('## 3. Private MAP_KEY and safe cached requests\nThe key is runtime-only. Every cached file needs an identical request contract and matching checksum. No credential-bearing URLs or provider errors are printed.\n')
code('''MAP_KEY=getpass('NASA FIRMS MAP_KEY (hidden): ').strip()
assert MAP_KEY and MAP_KEY.replace('-','').isalnum(),'Enter a FIRMS MAP_KEY, not an Earthdata password.'
def fetch_bytes(url,private=False):
    status='network/timeout'
    for attempt in range(5):
        try:
            with urlopen(Request(url,headers={'User-Agent':'CinderTrace-history-checkpoint/1.0','X-Requested-With':'XMLHttpRequest'}),timeout=90) as response:payload=response.read()
            if private and MAP_KEY.encode() in payload:raise ValueError('Credential echoed by provider; response was not saved.')
            return payload
        except HTTPError as error:
            status='HTTP '+str(error.code)
            if error.code not in [429,500,502,503,504]:break
        except (URLError,TimeoutError,OSError):status='network/timeout'
        if attempt<4:time.sleep(min(2**(attempt+1),30))
    raise RuntimeError(f'Data request failed ({status}); no zero was written. Wait for service/quota recovery, then resume. Verified files and completed year ZIPs remain cached.') from None

def cached_bytes(path,url,request,private=False):
    path=Path(path);receipt_path=Path(str(path)+'.receipt.json')
    if path.exists() and receipt_path.exists():
        raw=path.read_bytes();r=json.loads(receipt_path.read_text())
        assert r['request']==request and r['bytes']==len(raw) and r['sha256']==digest(raw),'Cached input changed; preserve it and start a fresh run for review.'
        return raw,r
    raw=fetch_bytes(url,private=private)
    r={'request':request,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(raw),'sha256':digest(raw)}
    temporary=Path(str(path)+'.part');temporary.write_bytes(raw);temporary.replace(path)
    receipt_path.write_text(json.dumps(r,indent=2))
    return raw,r
print('Private key entered; cached request helpers ready.')
''')
md('## 4. Pin availability and public outage snapshots\nThese snapshots stay fixed for this run. A new snapshot needs a new run. Historical notice rows that cannot be parsed are retained explicitly; they are not silently interpreted as an absence of outages. Neither the parsed inventory nor archive date metadata certifies complete local coverage.\n')
code('''snap=OUT/'snapshots'
raw,AVAILABILITY_RECEIPT=cached_bytes(snap/'nasa_availability.csv',
    'https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/'+MAP_KEY+'/all',{'service':'NASA FIRMS data_availability','source':'all'},private=True)
AVAILABLE=availability_table(raw)
PLANS,WINDOWS=history_plan(AVAILABLE,HISTORY_YEARS)
PLANS.to_parquet(OUT/'official_history_plan.parquet',index=False)
PUBLIC={};PUBLIC_RECEIPTS={}
for label,url in PUBLIC_SOURCES.items():
    name=label+('.json' if label=='missing' else '.html')
    PUBLIC[label],PUBLIC_RECEIPTS[label]=cached_bytes(snap/name,url,{'public_source':url})
GAPS,MISSING_DATES,UNPARSED_EVIDENCE=history_evidence(PUBLIC,HISTORY_YEARS)
GAPS.to_parquet(OUT/'documented_global_gaps.parquet',index=False)
MISSING_DATES.to_parquet(OUT/'upstream_missing_standard_dates.parquet',index=False)
UNPARSED_EVIDENCE.to_parquet(OUT/'unparsed_outage_evidence.parquet',index=False)
print('Target years:',HISTORY_YEARS[0],'through',HISTORY_YEARS[-1],'| planned NASA requests:',len(WINDOWS))
print('Parsed global intervals:',len(GAPS),'| listed missing standard dates:',len(MISSING_DATES),'| unparsed evidence rows:',len(UNPARSED_EVIDENCE))
display(PLANS[PLANS.year.isin([2000,2002,2012,2018,2021])])
''')
md('## 5. Year processing and immediate evidence packaging\nEach year uses NASA standard responses as canonical input. The complete mirror extract and NRT rows remain in the year audit files. A mirror mismatch stays visible and does not cause NRT-to-standard relabelling. Every canonical row has a raw response hash and zero-based parsed CSV row ordinal. Repeated native identities stop for review.\n')
code('''def mirror_fingerprint(url):
    try:
        with urlopen(Request(url,method='HEAD',headers={'User-Agent':'CinderTrace-history-checkpoint/1.0'}),timeout=60) as response:
            r={key:response.headers.get(key) for key in ['ETag','Content-Length','Last-Modified']}
    except Exception:raise RuntimeError('Mirror fingerprint request failed; no snapshot was invented. Resume after resolving access/service.') from None
    assert r['ETag'] and r['Content-Length'],'Incomplete source fingerprint; stop for review.'
    return r

def capture_mirror(year,folder):
    path=folder/'mirror.parquet';receipt_path=folder/'mirror.receipt.json'
    if path.exists() and receipt_path.exists():
        r=json.loads(receipt_path.read_text());raw=path.read_bytes()
        assert r['year']==year and r['boundary_sha256']==BOUNDARY_SHA256 and r['bytes']==len(raw) and r['sha256']==digest(raw)
        f=history_mirror_valid(pd.read_parquet(BytesIO(raw)),year,REGION)
        assert len(f)==r['rows']==r['direct_count'] and r['source_before']==r['source_after']
        return f,r
    url=f'https://data.source.coop/portolan-mirrors/firms-catalog/detections/year={year}/detections.parquet'
    before=mirror_fingerprint(url);con=duckdb.connect()
    try:
        con.execute("SET memory_limit='2GB'");con.execute('SET threads=2')
        con.execute('INSTALL httpfs');con.execute('LOAD httpfs');con.execute('INSTALL spatial');con.execute('LOAD spatial')
        schema=con.execute('DESCRIBE SELECT * FROM read_parquet(?)',[url]).df()
        assert str(schema.set_index('column_name').loc['geometry','column_type']).startswith('GEOMETRY'),'Native geometry decoding failed.'
        assert not {'geometry_wkb','audit_lon','audit_lat'}&set(schema.column_name)
        where="acq_date >= CAST(? AS DATE) AND acq_date < CAST(? AS DATE) AND ST_Intersects(geometry,ST_MakeEnvelope(?,?,?,?)) AND ST_Covers(ST_GeomFromText(?),geometry)"
        sql=f'SELECT * EXCLUDE(geometry),ST_AsWKB(geometry) AS geometry_wkb,ST_X(geometry) AS audit_lon,ST_Y(geometry) AS audit_lat FROM read_parquet(?) WHERE {where}'
        params=[url,f'{year}-01-01',f'{year+1}-01-01',*BBOX,REGION.wkt]
        f=con.execute(sql,params).df();f['geometry_wkb']=f.geometry_wkb.map(bytes)
        direct=int(con.execute(f'SELECT count(*) FROM read_parquet(?) WHERE {where}',params).fetchone()[0])
        after=mirror_fingerprint(url)
        assert before==after and len(f)==direct,'Mirror source/count changed; stop and start a new snapshot.'
        history_mirror_valid(f,year,REGION)
    finally:con.close()
    temporary=folder/'mirror.part.parquet';f.to_parquet(temporary,index=False);temporary.replace(path);raw=path.read_bytes()
    r={'year':year,'source_url':url,'source_before':before,'source_after':after,'etag_is_not_checksum':True,
       'sql':sql,'parameters':params,'boundary_sha256':BOUNDARY_SHA256,'rows':len(f),'direct_count':direct,'schema':schema.to_dict('records'),
       'bytes':len(raw),'sha256':digest(raw),'retrieved_utc':datetime.now(timezone.utc).isoformat()}
    receipt_path.write_text(json.dumps(r,indent=2,default=str));return f,r

def package_year(folder):
    m=verify_year_files(folder);year=m['year']
    destination=OUT/f'cindertrace_atlas_lk_history_{year}_{RUN_ID}.zip'
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*m['files'],'year_manifest.json']):archive.write(folder/name,name)
    receipt={'year':year,'zip_name':destination.name,'bytes':destination.stat().st_size,'sha256':digest(destination.read_bytes()),
             'canonical_standard_rows':m['canonical_standard_rows'],'completed_utc':m['completed_utc']}
    (OUT/f'year_{year}_zip_receipt.json').write_text(json.dumps(receipt,indent=2))
    return receipt

def process_year(year):
    assert year in HISTORY_YEARS and year<2022
    folder=OUT/'years'/str(year);folder.mkdir(exist_ok=True)
    if (folder/'year_manifest.json').exists():
        m=verify_year_files(folder)
        assert m['run_contract_sha256']==digest((OUT/'run_contract.json').read_bytes()),'Completed year belongs to a different contract.'
        return package_year(folder)
    cache=folder/'nasa_cache';cache.mkdir(exist_ok=True)
    mirror,mirror_receipt=capture_mirror(year,folder)
    plan=PLANS[PLANS.year.eq(year)].copy();windows=[w for w in WINDOWS if w[0]==year];parts=[];receipts=[]
    for index,(_,source,start,end) in enumerate(windows,1):
        request={'year':year,'source':source,'start_inclusive_utc':start,'end_exclusive_utc':end,'bbox':list(BBOX),'boundary_sha256':BOUNDARY_SHA256}
        name=f'{source}_{start}_{end}.csv';path=cache/name
        url='https://firms.modaps.eosdis.nasa.gov/api/area/csv/'+MAP_KEY+'/'+source+'/'+','.join(map(str,BBOX))+'/'+str((pd.Timestamp(end)-pd.Timestamp(start)).days)+'/'+start
        payload,receipt=cached_bytes(path,url,request,private=True)
        try:f=parse_official_csv(payload,source,start,end,REGION)
        except ValueError as error:raise ValueError(f'Unverified NASA response for {source} {start} to {end}: {error}. Raw bytes retained; no zero was written.') from None
        f['source_row_ordinal']=f.index.to_numpy();f['source_response_sha256']=receipt['sha256'];f['source_relative_path']='nasa_cache/'+name;f['source_stream']=source
        f['request_start_utc']=start;f['request_end_utc_exclusive']=end
        parts.append(f);receipts.append({**receipt,'regional_rows':len(f),'status':'native_schema_and_region_checked'})
        if index%10==0 or index==len(windows):print(f'{year}: {index}/{len(windows)} NASA windows; {sum(len(p) for p in parts):,} regional standard records.')
        time.sleep(REQUEST_PAUSE_SECONDS)
    canonical=history_canonical(parts)
    if len(canonical):assert pd.to_datetime(canonical.acq_datetime,utc=True).dt.year.eq(year).all()
    covered=pd.Series(False,index=mirror.index);times=pd.to_datetime(mirror.acq_datetime,utc=True);comparisons={}
    for row in plan.itertuples():
        sats=[s for s in HISTORY_SATELLITES if PLATFORM_SOURCE[s]==row.source]
        mask=mirror.quality.eq('sp')&mirror.satellite.isin(sats)
        if row.days:
            mask&=times.ge(pd.Timestamp(row.start,tz='UTC'))&times.lt(pd.Timestamp(row.end,tz='UTC'))
            covered|=mask
            comparisons[row.source]=compare_native(mirror.loc[mask],canonical[canonical.satellite.isin(sats)])
        else:comparisons[row.source]={'status':row.status,'canonical_query_rows':None}
    excluded=mirror.loc[~covered].copy();excluded['not_reconciled_reason']=np.where(excluded.quality.ne('sp'),'NRT_audit_only','outside_advertised_standard_interval')
    excluded.to_parquet(folder/'mirror_not_reconciled.parquet',index=False)
    mirror.loc[mirror.quality.eq('nrt')].to_parquet(folder/'mirror_nrt_audit_only.parquet',index=False)
    daily,monthly,grid=history_grids(year,canonical,plan,GAPS,MISSING_DATES)
    canonical.to_parquet(folder/'observations_standard.parquet',index=False)
    daily.to_parquet(folder/'daily_status.parquet',index=False);monthly.to_parquet(folder/'monthly_status.parquet',index=False);grid.to_parquet(folder/'native_standard_filter_grid.parquet',index=False)
    plan.to_parquet(folder/'official_request_plan.parquet',index=False)
    (folder/'mirror_standard_comparison.json').write_text(json.dumps(comparisons,indent=2,allow_nan=False))
    (folder/'request_receipts.json').write_text(json.dumps(receipts,indent=2))
    (folder/'region.geojson').write_bytes(BOUNDARY_BYTES)
    (folder/'run_contract.json').write_bytes((OUT/'run_contract.json').read_bytes())
    snapshot_dir=folder/'evidence';snapshot_dir.mkdir(exist_ok=True)
    for p in sorted((OUT/'snapshots').iterdir()):
        if p.is_file():shutil.copy2(p,snapshot_dir/p.name)
    for name in ['documented_global_gaps.parquet','upstream_missing_standard_dates.parquet','unparsed_outage_evidence.parquet']:shutil.copy2(OUT/name,snapshot_dir/name)
    conflicts=daily[daily.upstream_lists_missing_standard_data&daily.recorded_detections.fillna(0).gt(0)]
    conflicts.to_parquet(folder/'missing_date_positive_record_review.parquet',index=False)
    m={'year':year,'run_id':RUN_ID,'run_contract_sha256':digest((OUT/'run_contract.json').read_bytes()),'policy':HISTORY_POLICY,
       'availability_receipt':AVAILABILITY_RECEIPT,'public_source_receipts':PUBLIC_RECEIPTS,'mirror_receipt':mirror_receipt,
       'expected_requests':len(windows),'completed_requests':len(receipts),'canonical_standard_rows':len(canonical),
       'mirror_rows':len(mirror),'mirror_nrt_audit_rows':int(mirror.quality.eq('nrt').sum()),'mirror_standard_comparison_status':{s:r['status'] for s,r in comparisons.items()},
       'platform_year_counts':canonical.groupby('satellite').size().to_dict(),'daily_rows':len(daily),'monthly_rows':len(monthly),'native_grid_rows':len(grid),
       'unsupported_platform_days':int(daily.recorded_detections.isna().sum()),'missing_date_positive_records_for_review':len(conflicts),
       'coverage_verified':False,'harmonization_applied':False,'production_export_enabled':False,'frontend_changed':False,
       'packages':{p:metadata.version(p) for p in ['duckdb','pandas','pyarrow','numpy','shapely']},'completed_utc':datetime.now(timezone.utc).isoformat(),'files':{}}
    for path in sorted(folder.rglob('*')):
        if path.is_file() and path.name!='year_manifest.json':
            payload=path.read_bytes();assert MAP_KEY.encode() not in payload,'Credential found in output; stop before bundling.'
            m['files'][str(path.relative_to(folder))]={'bytes':len(payload),'sha256':digest(payload)}
    payload=json.dumps(m,indent=2,default=str,allow_nan=False).encode();assert MAP_KEY.encode() not in payload
    (folder/'year_manifest.json').write_bytes(payload)
    return package_year(folder)
print('Year processing helpers ready. No earlier history has been downloaded yet.')
''')
md('## 6. Process the next three incomplete years\nFirst invocation: 2000–2002. Each year ZIP is saved immediately and its hash printed. If this cell stops, rerun it: completed years are verified and cached requests for the interrupted year are reused. After the first batch, return its files for review before continuing.\n')
code('''assert isinstance(BATCH_SIZE,int) and 1<=BATCH_SIZE<=3
completed=[]
for year in HISTORY_YEARS:
    folder=OUT/'years'/str(year)
    if (folder/'year_manifest.json').exists():
        m=verify_year_files(folder)
        assert m['run_contract_sha256']==digest((OUT/'run_contract.json').read_bytes())
        completed.append(year)
active_batch_path=OUT/'active_batch.json'
previous=json.loads(active_batch_path.read_text()) if active_batch_path.exists() else []
assert isinstance(previous,list) and all(y in HISTORY_YEARS for y in previous)
NEXT_YEARS=previous if any(y not in completed for y in previous) else [y for y in HISTORY_YEARS if y not in completed][:BATCH_SIZE]
active_batch_path.write_text(json.dumps(NEXT_YEARS))
print('This batch:',NEXT_YEARS if NEXT_YEARS else 'all target years already captured')
BATCH_RECEIPTS=[]
for year in NEXT_YEARS:
    receipt=process_year(year);BATCH_RECEIPTS.append(receipt)
    print('SAVED:',receipt['zip_name'],'| rows:',receipt['canonical_standard_rows'],'| SHA256:',receipt['sha256'])
print('Batch finished. The output directory contains an evidence ZIP for each completed year.')
''')
md('## 7. Save progress and return the checkpoint files\nDownload the listed year ZIPs and the small progress ZIP, and save this executed notebook. For the first batch, send the 2000, 2001 and 2002 ZIPs for local verification. Nothing here merges or changes the 2022–2024 benchmark.\n')
code('''year_receipts=[]
for year in HISTORY_YEARS:
    folder=OUT/'years'/str(year)
    if (folder/'year_manifest.json').exists():year_receipts.append(package_year(folder))
progress={'run_id':RUN_ID,'target_years':HISTORY_YEARS,'completed_years':[r['year'] for r in year_receipts],
 'remaining_years':[y for y in HISTORY_YEARS if y not in {r['year'] for r in year_receipts}],
 'year_zip_receipts':year_receipts,'benchmark_reference':BENCHMARK_REFERENCE,'run_contract_sha256':digest((OUT/'run_contract.json').read_bytes()),
 'coverage_verified':False,'harmonization_applied':False,'frontend_changed':False}
(OUT/'progress.json').write_text(json.dumps(progress,indent=2))
PROGRESS_ZIP=OUT/f'cindertrace_atlas_lk_history_progress_{RUN_ID}.zip'
with zipfile.ZipFile(PROGRESS_ZIP,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in ['progress.json','run_contract.json','region.geojson','official_history_plan.parquet','documented_global_gaps.parquet','upstream_missing_standard_dates.parquet','unparsed_outage_evidence.parquet']:archive.write(OUT/name,name)
    for path in sorted((OUT/'snapshots').iterdir()):
        if path.is_file():archive.write(path,'snapshots/'+path.name)
print('Completed years:',progress['completed_years'])
print('Remaining years:',progress['remaining_years'])
display(pd.DataFrame(year_receipts))
print('Progress ZIP:',PROGRESS_ZIP.name,'| SHA256:',digest(PROGRESS_ZIP.read_bytes()))
if IN_COLAB:
    from google.colab import files
    for receipt in BATCH_RECEIPTS:files.download(str(OUT/receipt['zip_name']))
    files.download(str(PROGRESS_ZIP))
print('Save this executed notebook. If the browser blocks multiple downloads, retrieve the listed ZIPs directly from Drive.')
print('To continue after review in this runtime, rerun Steps 6 and 7. After restarting, rerun all cells with NEW_RUN=False and re-enter the key privately.')
''')
for i,c in enumerate(cells):c['id']=f'atlas-history-{i:02}'
nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.11'},'colab':{'name':'CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb'}},'nbformat':4,'nbformat_minor':5}
path=ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb';path.write_text(json.dumps(nb,indent=1)+'\n');print(path)
