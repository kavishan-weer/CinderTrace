"""Selected H3-cell/admin/polygon monthly analytics for the future web app.
History is allocated within each category/confidence slice by MODIS cell-day share;
this preserves regional totals where the input supports spatial allocation.
Usage: python -m pipeline.analytics lk --sub 0 --output /tmp/district.parquet
       python -m pipeline.analytics lk --polygon /path/to/polygon.geojson --output /tmp/aoi.parquet
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

ROOT=Path(__file__).resolve().parent.parent
KEYS=['month','cat','conf']


def select_members(members, sub=None, polygon=None, cell_ids=None):
    if sum(x is not None for x in [sub,polygon,cell_ids])>1:
        raise ValueError('Choose one selection: subregion, polygon, or H3 cells')
    selected=members
    if sub is not None:
        selected=members[members['sub']==sub]
    if cell_ids is not None:
        unknown=set(cell_ids)-set(members.h3_cell)
        if unknown:
            raise ValueError('Selection contains cells outside the region')
        selected=members[members.h3_cell.isin(cell_ids)]
    if polygon is not None:
        if polygon.get('type')=='Feature':
            polygon=polygon['geometry']
        geom=shape(polygon)
        if geom.geom_type not in ['Polygon','MultiPolygon'] or not geom.is_valid:
            raise ValueError('Provide a valid GeoJSON Polygon or MultiPolygon')
        selected=members[[geom.covers(Point(lon,lat)) for lon,lat in zip(members.lon,members.lat)]]
    if selected.empty:
        raise ValueError('No H3 cell centres selected; enlarge the area or choose an administrative area')
    return selected


def selected_monthly(cells, monthly, members, *, sub=None, polygon=None, cell_ids=None):
    selected=select_members(members,sub,polygon,cell_ids)
    local=cells[cells.h3_cell.isin(selected.h3_cell)]
    def counts(frame,fam):
        return frame[frame.fam==fam].groupby(KEYS).cell_days.sum()
    out=monthly.copy().set_index(KEYS)
    out['local_modis']=counts(local,'modis').reindex(out.index,fill_value=0)
    out['local_snpp']=counts(local,'snpp').reindex(out.index,fill_value=0)
    denom=counts(cells,'modis').reindex(out.index,fill_value=0)
    share=out.local_modis.div(denom.where(denom>0))
    share=share.mask((denom==0)&(out.harmonized==0),0)
    observed=out.source=='viirs_observed'
    full=len(selected)==len(members)
    for name in ['harmonized','lo','hi']:
        if not full:
            out[name]=out[name].mul(share).where(~observed,out.local_snpp)
    out['allocation_status']=np.where(observed,'local_observation',np.where(full,'regional_total',np.where(share.notna(),'regional_transfer','unallocatable_no_modis')))
    out.loc[out.harmonized.isna(),'comparison_eligible']=False
    if 'slice_status' in out:
        out.loc[out.harmonized.isna(),'slice_status']='unavailable'
    if 'interval_status' in out:
        out.loc[out.harmonized.isna(),'interval_status']='unavailable'
    out['modis_raw']=out.local_modis.where(out.modis_status!='missing')
    out['viirs_snpp_raw']=out.local_snpp.where(out.snpp_status!='missing')
    out['selected_cells']=len(selected)
    out['selected_grid_area_km2']=selected.area_km2.sum()
    out['activity_per_1000_km2']=out.harmonized/out.selected_grid_area_km2*1000
    out['spatial_method']='H3 centre selection; regional calibration; local accuracy unvalidated'
    out['interval_method']='scaled regional residual bounds; not locally calibrated'
    return out.drop(columns=['local_modis','local_snpp']).reset_index()


def now_vs_history(monthly, target=None, cats=('veg',), confs=(2,3), min_years=5):
    s=monthly[monthly.cat.isin(cats)&monthly.conf.isin(confs)].copy()
    if s.empty:
        return {'status':'no_matching_data'}
    groups=s.groupby('month')
    values=groups.harmonized.agg(lambda x:x.sum(min_count=len(x)))
    eligible=groups.comparison_eligible.all() & values.notna()
    expected=len(set(cats))*len(set(confs))
    complete=groups.apply(lambda g:len(g)==expected and not g.duplicated(['cat','conf']).any(),include_groups=False)
    values=values.where(complete)
    eligible &= complete
    target=pd.Timestamp(target) if target is not None else values.index.max()
    target=target.replace(day=1)
    if target not in values.index or not eligible.get(target,False):
        return {'status':'unavailable_or_provisional','month':str(target.date()),'value':None,'historical_median':None,'percentile':None}
    history=values[(values.index.month==target.month)&(values.index<target)&eligible]
    if len(history)<min_years:
        return {'status':'insufficient_history','historical_years':len(history)}
    value=float(values.loc[target]); median=float(history.median())
    return {'status':'inferred_archive_comparison','month':str(target.date()),'value':value,
            'historical_years':len(history),'historical_median':median,'anomaly':value-median,
            'percentile':float(((history<value).sum()+0.5*(history==value).sum())/len(history)*100)}


def load_region(region):
    return (pd.read_parquet(ROOT/f'data/harmonized/{region}_cells.parquet'),
            pd.read_parquet(ROOT/f'data/harmonized/{region}_monthly.parquet'),
            pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet'))


def export_subregions(region):
    cells,monthly,members=load_region(region)
    frames=[]
    definitions=json.loads((ROOT/f'data/boundaries/{region}_subs.geojson').read_text())['features']
    for feature in definitions:
        sub=feature['properties']['id']
        if sub in set(members['sub']):
            f=selected_monthly(cells,monthly,members,sub=sub)
        else:
            # Tiny administrative areas may contain no resolution-6 centre.
            f=monthly.copy()
            for col in ['harmonized','lo','hi','modis_raw','viirs_snpp_raw']:
                f[col]=np.nan
            f['source']='missing'
            f['period_status']='missing'
            f['comparison_eligible']=False
            f['allocation_status']='no_h3_centres'
            f['slice_status']='unavailable'
            f['interval_status']='unavailable'
            f['selected_cells']=0
            f['selected_grid_area_km2']=0.0
            f['activity_per_1000_km2']=np.nan
            f['spatial_method']='No H3 centre within administrative area'
            f['interval_method']='unavailable'
        f['sub_name']=feature['properties']['name']
        f['sub']=sub
        frames.append(f)
    result=pd.concat(frames,ignore_index=True)
    result.to_parquet(ROOT/f'data/harmonized/{region}_sub_monthly.parquet',index=False)
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('region',choices=['lk','ca','nsw'])
    group=ap.add_mutually_exclusive_group()
    group.add_argument('--sub',type=int)
    group.add_argument('--polygon',type=Path)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    polygon=json.loads(args.polygon.read_text()) if args.polygon else None
    result=selected_monthly(*load_region(args.region),sub=args.sub,polygon=polygon)
    result.to_parquet(args.output,index=False)
    print(json.dumps(now_vs_history(result),indent=2))
