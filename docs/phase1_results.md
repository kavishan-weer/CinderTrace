# Phase 1 results (harmonization v2: categorize, don't drop)

Every detection is kept and tagged; the web app filters by category.

| Tag | Values | Rule |
|---|---|---|
| `cat` | veg, volcano, static, offshore | Per 0.05° cell, so categories are disjoint and additive. Static = at least 10 labelled type-2 rows, at least 50% of the cell's labelled rows, in at least 3 years. Volcano = at least 3 type-1 rows, at least 50%. Cells with only NRT rows default to veg. NRT rows inherit their cell's category, which fills the catalog's missing `type` in recent data. |
| `conf` | 1 low, 2 nominal, 3 high | VIIRS l/n/h as published. MODIS 0-29 / 30-79 / 80-100 (FIRMS display convention; no official crosswalk exists). A cell-day takes the max confidence per sensor family. |
| `fam` | modis, terra, snpp, n20, n21 | modis = Terra+Aqua, deduplicated per cell-day |

Harmonization is fitted separately per region x cat x conf slice (fit on the 2012+ overlap, validated leave-one-year-out, monthly). Slices with too little overlap data fall back to a naive ratio and are flagged `low_data`.

## Validation, default filter (vegetation fires)

WAPE = weighted absolute percentage error (lower is better).

| Region | Conf | Naive ratio | Best model |
|---|---|---|---|
| Sri Lanka | low | 0.794 | 0.569 |
| Sri Lanka | nominal | 0.246 | 0.181 |
| Sri Lanka | high | 0.455 | 0.404 |
| California | low | 0.893 | 0.244 |
| California | nominal | 0.168 | 0.133 |
| California | high | 0.142 | 0.132 |
| NSW | low | 0.778 | 0.386 |
| NSW | nominal | 0.170 | 0.113 |
| NSW | high | 0.179 | 0.142 |

Low-confidence detections are the hardest to harmonize, which is why the app defaults to nominal and high.

## Seam test (2012 / 2011 annual activity)

| Region | Raw merged | Harmonized (veg, nominal+high) | Harmonized (all data) |
|---|---|---|---|
| Sri Lanka | 7.86x | 1.09x | 1.11x |
| California | 3.89x | 1.22x | 1.06x |
| NSW | 2.24x | 0.68x (MODIS-only 0.69x, so real) | 0.70x |

## Outputs (`data/harmonized/`)
- `<region>_cells.parquet`: cx, cy, lon, lat, month, fam, cat, conf, cell_days, detections, frp (for the map and filters)
- `<region>_monthly.parquet`: month, cat, conf, modis_raw, viirs_snpp_raw, harmonized, lo, hi, source, model, low_data
- `<region>_report.json`: per-slice validation and seam tests

Reproduce: `python -m pipeline.fetch` then `python -m pipeline.harmonize`.

Known limits: monthly-level validation only; Terra/Aqua orbit drift not modelled; static/volcano/offshore slices have little overlap data; 0.05° grid to be replaced by H3. Regions are clipped to real boundaries (geoBoundaries); a grid cell is kept if its centre is within ~3 km of the outline, and each cell is tagged with its district/county/LGA (`sub`).
