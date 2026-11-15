"""Build attributed geographic-context layers from captured public-source responses.

Reproduction uses checksummed raw captures in tmp/context/verified; request receipts
retain exact official queries. No source inventory is treated as complete exposure
or as a historical inventory for a selected satellite year.
"""
import gzip,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from shapely.geometry import shape,mapping,Point
from shapely.ops import unary_union
from shapely import make_valid
ROOT=Path(__file__).resolve().parents[1];RAW=ROOT/'tmp/context/verified';OUT=ROOT/'web/site-public/context'
def read(name):return json.loads((RAW/(name+'.json')).read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_url(name):return read(name+'-request')['url']
def build(rid):
 boundary=json.loads((ROOT/f'web/site-public/ready/{rid}/boundary.json').read_bytes());mask=unary_union([shape(f['geometry']) for f in boundary['features']]);features=[];sources=[];hashes=[];excluded=0;repaired=0
 def source(kind,provider,url,licence,detail,source_date=None):
  sources.append({'kind':kind,'provider':provider,'url':url,'license':licence,'source_date':source_date,'status':'partial','detail':detail,'count':0})
 def add(identifier,name,kind,geometry,url,basis):
  nonlocal excluded,repaired
  if geometry is None or geometry.is_empty:return
  if not geometry.is_valid:
   geometry=make_valid(geometry);repaired+=1
   if geometry.geom_type=='GeometryCollection':geometry=unary_union([g for g in geometry.geoms if g.geom_type in ['Polygon','MultiPolygon']])
   if geometry.is_empty or not geometry.is_valid:excluded+=1;return
  if geometry.geom_type=='Point':
   if not mask.covers(geometry):return
  else:
   geometry=geometry.intersection(mask)
   if geometry.is_empty:return
   if geometry.geom_type not in ['Polygon','MultiPolygon']:excluded+=1;return
   geometry=geometry.simplify(.0005,preserve_topology=True)
  features.append({'type':'Feature','id':identifier,'properties':{'id':identifier,'name':str(name or 'Unnamed mapped place'),'kind':kind,'coordinate_basis':basis,'url':url},'geometry':mapping(geometry)})
 if rid=='lk':
  path=ROOT/'tmp/context/lk-facilities.json';data=json.loads(path.read_bytes());hashes.append(sha(path));base=data['osm3s']['timestamp_osm_base'];endpoint='https://www.openstreetmap.org/copyright'
  for e in data['elements']:
   tags=e.get('tags',{});kind={'hospital':'health','fire_station':'response'}.get(tags.get('amenity'))
   if not kind:continue
   p=e.get('center',e)
   if 'lon' not in p or 'lat' not in p:continue
   key=f"{e['type']}/{e['id']}";add('osm/'+key,tags.get('name:en') or tags.get('name') or ('Mapped hospital' if kind=='health' else 'Mapped fire station'),kind,Point(p['lon'],p['lat']),'https://www.openstreetmap.org/'+key,'OSM mapped site centre')
  for kind in ['health','response']:source(kind,'OpenStreetMap contributors',endpoint,'ODbL 1.0','Only published hospital or fire-station tags in the captured regional extract. Volunteer mapping can be incomplete; positions may be site centroids.',base[:10])
 else:
  for kind,name,name_field in [('health',rid+'-health','FACNAME' if rid=='ca' else 'generalname'),('response',rid+'-response','NAME' if rid=='ca' else 'stationnam')]:
   data=read(name);assert not data.get('exceededTransferLimit') and not data.get('error');hashes.append(sha(RAW/(name+'.json')));url=source_url(name)
   for f in data['features']:
    p=f['properties']
    if rid=='ca' and kind=='response' and p.get('FACILITY_STATUS')!='Active':continue
    if rid=='nsw' and kind=='health' and p.get('operationalstatus')!=1:continue
    identifier=p.get('OBJECTID',p.get('objectid',p.get('fid',f.get('id'))));baseurl=url.split('?')[0];recordurl=baseurl+'?f=geojson&objectIds='+str(identifier)+'&outFields=*&outSR=4326'
    add(name+'/'+str(identifier),p.get(name_field),kind,shape(f['geometry']) if f.get('geometry') else None,recordurl,'Published facility point / not a complete site footprint')
   if rid=='ca':
    provider='California Department of Public Health' if kind=='health' else 'CAL FIRE facilities inventory'
    detail='Open GACH, APH, CHEM and SNF facilities from the published licensing table; includes hospitals and skilled nursing facilities. Not all health-service categories.' if kind=='health' else 'Active facilities in the published wildland-fire protection inventory. Includes response/support facility types; not every municipal station is necessarily represented.'
    vintage='2026-10-16' if kind=='health' else None
   else:
    provider='NSW Spatial Services / Health Facilities' if kind=='health' else 'Fire and Rescue NSW'
    detail='Published facility points with OperationalStatus=Operational. Feature reliability dates vary; this is not a complete historical inventory.' if kind=='health' else 'Published Fire and Rescue NSW locations. This does not represent all NSW Rural Fire Service brigades or every emergency resource.'
    vintage=None
   source(kind,provider,url,'Provider terms / attribution retained',detail,vintage)
 # Protected-area inventories differ; make that scope explicit rather than implying a global register.
 name=rid+'-protected';data=read(name);assert not data.get('error') and not data.get('exceededTransferLimit');hashes.append(sha(RAW/(name+'.json')));url=source_url(name)
 for f in data['features']:
  p=f.get('properties',{});identifier=p.get('OBJECTID',p.get('objectid',p.get('objectid_1',f.get('id'))));label=p.get('NAME') or p.get('name') or p.get('park_name');add(name+'/'+str(identifier),label,'protected',shape(f['geometry']) if f.get('geometry') else None,url,'Official inventory boundary / clipped and simplified for display')
 if rid=='lk':provider='Sri Lanka NSDI / Protected Area Network';detail='Published protected-area network polygons. Source vintage is not supplied by the service; this is not a certification of current legal status.'
 elif rid=='ca':provider='US National Park Service / park boundaries';detail='National Park Service units intersecting California only. State parks, local reserves and other protected lands are not included.'
 else:provider='NSW National Parks and Wildlife Service / Estate';detail='NPWS reserved estate polygons, including parks, reserves and conservation areas. Other tenure types are outside this inventory.'
 source('protected',provider,url,'Provider terms / attribution retained',detail)
 places=read('places');hashes.append(sha(RAW/'places.json'))
 for f in places['features']:
  p=f['properties'];identifier=str(p.get('ne_id'));add('naturalearth/'+identifier,p.get('nameascii') or p.get('name'),'settlement',shape(f['geometry']),'https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/','Generalized major-place point / not a population estimate')
 source('settlement','Natural Earth / populated places','https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/','Public domain','Cartographic major-place subset, not a complete settlement inventory or population grid. Many small towns and villages are omitted.')
 counts={kind:sum(f['properties']['kind']==kind for f in features) for kind in ['health','response','settlement','protected']}
 for s in sources:s['count']=counts[s['kind']]
 now=datetime.now(timezone.utc).isoformat();receipt_hash=hashlib.sha256('|'.join(hashes).encode()).hexdigest()
 payload={'version':1,'type':'FeatureCollection','region':rid,'features':features,'provenance':{'provider':'Attributed official and public context inventories','license':'Mixed licences / see per-layer sources','attribution_url':sources[0]['url'],'retrieved_utc':now,'snapshot_date':now[:10],'sources':sources,'raw_sha256':receipt_hash,'raw_file_sha256s':hashes,'protected_raw_sha256':sha(RAW/(name+'.json')),'counts':counts,'spatial_support':'Published facility point centres, generalized major places, and clipped display-simplified protected-area boundaries.','temporal_support':'Source dates differ and may be unspecified; none establishes a historical inventory for a selected fire year.','completeness':'All layers have bounded provider scope and may omit relevant places. Zero matching features does not establish no exposure.','excluded_incomplete_protected_geometries':excluded,'display_geometries_repaired':repaired}}
 path=OUT/f'{rid}.json.gz';path.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode(),mtime=0));print(rid,counts,'excluded',excluded,'bytes',path.stat().st_size)
 return {'region':rid,'sha256':sha(path),'counts':counts,'sources':sources}
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True);receipt=[build(r) for r in ['lk','ca','nsw']];(OUT/'sources.json').write_text(json.dumps(receipt,indent=2))
