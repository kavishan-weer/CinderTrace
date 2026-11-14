"""Cache public agency case perimeters and provenance. Explicit online fetch only.

python -m ml.incident_references --fetch
"""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import shutil
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import numpy as np
import shapely
from shapely.geometry import Polygon,mapping
from shapely.ops import unary_union

from .events import ROOT

SPEC=pathlib.Path(__file__).with_name('incident_cases.json')
CACHE=ROOT/'data/validation/incident_references'
DECODE='esri-oriented-rings-v1'


def decode_rings(rings):
    """Esri JSON: clockwise shells and counterclockwise holes; retain islands.

    Decode provider ring semantics before geometry repair. Some agency GeoJSON
    exports misclassify holes as independent nested polygons.
    """
    shells=[];holes=[];zero_area=0
    for ring in rings:
        xy=np.asarray(ring,float)
        if xy.ndim!=2 or xy.shape[1]<2:raise ValueError('Invalid agency ring coordinates.')
        xy=xy[:,:2]
        if len(xy)<4 or not np.isfinite(xy).all() or (np.abs(xy[:,0])>180).any() or (np.abs(xy[:,1])>90).any():
            raise ValueError('Agency rings must be finite WGS84 longitude/latitude coordinates.')
        if not np.array_equal(xy[0],xy[-1]):xy=np.vstack([xy,xy[0]])
        signed=float(np.sum(xy[:-1,0]*xy[1:,1]-xy[1:,0]*xy[:-1,1])/2)
        polygon=Polygon(xy)
        if abs(signed)<1e-13:
            if shapely.make_valid(polygon).area>1e-12:raise ValueError('Ambiguous nonempty ring orientation.')
            zero_area+=1;continue
        if signed<0:shells.append({'ring':xy,'cover':shapely.make_valid(polygon),'holes':[]})
        else:holes.append((xy,polygon))
    if not shells:raise ValueError('No clockwise agency exterior ring.')
    containment_repairs=0
    for ring,hole in holes:
        possible=[s for s in shells if s['cover'].area>hole.area and shapely.covers(s['cover'],hole)]
        if not possible:
            possible=[s for s in shells if s['cover'].area>hole.area and shapely.covers(s['cover'],hole.representative_point())]
            containment_repairs+=1
        if not possible:raise ValueError('Agency interior ring is not contained by an exterior.')
        min(possible,key=lambda s:s['cover'].area)['holes'].append(ring)
    polygons=[Polygon(s['ring'],s['holes']) for s in shells]
    repairs=sum(not p.is_valid for p in polygons)
    valid=unary_union([shapely.make_valid(p) for p in polygons])
    def parts(g):
        if g.geom_type in ['Polygon','MultiPolygon']:return [g]
        return [p for child in getattr(g,'geoms',[]) for p in parts(child)]
    geometry=unary_union(parts(valid))
    if geometry.is_empty or not geometry.is_valid:raise ValueError('Decoded reference has no valid polygon area.')
    return geometry,{'decoder':DECODE,'exterior_rings':len(shells),'interior_rings':len(holes),
        'zero_area_rings_discarded':zero_area,'shell_hole_repairs':repairs,'containment_repairs':containment_repairs}


def fetch_json(url):
    request=Request(url,headers={'User-Agent':'EMBERLINE-research-case-audit/1.0'})
    with urlopen(request,timeout=120) as response:body=response.read()
    data=json.loads(body)
    if 'error' in data:raise ValueError(f'Agency service error: {data["error"]}')
    return data,body


def fetch_case(case,source,refresh=False):
    target=CACHE/f'{case["id"]}.geojson';meta=CACHE/f'{case["id"]}.provenance.json'
    if target.exists() and meta.exists() and json.loads(meta.read_text()).get('geometry_decode')==DECODE and not refresh:
        print(f'{case["id"]}: cached',flush=True);return
    params={'f':'json','where':case['where'],'outFields':'*','returnGeometry':'true',
            'outSR':'4326','maxAllowableOffset':'0.0001'}
    url=source['layer']+'/query?'+urlencode(params)
    data,body=fetch_json(url)
    if data.get('exceededTransferLimit') or data.get('properties',{}).get('exceededTransferLimit'):
        raise ValueError('Agency response was truncated; do not validate an incomplete perimeter.')
    features=data.get('features',[])
    if not features or any(f.get('geometry') is None for f in features):
        raise ValueError(f'{case["id"]}: missing reference polygon')
    if target.exists() and meta.exists():
        previous=CACHE/'previous-geojson-export';previous.mkdir(exist_ok=True)
        if not (previous/target.name).exists():shutil.copyfile(target,previous/target.name);shutil.copyfile(meta,previous/meta.name)
    normalized=[];diagnostics=[];fallback_reason=None
    try:
        decoded=[decode_rings(feature['geometry']['rings']) for feature in features]
    except ValueError as error:
        # Generalizing rings independently can break shell/hole containment.
        # Retain the rejected response and retry the same case at full resolution.
        (CACHE/f'{case["id"]}.rejected-generalized.agency.json').write_bytes(body)
        fallback_reason=str(error);params.pop('maxAllowableOffset',None)
        url=source['layer']+'/query?'+urlencode(params);data,body=fetch_json(url)
        if data.get('exceededTransferLimit'):raise ValueError('Full-resolution reference was truncated.')
        features=data.get('features',[])
        if not features:raise ValueError('Full-resolution reference is missing.')
        decoded=[decode_rings(feature['geometry']['rings']) for feature in features]
    for feature,(geometry,notes) in zip(features,decoded):
        diagnostics.append(notes)
        normalized.append({'type':'Feature','properties':feature['attributes'],'geometry':mapping(geometry)})
    geojson=json.dumps({'type':'FeatureCollection','features':normalized},separators=(',',':')).encode()
    native=CACHE/f'{case["id"]}.agency.json';native.write_bytes(body);target.write_bytes(geojson)
    record={'case':case,'source':source,'query_url':url,'query_parameters':params,
        'retrieved_utc':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(geojson).hexdigest(),
        'native_file':native.name,'native_sha256':hashlib.sha256(body).hexdigest(),'geometry_decode':DECODE,'decode_diagnostics':diagnostics,
        'full_resolution_fallback_reason':fallback_reason,
        'features':len(features),'geometry_note':f"Native agency WGS84 rings; generalization {params.get('maxAllowableOffset','none')} degree; decoded by exterior/interior orientation before repair; not survey-grade."}
    meta.write_text(json.dumps(record,indent=2))
    print(f'{case["id"]}: {len(features)} feature(s), {len(body):,} bytes',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fetch',action='store_true');parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    if not args.fetch:parser.error('Use --fetch to authorize downloading public reference files.')
    spec=json.loads(SPEC.read_text());CACHE.mkdir(parents=True,exist_ok=True)
    for key,source in spec['sources'].items():
        output=CACHE/f'{key}-layer.json'
        if not output.exists() or args.refresh:
            _,body=fetch_json(source['layer']+'?f=pjson');output.write_bytes(body)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        jobs=[executor.submit(fetch_case,case,spec['sources'][case['source']],args.refresh) for case in spec['cases']]
        for job in jobs:job.result()
    (CACHE/'selection.json').write_text(json.dumps(spec,indent=2))


if __name__=='__main__':main()
