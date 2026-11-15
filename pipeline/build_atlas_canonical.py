"""Build an isolated observed-standard benchmark; never writes frontend/legacy data.
Inputs are independently verified returned bundles. NRT is audit-only, not a gap filler.
"""
from io import BytesIO
from pathlib import Path
import hashlib,json,shutil,zipfile
import numpy as np
import pandas as pd
import shapely
from .import_atlas_pilot import ROOT,verify_bundle
from .verify_atlas_official import verify_official,EXPECTED_SHA256 as SHA_2023
from .verify_atlas_two_year import verify_two_year,BUNDLE_NAME,EXPECTED_SHA256 as SHA_TWO,digest
from .atlas_source_compare import parse_official_csv,native_keys
from .atlas_two_year import PLATFORM_SOURCE,SOURCE_SENSOR,stack_native
from .atlas_pilot_review import parse_outages,parse_missing,SOURCES as EVIDENCE_2023,OUT as REVIEW_2023

SCOPE={2022:['Terra','Aqua','Suomi-NPP','NOAA-20'],2023:['Terra','Aqua','Suomi-NPP','NOAA-20'],2024:['Terra','Aqua','Suomi-NPP','NOAA-20','NOAA-21']}
POLICY={
 'policy_id':'lk_observed_standard_benchmark_v1','years':[2022,2023,2024],
 'canonical_quality':'sp','canonical_source':'NASA FIRMS standard-product responses independently verified from raw request bytes',
 'mirror_role':'validated extraction cache; historical NRT is not a substitute for an available verified standard stream',
 'source_precedence_unit':'platform and verified standard-product UTC archive interval',
 'nrt_rule':'retain the original NRT stream separately for audit; never stack or row-wise coalesce with standard records',
 'missing_standard_rule':'preserve a recorded zero or unavailable state; do not insert NRT or another platform to fill it',
 'deduplication_rule':'preserve native multiplicity and reject duplicate identities for review; never combine platforms into unique incidents',
 'zero_definition':'zero matching standard detections in a successfully verified query, not verified no-fire conditions',
 'coverage_verified':False,'harmonization_applied':False,'cross_year_raw_totals_comparable':False,
 'fleet_note':'four declared platforms in 2022/2023 and five in 2024; raw annual totals are not a calibrated trend',
 'production_export_enabled':False,'frontend_changed':False}

def lineage_2023(region):
    path=ROOT/'cindertrace_atlas_lk_2023_official_check.zip';report=verify_official(path);frames=[];receipts=[]
    with zipfile.ZipFile(path) as z:
        manifest=json.loads(z.read('official_reconciliation_manifest.json'))
        for r in manifest['request_receipts']:
            q=r['request'];source=q['source'];start=q['start_inclusive_utc'];end=q['end_exclusive_utc'];name=f'cache/{source}_{start}_{end}.csv'
            f=parse_official_csv(z.read(name),source,start,end,region)
            f['source_row_ordinal']=f.index.to_numpy();f['source_response_sha256']=r['sha256'];f['source_relative_path']=name;f['source_stream']=source
            f['request_start_utc']=start;f['request_end_utc_exclusive']=end;f['source_checkpoint_sha256']=SHA_2023;frames.append(f)
            receipts.append({'year':2023,**r})
    return stack_native(frames),receipts,report

def canonical_rows(frames):
    p=stack_native(list(frames.values())).copy()
    p['acq_datetime']=pd.to_datetime(p.acq_datetime,utc=True);p['acq_date']=p.acq_datetime.dt.strftime('%Y-%m-%d');p['year']=p.acq_datetime.dt.year
    p['sensor']=p.source_stream.map(SOURCE_SENSOR);p['quality']='sp';p['coordinate_reference']='OGC:CRS84'
    p['geometry_wkb']=shapely.to_wkb(shapely.points(p.longitude.to_numpy(),p.latitude.to_numpy()))
    p['type']=p.type.astype('Int64');p['confidence_pct']=p.confidence_pct.astype('Int64')
    p['observation_id']=[digest(f'{source}|{sha}|{int(ordinal)}'.encode()) for source,sha,ordinal in zip(p.source_stream,p.source_response_sha256,p.source_row_ordinal)]
    if p.observation_id.duplicated().any() or native_keys(p).duplicated().any():raise ValueError('Duplicate canonical native identity; no silent dropping')
    if p.source_stream.isna().any() or p.sensor.isna().any() or p.version.str.contains('NRT',case=False).any():raise ValueError('Invalid canonical provenance/quality')
    return p

def request_ledger(canonical,receipts):
    ledger=[]
    for r in receipts:
        q=r['request'];year=r['year'];source=q['source'];a=q['start_inclusive_utc'];b=q['end_exclusive_utc']
        for satellite in [s for s in SCOPE[year] if PLATFORM_SOURCE[s]==source]:
            for d in pd.date_range(a,pd.Timestamp(b)-pd.Timedelta(days=1)):
                ledger.append({'year':year,'date':str(d.date()),'satellite':satellite,'quality':'sp','source_stream':source,
                  'retrieval_status':'query_completed_and_locally_verified','source_response_sha256':r['sha256']})
    daily=pd.DataFrame(ledger)
    if daily.duplicated(['date','satellite']).any():raise ValueError('Repeated or overlapping canonical source intervals')
    expected={(str(d.date()),s) for y,sats in SCOPE.items() for d in pd.date_range(f'{y}-01-01',f'{y}-12-31') for s in sats}
    if set(zip(daily.date,daily.satellite))!=expected:raise ValueError('Incomplete canonical request ledger; unavailable dates must not become zero')
    counts=canonical.groupby(['acq_date','satellite']).size()
    daily['recorded_detections']=[int(counts.get((d,s),0)) for d,s in zip(daily.date,daily.satellite)]
    daily['record_state']=np.where(daily.recorded_detections.gt(0),'recorded_positive','recorded_zero_query_completed')
    daily['observing_coverage']='unverified';daily['coverage_adjusted_activity']=np.nan
    return daily

def make_grids(canonical,daily,gaps,missing):
    daily=daily.copy();missing_set=set(zip(missing.date,missing.satellite))
    daily['upstream_lists_missing_standard_data']=[(d,s) in missing_set for d,s in zip(daily.date,daily.satellite)]
    daily['documented_global_gap_on_date']=False
    for e in gaps.itertuples():
        days=pd.date_range(e.start_utc.floor('D'),(e.end_utc-pd.Timedelta(nanoseconds=1)).floor('D')).strftime('%Y-%m-%d')
        daily.loc[daily.satellite.eq(e.satellite)&daily.date.isin(days),'documented_global_gap_on_date']=True
    daily['month']=daily.date.str[:7]
    monthly=daily.groupby(['year','month','satellite'],sort=False).agg(recorded_detections=('recorded_detections','sum'),
        verified_query_days=('date','size'),days_with_detections=('recorded_detections',lambda x:int(x.gt(0).sum())),
        upstream_listed_missing_days=('upstream_lists_missing_standard_data','sum'),dates_overlapping_global_gaps=('documented_global_gap_on_date','sum')).reset_index()
    monthly['quality']='sp';monthly['observing_coverage']='unverified'
    grids=[];p=canonical.assign(month=canonical.acq_date.str[:7],native_confidence=canonical.confidence.astype(str))
    for year,sats in SCOPE.items():
        for sat in sats:
            domain=[str(i) for i in range(101)] if sat in ['Terra','Aqua'] else ['l','n','h']
            idx=pd.MultiIndex.from_product([[f'{year}-{m:02}' for m in range(1,13)],[sat],[0,1,2,3],domain],names=['month','satellite','type','native_confidence'])
            subset=p[p.year.eq(year)&p.satellite.eq(sat)]
            if not subset.native_confidence.isin(domain).all() or not subset.type.isin([0,1,2,3]).all():raise ValueError('Unknown native filter domain')
            f=subset.groupby(idx.names).size().reindex(idx,fill_value=0).rename('recorded_detections').reset_index()
            f['quality']='sp';f['record_state']=np.where(f.recorded_detections.gt(0),'recorded_positive','recorded_zero_query_completed');f['observing_coverage']='unverified';f['reference_model_support']='not_evaluated'
            annual=subset.groupby('type').size();f['category_records_in_year']=[int(annual.get(t,0)) for t in f.type]
            f['category_support']=np.where(f.category_records_in_year.eq(0),'not_recorded_in_this_platform_year','recorded_in_this_platform_year')
            grids.append(f)
    grid=pd.concat(grids,ignore_index=True)
    if not (daily.recorded_detections.sum()==monthly.recorded_detections.sum()==grid.recorded_detections.sum()==len(canonical)):raise ValueError('Canonical grids do not reconcile')
    return daily,monthly,grid

def build(output=ROOT/'data/atlas/canonical_lk_2022_2024_v1'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    two=verify_two_year();_,pilot,boundary,_=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip');region=shapely.geometry.shape(boundary['features'][0]['geometry'])
    frame2023,receipts2023,report2023=lineage_2023(region)
    frames={2022:two['lineaged'][2022],2023:frame2023,2024:two['lineaged'][2024]}
    p=canonical_rows(frames);receipts=[*two['manifest']['request_receipts'],*receipts2023]
    receipts=[{**r,'year':r.get('year',r['request'].get('year'))} for r in receipts]
    gaps=two['gaps'].copy();missing=two['missing'].copy();evidence_status={2022:'captured_2022_2024_bundle',2024:'captured_2022_2024_bundle'}
    evidence_dir=output/'evidence';evidence_dir.mkdir(exist_ok=True)
    for label in ['snpp','terra','notices','missing']:
        name='source_'+label+('.json' if label=='missing' else '.html')
        (evidence_dir/name).write_bytes(two['files'][name]);(evidence_dir/(name+'.receipt.json')).write_bytes(two['files'][name+'.receipt.json'])
    source=REVIEW_2023/'sources'
    if (source/'receipts.json').is_file():
        snapshot=json.loads((source/'receipts.json').read_text());original={}
        for label,r in snapshot.items():
            raw=(source/r['filename']).read_bytes()
            if digest(raw)!=r['sha256'] or len(raw)!=r['bytes']:raise ValueError('2023 outage evidence snapshot checksum differs')
            original[label]=raw;(evidence_dir/('2023_'+r['filename'])).write_bytes(raw)
        (evidence_dir/'2023_receipts.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        extra=pd.concat([parse_outages(original[label].decode(),sat,EVIDENCE_2023[label]) for label,sat in [('snpp','Suomi-NPP'),('terra','Terra')]],ignore_index=True)
        gaps=pd.concat([gaps,extra],ignore_index=True);missing=pd.concat([missing,parse_missing(original['missing_data'])],ignore_index=True);evidence_status[2023]='checksummed_local_public_snapshots'
    else:evidence_status[2023]='no_outage_snapshot_available; coverage remains unverified'
    daily,monthly,grid=make_grids(p,request_ledger(p,receipts),gaps,missing)
    archive=output/'audit';archive.mkdir(exist_ok=True)
    nrt=two['mirrors'][2024].loc[two['mirrors'][2024].satellite.eq('NOAA-21')].copy()
    nrt.to_parquet(archive/'noaa21_mirror_nrt_2024.parquet',index=False)
    comparison=two['quality_compare']
    for name in ['missing_in_mirror','extra_in_mirror','attribute_differences']:pd.DataFrame(comparison[name]).to_parquet(archive/f'noaa21_nrt_sp_{name}.parquet',index=False)
    n21=p[p.satellite.eq('NOAA-21')]
    monthly_nrt=nrt.assign(month=pd.to_datetime(nrt.acq_datetime).dt.strftime('%Y-%m')).groupby('month').size()
    monthly_sp=n21.assign(month=n21.acq_date.str[:7]).groupby('month').size()
    changes=pd.DataFrame({'month':[f'2024-{i:02}' for i in range(1,13)]})
    changes['mirror_nrt_records']=changes.month.map(monthly_nrt).fillna(0).astype(int);changes['canonical_standard_records']=changes.month.map(monthly_sp).fillna(0).astype(int)
    changes['net_record_count_difference']=changes.canonical_standard_records-changes.mirror_nrt_records
    changes['interpretation']='different processing streams; net change is not a count of added/removed physical fires'
    changes.to_parquet(archive/'noaa21_monthly_quality_comparison.parquet',index=False)
    p.to_parquet(output/'observations.parquet',index=False);daily.to_parquet(output/'daily_observed_counts.parquet',index=False)
    monthly.to_parquet(output/'monthly_observed_counts.parquet',index=False);grid.to_parquet(output/'native_standard_filter_grid.parquet',index=False)
    gaps.to_parquet(output/'documented_global_gap_intervals.parquet',index=False);missing.to_parquet(output/'upstream_missing_standard_dates.parquet',index=False)
    (output/'source_policy.json').write_text(json.dumps(POLICY,indent=2)+'\n')
    (output/'verified_request_receipts.json').write_text(json.dumps(receipts,indent=2)+'\n');(output/'region.geojson').write_bytes(two['files']['region.geojson'])
    report={'dataset_id':POLICY['policy_id'],'status':'isolated_observed_standard_benchmark; not wired to frontend',
      'observations':len(p),'year_counts':{str(y):len(f) for y,f in p.groupby('year')},'platform_year_counts':p.groupby(['year','satellite']).size().rename('recorded_detections').reset_index().to_dict('records'),
      'verified_raw_requests':len(receipts),'daily_rows':len(daily),'monthly_rows':len(monthly),'native_filter_grid_rows':len(grid),
      'NOAA21_canonical_standard_records':len(n21),'NOAA21_retained_audit_NRT_records':len(nrt),
      'NOAA21_exact_native_keys_shared':comparison['shared_rows'],'NOAA21_standard_only_native_keys':comparison['official_rows_missing_in_mirror'],'NOAA21_NRT_only_native_keys':comparison['mirror_rows_not_in_official'],
      'NOAA21_shared_key_changed_fields':two['report']['NOAA21_shared_key_attribute_difference_counts'],
      'source_checkpoints':{'2023':SHA_2023,'2022_2024':SHA_TWO},'boundary_sha256':pilot['boundary_sha256'],
      'outage_evidence_status':{str(k):v for k,v in evidence_status.items()},'coverage_verified':False,'harmonization_applied':False,'production_export_enabled':False,'frontend_changed':False,
      'files':{}}
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name!='manifest.json':
            raw=path.read_bytes();report['files'][str(path.relative_to(output))]={'bytes':len(raw),'sha256':digest(raw)}
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'report':report,'canonical':p,'daily':daily,'monthly':monthly,'grid':grid,'two_year_verification':two['report'],'verification_2023':report2023,'output':output}

if __name__=='__main__':
    result=build();r=result['report']
    (ROOT/'docs/atlas_lk_2022_2024_verification.json').write_text(json.dumps(result['two_year_verification'],indent=2)+'\n')
    summary={k:v for k,v in r.items() if k!='files'};(ROOT/'docs/atlas_canonical_benchmark.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
