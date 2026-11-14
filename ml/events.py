"""Single-satellite, exact-distance space-time connected-component candidates.

Run: python -m ml.events lk ca nsw [--satellites Suomi-NPP Aqua Terra]
No event-count harmonization, burned area, ignition date or spread-rate claim.
"""
import argparse
import hashlib
import json
import math
import pathlib
import tempfile
import time
from dataclasses import asdict, dataclass

import duckdb
import h3
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from pipeline.grid import H3_RESOLUTION
from pipeline.regions import REGIONS

ROOT = pathlib.Path(__file__).resolve().parents[1]
EARTH_KM = 6371.0088
VERSION = 'point-components-v1'
STREAMS = {'Suomi-NPP':'snpp', 'Aqua':'aqua', 'Terra':'terra', 'NOAA-20':'n20', 'NOAA-21':'n21'}
EVENT_COLUMNS=['event_id','start_utc','end_utc','observed_dates','detection_count',
 'peak_detection_frp_mw','valid_frp_detections','max_detection_gap_hours','centroid_lat',
 'centroid_lon','min_lat','max_lat','min_lon','max_lon','sampled_h3_res8_cells',
 'touches_region_grid_edge','sampled_grid_area_km2','region','satellite',
 'observed_span_hours','calendar_span_days','singleton','multi_date_support',
 'touches_archive_time_edge','end_in_latest_archive_month','long_chain_caution','possible_persistent_source']


@dataclass(frozen=True)
class Config:
    spatial_km: float = 2.
    temporal_hours: float = 48.

    def __post_init__(self):
        if not math.isfinite(self.spatial_km) or not .1 <= self.spatial_km <= 20:
            raise ValueError('Spatial radius must be 0.1-20 km.')
        if not math.isfinite(self.temporal_hours) or not 1 <= self.temporal_hours <= 168:
            raise ValueError('Temporal radius must be 1-168 hours.')


def xyz(lat, lon):
    phi, lam = np.radians(lat), np.radians(lon)
    return EARTH_KM * np.column_stack([np.cos(phi)*np.cos(lam), np.cos(phi)*np.sin(lam), np.sin(phi)])


def roots(parent, indices):
    result = parent[indices]
    while True:
        following = parent[result]
        if np.array_equal(result, following):
            parent[indices] = result
            return result
        result = following


def cluster_points(points, config=Config(), batch_size=1024):
    """Exact spherical-distance AND UTC-time graph, including isolated points.

    Streaming batches retain all prior points in the temporal window. Sparse
    local graphs plus old component stars avoid storing the full archive graph.
    Returns labels aligned to the ORIGINAL row order, and performance counters.
    """
    if batch_size < 1:
        raise ValueError('Batch size must be positive.')
    if points.empty:
        return np.array([],dtype=np.int64), {'candidate_pairs':0,'max_window_points':0}
    stamp = pd.to_datetime(points.acq_datetime,utc=True,errors='coerce')
    lat, lon = np.asarray(points.lat,float), np.asarray(points.lon,float)
    if stamp.isna().any() or not np.isfinite(lat).all() or not np.isfinite(lon).all() or (np.abs(lat)>90).any() or (np.abs(lon)>180).any():
        raise ValueError('Clustering requires valid UTC timestamps and coordinates.')
    t0 = stamp.dt.as_unit('ns').astype('int64').to_numpy()
    order = np.lexsort((lon,lat,t0)); t = t0[order]
    coordinates = xyz(lat[order],lon[order]); n = len(t)
    parent = np.arange(n,dtype=np.int64)
    gap = int(config.temporal_hours*3_600_000_000_000)
    chord = 2*EARTH_KM*math.sin(config.spatial_km/(2*EARTH_KM))
    candidate_pairs, max_window = 0, 0
    for start in range(0,n,batch_size):
        stop = min(n,start+batch_size)
        lo = int(np.searchsorted(t,t[start]-gap,side='left'))
        window = coordinates[lo:stop]; size = stop-lo; max_window=max(max_window,size)
        tree = cKDTree(window)
        neighbours = tree.query_ball_point(coordinates[start:stop],chord+1e-9)
        lengths = np.fromiter((len(x) for x in neighbours),dtype=np.int64)
        a = np.repeat(np.arange(start-lo,stop-lo),lengths)
        b = np.concatenate(neighbours).astype(np.int64) if lengths.sum() else np.array([],dtype=np.int64)
        keep = (b<a) & (t[lo+a]-t[lo+b]<=gap)
        a,b = a[keep],b[keep]; candidate_pairs += len(a)
        old = roots(parent,np.arange(lo,start))
        # Points connected through earlier batches remain connected even if
        # their original connecting path has left the active temporal window.
        _, first, inverse = np.unique(old,return_index=True,return_inverse=True)
        if len(old):
            a=np.concatenate([a,np.arange(len(old))]); b=np.concatenate([b,first[inverse]])
        graph=coo_matrix((np.ones(len(a),dtype=np.uint8),(a,b)),shape=(size,size)).tocsr()
        count,labels=connected_components(graph,directed=False)
        global_roots=np.concatenate([old,np.arange(start,stop)])
        anchors=np.full(count,n,dtype=np.int64)
        np.minimum.at(anchors,labels,global_roots)
        np.minimum.at(parent,global_roots,anchors[labels])
    all_roots=roots(parent,np.arange(n)); _,sorted_labels=np.unique(all_roots,return_inverse=True)
    result=np.empty(n,dtype=np.int64);result[order]=sorted_labels
    return result,{'candidate_pairs':int(candidate_pairs),'max_window_points':int(max_window)}


def file_sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def provenance(region):
    files=sorted((ROOT/'data/raw'/region).glob('*.parquet'))
    paths=[*files,ROOT/f'data/boundaries/{region}_members.parquet',ROOT/f'data/harmonized/{region}_cells.parquet']
    if not files or any(not p.exists() for p in paths):
        raise ValueError('Build regional raw, boundary and harmonized data first.')
    inputs=[{'path':str(p.relative_to(ROOT)),'sha256':file_sha(p),'bytes':p.stat().st_size} for p in paths]
    fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
    return files,inputs,fingerprint


def load_points(region,satellite):
    if region not in REGIONS or satellite not in STREAMS:
        raise ValueError('Unknown region or satellite.')
    members=pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet')
    cells=pd.read_parquet(ROOT/f'data/harmonized/{region}_cells.parquet',columns=['h3_cell','cat']).drop_duplicates()
    if cells.h3_cell.duplicated().any():raise ValueError('Ambiguous cell categories.')
    metadata=members[['h3_cell','sub']].merge(cells,on='h3_cell',validate='one_to_one')
    with duckdb.connect() as c:
        c.register('metadata',metadata)
        c.create_function('to_h3',lambda lat,lon:h3.latlng_to_cell(lat,lon,H3_RESOLUTION),['DOUBLE','DOUBLE'],'VARCHAR')
        raw=c.execute("""SELECT *, CASE WHEN sensor='MODIS' THEN CASE WHEN confidence_pct IS NULL OR confidence_pct<0 OR confidence_pct>100 THEN 0 WHEN confidence_pct<30 THEN 1 WHEN confidence_pct<80 THEN 2 ELSE 3 END
          ELSE CASE confidence WHEN 'l' THEN 1 WHEN 'n' THEN 2 WHEN 'h' THEN 3 ELSE 0 END END AS display_confidence
          FROM read_parquet(?,filename=true,file_row_number=true) WHERE satellite=?""",[str(ROOT/f'data/raw/{region}/*.parquet'),satellite]).df()
        valid=raw.acq_datetime.notna() & np.isfinite(raw.lat) & np.isfinite(raw.lon) & raw.lat.between(-90,90) & raw.lon.between(-180,180)
        audit={'raw_satellite_rows':len(raw),'invalid_time_or_coordinate':int((~valid).sum())}
        raw=raw[valid].copy();c.register('raw_valid',raw)
        tagged=c.execute('SELECT r.*,m.h3_cell,m.sub,m.cat FROM raw_valid r JOIN metadata m ON to_h3(r.lat,r.lon)=m.h3_cell').df()
    audit['outside_H3_membership']=len(raw)-len(tagged)
    mask_cat=(tagged.cat=='veg') & (tagged.type.isna() | (tagged.type==0))
    audit['excluded_source_category_or_type']=int((~mask_cat).sum())
    audit['excluded_low_or_unknown_individual_confidence']=int((mask_cat & (tagged.display_confidence<2)).sum())
    out=tagged[mask_cat & (tagged.display_confidence>=2)].copy()
    out['acq_datetime']=pd.to_datetime(out.acq_datetime,utc=True)
    out['raw_file']=out.filename.map(lambda name:pathlib.Path(name).name)
    out['detection_id']=region+':'+out.raw_file+':'+out.file_row_number.astype(str)
    out=out.drop(columns=['filename']).sort_values(['acq_datetime','lat','lon','detection_id']).reset_index(drop=True)
    audit['included_detections']=len(out)
    assert audit['raw_satellite_rows']==sum(v for k,v in audit.items() if k!='raw_satellite_rows')
    return out,audit


def summarize(points,labels,region,satellite,config_key,config=Config()):
    members=points.copy();members['component']=labels
    if members.empty:
        members=members.drop(columns='component')
        members['event_id']=pd.Series(dtype=str)
        members['observed_date']=pd.Series(dtype='datetime64[ns, UTC]')
        members['footprint_h3']=pd.Series(dtype=str)
        return pd.DataFrame(columns=EVENT_COLUMNS),members,pd.DataFrame(columns=['event_id','observed_date','detections','peak_detection_frp_mw','centroid_lat','centroid_lon'])
    members=members.sort_values(['acq_datetime','lat','lon']).reset_index(drop=True)
    anchors=members.drop_duplicates('component')
    names={component:f'{region}-{STREAMS[satellite]}-{config_key}-'+hashlib.sha256(f'{stamp.isoformat()}:{lat:.9f}:{lon:.9f}'.encode()).hexdigest()[:16]
           for component,stamp,lat,lon in zip(anchors.component,anchors.acq_datetime,anchors.lat,anchors.lon)}
    members['event_id']=members.component.map(names);members=members.drop(columns='component')
    members['observed_date']=members.acq_datetime.dt.floor('D')
    members['footprint_h3']=[h3.latlng_to_cell(lat,lon,8) for lat,lon in zip(members.lat,members.lon)]
    valid_frp=np.where(np.isfinite(members.frp)&(members.frp>=0),members.frp,np.nan)
    members['valid_frp_mw']=valid_frp
    members['gap_hours']=members.groupby('event_id',sort=False).acq_datetime.diff().dt.total_seconds().fillna(0)/3600
    regional_cells=set(pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet').h3_cell)
    boundary_cells={cell for cell in members.h3_cell.unique() if not set(h3.grid_disk(cell,1)).issubset(regional_cells)}
    members['grid_edge']=members.h3_cell.isin(boundary_cells)
    grouped=members.groupby('event_id',sort=True)
    events=grouped.agg(start_utc=('acq_datetime','min'),end_utc=('acq_datetime','max'),
        observed_dates=('observed_date','nunique'),detection_count=('detection_id','size'),
        peak_detection_frp_mw=('valid_frp_mw','max'),valid_frp_detections=('valid_frp_mw','count'),
        max_detection_gap_hours=('gap_hours','max'),centroid_lat=('lat','mean'),centroid_lon=('lon','mean'),
        min_lat=('lat','min'),max_lat=('lat','max'),min_lon=('lon','min'),max_lon=('lon','max'),
        sampled_h3_res8_cells=('footprint_h3','nunique'),touches_region_grid_edge=('grid_edge','any')).reset_index()
    unique_cells=members[['event_id','footprint_h3']].drop_duplicates().copy()
    area={cell:h3.cell_area(cell,unit='km^2') for cell in unique_cells.footprint_h3.unique()}
    unique_cells['area']=unique_cells.footprint_h3.map(area)
    events['sampled_grid_area_km2']=events.event_id.map(unique_cells.groupby('event_id').area.sum())
    events['region']=region;events['satellite']=satellite
    events['observed_span_hours']=(events.end_utc-events.start_utc).dt.total_seconds()/3600
    events['calendar_span_days']=(events.end_utc.dt.floor('D')-events.start_utc.dt.floor('D')).dt.days+1
    events['singleton']=events.detection_count==1;events['multi_date_support']=events.observed_dates>1
    first,last=members.acq_datetime.min(),members.acq_datetime.max()
    events['touches_archive_time_edge']=(events.start_utc<=first+pd.Timedelta(hours=config.temporal_hours))|(events.end_utc>=last-pd.Timedelta(hours=config.temporal_hours))
    events['end_in_latest_archive_month']=events.end_utc.dt.strftime('%Y-%m')==last.strftime('%Y-%m')
    events['long_chain_caution']=events.observed_span_hours>30*24
    events['possible_persistent_source']=events.long_chain_caution&(events.sampled_h3_res8_cells<=3)
    daily=members.groupby(['event_id','observed_date'],as_index=False).agg(detections=('detection_id','size'),peak_detection_frp_mw=('valid_frp_mw','max'),centroid_lat=('lat','mean'),centroid_lon=('lon','mean'))
    members=members.drop(columns=['valid_frp_mw','gap_hours','grid_edge'])
    return events,members,daily


def audit_catalog(events,members,daily,expected,temporal_hours=48.):
    grouped=members.groupby('event_id') if len(members) else None
    counts=grouped.size() if grouped is not None else pd.Series(dtype=int)
    reported=events.set_index('event_id') if len(events) else None
    checks={
      'all_included_rows_assigned_once':len(members)==expected and members.detection_id.nunique()==expected,
      'event_totals_conserve_detections':int(events.detection_count.sum())==expected if len(events) else expected==0,
      'daily_totals_conserve_detections':int(daily.detections.sum())==expected if len(daily) else expected==0,
      'event_ids_unique':not events.event_id.duplicated().any(),
      'one_satellite_per_catalog':members.satellite.nunique()<=1,
      'nonnegative_observed_spans':bool((events.observed_span_hours>=0).all()) if len(events) else True,
      'every_event_count_matches_memberships':bool(counts.equals(reported.detection_count.reindex(counts.index))) if len(events) else expected==0,
      'event_times_match_memberships':bool((grouped.acq_datetime.min()==reported.start_utc.reindex(counts.index)).all() and (grouped.acq_datetime.max()==reported.end_utc.reindex(counts.index)).all()) if len(events) else expected==0,
      'no_internal_time_gap_exceeds_link_limit':bool((events.max_detection_gap_hours<=temporal_hours+1e-8).all()) if len(events) else True,
      'daily_event_dates_unique':not daily.duplicated(['event_id','observed_date']).any() if len(daily) else True,
      'daily_and_membership_event_ids_match_catalog':set(members.event_id)==set(events.event_id)==set(daily.event_id) if len(members) else len(events)==len(daily)==0,
    }
    if not all(checks.values()):raise AssertionError(checks)
    return checks


def build(region,satellite,config,source=None):
    tick=time.monotonic();_,inputs,fingerprint=source or provenance(region)
    config_data={'version':VERSION,**asdict(config),'satellite':satellite,'category':'veg and raw type 0 or null','confidence':'individual nominal+high','boundary':'existing H3 resolution-6 membership'}
    config_key=hashlib.sha256(json.dumps(config_data,sort_keys=True).encode()).hexdigest()[:10]
    output=ROOT/'data/events'/region/STREAMS[satellite]/f'{config_key}-{fingerprint[:12]}'
    if (output/'report.json').exists():
        print(f'{region} {satellite}: existing completed snapshot {output.name}',flush=True);return output
    points,audit=load_points(region,satellite)
    labels,performance=cluster_points(points,config)
    events,members,daily=summarize(points,labels,region,satellite,config_key,config)
    checks=audit_catalog(events,members,daily,len(points),config.temporal_hours)
    report={'schema_version':1,'config':config_data,'input_fingerprint':fingerprint,'inputs':inputs,'selection_audit':audit,'checks':checks,'performance':performance,
        'candidate_events':len(events),'singleton_candidates':int(events.singleton.sum()) if len(events) else 0,
        'multi_date_candidates':int(events.multi_date_support.sum()) if len(events) else 0,
        'largest_event_detection_share':float(events.detection_count.max()/len(points)) if len(points) else None,
        'long_chain_candidates':int(events.long_chain_caution.sum()) if len(events) else 0,
        'seconds':round(time.monotonic()-tick,2),
        'limits':['Estimated connected detection components, not confirmed incident counts or harmonized events.',
          'Chaining can merge separate fires; observation gaps can split one fire. Singletons remain weak candidates.',
          'Duration is observed first-to-last detection span, not ignition/extinction or uninterrupted burning.',
          'Res8 sampled-grid area is not burned area or a fire perimeter; centroid is detection-weighted.',
          'Peak FRP is the maximum individual valid detection, not event-total power or energy.',
          'Archive and region-grid edges censor events; quiet periods do not verify observation coverage.',
          'Historical H3 source categorization is retrospective and can leak future labels; not an operational hindcast.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent,prefix='.building-') as directory:
        temp=pathlib.Path(directory)
        for name,frame in [('events',events),('memberships',members),('daily',daily)]:frame.to_parquet(temp/f'{name}.parquet',index=False)
        (temp/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        temp.rename(output)
    print(f'{region} {satellite}: {len(points):,} detections -> {len(events):,} candidates ({report["seconds"]}s)',flush=True)
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('regions',nargs='*',default=list(REGIONS),choices=list(REGIONS))
    parser.add_argument('--satellites',nargs='+',default=['Suomi-NPP'],choices=list(STREAMS))
    parser.add_argument('--spatial-km',type=float,default=2.)
    parser.add_argument('--temporal-hours',type=float,default=48.)
    args=parser.parse_args();config=Config(args.spatial_km,args.temporal_hours)
    for region in args.regions:
        source=provenance(region)
        for satellite in args.satellites:build(region,satellite,config,source)


if __name__=='__main__':main()
