"""Export whole-region monthly history and the actual H3 area denominator."""
import numpy as np
import pandas as pd
import json
from .export_web import ROOT,OUT,COLS,records,write
from .regions import REGIONS

def run():
    regions=[]
    for region,config in REGIONS.items():
        members=pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet')
        area=float(members.area_km2.sum())
        if not members.h3_cell.is_unique or not np.isfinite(area) or area<=0:raise ValueError('Invalid H3 area denominator')
        monthly=pd.read_parquet(ROOT/f'data/harmonized/{region}_monthly.parquet')
        if monthly.duplicated(['month','cat','conf']).any():raise ValueError('Duplicate comparison slices')
        report=json.loads((ROOT/f'data/harmonized/{region}_report.json').read_text())
        regions.append({'id':region,'name':config['name'],'grid_area_km2':area,'cell_count':len(members),'snapshot':report['as_of'],'rows':records(monthly[COLS])})
    write(OUT/'comparison.json',{'denominator':'Actual summed area of regional H3 cells; not exact land or polygon-intersection area','regions':regions})
    print('Exported normalized comparison denominators:',{r['id']:round(r['grid_area_km2'],2) for r in regions})

if __name__=='__main__':run()
