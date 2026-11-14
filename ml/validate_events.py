"""Audit built catalogues, threshold sensitivity, and independent-satellite support.

Run: python -m ml.validate_events lk ca nsw
These are structural/sensitivity/co-detection checks, not incident-ground-truth
precision or recall. No external files are downloaded.
"""
import argparse
import json
import time

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sklearn.metrics import adjusted_rand_score

from .events import ROOT, EARTH_KM, Config, STREAMS, audit_catalog, cluster_points, load_points, xyz

WINDOWS={
 'lk':('2020-01-01','2021-01-01'),
 'ca':('2020-09-01','2020-10-01'),
 'nsw':('2019-12-01','2020-01-01'),
}


def support(reference, labels, other, core, spatial_km=2., temporal_hours=24.):
    """Bidirectional point co-detection and ambiguous component support."""
    matched_reference=np.zeros(len(reference),dtype=bool)
    matched_other=np.zeros(len(other),dtype=bool)
    supported_events=set();ambiguous=0
    if len(reference) and len(other):
        ref_time=reference.acq_datetime.dt.as_unit('ns').astype('int64').to_numpy()
        other_time=other.acq_datetime.dt.as_unit('ns').astype('int64').to_numpy()
        coords=xyz(reference.lat.to_numpy(),reference.lon.to_numpy())
        other_coords=xyz(other.lat.to_numpy(),other.lon.to_numpy())
        delta=int(temporal_hours*3.6e12);chord=2*EARTH_KM*np.sin(spatial_km/(2*EARTH_KM))
        dates=other.acq_datetime.dt.floor('D')
        for _,indices in other.groupby(dates).indices.items():
            indices=np.asarray(indices)
            lo=np.searchsorted(ref_time,other_time[indices].min()-delta,side='left')
            hi=np.searchsorted(ref_time,other_time[indices].max()+delta,side='right')
            if lo==hi:continue
            neighbours=cKDTree(coords[lo:hi]).query_ball_point(other_coords[indices],chord+1e-9)
            for index,near in zip(indices,neighbours):
                near=np.asarray(near,dtype=np.int64)+lo
                near=near[np.abs(ref_time[near]-other_time[index])<=delta]
                if not len(near):continue
                matched_other[index]=True;matched_reference[near]=True
                events=set(labels[near]);supported_events.update(events);ambiguous+=len(events)>1
    core_events=set(labels[core])
    return {'reference_core_detections':int(core.sum()),'noaa20_core_detections':len(other),
      'reference_core_point_support_fraction':float(matched_reference[core].mean()) if core.any() else None,
      'noaa20_point_match_fraction':float(matched_other.mean()) if len(other) else None,
      'core_candidate_events':len(core_events),'core_candidates_with_noaa20_support':len(core_events&supported_events),
      'noaa20_points_matching_multiple_candidates':int(ambiguous),
      'tolerance_km':spatial_km,'tolerance_hours':temporal_hours,
      'interpretation':'Co-detection agreement only. Different overpasses and detection sensitivity; not event precision/recall or incident ground truth.'}


def validate(region):
    tick=time.monotonic()
    catalogs=[]
    for report_path in sorted((ROOT/'data/events'/region).glob('*/*/report.json')):
        report=json.loads(report_path.read_text());directory=report_path.parent
        events=pd.read_parquet(directory/'events.parquet')
        members=pd.read_parquet(directory/'memberships.parquet')
        daily=pd.read_parquet(directory/'daily.parquet')
        checks=audit_catalog(events,members,daily,report['selection_audit']['included_detections'],report['config']['temporal_hours'])
        catalogs.append({'path':str(directory.relative_to(ROOT)),'input_fingerprint':report['input_fingerprint'],'checks':checks,'candidate_events':len(events)})
    if not catalogs:raise ValueError(f'Build {region} catalogues first.')
    reference,selection=load_points(region,'Suomi-NPP')
    begin,end=(pd.Timestamp(x,tz='UTC') for x in WINDOWS[region])
    # Identical padded input across every parameter setting, including events
    # crossing Dec/Jan. These bounded windows can still censor longer chains.
    reference=reference[reference.acq_datetime.between(begin-pd.Timedelta(hours=72),end+pd.Timedelta(hours=72),inclusive='left')].reset_index(drop=True)
    core=((reference.acq_datetime>=begin)&(reference.acq_datetime<end)).to_numpy()
    baseline,_=cluster_points(reference,Config(2,48))
    rows=[]
    for radius in [1.,2.,3.]:
        for hours in [24.,48.,72.]:
            labels,performance=(baseline,{}) if (radius,hours)==(2.,48.) else cluster_points(reference,Config(radius,hours))
            unique,counts=np.unique(labels[core],return_counts=True)
            row={'spatial_km':radius,'temporal_hours':hours,'core_detections':int(core.sum()),'padded_detections':len(reference),
              'candidates_intersecting_core':len(unique),'single_detection_core_fragments':int((counts==1).sum()),
              'largest_core_component_share':float(counts.max()/counts.sum()) if len(counts) else None,
              'partition_agreement_with_default_ARI':float(adjusted_rand_score(baseline[core],labels[core])) if core.any() else None,
              'performance':performance}
            rows.append(row)
            print(f'{region} sensitivity {radius:g}km/{hours:g}h: {len(unique):,} candidates',flush=True)
    monotonic=all(rows[i*3+j]['candidates_intersecting_core']>=rows[i*3+j+1]['candidates_intersecting_core'] for i in range(3) for j in range(2)) and all(rows[i*3+j]['candidates_intersecting_core']>=rows[(i+1)*3+j]['candidates_intersecting_core'] for i in range(2) for j in range(3))
    if not monotonic:raise AssertionError('Increasing graph-link thresholds must not increase component count.')
    noaa20,noaa_audit=load_points(region,'NOAA-20')
    noaa20=noaa20[(noaa20.acq_datetime>=begin)&(noaa20.acq_datetime<end)].reset_index(drop=True)
    agreement=support(reference,baseline,noaa20,core)
    result={'region':region,'catalog_audits':catalogs,'validation_window_utc':[begin.isoformat(),end.isoformat()],
      'sensitivity_padding_hours':72,'reference_selection_audit':selection,'independent_satellite_selection_audit':noaa_audit,
      'threshold_sensitivity':rows,'threshold_monotonicity_passed':monotonic,'noaa20_co_detection':agreement,
      'seconds':round(time.monotonic()-tick,2),
      'limits':['Sensitivity windows are fixed diagnostic samples, not all years; 72-hour padding may still censor long connections.',
       'ARI compares partitions to the default, not to true fires. Candidates intersecting a window are not ignition counts.',
       'NOAA-20 is excluded from S-NPP clustering. Co-detection is not independent official-incident accuracy validation.',
       'The 2km/48h default is an unoptimized research baseline; no universal ecological threshold has been established.']}
    path=ROOT/f'data/events/{region}/validation.json';path.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(f'{region}: validation saved ({result["seconds"]}s)',flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('regions',nargs='*',default=list(WINDOWS))
    for region in parser.parse_args().regions:
        if region not in WINDOWS:raise ValueError('Unknown region')
        validate(region)
