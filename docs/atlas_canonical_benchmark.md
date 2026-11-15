# Verified Sri Lanka observed-standard benchmark

The returned 2022/2024 ZIP is now independently verified. Its SHA256 matches the saved notebook: `6203a50c88921de8c29757192fbcbd9ee2af3ee06bd7f923e5dcf50cc34deea5`. All 1,064 manifested file hashes/byte sizes and 515 NASA request receipts passed. Raw responses were re-parsed, re-clipped to the original polygon and compared with saved observations. The source comparisons, discrepancy tables, daily/monthly/filter grids and outage controls were reproduced locally. See `atlas_lk_2022_2024_verification.json`.

The 2023 checkpoint was independently verified as well. Both executed notebooks and every original input ZIP are preserved. The original frontend has no changes.

## NOAA-21 finding and source decision

The mirror contains 5,775 NOAA-21 records labelled `nrt`, version `2.0NRT`, with unavailable published type. NASA's verified standard stream contains 5,654 records, version `2`, with published types: vegetation 5,603; other static land 44; offshore 7.

Comparing the same satellite and UTC timestamp at five decimal degree coordinates:

- 1,848 native keys occur in both streams.
- 3,806 keys occur only in the standard stream; 3,927 occur only in NRT.
- Among shared keys, type and version differ for all 1,848; FRP differs for 32 and native confidence for 2 at the declared comparison tolerance.

These are processing-stream differences, not counts of new or extinguished physical fires. An unmatched key may reflect processing or geolocation/time revisions; no causal interpretation or inferred one-to-one pairing was imposed. The net difference of 121 rows is not a list of removed false alarms. The original mirror-versus-standard comparison still correctly reports `review_required`; its evidence has not been rewritten to appear matched.

For the separate canonical benchmark, select the independently verified **NASA standard-product stream** for each declared platform and year. This resolves the source-quality choice for 2024 NOAA-21 without claiming that the mirror NRT stream matched standard processing. Its 5,775 NRT records remain in an audit-only file. They are not stacked, relabelled, row-wise coalesced or inserted into missing standard periods.

This rule is recorded in `atlas_observed_source_policy.json` and with the generated dataset. It is a processing-quality selection, not satellite replacement or NOAA-20 gap filling.

## Generated local dataset

Directory: `data/atlas/canonical_lk_2022_2024_v1/`.

| Year | Declared platforms | Standard observations |
|---|---|---:|
| 2022 | Terra, Aqua, S-NPP, NOAA-20 | 8,593 |
| 2023 | Terra, Aqua, S-NPP, NOAA-20 | 13,366 |
| 2024 | Those four plus NOAA-21 | 17,036 |
| Total | Scope varies by year | 38,995 |

The changing platform scope makes these raw annual totals unsuitable for a calibrated cross-year trend. NOAA-21's absence from the declared 2022/2023 scope is not a verified global absence of that platform's data.

The dataset contains:

- `observations.parquet`: 38,995 standard observations, native sensor/confidence/type/FRP fields and exact geometry. Each record links to a verified raw response SHA256, input checkpoint SHA256, relative response filename, source stream, request dates and zero-based parsed CSV row ordinal.
- `verified_request_receipts.json`: the 734 original verified NASA request receipts across the three years.
- `daily_observed_counts.parquet`: all 4,750 expected platform/day rows, including leap day. A zero requires a verified successful query. Observing coverage remains unverified; missing-standard-date and global-gap flags are separate evidence. Coverage-adjusted activity remains null.
- `monthly_observed_counts.parquet`: 156 native platform/month totals, rederived from the chosen standard stream.
- `native_standard_filter_grid.parquet`: 30,096 expected month/platform/published-type/native-confidence combinations. MODIS percentages and VIIRS classes remain separate. Empty categories mean no record in that platform/year, not an established empty historical reference category. Model support remains unevaluated.
- `audit/`: the unchanged NOAA-21 NRT rows, NRT/standard unmatched-key lists, shared-key attribute differences and monthly quality-stream counts.
- `evidence/`, `documented_global_gap_intervals.parquet`, `upstream_missing_standard_dates.parquet`: captured public gap evidence and its receipts. Source lists are not exhaustive local observing records.
- `region.geojson`, `source_policy.json`, `manifest.json`: original spatial support, source-precedence rules, input identities and every generated file hash.

This directory is isolated from legacy data and the frontend. Production export remains disabled; the old harmonized outputs and validation scores are not inputs.

Reproduce locally, without a network request or a key:

```sh
.venv/bin/python -m pipeline.build_atlas_canonical
.venv/bin/python -m unittest discover -s tests -p 'test_atlas*.py'
```

All 33 data tests pass. Tests cover real checkpoint integrity, tampering, source-quality separation, exact response/row provenance, leap day, count reconciliation, unknown coverage states and generated file hashes. The 2022/2024 notebook tests continue to use explicit simulated responses; the returned ZIP checks use the actual submitted evidence.

## What happens next

The three-year benchmark now has a documented standard-product source rule and independently checked raw inputs. No download rerun is needed for these years.

The next data task is to extend that same contract to earlier Sri Lanka history in resumable year partitions, inspecting source quality rather than assuming every mirror row is standard. Historical standard streams should be checked against NASA, while NRT and unsupported dates stay separately identified. Retain the verified 2022–2024 benchmark as a regression cohort so an expansion cannot silently alter it.

Full historical observing coverage, outage recovery accounting, Terra-only transfer, NOAA-20 replacement, local allocation uncertainty and new scientific validation remain open. Do not compute new reference-equivalent medians, seasons or calibrated trend claims from this three-year observed-data benchmark. The original frontend remains unchanged.
