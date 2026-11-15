# Active direction: reuse published data and deliver analytics

15 November 2026. This supersedes the user-run swath-processing workflow. No more bulk observation notebooks are required for the current product work. Previous research is retained, not promoted into validated estimates. The subsequent delivery connects these sources to the existing CinderTrace visual design; see `web/README.md` for the active app.

## Sources actually checked

**Portolan FIRMS catalogue** — https://github.com/portolan-mirrors/firms-catalog

Primary observed detection source. Hosted, year-partitioned GeoParquet on Source Cooperative can be queried for only the requested dates/region. Live catalogue/collection requests returned HTTP 200; snapshots and hashes are saved in `docs/sources/ready_data_review/`. The repository identifies NASA FIRMS as upstream and publishes data as CC0. The current collection supplies standard/NRT quality and sensor lineage. Our previously verified local Sri Lanka standard-data checkpoint already contains 171,244 observations for 2000–2024 and is available immediately; it does not need rebuilding to support descriptive observed-data analytics.

**Fire Harmony** — https://github.com/Warren-530/fire-harmony

Ready-made analytics are published at https://huggingface.co/datasets/warrensaw530/fire-harmony under CC BY 4.0. The public API confirms that the dataset is not gated. Revision `9c1c703472d727d9f9b42477df39440bb34b2b64` was pinned and downloaded: the 7,392,288-byte global monthly table plus areas, metadata and dashboard. The monthly file's SHA256 matches the publisher's LFS hash. JSON files have local fingerprints and exact expected sizes. Code and model claims were inspected as documentation; no external repository code was executed.

This is a reusable third-party modelled/derived product, not independent validation of our own harmonization. Attribution is retained in `data/external/fire_harmony_v1/ATTRIBUTION.md`. The source supplies raw-sensor-related columns and a harmonized activity field on its stated NOAA-20 scale. That harmonized field remains labelled third-party derived across the record; its source codes and unavailable values are preserved.

**Alternatives reviewed:** NASA VEDA's FIRMS GitHub folder primarily supplies processing scripts rather than an immediately downloadable equivalent area table. The Huyt FIRMS archive on Hugging Face requires accepting access conditions, so it offers less convenience for this workflow. Neither is needed for the initial analytics.

## Work completed locally

The 1,344,809-row published global monthly table is saved under `data/external/fire_harmony_v1/`. Sri Lanka extracts under its `sri_lanka/` folder contain:

- 313 country-month records, November 2000–November 2026;
- 7,804 records for 25 provider administrative units;
- complete-provider-year totals through 2025;
- top provider-activity months;
- a monthly seasonal profile of provider-derived values;
- administrative yearly activity rankings, only for units with all twelve activity values;
- a separate native, satellite-specific monthly table from our verified checkpoint, retaining unavailable/partial/gap states instead of manufacturing zeros.

No provider values were changed or imputed. Missing administrative rows remain missing. Seasonal percentile envelopes describe variability of the provider's series, not model confidence intervals. Provider administrative support is a coarse H3 allocation, not exact district polygons or measured burned area; exact density rankings are not supplied. Some provider current-period activity is unavailable and stays null. Native observed counts and third-party harmonized units are distinct and must not be mixed into one total or represented as identical filters.

## Product work from here

Use Portolan/native observations for the map, time selection, satellite/confidence filters and exact observation exports. Use explicitly attributed, fixed-scope Fire Harmony tables for ready-made historical reference analytics and comparisons. Keep method, units, spatial support and modelled/observed distinctions visible. Do not label third-party results as models trained or independently validated by CinderTrace. Arbitrary polygon analytics must use appropriate point/cell data rather than pretending precomputed administrative rows describe the polygon.

Build monthly calendars, seasonal profiles, historical extremes and administrative activity tables from these ready files. Keep sensor-specific observed trends available. Neither source establishes unique incident counts, complete observation coverage or actual burned area by counting hotspots. The existing frontend design can be retained when these datasets are connected; the active app now uses these sources with the existing visual design.

The next user step is not another Colab processing/download exercise. Dataset extraction and analytics can now be handled directly in the project.
