# Sri Lanka 2022/2024 checkpoint handoff

## 2023 evidence is now independently verified

The returned `cindertrace_atlas_lk_2023_official_check.zip` matches the executed notebook's SHA256: `509afdf0418a01b248671addb4d7a221a02e0e5e275fb203aa6e170206d29077`.

Local verification checked the exact 444-member archive, all 219 response hashes and byte sizes, their saved request receipts, and complete nonoverlapping UTC intervals. Every response was re-parsed and clipped to the original polygon. All 21 saved official fields were reconstructed from raw responses. The native comparison again found 13,366 matching observations, no missing/extra records or checked attribute differences, and 48 matching monthly totals. Saved discrepancy tables are empty. See `atlas_2023_official_verification.json`.

This closes the returned-bundle verification gate. The preceding `atlas_2023_official_output_review.json` records the earlier notebook-output-only review, before the ZIP arrived; it remains historical evidence. Neither result certifies cloud/overpass completeness or sensor comparability.

Reproduce the local ZIP check from the project root:

```sh
.venv/bin/python -m pipeline.verify_atlas_official
```

## Run the next notebook

Open `notebooks/CinderTrace_Atlas_LK_2022_2024_Check.ipynb` in Colab or VS Code and run cells in order. Use your existing FIRMS MAP_KEY only at the hidden prompt. No Earthdata password or additional boundary upload is needed.

The notebook uses a dedicated run folder, outside the 2023 evidence. Colab saves under `MyDrive/cindertrace_atlas/verification/lk_2022_2024/`. VS Code uses `atlas_lk_2022_2024/` beneath the notebook's working folder. Keep the folder and leave `NEW_RUN=False` to resume. If the DuckDB version check asks for a kernel restart after installation, restart and resume from Step 1.

1. Verify the embedded original polygon and setup.
2. Enter the private MAP_KEY.
3. Retrieve NASA's advertised archive dates and public outage snapshots.
4. Extract and reconcile the two mirror years with pinned source fingerprints, schema, SQL, parameters and count receipts.
5. Retrieve NASA standard-product observations in windows of at most five days; verified raw bytes are cached and re-parsed on resume.
6. Compare native observations and attributes on exactly the supported dates. Preserve unmatched records, NRT rows and unsupported dates as review items.
7. Generate daily/monthly/native standard-confidence grids and outage controls.
8. Save the executed notebook and download the final `cindertrace_atlas_lk_2022_2024_<RUN_ID>.zip`. Add that ZIP to the project for independent verification.

Expect roughly 500 requests across both years, with the exact number computed from NASA availability. For example, a NOAA-21 standard archive starting January 17, 2024 yields 511 total requests; an unadvertised NOAA-21 standard stream yields 441, with its rows explicitly left unreconciled. These are planning examples, not claims about the live service's current availability. The notebook follows NASA's documented [date availability service](https://firms.modaps.eosdis.nasa.gov/api/data_availability/) and [five-day area-query limit](https://firms.modaps.eosdis.nasa.gov/api/area/).

## Decisions made explicit

- **2022:** Terra, Aqua, S-NPP and NOAA-20. NOAA-21 is outside the declared platform scope.
- **2024:** the same four plus NOAA-21. Archive dates are read from NASA; no historical start date is guessed or extrapolated from a different service.
- **Standard versus NRT:** the complete mirror extraction retains both. Only `sp` rows within advertised standard-product intervals enter the source comparison. All NRT and unsupported standard rows are exported separately with reasons. They are never silently dropped or labelled source-validated.
- **Zeros:** a completed, valid query may yield zero recorded detections. Dates outside advertised ranges have null authoritative counts. A partly queried month's full-month authoritative total also remains null; its observed overlap total is separate.
- **Outages:** capture the S-NPP/Terra production tables, FIRMS missing standard dates and original FIRMS notices. Global evidence flags do not quantify lost local detections or establish exact recovery times. Unknown coverage remains explicit on positive and zero dates alike.
- **Calendar:** 365 days in 2022; 366 in 2024. The daily grid has 3,290 rows, monthly grid 108 rows and native standard-confidence grid 20,112 rows across the declared platform scopes.
- **Confidence/type:** native MODIS integers and VIIRS classes remain separate. Published types stay unchanged and do not become confirmed wildfire identities.
- **Comparisons:** match multiplicities at five decimal degrees and check native attributes at the declared formatting tolerance. Preserve discrepancies rather than automatically replacing source records.
- **Release:** no frontend edits, calibration, historical medians/seasons, gap replacement, production exports or uncertainty bands are enabled.

## Verification of the new notebook

Twenty-five data tests pass. They include the real 2023 ZIP, tampered-response rejection, leap-day coverage, missing availability, NOAA-20/21 code provenance, and full execution of the actual generated notebook using clearly simulated data. Two offline scenarios exercise partial NOAA-21 availability and an absent NOAA-21 standard source. Both resume without additional simulated API calls, preserve NRT/unsupported rows, and verify every generated bundle hash and credential exclusion. This is execution testing, not a live 2022/2024 scientific result.

The new evidence parser was also checked against the already saved actual NASA pages: it parses 122 production intervals and 63 missing standard-date entries across 2022/2024. Fresh snapshots in the live run may differ and will be retained with new receipts. Those lists are not asserted exhaustive.

Regenerate the standalone notebook after changing its tested helpers:

```sh
.venv/bin/python scripts/create_atlas_two_year_notebook.py
.venv/bin/python -m unittest discover -s tests -p 'test_atlas*.py'
```

The executed 2023 notebook and both original ZIPs have not been edited.
