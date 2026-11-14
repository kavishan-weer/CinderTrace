"""Discover Sri Lanka MODIS observation products without asserting usable coverage.

Queries public CMR metadata, clips tile footprints to the study geometry, and probes
one science-file download per sensor without credentials. Never restores zeros.
Run python -m pipeline.observation_pilot; metadata only, no bulk science downloads.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import pandas as pd
from shapely.geometry import Polygon,shape
from .harmonize import ROOT

CMR='https://cmr.earthdata.nasa.gov/search/'
PRODUCTS=('MOD14A1','MYD14A1')
CONTROL_MONTHS=['2001-03','2002-01','2003-03','2012-08','2022-12','2023-08']


def request_json(endpoint,params):
    url=CMR+endpoint+'?'+urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url,timeout=60) as response:
                raw=response.read()
            return json.loads(raw),url,hashlib.sha256(raw).hexdigest()
        except (urllib.error.URLError,TimeoutError):
            if attempt==2:raise
            time.sleep(attempt+1)


def intersects(entry,region):
    polygons=entry.get('polygons',[])
    if not polygons:return None  # Metadata absence must not discard a possible tile.
    for group in polygons:
        for value in group:
            xy=list(map(float,value.split()))
            geom=Polygon([(xy[i+1],xy[i]) for i in range(0,len(xy),2)])
            if not geom.is_valid:return None
            if geom.intersects(region):return True
    return False


class LoginRequired(Exception):pass
class StopLoginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        if urllib.parse.urlsplit(newurl).hostname=='urs.earthdata.nasa.gov':
            raise LoginRequired('Earthdata authentication redirect')
        return super().redirect_request(request,fp,code,msg,headers,newurl)


def probe_access(url):
    opener=urllib.request.build_opener(StopLoginRedirect())
    try:
        req=urllib.request.Request(url,headers={'Range':'bytes=0-1023'})
        with opener.open(req,timeout=45) as response:
            sample=response.read(1024)
            # HDF4 or HDF5 signatures, not an HTML login page.
            hdf=sample.startswith(b'\x0e\x03\x13\x01') or sample.startswith(b'\x89HDF\r\n\x1a\n')
            return {'status':'anonymous_science_access' if hdf else 'unexpected_response',
                'http_status':response.status,'content_type':response.headers.get('Content-Type'),
                'sample_bytes':len(sample)}
    except LoginRequired:
        return {'status':'earthdata_login_required','evidence':'science download redirected to urs.earthdata.nasa.gov'}
    except urllib.error.HTTPError as error:
        return {'status':'anonymous_access_denied' if error.code in (401,403) else 'http_error',
                'http_status':error.code,'evidence':'HTTP denial alone does not identify its cause'}
    except (urllib.error.URLError,TimeoutError) as error:
        return {'status':'access_test_inconclusive','error_type':type(error).__name__}


def run():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'data/observation_pilot/lk'/stamp;out.mkdir(parents=True,exist_ok=False)
    coverage_path=ROOT/'data/harmonized/lk_coverage.parquet'
    coverage=pd.read_parquet(coverage_path)
    as_of=pd.Timestamp(datetime.now(timezone.utc).date()).replace(day=1)
    disputed=coverage[(coverage.fam=='modis')&(coverage.status=='missing')&
        (coverage.month>='2000-11-01')&(coverage.month<as_of)].month.dt.strftime('%Y-%m').tolist()
    months=sorted(set(disputed+CONTROL_MONTHS))
    region=shape(json.loads((ROOT/'data/boundaries/lk_region.geojson').read_text())['features'][0]['geometry'])
    bbox=','.join(map(str,region.bounds))
    collections={};queries=[];records={};rows=[];access=[]
    for product in PRODUCTS:
        response,url,digest=request_json('collections.json',{'short_name':product,'version':'061','page_size':100})
        (out/f'{product}-collection.json').write_text(json.dumps(response,indent=2)+'\n')
        entries=response['feed']['entry']
        chosen=[e for e in entries if e.get('data_center')=='LPCLOUD']
        if len(chosen)!=1:raise ValueError(f'Expected one LPCLOUD collection for {product}')
        collections[product]=chosen[0]['id']
        queries.append({'url':url,'response_sha256':digest})
        for month in months:
            start=pd.Timestamp(month+'-01');end=start+pd.offsets.MonthBegin(1)-pd.Timedelta(seconds=1)
            temporal=f'{start:%Y-%m-%dT00:00:00Z},{end:%Y-%m-%dT%H:%M:%SZ}'
            params={'collection_concept_id':collections[product],'bounding_box':bbox,
                'temporal':temporal,'page_size':200,'page_num':1}
            found=[]
            while True:
                response,url,digest=request_json('granules.json',params)
                (out/f'{product}-{month}-page{params["page_num"]}.json').write_text(json.dumps(response,indent=2)+'\n')
                queries.append({'url':url,'response_sha256':digest})
                entries=response['feed']['entry'];found.extend(entries)
                if len(entries)<200:break
                params['page_num']+=1
            accepted=[e for e in found if intersects(e,region) is not False]
            for entry in accepted:
                links=[l['href'] for l in entry.get('links',[]) if not l.get('inherited')
                    and l.get('rel','').endswith('/data#') and l['href'].startswith('https://') and '.hdf' in l['href']]
                if not links:continue
                records[entry['id']]={'id':entry['id'],'product':product,'producer_granule_id':entry['producer_granule_id'],
                    'time_start':entry.get('time_start'),'time_end':entry.get('time_end'),
                    'size_mb_catalogue':float(entry.get('granule_size',0)), 'download_url':links[0],
                    'footprint_intersects_region':intersects(entry,region)}
            local=coverage[(coverage.fam=='modis')&(coverage.month==start)].iloc[0]
            rows.append({'month':month,'role':'disputed' if month in disputed else 'control','product':product,
                'local_bbox_modis_detections':int(local.detections),'catalogue_bbox_matches':len(found),
                'region_intersecting_records':len(accepted),'pixel_coverage_verified':False,
                'note':'A file listing does not establish usable, cloud-free or complete observations.'})
        sample=next((r for r in records.values() if r['product']==product),None)
        if sample:access.append({'product':product,'url':sample['download_url'],**probe_access(sample['download_url'])})
        print(product,'catalogued',flush=True)
    manifest={'created_at_utc':stamp,'region':'lk','collections':collections,'region_bbox':region.bounds,
        'disputed_closed_months':disputed,'control_months':CONTROL_MONTHS,
        'excluded_current_month':str(as_of.date()),'monthly_inventory':rows,
        'unique_science_files':len(records),'estimated_download_mb_catalogue':sum(r['size_mb_catalogue'] for r in records.values()),
        'access_probes':access,'science_files':list(records.values()),'queries':queries,
        'status':'metadata_only_no_zero_restoration','production_changes':False,
        'interpretation':['L3 files contain daily layers packaged over eight-day intervals; temporal overlap includes boundary-crossing packages.',
            'L3 daily composites can screen regional coverage, but do not enumerate every swath/overpass or reproduce sensor-family cell-days.',
            'Reconciliation against MOD14/MYD14 swaths is required before certifying the detection archive.',
            'Early Aqua absences before its mission record are expected, not missing observations.'],
        'inputs':[]}
    for p in [coverage_path,ROOT/'data/boundaries/lk_region.geojson',Path(__file__)]:
        manifest['inputs'].append({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    (ROOT/'docs/lk_observation_pilot.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(out),'unique_files':len(records),'estimated_mb':manifest['estimated_download_mb_catalogue'],
        'access_probes':access},indent=2),flush=True)
    return out

if __name__=='__main__':run()
