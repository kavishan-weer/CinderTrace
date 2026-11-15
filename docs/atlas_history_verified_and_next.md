# Sri Lanka history verification and next scientific gate

## Verification result

The supplied combined ZIP matches the executed notebook's SHA256:

`b51ededac8925967d9d7edc58ea07524df7e72c41e0c02dea8ce5af0fded98c7`

Independent local verification checked the 40 outer members, every year ZIP identity, and all **5,704 manifested nested files**. All **2,555 NASA requests** were re-parsed and clipped to the original polygon. Their native records, per-response provenance, source comparisons, daily/monthly/filter grids and missing-date/outage flags were reconstructed rather than accepted from printed notebook totals.

The 22 years contain **132,249 standard observations**. All **36 active source/year comparisons** match the mirror standard records with zero outstanding comparison discrepancies. Source/date combinations outside advertised ranges remain unavailable; they are not counted as matching zero series. All 22 year captures are present, with none remaining. No NRT records were inserted into the historical canonical series.

See `atlas_history_2000_2021_verification.json` for annual counts and checks. Notebook outputs contain pandas FutureWarnings about empty/all-NA concatenation, but no saved execution errors; reconstructed results agree with the packaged data. The local verifier normalizes Arrow/Python missing-value representations without converting nulls to zero.

## Frozen observed-data checkpoint

The earlier history is joined with the independently verified 2022–2024 benchmark in a separate dataset:

`data/atlas/canonical_lk_2000_2024_v1/`

- **171,244** standard observations, each with source-response and parent-checkpoint provenance.
- **3,289** verified raw NASA requests across the joined inputs.
- **36,894** platform/day rows, **1,212** platform/month rows and **249,744** native standard filter combinations.
- The original polygon, its SHA256 and CRS84 coordinate reference included with the dataset.
- **12,287 unavailable platform-days** preserved as nulls, primarily reflecting pre-archive/platform support. They are not observed no-fire days.
- Two partial sensor-start months retain separate queried-period counts and null full-month totals: Aqua July 2002 and S-NPP January 2012.
- Known missing-standard dates and global production-gap evidence remain flags, not estimates of lost fires. A global interruption may not overlap a Sri Lanka pass; it must not automatically invalidate every flagged whole month.

The earliest supported FIRMS archive date is **November 1, 2000**. The four records in 2000 cover November–December only, not a complete year. This checkpoint ends **December 31, 2024**; 2025 onward has not been added. The declared fleet changes over time, so raw annual sums are not a calibrated trend.

The 2024 NOAA-21 source-quality decision remains unchanged: use its verified NASA standard stream and retain the mirror NRT stream separately in the original benchmark audit. The mirror NRT/standard discrepancy is documented, not erased by this join.

A single analysis-input ZIP is available at:

`data/atlas/cindertrace_atlas_lk_observed_2000_2024_v1.zip`

It contains standard observations, original spatial support, availability grids, source reconciliation and verification/policy metadata. It has an internal manifest with every member's hash. The original raw evidence archives remain separate and are identified by their hashes. `atlas_observed_analysis_bundle.json` records this ZIP's identity. This is an input package for the next analysis, not a production release.

## What this establishes—and what remains open

This verifies retrieval and internal consistency against the authoritative service. The mirror and FIRMS service share an upstream detection algorithm; their agreement is not independent physical-fire truth. Clouds, overpass timing, sensitivity and unmeasured local coverage can still affect positive and zero counts.

Known gap dates, unsupported periods, native confidence and processing quality are now explicit in the rebuilt inputs. Complete observing coverage, NOAA-20 replacement, cross-sensor transfer, Terra-only uncertainty and district/custom-area calibration remain unvalidated. No old validation scores, reference-equivalent medians, seasons or uncertainty bands were reused or recomputed.

The original frontend and all executed notebooks/input ZIPs remain unchanged. Production export is disabled. The verified 2022–2024 benchmark files remain frozen.

## Next: eligibility and overlap qualification, then scientific validation

The next notebook can consume the single analysis-input ZIP without repeating the historical downloads or requiring a MAP_KEY for these cached inputs.

1. **Freeze the target and eligible cohorts.** Define reference-sensor recorded activity, not physical fire counts. Qualify source starts, partial months, gap evidence and sparse categories. Distinguish matched dates from verified matched overpasses; hotspot absence alone cannot establish an observing opportunity. Keep conservative gap masks and sensitivity cohorts explicit.
2. **Test a common activity representation.** Build separate native-sensor activity on candidate spatial grids and daily units; assess grid-size sensitivity and Terra/Aqua duplicate handling. A shared grid does not make MODIS/VIIRS equally sensitive. Preserve native confidence filters and published source types.
3. **Evaluate transfer with held-out years.** Compare simple baselines and candidates, selecting inside training folds. Validate Terra → combined MODIS → S-NPP end to end; assess NOAA-20 replacement separately without stacking satellites. Produce actual held-out predictions, residuals, bias and empirical interval coverage.
4. **Validate derived uses separately.** Check annual errors/rankings, training-window sensitivity and any district/custom-area allocation method. Region-level performance cannot certify local estimates or summed-filter intervals. Unsupported outputs stay unavailable.

Only after those scientific gates pass should comparable medians/seasons and analytical frontend integration resume. Observed-only history is now available; it is not a certified harmonized fire history.

## Reproduction and tests

```sh
.venv/bin/python -m pipeline.verify_atlas_history
.venv/bin/python -m pipeline.assemble_atlas_observed
.venv/bin/python -m pipeline.package_atlas_observed
.venv/bin/python -m unittest discover -s tests -p 'test_atlas*.py'
```

The data tests cover actual returned history, nested archive tampering, reconstructed native fields and totals, missing-versus-zero distinctions, source-start/partial-month treatment, the frozen benchmark, output hashes and the packaged analysis inputs. Simulated notebook tests remain labelled as simulations; returned-ZIP verification uses the actual submitted responses.
