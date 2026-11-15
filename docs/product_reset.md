# CinderTrace Atlas — proposed product reset

Proposed direction, 14 November 2026. The Colab/swath investigation is no longer the active product plan. Existing data and notebooks are retained as prior work. This proposal does not certify previous outputs or change the frontend.

## Product promise

Draw an area. Explore its detected burning activity. Compare seasons using a documented common reference, and inspect the evidence behind that comparison.

The product is a map-first burning calendar. Its distinctive contribution is validated sensor comparability for a selected area. A smooth line through a sensor transition is not evidence of correctness.

## What we already have, and what changes

`pipeline/fetch.py` already reads the portolan-mirrors/firms-catalog GeoParquet files on Source Cooperative. The reset is therefore a fresh, checked extraction and replacement of derived analytics, not a switch to a new detection source. Existing raw extracts are unverified caches; retain them, but rebuild and reconcile against a pinned catalogue snapshot. Old calibration outputs and validation scores are not inputs to the new model.

The mirror supplies detection observations, not complete cloud/overpass accounting or harmonized physical fire counts. It is suitable as the primary detection source. Observation-product investigations remain targeted scientific checks, rather than a mandatory global HDF reconstruction before the explorer can work.

## Experience

### Explore

A large map, an always-visible time brush, search, polygon selection, satellite filters, and shareable area/date links. Aggregate cells at wide zoom; native detections at close zoom. Show source satellite, acquisition time, native confidence, FRP and processing quality on selection. Display the snapshot/update time.

The map represents observed detections. Changing the satellite selection changes the observing fleet; a shared colour scale does not make it harmonized. Counts are detections, not incidents or burned area.

### Calendar

Selecting an area opens its month-by-year calendar, seasonal profile and comparison against eligible history. Raw observations and reference-equivalent activity have distinct labels and units. Retrospective climatology and prior-only comparisons are explicit. Partial current periods compare with matched elapsed periods where supported, or remain provisional.

Use annual starting-year conventions explicitly; NSW can use July–June. A season describes the distribution of detected burning activity, including different burning types, rather than a confirmed wildfire season.

### Sensor check

An explanation panel shows the actual held-out observations and predictions, residuals, empirical interval coverage, evaluation years and sample counts for the selected scope. Users can inspect observed data by satellite, the unadjusted mixture, and the supported common-reference estimate. Transition charts are diagnostics; held-out results establish predictive performance.

### Area brief

Download the exact selected observations, comparable monthly series and a chart/brief with area, time range, units, source snapshot, quality flags and method version. The same selection and definitions drive the browser and every export.

## Data architecture

1. Pin the remote STAC/item metadata, actual schema, publication state and relevant source file fingerprints. Preserve extraction SQL, region geometry/hash, retrieval time and local extract checksums. Detect upstream revisions, especially replacement of NRT by standard products.
2. Use the publisher's A5 aggregate files for fast all-satellite overview queries that their dimensions support. Do not infer sensor-by-date counts by joining marginal aggregate columns; those require point-level data.
3. Query point GeoParquet using explicit year, spatial and date predicates for exact selected-area observations, filters and exports. Cache stable regional extracts and sensor-specific daily summaries. Avoid downloading the whole global archive into Colab.
4. Construct one canonical, versioned observation store; generate all charts and export formats from it. Keep standard and NRT lineage identifiable. Retain native confidence; documented display/filter conventions are not equivalent sensor probabilities.
5. Start with a global observed-data explorer and one benchmark area for harmonization. Expand comparable calendars to the three demonstration regions and user areas only as their evaluation supports it.

The browser can remain largely static; heavier selected-area history queries and calibration use a small DuckDB-backed service or prepared region datasets. Benchmark deployment latency and memory rather than promising that global on-demand scientific analysis will run instantly in a browser.

## Scientific method and release gates

- Define the prediction target as reference-sensor observed hotspot activity, not all physical fires or cloud-corrected burned area.
- Compare individual reference satellites before considering a combined fleet. Use a common spatial/temporal activity representation as an explicit metric, and validate any cross-sensor transfer. A common grid alone does not remove different detection sensitivities.
- Fit simple baselines and seasonal transfer candidates on overlap. Select models inside training folds; score complete outer held-out years. Keep an additional chronological test where the intended use needs it. Assess errors, bias, interval coverage and training-window sensitivity on paired evaluation cohorts.
- Retain Terra-only history as a separately supported transfer stage. Validate the complete chain before attaching uncertainty bands or allowing early-period trend claims.
- NOAA-20/21 stay distinct observations. Replacement is enabled only after reference matching, deduplication and uncertainty tests support it. Reference continuity must use actual source availability rather than a permanent hard-coded S-NPP assumption.
- Build an area's observed history directly from its own points. Calibrate at the same declared spatial scope where there is adequate overlap. Do not force an arbitrary polygon's history out of regional totals through an unsupported spatial allocation. Small/unsupported areas retain observed series with comparable history unavailable.
- A successful, reconciled query yielding no rows means zero recorded detections under those query conditions. It does not establish that no fires occurred. Failed/incomplete extraction, unsupported estimates and unknown coverage remain distinct states. Coverage limitations apply to positive months as well as zero months.
- Keep published thermal-source type and unknown/NRT type separate. Do not infer agricultural, prescribed or wildfire identity from timing or intensity alone. Use consistent category scope across historical and current comparisons.
- Emit the complete expected time/filter grid, retain explicit nulls and quality states, and reject partial sums. No model-generated value silently replaces unavailable observations.
- Validate annual totals/rankings, local intervals and summed-filter intervals separately. Regional marginal interval coverage cannot certify them.

## Implementation order

1. Retire current derived results from the new release path. Freeze definitions and the output schema; create a fresh source snapshot and query fixtures.
2. Build the observed map, time brush and AOI querying from the mirror. Reconcile sample counts against direct point queries and native source records where necessary. Test duplicate handling, NRT replacement and exact exports.
3. Build the observed calendar and source/quality diagnostics from the same store.
4. Implement and independently evaluate common-reference activity for one declared benchmark area. Release unsupported scopes as observed-only rather than silently applying a regional model.
5. Add supported anomaly, season and area-brief views. Run the complete region/filter/polygon/export/mobile journey before release.

Do not add incident counts, spread forecasts, causal burning labels or predictive warnings to the first release without separate validation. The product's strength is the map/calendar interaction and inspectable comparability.

## Sources reviewed

- Challenge brief in `challenge.md`: harmonized MODIS/VIIRS burning calendar, selected areas/date ranges, historical comparisons and downloadable results.
- [FIRMS explorer](https://portolan-mirrors.github.io/firms-catalog/)
- [Catalogue repository and ingestion architecture](https://github.com/portolan-mirrors/firms-catalog)
- [Detection definitions and limitations](https://github.com/portolan-mirrors/firms-catalog/blob/main/catalog/detections/README.md)
- [Query semantics and aggregate cross-tab limitations](https://github.com/portolan-mirrors/firms-catalog/blob/main/catalog/detections/AGENTS.md)

Some descriptive source documents disagree about physical sorting or historical file/schema details. Inspect the pinned current metadata/schema and benchmark the actual query plan before relying on those optimization claims.
