"""Offline verification of the returned 2022/2024 checkpoint and its quality mismatch."""
from io import BytesIO
from pathlib import Path
import hashlib,json,zipfile
import numpy as np
import pandas as pd
import shapely
from .import_atlas_pilot import ROOT,verify_bundle
from .atlas_source_compare import parse_official_csv,compare_native
from .atlas_two_year import availability_table,plan_requests,parse_gap_evidence,diagnostic_grids,stack_native,YEAR_SATELLITES,PLATFORM_SOURCE,SOURCE_SENSOR,PUBLIC_SOURCES

BUNDLE_NAME='cindertrace_atlas_lk_2022_2024_20261114T201123Z_30cc8ecb.zip'
EXPECTED_SHA256='6203a50c88921de8c29757192fbcbd9ee2af3ee06bd7f923e5dcf50cc34deea5'
def digest(raw):return hashlib.sha256(raw).hexdigest()
def same_frame(saved,recomputed):
    if set(saved.columns)!=set(recomputed.columns):raise ValueError('Recomputed table schema differs')
    pd.testing.assert_frame_equal(saved.reset_index(drop=True),recomputed[saved.columns].reset_index(drop=True),check_dtype=False,check_exact=False,atol=1e-9,rtol=0,check_index_type=False,check_column_type=False)

def validate_mirror(frame,year,region):
    times=pd.to_datetime(frame.acq_datetime,utc=True)
    if not times.dt.year.eq(year).all() or not times.dt.date.eq(pd.to_datetime(frame.acq_date).dt.date).all() or not frame.year.eq(year).all():raise ValueError('Mirror acquisition or partition dates differ')
    if frame.duplicated().any() or not frame.satellite.isin(YEAR_SATELLITES[year]).all() or not frame.quality.isin(['sp','nrt']).all():raise ValueError('Mirror native identity/domain needs review')
    expected=frame.satellite.map({s:SOURCE_SENSOR[PLATFORM_SOURCE[s]] for s in YEAR_SATELLITES[year]})
    if not frame.sensor.eq(expected).all():raise ValueError('Mirror sensor provenance differs')
    geo=shapely.from_wkb(frame.geometry_wkb.map(bytes).to_numpy())
    if not shapely.is_valid(geo).all() or not shapely.covers(region,geo).all():raise ValueError('Mirror coordinates outside polygon or invalid')
    if not np.allclose(shapely.get_x(geo),frame.audit_lon,atol=1e-9,rtol=0) or not np.allclose(shapely.get_y(geo),frame.audit_lat,atol=1e-9,rtol=0):raise ValueError('Mirror WKB/coordinate mismatch')
    modis=frame.sensor.eq('MODIS')
    if not frame.loc[modis,'confidence_pct'].between(0,100).all() or not pd.to_numeric(frame.loc[modis,'confidence']).eq(frame.loc[modis,'confidence_pct']).all():raise ValueError('Native MODIS confidence differs')
    if not frame.loc[~modis,'confidence'].isin(['l','n','h']).all() or frame.loc[~modis,'confidence_pct'].notna().any():raise ValueError('Native VIIRS confidence differs')
    if not frame.daynight.isin(['D','N']).all() or not frame.loc[frame.quality.eq('sp'),'type'].isin([0,1,2,3]).all():raise ValueError('Mirror type or day/night domain differs')
    if not np.isfinite(frame.frp).all() or frame.frp.lt(0).any():raise ValueError('Invalid native FRP')

def verify_two_year(path=ROOT/BUNDLE_NAME,expected_sha256=EXPECTED_SHA256):
    raw=Path(path).read_bytes()
    if digest(raw)!=expected_sha256:raise ValueError('Two-year ZIP differs from the executed notebook hash')
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or any(n.startswith('/') or '..' in Path(n).parts or '\\' in n for n in names):raise ValueError('Duplicate or unsafe ZIP member')
        if any(i.file_size>30_000_000 for i in archive.infolist()) or sum(i.file_size for i in archive.infolist())>200_000_000:raise ValueError('Oversized ZIP member/content')
        files={n:archive.read(n) for n in names}
    manifest=json.loads(files['checkpoint_manifest.json'])
    if set(manifest['files'])!=set(files)-{'checkpoint_manifest.json'}:raise ValueError('Manifest file inventory differs')
    for name,r in manifest['files'].items():
        if len(files[name])!=r['bytes'] or digest(files[name])!=r['sha256']:raise ValueError(f'Checkpoint file hash or byte size differs: {name}')
    _,pilot,boundary,_=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip')
    if digest(files['region.geojson'])!=pilot['boundary_sha256'] or manifest['boundary_sha256']!=pilot['boundary_sha256'] or manifest['bbox']!=pilot['query_parameters'][3:7]:raise ValueError('Original polygon/bbox identity differs')
    if manifest['year_satellites']!={str(y):s for y,s in YEAR_SATELLITES.items()} or manifest['years']!=[2022,2024]:raise ValueError('Wrong year/satellite contract')
    for field in ['coverage_verified','harmonization_applied','production_export_enabled','frontend_changed']:
        if manifest[field] is not False:raise ValueError('Unsupported production/scientific claim')
    region=shapely.geometry.shape(boundary['features'][0]['geometry'])
    def read(name):return pd.read_parquet(BytesIO(files[name]))
    def receipt(name,request,listed):
        saved=json.loads(files[name+'.receipt.json']);payload=files[name]
        if saved!=listed or saved['request']!=request or saved['bytes']!=len(payload) or saved['sha256']!=digest(payload):raise ValueError('Raw source/request receipt differs')
        if pd.Timestamp(saved['retrieved_utc']).tz is None:raise ValueError('Receipt retrieval time lacks timezone')
        return payload
    available=availability_table(receipt('nasa_availability.csv',{'service':'NASA FIRMS data_availability','source':'all'},manifest['availability_receipt']))
    plans,windows=plan_requests(available)
    if plans.to_dict('records')!=manifest['official_request_plan']:raise ValueError('Advertised request plan differs')
    same_frame(read('official_request_plan.parquet'),plans)
    if len(windows)!=manifest['expected_requests'] or len(windows)!=manifest['completed_requests'] or len(windows)!=len(manifest['request_receipts']):raise ValueError('Incomplete official request cohort')
    public={}
    for name,url in PUBLIC_SOURCES.items():
        filename='source_'+name+('.json' if name=='missing' else '.html')
        public[name]=receipt(filename,{'public_source':url},manifest['public_source_receipts'][name])
    gaps,missing=parse_gap_evidence(public)
    same_frame(read('documented_global_gaps.parquet'),gaps);same_frame(read('upstream_missing_standard_dates.parquet'),missing)
    parts={y:[] for y in YEAR_SATELLITES};lineaged={y:[] for y in YEAR_SATELLITES}
    expected_cache=set()
    for (year,source,start,end),listed in zip(windows,manifest['request_receipts']):
        name=f'cache/{source}_{start}_{end}.csv';expected_cache|={name,name+'.receipt.json'}
        request={'year':year,'source':source,'start_inclusive_utc':start,'end_exclusive_utc':end,'bbox':manifest['bbox'],'boundary_sha256':manifest['boundary_sha256']}
        cached=json.loads(files[name+'.receipt.json'])
        payload=receipt(name,request,{k:v for k,v in listed.items() if k not in ['regional_rows','request_status']})
        frame=parse_official_csv(payload,source,start,end,region)
        if len(frame)!=listed['regional_rows'] or listed['request_status']!='csv_schema_and_scope_verified':raise ValueError('Regional request count/status differs')
        parts[year].append(frame)
        provenance=frame.copy();provenance['source_row_ordinal']=frame.index.to_numpy();provenance['source_response_sha256']=cached['sha256'];provenance['source_relative_path']=name;provenance['source_stream']=source
        provenance['request_start_utc']=start;provenance['request_end_utc_exclusive']=end;provenance['source_checkpoint_sha256']=digest(raw);lineaged[year].append(provenance)
    if {n for n in files if n.startswith('cache/')}!=expected_cache:raise ValueError('Unplanned or missing raw cache files')
    official={y:stack_native(f) for y,f in parts.items()};mirrors={};comparisons={};source_results=[]
    for year in YEAR_SATELLITES:
        mirror=read(f'mirror_{year}.parquet');mirrors[year]=mirror;validate_mirror(mirror,year,region)
        mr=json.loads(files[f'mirror_{year}.receipt.json'])
        if mr!=manifest['mirror_receipts'][str(year)] or mr['sha256']!=digest(files[f'mirror_{year}.parquet']) or mr['bytes']!=len(files[f'mirror_{year}.parquet']):raise ValueError('Mirror receipt differs')
        expected_source=f'https://data.source.coop/portolan-mirrors/firms-catalog/detections/year={year}/detections.parquet'
        if mr['source_url']!=expected_source or mr['source_before']!=mr['source_after'] or mr['rows']!=len(mirror) or mr['direct_count']!=len(mirror):raise ValueError('Mirror snapshot/count reconciliation differs')
        if mr['parameters']!=[expected_source,f'{year}-01-01',f'{year+1}-01-01',*manifest['bbox'],region.wkt]:raise ValueError('Mirror spatial/time query parameters differ')
        same_frame(read(f'official_{year}.parquet'),official[year])
        covered=pd.Series(False,index=mirror.index);times=pd.to_datetime(mirror.acq_datetime,utc=True)
        for plan in plans[plans.year.eq(year)].itertuples():
            sats=[s for s in YEAR_SATELLITES[year] if PLATFORM_SOURCE[s]==plan.source]
            mask=mirror.quality.eq('sp')&mirror.satellite.isin(sats)
            if plan.days:
                mask&=times.ge(pd.Timestamp(plan.start,tz='UTC'))&times.lt(pd.Timestamp(plan.end,tz='UTC'));covered|=mask
                r=compare_native(mirror.loc[mask],official[year][official[year].satellite.isin(sats)])
                source_results.append({'year':year,'source':plan.source,'archive_scope':plan.status,**{k:v for k,v in r.items() if k not in ['missing_in_mirror','extra_in_mirror','attribute_differences']}})
            else:source_results.append({'year':year,'source':plan.source,'archive_scope':plan.status,'status':'not_checked_archive_unavailable'})
        excluded=mirror.loc[~covered].copy();excluded['not_reconciled_reason']=np.where(excluded.quality.ne('sp'),'NRT_retained_not_compared_as_standard','outside_advertised_standard_archive_range')
        same_frame(read(f'mirror_not_reconciled_{year}.parquet'),excluded)
        result=compare_native(mirror.loc[covered],official[year]);comparisons[str(year)]={**result,'scope_completeness':'full_declared_year' if plans[plans.year.eq(year)].status.eq('full_year_advertised').all() else 'partial_by_advertised_archive_dates',
            'mirror_rows_not_reconciled':len(excluded),'mirror_nrt_rows':int(mirror.quality.eq('nrt').sum()),'scientific_coverage_verified':False}
        for key in ['missing_in_mirror','extra_in_mirror','attribute_differences']:same_frame(read(f'{key}_{year}.parquet'),pd.DataFrame(result[key]))
    if comparisons!=manifest['comparisons']:raise ValueError('Recomputed source comparison differs from saved manifest')
    same_frame(read('source_reconciliation.parquet'),pd.DataFrame(source_results))
    daily,monthly,native=diagnostic_grids(mirrors,official,plans,gaps,missing)
    for name,frame in [('daily_diagnostics.parquet',daily),('monthly_diagnostics.parquet',monthly),('native_standard_filter_grid.parquet',native)]:same_frame(read(name),frame)
    same_frame(read('missing_date_positive_record_review.parquet'),daily[daily.upstream_lists_missing_standard_data&daily.official_sp_detections.fillna(0).gt(0)])
    controls=[]
    for event in gaps.itertuples():
        for year,mirror in mirrors.items():
            if event.start_utc.year!=year:continue
            times=pd.to_datetime(mirror.acq_datetime,utc=True)
            controls.append({'year':year,'satellite':event.satellite,'start_utc':event.start_utc,'end_utc':event.end_utc,
              'mirror_standard_records_in_reported_window':int((mirror.satellite.eq(event.satellite)&mirror.quality.eq('sp')&times.ge(event.start_utc)&times.lt(event.end_utc)).sum()),
              'source_url':event.source_url,'interpretation':'global reported interval; local impact/recovery not established; no rows deleted'})
    same_frame(read('outage_controls.parquet'),pd.DataFrame(controls))
    nrt=mirrors[2024].loc[mirrors[2024].satellite.eq('NOAA-21')].copy();sp=official[2024].loc[official[2024].satellite.eq('NOAA-21')].copy()
    quality_compare=compare_native(nrt,sp)
    report={'status':'verified_checkpoint_with_documented_NOAA21_quality_mismatch','zip_sha256':digest(raw),'zip_members':len(files),
      'manifested_files_verified':len(manifest['files']),'verified_requests':len(windows),'official_standard_observations':sum(len(f) for f in official.values()),
      'year_results':{y:{k:v for k,v in r.items() if k not in ['missing_in_mirror','extra_in_mirror','attribute_differences']} for y,r in comparisons.items()},
      'NOAA21_NRT_vs_standard':{k:v for k,v in quality_compare.items() if k not in ['missing_in_mirror','extra_in_mirror','attribute_differences']},
      'NOAA21_shared_key_attribute_difference_counts':pd.Series([r['field'] for r in quality_compare['attribute_differences']]).value_counts().to_dict(),
      'production_gap_intervals':len(gaps),'listed_missing_standard_dates':len(missing),'daily_rows':len(daily),'monthly_rows':len(monthly),'native_standard_grid_rows':len(native),
      'coverage_verified':False,'harmonization_validated':False,'frontend_changed':False,
      'checks':['Outer ZIP and every inner hash/byte size','All source snapshots and 515 request receipts','Native CSV schema/date/platform validation',
         'Re-clipping to original geometry','Saved official fields reconstructed from raw responses','Mirror geometry/confidence/quality/snapshot reconciliation',
         'Recomputed source comparisons and discrepancies','Recomputed daily/monthly/filter grids and outage controls']}
    return {'report':report,'manifest':manifest,'files':files,'official':official,'mirrors':mirrors,'lineaged':{y:stack_native(f) for y,f in lineaged.items()},'quality_compare':quality_compare,'gaps':gaps,'missing':missing}

if __name__=='__main__':
    result=verify_two_year();(ROOT/'docs/atlas_lk_2022_2024_verification.json').write_text(json.dumps(result['report'],indent=2)+'\n');print(json.dumps(result['report'],indent=2))
