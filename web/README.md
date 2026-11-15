# CinderTrace Observatory

A static observed-data explorer and attributed published fire-history reference for Sri Lanka, California and New South Wales. The original CinderTrace visual theme is retained. No user-run Colab processing, Earthdata authentication or API key is needed to use this release.

## Published app

https://cindertrace-fire-observatory.haleoak66.chatgpt.site — owner-private publication. Sign in with the owning ChatGPT account when prompted.

## Open locally

From `web/`, run `npm run dev` and open the printed URL. `npm run build` creates `dist/`; `npm run preview` serves the production build. Node 22.6+ is required. No Python query service is used by the active frontend. The finished `dist/` directory can be hosted as a static site. Keep the `.json.gz` files intact; the browser detects and decompresses them, whether the host supplies a gzip content-encoding header or not.

## Data included

The versioned native snapshot has **5,072,279 pixel observations**, 2000–2026, loaded one year/region at a time:

| Region | Native observations | Last recorded detection |
| --- | ---: | --- |
| Sri Lanka | 207,310 | 2026-11-04 |
| California | 2,168,313 | 2026-11-12 |
| New South Wales | 2,696,656 | 2026-11-12 |

These dates describe the snapshot's records, not evidence of complete observing coverage. The archive begins November 2000; individual sensors begin later. Sri Lanka 2000–2024 uses the official-source-reconciled standard-data checkpoint (171,244 observations). Later Sri Lanka and California/NSW use local Portolan FIRMS mirror snapshots, clipped to reference region polygons. Missing category/type values remain explicitly unattributed. Standard and NRT records remain distinguishable. Exact duplicate source records are removed; observations from different satellites remain separate.

The map, brush, sidebar calendar, record inspector and **Observed CSV** use one selection: region, year, inclusive UTC date window, satellite, published type, native confidence, quality and administrative/custom area. Administrative selections use point-centre membership, not estimated allocation. Unassigned/coastal points remain selectable. Custom polygons and coordinate-radius areas intersect the selected regional archive. Dense maps group observations into H3 resolution-6 cells for display only; the colour scale saturates at 1,000 observations per cell. CSV exports preserve individual records and source fingerprints. The optional place-label layer uses OpenStreetMap; the local boundary/observations work without it.

The observed count is **not unique fires, burned area, normalized activity or proof of observing completeness**. Zero means no matching records in the extract. Unsupported sensor periods and loading failures remain unavailable. MODIS and VIIRS changes affect observed counts. FRP means and nighttime shares require selecting a single satellite.

## Published historical reference

Ready-made **Fire Harmony v1.0** monthly data is pinned to Hugging Face revision `9c1c703472d727d9f9b42477df39440bb34b2b64`. The activity field is a third-party derived estimate on the publisher's NOAA-20 scale, including months whose inputs are observed VIIRS. It is not an CinderTrace model or independently validated uncertainty estimate.

This section includes a historical calendar (activity/anomaly/percentile), seasonal median/IQR/P10–P90 envelope and year overlay, complete-year totals, peak activity month, top-three-month share, historical extremes, available administrative rankings, and sensor-history context. NSW supports January–December or July–June starting years. Annual summaries require all twelve non-null provider values. Incomplete periods are excluded.

Provider scope is fixed: its vegetation/confidence selection and coarse H3 allocation **do not inherit the native observation filters or arbitrary polygons**. Sri Lanka has 25 published administrative units. California county and NSW LGA modelled values are not supplied; no values are invented. Coarse provider support does not justify exact-boundary density rankings.

Anomaly and percentile baselines use matching months from 2001–2025, excluding the selected year, with at least five reference values. Zero-median anomalies remain unavailable. Anomaly colours centre at 1× median and saturate at ≤0.25× / ≥4×. Browser and PNG use the same colour function. Seasonal envelopes describe historical variability of provider estimates, not prediction confidence. Peak monthly activity is not a confirmed wildfire-season peak. No automatic significance or causal burning-type claims are made.

## Downloads

- **Observed CSV:** exact selected point records with acquisition UTC, satellite, native confidence, type, quality, FRP, record IDs and source-file SHA256.
- **Historical CSV:** selected provider area's complete November 2000–November 2026 month index, retaining published zeros, missing rows and unavailable observations as distinct states, with provenance.
- **Calendar PNG:** currently chosen provider area, year range, calendar basis and metric, with baseline/scale labels.
- **Area brief PDF:** observed selection and filters, followed by a separately labelled whole-region provider reference; unavailable values stay unavailable.
- **Manifest:** downloadable under Data & method, containing source revisions and 90 dataset-file fingerprints.

## Sources and credit

NASA FIRMS observations via [Portolan's FIRMS catalogue](https://github.com/portolan-mirrors/firms-catalog); Portolan publishes the data as CC0. Boundaries are the supplied geoBoundaries reference files.

Fire Harmony data: **Kopi and Cosmos — Saw Yong Quan and Yap Yong Son**, **CC BY 4.0**. [Method/code](https://github.com/Warren-530/fire-harmony), [pinned dataset](https://huggingface.co/datasets/warrensaw530/fire-harmony/tree/9c1c703472d727d9f9b42477df39440bb34b2b64/v1.0). Underlying observations: NASA FIRMS. CinderTrace extracts three regions, aggregates descriptions and presents the data; it does not change or impute provider activity values. The source code's Apache license and the dataset's CC BY license are distinct.

## Reproduce and verify

Existing generated inputs are included locally; the browser requires only `site-public/ready/`. To regenerate static files from the existing downloaded/checkpoint inputs, run `.venv/bin/python -m pipeline.export_ready_site` from the repository root, then `npm run build` in `web/`. The exporter checks downloaded provider and canonical input hashes before preparing files. `npm test` includes actual 2023 dataset counts and selection/export consistency, missing-data semantics, annual completeness, baseline and PDF checks. The data receipt is `../docs/ready_site_data_receipt.json`.

## Research status

Earlier calibration components and notebooks are retained as research references and are not imported by the active app. The old `/data/` archive and local `/api/` routes are excluded from this production build. Previous validation scores remain results of the earlier dataset. This release does **not** resolve or claim completion of independent observation-coverage, satellite-outage, replacement-model or allocation-uncertainty validation. It avoids relying on that unfinished calibration by using native observations and explicitly attributed published reference estimates.

### Mapbox observation atlas

Set `VITE_MAPBOX_ACCESS_TOKEN` in `.env.local` before starting or building the app (see `.env.example`). The token is a public browser token. The observed explorer uses a recoloured Mapbox Dark basemap; Mapbox attribution stays visible. Detection records remain in the local archive.

The optional 3D view uses one Three.js mesh in Mapbox's WebGL context. Hexagon height is a logarithmic display of recorded observation count, capped at 1,000 observations, and does not represent physical fire height or intensity. GSAP animates the camera and column reveal, respects reduced motion, and stops rendering animations when they finish. Both flat and raised hexagons support record inspection. Drawing automatically returns to a flat view for precise point placement.

## Interactive investigations and visual reports

The extended experience retains the sage, forest and ember palette. Three.js powers a pointer-responsive terrain illustration and the map's raised observation hexagons. GSAP handles entrance motion, the reading-progress line, map camera transitions and a bounded orbit; reduced-motion preferences disable decorative movement. The terrain stops rendering outside the viewport or in a hidden document.

- Three guided investigations set a region/date and keep a sticky chapter guide available.
- Monthly playback follows supported archive dates, has three speeds, and pauses when the date window is manually changed.
- Compare years shows two native geographic patterns and a shared-scale published-history chart. Maps use all published native records for each selected period; they do not inherit explorer filters. NSW supports July–June across both input files. Missing values break the chart and invalidate annual totals.
- Emphasized roads/parks are optional geographic context. A separate NASA GIBS dated-imagery workspace supports Terra/Aqua daily mosaics, an accessible swipe divider, selected-record overlays and branded PNG export. Six actual example frames are bundled; live dates require NASA connectivity. Date gaps, no-data responses and request failures remain explicit.
- Explain selection uses deterministic calculations, including an inspectable peak UTC date, rather than a language model inventing estimates.
- Field notes and saved selections live in browser storage. Evidence packs export notes, selection metadata, selected CSV, a full-year daily SVG, the detailed visual PDF, validation receipt, current context snapshot, proximity receipt and any loaded imagery with exact source requests.
- PDF generation is dynamically loaded. The one-page brief contains a vector map, daily bars, metrics and findings. The detailed report adds a separately attributed historical calendar, loaded source imagery, geographic-context summaries, independent-case charts and complete notes/provenance; long notes continue onto branded pages.
- Production builds include an offline app shell. Up to four visited native archives and visited reference/boundary files are cached locally; unvisited data and external basemap tiles require connectivity. Saved investigations do not guarantee their underlying archives remain in the bounded cache.

Run `npm test` and `npm run build`. `node --experimental-strip-types scripts/check-visual-report.mts` generates real-data layout fixtures in the repository's `tmp/pdfs/` and a review report under `output/pdf/`; render these with Poppler for visual checks.

## Context layers and validation lab

Health facilities, response facilities, major settlements and protected areas are included for all three regions. Sources and licences differ: Sri Lanka OSM hospitals/fire stations and NSDI protected areas; California CDPH, CAL FIRE and NPS; NSW Health, Fire and Rescue NSW and NPWS; Natural Earth major places. Each layer declares its bounded coverage. Inventories are contemporary snapshots, not historical exposure inventories. Site-centre proximity uses great-circle distance, counts sites once and does not establish damage. Protected polygons are clipped/simplified only for display, with repair/exclusion counts retained.

The validation lab separates exact source reconciliation (171,244 Sri Lanka standard-data records, 2000–2024; zero missing/extra on nine native fields) from a geographic reference case against the official CAL FIRE Creek Fire final perimeter. That case measures concordance, not detection accuracy, observing completeness, harmonization quality or forecast performance. The NOAA-21 NRT/standard discrepancy remains visible.

Generated context and imagery are in `site-public/context/`; validation is in `site-public/validation/`. `scripts/export_verified_context.py` in the parent repository builds from local checksummed raw captures; `scripts/export_imagery_presets.py` retrieves the bundled NASA frames. `scripts/export_validation_showcase.py` rebuilds the benchmark from the local checkpoint and official reference capture. Exact source queries, hashes, dates and limitations are included in the generated receipts. Tests validate real snapshots, source reconciliation, imagery dates/requests, proximity calculations and receipt integrity.
