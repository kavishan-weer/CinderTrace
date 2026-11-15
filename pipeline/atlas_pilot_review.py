"""Offline data diagnostics for the immutable Sri Lanka 2023 pilot; no UI exports.
Public upstream missing dates are evidence of gaps, not a complete coverage ledger.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
from .import_atlas_pilot import ROOT, SATELLITES, verify_bundle

OUT=ROOT/'data/atlas/lk_2023_review'
SOURCES={
 'snpp':'https://modaps.modaps.eosdis.nasa.gov/services/production/outages_suomi_npp.html',
 'terra':'https://modaps.modaps.eosdis.nasa.gov/services/production/outages_terra.html',
 'firms':'https://firms2.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html',
 'missing_data':'https://firms.modaps.eosdis.nasa.gov/api/missing_data/?action=fetch_data',
}
class TableRows(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ['td','th']:self.cell=[]
        elif tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ['td','th'] and self.cell is not None:
            if self.row is not None:self.row.append(' '.join(''.join(self.cell).split()))
            self.cell=None
        elif tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def rows(html):
    parser=TableRows();parser.feed(html);return parser.rows

def parse_missing(raw):
    payload=json.loads(raw)
    if payload.get('success') is not True or not isinstance(payload.get('html'),str):
        raise ValueError('Upstream missing-date lookup failed; do not treat failure as no gaps')
    result=[]
    platforms={'Suomi NPP (VIIRS)':'Suomi-NPP','NOAA-20 (VIIRS)':'NOAA-20','Terra (MODIS)':'Terra','Aqua (MODIS)':'Aqua'}
    for row in rows(payload['html']):
        if len(row)!=4:raise ValueError('Missing-date table schema changed')
        date,platform=row[:2] # The last two columns describe NRT, not standard data.
        if date.startswith('2023-'):
            pd.Timestamp(date)
            if platform not in platforms:raise ValueError('Unexpected 2023 missing-date platform')
            result.append({'date':date,'satellite':platforms[platform],'quality':'sp',
              'evidence':'upstream_lists_missing_standard_data','source_url':SOURCES['missing_data']})
    return pd.DataFrame(result,columns=['date','satellite','quality','evidence','source_url'])

def parse_outages(html,satellite,source_url):
    result=[]
    for row in rows(html):
        if not row or not re.match(r'^2023-\d{3}(?:\s*-\s*2023-\d{3})?$',row[0]):continue
        if len(row)!=5:raise ValueError('Outage table schema changed')
        days=re.findall(r'2023-\d{3}',row[0])
        start=pd.to_datetime(days[0],format='%Y-%j',utc=True)+pd.Timedelta(row[2])
        end=pd.to_datetime(days[-1],format='%Y-%j',utc=True)+pd.Timedelta(row[3])
        if end<=start:raise ValueError('Invalid published outage interval; review instead of guessing dates')
        result.append({'satellite':satellite,'start_utc':start,'end_utc':end,
          'evidence':'documented_global_production_gap','recovery_status':'not_stated_in_this_table',
          'local_impact':'not_verified','source_url':source_url,
          'source_year_day':row[0],'source_reason':row[4],
          'interval_semantics':'reported granule window; not precise physical outage boundaries'})
    if not result:raise ValueError('No 2023 outage rows parsed; source/schema needs review')
    return pd.DataFrame(result)

def longest_zero_run(values):
    longest=current=0
    for value in values:
        current=current+1 if value==0 else 0;longest=max(longest,current)
    return longest

def make_tables(points,missing,outages):
    p=points.copy();p['date']=pd.to_datetime(p.acq_datetime,utc=True).dt.strftime('%Y-%m-%d');p['month']=p.date.str[:7]
    if not p.daynight.isin(['D','N']).all() or not p.type.isin([0,1,2,3]).all():raise ValueError('Unexpected native domain')
    if p.frp.isna().any() or not np.isfinite(p.frp).all() or p.frp.lt(0).any():raise ValueError('FRP requires investigation')
    if p.duplicated(['satellite','acq_datetime','audit_lon','audit_lat']).any():raise ValueError('Repeated native observation identity; investigate without silently dropping')
    index=pd.MultiIndex.from_product([pd.date_range('2023-01-01','2023-12-31').strftime('%Y-%m-%d'),SATELLITES],names=['date','satellite'])
    daily=p.groupby(['date','satellite']).size().reindex(index,fill_value=0).rename('recorded_detections').reset_index()
    known=set(zip(missing.date,missing.satellite))
    daily['upstream_lists_missing_standard_data']=[(d,s) in known for d,s in zip(daily.date,daily.satellite)]
    daily['coverage_status']=np.where(daily.upstream_lists_missing_standard_data,'known_upstream_gap_local_extent_unverified','unverified')
    daily['extraction_status']='query_completed';daily['coverage_adjusted_activity']=np.nan
    daily['documented_global_gap_on_date']=False
    for event in outages.itertuples():
        days=pd.date_range(event.start_utc.floor('D'),(event.end_utc-pd.Timedelta(nanoseconds=1)).floor('D')).strftime('%Y-%m-%d')
        daily.loc[daily.satellite.eq(event.satellite)&daily.date.isin(days),'documented_global_gap_on_date']=True
    conflicts=daily[daily.upstream_lists_missing_standard_data&daily.recorded_detections.gt(0)].copy()
    # A listed missing day can mean partial global coverage. Positive local rows are a discrepancy to inspect, never delete.
    daily['month']=daily.date.str[:7]
    monthly=daily.groupby(['month','satellite'],sort=False).agg(recorded_detections=('recorded_detections','sum'),
       days_with_recorded_detections=('recorded_detections',lambda x:int(x.gt(0).sum())),
       days_without_recorded_detections=('recorded_detections',lambda x:int(x.eq(0).sum())),
       longest_run_without_detections_days=('recorded_detections',longest_zero_run),
       upstream_listed_missing_days=('upstream_lists_missing_standard_data','sum'),
       dates_overlapping_documented_global_gap=('documented_global_gap_on_date','sum')).reset_index()
    monthly['observing_coverage']='unverified';monthly['extraction_status']='query_completed'
    # Complete native domains, without mapping numeric MODIS confidence into VIIRS classes.
    p['native_confidence']=p.confidence.astype(str)
    domains={s:[str(i) for i in range(101)] if s in ['Terra','Aqua'] else ['l','n','h'] for s in SATELLITES}
    for s,domain in domains.items():
        if not p.loc[p.satellite.eq(s),'native_confidence'].isin(domain).all():raise ValueError('Native confidence outside declared domain')
    grid=[]
    for s,domain in domains.items():
        idx=pd.MultiIndex.from_product([[f'2023-{m:02d}' for m in range(1,13)],[s],[0,1,2,3],domain],names=['month','satellite','published_type','native_confidence'])
        counts=p.loc[p.satellite.eq(s)].groupby(['month','satellite','type','native_confidence']).size()
        counts.index=counts.index.set_names(idx.names)
        grid.append(counts.reindex(idx,fill_value=0).rename('recorded_detections').reset_index())
    grid=pd.concat(grid,ignore_index=True)
    grid['confidence_scale']=np.where(grid.satellite.isin(['Terra','Aqua']),'native_MODIS_integer_0_to_100','native_VIIRS_class')
    grid['record_state']=np.where(grid.recorded_detections.gt(0),'recorded_positive','recorded_zero_query_complete')
    grid['observing_coverage']='unverified';grid['reference_model_support']='not_evaluated'
    annual=p.groupby(['satellite','type']).size()
    grid['category_observations_in_2023']=[int(annual.get((s,t),0)) for s,t in zip(grid.satellite,grid.published_type)]
    grid['category_pilot_support']=np.where(grid.category_observations_in_2023.eq(0),'no_record_in_this_pilot','recorded_in_this_pilot')
    # FRP and day/night are QA summaries within native platforms; no cross-sensor comparison claim.
    native=p.groupby(['month','satellite','daynight'],dropna=False).agg(recorded_detections=('frp','size'),frp_median_mw=('frp','median'),frp_max_mw=('frp','max')).reset_index()
    assert len(daily)==1460 and len(monthly)==48 and len(grid)==9984
    assert daily.recorded_detections.sum()==monthly.recorded_detections.sum()==grid.recorded_detections.sum()==len(p)
    evidence=outages.copy();times=pd.to_datetime(p.acq_datetime,utc=True)
    evidence['regional_records_in_reported_window']=[int((p.satellite.eq(e.satellite)&times.ge(e.start_utc)&times.lt(e.end_utc)).sum()) for e in evidence.itertuples()]
    return {'daily_observed_counts':daily,'monthly_diagnostics':monthly,'native_filter_grid':grid,'native_daynight_frp_qa':native,'source_evidence_conflicts':conflicts,'outage_inventory_2023':evidence}

def fetch_sources(destination):
    destination.mkdir(parents=True,exist_ok=True);receipts={}
    for name,url in SOURCES.items():
        with urlopen(Request(url,headers={'User-Agent':'CinderTrace-data-review/1.0','X-Requested-With':'XMLHttpRequest'}),timeout=60) as response:raw=response.read()
        if name=='missing_data':parse_missing(raw)
        filename=name+('.json' if name=='missing_data' else '.html');(destination/filename).write_bytes(raw)
        receipts[name]={'url':url,'filename':filename,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'retrieved_utc':datetime.now(timezone.utc).isoformat()}
    (destination/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')

def run(fetch=False):
    source=OUT/'sources'
    if fetch:fetch_sources(source)
    receipts=json.loads((source/'receipts.json').read_text())
    for receipt in receipts.values():
        raw=(source/receipt['filename']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=receipt['sha256'] or len(raw)!=receipt['bytes']:raise ValueError('Source snapshot checksum mismatch')
    p,manifest,boundary,bundle=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip')
    missing=parse_missing((source/'missing_data.json').read_bytes())
    outages=pd.concat([parse_outages((source/f'{name}.html').read_text(),sat,SOURCES[name]) for name,sat in [('snpp','Suomi-NPP'),('terra','Terra')]],ignore_index=True)
    tables=make_tables(p,missing,outages);tables['upstream_missing_standard_dates_2023']=missing
    tables['outage_notice_evidence']=pd.DataFrame([
      {'event_id':'snpp_2023_11_anomaly','satellite':'Suomi-NPP','notice_date':'2023-11-03',
       'reported_start_utc':'2023-11-01T14:56:00Z','exact_end_utc':None,
       'recovery_status':'missed_data_reported_unrecoverable',
       'later_update':'FIRMS reports products nominal on 2023-11-06; announcement is not an exact recovery timestamp.',
       'source_url':SOURCES['firms'],'local_impact':'not_verified',
       'cross_source_caution':'MODAPS granule-window start/end differ; retain both records without guessing exact loss boundaries.'},
      {'event_id':'noaa20_2023_09_anomaly','satellite':'NOAA-20','notice_date':'2023-09-30',
       'reported_start_utc':'2023-09-29T18:29:00Z','exact_end_utc':None,
       'recovery_status':'no_L0_received_since_reported_time; exact_recovery_not_stated_in_notice',
       'later_update':'Cross-check the separately captured standard-data missing-date table.',
       'source_url':SOURCES['firms'],'local_impact':'not_verified',
       'cross_source_caution':'18:29 is last L0 receipt time; spacecraft non-nominal time is about 18:47 UTC.'}
    ])
    OUT.mkdir(parents=True,exist_ok=True);files={}
    for name,frame in tables.items():
        path=OUT/f'{name}.parquet';frame.to_parquet(path,index=False)
        files[path.name]={'rows':len(frame),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    monthly=tables['monthly_diagnostics']
    report={'scope':'Sri Lanka 2023 observed-data pilot; frontend unchanged','bundle_sha256':bundle['bundle_sha256'],
       'observations':len(p),'daily_grid_rows':1460,'native_filter_grid_rows':9984,'monthly_grid_rows':48,
       'missing_standard_dates_2023':missing.to_dict('records'),'global_outage_intervals_2023':len(outages),
       'outage_table_intervals_with_local_records':int(tables['outage_inventory_2023'].regional_records_in_reported_window.gt(0).sum()),
       'listed_missing_dates_with_local_records':len(tables['source_evidence_conflicts']),
       'zero_satellite_months':monthly[monthly.recorded_detections.eq(0)][['month','satellite']].to_dict('records'),
       'published_type_totals':{str(k):int(v) for k,v in p.groupby('type').size().items()},
       'coverage_verified':False,'independent_NASA_row_reconciliation':'not_run; next notebook needs a free FIRMS MAP_KEY',
       'noaa20_replacement_validated':False,'cross_sensor_harmonization_validated':False,
       'decisions':['Retain raw recorded zeros; never infer complete observing coverage from them.',
          'Tag upstream missing dates and global gap overlaps as evidence, without replacing or discarding raw records.',
          'Do not expand historical calibration or compute new reference-equivalent medians/seasons yet.',
          'NOAA-21 is outside this four-satellite mirror pilot; NASA and mirror historical availability differ.'],
       'sources':receipts,'files':files}
    (OUT/'review_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'docs/atlas_2023_data_quality.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['sources','files']},indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--fetch-sources',action='store_true');args=parser.parse_args();run(args.fetch_sources)
