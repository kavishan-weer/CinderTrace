# Agency incident comparison: results and decision

Review date: 2026-11-14 (Asia/Colombo).

**The baseline finds dominant clusters for the selected California cases, but fragments some large NSW incidents. It is suitable for experimental candidate exploration; its clusters cannot yet be counted as confirmed incidents.**

## Scope

This is a purposive case audit of eight California agency records and four NSW records, plus two locality-only Sri Lankan reports. It is not a representative validation sample, an independent held-out tuning set, or an estimate of overall incident precision/recall. No clustering parameter was changed or selected by optimizing these cases.

The California sample includes two official complexes (August and SCU). The Dixie agency record explicitly includes named constituent fires. Multiple ignitions within these records must not automatically be scored as erroneous clustering. NSW records use the final boundaries and date attributes supplied by the respective government services.

## Results for the retained 2 km / 48 h baseline

| Agency reference | Associated S-NPP detections | All candidate fragments | Material fragments | Largest fragment share |
| --- | ---: | ---: | ---: | ---: |
| Camp 2018 | 4,213 | 3 | 1 | 99.7% |
| Kincade 2019 | 1,599 | 2 | 1 | 99.8% |
| Glass 2020 | 2,067 | 4 | 1 | 99.9% |
| Creek 2020 | 35,997 | 66 | 1 | 98.9% |
| August Complex 2020 | 60,886 | 112 | 1 | 99.1% |
| SCU Lightning Complex 2020 | 8,979 | 14 | 1 | 98.8% |
| Dixie 2021 | 56,114 | 108 | 1 | 97.5% |
| Caldor 2021 | 18,746 | 32 | 2 | 97.0% |
| Gospers Mountain 2019/20 | 37,215 | 98 | 6 | 40.2% |
| Westbrook Rd / Dunns 2019/20 | 13,937 | 35 | 4 | 72.9% |
| Green Wattle Creek 2019/20 | 29,340 | 77 | 1 | 97.2% |
| Liberation Trail 2019 | 17,319 | 61 | 2 | 90.2% |

A material fragment contains at least `max(3, ceil(1% of reference-associated detections))`. This descriptive cutoff was specified before the matching run. The largest-fragment percentage measures concentration of point evidence; it is **not event accuracy, burned-area overlap, or a confidence probability**. All fragments, including one-point fragments, remain in the downloadable results.

All 12 selected reference windows contain retained S-NPP detections. This does not establish detection recall: the cases were selected deliberately and do not form a complete reference inventory.

## Threshold assessment

All nine settings (1/2/3 km by 24/48/72 h) were evaluated on the full regional S-NPP archive. Clusters were never cut at the incident, month or year boundary. Reference association was evaluated with the exact decoded polygon and separately with a 1 km buffer.

| Reference | Largest fragment share across the nine settings, exact polygon | Material fragment count range |
| --- | ---: | ---: |
| Caldor 2021 | 96.4-97.4% | 2-2 |
| Gospers Mountain 2019/20 | 36.1-40.2% | 4-8 |
| Westbrook Rd / Dunns 2019/20 | 66.3-79.4% | 2-7 |
| Liberation Trail 2019 | 79.2-98.2% | 1-6 |

The Gospers result is not resolved by any tested universal threshold. Simply enlarging the spatial/temporal radius would risk merging separate incidents without establishing correct fire-front continuity. The 2 km / 48 h setting remains a transparent **research baseline**, with no claim that it is calibrated to true incident counts.

Cross-reference merge review found **0 shared material-candidate rows** among these selected records across the tested settings and buffers. This is not a general merge-error rate: a complete inventory of adjacent simultaneous fires was not sampled, and unmatched candidates have no false-positive label.

## Reference geometry and date handling

Official public sources were cached with query URLs, retrieval times and SHA-256 hashes. CAL FIRE was resolved through the California state data catalogue, rather than a third-party copy. NSW uses two government layers because the consolidated layer did not return the selected Gospers and Dunns records; their named 2019/20 RFS records are present in the alternate government fire-history layer.

The initial CAL FIRE GeoJSON exports contained nested polygon shells in place of some interior holes. Comparing an unsimplified export showed that this was not solely a simplification issue. The final audit therefore uses **native Esri polygon rings**, decoding clockwise exteriors and counterclockwise interiors while preserving islands. Original native responses, the normalized polygons, decoding diagnostics and rejected/previous exports are retained. The final geometries are valid.

Most reference queries use agency generalization of 0.0001 degree (about 11 m north-south). The generalized SCU rings failed containment validation, so that case was fetched without generalization. Residual geometry repairs and zero-area remnants are recorded explicitly; no arbitrary invalid polygon was treated as a verified perimeter. The secondary 1 km buffer is computed in a local spherical azimuthal-equidistant projection.

Stored start/end dates are used as calendar-day bounds, padded by one day on both sides to avoid implying precise acquisition-time agreement. California CONT_DATE is containment, not extinction. No ignition-time error, duration accuracy or perimeter-area accuracy is inferred from this association.

## Sri Lanka: contextual checks only

| Official report | District / local date | District detections in the 3-day window | District candidates |
| --- | --- | ---: | ---: |
| [Hanthana mountain fire](https://alt.army.lk/sfhqcentral/content/army-troops-doused-sudden-fire) | Kandy District / 2020-02-10 | 14 | 7 |
| [Redeepana forest fire](https://www.army.lk/news/army-troops-assist-extinguishing-wildfire-redeepana) | Badulla District / 2026-09-11 | 15 | 13 |

Windows use Sri Lankan local midnight with the day before and after. Neither report supplies an incident perimeter or precise ignition coordinates. These are whole-district/date checks: nearby candidates are **not verified matches**, and absent detections would not disprove the reported fire. These forest-fire reports do not validate agricultural-burn clustering. No Sri Lankan threshold was tuned from them.

Source retrieval status: lk-hanthana-2020: cached; lk-redeepana-2026: cached. Cached source hashes or retrieval errors are in `data/validation/incident_references/locality-sources.json`.

## Support flags for the future Events viewer

Default candidate/reference links retain stable candidate IDs, associated detections and dates, material/minor association, dominance for a reference, shared material references, and reference-fragmentation cautions. Aggregated candidate flags are in `ca-candidate-review-flags.csv` and `nsw-candidate-review-flags.csv`. These flags document association with the selected agency records; they do not assign an official incident identity or a calibrated confidence score.

The Events map layer has not been added. A future experimental viewer can expose these associations and existing singleton/edge/chaining flags. Headline confirmed-incident counts remain unsupported. Stronger claims need broader held-out references, close simultaneous fire pairs and precise Sri Lankan incident data; dynamic event tracking should be assessed before treating disconnected fire-front clusters as individual fires.

## Reproduce and inspect

```sh
.venv/bin/python -m ml.incident_references --fetch
.venv/bin/python -m ml.assess_incidents ca nsw lk
.venv/bin/python -m ml.report_incident_assessment
.venv/bin/python -m unittest discover -s tests -p "test_incident_assessment.py" -v
```

Case selection is versioned in `ml/incident_cases.json`. Cached references are under `data/validation/incident_references/`; results are under `data/validation/incident_assessment/`. The two regional `*-case-sensitivity.csv` files include every setting and both boundary tolerances; `*-default-links.csv` retains candidate-level evidence. Each assessment JSON identifies the production catalogue, exact membership-file hash, input fingerprint and reference hashes. `decision.json` records the interpretation gate.

Seven new tests cover polygon boundaries/holes, explicit date windows, metric buffers, ring decoding with nested islands, raw-reference hashes and missing dates, fragment statistics, cross-reference review and support-flag semantics. Existing clustering and pipeline/export tests remain part of the regression suite.

## Sources

- [California state catalogue: CAL FIRE fire perimeters](https://data.ca.gov/@cal-fire/california-fire-perimeters-all).
- [Official CAL FIRE historical perimeter service](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0).
- [NSW consolidated fire-history layer](https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/NSWFireHistory/FeatureServer/0).
- [NSW alternate historical fire layer](https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/NSW_Fire_History/FeatureServer/0).
- Sri Lanka Army report URLs are linked in the locality table.
