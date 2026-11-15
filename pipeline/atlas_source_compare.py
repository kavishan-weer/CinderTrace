"""Compare native FIRMS standard-product API rows with the checked mirror extract.
Shared by local tests and the standalone notebook. Never logs or persists MAP_KEY.
"""
from io import BytesIO
from collections import Counter
import json
import numpy as np
import pandas as pd
import shapely

SOURCES={'MODIS_SP':{'T':'Terra','A':'Aqua','Terra':'Terra','Aqua':'Aqua'},
 'VIIRS_SNPP_SP':{'N':'Suomi-NPP','Suomi-NPP':'Suomi-NPP'},
 'VIIRS_NOAA20_SP':{'1':'NOAA-20','N20':'NOAA-20','NOAA-20':'NOAA-20'},
 'VIIRS_NOAA21_SP':{'N21':'NOAA-21','NOAA-21':'NOAA-21'}}


def parse_official_csv(raw,source,start,end,boundary):
    """Reject failed/error/changed-schema responses; clip a bounding-box result exactly."""
    if source not in SOURCES:raise ValueError('Unsupported standard-product source')
    try:frame=pd.read_csv(BytesIO(raw),dtype={'acq_time':'string','satellite':'string','confidence':'string','version':'string'})
    except Exception:raise ValueError('FIRMS response is not valid CSV; do not interpret it as zero') from None
    base={'latitude','longitude','acq_date','acq_time','satellite','instrument','confidence','version','type','frp','scan','track','daynight'}
    required=base|({'brightness','bright_t31'} if source=='MODIS_SP' else {'bright_ti4','bright_ti5'})
    if not required.issubset(frame):raise ValueError('FIRMS CSV schema is incomplete or changed; response is not an observed zero')
    # Whitespace is formatting only; platform aliases remain specific to each requested stream.
    codes=frame.satellite.astype('string').str.strip()
    satellite=codes.map(SOURCES[source])
    if satellite.isna().any():
        received={str(k):int(v) for k,v in codes.fillna('<missing>').value_counts(dropna=False).items()}
        unexpected=sorted(codes[satellite.isna()].fillna('<missing>').unique().tolist())
        raise ValueError(f'Unexpected satellite code for {source} [{start}, {end}): '
                         f'{json.dumps(unexpected)}. Received code counts: {json.dumps(received,sort_keys=True)}. '
                         'No rows were reclassified or discarded. Keep this source/date/code diagnostic for review.')
    times=frame.acq_time.astype('string').str.zfill(4)
    if not times.str.match(r'^\d{4}$').all():raise ValueError('Invalid acquisition time')
    try:
        acquired=pd.to_datetime(frame.acq_date.astype(str)+' '+times.str[:2]+':'+times.str[2:],utc=True,errors='raise')
        lon=pd.to_numeric(frame.longitude,errors='raise');lat=pd.to_numeric(frame.latitude,errors='raise')
    except Exception:raise ValueError('Invalid native date/time/coordinate fields') from None
    if not np.isfinite(lon).all() or not np.isfinite(lat).all() or not lon.between(-180,180).all() or not lat.between(-90,90).all():raise ValueError('Invalid coordinates')
    if not acquired.ge(pd.Timestamp(start,tz='UTC')).all() or not acquired.lt(pd.Timestamp(end,tz='UTC')).all():raise ValueError('API returned observations outside the requested window')
    frame['satellite']=satellite;frame['acq_datetime']=acquired;frame['audit_lon']=lon;frame['audit_lat']=lat
    if frame.version.str.contains('NRT',case=False,na=True).any():raise ValueError('NRT rows received for a standard-product query')
    if not frame.daynight.isin(['D','N']).all():raise ValueError('Invalid day/night value')
    if not frame.type.isin([0,1,2,3]).all():raise ValueError('Missing or unsupported standard-product type')
    if source=='MODIS_SP':
        numeric=pd.to_numeric(frame.confidence,errors='raise')
        if not (numeric.between(0,100)&numeric.eq(numeric.round())).all():raise ValueError('Invalid native MODIS confidence')
        frame['confidence']=numeric.map(lambda v:str(int(v)))
        frame['confidence_pct']=numeric
    else:
        if not frame.confidence.isin(['l','n','h']).all():raise ValueError('Invalid native VIIRS confidence')
        frame['confidence_pct']=np.nan
    for column in ['frp','scan','track']:
        numeric=pd.to_numeric(frame[column],errors='raise')
        if not np.isfinite(numeric).all() or numeric.lt(0).any():raise ValueError('Invalid native numeric field')
        frame[column]=numeric
    inside=shapely.covers(boundary,shapely.points(lon.to_numpy(),lat.to_numpy()))
    return frame.loc[inside].copy()


def native_keys(frame):
    """Published coordinates compared at 5 decimal degrees; multiplicities preserved."""
    times=pd.to_datetime(frame.acq_datetime,utc=True).dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    return pd.Series([f'{s}|{t}|{float(x):.5f}|{float(y):.5f}' for s,t,x,y in zip(frame.satellite,times,frame.audit_lon,frame.audit_lat)],index=frame.index)


def compare_native(mirror,official):
    left=mirror.copy();right=official.copy();left['record_key']=native_keys(left);right['record_key']=native_keys(right)
    lc,rc=Counter(left.record_key),Counter(right.record_key)
    missing=[{'record_key':k,'rows':n} for k,n in (rc-lc).items()]
    extra=[{'record_key':k,'rows':n} for k,n in (lc-rc).items()]
    duplicate_keys=any(n>1 for n in lc.values()) or any(n>1 for n in rc.values())
    differences=[]
    if not duplicate_keys:
        l=left.set_index('record_key');r=right.set_index('record_key')
        columns=['confidence','type','daynight','instrument','version','frp','scan','track','brightness','bright_t31','bright_ti4','bright_ti5']
        common=l.index.intersection(r.index)
        numeric={'type','frp','scan','track','brightness','bright_t31','bright_ti4','bright_ti5'}
        for col in columns:
            if col not in l or col not in r:continue # sensor-inapplicable channels remain null / absent.
            a,b=l.loc[common,col],r.loc[common,col]
            if col in numeric:
                av=pd.to_numeric(a,errors='raise').to_numpy(dtype=float,na_value=np.nan);bv=pd.to_numeric(b,errors='raise').to_numpy(dtype=float,na_value=np.nan)
                same=np.isclose(av,bv,atol=1e-5,rtol=0,equal_nan=True)
            else:same=(a.astype('string').fillna('<NULL>')==b.astype('string').fillna('<NULL>')).to_numpy(dtype=bool)
            for key in common[~same]:differences.append({'record_key':key,'field':col,'mirror':str(l.loc[key,col]),'official':str(r.loc[key,col])})
    status='matched_native_records' if not (missing or extra or differences or duplicate_keys) else 'review_required'
    return {'status':status,'mirror_rows':len(left),'official_rows':len(right),'shared_rows':sum((lc&rc).values()),
      'official_rows_missing_in_mirror':sum((rc-lc).values()),'mirror_rows_not_in_official':sum((lc-rc).values()),
      'duplicate_keys_need_review':duplicate_keys,'native_attribute_differences':len(differences),
      'coordinate_comparison_decimals':5,'numeric_comparison_abs_tolerance':1e-5,
      'coverage_verified':False,'missing_in_mirror':missing,'extra_in_mirror':extra,'attribute_differences':differences}
