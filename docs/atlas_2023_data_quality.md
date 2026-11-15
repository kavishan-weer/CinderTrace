# Sri Lanka 2023 data review

The original frontend remains unchanged. This review uses the immutable `cindertrace_atlas_lk_2023_pilot.zip`, not old harmonized estimates. It adds offline evidence and diagnostics; none are wired into production charts.

## Findings

The checked extract contains **13,366 native observations**, with no exact duplicates or repeated satellite/time/coordinate identities. Monthly totals and native satellite/type/confidence totals reconcile. Standard-quality records, UTC acquisition times, original coordinates and polygon membership were checked. The bundle SHA256 remains `11184caea4d9ca669e4f7f455d120d8f4d898db0bf2086f5c86cb9b47650e49e`.

NASA FIRMS' public missing-data response lists **NOAA-20 standard-data gaps on July 19–22 and September 30, 2023**. The extract contains zero NOAA-20 records on all five dates. These are recorded counts with upstream gap evidence, not coverage-certified no-fire days. The table is global; the exact missing local observing opportunities have not been measured. An unlisted date is not certified complete. The near-real-time columns were not mixed into the standard-product evidence. [NASA missing-data table](https://firms.modaps.eosdis.nasa.gov/api/missing_data/).

The 2023 MODAPS production tables supply **12 S-NPP and 23 Terra gap intervals**. These global intervals have been retained separately from local coverage conclusions. No regional observations fall within the reported half-open windows used for this diagnostic. This consistency check cannot prove that the inventory covers every outage or that every interval affected Sri Lanka. [S-NPP production gaps](https://modaps.modaps.eosdis.nasa.gov/services/production/outages_suomi_npp.html), [Terra production gaps](https://modaps.modaps.eosdis.nasa.gov/services/production/outages_terra.html).

For the S-NPP July event, this pilot has no S-NPP detections on July 26. Its three July 27 detections occur at 20:39–20:40 UTC, after the table's 19:54 UTC end. Keep the recovered observations; do not discard the full month. Recovery of subsequent observing service does not recover observations missed during a gap.

The FIRMS November notice explicitly describes missed S-NPP data as unrecoverable and later announces nominal products on November 6. That announcement is not an exact recovery timestamp. Its timing differs from the MODAPS granule window, so both pieces of evidence are retained without inventing a precise loss interval. A separate notice records NOAA-20's September anomaly. [FIRMS outage notices](https://firms2.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).

November has **14** detections across the four platforms; December has **7**. December's Terra and Aqua counts are both zero. These facts do not establish a month-long outage, an extraction failure, complete observations or physical fire absence. Raw counts remain intact and coverage remains unverified.

The published type totals are vegetation 13,264; other static land 77; offshore 25; volcanic 0. “No volcanic record in this 2023 pilot” does not mean the reference category is empty across history. None of these labels is a verified wildfire identity.

NOAA-21 is outside the mirror's stated 2023 platform scope. The mirror describes its NOAA-21 record as starting in 2024, while NASA's download page lists availability from March 2023. This pilot must be described as a **four-satellite mirror extract**, not all five NASA satellite streams. [Mirror definitions](https://raw.githubusercontent.com/portolan-mirrors/firms-catalog/main/catalog/detections/README.md), [NASA archive scope](https://firms.modaps.eosdis.nasa.gov/download/).

## New diagnostics

Generated under `data/atlas/lk_2023_review/` (ignored by Git):

- `daily_observed_counts.parquet`: 1,460 day/platform rows, raw counts, upstream missing-date flag, global production-gap date overlap and explicit unverified local coverage. Coverage-adjusted activity remains null throughout.
- `monthly_diagnostics.parquet`: all 48 month/platform rows, detection-day counts, longest within-month zero run and source-evidence counts.
- `native_filter_grid.parquet`: all 9,984 month/platform/published-type/native-confidence combinations. MODIS uses integers 0–100; VIIRS uses l/n/h. Recorded zeros and positive counts are explicit; model support remains unevaluated. No confidence crosswalk is invented.
- `native_daynight_frp_qa.parquet`: platform-specific quality-review summaries, not a cross-sensor intensity comparison.
- `upstream_missing_standard_dates_2023.parquet`, `outage_inventory_2023.parquet`, `outage_notice_evidence.parquet`, `source_evidence_conflicts.parquet`: source evidence and discrepancies without overwriting observations.
- `sources/`: original public responses and SHA256/retrieval receipts.
- `review_manifest.json`: checksums of generated outputs and review decisions.

The tracked summary is `docs/atlas_2023_data_quality.json`. Regenerate the review with `.venv/bin/python -m pipeline.atlas_pilot_review`; add `--fetch-sources` to capture fresh upstream notices. A changed upstream snapshot is a new review, not proof that the original mirror extract changed.

## What remains unresolved in audit items 1–7

| Item | What this pilot establishes | Remaining gate |
|---|---|---|
| 1. Zero versus missing | Reconciled recorded zeros and explicit upstream gap evidence | Per-area observing coverage; then affected historical reference medians/seasons |
| 2. Outages | Sourced 2023 S-NPP/Terra intervals, missing standard dates and separate recovery notices | Full historical inventory; local impact and recovery/processing reconciliation |
| 3. NOAA-20 replacement | Provenance preserved and its own missing dates identified | Matched-observation transfer, duplicate prevention and uncertainty validation |
| 4. Local allocation | Observed rows are clipped directly to the polygon | Historical allocation fallback remains unvalidated |
| 5. Filter combinations | Complete native observed grid with explicit states | Reference-category support and frontend/export integration after data repair |
| 6. Terra history | No new early-period validity claim | End-to-end Terra → MODIS → VIIRS evaluation |
| 7. Scientific validation | No old validation score reused | New nested held-out evaluation on repaired historical inputs |

No new harmonized series, medians, seasons, replacement values or confidence bands have been produced.

## Next checkpoint: authoritative-source reconciliation

Run `notebooks/CinderTrace_Atlas_2023_Official_Check.ipynb` in Colab or VS Code. It checks the original ZIP, retrieves the three matching standard-product streams directly from NASA for all 2023 dates, clips the same polygon and compares native record multiplicities and attributes. The 219 requests use the documented maximum of five days each, with checksummed resumable caches. Failed requests and changed schemas never become zero. Country CSV totals are not substituted for the exact polygon/API query.

Obtain a free MAP_KEY using **Get MAP_KEY** on the [NASA FIRMS API page](https://firms.modaps.eosdis.nasa.gov/api/area/). Enter it only into the hidden notebook prompt; no Earthdata password is needed. The key is kept in runtime memory and excluded from request receipts and result files.

The comparison uses five decimal degree coordinate keys, preserves duplicate multiplicities and checks native attributes for unique matched keys. Numeric attribute tolerance is 0.00001 in each field's native unit; it is a formatting tolerance, not scientific uncertainty. Duplicate keys or any unmatched/changed native records require review. The mirror is never overwritten automatically.

Save the executed notebook and `cindertrace_atlas_lk_2023_official_check.zip`. A successful match will establish retrieval consistency against the upstream service, not independent physical fire truth or complete satellite coverage. Resolve source differences before extending the same extraction contract to historical years.

## Validation performed

Twelve importer/comparison/diagnostic tests pass. A separate offline notebook dry run exercised all 219 windows with mocked upstream CSVs, reconciled 13,366 records and 48 monthly totals, and checked that the fake key was absent from exported files. This tested execution and resume-file structure; **the live NASA row comparison has not yet run** because a MAP_KEY is required. No frontend build or UI edits were made in this data-review step.

## Executed official check — checkpoint review

The saved `CinderTrace_Atlas_2023_Official_Check.ipynb` now reports all 219 NASA requests completed and `matched_native_records`: 13,366 mirror rows, 13,366 official rows, 13,366 shared rows; zero missing/extra records, duplicate-key concerns or checked native-attribute differences. All 48 displayed month/platform totals were rechecked locally against the immutable pilot and agree. This supersedes the earlier statement that the live comparison had not run. The pandas concatenation FutureWarning did not prevent completion.

That first checkpoint review inspected executed notebook outputs only. The returned ZIP has now been independently verified: its identity, all 219 raw response receipts, reconstructed observations and 48 monthly totals pass. See `atlas_2023_official_verification.json`. The preceding output-only review remains historical evidence. Preserve the executed notebook unchanged.

The next standalone notebook is `notebooks/CinderTrace_Atlas_LK_2022_2024_Check.ipynb`; follow `atlas_lk_2022_2024_checkpoint.md`. It extends the same observed-data contract to 2022 and 2024, with outage controls and explicit NOAA-21 archive scope, before a full historical rebuild. Keep per-satellite provenance, native confidence, complete filter grids, source snapshots and unknown coverage states. Annual source reconciliation should precede model fitting. Only after the observed history and its coverage limitations are established should common-reference transfer, replacements and held-out validation resume. The original frontend remains unchanged throughout.
