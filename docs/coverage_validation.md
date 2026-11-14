# Coverage and selected-area validation

H3 resolution 6; unchanged raw data, source-category thresholds, confidence convention, combined Terra+Aqua reference. Monthly LOYO now excludes provisional/missing reference months and retains category-level zero months. Square-grid scores are from the pre-migration output snapshot and a different evaluation sample; this is not a controlled grid-only comparison. WAPE is lower-is-better.

| Region | Vegetation confidence | Square model WAPE | H3 naive WAPE | H3 model WAPE | H3 predictive R² |
|---|---|---:|---:|---:|---:|
| Sri Lanka | low | 0.5764 | 0.8220 | 0.5849 | 0.628 |
| Sri Lanka | nominal | 0.1809 | 0.2493 | 0.1849 | 0.927 |
| Sri Lanka | high | 0.4044 | 0.4678 | 0.4115 | 0.765 |
| California | low | 0.2801 | 0.9362 | 0.2983 | 0.700 |
| California | nominal | 0.1401 | 0.1621 | 0.1298 | 0.906 |
| California | high | 0.1395 | 0.1427 | 0.1418 | 0.985 |
| New South Wales | low | 0.3870 | 0.8447 | 0.3856 | 0.611 |
| New South Wales | nominal | 0.1171 | 0.1650 | 0.1097 | 0.946 |
| New South Wales | high | 0.1408 | 0.1701 | 0.1426 | 0.975 |

## Transition comparison

Vegetation, nominal + high confidence. These are annual 2012/2011 ratios, not independent accuracy scores.

| Region | Raw merged | Harmonized |
|---|---:|---:|
| Sri Lanka | 7.69× | 1.08× |
| California | 3.72× | 1.09× |
| New South Wales | 2.46× | 0.72× |

## Integrity audit

- Sri Lanka: 1,848 boundary cells; 207,552 retained detections; 25 admin areas (0 without H3 centres); identity, membership, raw and area conservation, eligibility and uncertainty checks passed.
- California: 10,973 boundary cells; 2,185,727 retained detections; 58 admin areas (0 without H3 centres); identity, membership, raw and area conservation, eligibility and uncertainty checks passed.
- New South Wales: 19,235 boundary cells; 2,741,375 retained detections; 129 admin areas (7 without H3 centres); identity, membership, raw and area conservation, eligibility and uncertainty checks passed.

## Interpretation and limits

- H3 changes cell-day units, coastal membership and category assignments; compare predictive errors rather than expecting identical totals. Resolution 6 is the initial production grid, not a demonstrated optimum.
- H3 slightly improves some slices and worsens others versus squares; retain the migration for a consistent map/query schema, not as a claim of universal accuracy improvement.
- Cell centres use the existing 0.03° coastal buffer. This is approximate clipping; whole cells and their centre/nearest subdivision labels can cross administrative borders. Raw bbox files remain untouched.
- H3 cells vary in area; area_km2 stores actual cell area, not the portion intersecting land or an AOI.
- R² now uses 1 − SSE/SST, MAE is included, and predictions/bands are constrained nonnegative. Observed-month bands still collapse to observations and do not represent measurement uncertainty.
- Validation uses only inferred-available closed reference months; category-level zeros are retained. These are availability proxies from hotspot activity, not verified satellite observation/cloud coverage. Model choice still uses the held-out scores, not an independent final test.
- Static/volcano/offshore slices can be sparse and use unvalidated fallback ratios. Cell-level source labels use the full history and are heuristic, not independently verified classifications.
- Selected-area outputs use local S-NPP observations or MODIS-share allocation of the regional transfer. Areas without MODIS support for a nonzero regional prediction remain unallocatable. Local accuracy and local interval coverage are unvalidated; land-cover inputs, reference-fleet review and independent satellite validation remain future work.
