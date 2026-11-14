# EMBERLINE Observatory

React + TypeScript + Vite, MapLibre with CARTO Dark Matter, deck.gl H3 columns,
Three.js contour art, and GSAP entrance animation. Honors reduced-motion settings.

## Run

Use Node.js 22.6 or newer (tested with 22.16).

From the repository root, with the existing generated pipeline datasets available:

```sh
.venv/bin/python -m pipeline.export_web
cd web
npm install
npm run dev
```

The dev command starts both the web app and its loopback-only Python area/download service. No source or fire data is uploaded.

Open the printed local URL. Use **Map settings → CARTO Basemaps key** to connect your
Basemaps key for the browser session. Alternatively copy `.env.example` to
`.env.local` and populate `VITE_CARTO_BASEMAP_KEY`. This is a browser-visible key:
restrict it to approved origins. Never use a private CARTO platform token here.
Without a key the app renders the local boundary and real H3 fire layer on a dark
background; it does not make unauthenticated CARTO requests.

`npm run build` creates `dist/`; `npm run preview` serves that build with the same local area/download service. A standalone static host will need an equivalent query service for custom areas and raw downloads; no hosting is configured by this change.
`npm test` checks missing values, filter aggregation, and historical comparisons.
Web datasets are generated and ignored by Git. Regenerate them before building on
a new machine; the build intentionally does not fabricate sample data.

## First app slice

- Whole-region side-by-side comparison for Sri Lanka, California and NSW: harmonized activity per 1,000 km² of actual H3 grid area, common selected month/filters, explicit missing/provisional states and a comparison CSV. See [comparison method](../docs/region_comparison.md).

- Three regions and all administrative selections, preserving no-grid-coverage states.
- Polygon drawing with undo/finish/cancel, click-first-point closure, Enter/Escape/Backspace map shortcuts, plus latitude/longitude with a configurable 0.5–250 km radius.
- Region-calibrated custom-area history and exact-coordinate polygon raw downloads.
- Original hotspot CSV export, streamed from a temporary local file, and high-resolution calendar/Seam Test PNGs with area/filter/date/provenance labels.
- Category and confidence filters shared by calendar, selected-month statistics, map and Seam Test.
- Observed H3 map with pan/zoom, fit-region, height view, hover values and CARTO connection settings.
- Month selection and history year window; calendar activity/anomaly/percentile modes.
- NSW July–June fire year, with the label identifying the starting year.
- Annual Raw versus Harmonized Seam Test, incomplete-year flags, and regional held-out validation error.
- Harmonized monthly CSV export, method dialog, loading, retry and empty-filter feedback.
- Fire-season onset/peak/end, inclusive duration in months, interactive season
  history and monthly-share/cumulative profile. NSW seasons use July–June.
- Robust timing trends (months per decade) with VIIRS-era/full-record controls,
  complete-year rules, tied-peak/boundary safeguards and a season CSV.
- Local one-page Situation Brief PDF: selected-month comparison, calculated
  findings, compact burning calendar, latest complete season and uncertainty.
- Experimental Events map: single-satellite candidate markers, paged accessible
  list, full observation timelines, observed duration, peak individual-detection
  fire power, daily sampled footprints and agency-review cautions.

The map deliberately labels **observed** sensor activity, rather than presenting
uncalibrated cell counts as local harmonized estimates. Area calendars and CSVs use
the pipeline’s region-calibrated allocation. Inference/uncertainty limits remain in
the method dialog. The archive snapshot is not described as a live warning service.

This slice uses compact precomputed JSON instead of loading DuckDB-WASM and the raw
archive on first paint. Region-year map files load on demand. Event clustering is available through the experimental Events map. Outlook research runs separately and is not integrated into the app. Custom-area requests read the local Parquet archive through the local query service; raw point data is not bundled into the web’s static assets.
The time window applies to the calendar, annual chart and CSV; the map has its own
explicit month selection.

## Verification

Production TypeScript/Vite build, frontend tests, and Python pipeline/export tests passed. Browser
checks covered actual H3 rendering, region/category changes, an administrative
selection, the Raw/Harmonized toggle, CARTO settings, method notes, missing-month
comparisons, and a 390-pixel mobile viewport. The CARTO basemap itself awaits your
key. The map uses deck.gl PolygonLayer over H3 cell boundaries, avoiding unused
3D-tile decoders. A captured local preview is saved as `preview.jpg`.

The app is currently local. External source/data upload requires authorization;
no hosted version has been uploaded or deployed.

## Select an area and download

- **Draw area:** click vertices on the map, then click the first vertex or **Finish polygon**. Use **Undo point** to correct a boundary. Self-intersections are rejected. The map and all monthly charts update after the local query finishes.
- **Lat / lon:** enter coordinates and radius. The boundary uses 64 geodesic segments. The area is restricted to the selected regional archive; a wholly outside selection gets a clear error. Areas with no H3 centres show unavailable charts but can still export raw points.
- **Monthly CSV:** exports the harmonized series for the current category/confidence filters and history year window.
- **Raw hotspot CSV:** exports original rows across all five satellites for that same window, not just the selected map month. Polygon/circle exports clip exact coordinates. Regional/admin exports use existing H3 membership. Original columns remain intact, with added H3, category, display confidence, cell-day confidence and selection-method fields. Confidence selection uses the full sensor-family cell-day maximum, matching the aggregate convention; individual rows can therefore retain a lower original confidence.
- **Calendar PNG / Seam Test PNG:** exports the current chart metric/view with legends, selected area, filter/date labels, archive date and limitations. Calendar PNG includes every year in the window, including rows outside the scroll viewport. Missing/provisional states are preserved. Ready links allow a second download when a browser blocks an automatic download; image links last ten minutes.

Raw points and H3 chart counts are different units and different spatial selections: do not interpret a CSV row as a harmonized cell-day or a distinct fire event. Local calibration remains unvalidated at individual AOI scale.

Temporary raw CSVs expire after ten minutes and are periodically removed. They are stored in a private temporary directory and cleared at normal service shutdown. Downloads stream to disk rather than into a large browser Blob. The service binds only to 127.0.0.1, rejects foreign browser origins, and serves only generated-token exports. Restart the local app after regenerating the Parquet datasets to clear its in-memory cache.

## Fire-season insights

The new panel follows the burning calendar. Select a year or a timeline row to
inspect onset (10% cumulative activity), peak month(s), end (90%) and inclusive
duration in months. All 12 months must be eligible; missing/provisional years and
zero-activity years have no timing estimates. Low-data seasons are shown but
excluded from trends. The history window controls starting fire years for NSW,
so the final January–June can fall in the following calendar year.

Trends default to seasons starting in 2013 or later within that window. Full-record
trends also include calibrated MODIS history. Median pairwise slopes require at
least 10 seasons spanning 10 years. Peak trends exclude ties and suppress wide
month spans where linear timing can cross the year boundary. Month resolution is
explicit; no daily dates, significance claims or continuous-burning duration are
inferred. See `../docs/season_insights.md` for the full method and limitations.

## Situation Brief PDF

Use the **Situation Brief PDF** button above the calendar. The one-page report
uses the current selected area, month, filters and history window. It includes
the latest up to eight chart years and the latest complete active season in that
window, plus data-derived findings and separate uncertainty notes. Its historical
month comparison uses all eligible prior matching months, as the app does.

PDFs are rendered by the local Python service; install the updated repository
`requirements.txt` and restart `npm run dev` after updating. There is no external
upload. Temporary report links last ten minutes. See `../docs/situation_brief.md`.

## Events map

Choose **Event candidates** above the map, then select a marker or a candidate in
the list below. The selected map month and area require actual member detections;
details use the candidate's full regional history. Switch reference satellites
without combining their counts. Single detections are optional and labelled weak.

Events use fixed vegetation / individual nominal+high / 2 km / 48 h catalogues,
independently of the activity-chart filters. An observation-date selector updates
the sampled H3 footprint. The view labels clusters as experimental, explains the
duration/FRP/footprint limits and exposes available agency-reference associations
and fragmentation cautions. See `../docs/events_view.md` for the complete contract.
The existing offline catalogue files are required; restart the local app after
updating the Python query service or rebuilding data. No event data is uploaded.

## Outlook research (outside the app)

The separate local pipeline uses NASA POWER weather and NOAA ONI/DMI climate
history to produce three monthly research outlooks. Expanding-window historical
tests compare a seasonal baseline, fire-history ML and weather/climate ML on
identical origins, with explicit availability lags and missing-data rules.

The initial 2019–2025 benchmark does not pass the combined skill gate for any
region/lead. No outlook panel or forecast endpoint has been added. See
[method, results and reproduction commands](../docs/fire_outlook.md) before using
the outputs; they are revised-archive hindcasts, not validated operational warnings.

A subsequent frozen probability-calibration experiment tests the previously
unscored January–September 2026 period. Calibration helps Sri Lanka/NSW compared
with raw ML, worsens California, and still loses to seasonal history in seven of
nine region/lead comparisons. See [calibration and fresh holdout results](../docs/outlook_calibration.md).
The outlook remains outside the app.
