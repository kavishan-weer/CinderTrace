"""Join independently verified standard observations, without changing frontend data."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .import_atlas_pilot import ROOT
from .atlas_source_compare import native_keys
from .verify_atlas_history import verify_history,EXPECTED_SHA256 as HISTORY_SHA
from .atlas_two_year import PLATFORM_SOURCE
from .atlas_history import digest

BENCHMARK=ROOT/'data/atlas/canonical_lk_2022_2024_v1'

def assemble(history=None,output=ROOT/'data/atlas/canonical_lk_2000_2024_v1'):
    history=history if history is not None else verify_history(progress=True)
    if history['report']['zip_sha256']!=HISTORY_SHA or history['report']['status']!='independently_verified_historical_capture':raise ValueError('History is not the verified source checkpoint')
    benchmark=json.loads((BENCHMARK/'manifest.json').read_text())
    for name,r in benchmark['files'].items():
        raw=(BENCHMARK/name).read_bytes()
        if len(raw)!=r['bytes'] or digest(raw)!=r['sha256']:raise ValueError('Frozen benchmark file changed')
    recent=pd.read_parquet(BENCHMARK/'observations.parquet');recent_daily=pd.read_parquet(BENCHMARK/'daily_observed_counts.parquet')
    if len(recent)!=38995 or not recent.quality.eq('sp').all():raise ValueError('Unexpected benchmark observations')
    p=pd.concat([history['canonical'],recent],ignore_index=True)
    if not p.quality.eq('sp').all() or len(p)!=171244 or p.observation_id.duplicated().any() or native_keys(p).duplicated().any():raise ValueError('Observed history count/identity/quality differs')
    p['acq_datetime']=pd.to_datetime(p.acq_datetime,utc=True);p['year']=p.acq_datetime.dt.year
    if set(p.year)!=set(range(2000,2025)):raise ValueError('Wrong unified historical years')
    if not p.year.between(2000,2024).all() or p.source_checkpoint_sha256.isna().any():raise ValueError('Missing unified source provenance')
    old=history['daily'].copy();new=recent_daily.copy()
    old['quality']='sp'
    new['retrieval_state']=new['retrieval_status']
    daily_columns=['year','date','satellite','quality','source_stream','retrieval_state','recorded_detections','observing_coverage','coverage_adjusted_activity','upstream_lists_missing_standard_data','documented_global_gap_on_date']
    daily=pd.concat([old[daily_columns],new[daily_columns]],ignore_index=True)
    daily['recorded_detections']=daily.recorded_detections.astype('Int64');daily['month']=daily.date.str[:7]
    daily['record_state']=np.select([daily.recorded_detections.isna(),daily.recorded_detections.fillna(0).gt(0)],['unavailable','recorded_positive'],default='recorded_zero_query_completed')
    if daily.duplicated(['date','satellite']).any() or not daily.observing_coverage.eq('unverified').all() or not daily.coverage_adjusted_activity.isna().all():raise ValueError('Unified availability/coverage states differ')
    counts=p.groupby(['acq_date','satellite']).size()
    for row in daily.itertuples():
        n=int(counts.get((row.date,row.satellite),0))
        if pd.isna(row.recorded_detections):
            if n:raise ValueError('Canonical records outside the supported source ledger')
        elif n!=row.recorded_detections:raise ValueError('Unified daily count differs from native observations')
    monthly=daily.groupby(['year','month','satellite'],sort=False).agg(detections_on_queried_dates=('recorded_detections',lambda x:x.sum(min_count=1)),
      days_in_month=('date','size'),supported_queried_days=('recorded_detections',lambda x:int(x.notna().sum())),
      upstream_listed_missing_days=('upstream_lists_missing_standard_data','sum'),dates_overlapping_global_gap=('documented_global_gap_on_date','sum')).reset_index()
    monthly['full_month_standard_detections']=monthly.detections_on_queried_dates.where(monthly.supported_queried_days.eq(monthly.days_in_month)).astype('Int64')
    monthly['period_state']=np.select([monthly.supported_queried_days.eq(0),monthly.supported_queried_days.eq(monthly.days_in_month)],['unavailable','complete_declared_query_month'],default='partial_archive_or_platform_month')
    monthly['quality']='sp';monthly['observing_coverage']='unverified'
    grids=[];observed=p.assign(month=p.acq_date.str[:7],native_confidence=p.confidence.astype(str))
    for year in range(2000,2025):
        sats=['Terra','Aqua','Suomi-NPP','NOAA-20']+(['NOAA-21'] if year==2024 else [])
        for sat in sats:
            subset=observed[observed.year.eq(year)&observed.satellite.eq(sat)];domain=[str(i) for i in range(101)] if sat in ['Terra','Aqua'] else ['l','n','h']
            if not subset.native_confidence.isin(domain).all():raise ValueError('Native confidence domain differs')
            idx=pd.MultiIndex.from_product([[f'{year}-{m:02}' for m in range(1,13)],[sat],[0,1,2,3],domain],names=['month','satellite','type','native_confidence'])
            f=subset.groupby(idx.names).size().reindex(idx,fill_value=0).rename('detections_on_queried_dates').reset_index()
            support=monthly[monthly.year.eq(year)&monthly.satellite.eq(sat)].set_index('month')
            f['supported_queried_days']=f.month.map(support.supported_queried_days);f['period_state']=f.month.map(support.period_state)
            f['detections_on_queried_dates']=f.detections_on_queried_dates.where(f.supported_queried_days.gt(0)).astype('Int64')
            f['full_month_standard_detections']=f.detections_on_queried_dates.where(f.period_state.eq('complete_declared_query_month')).astype('Int64')
            f['quality']='sp';f['observing_coverage']='unverified';f['reference_model_support']='not_evaluated';grids.append(f)
    grid=pd.concat(grids,ignore_index=True)
    if not (len(p)==daily.recorded_detections.sum()==monthly.detections_on_queried_dates.sum()==grid.detections_on_queried_dates.sum()):raise ValueError('Unified observed aggregation differs')
    boundary_raw=history['shared_files']['shared/region.geojson']
    if digest(boundary_raw)!=history['contract']['boundary_sha256'] or digest(boundary_raw)!=benchmark['boundary_sha256']:raise ValueError('Unified polygon differs from frozen source support')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    (output/'region.geojson').write_bytes(boundary_raw)
    for name,f in [('observations.parquet',p),('daily_status.parquet',daily),('monthly_status.parquet',monthly),('native_standard_filter_grid.parquet',grid),('history_source_reconciliation.parquet',history['source_results'])]:f.to_parquet(output/name,index=False)
    report={'dataset_id':'lk_observed_standard_2000_2024_v1','status':'verified observed data only; isolated from frontend',
      'observations':len(p),'year_counts':{str(y):len(f) for y,f in p.groupby('year')},'declared_years':[2000,2024],
      'boundary_sha256':digest(boundary_raw),'bbox':history['contract']['bbox'],'coordinate_reference':'OGC:CRS84',
      'first_available_archive_date':'2000-11-01','last_included_date':'2024-12-31','years_2025_onward':'not part of this verified checkpoint',
      'verified_raw_requests':history['report']['verified_raw_requests']+734,'daily_rows':len(daily),'monthly_rows':len(monthly),'native_grid_rows':len(grid),
      'unavailable_platform_days':int(daily.recorded_detections.isna().sum()),'partial_archive_or_platform_months':int(monthly.period_state.eq('partial_archive_or_platform_month').sum()),
      'flagged_months_with_global_gap_evidence':int(monthly.dates_overlapping_global_gap.gt(0).sum()),
      'history_checkpoint_sha256':HISTORY_SHA,'benchmark_manifest_sha256':digest((BENCHMARK/'manifest.json').read_bytes()),
      'source_rule':'verified NASA standard stream; preserve NRT audit separately; no sensor/date gap filling',
      'raw_annual_totals_comparable':False,'coverage_verified':False,'harmonization_validated':False,'production_export_enabled':False,'frontend_changed':False,'files':{}}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name!='manifest.json':
            raw=path.read_bytes();report['files'][path.name]={'bytes':len(raw),'sha256':digest(raw)}
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'report':report,'observations':p,'daily':daily,'monthly':monthly,'grid':grid,'history':history,'output':output}

if __name__=='__main__':
    r=assemble();summary={k:v for k,v in r['report'].items() if k!='files'}
    (ROOT/'docs/atlas_observed_2000_2024_checkpoint.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
