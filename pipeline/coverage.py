"""Conservative archive availability, not satellite/cloud observation coverage.
A populated closed archive month is inferred available; detection absence alone cannot
establish a real zero. First/last sensor months and current month are provisional.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import duckdb
import pandas as pd
import json
import hashlib
from pathlib import Path
from .outages import major_outage_month, SOURCE

FAMILIES = {'Terra':'modis','Aqua':'modis','Suomi-NPP':'snpp'}

def load_evidence(path, raw_dir):
    """Require archive identity and regional observation accounting before restoring zeros.

    Evidence is independently supplied; a successful detection download is insufficient.
    An expected count must come from an observation manifest, never hotspot counts.
    """
    if not path or not Path(path).exists(): return {}
    rows=json.loads(Path(path).read_text())
    result={}
    hashes={}
    for r in rows:
        key=(pd.Timestamp(r['month']).replace(day=1),r['fam'])
        if key in result: raise ValueError('Duplicate coverage evidence key')
        archive=Path(raw_dir)/f'{key[0].year}.parquet'
        if archive not in hashes:
            hashes[archive]=hashlib.sha256(archive.read_bytes()).hexdigest()
        valid=(r.get('archive_sha256')==hashes[archive] and r.get('ingestion_complete') is True
               and r.get('regional_observation_manifest_complete') is True
               and r.get('quality_review_complete') is True
               and r.get('expected_observations',0)>0
               and r.get('received_observations')==r.get('expected_observations')
               and bool(r.get('ingestion_source')) and bool(r.get('observation_source')))
        result[key]={**r,'verified_complete':valid}
    return result

def build_coverage(raw_glob, idx, as_of=None, evidence_path=None):
    as_of = pd.Timestamp(as_of or datetime.now(ZoneInfo('Asia/Colombo')).date()).normalize()
    with duckdb.connect() as con:
        dates = con.execute('SELECT satellite, acq_date FROM read_parquet(?) WHERE acq_date <= ?', [str(raw_glob), as_of.date()]).df()
    dates['fam'] = dates.satellite.map(FAMILIES)
    dates['acq_date'] = pd.to_datetime(dates.acq_date)
    dates['month'] = dates.acq_date.dt.to_period('M').dt.to_timestamp()
    rows=[]
    raw_dir=Path(raw_glob).parent
    evidence=load_evidence(evidence_path or raw_dir/'coverage_evidence.json',raw_dir)
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
            affected=major_outage_month(month,fam)
            proof=evidence.get((pd.Timestamp(month),fam),{})
            complete=proof.get('verified_complete',False) and month+pd.offsets.MonthEnd(0)<as_of
            if complete: state='inferred_available'
            if affected and state=='inferred_available':state='provisional'
            rows.append(dict(month=month,fam=fam,status=state,detections=n,
                             as_of=as_of,last_detection=last,
                             archive_complete=bool(complete),
                             observation_source=proof.get('observation_source'),
                             coverage_basis='verified_archive_and_regional_observations' if complete else 'regional_bbox_detection_activity',
                             known_major_outage=affected,outage_source=(SOURCE if fam=='snpp' else 'https://modaps.modaps.eosdis.nasa.gov/services/production/outages_terra.html') if affected else None))
    return pd.DataFrame(rows)


def attach_coverage(series, coverage):
    d=series.copy()
    for fam in ['modis','snpp']:
        c=coverage[coverage.fam==fam].set_index('month').status.reindex(d.index).fillna('missing')
        d[f'{fam}_status']=c
        d[fam]=d[fam].where(c!='missing')
    d['training_ok']=(d.modis_status=='inferred_available') & (d.snpp_status=='inferred_available')
    return d
