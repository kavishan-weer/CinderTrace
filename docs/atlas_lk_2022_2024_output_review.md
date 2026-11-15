# Executed Sri Lanka 2022/2024 notebook review

Reviewed the saved outputs of `CinderTrace_Atlas_LK_2022_2024_Check.ipynb`, run `20261114T201123Z_30cc8ecb`. The executed notebook is preserved unchanged. Its SHA256 is recorded in `atlas_lk_2022_2024_output_review.json`. This is a saved-output review; the returned data ZIP has not yet been supplied locally.

## Findings

All **515/515 NASA requests** completed, yielding **25,629 standard-product observations** across both years. There are no saved execution errors. The pandas concatenation FutureWarnings did not prevent the comparison or checkpoint export.

| Cohort | Mirror standard observations | NASA standard observations | Result |
|---|---:|---:|---|
| 2022, Terra/Aqua/S-NPP/NOAA-20 | 8,593 | 8,593 | All native records and checked attributes match |
| 2024, Terra/Aqua/S-NPP/NOAA-20 | 11,382 | 11,382 | All native records and checked attributes match |
| 2024, NOAA-21 | 0 | 5,654 | Standard-product source needs reconciliation; mirror retains 5,775 NRT rows separately |

For the matched cohorts, no extra/missing records, duplicate-key concerns or native-attribute differences are reported. The 2024 overall status correctly remains `review_required`.

NASA's availability response advertised complete 2024 standard-product date coverage for NOAA-21 in this run, so the notebook queried all 366 days. This is measured metadata from the run, superseding examples based on a later January start or absent standard stream. Advertised archive coverage is not complete satellite/cloud/overpass coverage.

The 2024 mirror total of **17,157** comprises **11,382 standard** records from the four established satellites and **5,775 NOAA-21 NRT** records. NASA returned **17,036 standard** records across all five satellites. The two totals are different processing-quality cohorts. Do not interpret the difference of 121 as a list of removed false detections, or label all 5,654 standard NOAA-21 records physically absent from the mirror's observation history. Native row correspondence and processing changes still need inspection.

The diagnostic cell completed its assertions for 3,290 daily rows, 108 monthly rows, 20,112 native standard-confidence combinations and leap day. It reported 122 global production intervals and 63 listed missing standard dates from the captured sources, with no listed-missing-date/positive-standard-record conflicts in the local diagnostic. These are source evidence, not exhaustive local coverage verification. “All raw/derived counts reconcile” describes internal aggregation consistency; it does not override the NOAA-21 source mismatch.

## Next gate

Copy this generated ZIP into the project folder:

`cindertrace_atlas_lk_2022_2024_20261114T201123Z_30cc8ecb.zip`

Saved Drive location:

`MyDrive/cindertrace_atlas/verification/lk_2022_2024/`

Expected SHA256 printed by the executed notebook:

`6203a50c88921de8c29757192fbcbd9ee2af3ee06bd7f923e5dcf50cc34deea5`

No new download or notebook rerun is needed. That bundle already contains the mirror extracts, NASA raw responses/receipts, availability snapshots and discrepancies required for the next investigation.

After receipt:

1. Independently verify the ZIP's outer hash, every manifested file hash, all 515 requested intervals, geometry identity, native fields and recomputed comparisons. Confirm the NOAA-21 quality labels and source versions directly from the raw files.
2. Compare NOAA-21 NRT with its authoritative standard products by month, native record identities, coordinates and attributes. Describe unmatched records and revisions without assuming one-to-one correspondence or equating net count changes with deleted fires.
3. Prepare a versioned canonical observed-data checkpoint. Subject to verification, use the NASA standard stream for 2024 NOAA-21 and the matching standard streams for the other platforms. Retain the original NRT stream in the audit archive; do not stack it with standard rows or relabel it as standard.
4. Recompute the affected native category/confidence/day-night/monthly grids from that chosen quality stream. Then decide the extraction and source-precedence contract for historical expansion.

No calibration, NOAA-20 satellite replacement, historical medians/seasons or uncertainty bands should be enabled by these source matches alone. Observing coverage remains unverified. The original frontend is unchanged.

## Returned ZIP verification completed

The ZIP was subsequently supplied and independently verified. The saved-output-only review above is retained as an audit trail. See `atlas_lk_2022_2024_verification.json` and `atlas_canonical_benchmark.md` for the recomputed results, NOAA-21 quality-stream comparison and isolated standard-product benchmark. No frontend integration was made.
