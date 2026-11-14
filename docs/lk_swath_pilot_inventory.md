# Sri Lanka swath/geolocation pilot inventory

Public catalogue checks compare Collection 6.1 fire swaths against independently listed geolocation acquisitions. This is metadata reconciliation, not pixel-level completeness certification.

| Month | Sensor | Fire swaths in bbox | Geolocation swaths in bbox | Matching acquisition times | Geolocation without bbox fire match |
|---|---|---:|---:|---:|---:|
| 2001-01 | Terra | 74 | 74 | 74 | 0 |
| 2001-01 | Aqua | 0 | 0 | 0 | 0 |
| 2002-01 | Terra | 74 | 74 | 74 | 0 |
| 2002-01 | Aqua | 0 | 0 | 0 | 0 |
| 2022-12 | Terra | 77 | 78 | 77 | 1 |
| 2022-12 | Aqua | 76 | 76 | 76 | 0 |
| 2023-12 | Terra | 73 | 73 | 73 | 0 |
| 2023-12 | Aqua | 77 | 77 | 77 | 0 |

January 2001 and January 2002 each have 74 paired Terra acquisition identifiers. Aqua is absent in these pre-Aqua months by design. December 2023 has 73 Terra and 77 Aqua bbox-matched identifiers. Those positive matches do not establish that every relevant pixel was observed or every fire detection reached the local archive.

One December 2022 Terra geolocation acquisition (`2022355.1700`, December 21 at 17:00 UTC) has no counterpart in the regional fire-product bbox result. An exact CMR acquisition query without the spatial filter also returned zero files. However, independent LAADS day listings contain `MOD14.A2022355.1700.061.2022356032056.hdf` (285,635 bytes). This is an archive/catalogue availability discrepancy, not evidence of an unrecoverable observation gap. The listed file has not yet been downloaded or quality checked. See [cross-archive reconciliation](lk_swath_reconciliation.json).

- [Full public catalogue responses, file links and source query hashes](lk_swath_pilot_inventory.json)
- MOD14/MYD14 Collection 061 is paired with MOD03/MYD03 Collection 6.1, not newer Collection 7 geolocation.
- Swath file and quality verification, acquisitions absent from both catalogues, and archive ingestion remain unresolved by this metadata-only check.
