# Sri Lanka cached pixel/pass audit: verified results

The returned `cindertrace_atlas_lk_pixel_pass_audit_20261115T004550Z.zip` and saved notebook outputs are consistent. All 34 fire granules were reprocessed without failures, and the run reports rehashing all 68 original science files with no new science downloads. The original frontend, observed checkpoint and completed pilot are unchanged.

## What passed

All 17 manifested ZIP members and the nested result manifest pass their byte-length/SHA256 checks. Embedded methods match the reviewed implementations; frozen notebook inputs match the returned inputs and canonical archive. The saved notebook has no error outputs and prints the matching returned ZIP hash.

All **335 native regional fire pixels** match unique standard archive records. No archive record is reused; no ambiguous or unmatched pixels remain. The maximum coordinate distance to the archive record is **0.747 metres**. Sparse fire coordinates agree exactly with their geolocation-grid coordinates, and both sparse viewing/solar angles agree exactly with the corresponding geolocation angles in this sample. All carried archive type labels are 0; these are source labels, not independent verification of burning type.

The quality screen retains **288 pixels**. It excludes 29 for non-nominal inputs alone, 14 for residual bowtie alone and four for both. This accounts for all 47 exclusions without changing the native detection archive. Pixel/granule counts reproduce the preceding pilot; the geometry-bin totals, pass membership and pass totals are internally consistent.

These checks concern the returned evidence. The original science files and full derived clear-centre tables remain in the user's Drive. Raw array reading and nearest-neighbour queries were not independently rerun locally. Individual coordinate/time archive associations, QA flags and pass assignments were independently recomputed; nearest-neighbour summaries were checked for consistency and source provenance.

## What the pass comparisons establish

There are **27 pass groups** and **eight distinct paired-pass combinations**. The 30-minute window supplies two pairs; 60 and 90 minutes each supply the same eight pairs. A pass is not reused within a temporal-window comparison. The 108 diagnostic rows repeat combinations across temporal, distance and viewing screens; only 48 are unique pair/view/distance combinations.

With known geometry and no additional viewing cap, seven of eight distinct pairs have some mutual clear-centre support at both 250 and 500 metres. At a 60° cap, five pairs have support. At a 40° cap, **none** have shared support in this pilot. A stricter geometry screen cannot be described as an equally supported version of the same comparison.

At 60 minutes / 250 metres / no extra view cap:

| Date | Day/night | Matched clear-centre pairs | S-NPP active centres | NOAA-20 active centres |
|---|---|---:|---:|---:|
| 2021-08-15 | Day | 0 | Unavailable | Unavailable |
| 2021-08-15 | Night | 1,817 | 0 | 0 |
| 2021-08-19 | Day | 176,292 | 48 | 122 |
| 2021-08-19 | Night | 91,036 | 0 | 1 |
| 2022-08-12 | Day | 39,260 | 0 | 4 |
| 2022-08-12 | Night | 122,217 | 1 | 1 |
| 2024-06-05 | Day | 53,878 | 0 | 0 |
| 2024-06-05 | Night | 1,376 | 0 | 0 |

These are pixel-centre diagnostic counts, not equal physical footprints, simultaneous fire observations, area fractions or independent fire events. The positive-control difference remains substantial even after refining spatial support. It does not tell us which sensor is physically correct or establish a replacement factor.

The pass assignment currently minimizes time separation before applying geometry screens. On August 12, 2022 it selects the later S-NPP daytime pass; the earlier pass remains unmatched. The next matched-observation study must establish geometry/support eligibility for **all** temporal candidates before assigning one-to-one pairs. It must not choose the alternative because its fire counts look preferable.

## Next stage: broader validation design

The six-day workflow is now verified sufficiently to plan expansion; coverage, missing-month zeros, replacement uncertainty and historical bands remain unvalidated. Do not rerun these completed pilot notebooks.

A calendar-only design has been frozen in `docs/atlas_viirs_expansion_design_v1.json`, with dates in `docs/atlas_viirs_expansion_dates_v1.csv`:

- **54 dates across 2018–2024**, selected by deterministic hashing within half-quarter calendar strata, without ranking detection counts. Pilot dates are excluded.
- **22 fit dates**, **16 calibration dates**, **16 evaluation dates**, with disjoint calendar years. NOAA-20's standard archive begins in April 2018 in this checkpoint, so the two unsupported first-quarter slots remain absent instead of being forced into the sample.
- Query public metadata and estimate volume before obtaining more science files; reuse existing caches. No additional science files have been fetched in this planning step.

Two questions must remain distinct. Paired-support comparisons describe sensor differences conditional on observed common support. A deployable simulated-outage predictor can use NOAA-20 observations, its own quality/geometry and calendar information, but **cannot use S-NPP fire/cloud masks or reference-derived support** that would be unavailable during an actual S-NPP outage. Reference availability can qualify evaluation labels, not supply prediction features.

Whole dates/passes must stay together through fit/calibration/evaluation. Coverage and widths must be reported on held-out date groups, with unsupported intervals withheld. The earlier aggregate dataset and pilot scores have already been inspected: the expanded study is not a blind external replication. No monthly/annual interval or early-history claim can be validated from these few sampled passes, and custom-area allocation remains separate work.

No gap filling or reconstructed frontend data is enabled by these results.

Machine-readable verification: `docs/atlas_pixel_pass_output_review.json`. Reproduce verification with `python -m pipeline.verify_atlas_pixel_pass`. Existing cache-audit tests pass, including the complete synthetic NetCDF workflow, archive ambiguity handling, matching uniqueness, corrupt-cache rejection and notebook ZIP export.

## Expanded public inventory completed

The metadata-only inventory has now been retrieved for all 54 frozen dates: 638 listed science files, including 316 fire granules. Every listed fire granule has one unique geolocation companion. The 632 linked fire/companion files total **45.57 GiB** by catalogue sizes; six additional geolocation listings have no listed fire companion. No new science files have been downloaded. The original 5 GiB pilot cache remains preserved.

Two early NOAA-20 dates require source reconciliation. The VJ114IMG Collection 2 CMR query returns no granules, even without a spatial filter, on April 19 and May 27, 2018. The standard archive contains two NOAA-20 detections on April 19 and none on May 27. This does not determine whether the cause is catalogue omission, product availability or a source/version discrepancy. An attempted alternate LAADS metadata route returned HTML rather than usable directory records and does not establish recovery. Neither date may be treated as verified no-fire coverage; keep them explicitly unavailable for pixel-level comparisons until resolved.

Full metadata pages, receipts, inventory and file hashes are under `data/atlas/viirs_expansion_inventory_v1/`; the summary is `docs/atlas_viirs_expansion_inventory.json`. The next processing notebook should stage new raw files temporarily, retain receipts and derived evidence for resuming, and preserve the original pilot cache. It must resolve or explicitly withhold these two dates, compute all temporal candidates' spatial support before assigning pairs, and keep the operational simulated-outage predictor separate from reference-conditioned matching diagnostics. There is no need for the user to rerun either completed pilot now.
