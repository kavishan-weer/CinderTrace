# Fire-season timing and trends

Implemented in the local observatory after the burning calendar. All results use
the same selected-area, category and confidence aggregation as the calendar.
No pipeline refit, raw-data change or additional download is required.

## Definitions and resolution

For Sri Lanka and California, a season is January–December. NSW uses July–June;
`2019/20` means July 2019 through June 2020. The history window selects **starting
years** for NSW, and the closing January–June is read from the full history even
when it falls beyond the window's end calendar year.

- Onset: first month where cumulative activity reaches 10% of annual activity.
- End: first month where cumulative activity reaches 90%.
- Peak: month with the maximum activity; all equal maxima are retained.
- Duration: end index minus onset index plus one, in calendar months, inclusive.

The measure is harmonized VIIRS-equivalent fire-active cell-days. This adapts the
cumulative 10–90% approach used in [Freeborn et al. (2014)](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1002/2013JG002518),
whose activity measure differs. We do not interpolate daily dates from monthly
totals. A one-month concentration has a one-month window; a broad window can
contain inactive months between two burning periods. This is especially relevant
to Sri Lanka's multiple burning periods. Calendar boundaries can split activity.
These measures do not estimate ignition dates, continuous burning or event counts.
Non-vegetation filters describe thermal-activity timing.

## Eligibility

Every one of the 12 expected months must be present, comparison-eligible,
non-provisional, finite and nonnegative. One unavailable month invalidates annual
timing and the annual total in this panel. Incomplete years remain visible with
their eligible-month count. Complete zero-total years retain total zero but have
no onset, peak, end or duration. Future/provisional years are never extrapolated.
Low-data calibration seasons can be viewed, marked with `*`, but do not enter trends.

Availability is the existing archive proxy, not verified cloud-free observation.
Selected-area timing inherits regional calibration and spatial-allocation limits.
Monthly transfer bounds are not treated as timing confidence intervals.

## Trends

The default trend period is seasons starting in 2013 or later (the first full
S-NPP calendar year), intersected with the history window. An explicit full-record
option includes earlier calibrated MODIS history. At least 10 eligible, active,
non-low-data seasons spanning at least 10 years are required for each metric.

The trend is the median of all pairwise `(timing_j - timing_i)/(year_j - year_i)`
slopes, multiplied by 10: months per decade (Theil–Sen). Gaps retain their actual
year separation. A second descriptive comparison subtracts the median of the
earliest five eligible seasons from that of the latest five; periods are labelled
and nonoverlapping. Positive onset/peak/end values mean later; positive duration
means longer. Near-zero slopes are labelled “No directional shift”, which is not
proof of stability. No statistical-significance or daily-precision claim is made.

Peak trends exclude tied maxima. A peak-month span exceeding six months suppresses
the linear trend because timing may cross the fixed year boundary or reflect
multiple burning periods. The interface explains this suppression.

## UI and export

The panel has a season-year selector, four timing cards, monthly-share bars and
cumulative activity, an interactive year-by-year window/peak timeline, four trend
cards and inline method notes. Missing and zero-activity years remain visible.
The season CSV includes every requested year, status, eligible-month count,
low-data flag, precise calendar month strings for all timing values, duration,
annual activity, area/filter/snapshot provenance and method description.

## Verification

Nine season-specific tests cover thresholds, tied peaks, single-month seasons,
NSW cross-year selection, all invalid-month cases, zero activity, actual-year
trend slopes and outlier resistance, minimum history, low-data exclusions,
peak wrap/ties and CSV provenance. Existing frontend tests also run.

With the current archive and default vegetation / nominal+high filters, whole-region
eligible active seasons number 17 (Sri Lanka), 25 (California), and 25 (NSW), over
starting years 2000–2026. Latest complete seasons are 2025, 2025 and 2025/26.
The default VIIRS-era onset/end/duration median pairwise slopes are zero at monthly
resolution; peak slopes are suppressed by the wide month span in each region.
These are descriptive snapshot checks, not independently validated ecological findings.
