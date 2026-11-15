# Sri Lanka observation-evidence pilot: returned-output review

The saved notebook and `cindertrace_atlas_lk_observation_evidence_20261115T001225Z.zip` are verified. The run completed all 34 listed fire-granule screens and their 34 geolocation companions, with no reported download or screening failures. The frontend and frozen observed dataset remain unchanged.

## Verification

All 64 manifested ZIP members pass byte-length and SHA256 checks; nested metadata and result manifests also pass. The ZIP hash matches the saved notebook output. The saved notebook has eight executed code cells with no error outputs, and its embedded method matches the reviewed local implementation.

All 68 science-file receipts have the expected product, acquisition, granule identity and catalogue size. The original NetCDF files are in the user's cache, not in this ZIP: their download receipts and derived-table consistency were checked here; the raw science arrays were not independently reread locally.

The 1,909,386 cell-support rows have valid resolution-8 H3 cells, unique granule/cell keys, consistent provenance and nonnegative integer counts. Their totals reproduce every granule summary. All ten local fire-mask classes sum to the geolocated local pixel totals. Daily statuses and all 19 time-candidate diagnostics reproduce from the returned support tables. Twenty-five granules checked sparse-fire coordinates against geolocation with zero reported coordinate difference; nine had no sparse fires and retain the weaker time/grid-shape alignment status. Three bounding-box catalogue matches have no actual local pixel centres, reinforcing why catalogue matches alone do not certify regional observations.

## What the results establish

For all **ten available platform-days**, the unfiltered local fire-mask counts agree exactly with the frozen standard detection archive. The two absent S-NPP platform-days remain unavailable. These checks support the consistency of this sample, not a blanket accuracy certification for the archive or all historical months.

| UTC day | Platform | Native archive and raw fire-mask count | Stricter screened fire-centre count |
|---|---|---:|---:|
| 2021-08-15 | S-NPP | 0 | 0 |
| 2021-08-15 | NOAA-20 | 0 | 0 |
| 2021-08-19 | S-NPP | 94 | 69 |
| 2021-08-19 | NOAA-20 | 221 | 203 |
| 2022-08-04 | S-NPP | Unavailable | Unavailable |
| 2022-08-04 | NOAA-20 | 0 | 0 |
| 2022-08-12 | S-NPP | 6 | 3 |
| 2022-08-12 | NOAA-20 | 13 | 12 |
| 2024-05-31 | S-NPP | Unavailable | Unavailable |
| 2024-05-31 | NOAA-20 | 1 | 1 |
| 2024-06-05 | S-NPP | 0 | 0 |
| 2024-06-05 | NOAA-20 | 0 | 0 |

The stricter screen deliberately excludes some detections using input-quality and residual-bowtie flags; it is a separate diagnostic, not a corrected archive total. Native masks contain all fire classes and do not independently supply the vegetation-type attribution used in the earlier transfer experiment. These results must not be silently substituted into that experiment.

On the recorded-zero control day, S-NPP has only 6,268 nominal clear pixel centres across the screened swaths, and the sole positive common-clear-cell candidate has only 837 cell labels in common. These are sampling counts, not area fractions. Cloud and other excluded classes are substantial. Therefore this verifies zero recorded detections for the sample, not complete no-fire coverage of Sri Lanka, and cannot restore a whole monthly zero.

S-NPP products are absent on the two sampled interruption dates. Later S-NPP science files are readable and have local support on August 12, 2022 and June 5, 2024. This establishes usable products on those later sampled days; it does not demonstrate recovery of the absent outage-date products or date the exact resumption of observations. NOAA-20 records one detection on May 31, 2024 while S-NPP is unavailable; that detection must retain NOAA-20 provenance and is not automatically a replacement S-NPP observation.

Thirteen of 19 granule-time candidates have nonzero common clear-cell support. Three have zero common support and three involve a granule with no regional centres. Candidate rows can share granules and cannot be summed or treated as independent validation units. Even the positive control's daytime comparison differs substantially across sensors (61 versus 172 active cells on coarse common support); timing, viewing geometry, cloud screening and footprint differences still need examination. This difference alone does not establish which sensor is correct or a transferable correction factor.

## Next step: reuse the cache before expanding downloads

Keep the approximately 5 GiB `science_cache` in the existing notebook workspace. Do not repeat the six-day download. The next processing notebook should read those same cached files and:

1. Extract regional native fire-pixel coordinates, confidence, QA flags, residual-bowtie status and viewing/solar geometry, with granule provenance. Reconcile both unfiltered and screened records against the standard archive, including type attribution or an explicit unmatched/ambiguous status. Do not infer vegetation type from the mask alone.
2. Group adjacent granules into orbital passes, retain day/night and time separation, and avoid reusing a pass as several independent samples. Keep absent S-NPP passes unavailable.
3. Refine spatial-support diagnostics beyond sharing a coarse cell label. Retain the difference between clear centres and physical footprint/area coverage. Do not call a pixel-centre count a regional coverage percentage.
4. Use these diagnostics to freeze a broader seasonally balanced, multi-year simulated-gap study, with disjoint fit, calibration and evaluation periods and an explicit spatial/type target. Estimate download volume from metadata before acquiring additional science files; reuse all existing files.
5. Assess replacement errors and interval coverage on that new design before filling gaps. Keep the Terra-to-MODIS-to-VIIRS chain uncertainty test separate; the six-day VIIRS sample cannot validate early history, annual intervals or district allocation.

No historical medians/seasons, early bands, gap-filled records or frontend data were changed. The pilot has established that the standard-data observation workflow works and that this small native detection sample reconciles; the remaining scientific validation is still required.

Machine-readable details: `docs/atlas_observation_evidence_output_review.json`. Reproduce the returned-bundle checks with `python -m pipeline.verify_atlas_observation_evidence`. The verifier also tests rejection of changed/unmanifested files and invalid counts.
