# Normalized whole-region comparisons

The new comparison panel shows Sri Lanka, California and NSW side by side for the same selected calendar month, source-category filters and confidence classes. It appears after the selected-month statistics. Its month picker shares the map/calendar month state; administrative/drawn selections and the history-year window do not change the whole-region comparison.

`rate = sum(selected harmonized monthly slices) / sum(actual regional member H3 cell areas) × 1,000`

The denominator is the complete fixed regional grid membership, including inactive cells. It is not just active cells, an average H3 area, a bounding-box area, exact land area or a land-clipped polygon area. H3 resolution-6 membership includes the pipeline's approximate coastal buffers. Stored sums are approximately 72,094.27 km² for Sri Lanka, 422,742.77 km² for California and 818,386.00 km² for NSW. This definition makes the denominator consistent with the monthly numerator's spatial membership.

Every requested category/confidence slice must exist exactly once for the month, have finite nonnegative activity, and be eligible. Unsupported or duplicate slices, missing values and provisional months show an explicit unavailable state rather than zero or a partial sum. Genuine zeros remain comparable. Low-data slices carry a caution. The side-by-side bars use one common maximum for the three displayed rates; they do not estimate fire danger or forecast future activity.

Cards show the normalized rate, total harmonized activity, grid-area denominator and per-region archive snapshot. The comparison CSV includes all three rows, category/confidence selections, month, status, numerator, exact denominator, rate, low-data flag and snapshot. Missing rates export as empty fields with status retained. It is a separate download from selected-area monthly/raw CSVs.

Normalize area to compare burning-activity density, not distinct fire counts, burned area or risk. The same calendar month can occur in different local seasons. Land cover, sensor visibility and retrospective calibration limits remain; equal normalized rates do not imply equal hazard or equal detection completeness. No local spatial experiment or unvalidated outlook has been added.

Rebuild the compact static bundle with `.venv/bin/python -m pipeline.export_comparison`. The usual `pipeline.export_web` run also invokes this exporter. Tests cover filtering, exact area scaling, zero/missing/provisional handling, incomplete/duplicate slices, invalid denominators and low-data flags. Production build and all 32 frontend tests pass. Browser checks covered September rates, October provisional exclusion, shared confidence filters, the actual downloaded CSV and a 390-pixel stacked mobile layout without horizontal page overflow.
