# Scientific repair status — 14 November 2026

Items 1–7 remain a release gate. This work repairs software and adds reproducible scientific checks; it does not certify the archive or complete the scientific repair. No new analytical feature or gap fill was released. The user confirmed that no additional observation records are available.

## Status by audit item

| Item | Work performed | Remaining requirement |
|---|---|---|
| 1. Zero versus missing | Added archive-hash-bound regional observation evidence, retained unknown months, recorded ingestion provenance for future fetches, rebuilt monthly, district and browser outputs. | No independently verified observation manifests exist in this checkout. Genuine regional zero months cannot yet be identified; zero-restoration and resulting corrected medians/seasons remain blocked. |
| 2. Outages | Pinned and parsed NASA mission tables: 1,166 S-NPP/Terra events, plus a separate FIRMS notice inventory. Multi-day unknown-recovery events and reviewed quality episodes exclude months conservatively. | Most mission-table rows do not specify product recovery or regional impact. Sub-day events require footprint/granule reconciliation; archive recovery must be checked against the actual product. |
| 3. NOAA-20 | Added separate-sensor deduplication and conditional matched-pass nested validation, uncertainty and provenance. | Passes are matched by regional detection activity and median acquisition time, not independent co-observation. Quiet-cell coverage and actual outage replacement uncertainty remain unverified. Filling is disabled. |
| 4. Allocation | Benchmarked existing MODIS shares against a fixed training-only seasonal prior candidate across all three regions. Scored matched-support and zero-denominator cohorts separately; preserved null slices. | Candidate does not establish acceptable district uncertainty and fails the key Sri Lanka nominal vegetation zero-denominator cohort. No fallback promoted. Arbitrary polygons are not validated by district results. |
| 5. Combinations | Retained all 12 monthly combinations, added empty/sparse/unavailable slice status and interval provenance to static/custom-area responses. Browser and Python comparisons reject absent/duplicate combinations rather than sum a partial total. | Full interactive/export/mobile journey (item 18) remains a separate release check; structural empty-reference categories are not independently verified heat-source absence. |
| 6. Terra chain | Added outer-year-held-out Terra → combined MODIS → S-NPP chain tests and training-only end-to-end residual intervals. Excluded flagged reference months from stage-1 ratios. Withheld arbitrary sparse half/double ranges. | Later-overlap performance cannot certify early-period representativeness. Early production bands stay withheld. |
| 7. Scientific validation | Reran nested regional predictions, empirical coverage, full transfer-chain diagnostics, district allocation and paired training-window sensitivity on rebuilt inputs. Saved predictions, residuals, annual eligible sums, protocols and hashes in new versioned directories. | Inputs still lack verified observation coverage. These are development results, not validation of a fully repaired archive. Annual rankings and joint-filter intervals are not validated. |

## Selected results

Vegetation, nominal confidence only. These scores must not be displayed as nominal+high, all-category, local-area or early-history validation. WAPE is sum absolute error / sum observations. Interval coverage is empirical containment of held-out observations in the proposed P10–P90 interval; the target is 80%.

| Region | Eligible outer months | Regional WAPE | Regional interval coverage | Chain months | Terra-chain WAPE | Chain interval coverage |
|---|---:|---:|---:|---:|---:|---:|
| Sri Lanka | 147 | 18.7% | 78.9% | 127 | 32.2% | 78.7% |
| California | 153 | 12.7% | 77.8% | 153 | 16.3% | 78.4% |
| New South Wales | 153 | 10.6% | 79.1% | 153 | 21.6% | 77.8% |

Existing scaled district intervals cover only 33.9% (California), 46.2% (Sri Lanka) and 44.0% (NSW) of these nominal vegetation observations. The seasonal-prior candidate improves aggregate point WAPE but worsens these interval coverages to about 17–25%. In the Sri Lanka nominal zero-denominator cohort, its WAPE is 100% across 25 district rows from one month. This is insufficient evidence to release a fallback. Current and candidate scores on supported rows must be compared using `district_cohorts`, not unpaired aggregate populations.

Training-window sensitivity uses identical 2020–2025 target months for early-window and full-overlap outer fits (`paired_training_windows`). It is not attribution of orbit-drift effects. Source-category masks remain retrospective.

## Evidence and reproducibility

- Latest regional/chain/district predictions: `data/scientific_validation/20261114T122303Z/predictions.parquet` and `district-predictions.parquet`; protocol pins code and input hashes.
- Latest conditional NOAA-20 predictions: `data/noaa20_validation/20261114T122324Z/predictions.parquet`.
- Reviewable summaries: [scientific_validation_summary.json](scientific_validation_summary.json), [scientific_validation_protocol.json](scientific_validation_protocol.json), [noaa20_validation_summary.json](noaa20_validation_summary.json).
- Earlier `data/validation_nested`, `data/transfer_sensitivity_v1` and `data/spatial_transfer_v1` results remain unchanged and describe the earlier dataset. Development LOYO scores in `coverage_validation.md` are selection-optimistic and separately labelled.
- Observation evidence template: [coverage_evidence.example.json](coverage_evidence.example.json). Place reviewed evidence at `data/raw/<region>/coverage_evidence.json`. Expected/received counts must refer to the entire regional observation manifest for that month, including quality and ingestion accounting; counts of hotspots or populated days are insufficient. Archive SHA256 mismatch, incomplete quality review, zero expected observations or unequal counts cannot restore a zero. `inferred_available` is retained as the legacy consumer status; `archive_complete` and `coverage_basis` identify the independently evidenced subset.
- Current archives have zero independently verified complete sensor-month records. Sri Lanka has 16 missing MODIS months within the analysis period; all three regions also have an unavailable current S-NPP month. Pre-mission S-NPP rows are unavailable by design.
- Future downloads write an ingestion manifest. This is download provenance, not proof of observation completeness. Existing raw archives were not rewritten or retrospectively certified.

```sh
.venv/bin/python -m pipeline.outage_inventory
.venv/bin/python -m pipeline.repair_release
.venv/bin/python -m pipeline.scientific_validation
.venv/bin/python -m pipeline.validate_noaa20
.venv/bin/python -m pipeline.validate
```

Each repair run preserves previous monthly outputs. Existing local-query servers need a restart after regeneration to clear their cached datasets. Scientific validation outputs have unique timestamp directories.

## Sources and outage policy

- [NASA MODAPS S-NPP mission outage table](https://modaps.modaps.eosdis.nasa.gov/services/production/outages_suomi_npp.html)
- [NASA MODAPS Terra mission outage table](https://modaps.modaps.eosdis.nasa.gov/services/production/outages_terra.html)
- [NASA FIRMS outage, processing and quality notices](https://firms2.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html)

Original HTML is pinned under `docs/sources/` with retrieval date 2026-11-14; parsed rows and source hashes are in `outage_inventory.json` and `outage_notices.json`. Contradictory start/end timestamps remain flagged without invented corrections. Mission-table recovery is unknown unless explicitly supported; processing resumption, quality clearance from a stated time, recovered processed products, delays and unrecoverable interruptions are distinct notice types. A notice publication date is not an outage interval. FIRMS November 2025 nominal processed-data recovery is retained as a notice and does not imply every unrelated outage that month recovered.

The monthly exclusion rule uses documented events lasting at least 24 hours, the earlier reviewed S-NPP list, and the March 2026 Terra quality episode. Shorter global outages remain inventoried with unresolved local impact. This is a conservative exclusion policy, not a complete regional observing-coverage model.

## Verification

63 Python tests and 35 frontend tests passed; the production build passed. The actual-data integrity audit verified raw detection retention, H3 membership, all 12 slice keys, administrative conservation where allocation is supported, and comparison eligibility. New tests check archive-bound zero evidence, stale evidence rejection, absent/duplicate filter rows, outer-target isolation, NOAA-20 confidence/pass matching, candidate conservation and target-label exclusion, and withheld sparse uncertainty. These checks do not establish satellite coverage or complete item 18. Browser mobile/PNG journeys were not newly exercised in this pass.
