# Earlier Sri Lanka standard-data rebuild

Notebook: `notebooks/CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb`.

This is a separate observed-data rebuild for **2000–2021**, following the verified standard-product source policy. It does not change the original frontend, old data, executed notebooks, input ZIPs or the 38,995-record 2022–2024 benchmark. It does not fit transfer models, fill satellite gaps, compute calibrated historical medians/seasons or produce scientific validation scores.

## First run

1. Open the notebook in Colab or VS Code and run cells in order. If the DuckDB version check requests a kernel restart after installation, restart and resume from Step 1.
2. Enter your existing FIRMS MAP_KEY only at the hidden prompt. No Earthdata password or input upload is needed. The exact benchmark polygon is embedded and checksum-verified.
3. Keep `NEW_RUN=False`, `BATCH_SIZE=3` and the default output folder.
4. The first batch processes **2000, 2001 and 2002**, saving each year's evidence ZIP immediately.
5. Save the executed notebook and return the three year ZIPs plus the small progress ZIP for independent local verification before continuing.

Colab saves under:

`MyDrive/cindertrace_atlas/rebuild/lk_history_2000_2021/<RUN_ID>/`

VS Code uses:

`atlas_lk_history_2000_2021/<RUN_ID>/`

beneath its working folder. It never calls the browser-only Colab upload function.

The year filenames are:

- `cindertrace_atlas_lk_history_2000_<RUN_ID>.zip`
- `cindertrace_atlas_lk_history_2001_<RUN_ID>.zip`
- `cindertrace_atlas_lk_history_2002_<RUN_ID>.zip`
- `cindertrace_atlas_lk_history_progress_<RUN_ID>.zip`

If Colab/browser blocks several downloads, copy the listed files directly from Drive. Do not delete the run folder or caches.

## Resume and continuation

If interrupted, rerun Step 6 in the same runtime. The active three-year batch is remembered: completed years are verified and the interrupted year's verified windows are reused. No extra year is added to an interrupted batch. Step 7 packages progress and downloads all files in that batch.

After reviewing the first batch, rerun Steps 6 and 7 to process the next three incomplete years. After a runtime restart, run the notebook in order again with `NEW_RUN=False` and re-enter the key. Completed-year manifests and raw cache checksums are verified before reuse. A changed contract or corrupt cache stops rather than silently switching inputs. Set `NEW_RUN=True` only to deliberately start a separate snapshot.

The full 22-year scope is planned from NASA's pinned availability response; only three years are processed per invocation. The already verified availability snapshot would produce **2,555** requests for the full history and **159** for the first batch. These are planning examples: a fresh live run calculates its actual count from NASA metadata. Requests are paced and no more than five days each, following the [NASA area service](https://firms.modaps.eosdis.nasa.gov/api/area/) and [availability service](https://firms.modaps.eosdis.nasa.gov/api/data_availability/). Quota/network failures retain progress and never become zero observations. Wait for quota/service recovery before resuming a failed request.

## Source and availability rules

- NASA standard-product rows are canonical. Every record carries its source stream, raw response SHA256, request interval and zero-based parsed CSV row ordinal.
- Full mirror extracts, their pinned fingerprints/schema/SQL/count receipts, and separate NRT rows remain audit evidence. A mirror mismatch is reported; no NRT row is relabelled, appended to standard, or inserted as a missing-standard fallback.
- Historical scope includes Terra, Aqua, S-NPP and NOAA-20, with availability states for each day. NOAA-21 is not queried for this pre-2022 scope.
- Source min/max dates are read from NASA. Pre-archive dates retain null authoritative counts. A completed valid empty query records zero detections, with observing coverage still unverified.
- The shared MODIS stream does not certify early Aqua dates. July 4, 2002 is recorded as Aqua's reported first-light lower bound, with its [MODAPS source](https://modaps.modaps.eosdis.nasa.gov/services/about/). It is not inferred from the first local hotspot or treated as proof of continuous observations afterward. Unexpected earlier Aqua detections stop for temporal-contract review.
- Daily and native-filter rows before supported platform/archive intervals are unavailable, not zero. A partially supported month has a count on its queried dates and a separate null full-month total.
- Leap days, original polygon support, native confidence domains and published source types remain explicit. Empty filter categories are not certified empty historical reference categories. Model support stays unevaluated.
- Public S-NPP/Terra production tables, FIRMS missing standard dates and FIRMS notices are captured. Unparseable historical notice rows are saved for review. None of these lists is treated as an exhaustive local coverage ledger or used to estimate lost fires.
- Raw annual totals across a changing satellite fleet are not a calibrated trend. Standard processing does not by itself establish physical fire truth or complete observing coverage.

## Evidence in each year ZIP

Each year is independently packaged with its original polygon, run contract and relevant snapshots. Its manifest hashes every included file and records the exact request cohort and source-comparison status.

Included are raw NASA CSV responses and receipts, canonical standard observations, full mirror extract/receipt, NRT audit rows, unreconciled mirror rows with reasons, native source comparisons, daily/monthly support states, all 9,984 standard native-filter combinations, and public outage evidence. Null totals and unsupported periods are preserved. Original per-sensor fields remain native; no confidence probability crosswalk is applied.

The small progress ZIP records completed/remaining years and year-ZIP hashes. It is an index, not a replacement for the year ZIPs. The 2022–2024 benchmark's input hashes and counts are referenced in the run contract; those years are excluded from every download/write target. Their source data are not re-downloaded or re-evaluated by this notebook.

## Verification of the prepared notebook

All **40 data tests pass**. New tests execute the actual generated notebook using explicitly simulated source responses. They interrupt 2001 after a completed 2000 ZIP, resume the same batch, confirm exactly 159 successful unique NASA windows, validate every year-file hash and verify that the private test key appears in no bundled output. Other tests cover a header-only successful empty year, partial 2000 archive support, pre-Aqua periods, partial VIIRS start months, leap day, corrupt completed-year files and unparseable outage evidence.

The historical parser was also checked offline against already verified actual NASA snapshots: 750 historical production intervals and 55 missing standard dates parsed, with no unparseable rows in that particular snapshot. A live run captures fresh evidence and preserves any new unparseable rows.

No live earlier-history retrieval has run during notebook preparation. Final independent source verification awaits the returned year ZIPs. Executed earlier notebooks and the frontend remain unchanged.

Regenerate this new notebook only before it has been executed:

```sh
.venv/bin/python scripts/create_atlas_history_notebook.py
.venv/bin/python -m unittest discover -s tests -p 'test_atlas*.py'
```

Preserve the executed notebook as evidence once a user run is saved; do not regenerate over it.
