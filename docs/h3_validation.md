# H3 migration validation

H3 resolution 6; unchanged raw data, source-category thresholds, confidence convention, combined Terra+Aqua reference, and monthly leave-one-year-out (LOYO) procedure. Square-grid scores are from the pre-migration output snapshot. WAPE is lower-is-better.

| Region | Vegetation confidence | Square model WAPE | H3 naive WAPE | H3 model WAPE | H3 predictive R² |
|---|---|---:|---:|---:|---:|
| Sri Lanka | low | 0.5764 | 0.7925 | 0.5793 | 0.587 |
| Sri Lanka | nominal | 0.1809 | 0.2504 | 0.1859 | 0.929 |
| Sri Lanka | high | 0.4044 | 0.4573 | 0.3988 | 0.734 |
| California | low | 0.2801 | 0.9113 | 0.2910 | 0.654 |
| California | nominal | 0.1401 | 0.1645 | 0.1360 | 0.932 |
| California | high | 0.1395 | 0.1427 | 0.1418 | 0.985 |
| New South Wales | low | 0.3870 | 0.8402 | 0.3823 | 0.612 |
| New South Wales | nominal | 0.1171 | 0.1657 | 0.1155 | 0.944 |
| New South Wales | high | 0.1408 | 0.1705 | 0.1417 | 0.976 |

## Transition comparison

Vegetation, nominal + high confidence. These are annual 2012/2011 ratios, not independent accuracy scores.

| Region | Raw merged | Harmonized |
|---|---:|---:|
| Sri Lanka | 7.69× | 1.08× |
| California | 3.72× | 1.16× |
| New South Wales | 2.46× | 0.72× |

## Integrity audit

- Sri Lanka: 1,848 boundary cells; 207,552 retained raw detections; all identity, membership, conservation and uncertainty checks passed.
- California: 10,973 boundary cells; 2,185,727 retained raw detections; all identity, membership, conservation and uncertainty checks passed.
- New South Wales: 19,235 boundary cells; 2,741,375 retained raw detections; all identity, membership, conservation and uncertainty checks passed.

## Interpretation and limits

- H3 changes cell-day units, coastal membership and category assignments; compare predictive errors rather than expecting identical totals. Resolution 6 is the initial production grid, not a demonstrated optimum.
- H3 slightly improves some slices and worsens others versus squares; retain the migration for a consistent map/query schema, not as a claim of universal accuracy improvement.
- Cell centres use the existing 0.03° coastal buffer. This is approximate clipping; whole cells and their centre/nearest subdivision labels can cross administrative borders. Raw bbox files remain untouched.
- H3 cells vary in area; area_km2 stores actual cell area, not the portion intersecting land or an AOI.
- R² now uses 1 − SSE/SST, MAE is included, and predictions/bands are constrained nonnegative. Observed-month bands still collapse to observations and do not represent measurement uncertainty.
- Validation still excludes zero-S-NPP months and includes partial recent months. Missing coverage is not yet distinguished from no activity. Model choice uses these same held-out scores, so they are model-selection estimates rather than an independent final test.
- Static/volcano/offshore slices can be sparse and use unvalidated fallback ratios. Cell-level source labels use the full history and are heuristic, not independently verified classifications.
- Selected-area calibration, land-cover inputs, reference-fleet review and independent satellite validation remain separate work before the web app can make strong local claims.
