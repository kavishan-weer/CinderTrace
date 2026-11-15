"""Independently reconstruct the entire returned earlier-history evidence bundle offline."""
from io import BytesIO
from pathlib import Path
import hashlib,json,zipfile
import numpy as np
import pandas as pd
import shapely
from .import_atlas_pilot import ROOT
from .atlas_source_compare import parse_official_csv,compare_native
from .atlas_two_year import availability_table,PLATFORM_SOURCE
from .atlas_history import HISTORY_YEARS,HISTORY_SATELLITES,HISTORY_POLICY,history_plan,history_evidence,history_mirror_valid,history_canonical,history_grids,digest
from .verify_atlas_two_year import same_frame as _same_frame

BUNDLE_NAME='cindertrace_atlas_lk_history_complete_2000_2021_20261114T211825Z_97d5550a.zip'
EXPECTED_SHA256='b51ededac8925967d9d7edc58ea07524df7e72c41e0c02dea8ce5af0fded98c7'

def same_frame(saved,recomputed):
    # Arrow strings may deserialize missing dates as NaN while Python uses None.
    # Normalize only missing representations, never missing values to numeric zero.
    a=saved.copy();b=recomputed.copy()
    for frame in [a,b]:
        for column in frame:
            if pd.api.types.is_object_dtype(frame[column].dtype) or pd.api.types.is_string_dtype(frame[column].dtype):
                frame[column]=frame[column].astype(object).where(frame[column].notna(),None)
    return _same_frame(a,b)

def read_zip(raw,limit=400_000_000):
    with zipfile.ZipFile(BytesIO(raw)) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or any(n.startswith('/') or '..' in Path(n).parts or '\\' in n for n in names):raise ValueError('Unsafe or duplicate ZIP member')
        if sum(i.file_size for i in z.infolist())>limit or any(i.file_size>60_000_000 for i in z.infolist()):raise ValueError('ZIP size exceeds expected evidence limits')
        return {name:z.read(name) for name in names}

def check_inventory(files,manifest_name):
    m=json.loads(files[manifest_name])
    if set(m['files'])!=set(files)-{manifest_name}:raise ValueError('ZIP file inventory differs from manifest')
    for name,r in m['files'].items():
        if len(files[name])!=r['bytes'] or digest(files[name])!=r['sha256']:raise ValueError(f'File checksum/byte size differs: {name}')
    return m

def verify_history(path=ROOT/BUNDLE_NAME,expected_sha256=EXPECTED_SHA256,progress=False):
    raw=Path(path).read_bytes()
    if digest(raw)!=expected_sha256:raise ValueError('Combined ZIP differs from saved notebook SHA256')
    files=read_zip(raw);outer=check_inventory(files,'bundle_manifest.json');index=json.loads(files['progress.json'])
    if {k:v for k,v in outer.items() if k!='files'}!=index:raise ValueError('Progress index differs from bundle manifest')
    if index['target_years']!=HISTORY_YEARS or index['completed_years']!=HISTORY_YEARS or index['remaining_years'] or index['capture_status']!='all_target_years_captured':raise ValueError('Historical capture is incomplete or has a wrong year cohort')
    for field in ['coverage_verified','harmonization_applied','frontend_changed']:
        if index[field] is not False:raise ValueError('Unsupported scientific or frontend claim')
    contract_raw=files['shared/run_contract.json'];contract=json.loads(contract_raw)
    if index['run_contract_sha256']!=digest(contract_raw) or contract['target_years']!=HISTORY_YEARS or contract['policy']!=HISTORY_POLICY:raise ValueError('Pinned history contract differs')
    if index['benchmark_reference']!=contract['benchmark_reference']:raise ValueError('Benchmark reference differs')
    boundary_raw=files['shared/region.geojson']
    if digest(boundary_raw)!=contract['boundary_sha256'] or contract['boundary_sha256']!=contract['benchmark_reference']['boundary_sha256']:raise ValueError('Reference polygon hash differs')
    region=shapely.geometry.shape(json.loads(boundary_raw)['features'][0]['geometry']);bbox=contract['bbox']
    plans,windows=history_plan(availability_table(files['shared/snapshots/nasa_availability.csv']),HISTORY_YEARS)
    same_frame(pd.read_parquet(BytesIO(files['shared/official_history_plan.parquet'])),plans)
    public={name:files['shared/snapshots/'+name+('.json' if name=='missing' else '.html')] for name in ['snpp','terra','notices','missing']}
    gaps,missing,unparsed=history_evidence(public,HISTORY_YEARS)
    for name,f in [('documented_global_gaps.parquet',gaps),('upstream_missing_standard_dates.parquet',missing),('unparsed_outage_evidence.parquet',unparsed)]:same_frame(pd.read_parquet(BytesIO(files['shared/'+name])),f)
    for name in [n for n in files if n.startswith('shared/snapshots/') and not n.endswith('.receipt.json')]:
        r=json.loads(files[name+'.receipt.json'])
        if len(files[name])!=r['bytes'] or digest(files[name])!=r['sha256'] or pd.Timestamp(r['retrieved_utc']).tz is None:raise ValueError('Shared public source receipt differs')
    receipts=index['year_zip_receipts']
    if [r['year'] for r in receipts]!=HISTORY_YEARS:raise ValueError('Year ZIP receipts are incomplete or repeated')
    # Frozen archive member names belong to the checksummed capture, not the current product brand.
    for receipt in receipts:
        member=receipt['zip_name']
        if Path(member).name!=member or not member.endswith(f'_atlas_lk_history_{receipt["year"]}_{index["run_id"]}.zip'):
            raise ValueError('Year ZIP receipt name differs from its year/run')
    expected_members={'year_zips/'+r['zip_name'] for r in receipts}
    if {n for n in files if n.startswith('year_zips/')}!=expected_members:raise ValueError('Year ZIP member cohort differs')
    annual=[];canonical_parts=[];daily_parts=[];monthly_parts=[];native_parts=[];source_results=[];all_receipts=[];verified_files=0
    for yr in receipts:
        year=yr['year'];name='year_zips/'+yr['zip_name'];payload=files[name]
        if yr['zip_name']!=name.split('/')[-1] or len(payload)!=yr['bytes'] or digest(payload)!=yr['sha256']:raise ValueError('Nested year ZIP identity differs')
        members=read_zip(payload);m=check_inventory(members,'year_manifest.json');verified_files+=len(m['files'])
        if m['year']!=year or m['run_id']!=index['run_id'] or m['run_contract_sha256']!=digest(contract_raw) or m['policy']!=HISTORY_POLICY:raise ValueError('Year contract differs')
        if members['run_contract.json']!=contract_raw or members['region.geojson']!=boundary_raw:raise ValueError('Nested polygon/run identity differs')
        for field in ['coverage_verified','harmonization_applied','production_export_enabled','frontend_changed']:
            if m[field] is not False:raise ValueError('Unsupported year validation claim')
        for shared_name in [n for n in files if n.startswith('shared/snapshots/')]:
            nested='evidence/'+shared_name.split('shared/snapshots/',1)[1]
            if members[nested]!=files[shared_name]:raise ValueError('Year public snapshot differs from pinned snapshot')
        for artifact in ['documented_global_gaps.parquet','upstream_missing_standard_dates.parquet','unparsed_outage_evidence.parquet']:
            if members['evidence/'+artifact]!=files['shared/'+artifact]:raise ValueError('Year outage evidence differs from shared snapshot')
        def frame(n):return pd.read_parquet(BytesIO(members[n]))
        mirror=history_mirror_valid(frame('mirror.parquet'),year,region);mr=json.loads(members['mirror.receipt.json'])
        url=f'https://data.source.coop/portolan-mirrors/firms-catalog/detections/year={year}/detections.parquet'
        if mr!=m['mirror_receipt'] or mr['sha256']!=digest(members['mirror.parquet']) or mr['bytes']!=len(members['mirror.parquet']):raise ValueError('Mirror receipt/hash differs')
        if mr['source_url']!=url or mr['source_before']!=mr['source_after'] or mr['rows']!=len(mirror) or mr['direct_count']!=len(mirror) or mr['boundary_sha256']!=contract['boundary_sha256']:raise ValueError('Mirror source/count reconciliation differs')
        if mr['parameters']!=[url,f'{year}-01-01',f'{year+1}-01-01',*bbox,region.wkt]:raise ValueError('Mirror query support differs')
        plan=plans[plans.year.eq(year)].copy();same_frame(frame('official_request_plan.parquet'),plan)
        year_windows=[w for w in windows if w[0]==year];rr=json.loads(members['request_receipts.json'])
        if len(year_windows)!=m['expected_requests'] or len(year_windows)!=m['completed_requests'] or len(rr)!=len(year_windows):raise ValueError('Incomplete year request cohort')
        parts=[];cache=set()
        for (_,source,start,end),r in zip(year_windows,rr):
            fn=f'nasa_cache/{source}_{start}_{end}.csv';cache|={fn,fn+'.receipt.json'}
            request={'year':year,'source':source,'start_inclusive_utc':start,'end_exclusive_utc':end,'bbox':bbox,'boundary_sha256':contract['boundary_sha256']}
            recorded=json.loads(members[fn+'.receipt.json']);csv=members[fn]
            if recorded!={k:v for k,v in r.items() if k not in ['regional_rows','status']} or recorded['request']!=request:raise ValueError('Year NASA request receipt differs')
            if len(csv)!=recorded['bytes'] or digest(csv)!=recorded['sha256'] or pd.Timestamp(recorded['retrieved_utc']).tz is None:raise ValueError('NASA raw CSV identity differs')
            f=parse_official_csv(csv,source,start,end,region)
            if len(f)!=r['regional_rows'] or r['status']!='native_schema_and_region_checked':raise ValueError('Regional response counts/status differ')
            f['source_row_ordinal']=f.index.to_numpy();f['source_response_sha256']=recorded['sha256'];f['source_relative_path']=fn;f['source_stream']=source;f['request_start_utc']=start;f['request_end_utc_exclusive']=end;parts.append(f)
            all_receipts.append({'year':year,'year_zip_sha256':yr['sha256'],**r})
        if cache!={n for n in members if n.startswith('nasa_cache/')}:raise ValueError('Unplanned or missing NASA cache files')
        canonical=history_canonical(parts);same_frame(frame('observations_standard.parquet'),canonical)
        if len(canonical)!=m['canonical_standard_rows'] or len(canonical)!=yr['canonical_standard_rows']:raise ValueError('Canonical year count differs')
        if canonical.groupby('satellite').size().to_dict()!=m['platform_year_counts']:raise ValueError('Canonical platform counts differ')
        covered=pd.Series(False,index=mirror.index);times=pd.to_datetime(mirror.acq_datetime,utc=True);comparisons={}
        for p in plan.itertuples():
            sats=[s for s in HISTORY_SATELLITES if PLATFORM_SOURCE[s]==p.source];mask=mirror.quality.eq('sp')&mirror.satellite.isin(sats)
            if p.days:
                mask&=times.ge(pd.Timestamp(p.start,tz='UTC'))&times.lt(pd.Timestamp(p.end,tz='UTC'));covered|=mask
                comparisons[p.source]=compare_native(mirror.loc[mask],canonical[canonical.satellite.isin(sats)])
                source_results.append({'year':year,'source':p.source,**{k:v for k,v in comparisons[p.source].items() if k not in ['missing_in_mirror','extra_in_mirror','attribute_differences']}})
            else:comparisons[p.source]={'status':p.status,'canonical_query_rows':None}
        if comparisons!=json.loads(members['mirror_standard_comparison.json']) or {s:r['status'] for s,r in comparisons.items()}!=m['mirror_standard_comparison_status']:raise ValueError('Mirror standard comparison differs')
        excluded=mirror.loc[~covered].copy();excluded['not_reconciled_reason']=np.where(excluded.quality.ne('sp'),'NRT_audit_only','outside_advertised_standard_interval')
        same_frame(frame('mirror_not_reconciled.parquet'),excluded);same_frame(frame('mirror_nrt_audit_only.parquet'),mirror.loc[mirror.quality.eq('nrt')])
        daily,monthly,grid=history_grids(year,canonical,plan,gaps,missing)
        for artifact,f in [('daily_status.parquet',daily),('monthly_status.parquet',monthly),('native_standard_filter_grid.parquet',grid)]:same_frame(frame(artifact),f)
        conflicts=daily[daily.upstream_lists_missing_standard_data&daily.recorded_detections.fillna(0).gt(0)];same_frame(frame('missing_date_positive_record_review.parquet'),conflicts)
        if len(conflicts)!=m['missing_date_positive_records_for_review'] or int(daily.recorded_detections.isna().sum())!=m['unsupported_platform_days']:raise ValueError('Year eligibility evidence differs')
        canonical=canonical.copy();canonical['year']=year;canonical['source_year_zip_sha256']=yr['sha256'];canonical['source_checkpoint_sha256']=expected_sha256
        canonical_parts.append(canonical);daily_parts.append(daily);monthly_parts.append(monthly);native_parts.append(grid)
        annual.append({'year':year,'standard_observations':len(canonical),'requests_verified':len(rr),'mirror_nrt_audit_rows':int(mirror.quality.eq('nrt').sum()),'source_comparison_status':m['mirror_standard_comparison_status'],'unsupported_platform_days':int(daily.recorded_detections.isna().sum())})
        if progress:print(f'Verified {year}: {len(canonical):,} standard records; {len(rr)} raw responses.',flush=True)
    sources=pd.DataFrame(source_results)
    report={'status':'independently_verified_historical_capture','zip_sha256':expected_sha256,'run_id':index['run_id'],'years':HISTORY_YEARS,
      'outer_members':len(files),'nested_manifested_files_verified':verified_files,'verified_raw_requests':len(all_receipts),
      'standard_observations':sum(r['standard_observations'] for r in annual),'annual':annual,
      'source_comparisons_checked':len(sources),'source_comparisons_requiring_review':sources[sources.status.ne('matched_native_records')].to_dict('records'),
      'global_gap_intervals':len(gaps),'listed_missing_standard_dates':len(missing),'unparsed_outage_rows':len(unparsed),
      'coverage_verified':False,'harmonization_validated':False,'frontend_changed':False,
      'checks':['Outer and all nested file hashes and receipts','All 22 year identities and pinned run/polygon contracts','Every native NASA response re-parsed and re-clipped',
        'Canonical fields and row provenance reconstructed','Mirror standard comparisons recomputed','All daily/monthly/native grids recomputed','Early unavailable periods and partial months retained']}
    return {'report':report,'canonical':pd.concat(canonical_parts,ignore_index=True),'daily':pd.concat(daily_parts,ignore_index=True),'monthly':pd.concat(monthly_parts,ignore_index=True),
      'native_grid':pd.concat(native_parts,ignore_index=True),'source_results':sources,'request_receipts':all_receipts,'contract':contract,'outer':outer,'shared_files':{n:b for n,b in files.items() if n.startswith('shared/')}}

if __name__=='__main__':
    result=verify_history(progress=True);out=ROOT/'data/atlas/verified_history_2000_2021';out.mkdir(parents=True,exist_ok=True)
    for key,name in [('canonical','observations_standard.parquet'),('daily','daily_status.parquet'),('monthly','monthly_status.parquet'),('native_grid','native_standard_filter_grid.parquet'),('source_results','source_reconciliation.parquet')]:result[key].to_parquet(out/name,index=False)
    (out/'request_receipts.json').write_text(json.dumps(result['request_receipts'],indent=2)+'\n')
    (out/'verification.json').write_text(json.dumps(result['report'],indent=2)+'\n');(ROOT/'docs/atlas_history_2000_2021_verification.json').write_text(json.dumps(result['report'],indent=2)+'\n')
    print(json.dumps({k:v for k,v in result['report'].items() if k!='annual'},indent=2))
