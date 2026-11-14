# Selected-area Situation Brief PDF

The local observatory now has a **Situation Brief PDF** action above the burning
calendar. It captures the selected area, category/confidence filters, map month,
history window and archive snapshot, then downloads one A4 page. No data, source
or report is uploaded to external hosting or an AI service.

## Contents

- Selected-month harmonized activity, historical median and percentile.
- Three deterministic findings: month comparison, latest complete active season
  within the history window, and VIIRS-era duration trend (when supported).
- A compact burning calendar for the latest up to eight starting years within
  that window, preserving missing and provisional states and outlining the
  selected month when it falls in the displayed years.
- The latest complete active season's monthly activity and cumulative-share
  profile, with tied peaks and inclusive monthly duration.
- Separate uncertainty notes, sources, archive date and generated UTC timestamp.

Selected-month comparisons use all prior eligible matching months, just as the
app's history cards do; they are independent of the chart window. Both scopes are
labelled. NSW uses July-June starting years, including the next January-June.
The PDF's profile intentionally uses the latest complete active season rather
than the season panel's independently selected year. This is stated in the action
description and report. Custom polygons include their longitude/latitude extent;
coordinate-radius selections include coordinates/radius in the area name. Grid
cell count and available grid area describe H3 selection, not exact land area.

## Safeguards

The text is constructed from `web/src/brief.ts`, reusing the same history and
season calculations as the app. There is no generated interpretation or invented
statistic. Provisional months have no full-month comparison; missing values stay
unavailable. Zero historical medians do not produce percentage-change claims.
Incomplete seasons have no profile. Low-data flags and unsupported trends are
explicit. No daily precision or statistical significance is claimed.

Variable monthly bounds are labelled model-transfer ranges, not total measurement
confidence intervals. Equal/absent observed-month bounds are reported as
unquantified uncertainty, not certainty. The brief retains archive-coverage,
cloud/overpass, H3 membership, regional allocation and local-validation limits.
It is historical evidence, not an operational warning, forecast or event count.

## Local rendering and downloads

`POST /api/exports/brief` accepts a bounded computed snapshot and renders it with
ReportLab (`pipeline/brief_pdf.py`). The renderer validates the snapshot structure,
escapes text, draws vector charts and rejects a report that would exceed one page.
It does not load remote fonts, maps, images, URLs or files named by the client.
Python requirements now include `reportlab>=4.4,<5`.

Generated PDFs share the loopback service's private temporary directory, random
download tokens, ten-minute expiry and cleanup with raw CSVs. GET responses use
`application/pdf` and an attachment filename. A ready link lets users retry the
download if automatic downloads are blocked; it includes captured selection
labels so a report generated during a filter change remains identifiable.

## Verification

Six new frontend tests cover historical scope, provisional/missing months,
zero-median comparisons, NSW closing-year preservation, transfer/low-data notes
and the eight-year calendar limit. Python checks cover one-page output with and
without a season, long-area layouts, malformed input, PDF MIME/download behavior,
token extension/expiry and rejection of foreign browser origins. PDFs are rendered
with Poppler for visual inspection and checked with a PDF reader for text/page count.
