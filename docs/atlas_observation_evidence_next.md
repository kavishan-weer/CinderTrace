# Sri Lanka observation-evidence pilot

The public catalogue discovery is complete. Science downloads and pixel screening remain pending Earthdata authentication in the notebook. The frontend and frozen observed-data checkpoint have not been changed.

## What was retrieved

The frozen catalogue is under `data/atlas/observation_evidence_pilot_v1/`. It contains 24 complete CMR response pages with retrieval receipts, the verified study boundary, a normalized inventory and anonymous access probes. All 34 listed fire granules have one matching same-platform geolocation granule with an identical acquisition and time extent: 68 science files in total. Catalogue sizes sum to 5,071.6 MiB, approximately 5 GiB. Nineteen cross-sensor granule-time candidates fall within 90 minutes. They are candidates only, not independent validated matched observations.

| UTC day | Sample role | S-NPP fire granules | NOAA-20 fire granules |
|---|---|---:|---:|
| 2021-08-15 | Recorded-zero control | 4 | 2 |
| 2021-08-19 | Positive control | 3 | 3 |
| 2022-08-04 | Listed S-NPP missing-standard-data date | 0 | 5 |
| 2022-08-12 | Recovery candidate | 4 | 2 |
| 2024-05-31 | Listed S-NPP missing-standard-data date | 0 | 3 |
| 2024-06-05 | Recovery candidate | 3 | 5 |

These are catalogue matches to the study bounding box, not counts of usable regional observations. Zero catalogue matches on the sampled outage dates remain unavailable observations. Listed later products are recovery candidates; they do not prove that intervening gaps were recovered. All four product download probes redirected to Earthdata login. No credentials were read or stored during discovery.

## Run the next notebook

Open `notebooks/CinderTrace_Atlas_LK_Observation_Evidence_Pilot.ipynb` and run the cells in order. The verified public metadata is embedded, so no input upload or FIRMS key is required. In Colab the default stores the cache in Drive for resuming; in VS Code it uses a local data folder. Allow approximately 5 GiB plus workspace overhead. Sign in at the Earthdata prompts inside the notebook: a browser session does not authenticate its Python session.

The workflow downloads all six sample days, checks file signatures and lengths, hashes completed files, verifies exact-acquisition companions and grid shapes, and checks sparse-fire coordinates where available. It retains local cloud, water, land, unclassified and fire-mask counts. A separate conservative pixel-centre quality screen excludes non-nominal input flags and residual bowtie pixels. Interrupted downloads retain verified files; an authentication denial stops subsequent downloads and exports a partial result with unavailable states. Each completed granule is checkpointed. On rerun the small diagnostics are recomputed from the verified cache.

The last cell downloads **one review ZIP**, including partial results if needed. It contains all metadata, method, download receipts, screening summaries, coarse spatial-support diagnostics, failure states and hashes. It excludes credentials and the large science-file cache. Save the notebook outputs and add that ZIP to the project folder.

## Interpretation and uncertainty work

This is a purposive feasibility sample. It cannot validate replacement error or interval coverage. Coarse H3 cell-centre overlap is not identical physical pixel footprints, complete area coverage or exact per-pixel time matching. Multiple candidate pairs can share granules and must not be counted as independent samples. Native fire masks also lack the vegetation-type attribution used in the prior regional transfer experiment. Those targets must be reconciled before comparing scores.

After reviewing the science outputs, the next study must establish pass grouping, actual spatial support, day/night and viewing geometry, type scope, archive reconciliation and recovery status. Then freeze a larger simulated-gap evaluation using disjoint fit, calibration and evaluation blocks. Evaluate replacement uncertainty separately from the full historical transfer chain. Do not adjust intervals to hit coverage on the already inspected holdouts and label that as new validation. The limited number of independent overlapping years constrains annual uncertainty: wider monthly bands do not validate annual bands or pre-overlap stability.

No gap filling, zero restoration, comparable historical bands, medians/seasons or district allocation is enabled by this pilot. Their scientific gates remain open. Existing published scores remain results from the earlier dataset; the repaired regional research scores retain their own narrow scope.

## Sources

- [NASA CMR search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html): public collection/granule metadata used in the frozen inventory.
- [NASA Collection 2 VIIRS active-fire guide](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.0.pdf): fire-mask classes, QA bit definitions and sparse-fire indices used by the reader.
- [S-NPP imagery geolocation](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP03IMG/) and [NOAA-20 imagery geolocation](https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VJ103IMG): companion pixel-location products.

The exact CMR request URLs, original responses, retrieval timestamps and hashes are retained with the pilot. Science screening has been tested with synthetic NetCDF files and failure cases; real science products have not yet been downloaded or screened in this step.
