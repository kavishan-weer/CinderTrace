# Atlas mirror pilot output review — 15 November 2026

Reviewed the saved outputs in `notebooks/CinderTrace_Atlas_Mirror_Pilot.ipynb`. The handoff ZIP has now been supplied and independently verified locally; see `atlas_bundle_verification.json`.

- Run: `20261114T183601Z_07884c3d`.
- Scope: Sri Lanka reference polygon, calendar year 2023, all published categories and confidence values.
- Actual source schema decoded as native `GEOMETRY('OGC:CRS84')` with DuckDB 1.5.6.
- Extracted observations: **13,366**.
- Direct mirror query count: **13,366**.
- Sum of monthly satellite counts: **13,366**.
- Exact duplicate extract rows reported: **0**.
- All extracted rows are marked standard/science-quality (`sp`) by the source.
- Satellite totals: Aqua 642; Terra 198; Suomi-NPP 6,432; NOAA-20 6,094.
- Published type totals: vegetation (`0`) 13,264; other static (`2`) 77; offshore (`3`) 25. These labels must not be silently changed into wildfire identities.
- December observed counts: Aqua 0; Terra 0; Suomi-NPP 3; NOAA-20 4. Preserve satellites and observed-zero semantics rather than assuming absent MODIS detections imply a failed query or an absence of physical fires.
- Saved assertions completed without recorded notebook errors, including unchanged source fingerprint across extraction/count queries.

Expected handoff filename: `cindertrace_atlas_lk_2023_pilot.zip`.

Expected ZIP SHA256 printed by this run:
`11184caea4d9ca669e4f7f455d120d8f4d898db0bf2086f5c86cb9b47650e49e`.

Google Drive location:
`MyDrive/cindertrace_atlas/runs/20261114T183601Z_07884c3d/cindertrace_atlas_lk_2023_pilot.zip`.

Completed: ZIP identity and every inner hash/size verified; native coordinates, polygon membership, confidence, timestamps, duplicates and all monthly/satellite totals checked. The observed map/time-brush/calendar explorer now uses only these rows. Existing harmonized outputs and validation scores are not inputs to this view. Cross-sensor harmonization, cloud/overpass completeness, physical fire counts, and general historical validity are not established by these pilot extraction checks.
