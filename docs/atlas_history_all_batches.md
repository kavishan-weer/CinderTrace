# All history batches, one download

Use `notebooks/CinderTrace_Atlas_LK_History_2000_2021_All_Batches.ipynb`.

This continuation replaces the earlier manual handoff after each batch. It contains eight separate processing cells for 2000–2002, 2003–2005, 2006–2008, 2009–2011, 2012–2014, 2015–2017, 2018–2020 and 2021. Run the notebook in order or use **Runtime → Run all**. The last cell downloads one combined evidence ZIP. No folder download is needed.

## Reuse existing work

Leave `NEW_RUN=False` and retain the same Drive folder and active run. The setup/data code is copied unchanged from the executed history notebook, including the pinned run contract. Existing 2000–2002 year manifests, file hashes and ZIP hashes are checked and reused without new data requests. The original executed notebook is preserved as evidence.

Completed years in any later cell are also reused. If a request fails, completed years stay saved. Resume the failed batch cell in the same runtime; after a restart, run setup/helper cells again and re-enter the MAP_KEY privately. Do not delete caches or change the run contract. There are no automatic downloads or approval pauses between batch cells.

## One download function

The notebook defines:

```python
download_history_bundle(require_all=True, download=True)
```

The final cell calls it once. It verifies every completed-year file inventory and saved year-ZIP hash before creating an outer ZIP containing:

- All 22 year evidence ZIPs, with their native raw responses and receipts intact.
- A progress index and manifest with completed/remaining years and hashes of every outer member.
- The run contract, original geometry, request plan and shared source/outage snapshots.

Existing compressed ZIPs are stored rather than repeatedly compressed. Only selected evidence files are included; the entire Drive folder, notebook, unrelated files and incomplete-year caches are not bundled. The original availability, source-quality and missing-versus-zero rules remain unchanged.

The default refuses to label an incomplete history as complete. To download just the already completed work now, run setup/helpers through the **Batch and single-download functions** cells, then execute:

```python
download_history_bundle(require_all=False);
```

That creates and downloads one clearly labelled partial ZIP, with remaining years explicit. It does not process another year. In VS Code the function displays a file link instead of calling Colab's browser download.

When the full run finishes, save the executed continuation notebook and return its **single combined ZIP** for independent verification. A complete capture is not certification of complete satellite observing coverage or cross-sensor comparability.

## Checks

Tests execute the actual eight generated batch cells with simulated completed-year evidence. They confirm that cached 2000–2002 are skipped, only 2003–2021 are processed, 22 year ZIPs enter the final archive, and exactly one Colab download call is made. They also test partial capture, incomplete-history rejection, tampered ZIP rejection, all outer file hashes, exclusion of unrelated files and byte-for-byte preservation of the original data-code prefix.

The frontend, verified benchmark and executed original notebook remain unchanged. Packaging does not redownload data, mix NRT with standard products or calculate new scientific metrics.
