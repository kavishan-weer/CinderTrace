"""Compare full-archive S-NPP components with cached, fixed agency case samples.

python -m ml.assess_incidents [ca nsw lk]
No downloads, threshold tuning, incident accuracy or false-positive-rate claim.
"""
import argparse
import hashlib
import itertools
import json
import math
import pathlib
import time

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

from .events import ROOT, EARTH_KM, Config, cluster_points, provenance, file_sha
from .incident_references import CACHE, SPEC

OUT=ROOT/'data/validation/incident_assessment'
METHOD='agency-case-audit-v1'


def project_local(lon,lat,lon0,lat0):
    """Spherical azimuthal-equidistant projection, output km (regional only)."""
    lam,phi=np.radians(lon),np.radians(lat);a,b=math.radians(lon0),math.radians(lat0)
    dl=lam-a;cosc=np.clip(math.sin(b)*np.sin(phi)+math.cos(b)*np.cos(phi)*np.cos(dl),-1,1)
    c=np.arccos(cosc);s=np.sin(c)
    k=np.divide(c,s,out=np.ones_like(c),where=np.abs(s)>1e-12)
    return EARTH_KM*k*np.cos(phi)*np.sin(dl),EARTH_KM*k*(math.cos(b)*np.sin(phi)-math.sin(b)*np.cos(phi)*np.cos(dl))


def read_case(case,sources):
    path=CACHE/f'{case["id"]}.geojson';meta=CACHE/f'{case["id"]}.provenance.json'
    if not path.exists() or not meta.exists():raise ValueError('Fetch reference perimeters first: python -m ml.incident_references --fetch')
    record=json.loads(meta.read_text())
    if file_sha(path)!=record['sha256']:raise ValueError('Reference SHA-256 mismatch.')
    if record.get('native_file') and file_sha(CACHE/record['native_file'])!=record['native_sha256']:
        raise ValueError('Native agency response SHA-256 mismatch.')
    if record['case']!=case:raise ValueError('Case selection changed; explicitly refresh references.')
    features=json.loads(path.read_text())['features'];source=sources[case['source']]
    identifiers={str(f['properties'][source['id_field']]) for f in features}
    if len(identifiers)!=1:raise ValueError('Reference query returned more than one agency incident identifier.')
    geometries=[shape(f['geometry']) for f in features]
    repaired=any(not g.is_valid for g in geometries)
    valid_geometry=unary_union([shapely.make_valid(g) for g in geometries])
    def polygon_parts(g):
        if g.geom_type in ['Polygon','MultiPolygon']:return [g]
        return [part for child in getattr(g,'geoms',[]) for part in polygon_parts(child)]
    geometry=unary_union(polygon_parts(valid_geometry))
    if geometry.is_empty or geometry.geom_type not in ['Polygon','MultiPolygon']:raise ValueError('Reference must have polygon area.')
    starts=[f['properties'].get(source['start_field']) for f in features]
    ends=[f['properties'].get(source['end_field']) for f in features]
    if any(type(v) not in [int,float] or not np.isfinite(v) for v in starts+ends):
        raise ValueError(f'{case["id"]}: missing agency dates; no year-only substitution allowed.')
    start=pd.to_datetime(min(starts),unit='ms',utc=True);end=pd.to_datetime(max(ends),unit='ms',utc=True)
    if start>end:raise ValueError('Agency dates are reversed.')
    return {**case,'geometry':geometry,'start':start,'end':end,'agency_identifier':next(iter(identifiers)),
            'sha256':record['sha256'],'geometry_repaired':repaired,
            'zero_area_remnants_discarded':valid_geometry.geom_type=='GeometryCollection',
            'source_geometry_decode':record.get('geometry_decode','agency_geojson'),
            'decode_diagnostics':record.get('decode_diagnostics',[]),
            'native_sha256':record.get('native_sha256'),
            'relative_planar_area_change_after_repair':float((geometry.area-sum(g.area for g in geometries))/sum(g.area for g in geometries)) if sum(g.area for g in geometries)>0 else None,
            'source_url':record['query_url'],'date_meaning':source['date_meaning']}


def match_indices(points,geometry,start,end,buffer_km=0.,date_padding_days=1):
    if buffer_km<0 or date_padding_days<0:raise ValueError('Tolerances must be nonnegative.')
    begin=start.floor('D')-pd.Timedelta(days=date_padding_days)
    stop=end.floor('D')+pd.Timedelta(days=date_padding_days+1)
    time_mask=(points.acq_datetime>=begin)&(points.acq_datetime<stop)
    indices=np.flatnonzero(time_mask.to_numpy())
    if not len(indices):return indices
    subset=points.iloc[indices]
    if buffer_km:
        center=geometry.centroid;lon0,lat0=center.x,center.y
        projected=shapely.transform(geometry,lambda xy:np.column_stack(project_local(xy[:,0],xy[:,1],lon0,lat0)))
        target=projected.buffer(buffer_km)
        x,y=project_local(subset.lon.to_numpy(),subset.lat.to_numpy(),lon0,lat0)
    else:
        target=geometry;x,y=subset.lon.to_numpy(),subset.lat.to_numpy()
    shapely.prepare(target)
    covered=shapely.covers(target,shapely.points(x,y))
    return indices[np.asarray(covered)]


def score_case(case,indices,labels,global_sizes):
    components,counts=np.unique(labels[indices],return_counts=True)
    n=len(indices);threshold=max(3,int(math.ceil(.01*n)))
    if not n:
        return {'case_id':case['id'],'case_name':case['name'],'case_kind':case['kind'],'reference_points':0,
            'candidate_fragments':0,'material_fragments':0,'material_min_points':threshold,'dominant_reference_share':None,
            'one_point_reference_fragments':0,'global_singletons':0,'dominant_candidate_global_points':None,'dominant_candidate_reference_fraction':None},{}
    dominant=int(components[np.argmax(counts)]);largest=int(counts.max())
    return {'case_id':case['id'],'case_name':case['name'],'case_kind':case['kind'],'reference_points':n,
        'candidate_fragments':len(components),'material_fragments':int((counts>=threshold).sum()),'material_min_points':threshold,
        'dominant_reference_share':largest/n,'one_point_reference_fragments':int((counts==1).sum()),
        'global_singletons':int((global_sizes[components]==1).sum()),'dominant_candidate_global_points':int(global_sizes[dominant]),
        'dominant_candidate_reference_fraction':largest/int(global_sizes[dominant])},dict(zip(components[counts>=threshold].tolist(),counts[counts>=threshold].tolist()))


def merge_review(cases,indices_by_case,material_by_case):
    result=[]
    for a,b in itertools.combinations(cases,2):
        shared=set(material_by_case[a['id']])&set(material_by_case[b['id']])
        if not shared:continue
        overlap=a['geometry'].intersection(b['geometry']).area>1e-10
        ambiguous=len(np.intersect1d(indices_by_case[a['id']],indices_by_case[b['id']]))
        for component in sorted(shared):
            result.append({'case_a':a['id'],'case_b':b['id'],'component':int(component),
             'points_a':material_by_case[a['id']][component],'points_b':material_by_case[b['id']][component],
             'reference_polygons_overlap':bool(overlap),'points_associated_with_both_references':ambiguous,
             'interpretation':'Shared material candidate; review merging/agency-complex/overlapping-reference ambiguity. Not automatically a confirmed merge error.'})
    return result


def annotate_links(links,primary_scores):
    """Evidence labels for later UI use; never an official-incident assignment."""
    if links.empty:
        result=links.copy()
        for key in ['case_kind','material_fragments','material_min_points','material_reference_association','dominant_for_reference','candidate_material_reference_count','shared_candidate_review','reference_fragmentation_caution','association_note']:
            result[key]=pd.Series(dtype=object)
        return result
    result=links.merge(primary_scores[['case_id','case_kind','material_fragments','material_min_points']],on='case_id',validate='many_to_one')
    result['material_reference_association']=result.reference_points>=result.material_min_points
    result['dominant_for_reference']=result.reference_points==result.groupby('case_id').reference_points.transform('max')
    result['candidate_material_reference_count']=result.event_id.map(result.groupby('event_id').material_reference_association.sum()).astype(int)
    result['shared_candidate_review']=result.candidate_material_reference_count>1
    result['reference_fragmentation_caution']=result.material_fragments>1
    result['association_note']='Spatial/date association only; not an official incident identity or an event accuracy probability.'
    return result


def current_catalog(region):
    fingerprint=provenance(region)[2]
    matching=[]
    for report_path in (ROOT/f'data/events/{region}/snpp').glob('*/report.json'):
        report=json.loads(report_path.read_text());config=report['config']
        if report['input_fingerprint']==fingerprint and config['spatial_km']==2 and config['temporal_hours']==48:
            matching.append(report_path.parent)
    if len(matching)!=1:raise ValueError(f'{region}: expected exactly one current 2km/48h S-NPP catalogue. Build ml.events first.')
    path=matching[0]
    columns=['event_id','detection_id','acq_datetime','lat','lon','sub']
    points=pd.read_parquet(path/'memberships.parquet',columns=columns).reset_index(drop=True)
    return points,path,{'catalog':str(path.relative_to(ROOT)),'input_fingerprint':fingerprint,'memberships_sha256':file_sha(path/'memberships.parquet')}


def locality_audit(spec):
    points,path,identity=current_catalog('lk')
    subs=json.loads((ROOT/'data/boundaries/lk_subs.geojson').read_text())['features']
    ids={f['properties']['name']:f['properties']['id'] for f in subs}
    result=[]
    for case in spec['locality_cases']:
        start=pd.Timestamp(case['date_local'],tz='Asia/Colombo').tz_convert('UTC')-pd.Timedelta(days=1)
        stop=start+pd.Timedelta(days=3)
        matched=points[(points['sub']==ids[case['district']])&(points.acq_datetime>=start)&(points.acq_datetime<stop)]
        result.append({**case,'window_start_utc':start.isoformat(),'window_end_exclusive_utc':stop.isoformat(),
            'district_detections':len(matched),'district_candidates':matched.event_id.nunique(),
            'candidate_ids':sorted(matched.event_id.unique().tolist()),
            'assessment':'District/date context only; no perimeter or ignition coordinates. Nearby candidates are not verified matches, and no detection does not disprove the report.'})
    return {'region':'lk','identity':identity,'cases':result,'decision':'No geometric incident accuracy or threshold tuning from these locality-only records.'}


def assess_region(region,spec):
    tick=time.monotonic();points,catalog,identity=current_catalog(region)
    cases=[read_case(c,spec['sources']) for c in spec['cases'] if c['region']==region]
    matches={}
    for buffer in [0.,1.]:
        matches[buffer]={case['id']:match_indices(points,case['geometry'],case['start'],case['end'],buffer,1) for case in cases}
    labels_default=pd.factorize(points.event_id,sort=True)[0]
    scores=[];reviews=[]
    for radius in [1.,2.,3.]:
        for hours in [24.,48.,72.]:
            labels=labels_default if (radius,hours)==(2.,48.) else cluster_points(points,Config(radius,hours))[0]
            sizes=np.bincount(labels)
            for buffer in [0.,1.]:
                materials={}
                for case in cases:
                    score,material=score_case(case,matches[buffer][case['id']],labels,sizes)
                    scores.append({**score,'region':region,'spatial_km':radius,'temporal_hours':hours,'boundary_buffer_km':buffer,'date_padding_days':1})
                    materials[case['id']]=material
                for review in merge_review(cases,matches[buffer],materials):
                    reviews.append({**review,'region':region,'spatial_km':radius,'temporal_hours':hours,'boundary_buffer_km':buffer})
            print(f'{region}: full-archive case audit {radius:g}km/{hours:g}h complete',flush=True)
    default_details=[]
    for case in cases:
        indices=matches[0.][case['id']]
        for event_id,g in points.iloc[indices].groupby('event_id'):
            default_details.append({'case_id':case['id'],'event_id':event_id,'reference_points':len(g),
                'first_associated_utc':g.acq_datetime.min().isoformat(),'last_associated_utc':g.acq_datetime.max().isoformat()})
    provenance_cases=[{k:(v.isoformat() if isinstance(v,pd.Timestamp) else v) for k,v in case.items() if k!='geometry'} for case in cases]
    result={'method':METHOD,'region':region,'identity':identity,'cases':provenance_cases,'parameters':{
        'primary_spatial_buffer_km':0,'secondary_spatial_buffer_km':1,'date_padding_days':1,
        'material_fragment_rule':'at least max(3, ceil(1% of reference-associated detections))',
        'clustering_scope':'Entire current S-NPP regional archive; no per-incident or year truncation.'},
        'selection':spec['selection'],'seconds':round(time.monotonic()-tick,2),
        'limits':['Final agency perimeters and dates have uncertainty; containment is not extinction.',
        'Dominant-component share and association are descriptive, not incident precision/recall or perimeter accuracy.',
        'Merge review only covers these selected references; unmatched candidates have no false-positive label.',
        'No threshold was chosen by optimizing these cases. Large, documented cases do not validate small agricultural fires.']}
    OUT.mkdir(parents=True,exist_ok=True)
    score_frame=pd.DataFrame(scores)
    score_frame.to_csv(OUT/f'{region}-case-sensitivity.csv',index=False)
    primary=score_frame[(score_frame.spatial_km==2)&(score_frame.temporal_hours==48)&(score_frame.boundary_buffer_km==0)]
    detail_frame=pd.DataFrame(default_details,columns=['case_id','event_id','reference_points','first_associated_utc','last_associated_utc'])
    annotate_links(detail_frame,primary).to_csv(OUT/f'{region}-default-links.csv',index=False)
    pd.DataFrame(reviews,columns=['case_a','case_b','component','points_a','points_b','reference_polygons_overlap','points_associated_with_both_references','interpretation','region','spatial_km','temporal_hours','boundary_buffer_km']).to_csv(OUT/f'{region}-merge-review.csv',index=False)
    (OUT/f'{region}-assessment.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print(f'{region}: saved case audit ({result["seconds"]}s)',flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('regions',nargs='*',default=['ca','nsw','lk'])
    args=parser.parse_args();spec=json.loads(SPEC.read_text());OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'selection.json').write_text(json.dumps(spec,indent=2))
    for region in args.regions:
        if region=='lk':(OUT/'lk-context.json').write_text(json.dumps(locality_audit(spec),indent=2))
        elif region in ['ca','nsw']:assess_region(region,spec)
        else:raise ValueError('Unknown region')


if __name__=='__main__':main()
