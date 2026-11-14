"""Conservative archive availability, not satellite/cloud observation coverage.
A populated closed archive month is inferred available; detection absence alone cannot
establish a real zero. First/last sensor months and current month are provisional.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import duckdb
import pandas as pd

FAMILIES = {'Terra':'modis','Aqua':'modis','Suomi-NPP':'snpp'}

def build_coverage(raw_glob, idx, as_of=None):
    as_of = pd.Timestamp(as_of or datetime.now(ZoneInfo('Asia/Colombo')).date()).normalize()
    with duckdb.connect() as con:
        dates = con.execute('SELECT satellite, acq_date FROM read_parquet(?) WHERE acq_date <= ?', [str(raw_glob), as_of.date()]).df()
    dates['fam'] = dates.satellite.map(FAMILIES)
    dates['acq_date'] = pd.to_datetime(dates.acq_date)
    dates['month'] = dates.acq_date.dt.to_period('M').dt.to_timestamp()
    rows=[]
    for fam in ['modis','snpp']:
        s=dates[dates.fam==fam]
        first=s.acq_date.min(); last=s.acq_date.max()
        counts=s.groupby('month').size()
        for month in idx:
            n=int(counts.get(month,0))
            state='missing'
            if n:
                state='inferred_available'
                if month==as_of.replace(day=1) or month==first.replace(day=1) or month==last.replace(day=1):
                    state='provisional'
            rows.append(dict(month=month,fam=fam,status=state,detections=n,
                             as_of=as_of,last_detection=last,coverage_basis='regional_bbox_detection_activity'))
    return pd.DataFrame(rows)


def attach_coverage(series, coverage):
    d=series.copy()
    for fam in ['modis','snpp']:
        c=coverage[coverage.fam==fam].set_index('month').status.reindex(d.index).fillna('missing')
        d[f'{fam}_status']=c
        d[fam]=d[fam].where(c!='missing')
    d['training_ok']=(d.modis_status=='inferred_available') & (d.snpp_status=='inferred_available')
    return d
