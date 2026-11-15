"""Public catalogue inventory for the frozen expanded study; no science downloads."""
from pathlib import Path
from datetime import datetime,timezone
import json
from . import atlas_observation_evidence as e

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'data/atlas/viirs_expansion_inventory_v1'

def run():
    design_path=ROOT/'docs/atlas_viirs_expansion_design_v1.json';design=json.loads(design_path.read_text());OUT.mkdir(parents=True,exist_ok=True);rawdir=OUT/'cmr';rawdir.mkdir(exist_ok=True)
    boundary=(ROOT/'data/atlas/canonical_lk_2000_2024_v1/region.geojson').read_bytes()
    if e.sha(boundary)!=e.BOUNDARY_SHA:raise ValueError('Boundary changed')
    from shapely.geometry import shape
    region=shape(json.loads(boundary)['features'][0]['geometry']);bbox=','.join(map(str,region.bounds));records=[];summaries=[]
    for index,slot in enumerate(design['dates'],1):
        day=slot['date']
        for product,spec in e.PRODUCTS.items():
            found=[];page=1;hits=None
            while True:
                params={'collection_concept_id':spec['collection'],'bounding_box':bbox,'temporal':day+'T00:00:00Z,'+day+'T23:59:59.999Z','page_size':200,'page_num':page}
                body,receipt=e.query(params,rawdir/f'{product}_{day}_{page}.json');entries=body['feed']['entry']
                if page==1:hits=receipt['cmr_hits']
                elif receipt['cmr_hits']!=hits:raise ValueError('CMR changed during pagination')
                found.extend(entries)
                if len(entries)<200:break
                page+=1
                if page>100:raise ValueError('Unexpected catalogue size')
            if hits is not None and hits!=len(found):raise ValueError('Incomplete catalogue page set')
            if len({x['id'] for x in found})!=len(found):raise ValueError('Duplicate CMR record')
            found=[r for r in found if r['time_start'][:10]==day]
            rows=[e.normalize(r,product,day) for r in found];records.extend(rows)
            summaries.append({**slot,'product':product,'records':len(rows),'catalogue_mib':sum(r['catalogue_size_mb'] for r in rows),'status':'catalogue_listed_coverage_unverified' if rows else 'catalogue_absent_not_zero_activity'})
        print('Catalogued expanded date',index,'/',len(design['dates']),day,flush=True)
    joins=e.join_companions(records);inventory={'study_id':design['study_id'],'design_sha256':e.sha(design_path.read_bytes()),'created_utc':datetime.now(timezone.utc).isoformat(),
      'records':records,'daily_catalogue':summaries,'companions':joins,'time_candidates':e.time_candidates(records),
      'catalogue_mib':sum(r['catalogue_size_mb'] for r in records),'science_files_downloaded':0,'coverage_verified':False,'replacement_validated':False,'frontend_changed':False}
    (OUT/'inventory.json').write_text(json.dumps(inventory,indent=2,allow_nan=False)+'\n');(OUT/'region.geojson').write_bytes(boundary)
    report={'study_id':design['study_id'],'sampled_dates':len(design['dates']),'catalogued_science_files':len(records),'fire_granules':sum(r['kind']=='fire' for r in records),
     'catalogue_mib':inventory['catalogue_mib'],'catalogue_gib':inventory['catalogue_mib']/1024,
     'companion_states':{state:sum(j['status']==state for j in joins) for state in sorted({j['status'] for j in joins})},
     'absent_product_dates':[{'date':x['date'],'product':x['product']} for x in summaries if x['records']==0],
     'science_files_downloaded':0,'coverage_verified':False,'replacement_validated':False,'frontend_changed':False,
     'resource_note':'Full geolocation files dominate. Estimate is catalogue size, not a storage guarantee. Plan transient raw-file staging with retained receipts/derived evidence; preserve the original pilot cache.',
     'files':{}}
    for path in sorted(OUT.rglob('*')):
        if path.is_file():b=path.read_bytes();report['files'][path.relative_to(OUT).as_posix()]={'bytes':len(b),'sha256':e.sha(b)}
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');(ROOT/'docs/atlas_viirs_expansion_inventory.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2));return inventory
if __name__=='__main__':run()
