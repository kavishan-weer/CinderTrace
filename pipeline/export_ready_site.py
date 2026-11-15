"""Export native observations and attributed published analytics for the static app.
No legacy calibration, allocation, uncertainty or forecast results are used.
"""
from pathlib import Path
import gzip,hashlib,json
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.strtree import STRtree
import h3
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'web/site-public/ready'
SAT=['Terra','Aqua','Suomi-NPP','NOAA-20','NOAA-21']
IDS={'lk':('country','LKA'),'ca':('state','USA-3521'),'nsw':('state','AUS-2654')}
NAMES={'lk':'Sri Lanka','ca':'California','nsw':'New South Wales'}
def sha(b):return hashlib.sha256(b).hexdigest()
def records(d):return json.loads(d.to_json(orient='records',date_format='iso'))
def write(path,obj,compress=False):
    raw=(json.dumps(obj,separators=(',',':'),allow_nan=False)+'\n').encode();path.parent.mkdir(parents=True,exist_ok=True)
    if compress:raw=gzip.compress(raw,compresslevel=6,mtime=0)
    path.write_bytes(raw);return {'bytes':len(raw),'sha256':sha(raw)}
def run():
    OUT.mkdir(parents=True,exist_ok=True);source=ROOT/'data/external/fire_harmony_v1';provider=json.loads((source/'manifest.json').read_text())
    for r in provider['files']:
        b=(source/r['file']).read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256']
    areas=json.loads((source/'areas.json').read_text());meta=json.loads((source/'meta.json').read_text());monthly=pd.read_parquet(source/'area_monthly.parquet')
    canonical=ROOT/'data/atlas/canonical_lk_2000_2024_v1';cm=json.loads((canonical/'manifest.json').read_text())
    for name,r in cm['files'].items():
        b=(canonical/name).read_bytes();assert len(b)==r['bytes'] and sha(b)==r['sha256']
    lk=pd.read_parquet(canonical/'observations.parquet');old=json.loads((ROOT/'web/public/data/manifest.json').read_text())
    manifest={'version':'cindertrace-ready-v1','observed_units':'recorded satellite pixel observations, not unique fires or burned area','provider':provider,'provider_scale':meta['scale'],'provider_built_utc':meta['built_utc'],'provider_source_labels':meta['sources'],
      'native_row_columns':['utc_seconds','longitude','latitude','satellite_index','frp_mw','native_confidence','published_type','quality_index','cell_index','admin_id','daynight','source_row'],
      'native_satellites':SAT,'source_catalogue':'https://github.com/portolan-mirrors/firms-catalog','observation_coverage':'unverified','regions':[],'files':{}}
    for region,(kind,id) in IDS.items():
        folder=OUT/region;folder.mkdir(exist_ok=True)
        boundary=json.loads((ROOT/'data/boundaries'/f'{region}_region.geojson').read_text());geom=shapely.union_all([shape(f['geometry']) for f in boundary['features']]);subs=json.loads((ROOT/'data/boundaries'/f'{region}_subs.geojson').read_text())
        sg=[shape(f['geometry']) for f in subs['features']];tree=STRtree(sg);sublist=[{'id':int(f['properties']['id']),'name':f['properties']['name']} for f in subs['features']]
        write(folder/'boundary.json',boundary);write(folder/'administrative.json.gz',subs,True)
        provider_areas=[a for a in areas if (a['kind'],a['id'])==(kind,id) or (region=='lk' and a.get('country_iso3')=='LKA' and a['kind']=='state')]
        keys={(a['kind'],a['id']) for a in provider_areas};pm=monthly[monthly.id.isin([a['id'] for a in provider_areas])].copy()
        pm=pm[pm.apply(lambda r:(r['kind'],r['id']) in keys,axis=1)]
        assert not pm.duplicated(['kind','id','yr','mo']).any()
        write(folder/'provider.json',{'areas':provider_areas,'root_id':id,'root_kind':kind,'rows':records(pm)})
        years=[];total=0;latest='';sources=[]
        for year in range(2000,2027):
            if region=='lk' and year<=2024:
                d=lk[lk.year.eq(year)].copy().rename(columns={'longitude':'lon','latitude':'lat'});validation='official-source-reconciled archive';inputsha=cm['files']['observations.parquet']['sha256']
            else:
                path=ROOT/'data/raw'/region/f'{year}.parquet'
                if not path.exists():continue
                d=pd.read_parquet(path);validation='regional mirror extract; observing coverage unverified';inputsha=sha(path.read_bytes())
            if len(d):
                d=d[shapely.intersects_xy(geom,d.lon.to_numpy(),d.lat.to_numpy())].copy();d=d.drop_duplicates(subset=['acq_datetime','lon','lat','satellite','quality','confidence','type','frp'])
            n=len(d);total+=n
            if n:
                d=d.sort_values(['acq_datetime','satellite','lon','lat']).reset_index(drop=True)
                matches=tree.query(shapely.points(d.lon.to_numpy(),d.lat.to_numpy()),predicate='within');admin=np.full(n,-1,dtype=int)
                # Boundary points stay unassigned; never duplicate observations.
                for point,index in zip(*matches):admin[point]=int(sublist[index]['id'])
                hexes=[h3.latlng_to_cell(float(a),float(b),6) for a,b in zip(d.lat,d.lon)];cells=sorted(set(hexes));hi={v:i for i,v in enumerate(cells)}
                timestamp=pd.to_datetime(d.acq_datetime,utc=True).astype('int64')
                # Explicit seconds avoids pandas datetime-unit assumptions.
                epoch=[int(pd.Timestamp(t).timestamp()) for t in d.acq_datetime]
                typecol=pd.to_numeric(d.type,errors='coerce');frp=pd.to_numeric(d.frp,errors='coerce')
                tuples=[]
                for i,r in enumerate(d.itertuples()):
                    tuples.append([epoch[i],float(r.lon),float(r.lat),SAT.index(r.satellite),float(frp.iloc[i]) if pd.notna(frp.iloc[i]) else None,str(r.confidence),int(typecol.iloc[i]) if pd.notna(typecol.iloc[i]) else None,0 if r.quality=='sp' else 1,hi[hexes[i]],int(admin[i]),str(r.daynight),i])
                latest=max(latest,pd.to_datetime(d.acq_datetime,utc=True).max().strftime('%Y-%m-%d'))
            else:tuples=[];cells=[]
            file=f'{region}/native-{year}.json.gz';receipt=write(OUT/file,{'year':year,'rows':tuples,'cells':cells,'count':n,'provenance':validation,'source_sha256':inputsha},True);manifest['files'][file]=receipt
            years.append({'year':year,'rows':n,'source_sha256':inputsha,'provenance':validation});print(region,year,n,flush=True)
        entry={'id':region,'name':NAMES[region],'bbox':list(geom.bounds),'native_years':years,'observations':total,'last_recorded_date':latest,'start_date':'2000-11-01','subs':sublist,'provider_id':id,'provider_kind':kind,'silhouette':next(r['silhouette'] for r in old['regions'] if r['id']==region)}
        manifest['regions'].append(entry)
    for path in sorted(OUT.rglob('*')):
        if path.is_file() and path.name!='manifest.json':b=path.read_bytes();manifest['files'][path.relative_to(OUT).as_posix()]={'bytes':len(b),'sha256':sha(b)}
    write(OUT/'manifest.json',manifest)
    (ROOT/'docs/ready_site_data_receipt.json').write_text(json.dumps({'regions':[{k:r[k] for k in ['id','observations','last_recorded_date']} for r in manifest['regions']],'provider_revision':provider['revision'],'legacy_calibration_used':False,'files':manifest['files']},indent=2)+'\n')
    return manifest
if __name__=='__main__':run()
