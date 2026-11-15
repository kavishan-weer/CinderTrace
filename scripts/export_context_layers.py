"""Prepare bounded, attributed OSM geographic context snapshots for the observatory.

Requests are read-only; response remarks and incomplete geometry are rejected, never
represented as empty data. Site-centre proximity is not an impact assessment.
"""
import argparse,concurrent.futures,gzip,hashlib,json,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from shapely.geometry import shape,mapping,Point,Polygon,LineString
from shapely.ops import polygonize,unary_union
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'tmp/context';OUT=ROOT/'web/site-public/context'
ENDPOINTS=['https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter']
KINDS={'hospital':'health','school':'education','fire_station':'response'}
def request(query,path):
 if path.exists():
  result=json.loads(path.read_bytes())
  if 'elements' in result and not result.get('remark'):return result,'cached response'
 for endpoint in ENDPOINTS:
  for method in ['POST','GET']:
   args=['curl','--fail','--silent','--show-error','--compressed','--max-time','110','--user-agent','CinderTraceResearch/1.0 (public geographic-context extract)',endpoint,'--data-urlencode','data='+query,'-o',str(path)+'.partial']
   if method=='GET':args.insert(1,'--get')
   proc=subprocess.run(args,capture_output=True,text=True,timeout=115)
   try:
    result=json.loads(Path(str(path)+'.partial').read_bytes())
    if proc.returncode not in [0,18,56] or result.get('remark') or 'elements' not in result:raise ValueError(result.get('remark') or proc.stderr[:180])
    Path(str(path)+'.partial').replace(path);return result,endpoint
   except (ValueError,OSError) as e:print('Source retry:',endpoint,method,(str(e)+' / '+proc.stderr)[:240],flush=True)
 raise RuntimeError('No complete OSM response for '+path.name)
def protected_geometry(element):
 try:
  if element['type']=='way':
   pts=[(p['lon'],p['lat']) for p in element.get('geometry',[])]
   return Polygon(pts) if len(pts)>=4 and pts[0]==pts[-1] else None
  lines={'outer':[],'inner':[]}
  for member in element.get('members',[]):
   pts=[(p['lon'],p['lat']) for p in member.get('geometry',[]) if 'lon' in p]
   if len(pts)>1:lines['inner' if member.get('role')=='inner' else 'outer'].append(LineString(pts))
  outer=unary_union(list(polygonize(unary_union(lines['outer']))))
  inner=unary_union(list(polygonize(unary_union(lines['inner'])))) if lines['inner'] else None
  return outer.difference(inner) if inner is not None else outer
 except Exception:return None

def build(region):
 rid=region['id'];w,s,e,n=region['bbox'];bbox=f'({s},{w},{n},{e})'
 query=f'[out:json][timeout:60];(nwr[amenity~"^(hospital|fire_station)$"]{bbox};node[place~"^(city|town)$"]{bbox};);out center;'
 facilities,endpoint=request(query,RAW/f'{rid}-sites-v2.json')
 query2=f'[out:json][timeout:80];(way[leisure=nature_reserve]{bbox};relation[leisure=nature_reserve]{bbox};way[boundary=national_park]{bbox};relation[boundary=national_park]{bbox};way[boundary=protected_area][protect_class=2]{bbox};relation[boundary=protected_area][protect_class=2]{bbox};);out geom;'
 parks,park_endpoint=request(query2,RAW/f'{rid}-parks-v2.json')
 boundary=json.loads((ROOT/f'web/site-public/ready/{rid}/boundary.json').read_bytes())
 region_shape=unary_union([shape(f['geometry']) for f in boundary['features']])
 features=[];seen=set();skip=0
 for element in facilities['elements']:
  tags=element.get('tags',{});centre=element.get('center',element)
  if 'lon' not in centre or 'lat' not in centre:continue
  point=Point(centre['lon'],centre['lat'])
  if not region_shape.covers(point):continue
  key=f"{element['type']}/{element['id']}"
  if key in seen:continue
  seen.add(key);kind=KINDS.get(tags.get('amenity'),'settlement')
  features.append({'type':'Feature','id':key,'properties':{'id':key,'name':tags.get('name:en') or tags.get('name') or {'health':'Mapped hospital','education':'Mapped school','response':'Mapped fire station','settlement':'Mapped settlement'}[kind],'kind':kind,'coordinate_basis':'mapped site centre','url':'https://www.openstreetmap.org/'+key},'geometry':mapping(point)})
 for element in parks['elements']:
  key=f"{element['type']}/{element['id']}"
  if key in seen:continue
  geometry=protected_geometry(element)
  if geometry is None or geometry.is_empty or not geometry.is_valid:skip+=1;continue
  geometry=geometry.intersection(region_shape)
  if geometry.is_empty or geometry.geom_type not in ['Polygon','MultiPolygon']:continue
  geometry=geometry.simplify(.0005,preserve_topology=True)
  tags=element.get('tags',{});seen.add(key)
  features.append({'type':'Feature','id':key,'properties':{'id':key,'name':tags.get('name:en') or tags.get('name') or 'Mapped protected area','kind':'protected','coordinate_basis':'OSM boundary, simplified for display','url':'https://www.openstreetmap.org/'+key},'geometry':mapping(geometry)})
 counts={k:sum(f['properties']['kind']==k for f in features) for k in ['health','education','response','settlement','protected']}
 payload={'version':1,'region':rid,'type':'FeatureCollection','features':features,'provenance':{'provider':'OpenStreetMap contributors','license':'ODbL 1.0','attribution_url':'https://www.openstreetmap.org/copyright','retrieved_utc':datetime.now(timezone.utc).isoformat(),'osm_base':facilities.get('osm3s',{}).get('timestamp_osm_base'),'protected_osm_base':parks.get('osm3s',{}).get('timestamp_osm_base'),'endpoint':endpoint,'protected_endpoint':park_endpoint,'query':query,'protected_query':query2,'raw_sha256':hashlib.sha256((RAW/f'{rid}-sites-v2.json').read_bytes()).hexdigest(),'protected_raw_sha256':hashlib.sha256((RAW/f'{rid}-parks-v2.json').read_bytes()).hexdigest(),'excluded_incomplete_protected_geometries':skip,'counts':counts,'spatial_support':'Mapped centres and clipped mapped protected-area boundaries. Geometry simplified by 0.0005 degrees for display. No population or damage estimates.','temporal_support':'Current OSM snapshot, not historical inventories for the selected fire year.','completeness':'Community mapping may be incomplete; unmapped facilities are unknown.'}}
 target=OUT/f'{rid}.json.gz';target.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode(),mtime=0));print(rid,counts,'bytes',target.stat().st_size,flush=True)
 return {'region':rid,**counts,'path':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--region',choices=['lk','ca','nsw']);args=ap.parse_args();RAW.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((ROOT/'web/site-public/ready/manifest.json').read_bytes());regions=[r for r in manifest['regions'] if not args.region or r['id']==args.region]
 results=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for result in pool.map(build,regions):results.append(result)
 (RAW/'context-receipt.json').write_text(json.dumps(results,indent=2))
