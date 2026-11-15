# Sri Lanka multi-year validation notebook

Prepared `notebooks/CinderTrace_Atlas_LK_Multiyear_Validation.ipynb`. It processes the frozen 54-date study in three resumable batches inside one notebook and downloads one combined results ZIP. The original frontend, canonical observations, executed pilot notebooks and original caches are preserved.

## How to run

1. Open the new notebook in Colab using the same Drive account as the pilot.
2. Run **step 1** once to install dependencies. Restart the session, then continue at **step 2**, skipping installation. This avoids the NumPy/SciPy loaded-version mismatch encountered previously.
3. Run **steps 2–5** to check the environment, mount Drive, verify frozen inputs and load the method. No input upload is required. In VS Code, set the storage paths to local folders.
4. Run **step 6** to sign in to Earthdata at the interactive prompts. A browser login alone does not authenticate the Python session. The notebook does not persist login credentials.
5. Run all three batches: **step 7** (2018–2020 fitting dates), **step 8** (2021–2022 calibration dates), and **step 9** (2023–2024 evaluation dates).
6. Run **step 10** to assemble the evidence and perform the prespecified evaluation. It can also report an honest partial run, with unprocessed dates explicitly unavailable.
7. Run **step 11** to download one ZIP. Save notebook outputs and add that ZIP to the project folder.

## Resources and resuming

The linked catalogue contains 632 fire/geolocation files, approximately **45.6 GiB of total downloads**. This is a download-volume estimate, not a requirement to retain 45.6 GiB in Drive. Each new granule's raw files are staged in a dedicated temporary directory, processed and checkpointed, then only those temporary copies are removed. The original pilot cache is read-only to this workflow. Derived clear-centre evidence, native pixel records, receipts and checkpoints remain in the new study workspace. Allow several GiB of additional Drive space and at least a couple of GiB of temporary runtime space; exact use depends on the data and runtime.

Default Colab storage:

- Preserved original cache: `/content/drive/MyDrive/CinderTrace_Observation_Evidence_v1/science_cache`
- New workspace: `/content/drive/MyDrive/CinderTrace_Multiyear_Validation_v1`
- Temporary new raw copies: `/content/cindertrace_multiyear_temporary_raw`

After an interruption, repeat setup and login, then rerun the interrupted batch. On a fresh runtime, install dependencies and restart first. Completed granule/date checkpoints are checked by hashes and reused. The current incomplete granule may need to download again. Input/method changes create a separate run directory rather than mixing incompatible checkpoints.

A provider access denial stops further downloads in that batch and causes later batch cells to skip work. Rerun Earthdata login and the same batch after correcting access. Other failed granules remain unavailable in the output and are retried when rerunning a partial date. Do not delete the derived cache to resume. A partial results ZIP includes failure details for review and never converts those failures into zero activity.

## Scientific design

The sample contains 22 fitting dates, 16 calibration dates and 16 evaluation dates in disjoint calendar years. It was selected by calendar strata and archive availability without ranking fire counts. First-quarter 2018 slots without supported NOAA-20 archive dates remain absent. The two unresolved NOAA-20 dates, April 19 and May 27, 2018, remain explicit unavailable source states when no fire-product catalogue entries exist. Different sensors or product versions are not substituted.

Every native fire pixel is reconciled against the frozen standard archive using unique same-sensor coordinate/time matching. Confidence must agree before vegetation counts are available. Type labels are carried from the archive and are not independently confirmed burning types. Unmatched/ambiguous pixels, archive discrepancies, failed processing and absent nominal-clear support withhold the affected vegetation total.

Two analyses remain separate:

- **Paired-observation diagnostics:** compute clear-centre geometry for every temporal candidate before assigning one-to-one pairs. Pair eligibility uses geometry/support and time, never fire counts. All 30/60/90-minute, 250/500-metre and viewing-angle sensitivities are retained. Nearby centres are not equivalent physical pixel footprints or complete regional coverage.
- **Simulated-outage research:** predict S-NPP-observed screened vegetation H3-resolution-8 active-cell-days from NOAA-20's own screened vegetation active cells and calendar month. S-NPP masks, geometry and reference-conditioned pair selection cannot enter predictor features. NOAA-20 features and reference labels are exported separately. A failed reference swath cannot remove an otherwise valid source predictor.

The global ratio, shrunk seasonal ratio and nonnegative affine candidates are selected using fit-year holdouts only. Calibration dates do not select/refit the point model. Native-source identity and fitting-period seasonal climatology are separate baselines. Exploratory date-level 80/90% intervals need at least twelve supported calibration dates; unsupported intervals remain withheld. Coverage, interval widths and prediction errors are evaluated only where reference labels are available, with source-only prediction availability kept separate.

Earlier aggregate metrics and the pilot have already been inspected. This is not a blind external replication. The outputs do not validate physical fire truth, full observing coverage, actual-outage distribution shifts, monthly/annual uncertainty, Terra-era history, district allocation or all category/confidence combinations. No production values, gap-filled records or frontend changes are enabled automatically, regardless of the scores.

## Verification before delivery

Tests cover held-out label isolation, separation of calibration and point-model fitting, rejection of reference fields in the predictor schema, geometry eligibility before temporal pairing, independence from fire counts in pair selection, explicit unavailable states, reference-only failures, access denials, checkpoint resuming, temporary-file cleanup and preservation of original caches. Synthetic NetCDF files exercise the processing path. The standalone notebook's embedded inputs/methods, partial-run finalization and final ZIP manifests are also checked. The full 54-date science download has not been run locally; it requires the user's authenticated Earthdata session.
