"""Export static browser datasets. Run after harmonization and area validation.
No raw archive or credentials are copied. Map data are loaded one region-year at a time.
"""
import json
from pathlib import Path
import pandas as pd
from shapely.geometry import shape
from .regions import REGIONS
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'web/public/data'
CATS=['veg','volcano','static','offshore']
COLS=['month','cat','conf','modis_raw','viirs_snpp_raw','harmonized','lo','hi','source','period_status','comparison_eligible','low_data']

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,separators=(',',':'),allow_nan=False))

def records(df):
    df=df.copy()
    df['month']=pd.to_datetime(df.month).dt.strftime('%Y-%m')
    return json.loads(df.to_json(orient='records',double_precision=5))

def run():
    manifest={'as_of':None,'regions':[],'unit':'VIIRS-equivalent fire-active cell-days','categories':CATS}
    for region,config in REGIONS.items():
        base=ROOT/'data/harmonized'
        monthly=pd.read_parquet(base/f'{region}_monthly.parquet')
        cells=pd.read_parquet(base/f'{region}_cells.parquet')
        members=pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet')
        report=json.loads((base/f'{region}_report.json').read_text())
        manifest['as_of']=report['as_of']
        write(OUT/region/'monthly.json',records(monthly[COLS]))
        write(OUT/region/'report.json',report)
        definitions=json.loads((ROOT/f'data/boundaries/{region}_subs.geojson').read_text())
        sub_counts=members['sub'].value_counts()
        subs=[{**f['properties'],'cell_count':int(sub_counts.get(f['properties']['id'],0))} for f in definitions['features']]
        write(OUT/region/'subs.geojson',definitions)
        write(OUT/region/'boundary.geojson',json.loads((ROOT/f'data/boundaries/{region}_region.geojson').read_text()))
        write(OUT/region/'members.json',[[r.h3_cell,int(r.sub)] for r in members.itertuples()])
        areas=pd.read_parquet(base/f'{region}_sub_monthly.parquet')
        for sub,df in areas.groupby('sub'):
            # Preserve spatial eligibility for tiny/unallocatable areas.
            write(OUT/region/f'sub-{sub}.json',records(df[COLS]))
        ids=sorted(cells.h3_cell.unique()); lookup={h:i for i,h in enumerate(ids)}
        write(OUT/region/'hexagons.json',ids)
        maps=cells[cells.fam.isin(['modis','snpp'])].copy()
        maps['year']=maps.month.dt.year
        for year,df in maps.groupby('year'):
            rows=[[lookup[r.h3_cell],int(r.month.month),CATS.index(r.cat),int(r.conf),0 if r.fam=='modis' else 1,int(r.cell_days)] for r in df.itertuples()]
            write(OUT/region/f'map-{year}.json',rows)
        boundary=shape(json.loads((ROOT/f'data/boundaries/{region}_region.geojson').read_text())['features'][0]['geometry']).simplify(.025)
        west,south,east,north=boundary.bounds
        scale=62/max(east-west,north-south)
        polygons=list(boundary.geoms) if boundary.geom_type=='MultiPolygon' else [boundary]
        silhouette=' '.join('M'+' L'.join(f'{(x-west)*scale+9:.1f},{(north-y)*scale+9:.1f}' for x,y in poly.exterior.coords)+' Z' for poly in polygons)
        manifest['regions'].append({'id':region,'silhouette':silhouette,**config,'subs':subs,'cell_count':len(members),'years':sorted(int(x) for x in maps.year.unique())})
        print(region,'exported',len(monthly),'monthly rows;',len(ids),'active hexagons')
    write(OUT/'manifest.json',manifest)

if __name__=='__main__':run()
