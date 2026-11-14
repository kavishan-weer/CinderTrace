# Coverage and selected-area analytics

## Rebuild and use

Run `python -m pipeline.harmonize`, followed by `python -m pipeline.validate`.
Validation also writes `<region>_sub_monthly.parquet` for every administrative area.
The boundary source files and regional raw files must already exist locally.

`python -m pipeline.fetch` now refreshes existing current-year files; earlier years
remain resumable. Use `--years 2025-2026 --refresh` to explicitly refresh earlier
snapshots as well. Fetch uses temporary files before replacing a successful snapshot.
Refresh does not run automatically during harmonization.

For an area, call `pipeline.analytics.selected_monthly(cells, monthly, members, sub=ID)`,
`polygon=GEOJSON`, or `cell_ids=LIST`. No selector returns the regional series.
The CLI accepts a region plus `--sub ID` or `--polygon PATH`, and `--output PATH`.
Example: `python -m pipeline.analytics lk --sub 0 --output /tmp/lk_district.parquet`.
IDs and names are in `data/boundaries/<region>_subs.geojson`.
Selections are monthly H3 aggregates. Polygon selection uses cell centres, includes
polygon boundaries, respects holes, and rejects selections containing no centres.
Precomputed admin outputs include names and explicit `no_h3_centres` null records for tiny areas without cell centres (seven NSW areas at resolution 6).
This is not exact point-level clipping. The selected grid area is the sum of whole
H3 cell areas, not exact district/land area. Daily ranges and MTD comparisons are
not exposed because saved cell aggregates are monthly.

## Availability states

`<region>_coverage.parquet` records `month`, reference `fam`, `status`, bbox detection
count, `as_of`, `last_detection`, and `coverage_basis`.

- `inferred_available`: a closed archive month with regional bbox activity and later
  reference activity. Absence within a category or selected cell is treated as zero
  conditional on this regional availability assumption.
- `provisional`: the first/last detection month of a reference, or current month.
  Counts remain available but cannot enter full-month training or historical comparisons.
- `missing`: no reference detections in the regional bbox month. This is not a claim
  that the instrument was offline: it can also be a genuinely quiet month. Values
  remain null unless a calibrated MODIS estimate is available.

Hotspot records alone cannot establish satellite overpass, cloud-free observation,
or archive completeness. This proxy is explicitly labelled; actual observation
coverage requires additional inputs. No days-with-detections fraction is called
coverage, and provisional totals are never extrapolated to a full month.

Regional monthly outputs include each reference status, `period_status`,
`comparison_eligible`, and `training_eligible`. Both references must be inferred
available for calibration. Category/confidence zeros are retained in those months.
S-NPP is preferred for observed months; missing S-NPP falls back to calibrated
MODIS where possible. No supported calibration/input means null and source
`missing`, not a synthetic zero. NOAA-20/21 remain separate and are not stacked.

`now_vs_history` compares an eligible target against previous eligible years of the
same calendar month (default five historical years). It excludes the target itself,
provisional/missing values, and returns unavailable for a partial current month.
It reports median, absolute anomaly, and a midrank empirical percentile. Filtering
uses categories and confidence. Cross-year NSW seasonal timing is now computed
from the monthly history in the web app; see `season_insights.md` for definitions,
eligibility, month-level precision and trend limits.

## Spatial transfer and uncertainty

Within each category/confidence/month, selected-area history is the regional
VIIRS-equivalent result multiplied by selected MODIS cell-days / regional MODIS
cell-days. Modern observations use local S-NPP directly. This avoids applying a
nonlinear regional model independently to every small area, which would create
non-additive intercepts. District partitions sum back to the region wherever input
supports allocation. A positive regional prediction with no MODIS activity cannot
be located: smaller areas receive null and `unallocatable_no_modis`, rather than
invented locations. A whole-region query retains the regional result.

`allocation_status`, selected cell count, grid area, activity per 1,000 km²,
`spatial_method`, and `interval_method` accompany area results. Local transfer
accuracy has not been independently validated. Bounds are proportional allocations
of regional residual bounds, not calibrated local prediction intervals. Observed
bounds remain point values and do not describe instrument measurement uncertainty.

Validation checks full-region query identity, supported subregion conservation,
null/eligibility rules, H3 identity, raw detection conservation, and band ordering.
The square-grid comparison is historical context; its evaluation sample predates
these availability rules, so it is not a controlled grid-only comparison anymore.
The original migration comparison remains in `h3_validation.md`.
