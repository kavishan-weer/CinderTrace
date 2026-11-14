"""Read-only local access to built, single-satellite event candidate catalogues."""
import json
import re
from functools import lru_cache

import numpy as np
import pandas as pd
import shapely

from ml.events import ROOT, STREAMS, provenance, file_sha

SATELLITES=['Suomi-NPP','Aqua','Terra']


@lru_cache(maxsize=3)
def current_fingerprint(region):
    return provenance(region)[2]


@lru_cache(maxsize=3)
def catalog(region,satellite):
    if region not in ['lk','ca','nsw'] or satellite not in SATELLITES:raise ValueError('Choose a supported event region and satellite.')
    fingerprint=current_fingerprint(region);matches=[]
    for path in (ROOT/f'data/events/{region}/{STREAMS[satellite]}').glob('*/report.json'):
        report=json.loads(path.read_text())
        if report['input_fingerprint']==fingerprint and report['config']['spatial_km']==2 and report['config']['temporal_hours']==48:matches.append((path.parent,report))
    if len(matches)!=1:raise ValueError('Build the current event catalogue first: python -m ml.events '+region+' --satellites "'+satellite+'"')
    path,report=matches[0]
    events=pd.read_parquet(path/'events.parquet')
    points=pd.read_parquet(path/'memberships.parquet',columns=['event_id','acq_datetime','lat','lon','sub','frp','footprint_h3'])
    links_path=ROOT/f'data/validation/incident_assessment/{region}-default-links.csv'
    links=pd.read_csv(links_path) if satellite=='Suomi-NPP' and links_path.exists() else pd.DataFrame()
    scores_path=ROOT/f'data/validation/incident_assessment/{region}-case-sensitivity.csv'
    scores=pd.read_csv(scores_path) if satellite=='Suomi-NPP' and scores_path.exists() else pd.DataFrame()
    if len(scores):scores=scores[(scores.spatial_km==2)&(scores.temporal_hours==48)&(scores.boundary_buffer_km==0)]
    # Reference labels are usable only with the exact audited membership snapshot.
    audit_path=ROOT/f'data/validation/incident_assessment/{region}-assessment.json'
    identity=json.loads(audit_path.read_text())['identity'] if audit_path.exists() else {}
    if identity.get('input_fingerprint')!=fingerprint or identity.get('catalog')!=str(path.relative_to(ROOT)) or identity.get('memberships_sha256')!=file_sha(path/'memberships.parquet'):
        links=pd.DataFrame();scores=pd.DataFrame()
    return events,points,report,links,scores


def records(frame):
    return json.loads(frame.to_json(orient='records',date_format='iso',double_precision=6))


def inputs(request):
    region=request.get('region');satellite=request.get('satellite','Suomi-NPP')
    if region not in ['lk','ca','nsw'] or satellite not in SATELLITES:raise ValueError('Choose a supported event region and satellite.')
    return region,satellite


def query_events(request,geometry=None):
    region,satellite=inputs(request)
    month=request.get('month')
    if not isinstance(month,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month):raise ValueError('Choose a valid event month.')
    include=request.get('include_singletons',False)
    if type(include) is not bool:raise ValueError('Invalid singleton filter.')
    sub=request.get('sub')
    if sub is not None and (type(sub) is not int or sub<0):raise ValueError('Invalid administrative selection.')
    if geometry is not None and sub is not None:raise ValueError('Choose a custom area or administrative area.')
    events,points,report,_,scores=catalog(region,satellite)
    begin=pd.Timestamp(month+'-01',tz='UTC');end=begin+pd.offsets.MonthBegin(1)
    selected=points[(points.acq_datetime>=begin)&(points.acq_datetime<end)]
    if sub is not None:
        definitions=json.loads((ROOT/f'data/boundaries/{region}_subs.geojson').read_text())['features']
        if sub not in {f['properties']['id'] for f in definitions}:raise ValueError('Invalid administrative selection.')
        selected=selected[selected['sub']==sub]
    if geometry is not None:
        shapely.prepare(geometry)
        selected=selected[shapely.covers(geometry,shapely.points(selected.lon.to_numpy(),selected.lat.to_numpy()))]
    totals=selected.groupby('event_id').size().rename('selected_month_detections')
    matched=events.merge(totals,on='event_id',how='inner')
    hidden=int(matched.singleton.sum()) if not include else 0
    if not include:matched=matched[~matched.singleton]
    # Representative markers are real selected-month/AOI observations, not a
    # potentially offshore centroid or an inferred event perimeter.
    representatives=selected.sort_values(['frp','acq_datetime'],ascending=[False,True],na_position='last').drop_duplicates('event_id')
    matched=matched.merge(representatives[['event_id','lat','lon']].rename(columns={'lat':'marker_lat','lon':'marker_lon'}),on='event_id',validate='one_to_one')
    matched=matched.sort_values(['selected_month_detections','event_id'],ascending=[False,True])
    total=len(matched);matched=matched.head(2000)
    columns=['event_id','start_utc','end_utc','observed_span_hours','observed_dates','detection_count','selected_month_detections','peak_detection_frp_mw','singleton','multi_date_support','touches_region_grid_edge','touches_archive_time_edge','end_in_latest_archive_month','long_chain_caution','possible_persistent_source','marker_lat','marker_lon']
    validation=records(scores[['case_name','material_fragments','dominant_reference_share']]) if len(scores) else []
    return {'candidates':records(matched[columns]),'total':total,'shown':len(matched),'hidden_singletons':hidden,
        'satellite':satellite,'month':month,'scope':'Candidates with an actual detection in the selected month and area; candidate metrics cover the full regional candidate history.',
        'filters':'Vegetation / individual nominal+high / 2 km and 48 h. Existing candidates are selected, never reclustered by the area.',
        'input_fingerprint':report['input_fingerprint'],'validation':validation,
        'archive_first_utc':points.acq_datetime.min().isoformat() if len(points) else None,
        'archive_last_utc':points.acq_datetime.max().isoformat() if len(points) else None}


def event_detail(request):
    region,satellite=inputs(request)
    event_id=request.get('event_id')
    if not isinstance(event_id,str) or len(event_id)>150:raise ValueError('Choose a candidate from the map or list.')
    events,points,_,links,scores=catalog(region,satellite)
    event=events[events.event_id==event_id]
    if len(event)!=1:raise ValueError('This candidate is not in the selected satellite catalogue.')
    selected=points[points.event_id==event_id].copy()
    selected['date']=selected.acq_datetime.dt.strftime('%Y-%m-%d')
    selected['valid_frp']=np.where(np.isfinite(selected.frp)&(selected.frp>=0),selected.frp,np.nan)
    daily=selected.groupby('date',as_index=False).agg(detections=('event_id','size'),peak_detection_frp_mw=('valid_frp','max'))
    day=request.get('day','all')
    if day!='all' and (not isinstance(day,str) or day not in set(selected.date)):raise ValueError('Choose an observed candidate date.')
    footprint=selected if day=='all' else selected[selected.date==day]
    hexes=sorted(footprint.footprint_h3.unique().tolist())
    reference_links=[]
    if len(links):
        evidence=links[links.event_id==event_id]
        if len(evidence):
            evidence=evidence.merge(scores[['case_id','case_name','dominant_reference_share']],on='case_id',how='left',validate='many_to_one')
            reference_links=records(evidence[['case_id','case_name','reference_points','material_reference_association','dominant_for_reference','reference_fragmentation_caution','shared_candidate_review','dominant_reference_share']])
    return {'candidate':records(event)[0],'daily':records(daily),'footprint_hexes':hexes,'footprint_day':day,
        'footprint_count':len(hexes),'reference_links':reference_links,
        'cautions':['Estimated detection cluster, not a confirmed incident. Nearby fires can merge; observation gaps and changing fronts can split one fire.',
        'Duration is first-to-last observed detection, not continuous burning or ignition-to-extinction time.',
        'Peak fire power is the largest individual detection FRP, not whole-event power. Sampled H3 footprint is not burned area or a validated perimeter.']}
