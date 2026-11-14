"""Audit generated H3 outputs and compare their saved LOYO scores with a square-grid snapshot.
Usage: python -m pipeline.validate
The baseline snapshot must be taken before migration (data/baseline_square/harmonized).
"""
import json
import pathlib
import duckdb
import h3
import numpy as np
import pandas as pd
from .grid import H3_RESOLUTION
from .regions import REGIONS

ROOT = pathlib.Path(__file__).resolve().parent.parent

def run():
    lines = ['# Coverage and selected-area validation', '',
             'Development LOYO scores below use model-selection folds and are selection-optimistic. '
             'They are not independent repaired-release validation. Versioned nested results are generated separately by pipeline.scientific_validation.', '',
             'H3 resolution 6; unchanged raw data, source-category thresholds, confidence convention, '
             'combined Terra+Aqua reference. Monthly LOYO now excludes provisional/missing reference months and retains category-level zero months. '
             'Square-grid scores are from the pre-migration output snapshot and a different evaluation sample; this is not a controlled grid-only comparison. WAPE is lower-is-better.', '',
             '| Region | Vegetation confidence | Square model WAPE | H3 naive WAPE | H3 model WAPE | H3 predictive R² |',
             '|---|---|---:|---:|---:|---:|']
    seams, audits = [], []
    for region, config in REGIONS.items():
        report = json.loads((ROOT/f'data/harmonized/{region}_report.json').read_text())
        old = json.loads((ROOT/f'data/baseline_square/harmonized/{region}_report.json').read_text())
        members = pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet')
        cells = pd.read_parquet(ROOT/f'data/harmonized/{region}_cells.parquet')
        monthly = pd.read_parquet(ROOT/f'data/harmonized/{region}_monthly.parquet')
        assert members.h3_cell.is_unique
        assert all(h3.is_valid_cell(x) and h3.get_resolution(x)==H3_RESOLUTION for x in members.h3_cell)
        assert set(cells.h3_cell) <= set(members.h3_cell)
        assert not cells.duplicated(['h3_cell','month','fam','cat','conf']).any()
        assert cells.groupby('h3_cell').cat.nunique().max()==1
        assert cells.groupby('h3_cell')['sub'].nunique().max()==1
        assert (cells.area_km2>0).all() and (cells.cell_days>0).all()
        known=monthly[monthly.source!='missing']
        assert np.isfinite(known.harmonized).all()
        bounded=known.dropna(subset=['lo','hi'])
        assert monthly.loc[monthly.source=='missing',['harmonized','lo','hi']].isna().all().all()
        assert (bounded.lo>=0).all() and (bounded.lo<=bounded.harmonized).all() and (bounded.hi>=bounded.harmonized).all()
        unsupported=known[(known.model!='empty_reference_slice')&((known.month<'2002-08-01')|((known.low_data)&(known.source!='viirs_observed')))]
        assert unsupported[['lo','hi']].isna().all().all()
        assert not monthly.loc[monthly.period_status!='inferred_available','comparison_eligible'].any()
        assert not monthly.loc[(monthly.modis_status!='inferred_available') | (monthly.snpp_status!='inferred_available'),'training_eligible'].any()
        from .analytics import export_subregions, selected_monthly
        full=selected_monthly(cells,monthly,members)
        assert np.allclose(full.harmonized,monthly.harmonized,equal_nan=True)
        subs=export_subregions(region)
        allocated=subs[subs.selected_cells>0].groupby(['month','cat','conf']).harmonized.agg(lambda x:x.sum(min_count=len(x)))
        reference=monthly.set_index(['month','cat','conf']).harmonized.reindex(allocated.index)
        supported=allocated.notna() & reference.notna()
        assert np.allclose(allocated[supported],reference[supported])
        assert not subs.loc[subs.harmonized.isna(),'comparison_eligible'].any()
        # Independently count retained input rows: no category or confidence is discarded.
        con = duckdb.connect()
        con.create_function('to_h3',lambda lat,lon:h3.latlng_to_cell(lat,lon,H3_RESOLUTION),['DOUBLE','DOUBLE'],'VARCHAR')
        con.register('members',members)
        expected = con.execute("SELECT satellite, count(*) n FROM read_parquet(?) r JOIN members m ON to_h3(r.lat,r.lon)=m.h3_cell GROUP BY satellite",[str(ROOT/f'data/raw/{region}/*.parquet')]).df().set_index('satellite').n
        fams={'Terra':'terra','Aqua':'aqua','Suomi-NPP':'snpp','NOAA-20':'n20','NOAA-21':'n21'}
        for satellite,fam in fams.items():
            assert cells[cells.fam==fam].detections.sum()==expected.get(satellite,0), (region,fam)
        assert cells[cells.fam=='modis'].detections.sum()==expected.get('Terra',0)+expected.get('Aqua',0)
        con.close()
        for conf,label in [(1,'low'),(2,'nominal'),(3,'high')]:
            key=f'veg/conf{conf}'
            s,b=report['slices'][key],old['slices'][key]
            v=s['validation_LOYO_monthly']; bv=b['validation_LOYO_monthly']
            lines.append(f"| {config['name']} | {label} | {bv[b['model']]['WAPE']:.4f} | {v['naive']['WAPE']:.4f} | {v[s['model']]['WAPE']:.4f} | {v[s['model']]['R2']:.3f} |")
        seam=report['seam_default_veg_nom_high']
        seams.append(f"| {config['name']} | {seam['raw_merged_2012_over_2011']:.2f}× | {seam['harmonized_2012_over_2011']:.2f}× |")
        audits.append(f"- {config['name']}: {len(members):,} boundary cells; {int(expected.sum()):,} retained detections; {subs['sub'].nunique()} admin areas ({subs.loc[subs.selected_cells==0,'sub'].nunique()} without H3 centres); identity, membership, raw and area conservation, eligibility and uncertainty checks passed.")
    lines += ['', '## Transition comparison', '', 'Vegetation, nominal + high confidence. These are annual 2012/2011 ratios, not independent accuracy scores.', '', '| Region | Raw merged | Harmonized |','|---|---:|---:|', *seams, '', '## Integrity audit', '', *audits, '', '## Interpretation and limits', '',
              '- H3 changes cell-day units, coastal membership and category assignments; compare predictive errors rather than expecting identical totals. Resolution 6 is the initial production grid, not a demonstrated optimum.',
              '- H3 slightly improves some slices and worsens others versus squares; retain the migration for a consistent map/query schema, not as a claim of universal accuracy improvement.',
              '- Cell centres use the existing 0.03° coastal buffer. This is approximate clipping; whole cells and their centre/nearest subdivision labels can cross administrative borders. Raw bbox files remain untouched.',
              '- H3 cells vary in area; area_km2 stores actual cell area, not the portion intersecting land or an AOI.',
              '- R² now uses 1 − SSE/SST, MAE is included, and predictions/bands are constrained nonnegative. Observed-month bands still collapse to observations and do not represent measurement uncertainty.',
              '- Validation uses only inferred-available closed reference months; category-level zeros are retained. These are availability proxies from hotspot activity, not verified satellite observation/cloud coverage. Model choice still uses the held-out scores, not an independent final test.',
              '- Static/volcano/offshore slices can be sparse and use unvalidated fallback ratios. Cell-level source labels use the full history and are heuristic, not independently verified classifications.',
              '- Selected-area outputs use local S-NPP observations or MODIS-share allocation of the regional transfer. Areas without MODIS support for a nonzero regional prediction remain unallocatable. Local accuracy and local interval coverage are unvalidated; land-cover inputs, reference-fleet review and independent satellite validation remain future work.', '']
    target=ROOT/'docs/coverage_validation.md'
    target.write_text('\n'.join(lines))
    print('\n'.join(lines))

if __name__=='__main__':
    run()
