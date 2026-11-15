# Sri Lanka rebuilt-data sensor-transfer review

Completed on the frozen 171,244-observation standard-data checkpoint for November 2000–December 2024. These are new research results. Earlier dashboard validation scores remain results from the earlier dataset and are not certified by this run.

## What was tested

The target is regional vegetation active-cell-days recorded by a reference sensor, on common eligible UTC calendar dates. One activity cell per sensor/day is counted; Terra and Aqua are combined by cell/day union. This measures observed activity, not unique fires, burned area, complete observation coverage or physical fire truth. The primary grid is H3 resolution 8; resolutions 7/9, native confidence screens, gap masks and recent training windows are tested separately. Native confidence screens are filtering conventions, not equivalent probabilities.

Archive availability, upstream missing-data notices and sourced global production-gap dates determine calendar eligibility. A month needs at least 20 common dates and 80% of calendar dates; a cohort year needs at least eight eligible months. This is a calendar-support threshold, not a percentage of valid satellite coverage. A global interruption is not evidence that Sri Lanka was affected. The conservative primary exclusion and listed-missing-only sensitivity deliberately bracket that uncertainty; neither certifies recovery or local impact.

Whole years are held out. Model choice uses inner held-out fit years; the latest two remaining training years are reserved only for empirical interval calibration. Fit, calibration and test years are disjoint. Random year holdouts may use later years to evaluate earlier years and are hindcast tests. A separate chronological test uses training/calibration through 2021 only. It is contemporaneous sensor transfer, not fire forecasting.

The Terra chain is tested end to end in the later all-sensor overlap period, with both stages fitted there. It does not validate stability back to 2000 or establish early-period uncertainty. Combined MODIS predictions respect the known Terra activity floor.

## Primary held-out results

WAPE is total absolute error divided by total reference activity, not a percentage error for each individual month. Coverage is empirical monthly coverage of separately calibrated nominal intervals; no formal nominal guarantee is asserted under temporal dependence.

| Transfer | Months | WAPE | 80% interval coverage | 90% interval coverage |
|---|---:|---:|---:|---:|
| terra_to_modis | 248 | 27.5% | 80.2% | 91.9% |
| modis_to_snpp | 127 | 22.6% | 89.0% | 92.1% |
| terra_chain_to_snpp | 127 | 29.6% | 74.8% | 85.8% |
| noaa20_to_snpp_diagnostic | 78 | 13.1% | 75.6% | 93.6% |

The MODIS-to-S-NPP transfer improves on the seasonal baseline (22.6% versus 72.9% WAPE). However, the full Terra chain misses nominal interval coverage: 74.8% for the nominal 80% interval and 85.8% for the nominal 90% interval. NOAA-20 calibration has only a small error advantage over native-source identity (13.1% versus 13.6% WAPE), and its nominal 80% interval covers 75.6%. This calendar-aligned comparison is not validation of NOAA-20 gap replacement.

## Chronological and sensitivity checks

The chronological 2022–2024 test actually evaluates 2022 and 2023 only for the MODIS tasks. Under the conservative global-gap-date mask, 2024 has five eligible MODIS months and fails the eight-month cohort threshold. It must not be presented as a successful 2024 evaluation. Terra-to-MODIS has 22 tested months; MODIS-to-S-NPP and the chain have 21 each. NOAA-20 has only two pre-calibration fit years and its chronological test is withheld.

| Transfer | Tested months | Chronological WAPE | 80% coverage | 90% coverage |
|---|---:|---:|---:|---:|
| terra_to_modis | 22 | 38.3% | 86.4% | 100.0% |
| modis_to_snpp | 21 | 33.3% | 71.4% | 90.5% |
| terra_chain_to_snpp | 21 | 29.9% | 85.7% | 90.5% |

The primary direct MODIS transfer performs less well in the chronological test: 33.3% WAPE and 71.4% coverage of the nominal 80% interval. Seven prespecified configurations were evaluated without choosing a winner from test scores. Across them the chain’s nominal 90% coverage ranges from 85.0% to 94.2%; these configurations change the target/filter or sample support, so this range is a sensitivity diagnostic, not a confidence interval or justification to select the best-looking mask.

## Annual errors and rankings

Annual evaluation requires all 12 months to qualify; totals are still only for common eligible dates, not complete annual observing exposure. The primary direct MODIS-to-S-NPP transfer has 12.95% annual WAPE over eight years and rank correlation 0.857. The chain has 16.01% annual WAPE and rank correlation 0.762 over eight years. These are descriptive results with small samples; no significance or general ranking accuracy is claimed. The chronological annual evaluation has only one qualifying year, so its rank is unavailable. Annual intervals are withheld because two calibration years do not support their validation; monthly bounds are never summed.

## Release decisions and next work

- Observed standard-data checkpoint remains frozen; no calibrated values are inserted into it.
- Early-history comparable bands, historical medians/seasons and NOAA-20 gap filling remain disabled.
- Before any filling, pair actual overpass/footprint and valid-observation evidence, establish which interruption products were recovered, and validate replacement during simulated gaps. Maintain native sensor provenance and explicit deduplication.
- Revise and independently evaluate chain uncertainty; do not tune intervals on these same held-out scores and report them as fresh evidence. A changed method needs a separate evaluation plan.
- District/custom-polygon allocation, zero denominators and all category/confidence slices remain unvalidated by this regional vegetation-only experiment. Regional scores must not appear as local/filter-specific scores.
- Complete observing coverage remains unverified; an archive zero is only zero recorded detections and never proof of no fire.
- Frontend unchanged. No production data/export changes.

## Reproduce and inspect

Run `python -m pipeline.atlas_transfer_research` in the project environment, or use the standalone sensor-transfer notebook with the single verified observed-data input ZIP. No Earthdata or FIRMS login is required. Outputs include every held-out prediction, residual and monthly interval, monthly qualifications, annual errors/ranks, complete split audit, methods and hashed manifest. Nine targeted tests verify split isolation, calibration separation, sensor union constraints, unsupported zero denominators, annual support and interval withholding.
