"""Conditional NOAA-20/S-NPP matched-pass development benchmark, never a fill.
Matched regional activity does not prove co-observation of quiet cells. Report this
selection bias explicitly and fail the promotion gate until coverage is supplied.
"""
import json
from datetime import datetime,timezone
import duckdb
import h3
import numpy as np
import pandas as pd
from .harmonize import ROOT, CATS, CONF
from .scientific_validation import nested,summary

SQL="""
WITH points AS (
 SELECT DISTINCT acq_datetime,acq_date,lat,lon,satellite,daynight,confidence
 FROM read_parquet(?) WHERE satellite IN ('Suomi-NPP','NOAA-20')
 AND acq_date BETWEEN DATE '2018-04-01' AND DATE '2025-12-31'
), tagged AS (
 SELECT p.*,to_h3(lat,lon) h3_cell,
 CASE confidence WHEN 'l' THEN 1 WHEN 'h' THEN 3 ELSE 2 END conf
 FROM points p
), cells AS (
 SELECT satellite,acq_date,daynight,h3_cell,max(conf) conf,median(epoch(acq_datetime)) pass_time
 FROM tagged JOIN members USING(h3_cell)
 GROUP BY satellite,acq_date,daynight,h3_cell
)
SELECT c.*,k.cat FROM cells c JOIN categories k USING(h3_cell)
"""

def paired_counts(daily,eligible):
    d=daily.copy();d['acq_date']=pd.to_datetime(d.acq_date)
    d['month']=d.acq_date.dt.to_period('M').dt.to_timestamp()
    d=d[d.month.isin(eligible)]
    pass_times=d.groupby(['acq_date','daynight','satellite']).pass_time.median().unstack('satellite')
    if not {'Suomi-NPP','NOAA-20'}<=set(pass_times): return pd.DataFrame(),0
    matched=pass_times.dropna()
    matched=matched[(matched['Suomi-NPP']-matched['NOAA-20']).abs()<=90*60]
    pairs=d.set_index(['acq_date','daynight']).join(matched[[]],how='inner').reset_index()
    if pairs.empty:return pd.DataFrame(),0
    # One record per cell/date/day-night/sensor, retaining each sensor's maximum
    # confidence. S-NPP and NOAA-20 are never concatenated into one fire total.
    assert not pairs.duplicated(['satellite','acq_date','daynight','h3_cell']).any()
    counts=pairs.groupby(['month','cat','conf','satellite']).size().unstack('satellite',fill_value=0)
    complete=pd.MultiIndex.from_product([sorted(pairs.month.unique()),CATS,CONF],names=['month','cat','conf'])
    counts=counts.reindex(complete,fill_value=0)
    counts=counts.reindex(columns=['Suomi-NPP','NOAA-20'],fill_value=0).rename(columns={'Suomi-NPP':'snpp','NOAA-20':'modis'})
    return counts.reset_index(),len(matched)


def run():
    out=ROOT/'data/noaa20_validation'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False);scores=[];preds=[];support=[]
    for region in ('lk','ca','nsw'):
        cells=pd.read_parquet(ROOT/f'data/harmonized/{region}_cells.parquet')
        categories=cells[['h3_cell','cat']].drop_duplicates()
        members=pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet')[['h3_cell']]
        cov=pd.read_parquet(ROOT/f'data/harmonized/{region}_coverage.parquet')
        eligible=cov[(cov.fam=='snpp')&(cov.status=='inferred_available')].month
        with duckdb.connect() as con:
            con.create_function('to_h3',lambda lat,lon:h3.latlng_to_cell(lat,lon,6),['DOUBLE','DOUBLE'],'VARCHAR')
            con.register('members',members);con.register('categories',categories)
            daily=con.execute(SQL,[str(ROOT/f'data/raw/{region}/*.parquet')]).df()
        counts,n=paired_counts(daily,eligible)
        support.append({'region':region,'matched_date_daynight_blocks':n,'deduplicated_pass_cells':len(daily)})
        for (cat,conf),g in counts.groupby(['cat','conf']):
            r=nested(g.set_index('month')[['modis','snpp']].sort_index(),kind='noaa20_conditional_matched_pass')
            if r.empty:continue
            r['region']=region;r['cat']=cat;r['conf']=conf;preds.append(r)
            scores.append(dict(region=region,cat=cat,conf=int(conf))|summary(r))
        print(region,'NOAA-20 matched-pass benchmark',n,flush=True)
    if preds:pd.concat(preds,ignore_index=True).to_parquet(out/'predictions.parquet',index=False)
    report={'status':'not_approved_for_gap_filling','production_fill_enabled':False,'scores':scores,'support':support,
        'unit':'active H3 cell/date/day-night blocks within conditional regional matched passes',
        'matching':'same regional UTC date and day/night; median active-cell acquisition times within 90 minutes',
        'deduplication':'Exact raw detection duplicates removed; max confidence per sensor/cell/date/day-night; sensors kept separate.',
        'uncertainty':'Nested year-held-out empirical P10-P90 transfer residuals, conditional on matched activity.',
        'promotion_blockers':['No independent NOAA-20/S-NPP overpass/quality coverage manifest.',
            'Matching requires detections in both sensors and is selection biased; quiet-cell co-observation is unverified.',
            'Regional matching does not establish each cell was observed within 90 minutes.',
            'NOAA-20 cell/date/day-night benchmark differs from production sensor cell-day units.',
            'No replacement uncertainty validated in actual S-NPP outage conditions.'],
        'inputs':[]}
    import hashlib
    for p in [ROOT/'pipeline/validate_noaa20.py',ROOT/'pipeline/scientific_validation.py']+list((ROOT/'data/raw').glob('*/*.parquet'))+list((ROOT/'data/harmonized').glob('*_coverage.parquet'))+list((ROOT/'data/harmonized').glob('*_cells.parquet'))+list((ROOT/'data/boundaries').glob('*_members.parquet')):
        report['inputs'].append({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(out)

if __name__=='__main__':run()
