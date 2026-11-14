"""Independent public-catalogue swath/geolocation reconciliation for the LK pilot.
A paired listing is metadata evidence, not verified pixel quality or ingestion.
Do not automatically restore zero months from this inventory.
"""
from datetime import datetime,timezone
from pathlib import Path
import json
import re
from collections import defaultdict
import pandas as pd
from shapely.geometry import shape
from .harmonize import ROOT
from .observation_pilot import request_json,intersects
from .lk_observation_analysis import PILOT_MONTHS

COLLECTIONS={'MOD14':'C2271754179-LPCLOUD','MYD14':'C2278858993-LPCLOUD',
             'MOD03':'C1379767668-LAADS','MYD03':'C1379841358-LAADS'}

def acquisition_key(name):
    match=re.search(r'\.A(\d{7})\.(\d{4})\.',name)
    if not match:raise ValueError('Cannot identify swath acquisition')
    return match.group(1)+'.'+match.group(2)


def run():
    region=shape(json.loads((ROOT/'data/boundaries/lk_region.geojson').read_text())['features'][0]['geometry'])
    out=ROOT/'data/observation_pilot/lk'/('swath_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    records=[];queries=[]
    for product,collection in COLLECTIONS.items():
        for month in PILOT_MONTHS:
            start=pd.Timestamp(month+'-01');end=start+pd.offsets.MonthBegin(1)-pd.Timedelta(seconds=1)
            params={'collection_concept_id':collection,'bounding_box':','.join(map(str,region.bounds)),
                'temporal':f'{start:%Y-%m-%dT00:00:00Z},{end:%Y-%m-%dT%H:%M:%SZ}',
                'page_size':200,'page_num':1}
            while True:
                response,url,digest=request_json('granules.json',params)
                (out/f'{product}-{month}-page{params["page_num"]}.json').write_text(json.dumps(response,indent=2)+'\n')
                queries.append({'url':url,'response_sha256':digest})
                entries=response['feed']['entry']
                for e in entries:
                    # Keep bbox candidates so footprint geometry differences do
                    # not masquerade as missing acquisitions across collections.
                    name=e['producer_granule_id']
                    records.append({'month':month,'product':product,'id':e['id'],'name':name,
                        'acquisition':acquisition_key(name),'time_start':e.get('time_start'),'time_end':e.get('time_end'),
                        'region_intersection':intersects(e,region),
                        'download_links':[l['href'] for l in e.get('links',[]) if not l.get('inherited')
                            and l.get('rel','').endswith('/data#') and l['href'].startswith('https://')]})
                if len(entries)<200:break
                params['page_num']+=1
        print(product,'swath catalogue queried',flush=True)
    summary=[]
    for month in PILOT_MONTHS:
        for sensor,fire,geo in [('Terra','MOD14','MOD03'),('Aqua','MYD14','MYD03')]:
            sets={p:{r['acquisition'] for r in records if r['month']==month and r['product']==p} for p in (fire,geo)}
            summary.append({'month':month,'sensor':sensor,'fire_swath_bbox_acquisitions':len(sets[fire]),
                'geolocation_bbox_acquisitions':len(sets[geo]),'paired_bbox_acquisitions':len(sets[fire]&sets[geo]),
                'geolocation_without_fire_bbox_match':sorted(sets[geo]-sets[fire]),
                'fire_without_geolocation_bbox_match':sorted(sets[fire]-sets[geo]),
                'pixel_observation_verification_complete':False})
    report={'created_at_utc':datetime.now(timezone.utc).isoformat(),'collections':COLLECTIONS,'summary':summary,
        'records':records,'queries':queries,'status':'catalogue_reconciliation_only_no_zero_restoration',
        'limits':['An acquisition missing from a bbox result can reflect different footprint metadata; inspect exact granules before treating it as data loss.',
            'The geolocation inventory is independent of fire detection but cannot reveal acquisitions missing from both catalogues.',
            'File bytes, quality layers, product-version compatibility and local archive ingestion require verification.',
            'Early Aqua absence is expected.']}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'docs/lk_swath_pilot_inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out,flush=True)

if __name__=='__main__':run()
