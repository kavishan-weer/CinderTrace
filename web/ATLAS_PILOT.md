> Separate 2023 data verification prototype. It is not the default frontend. The original frontend has been restored; UI integration is deferred while data work continues.

# CinderTrace Atlas — observed-data pilot

The separate prototype explores the checked Sri Lanka 2023 FIRMS mirror extract: **13,366 satellite pixel observations**. It does not load earlier harmonized outputs or their validation scores. Archived prototype documentation is in `LEGACY_OBSERVATORY.md`.

## Run

Use Node.js 22.6 or newer. From the project root:

```sh
.venv/bin/python -m pipeline.import_atlas_pilot
cd web
npm install
npm run dev
```

Open the printed local URL. No Earthdata login or Python query service is needed to browse this pilot. The original `cindertrace_atlas_lk_2023_pilot.zip` must be in the project root for regeneration. Verified browser assets are in `atlas-public/atlas/`; they are included in the Site source. A build requires its manifest and never fabricates data. `npm run build` produces `dist/`; `npm run preview` serves it.

## Explorer

- Pan and zoom a MapLibre map, expand clusters, or inspect a native pixel observation. Satellite colours identify individual points; cluster circles combine observation counts. A geographic overview remains available if WebGL cannot run.
- Brush the inclusive UTC date window with two keyboard-accessible handles; drag the band to move it. The daily histogram keeps full-year context for the selected satellites and uses square-root heights.
- Select Terra, Aqua, Suomi-NPP and NOAA-20 independently. Counts beside checkboxes cover each satellite within the date window, including currently disabled satellites.
- Click any monthly calendar tile to select that month. Counts include only selected dates and satellites; partial months are marked with a dot. A dash is outside the window. Zero means no matching recorded detections.
- Export the exact selected observations as CSV, download the original verified bundle, inspect native confidence/FRP/type, or copy a selection link.

All counts cover the full supplied study polygon; map panning does not change this scope. All published source types and confidence values are retained. Duplicate passes/satellites can observe one fire repeatedly: these are neither unique fire counts nor burned area. Coverage remains unverified, so zero records does not establish physical fire absence. No calibration, gap replacement, confidence harmonization, or historical trend claim is made.

The data and method dialog and downloadable verification receipt explain provenance and limitations. The manifest retains the source URL, extraction run, source object fingerprint and original bundle checksum. ETag is an object fingerprint, not a content checksum.

## Verification

```sh
# From the project root
.venv/bin/python -m unittest discover -s tests -p test_atlas_import.py
# From web/
npm test
npm run build
```

Importer tests reject a wrong bundle hash, changed inner files and unexpected ZIP members. Frontend tests reconcile the actual pilot totals, inclusive dates, sparse months, empty satellite selections, shared links and native-confidence CSV fields. Browser QA covered desktop and 390 px mobile layout, date/satellite controls, a keyboard brush change, native record details, provenance, and the downloaded 6,987-row August 2–31 CSV.

## Basemap

OpenStreetMap tiles load only for the viewed map, with visible attribution and normal browser caching. There is no offline tile download. Follow https://operations.osmfoundation.org/policies/tiles/ when hosting; service availability is best effort. `VITE_ATLAS_TILE_URL` can select another compatible raster provider before building; update attribution in `AtlasMap.tsx` if changing providers. Fonts use Google Fonts. The observations and boundary are served with the app, independent of those external visual services.

The deployment build copies only `atlas-public/`, excluding the previous `public/data/` outputs. `.openai/hosting.json` retains the existing Site identity and static output configuration.
