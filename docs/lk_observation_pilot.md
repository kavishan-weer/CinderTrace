# Sri Lanka observation pilot — 14 November 2026

Public catalogue discovery is complete. Pixel-level observation verification is pending Earthdata authentication. No zero months, model inputs or production datasets were changed.

## Findings

- Found 342 unique Terra/Aqua daily fire-mask science files for 15 disputed closed months and six populated control months; estimated download size 206.4 MB from catalogue metadata.
- Both tested science download endpoints redirected anonymous requests to NASA Earthdata Login. Public catalogue metadata is accessible without signing in; the actual HDF science files require authenticated download through these endpoints.
- The prior count of 16 missing MODIS months included the ongoing November 2026 month. This pilot excludes it and investigates 15 closed months.
- Disputed months: 2001-01, 2001-12, 2002-12, 2003-01, 2004-11, 2005-11, 2009-11, 2010-11, 2011-12, 2012-11, 2012-12, 2015-11, 2015-12, 2023-12, 2025-01.
- Control months: 2001-03, 2002-01, 2003-03, 2012-08, 2022-12, 2023-08.
- Retained tiles: h25v08, h26v08. Spatial search results were checked against the study boundary; nonintersecting footprint matches were excluded.

## Month inventory

Counts are product files intersecting the region and time interval, not clear-sky observations. Each product packages daily layers across an eight-day interval, including packages crossing month boundaries. Early pre-mission Aqua absences are expected.

| Month | Role | Local combined MODIS detections in bbox | Terra files | Aqua files |
|---|---|---:|---:|---:|
| 2001-01 | disputed | 0 | 10 | 0 |
| 2001-03 | control | 42 | 10 | 0 |
| 2001-12 | disputed | 0 | 10 | 0 |
| 2002-01 | control | 2 | 10 | 0 |
| 2002-12 | disputed | 0 | 10 | 10 |
| 2003-01 | disputed | 0 | 10 | 10 |
| 2003-03 | control | 26 | 10 | 10 |
| 2004-11 | disputed | 0 | 8 | 8 |
| 2005-11 | disputed | 0 | 8 | 8 |
| 2009-11 | disputed | 0 | 8 | 8 |
| 2010-11 | disputed | 0 | 8 | 8 |
| 2011-12 | disputed | 0 | 10 | 10 |
| 2012-08 | control | 754 | 10 | 10 |
| 2012-11 | disputed | 0 | 8 | 8 |
| 2012-12 | disputed | 0 | 10 | 10 |
| 2015-11 | disputed | 0 | 8 | 8 |
| 2015-12 | disputed | 0 | 10 | 10 |
| 2022-12 | control | 2 | 10 | 10 |
| 2023-08 | control | 425 | 10 | 10 |
| 2023-12 | disputed | 0 | 10 | 10 |
| 2025-01 | disputed | 0 | 10 | 10 |

## Next steps after authentication

1. Download a small first batch: disputed January 2001 and December 2023, with populated January 2002 and December 2022 controls. This spans Terra-only and combined-sensor history while retaining same-calendar-month comparisons.
2. Read daily fire-mask and quality layers, retain the correct days from boundary-crossing packages, clip to Sri Lanka, and report fire, valid non-fire, cloud, unprocessed and missing conditions separately. Derive availability per location/day before regional monthly summaries.
3. Compare detections with the local archive. L3 daily compositing differs from individual overpasses and H3 sensor-family cell-days, so these files screen coverage; reconcile discrepancies against MOD14/MYD14 swath products and acquisition/geolocation records before certifying archive completeness.
4. Define coverage eligibility explicitly, test sensitivity to it, and leave poorly observed periods unavailable. Do not manufacture complete coverage from counts of existing product files.
5. Expand to remaining disputed/control months only after the small batch has been read and independently checked. Then feed reviewed evidence into the repair and scientific-validation workflow.

## Access and evidence

- [NASA Earthdata Login](https://urs.earthdata.nasa.gov/)
- [Terra collection in Earthdata Search](https://search.earthdata.nasa.gov/search?p=C2565791013-LPCLOUD)
- [Aqua collection in Earthdata Search](https://search.earthdata.nasa.gov/search?p=C2565794059-LPCLOUD)
- [Catalogue queries, complete file URLs, access probes and input hashes](lk_observation_pilot.json)
- Original query responses: `data/observation_pilot/lk/20261114T123742Z/`.
- Reproduce discovery with `.venv/bin/python -m pipeline.observation_pilot` (network access required; no credentials, bulk downloads or production writes).
- A browser sign-in and command-line download authentication are separate sessions. Connect the downloader through a secure local authentication flow after account access is available; do not place credentials or tokens in chat or tracked files.

## Checks

Three focused tests pass: footprint coordinate ordering, explicit Earthdata login redirects and rejection of HTML pages as successful science downloads. The pilot has not yet assessed pixel values, usable regional observation coverage or the scientific validity of any restored zero.
