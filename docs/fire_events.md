# Estimated fire-event candidates: pipeline and validation

Phase 3A is implemented as an **offline research pipeline**. The Events map layer
has not been added. Raw archive files, harmonized monthly series and the current
web app remain unchanged.

## Run and outputs

From the repository root, using the existing local archive:

```sh
.venv/bin/python -m ml.events lk ca nsw --satellites Suomi-NPP Aqua Terra
.venv/bin/python -m ml.validate_events lk ca nsw
.venv/bin/python -m unittest discover -s tests -p 'test_events.py' -v
```

`ml.events` defaults to Suomi-NPP only. Additional satellites are separate streams,
never extra points stacked into that catalogue. NOAA-20/21 can be built explicitly
but are not merged with S-NPP. Aqua and Terra are separate historical catalogues,
not a stitched 2000-present event-count series. No event-count harmonization is
implemented or implied.

Optional `--spatial-km` and `--temporal-hours` control the graph-link thresholds.
The default is **2 km / 48 hours**, a transparent research baseline rather than a
threshold fitted to official incidents. Each region/stream/configuration/input
snapshot has its own directory:

`data/events/<region>/<stream>/<configuration hash>-<input fingerprint prefix>/`

It contains:

| File | Contents |
| --- | --- |
| `events.parquet` | Candidate ID, observed start/end/span, dates, count, peak individual-detection FRP, centroid, bounds, sampled grid footprint and caution flags |
| `memberships.parquet` | Every included original detection, source file/row and detection ID, event ID, H3 source labels and footprint cell |
| `daily.parquet` | Candidate/date detection counts, peak individual-detection FRP and detection-weighted centroid |
| `report.json` | Parameters, exact input SHA-256s, selection accounting, structural checks and limitations |

The input fingerprint includes raw files, H3 membership and historical source
categories. Output directories are assembled before being renamed into place.
A completed snapshot is reused on rerun. IDs are deterministic for a given
configuration and connected-component anchor, invariant to input-row order.
New observations can merge candidates; IDs are not permanent incident identifiers.
Algorithm changes must update `VERSION` in `ml/events.py` before reuse of outputs.

## Selection and clustering

- Reuse the existing regional resolution-6 H3 membership and cell source categories.
  This is the project's approximate regional selection, not exact point clipping.
- Keep vegetation-category cells and original source type `0` or unassigned.
  Original non-vegetation flags are excluded even inside a vegetation cell.
- Use **individual-detection nominal/high confidence**. Unknown or out-of-range
  confidence is excluded. This differs intentionally from the headline calendar's
  maximum sensor-family cell-day convention: an event needs actual point evidence.
- Preserve every selected row, including repeated coordinates/times. Repeated
  observations belong to the same component; their original rows are not erased.
- Link two points only when both spherical great-circle separation is at most
  the spatial radius and exact acquisition-time separation is at most the time
  limit. Acquisition timestamps are interpreted as UTC and normalized explicitly
  to nanoseconds to avoid pandas timestamp-unit differences.
- Components are transitive, equivalent to space-time DBSCAN connectivity with
  `min_samples=1`. Singletons remain **weak candidates**, not confirmed fires or
  automatically discarded noise. This is not density-based noise rejection.
- Stream the entire archive by time across file, month and year boundaries.
  Local sparse graphs and retained component links preserve earlier connections
  without storing every graph edge for the full archive.

H3 does not determine event adjacency. Distances use original point coordinates;
resolution-8 H3 cells describe the sampled footprint only, while resolution-6
cells supply existing regional membership/category metadata.

## Metric definitions and limits

`observed_span_hours` is last minus first detection; a singleton has zero observed
span. `calendar_span_days` is inclusive date span and `observed_dates` counts dates
with detections. None proves continuous burning, ignition date or extinction.
`max_detection_gap_hours` exposes temporal bridges within a component.

`peak_detection_frp_mw` is the maximum nonnegative finite **individual detection**
FRP. It is not instantaneous whole-event power, summed power across overpasses or
energy. Missing/invalid FRP is excluded from this metric, not fabricated as zero.

The footprint is the area sum of unique resolution-8 cells touched by detections.
It is **sampled grid area, not burned area, event size or a validated perimeter**.
The bounding box and detection-weighted centroid support later visualization.
No spread-speed or fire-line claim is made from these point samples.

Cautions mark singletons, candidates touching the regional membership edge,
archive-time-edge candidates, candidates ending in the latest observed month,
chains exceeding 30 days and long chains restricted to at most three footprint
cells (possible persistent heat). Edge flags indicate potential censoring; quiet
periods do not verify observation coverage. Source categories are retrospective
and can use later observations, so this is not a leakage-free operational hindcast.

Transitive links can join nearby agricultural burns or separate incidents into a
complex. Clouds, missing observations and threshold choices can split one fire.
Different sensors have different detection sensitivity. Candidate counts must
not be presented as confirmed incidents, comparable cross-sensor trends, official
fire perimeters or evidence that event counts are now harmonized.

## Validation results for the current archive

Full-archive **Suomi-NPP** results, across its available 2012-2026 detections:

| Region | Included detections | Candidate components | Singletons | Multi-date candidates |
| --- | ---: | ---: | ---: | ---: |
| Sri Lanka | 93,265 | 57,894 | 39,841 | 4,592 |
| California | 886,252 | 57,926 | 31,405 | 9,485 |
| NSW | 1,187,746 | 170,015 | 73,667 | 30,351 |

Every included detection is assigned exactly once. Event and daily totals conserve
the selected points. Checks additionally verify per-event counts/start/end times,
catalogue and membership ID agreement, unique daily event/date records, one
satellite per catalogue, nonnegative spans and internal time gaps within the link
limit. All nine catalogues (three regions x S-NPP/Aqua/Terra) pass these checks.
The full raw selection audit also accounts for excluded boundary, category/type,
low/unknown-confidence and invalid-time/coordinate records.

Nine algorithm tests cover isolated detections, spatial/time separation, exact
thresholds, UTC year boundaries, duplicates, order/batch invariance, long chains,
retained old connections, dateline/high-latitude distances, invalid input,
raw-row lineage/filtering, empty outputs, tampered summary rejection and
independent-satellite matching. Randomized outputs match a separate all-pairs
haversine oracle at three latitudes and three batch sizes.

### Threshold sensitivity

The fixed diagnostics use identical inputs padded by 72 hours on either side,
then count components intersecting the unpadded period. Grids test radii 1/2/3 km
and gaps 24/48/72 hours. Padding can still truncate longer connections; these are
bounded diagnostic results, not full-catalogue event/ignition counts.

| Region / diagnostic period (UTC) | Default 2 km / 48 h | Range across nine settings |
| --- | ---: | ---: |
| Sri Lanka / 2020 | 4,436 | 3,854-4,948 |
| California / September 2020 | 379 | 267-981 |
| NSW / December 2019 | 836 | 587-2,216 |

Increasing either link threshold never increases the number of connected
components; this monotonicity check passes in all regions. Reports also retain
singleton core fragments, largest-component share and adjusted Rand agreement
against the default. ARI is agreement with a baseline partition, not accuracy.
The wide ranges are a substantive limitation: no single count should be sold as
the true number of incidents.

### Independent satellite co-detection

NOAA-20 is excluded from the S-NPP clusters. Selected NOAA-20 detections in the
same diagnostic periods are matched to S-NPP points within 2 km / 24 hours.

| Region | S-NPP points with NOAA-20 support | NOAA-20 points matching S-NPP | Default candidates with NOAA-20 support |
| --- | ---: | ---: | ---: |
| Sri Lanka | 23.8% | 22.9% | 888 / 4,436 |
| California | 99.4% | 98.8% | 219 / 379 |
| NSW | 99.0% | 98.7% | 510 / 836 |

Reports also flag NOAA-20 points supporting multiple candidate components.
Large-fire point support can be high even when cluster boundaries/counts are
sensitive. Low support for small short-lived detections can reflect differences
in overpass time and persistence; it is not a false-positive estimate.

**Update:** a purposive agency-record comparison has now been completed for 12
California/NSW perimeters, with two locality-only Sri Lankan reports. See
[the incident assessment](incident_validation.md). It identifies substantial NSW
fragmentation and retains the baseline as experimental; it does not establish
incident-count accuracy.

**Not yet validated:** representative/held-out official-incident matching, event-count precision/recall,
perimeter accuracy, event-size/spread estimates, independent local source labels,
cross-sensor count comparability, or performance outside the stated sensitivity
windows. The 2 km / 48 h baseline is not tuned on incident ground truth.

## Gate before the Events map layer

The pipeline is ready for review and experimental candidate visualization. The UI
must say **estimated event candidates**, expose singleton/support and caution
flags, keep reference satellites separate, and avoid reporting a count as official
incidents. Before stronger operational or accuracy claims, match a documented set
of agency incidents/perimeters across multiple regimes and review merges/splits.
The large parameter sensitivity should be visible in the method, not hidden.

### References

- [NASA FIRMS: VIIRS modeled fire perimeters / FEDS](https://firms.modaps.eosdis.nasa.gov/descriptions/FEDS_VIIRS_SNPP.html) - an established event approach and interpretation limits. Our connected-component baseline is **not** an implementation of FEDS.
- [Global Fire Atlas, Andela et al. (2019)](https://essd.copernicus.org/articles/11/529/2019/) - demonstrates individual-fire tracking using burned-area inputs. We do not use its burned-area product or claim its accuracy.
