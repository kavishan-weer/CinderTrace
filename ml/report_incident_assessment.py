"""Write the human-readable case review and machine-readable interpretation gate."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .assess_incidents import OUT
from .events import ROOT
from .incident_references import CACHE


def main():
    frames=[pd.read_csv(OUT/f'{region}-case-sensitivity.csv') for region in ['ca','nsw']]
    scores=pd.concat(frames,ignore_index=True)
    primary=scores[(scores.spatial_km==2)&(scores.temporal_hours==48)&(scores.boundary_buffer_km==0)]
    sample=primary[['case_id','case_name','case_kind','reference_points','candidate_fragments','material_fragments','dominant_reference_share']]
    (OUT/'default-case-summary.csv').write_text(sample.to_csv(index=False))
    for region in ['ca','nsw']:
        links=pd.read_csv(OUT/f'{region}-default-links.csv')
        flags=links.groupby('event_id',as_index=False).agg(associated_reference_records=('case_id','size'),
            material_reference_records=('material_reference_association','sum'),
            dominant_for_any_reference=('dominant_for_reference','any'),
            shared_candidate_review=('shared_candidate_review','any'),
            reference_fragmentation_caution=('reference_fragmentation_caution','any'),
            associated_case_ids=('case_id',lambda ids:';'.join(sorted(ids))))
        flags['evidence_scope']='Selected agency records only; association is not official incident identity.'
        flags.to_csv(OUT/f'{region}-candidate-review-flags.csv',index=False)
    merges=pd.concat([pd.read_csv(OUT/f'{r}-merge-review.csv') for r in ['ca','nsw']],ignore_index=True)
    context=json.loads((OUT/'lk-context.json').read_text())
    locality_sources=json.loads((CACHE/'locality-sources.json').read_text()) if (CACHE/'locality-sources.json').exists() else []
    decision={
        'method':'agency-case-audit-v1','default_parameters':{'spatial_km':2,'temporal_hours':48},
        'default_status':'Research baseline retained without tuning on this purposive sample.',
        'official_incident_count_ready':False,
        'experimental_candidate_map_ready':True,
        'map_conditions':['Say estimated detection clusters / event candidates.',
            'Show singleton, observation-span, archive-edge, chaining and reference-fragmentation cautions.',
            'Keep satellites separate; preserve reference-association provenance.',
            'Do not claim confirmed incident counts, event accuracy probabilities or burned-area/perimeter accuracy.'],
        'perimeter_cases':len(primary),'locality_only_reports':len(context['cases']),
        'cases_with_multiple_material_components':sample[sample.material_fragments>1].to_dict(orient='records'),
        'sampled_cross_reference_shared_candidates_review_rows':len(merges),
        'remaining_validation':['Broader held-out incidents across size/regime distributions.',
            'Adjacent simultaneous fires and a more complete reference inventory for merge evaluation.',
            'Precise Sri Lanka incident locations/perimeters, including small agricultural burns.',
            'Temporal/object tracking to connect changing fire fronts; do not simply enlarge graph-link gaps.']}
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2,allow_nan=False))
    lines=['# Agency incident comparison: results and decision','',
        f"Review date: {datetime.now(ZoneInfo('Asia/Colombo')).date().isoformat()} (Asia/Colombo).",'',
        '**The baseline finds dominant clusters for the selected California cases, but fragments some large NSW incidents. It is suitable for experimental candidate exploration; its clusters cannot yet be counted as confirmed incidents.**','',
        '## Scope','',
        'This is a purposive case audit of eight California agency records and four NSW records, plus two locality-only Sri Lankan reports. It is not a representative validation sample, an independent held-out tuning set, or an estimate of overall incident precision/recall. No clustering parameter was changed or selected by optimizing these cases.','',
        'The California sample includes two official complexes (August and SCU). The Dixie agency record explicitly includes named constituent fires. Multiple ignitions within these records must not automatically be scored as erroneous clustering. NSW records use the final boundaries and date attributes supplied by the respective government services.','',
        '## Results for the retained 2 km / 48 h baseline','',
        '| Agency reference | Associated S-NPP detections | All candidate fragments | Material fragments | Largest fragment share |',
        '| --- | ---: | ---: | ---: | ---: |']
    for row in sample.itertuples():
        lines.append(f'| {row.case_name} | {row.reference_points:,} | {row.candidate_fragments} | {row.material_fragments} | {100*row.dominant_reference_share:.1f}% |')
    lines+=['',
        'A material fragment contains at least `max(3, ceil(1% of reference-associated detections))`. This descriptive cutoff was specified before the matching run. The largest-fragment percentage measures concentration of point evidence; it is **not event accuracy, burned-area overlap, or a confidence probability**. All fragments, including one-point fragments, remain in the downloadable results.','',
        'All 12 selected reference windows contain retained S-NPP detections. This does not establish detection recall: the cases were selected deliberately and do not form a complete reference inventory.','',
        '## Threshold assessment','',
        'All nine settings (1/2/3 km by 24/48/72 h) were evaluated on the full regional S-NPP archive. Clusters were never cut at the incident, month or year boundary. Reference association was evaluated with the exact decoded polygon and separately with a 1 km buffer.','',
        '| Reference | Largest fragment share across the nine settings, exact polygon | Material fragment count range |',
        '| --- | ---: | ---: |']
    for case_id in ['ca-caldor-2021','nsw-gospers-2019','nsw-dunns-2019','nsw-liberation-2019']:
        rows=scores[(scores.case_id==case_id)&(scores.boundary_buffer_km==0)]
        lines.append(f'| {rows.case_name.iloc[0]} | {100*rows.dominant_reference_share.min():.1f}-{100*rows.dominant_reference_share.max():.1f}% | {rows.material_fragments.min()}-{rows.material_fragments.max()} |')
    lines+=['',
        'The Gospers result is not resolved by any tested universal threshold. Simply enlarging the spatial/temporal radius would risk merging separate incidents without establishing correct fire-front continuity. The 2 km / 48 h setting remains a transparent **research baseline**, with no claim that it is calibrated to true incident counts.','',
        f'Cross-reference merge review found **{len(merges)} shared material-candidate rows** among these selected records across the tested settings and buffers. This is not a general merge-error rate: a complete inventory of adjacent simultaneous fires was not sampled, and unmatched candidates have no false-positive label.','',
        '## Reference geometry and date handling','',
        'Official public sources were cached with query URLs, retrieval times and SHA-256 hashes. CAL FIRE was resolved through the California state data catalogue, rather than a third-party copy. NSW uses two government layers because the consolidated layer did not return the selected Gospers and Dunns records; their named 2019/20 RFS records are present in the alternate government fire-history layer.','',
        'The initial CAL FIRE GeoJSON exports contained nested polygon shells in place of some interior holes. Comparing an unsimplified export showed that this was not solely a simplification issue. The final audit therefore uses **native Esri polygon rings**, decoding clockwise exteriors and counterclockwise interiors while preserving islands. Original native responses, the normalized polygons, decoding diagnostics and rejected/previous exports are retained. The final geometries are valid.','',
        'Most reference queries use agency generalization of 0.0001 degree (about 11 m north-south). The generalized SCU rings failed containment validation, so that case was fetched without generalization. Residual geometry repairs and zero-area remnants are recorded explicitly; no arbitrary invalid polygon was treated as a verified perimeter. The secondary 1 km buffer is computed in a local spherical azimuthal-equidistant projection.','',
        'Stored start/end dates are used as calendar-day bounds, padded by one day on both sides to avoid implying precise acquisition-time agreement. California CONT_DATE is containment, not extinction. No ignition-time error, duration accuracy or perimeter-area accuracy is inferred from this association.','',
        '## Sri Lanka: contextual checks only','',
        '| Official report | District / local date | District detections in the 3-day window | District candidates |',
        '| --- | --- | ---: | ---: |']
    for case in context['cases']:
        lines.append(f"| [{case['name']}]({case['source']}) | {case['district']} / {case['date_local']} | {case['district_detections']} | {case['district_candidates']} |")
    lines+=['',
        'Windows use Sri Lankan local midnight with the day before and after. Neither report supplies an incident perimeter or precise ignition coordinates. These are whole-district/date checks: nearby candidates are **not verified matches**, and absent detections would not disprove the reported fire. These forest-fire reports do not validate agricultural-burn clustering. No Sri Lankan threshold was tuned from them.']
    if locality_sources:
        lines+=['', 'Source retrieval status: '+ '; '.join(f"{s['id']}: {s['status']}" for s in locality_sources)+'. Cached source hashes or retrieval errors are in `data/validation/incident_references/locality-sources.json`.']
    lines+=['',
        '## Support flags for the future Events viewer','',
        'Default candidate/reference links retain stable candidate IDs, associated detections and dates, material/minor association, dominance for a reference, shared material references, and reference-fragmentation cautions. Aggregated candidate flags are in `ca-candidate-review-flags.csv` and `nsw-candidate-review-flags.csv`. These flags document association with the selected agency records; they do not assign an official incident identity or a calibrated confidence score.','',
        'The Events map layer has not been added. A future experimental viewer can expose these associations and existing singleton/edge/chaining flags. Headline confirmed-incident counts remain unsupported. Stronger claims need broader held-out references, close simultaneous fire pairs and precise Sri Lankan incident data; dynamic event tracking should be assessed before treating disconnected fire-front clusters as individual fires.','',
        '## Reproduce and inspect','',
        '```sh',
        '.venv/bin/python -m ml.incident_references --fetch',
        '.venv/bin/python -m ml.assess_incidents ca nsw lk',
        '.venv/bin/python -m ml.report_incident_assessment',
        '.venv/bin/python -m unittest discover -s tests -p "test_incident_assessment.py" -v',
        '```','',
        'Case selection is versioned in `ml/incident_cases.json`. Cached references are under `data/validation/incident_references/`; results are under `data/validation/incident_assessment/`. The two regional `*-case-sensitivity.csv` files include every setting and both boundary tolerances; `*-default-links.csv` retains candidate-level evidence. Each assessment JSON identifies the production catalogue, exact membership-file hash, input fingerprint and reference hashes. `decision.json` records the interpretation gate.','',
        'Seven new tests cover polygon boundaries/holes, explicit date windows, metric buffers, ring decoding with nested islands, raw-reference hashes and missing dates, fragment statistics, cross-reference review and support-flag semantics. Existing clustering and pipeline/export tests remain part of the regression suite.','',
        '## Sources','',
        '- [California state catalogue: CAL FIRE fire perimeters](https://data.ca.gov/@cal-fire/california-fire-perimeters-all).',
        '- [Official CAL FIRE historical perimeter service](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/California_Historic_Fire_Perimeters/FeatureServer/0).',
        '- [NSW consolidated fire-history layer](https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/NSWFireHistory/FeatureServer/0).',
        '- [NSW alternate historical fire layer](https://portal.data.nsw.gov.au/arcgis/rest/services/Hosted/NSW_Fire_History/FeatureServer/0).',
        '- Sri Lanka Army report URLs are linked in the locality table.','']
    path=ROOT/'docs/incident_validation.md';path.write_text('\n'.join(lines))
    print(f'Wrote {path.relative_to(ROOT)} and review flags / interpretation gate.')


if __name__=='__main__':main()
