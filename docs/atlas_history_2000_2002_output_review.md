# Earlier-history first batch: executed-output review

Reviewed the saved outputs of `CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb`, run `20261114T211825Z_97d5550a`. No saved execution errors are present. The executed notebook remains unchanged; its SHA256 and the printed ZIP receipts are recorded in `atlas_history_2000_2002_output_review.json`.

| Year | Completed NASA windows | Standard observations reported |
|---|---:|---:|
| 2000 | 13/13 | 4 |
| 2001 | 73/73 | 354 |
| 2002 | 73/73 | 1,577 |
| Total | 159/159 | 1,935 |

The availability snapshot identifies November 1, 2000 as the start of the MODIS standard archive: only 61 dates in 2000 were queried. The four reported records are therefore a November–December extract, not a complete-year fire total. Earlier dates must stay unavailable, not zero. The snapshot also retains the later VIIRS archive starts rather than pretending those satellites contributed to early history.

The notebook completed its per-year parsing, geometry, provenance and aggregation assertions and saved year ZIPs. Its terminal output does **not** display the mirror comparison statuses, detailed daily unavailable states or Aqua transition rows. Those must be inspected in the returned year ZIPs before claiming complete source matches or certifying the temporal treatment independently. A completed run does not prove complete observing coverage.

## Next action

Copy these four files into the project folder from:

`MyDrive/cindertrace_atlas/rebuild/lk_history_2000_2021/20261114T211825Z_97d5550a/`

- `cindertrace_atlas_lk_history_2000_20261114T211825Z_97d5550a.zip`
- `cindertrace_atlas_lk_history_2001_20261114T211825Z_97d5550a.zip`
- `cindertrace_atlas_lk_history_2002_20261114T211825Z_97d5550a.zip`
- `cindertrace_atlas_lk_history_progress_20261114T211825Z_97d5550a.zip`

Their expected hashes are in the machine-readable review. No download rerun or replacement notebook is needed.

Local verification will check each outer hash, all raw response/file receipts, exact source/date intervals, reconstruction of canonical rows, source comparison discrepancies, null versus zero states, July 2002 Aqua support and partial-month totals, complete native filter grids, and the progress receipt inventory. The original 2022–2024 benchmark remains separate.

After this checkpoint passes, process **2003–2005** with the same notebook and run folder: rerun Steps 6 and 7 in the same runtime. After a runtime restart, rerun all cells with `NEW_RUN=False` and re-enter the key privately. Do not delete caches, change the run contract or regenerate over the executed notebook.

The frontend is unchanged. No calibrated history, harmonized comparisons, gap replacements or new scientific validation scores have been produced.
