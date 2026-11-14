# Fire outlook: retrospective validation

Follow-up: [probability calibration and the newly scored January–September 2026 holdout](outlook_calibration.md). The original benchmark below is retained unchanged; the follow-up remains outside the app.

Review date: 2026-11-14 (Asia/Colombo).

**The research pipeline is implemented and evaluated. Its forecasts remain outside the app. Numerical results below determine whether it outperforms seasonal history; current revised archives do not establish operational forecast validity.**

## What is predicted

One separate monthly distribution for each of the first, second and third calendar months beginning on the issue date. An issue dated 1 August predicts August, September and October, respectively; these are not cumulative 30/60/90-day totals. It cannot establish an August forecast of December or of the whole NSW summer.

The target is **directly observed Suomi-NPP vegetation fire-active H3 resolution-6 cell-days**, nominal plus high confidence, from 2013 onward. It is not individual fire events, burned area, fire severity or danger to a particular property. Both confidence rows must be eligible and non-provisional. Missing and low-data targets are unavailable, never zero-filled.

This deliberately narrows the original harmonized-series plan: pre-2013 transfers were calibrated on later sensor overlap, so using them as historical forecast labels would leak later information. Existing source labels are still retrospective and regional archive-availability flags remain proxies for sensor completeness. Consequently this is a **pseudo-real-time hindcast**, not a vintage-correct historical replay.

## Public inputs and missing-data rules

- NASA POWER daily UTC temperature (°C), corrected precipitation (mm/day), relative humidity (%) and wind speed (m/s), aggregated to monthly values. Rainfall is summed across days; other variables are averaged.
- Five fixed area-weighted geographic strata per region, chosen from boundary H3 members using seed-42 KMeans and represented by their nearest member centres. Weights reflect stratum area, never fire counts. This is a regional weather approximation, not an area-integrated weather grid.
- A site month requires every calendar day and all four valid variables. Regional weather requires all five sites; missing sites are not silently reweighted. Missing model inputs are never filled from a future date.
- NOAA historical ONI: centred three-month ENSO index. DJF is January, NDJ is December of its stated year. The lag accounts for the centred window and publication/revision delay.
- NOAA PSL monthly HadISST-based DMI for the Indian Ocean Dipole. Negative anomalies remain valid; missing sentinels remain missing.
- Raw responses, retrieval timestamps, URLs, hashes, sampling sites and weights are cached locally. Each model report records input/code hashes and library versions. Refreshing an archive creates a new retrospective experiment; it does not reconstruct historical releases.

| Region | Complete weather months | Weather range | Eligible target months | Target range |
| --- | ---: | --- | ---: | --- |
| Sri Lanka | 190/190 | 2011-01–2026-10 | 165 | 2013-01–2026-09 |
| California | 190/190 | 2011-01–2026-10 | 166 | 2013-01–2026-10 |
| NSW | 190/190 | 2011-01–2026-10 | 166 | 2013-01–2026-10 |

## Fixed availability policy

| Input / label | Latest month allowed at issue month T | Example for 1 August 2019 |
| --- | --- | --- |
| Fire predictors and training labels | T − 2 | June 2019 |
| Weather | T − 3 | May 2019 |
| ONI centre month | T − 5 | March 2019 (FMA window ends April) |
| DMI | T − 4 | April 2019 |

These are conservative observation lags, not forecasts of future weather. NASA documents a distinction between near-real-time and climate-analysis inputs; current ONI/DMI archives can be revised. Lags prevent later observation dates entering predictors, but cannot remove revisions already present in today’s archives. ONI is used as a historical predictor, not presented as NOAA’s current official ENSO diagnosis (monitoring moved to RONI in 2026).

## Validation design

Fixed expanding-window origins: January 2019–December 2025. Each origin retrains using only target months available by T−2. Leads 2 and 3 purge additional recent training rows so their labels also obey that cutoff. All three models are scored on the identical eligible origins. Targets extending beyond December 2025 are excluded, giving 84 / 83 / 82 potential cases. Training needs at least 48 eligible rows and a baseline needs at least five prior examples of the target calendar month. No random train/test split, shuffled cross-validation, test-set parameter search or weather normalization fitted on the full record is used.

The experiment is prequential: earlier evaluation outcomes can enter later origins once available. The 2024–2025 table is a diagnostic within that same rolling evaluation, not a separate untouched holdout. Treat 2019–2025 as a development benchmark for any subsequent revisions.

| Model | Inputs |
| --- | --- |
| Seasonal | Empirical distribution of available previous occurrences of the target calendar month |
| History ML | Target-month sine/cosine; prior seasonal median/P10/P90; fire lags 2,3,4,13,14; target month last year; recent 3-month fire total |
| Weather + climate ML | Same history features plus weather lags 3,4,5; ONI centre lags 5,6; DMI lags 4,5 |

Five independent LightGBM quantile regressors predict log(1+activity), with quantiles 0.10/0.25/0.50/0.75/0.90, 64 trees, learning rate 0.04, 7 leaves, depth 3, minimum 12 child samples, L2 5, seed 42 and one worker. Predictions are transformed back, clipped at zero and sorted to repair crossing. Choices were fixed before inspecting this benchmark; no regional winner was selected after testing.

## Interval and point performance

WIS is a weighted interval score using the median and the central 80% interval: `(0.5 × absolute median error + 0.1 × interval score) / 1.5`, with interval score `width + 10 × distance outside the interval`. Lower is better. Five-quantile mean pinball loss, MAE, WAPE and bias are also saved. Skill is `1 − model score / baseline score`; positive means improvement. Brackets show a paired calendar-year-block bootstrap 95% interval (1,000 resamples, seed 42). Only seven year blocks are available, and intervals are descriptive rather than strong evidence of generalization.

| Region | Lead | Cases | Seasonal WIS | Weather WIS | WIS skill [95% interval] | History ML WIS | Weather vs history WIS skill | Weather P10–P90 coverage |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| Sri Lanka | 1 | 84 | 115.1 | 104.4 | +9.3% [-4.1%, +20.4%] | 111.1 | +6.0% | 76.2% |
| Sri Lanka | 2 | 83 | 116.3 | 110.5 | +5.0% [-7.3%, +16.7%] | 112.9 | +2.2% | 73.5% |
| Sri Lanka | 3 | 82 | 117.4 | 103.3 | +12.0% [-0.5%, +23.7%] | 109.3 | +5.6% | 73.2% |
| California | 1 | 84 | 216.4 | 213.1 | +1.5% [-3.8%, +15.9%] | 210.8 | -1.1% | 73.8% |
| California | 2 | 83 | 218.4 | 215.8 | +1.2% [-4.5%, +16.1%] | 208.0 | -3.7% | 74.7% |
| California | 3 | 82 | 218.9 | 213.6 | +2.4% [-2.0%, +13.8%] | 209.0 | -2.2% | 76.8% |
| NSW | 1 | 84 | 473.0 | 478.0 | -1.0% [-34.3%, +13.1%] | 467.7 | -2.2% | 71.4% |
| NSW | 2 | 83 | 478.4 | 496.7 | -3.8% [-41.3%, +11.1%] | 470.7 | -5.5% | 74.7% |
| NSW | 3 | 82 | 483.8 | 503.0 | -4.0% [-40.9%, +12.1%] | 490.3 | -2.6% | 75.6% |

## Above-normal probability performance

“Above normal” means strictly greater than the available previous same-month median at that origin. Seasonal probabilities use observed exceedance frequency with Beta(1,1) smoothing; ML probabilities interpolate the five predicted quantiles and cap tails at 0.1–0.9. These are not separately calibrated probabilities. Ties can make the seasonal exceedance probability less than 0.5. Brier score measures squared probability error; lower is better. Equal-width reliability bins, sample counts and observed frequencies are saved in each report. Do not advertise a “70% chance” as calibrated on this evidence.

| Region | Lead | Seasonal Brier | History ML Brier | Weather Brier | Weather Brier skill [95% interval] | Numerical gate |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Sri Lanka | 1 | 0.253 | 0.276 | 0.265 | -4.5% [-29.8%, +21.3%] | fail |
| Sri Lanka | 2 | 0.252 | 0.283 | 0.274 | -8.8% [-35.3%, +20.9%] | fail |
| Sri Lanka | 3 | 0.252 | 0.292 | 0.270 | -7.2% [-32.2%, +18.6%] | fail |
| California | 1 | 0.257 | 0.221 | 0.224 | +12.8% [+1.5%, +21.1%] | fail |
| California | 2 | 0.257 | 0.223 | 0.226 | +12.1% [+2.6%, +20.0%] | fail |
| California | 3 | 0.257 | 0.218 | 0.226 | +12.1% [-1.5%, +22.5%] | fail |
| NSW | 1 | 0.239 | 0.285 | 0.280 | -17.0% [-27.6%, -5.0%] | fail |
| NSW | 2 | 0.239 | 0.280 | 0.278 | -16.4% [-29.8%, -3.8%] | fail |
| NSW | 3 | 0.239 | 0.279 | 0.270 | -13.1% [-22.9%, -2.6%] | fail |

## Recent rolling diagnostic (2024–2025)

| Region | Lead | Cases | Seasonal WIS | Weather WIS | Seasonal Brier | Weather Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sri Lanka | 1 | 24 | 82.2 | 92.3 | 0.239 | 0.344 |
| Sri Lanka | 2 | 24 | 82.2 | 85.7 | 0.239 | 0.320 |
| Sri Lanka | 3 | 24 | 82.2 | 81.4 | 0.239 | 0.314 |
| California | 1 | 24 | 98.6 | 86.3 | 0.251 | 0.207 |
| California | 2 | 24 | 98.6 | 88.9 | 0.251 | 0.204 |
| California | 3 | 24 | 98.6 | 85.2 | 0.251 | 0.196 |
| NSW | 1 | 24 | 166.1 | 249.6 | 0.241 | 0.302 |
| NSW | 2 | 24 | 166.1 | 259.0 | 0.241 | 0.308 |
| NSW | 3 | 24 | 166.1 | 252.3 | 0.241 | 0.283 |

## NSW August 2019 story check

The strategy’s proposed Black Summer early-warning claim must follow the evidence. An August issue covers August–October only. The complete output for that issue, including both comparators and actuals, is saved in `data/outlook/results/nsw/august-2019-case.csv`; it was not used to select parameters.

| Target | Seasonal median | Weather median | Weather P10–P90 | Observed | Weather P(above prior median) |
| --- | ---: | ---: | --- | ---: | ---: |
| 2019-08 | 2,228 | 2,003 | 603–3,513 | 2,761 | 31% |
| 2019-09 | 1,937 | 1,369 | 652–2,338 | 2,124 | 27% |
| 2019-10 | 966 | 811 | 565–1,393 | 1,470 | 30% |

## Decision and remaining work

A lead passes the preliminary numerical gate only if it has at least 60 scored cases, positive lower bootstrap bounds for both WIS and Brier improvement over the seasonal baseline, and empirical 80% interval coverage between 65% and 95%. This exploratory gate is necessary but insufficient: no historical-vintage validation, spatial transfer test or operational release test has been completed. `app_ready` and `operationally_validated` remain false for every region.

Numerical passes: 0/9 region–lead combinations. Do not integrate a claimed validated early-warning product based on this run.

Before considering app integration: obtain historical input release vintages or prospectively log forecasts; assess calibration using training-only splits; evaluate any revised model on a newly reserved period; test weather-grid representativeness and sensitivity to lag choices; retain seasonal history as the comparator and fallback. Improvements should be motivated scientifically and re-evaluated without tuning on the same benchmark. Regional results do not support arbitrary polygons, districts or other source/confidence categories.

## Latest research availability

The latest issue is generated separately and explicitly marked unavailable when any required lagged input is missing. No stale-value substitution is used. Latest predictions, where present, inherit the same research-only cautions.

| Region | Issue | Available leads | Unavailable reason |
| --- | --- | --- | --- |
| Sri Lanka | 2026-11-01 | 1, 2, 3 | — |
| California | 2026-11-01 | 1, 2, 3 | — |
| NSW | 2026-11-01 | 1, 2, 3 | — |

## Reproduce locally

```sh
.venv/bin/python -m ml.outlook_data --fetch
.venv/bin/python -m unittest tests.test_outlook -v
.venv/bin/python -m ml.outlook
.venv/bin/python -m ml.validate_outlook
.venv/bin/python -m ml.report_outlook
```

The first command makes public agency downloads and resumes matching cached inputs. Use `--refresh` only deliberately to obtain revised source responses. Generated data remain under ignored `data/outlook/`; no frontend assets or app endpoints are added.

Machine-readable outputs per region: `hindcasts.parquet`, `hindcasts.csv`, `report.json`, `latest-research.json`. They include every comparison model, prediction quantiles, target/issue dates, availability cutoffs, training counts and proper scores. The source/parameter identity is in `report.json`.

## Primary source documentation

- [NASA POWER meteorology sources and near-real-time caveats](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/)
- [NASA POWER data FAQ and latency](https://power.larc.nasa.gov/docs/faqs/data/)
- [NASA POWER monthly service limitations](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/)
- [NOAA ONI definition, revisions and RONI transition](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v5/)
- [NOAA ONI raw historical series](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt)
- [NOAA PSL DMI definition and source](https://psl.noaa.gov/data/timeseries/month/DMI/)
- [NOAA PSL DMI raw monthly series](https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data)
