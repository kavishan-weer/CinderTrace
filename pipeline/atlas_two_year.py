"""Pure data helpers embedded in the standalone 2022/2024 Sri Lanka notebook."""
from html.parser import HTMLParser
from io import BytesIO
import json
import re
import pandas as pd
import numpy as np

YEAR_SATELLITES={2022:['Terra','Aqua','Suomi-NPP','NOAA-20'],2024:['Terra','Aqua','Suomi-NPP','NOAA-20','NOAA-21']}
PLATFORM_SOURCE={'Terra':'MODIS_SP','Aqua':'MODIS_SP','Suomi-NPP':'VIIRS_SNPP_SP','NOAA-20':'VIIRS_NOAA20_SP','NOAA-21':'VIIRS_NOAA21_SP'}
SOURCE_SENSOR={'MODIS_SP':'MODIS','VIIRS_SNPP_SP':'VIIRS_SNPP','VIIRS_NOAA20_SP':'VIIRS_NOAA20','VIIRS_NOAA21_SP':'VIIRS_NOAA21'}
PUBLIC_SOURCES={
 'snpp':'https://modaps.modaps.eosdis.nasa.gov/services/production/outages_suomi_npp.html',
 'terra':'https://modaps.modaps.eosdis.nasa.gov/services/production/outages_terra.html',
 'notices':'https://firms2.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html',
 'missing':'https://firms.modaps.eosdis.nasa.gov/api/missing_data/?action=fetch_data'}

class EvidenceRows(HTMLParser):
    def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr':self.row=[]
        elif tag in ['td','th']:self.cell=[]
        elif tag=='br' and self.cell is not None:self.cell.append(' ')
    def handle_data(self,text):
        if self.cell is not None:self.cell.append(text)
    def handle_endtag(self,tag):
        if tag in ['td','th'] and self.cell is not None:
            if self.row is not None:self.row.append(' '.join(''.join(self.cell).split()))
            self.cell=None
        elif tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def evidence_rows(text):
    p=EvidenceRows();p.feed(text);return p.rows

def availability_table(raw):
    try:table=pd.read_csv(BytesIO(raw),dtype=str)
    except Exception:raise ValueError('Availability lookup did not return CSV; no dates may be treated as zero') from None
    if not {'data_id','min_date','max_date'}.issubset(table):raise ValueError('NASA availability schema changed')
    table=table[table.data_id.isin(set(PLATFORM_SOURCE.values()))].copy()
    if table.data_id.duplicated().any():raise ValueError('Duplicate advertised source date ranges')
    for c in ['min_date','max_date']:
        if not table[c].str.fullmatch(r'\d{4}-\d{2}-\d{2}',na=False).all():raise ValueError('Invalid advertised date')
        pd.to_datetime(table[c],errors='raise')
    if (table.min_date>table.max_date).any():raise ValueError('Reversed advertised date range')
    return table

def plan_requests(available):
    plans=[];windows=[]
    by_source=available.set_index('data_id')
    for year,satellites in YEAR_SATELLITES.items():
        for source in dict.fromkeys(PLATFORM_SOURCE[s] for s in satellites):
            begin=pd.Timestamp(year,1,1);stop=pd.Timestamp(year+1,1,1)
            if source not in by_source.index:
                plans.append({'year':year,'source':source,'status':'standard_source_not_advertised','start':None,'end':None,'days':0});continue
            a=max(begin,pd.Timestamp(by_source.loc[source,'min_date']))
            b=min(stop,pd.Timestamp(by_source.loc[source,'max_date'])+pd.Timedelta(days=1))
            if a>=b:
                plans.append({'year':year,'source':source,'status':'outside_advertised_archive_range','start':None,'end':None,'days':0});continue
            status='full_year_advertised' if a==begin and b==stop else 'partial_year_advertised'
            plans.append({'year':year,'source':source,'status':status,'start':str(a.date()),'end':str(b.date()),'days':(b-a).days})
            start=a
            while start<b:
                end=min(start+pd.Timedelta(days=5),b)
                windows.append((year,source,str(start.date()),str(end.date())));start=end
    plans=pd.DataFrame(plans)
    for column in ['start','end']:plans[column]=plans[column].astype(object).where(plans[column].notna(),None)
    return plans,windows

def stack_native(parts):
    columns=list(dict.fromkeys(c for p in parts for c in p.columns))
    nonempty=[p for p in parts if len(p)]
    return pd.concat(nonempty,ignore_index=True).reindex(columns=columns) if nonempty else parts[0].iloc[:0].reindex(columns=columns).copy()

def parse_gap_evidence(public):
    intervals=[]
    for label,satellite in [('snpp','Suomi-NPP'),('terra','Terra')]:
        for row in evidence_rows(public[label].decode()):
            if not row or not re.match(r'^(2022|2024)-\d{3}(?:\s*-\s*(?:2022|2024)-\d{3})?$',row[0]):continue
            if len(row)!=5:raise ValueError('Production outage table schema changed')
            dates=re.findall(r'20\d\d-\d{3}',row[0]);a=pd.to_datetime(dates[0],format='%Y-%j',utc=True)+pd.Timedelta(row[2]);b=pd.to_datetime(dates[-1],format='%Y-%j',utc=True)+pd.Timedelta(row[3])
            if b<=a:raise ValueError('Ambiguous outage end time; do not guess an interval')
            intervals.append({'satellite':satellite,'start_utc':a,'end_utc':b,'source_url':PUBLIC_SOURCES[label],
                'source_year_day':row[0],'source_reason':row[4],'local_impact':'unverified','recovery_status':'not_stated_in_table',
                'interval_semantics':'reported production/granule window; endpoints retained as published'})
    payload=json.loads(public['missing'])
    if payload.get('success') is not True or not isinstance(payload.get('html'),str):raise ValueError('Public missing-date lookup failed; no empty inventory inferred')
    platform={'Terra (MODIS)':'Terra','Aqua (MODIS)':'Aqua','Suomi NPP (VIIRS)':'Suomi-NPP','NOAA-20 (VIIRS)':'NOAA-20','NOAA-21 (VIIRS)':'NOAA-21'}
    missing=[]
    for row in evidence_rows(payload['html']):
        if len(row)!=4:raise ValueError('Missing-date table schema changed')
        if row[0].startswith(('2022-','2024-')):
            if row[1] not in platform:raise ValueError('Unknown missing-date platform')
            pd.Timestamp(row[0]);missing.append({'date':row[0],'satellite':platform[row[1]],'quality':'sp','source_url':PUBLIC_SOURCES['missing']})
    return pd.DataFrame(intervals,columns=['satellite','start_utc','end_utc','source_url','source_year_day','source_reason','local_impact','recovery_status','interval_semantics']),pd.DataFrame(missing,columns=['date','satellite','quality','source_url'])

def diagnostic_grids(mirrors,officials,plans,intervals,missing):
    daily=[];grids=[]
    gaps=set(zip(missing.date,missing.satellite))
    for year,satellites in YEAR_SATELLITES.items():
        m=mirrors[year].copy();m['date']=pd.to_datetime(m.acq_datetime,utc=True).dt.strftime('%Y-%m-%d');m['month']=m.date.str[:7]
        if not m.quality.isin(['sp','nrt']).all():raise ValueError('Unknown mirror quality')
        if not m.loc[m.quality.eq('sp'),'type'].isin([0,1,2,3]).all():raise ValueError('Unknown standard type domain')
        if not m.satellite.isin(satellites).all():raise ValueError('Unexpected platform in the yearly mirror contract')
        official=officials[year].copy();official['date']=pd.to_datetime(official.acq_datetime,utc=True).dt.strftime('%Y-%m-%d')
        for satellite in satellites:
            days=pd.date_range(f'{year}-01-01',f'{year}-12-31').strftime('%Y-%m-%d')
            frame=pd.DataFrame({'year':year,'date':days,'satellite':satellite})
            local=m[m.satellite.eq(satellite)]
            for quality in ['sp','nrt']:
                counts=local[local.quality.eq(quality)].groupby('date').size()
                frame['mirror_'+quality+'_detections']=frame.date.map(counts).fillna(0).astype(int)
            frame['official_sp_detections']=pd.Series(pd.NA,index=frame.index,dtype='Int64')
            plan=plans[plans.year.eq(year)&plans.source.eq(PLATFORM_SOURCE[satellite])].iloc[0]
            frame['official_query_state']=plan.status
            queried=frame.date.ge(plan.start)&frame.date.lt(plan.end) if plan.days else pd.Series(False,index=frame.index)
            counts=official[official.satellite.eq(satellite)].groupby('date').size()
            frame.loc[queried,'official_sp_detections']=frame.loc[queried,'date'].map(counts).fillna(0).astype('Int64')
            frame.loc[queried,'official_query_state']='query_completed'
            frame.loc[~queried&bool(plan.days),'official_query_state']='outside_advertised_archive_range'
            frame['upstream_lists_missing_standard_data']=[(d,satellite) in gaps for d in frame.date]
            frame['documented_global_gap_on_date']=False
            for event in intervals[intervals.satellite.eq(satellite)].itertuples():
                overlap=pd.date_range(event.start_utc.floor('D'),(event.end_utc-pd.Timedelta(nanoseconds=1)).floor('D')).strftime('%Y-%m-%d')
                frame.loc[frame.date.isin(overlap),'documented_global_gap_on_date']=True
            frame['observing_coverage']='unverified';frame['coverage_adjusted_activity']=np.nan;daily.append(frame)
            domain=[str(i) for i in range(101)] if satellite in ['Terra','Aqua'] else ['l','n','h']
            sp=local[local.quality.eq('sp')].copy();sp['native_confidence']=sp.confidence.astype(str)
            if not sp.native_confidence.isin(domain).all():raise ValueError('Native confidence changed; no crosswalk applied')
            idx=pd.MultiIndex.from_product([[f'{year}-{i:02}' for i in range(1,13)],[satellite],[0,1,2,3],domain],names=['month','satellite','type','native_confidence'])
            counts=sp.groupby(idx.names).size().reindex(idx,fill_value=0).rename('recorded_detections').reset_index()
            counts['quality']='sp';counts['confidence_scale']='MODIS_integer' if satellite in ['Terra','Aqua'] else 'VIIRS_class';counts['observing_coverage']='unverified'
            counts['record_state']=np.where(counts.recorded_detections.gt(0),'recorded_positive','recorded_zero_query_completed');grids.append(counts)
    daily=pd.concat(daily,ignore_index=True);daily['month']=daily.date.str[:7]
    monthly=daily.groupby(['year','month','satellite'],sort=False).agg(mirror_sp_detections=('mirror_sp_detections','sum'),mirror_nrt_detections=('mirror_nrt_detections','sum'),
        official_sp_on_queried_days=('official_sp_detections',lambda x:x.sum(min_count=1)),days_in_month=('date','size'),days_queried=('official_query_state',lambda x:int(x.eq('query_completed').sum())),
        upstream_listed_missing_days=('upstream_lists_missing_standard_data','sum'),dates_overlapping_global_gap=('documented_global_gap_on_date','sum')).reset_index()
    monthly['official_full_month_sp_detections']=monthly.official_sp_on_queried_days.where(monthly.days_queried.eq(monthly.days_in_month)).astype('Int64')
    monthly['observing_coverage']='unverified'
    return daily,monthly,pd.concat(grids,ignore_index=True)
