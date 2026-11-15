"""Independently verify the returned 2023 NASA checkpoint, without extracting ZIP paths."""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import zipfile
import pandas as pd
import shapely
from .import_atlas_pilot import ROOT,verify_bundle
from .atlas_source_compare import SOURCES,parse_official_csv,compare_native

EXPECTED_SHA256='509afdf0418a01b248671addb4d7a221a02e0e5e275fb203aa6e170206d29077'
CHECKED_SOURCES=["MODIS_SP","VIIRS_SNPP_SP","VIIRS_NOAA20_SP"]
BASE={'attribute_differences.parquet','extra_in_mirror.parquet','missing_in_mirror.parquet',
 'monthly_reconciliation.parquet','official_reconciliation_manifest.json','official_regional_observations.parquet'}

def expected_windows(year,sources):
    result=[]
    for source in sources:
        start=pd.Timestamp(year,1,1);stop=pd.Timestamp(year+1,1,1)
        while start<stop:
            end=min(start+pd.Timedelta(days=5),stop)
            result.append((source,start.strftime('%Y-%m-%d'),end.strftime('%Y-%m-%d')));start=end
    return result

def verify_official(path,expected_sha256=EXPECTED_SHA256):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Official checkpoint ZIP differs from executed notebook hash')
    mirror,audit,boundary,pilot_report=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip')
    region=shapely.geometry.shape(boundary['features'][0]['geometry']);bbox=audit['query_parameters'][3:7]
    windows=expected_windows(2023,CHECKED_SOURCES)
    members=BASE|{f'cache/{s}_{a}_{b}{suffix}' for s,a,b in windows for suffix in ['.csv','.receipt.json']}
    with zipfile.ZipFile(BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or set(names)!=members:raise ValueError('Unexpected, missing, duplicate or unsafe checkpoint ZIP members')
        if any(i.file_size>20_000_000 for i in z.infolist()) or sum(i.file_size for i in z.infolist())>80_000_000:raise ValueError('Oversized checkpoint ZIP')
        files={n:z.read(n) for n in names}
    manifest=json.loads(files['official_reconciliation_manifest.json'])
    if manifest['pilot_bundle_sha256']!=pilot_report['bundle_sha256'] or manifest['boundary_sha256']!=audit['boundary_sha256']:raise ValueError('Checkpoint pilot/boundary identity differs')
    if manifest['checked_sources']!=CHECKED_SOURCES or manifest['completed_windows']!=219 or manifest['expected_windows']!=219:raise ValueError('Wrong checkpoint request cohort')
    if manifest['coverage_verified'] is not False or manifest['harmonization_validated'] is not False:raise ValueError('Unsupported scientific validation claim')
    listed=manifest['request_receipts']
    if len(listed)!=219:raise ValueError('Request receipts incomplete')
    parts=[];all_receipts=[]
    for i,(source,start,end) in enumerate(windows):
        stem=f'cache/{source}_{start}_{end}'
        receipt=json.loads(files[stem+'.receipt.json']);payload=files[stem+'.csv']
        if receipt!=listed[i]:raise ValueError('Cached receipt differs from final manifest')
        expected={'source':source,'start_inclusive_utc':start,'end_exclusive_utc':end,'bbox':bbox}
        if receipt['request']!=expected:raise ValueError('Request dates, source or bbox differ')
        if len(payload)!=receipt['bytes'] or hashlib.sha256(payload).hexdigest()!=receipt['sha256']:raise ValueError('NASA response checksum or byte size differs')
        if receipt['request_status']!='csv_schema_and_scope_verified' or pd.Timestamp(receipt['retrieved_utc']).tz is None:raise ValueError('Invalid request receipt')
        frame=parse_official_csv(payload,source,start,end,region)
        if len(frame)!=receipt['regional_rows']:raise ValueError('Recomputed regional request count differs')
        parts.append(frame);all_receipts.append(receipt)
    official=pd.concat([f for f in parts if not f.empty],ignore_index=True)
    saved=pd.read_parquet(BytesIO(files['official_regional_observations.parquet']))
    reconstructed=compare_native(saved,official)
    if reconstructed['status']!='matched_native_records':raise ValueError('Saved observations differ from cached NASA responses')
    # Reconcile every saved field, beyond the declared core comparison fields.
    if set(saved.columns)!=set(official.columns):raise ValueError('Saved observation schema differs')
    pd.testing.assert_frame_equal(saved.reset_index(drop=True),official[saved.columns].reset_index(drop=True),check_dtype=False,check_exact=False,atol=1e-9,rtol=0,check_index_type=False)
    comparison=compare_native(mirror,official)
    if comparison!=manifest['comparison'] or comparison['status']!='matched_native_records':raise ValueError('Recomputed native comparison differs or needs review')
    monthly=pd.read_parquet(BytesIO(files['monthly_reconciliation.parquet']))
    if len(monthly)!=48 or monthly.duplicated(['month','satellite']).any():raise ValueError('Monthly grid is incomplete')
    expected=pd.MultiIndex.from_product([[f'2023-{m:02}' for m in range(1,13)],['Terra','Aqua','Suomi-NPP','NOAA-20']],names=['month','satellite'])
    if set(map(tuple,monthly[['month','satellite']].to_numpy()))!=set(expected):raise ValueError('Wrong monthly filter cohort')
    for frame,column in [(mirror,'mirror_recorded_detections'),(official,'official_recorded_detections')]:
        counts=frame.assign(month=pd.to_datetime(frame.acq_datetime,utc=True).dt.strftime('%Y-%m')).groupby(['month','satellite']).size().reindex(expected,fill_value=0)
        if not counts.eq(monthly.set_index(['month','satellite'])[column].reindex(expected)).all():raise ValueError('Monthly totals differ')
    if not monthly.difference.eq(0).all() or not monthly.coverage_status.eq('unverified').all():raise ValueError('Monthly discrepancy or unsupported coverage state')
    for name in ['attribute_differences','missing_in_mirror','extra_in_mirror']:
        if len(pd.read_parquet(BytesIO(files[name+'.parquet']))):raise ValueError('Unexpected saved discrepancy records')
    report={'status':'independently_verified_official_checkpoint','zip_sha256':hashlib.sha256(raw).hexdigest(),
       'zip_members':len(files),'verified_requests':219,'matched_observations':len(official),'monthly_rows':48,
       'missing_records':0,'extra_records':0,'native_attribute_differences':0,'saved_fields_reconstructed':list(saved.columns),
       'original_pilot_sha256':pilot_report['bundle_sha256'],'boundary_sha256':audit['boundary_sha256'],
       'coordinate_comparison_decimals':5,'numeric_attribute_absolute_tolerance':1e-5,
       'retrieved_utc_min':min(r['retrieved_utc'] for r in all_receipts),'retrieved_utc_max':max(r['retrieved_utc'] for r in all_receipts),
       'coverage_verified':False,'harmonization_validated':False,'frontend_changed':False,
       'checks':['Outer ZIP hash and exact member list','All 219 per-request hashes, sizes, parameters and counts',
          'Complete nonoverlapping five-day UTC request cohort','CSV schema and native satellite provenance',
          'Exact polygon re-clipping','Reconstruction of all saved official fields from raw responses',
          'Recomputed mirror/native attribute comparison','Recomputed 48 monthly totals','Empty saved discrepancy tables']}
    return report

if __name__=='__main__':
    report=verify_official(ROOT/'cindertrace_atlas_lk_2023_official_check.zip')
    (ROOT/'docs/atlas_2023_official_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
