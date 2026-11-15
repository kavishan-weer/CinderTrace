"""Data-only historical rebuild helpers; authoritative standard streams, no calibration."""
from pathlib import Path
from io import BytesIO
import hashlib,json,re
import numpy as np
import pandas as pd
import shapely
from .atlas_two_year import PLATFORM_SOURCE,SOURCE_SENSOR,PUBLIC_SOURCES,stack_native,evidence_rows
from .atlas_source_compare import native_keys

HISTORY_YEARS=list(range(2000,2022))
HISTORY_SATELLITES=['Terra','Aqua','Suomi-NPP','NOAA-20']
HISTORY_SOURCES=['MODIS_SP','VIIRS_SNPP_SP','VIIRS_NOAA20_SP']
# A platform lower bound, not a claim of complete observing coverage on/after this day.
AQUA_FIRST_LIGHT='2002-07-04'
AQUA_DATE_SOURCE='https://modaps.modaps.eosdis.nasa.gov/services/about/'
HISTORY_POLICY={'policy_id':'lk_observed_standard_history_v1','target_years':HISTORY_YEARS,
 'canonical_source':'NASA FIRMS standard-product responses with raw checksums and native row provenance',
 'coordinate_reference':'OGC:CRS84',
 'nrt_rule':'audit-only; never append/coalesce with standard or use as missing-standard fallback',
 'unavailable_rule':'null count before supported platform/archive intervals or when source is not advertised',
 'zero_rule':'zero recorded detections requires a completed verified query; not physical fire absence',
 'aqua_lower_bound':AQUA_FIRST_LIGHT,'aqua_lower_bound_source':AQUA_DATE_SOURCE,
 'aqua_lower_bound_interpretation':'reported first light; local observing completeness remains unverified',
 'coverage_verified':False,'harmonization_applied':False,'production_export_enabled':False,'frontend_changed':False,
 'benchmark_years_excluded':[2022,2023,2024],'raw_annual_totals_comparable_across_fleets':False}

def digest(payload):return hashlib.sha256(payload).hexdigest()

def history_plan(available,years):
    if not years or len(set(years))!=len(years) or any(y not in HISTORY_YEARS for y in years):raise ValueError('Choose unique historical years 2000–2021; verified benchmark is out of scope')
    by=available.set_index('data_id');plans=[];windows=[]
    for year in years:
        for source in HISTORY_SOURCES:
            a=pd.Timestamp(year,1,1);b=pd.Timestamp(year+1,1,1)
            if source not in by.index:
                plans.append({'year':year,'source':source,'status':'standard_source_not_advertised','start':None,'end':None,'days':0});continue
            start=max(a,pd.Timestamp(by.loc[source,'min_date']));end=min(b,pd.Timestamp(by.loc[source,'max_date'])+pd.Timedelta(days=1))
            if start>=end:
                plans.append({'year':year,'source':source,'status':'outside_advertised_archive_range','start':None,'end':None,'days':0});continue
            plans.append({'year':year,'source':source,'status':'full_year_advertised' if start==a and end==b else 'partial_year_advertised','start':str(start.date()),'end':str(end.date()),'days':(end-start).days})
            while start<end:
                stop=min(start+pd.Timedelta(days=5),end);windows.append((year,source,str(start.date()),str(stop.date())));start=stop
    frame=pd.DataFrame(plans)
    for col in ['start','end']:frame[col]=frame[col].astype(object).where(frame[col].notna(),None)
    return frame,windows

def history_evidence(public,years):
    intervals=[];unparsed=[];missing=[]
    for label,satellite in [('snpp','Suomi-NPP'),('terra','Terra')]:
        for row in evidence_rows(public[label].decode()):
            if not row:continue
            found=re.findall(r'(20\d{2})-\d{3}',row[0])
            if not any(int(y) in years for y in found):continue
            try:
                if len(row)!=5:raise ValueError('unexpected table columns')
                doy=re.findall(r'20\d{2}-\d{3}',row[0])
                a=pd.to_datetime(doy[0],format='%Y-%j',utc=True)+pd.Timedelta(row[2]);b=pd.to_datetime(doy[-1],format='%Y-%j',utc=True)+pd.Timedelta(row[3])
                if b<=a:raise ValueError('non-positive interval; endpoint cannot be guessed')
                intervals.append({'satellite':satellite,'start_utc':a,'end_utc':b,'source_url':PUBLIC_SOURCES[label],
                  'source_year_day':row[0],'source_reason':row[4],'local_impact':'unverified','recovery_status':'not_stated_in_table'})
            except Exception as error:
                unparsed.append({'satellite':satellite,'source_url':PUBLIC_SOURCES[label],'raw_cells_json':json.dumps(row),'reason':str(error)})
    payload=json.loads(public['missing'])
    if payload.get('success') is not True or not isinstance(payload.get('html'),str):raise ValueError('Upstream missing-date lookup failed; do not infer no gaps')
    platforms={'Terra (MODIS)':'Terra','Aqua (MODIS)':'Aqua','Suomi NPP (VIIRS)':'Suomi-NPP','NOAA-20 (VIIRS)':'NOAA-20','NOAA-21 (VIIRS)':'NOAA-21'}
    for row in evidence_rows(payload['html']):
        if len(row)!=4:raise ValueError('Missing-date columns changed')
        if row[0][:4].isdigit() and int(row[0][:4]) in years:
            if row[1] not in platforms:raise ValueError('Unknown missing-date platform')
            pd.Timestamp(row[0]);missing.append({'date':row[0],'satellite':platforms[row[1]],'quality':'sp','source_url':PUBLIC_SOURCES['missing']})
    return (pd.DataFrame(intervals,columns=['satellite','start_utc','end_utc','source_url','source_year_day','source_reason','local_impact','recovery_status']),
        pd.DataFrame(missing,columns=['date','satellite','quality','source_url']),
        pd.DataFrame(unparsed,columns=['satellite','source_url','raw_cells_json','reason']))

def history_mirror_valid(frame,year,region):
    required={'acq_datetime','acq_date','satellite','sensor','instrument','quality','confidence','confidence_pct','type','version','frp','scan','track','daynight','geometry_wkb','audit_lon','audit_lat'}
    if not required<=set(frame):raise ValueError('Mirror schema changed')
    times=pd.to_datetime(frame.acq_datetime,utc=True)
    if not times.dt.year.eq(year).all() or not times.dt.date.eq(pd.to_datetime(frame.acq_date).dt.date).all():raise ValueError('Mirror UTC date mismatch')
    if 'year' in frame and not frame.year.eq(year).all():raise ValueError('Mirror partition year mismatch')
    if frame.duplicated().any() or not frame.satellite.isin(HISTORY_SATELLITES).all() or not frame.quality.isin(['sp','nrt']).all():raise ValueError('Mirror duplicates or unexpected platform/quality')
    if not frame.sensor.eq(frame.satellite.map({s:SOURCE_SENSOR[PLATFORM_SOURCE[s]] for s in HISTORY_SATELLITES})).all():raise ValueError('Mirror sensor identity mismatch')
    geometry=shapely.from_wkb(frame.geometry_wkb.map(bytes).to_numpy())
    if not shapely.is_valid(geometry).all() or not shapely.covers(region,geometry).all():raise ValueError('Invalid or out-of-bound mirror geometry')
    if not np.allclose(shapely.get_x(geometry),frame.audit_lon,atol=1e-9,rtol=0) or not np.allclose(shapely.get_y(geometry),frame.audit_lat,atol=1e-9,rtol=0):raise ValueError('Mirror WKB/coordinate mismatch')
    modis=frame.sensor.eq('MODIS')
    if not frame.loc[modis,'confidence_pct'].between(0,100).all() or not pd.to_numeric(frame.loc[modis,'confidence']).eq(frame.loc[modis,'confidence_pct']).all():raise ValueError('Native MODIS confidence invalid')
    if not frame.loc[~modis,'confidence'].isin(['l','n','h']).all() or frame.loc[~modis,'confidence_pct'].notna().any():raise ValueError('Native VIIRS confidence invalid')
    return frame

def history_canonical(parts):
    if not parts:return pd.DataFrame(columns=['acq_datetime','acq_date','satellite','sensor','instrument','quality','version','audit_lon','audit_lat','longitude','latitude','confidence','confidence_pct','type','frp','daynight','scan','track','geometry_wkb','observation_id'])
    p=stack_native(parts).copy();p['acq_datetime']=pd.to_datetime(p.acq_datetime,utc=True);p['acq_date']=p.acq_datetime.dt.strftime('%Y-%m-%d')
    p['longitude']=p.audit_lon.astype(float);p['latitude']=p.audit_lat.astype(float)
    p['quality']='sp';p['coordinate_reference']='OGC:CRS84';p['confidence_pct']=p.confidence_pct.astype('Int64');p['type']=p.type.astype('Int64');p['sensor']=p.source_stream.map(SOURCE_SENSOR);p['geometry_wkb']=shapely.to_wkb(shapely.points(p.longitude.to_numpy(),p.latitude.to_numpy()))
    p['observation_id']=pd.Series([digest(f'{source}|{sha}|{int(row)}'.encode()) for source,sha,row in zip(p.source_stream,p.source_response_sha256,p.source_row_ordinal)],index=p.index,dtype='string')
    if p.observation_id.duplicated().any() or native_keys(p).duplicated().any():raise ValueError('Repeated native identity; no rows automatically dropped')
    if (p.satellite.eq('Aqua')&p.acq_datetime.lt(pd.Timestamp(AQUA_FIRST_LIGHT,tz='UTC'))).any():raise ValueError('Aqua detections precede declared first-light support; retain inputs and review the temporal contract')
    return p

def history_grids(year,canonical,plans,gaps,missing):
    days=pd.date_range(f'{year}-01-01',f'{year}-12-31').strftime('%Y-%m-%d');daily=[];known=set(zip(missing.date,missing.satellite))
    p=canonical.copy();p['date']=pd.to_datetime(p.acq_datetime,utc=True).dt.strftime('%Y-%m-%d')
    for sat in HISTORY_SATELLITES:
        plan=plans[plans.year.eq(year)&plans.source.eq(PLATFORM_SOURCE[sat])].iloc[0]
        frame=pd.DataFrame({'year':year,'date':days,'satellite':sat,'source_stream':PLATFORM_SOURCE[sat]})
        frame['retrieval_state']=plan.status;frame['recorded_detections']=pd.Series(pd.NA,index=frame.index,dtype='Int64')
        queried=pd.Series(False,index=frame.index)
        if plan.days:
            queried=frame.date.ge(plan.start)&frame.date.lt(plan.end)
            frame.loc[~queried,'retrieval_state']='outside_advertised_archive_range'
        if sat=='Aqua':
            before=frame.date.lt(AQUA_FIRST_LIGHT);queried&=~before;frame.loc[before,'retrieval_state']='before_declared_platform_first_light'
        counts=p[p.satellite.eq(sat)].groupby('date').size()
        frame.loc[queried,'recorded_detections']=frame.loc[queried,'date'].map(counts).fillna(0).astype('Int64')
        frame.loc[queried,'retrieval_state']='query_completed_and_locally_checked'
        frame['upstream_lists_missing_standard_data']=[(d,sat) in known for d in frame.date]
        frame['documented_global_gap_on_date']=False
        for event in gaps[gaps.satellite.eq(sat)].itertuples():
            affected=pd.date_range(event.start_utc.floor('D'),(event.end_utc-pd.Timedelta(nanoseconds=1)).floor('D')).strftime('%Y-%m-%d')
            frame.loc[frame.date.isin(affected),'documented_global_gap_on_date']=True
        frame['observing_coverage']='unverified';frame['coverage_adjusted_activity']=np.nan;daily.append(frame)
    daily=pd.concat(daily,ignore_index=True);daily['month']=daily.date.str[:7]
    monthly=daily.groupby(['year','month','satellite'],sort=False).agg(detections_on_queried_dates=('recorded_detections',lambda x:x.sum(min_count=1)),
      days_in_month=('date','size'),supported_queried_days=('recorded_detections',lambda x:int(x.notna().sum())),
      upstream_listed_missing_days=('upstream_lists_missing_standard_data','sum'),dates_overlapping_global_gap=('documented_global_gap_on_date','sum')).reset_index()
    monthly['full_month_standard_detections']=monthly.detections_on_queried_dates.where(monthly.supported_queried_days.eq(monthly.days_in_month)).astype('Int64')
    monthly['period_state']=np.select([monthly.supported_queried_days.eq(0),monthly.supported_queried_days.eq(monthly.days_in_month)],['unavailable','complete_declared_query_month'],default='partial_archive_or_platform_month')
    monthly['observing_coverage']='unverified';monthly['quality']='sp'
    grids=[];p['month']=p.date.str[:7];p['native_confidence']=p.confidence.astype(str)
    for sat in HISTORY_SATELLITES:
        domain=[str(i) for i in range(101)] if sat in ['Terra','Aqua'] else ['l','n','h']
        subset=p[p.satellite.eq(sat)]
        if not subset.native_confidence.isin(domain).all() or not subset.type.isin([0,1,2,3]).all():raise ValueError('Unknown standard native filter domain')
        idx=pd.MultiIndex.from_product([[f'{year}-{i:02}' for i in range(1,13)],[sat],[0,1,2,3],domain],names=['month','satellite','type','native_confidence'])
        f=subset.groupby(idx.names).size().reindex(idx,fill_value=0).rename('detections_on_queried_dates').reset_index()
        support=monthly[monthly.satellite.eq(sat)].set_index('month')
        f['supported_queried_days']=f.month.map(support.supported_queried_days);f['period_state']=f.month.map(support.period_state)
        f['detections_on_queried_dates']=f.detections_on_queried_dates.where(f.supported_queried_days.gt(0)).astype('Int64')
        f['full_month_standard_detections']=f.detections_on_queried_dates.where(f.period_state.eq('complete_declared_query_month')).astype('Int64')
        f['quality']='sp';f['observing_coverage']='unverified';f['reference_model_support']='not_evaluated';grids.append(f)
    grid=pd.concat(grids,ignore_index=True)
    if not (daily.recorded_detections.sum()==monthly.detections_on_queried_dates.sum()==grid.detections_on_queried_dates.sum()==len(p)):raise ValueError('Canonical counts or supported-date ledger do not reconcile')
    return daily,monthly,grid

def verify_year_files(folder):
    folder=Path(folder);manifest=json.loads((folder/'year_manifest.json').read_text())
    actual={str(p.relative_to(folder)) for p in folder.rglob('*') if p.is_file() and p.name!='year_manifest.json'}
    if actual!=set(manifest['files']):raise ValueError('Completed year file inventory changed')
    for name,r in manifest['files'].items():
        raw=(folder/name).read_bytes()
        if len(raw)!=r['bytes'] or digest(raw)!=r['sha256']:raise ValueError(f'Completed-year checksum changed: {name}')
    return manifest
