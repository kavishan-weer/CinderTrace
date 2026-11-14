# Events map and candidate explorer

The local observatory now has an **Activity / Event candidates** switch above
the map. It queries the existing offline event catalogues through the loopback
service; it performs no live clustering, remote query or external upload.

## Selection contract

- Select one reference satellite: Suomi-NPP, Aqua or Terra. Streams stay separate
  and counts are not harmonized or added across satellites.
- Event membership uses the existing vegetation / individual nominal+high /
  2 km / 48 h catalogue. Activity-chart filters do not rebuild these components;
  the fixed event filters and their distinction are visible above and below the map.
- A candidate appears only if an original member detection falls in the selected
  UTC month and area. An interval overlap without an observation is insufficient.
- Custom polygons/circles clip point coordinates exactly. Administrative selections
  use the existing point-to-H3 administrative membership. The area selects global
  candidates; it never splits or reclusters them.
- Single-detection candidates are hidden by default with their hidden count shown.
  A checkbox includes them. Other candidates may still have one observed date.
- Markers are actual selected-month/area observations (the largest FRP point,
  with a timestamp tie-break). Their position is not an inferred ignition point,
  incident centroid, perimeter or event extent.
- Responses are ranked by selected-month/area detection count and capped at 2,000
  markers. The UI explicitly reports truncation and totals if the cap applies;
  the list pages through the returned candidates, eight at a time.

The history-window year controls belong to the historical charts. The Events view
uses the selected map month, which is shown in its heading and query scope.

## Details and map footprint

Click a marker or a list candidate. Its full regional candidate history shows:
first/last UTC detection, elapsed observed span, number of observed dates,
inclusive calendar span, maximum gap, total original detections and maximum valid
individual-detection FRP in MW. These metrics can extend outside the selected
month or area; the scope is explicit. Duration does not establish continuous
burning or ignition-to-extinction time. Peak FRP is not total event power.

The daily-count timeline uses actual elapsed dates, preserving quiet gaps. A date
selector and previous/next observed-date buttons change the sampled footprint;
**All dates** restores the full candidate footprint. Resolution-8 H3 cells touched
by member detections are rendered as a translucent outline layer. This is sampled
grid coverage, not burned area or a validated fire perimeter. The selected marker
is orange and drawn last; selection fits the full candidate bounding box once.
Changing observation dates preserves the user's current map view.

## Evidence and cautions

The view is labelled **experimental estimated detection clusters**. The main
warning explains splitting/merging and explicitly says confirmed counts are not
available. Details expose singleton/one-date support, regional and archive edges,
chains exceeding 30 days, possible persistent sources, and general duration/FRP/
footprint limits.

For S-NPP candidates in the 12-case California/NSW review, details show associated
agency references, material/minor support, fragmentation and shared-candidate
review flags. They never assign an official incident identity or accuracy score.
The Gospers example shows the documented 40.2% dominant-fragment share where relevant.
Reference associations are shown only for the exact audited input fingerprint,
catalogue path and membership-file SHA-256. Aqua/Terra have no agency case audit;
Sri Lankan records provide locality/date context only. Lack of an association is
explicitly not a false-positive label. Regional validation expands to all sampled
case summaries and limits.

## Local API and operation

- `POST /api/events/query`: region, satellite, month, optional administrative ID
  or polygon, and boolean `include_singletons`.
- `POST /api/events/detail`: region, satellite, candidate ID and an observed date
  or `all` for the footprint. The ID must belong to that exact stream.

Queries use the current default catalogue matching the pipeline's source
fingerprint. A missing/ambiguous catalogue is a clear error, not a fabricated empty
layer. The local service's origin rejection, request-size limit and two-job bound
also apply. Up to three catalogue datasets are cached. Restart the local app after
rebuilding catalogues or reference reviews so cached snapshots are cleared.

Browser requests cancel when selection changes; stale responses do not populate
another region, month, satellite or candidate. The list supplies keyboard-accessible
selection alongside canvas markers. Empty months, pre-satellite periods and empty
areas report the available catalogue date range and do not imply low fire risk.

## Verification

Four new Python API tests cover original point/month selection, global metric
scope, singleton visibility, missing-observation exclusion, full timelines,
date-specific footprints and invalid inputs. Three new frontend tests cover
cautions, elapsed duration and date spacing (including leap day). Real query/detail
responses were checked for Sri Lanka, California and NSW and strict JSON validity.
Browser checks cover marker selection, agency cautions, date stepping and footprint
updates, satellite switching, empty/area results and mobile layout.
