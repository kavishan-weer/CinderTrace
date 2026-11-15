"""Verify the supplied Atlas pilot and export only observed detections for the explorer.
The original bundle is immutable. This does not reuse harmonized/model outputs.
"""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import shutil
import zipfile
import numpy as np
import pandas as pd
import shapely

ROOT=Path(__file__).resolve().parent.parent
EXPECTED_SHA256='11184caea4d9ca669e4f7f455d120d8f4d898db0bf2086f5c86cb9b47650e49e'
SATELLITES=['Terra','Aqua','Suomi-NPP','NOAA-20']
EXPECTED_TOTALS={'Terra':198,'Aqua':642,'Suomi-NPP':6432,'NOAA-20':6094}
MEMBERS={'audit_manifest.json','observations.parquet','monthly_observed_counts.csv','region.geojson','sensor_counts.csv','source_schema.csv'}

def digest(data):return hashlib.sha256(data).hexdigest()

def verify_bundle(path,expected_sha256=EXPECTED_SHA256):
    raw=Path(path).read_bytes()
    if digest(raw)!=expected_sha256:raise ValueError('Bundle SHA256 differs from the executed notebook receipt')
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names=[i.filename for i in archive.infolist()]
        if len(names)!=len(set(names)) or set(names)!=MEMBERS:raise ValueError('Unexpected or duplicate ZIP members')
        if any(i.file_size>30_000_000 for i in archive.infolist()):raise ValueError('Oversized ZIP member')
        files={name:archive.read(name) for name in names}
    manifest=json.loads(files['audit_manifest.json'])
    if set(manifest['files'])!=MEMBERS-{'audit_manifest.json'}:raise ValueError('Inner manifest file list differs')
    for name,receipt in manifest['files'].items():
        if len(files[name])!=receipt['bytes'] or digest(files[name])!=receipt['sha256']:
            raise ValueError(f'Inner checksum or byte size differs: {name}')
    if manifest['source_before']!=manifest['source_after']:raise ValueError('Source changed during extraction')
    if manifest['source_url']!='https://data.source.coop/portolan-mirrors/firms-catalog/detections/year=2023/detections.parquet':raise ValueError('Unexpected source')
    if manifest['coordinate_reference']!='OGC:CRS84' or manifest['year']!=2023:raise ValueError('Unexpected spatial/time contract')
    boundary=json.loads(files['region.geojson']);region=shapely.geometry.shape(boundary['features'][0]['geometry'])
    if digest(files['region.geojson'])!=manifest['boundary_sha256'] or not region.is_valid:raise ValueError('Boundary verification failed')
    points=pd.read_parquet(BytesIO(files['observations.parquet']))
    if len(points)!=13366 or any(manifest[key]!=len(points) for key in ['extracted_rows','direct_source_count','monthly_count_sum']):raise ValueError('Row reconciliation failed')
    if points.duplicated().any() or manifest['exact_duplicate_rows']!=0:raise ValueError('Duplicate observation rows')
    dates=pd.to_datetime(points.acq_datetime,utc=True)
    if not dates.dt.year.eq(2023).all() or not dates.dt.date.eq(pd.to_datetime(points.acq_date).dt.date).all():raise ValueError('Acquisition date/time mismatch')
    geometry=shapely.from_wkb(points.geometry_wkb.map(bytes).to_numpy())
    if not shapely.is_valid(geometry).all() or not shapely.covers(region,geometry).all():raise ValueError('Invalid or out-of-bound observations')
    if not np.allclose(shapely.get_x(geometry),points.audit_lon,rtol=0,atol=1e-9) or not np.allclose(shapely.get_y(geometry),points.audit_lat,rtol=0,atol=1e-9):raise ValueError('WKB/coordinate mismatch')
    totals=points.groupby('satellite').size().to_dict()
    if totals!=EXPECTED_TOTALS or not points.quality.eq('sp').all():raise ValueError('Satellite or quality totals differ')
    sensor={'Terra':'MODIS','Aqua':'MODIS','Suomi-NPP':'VIIRS_SNPP','NOAA-20':'VIIRS_NOAA20'}
    if not points.sensor.eq(points.satellite.map(sensor)).all():raise ValueError('Sensor provenance mismatch')
    modis=points.sensor.eq('MODIS')
    if not points.loc[modis,'confidence_pct'].between(0,100).all() or not points.loc[modis,'confidence'].astype(int).eq(points.loc[modis,'confidence_pct']).all():raise ValueError('Native MODIS confidence mismatch')
    if not points.loc[~modis,'confidence'].isin(['l','n','h']).all() or points.loc[~modis,'confidence_pct'].notna().any():raise ValueError('Native VIIRS confidence mismatch')
    monthly=pd.read_csv(BytesIO(files['monthly_observed_counts.csv']))
    expected=pd.MultiIndex.from_product([[f'2023-{i:02d}' for i in range(1,13)],SATELLITES],names=['month','satellite'])
    if monthly.duplicated(['month','satellite']).any() or set(map(tuple,monthly[['month','satellite']].values))!=set(expected):raise ValueError('Incomplete monthly filter grid')
    computed=points.assign(month=dates.dt.strftime('%Y-%m')).groupby(['month','satellite']).size().reindex(expected,fill_value=0)
    supplied=monthly.set_index(['month','satellite']).recorded_detections.reindex(expected)
    if not computed.eq(supplied).all() or not monthly.observing_coverage.eq('unverified').all():raise ValueError('Monthly counts or coverage labels differ')
    sensors=pd.read_csv(BytesIO(files['sensor_counts.csv'])).set_index(['satellite','sensor','quality']).recorded_detections.sort_index()
    if not sensors.equals(points.groupby(['satellite','sensor','quality']).size().sort_index().rename('recorded_detections')):raise ValueError('Sensor-count reconciliation failed')
    report={'status':'verified_extract','bundle_sha256':digest(raw),'run_id':manifest['run_id'],'rows':len(points),
        'satellite_totals':totals,'year':2023,'checks':['ZIP identity and member list','inner byte sizes and SHA256','unchanged source fingerprint','row/month/satellite reconciliation','no exact duplicates','UTC acquisition dates','native WKB coordinates and region membership','native confidence and quality'],
        'scope':'Sri Lanka, 2023; recorded detection observations per satellite',
        'observing_coverage_verified':False,'harmonization_applied':False,
        'source_url':manifest['source_url'],'source_fingerprint':manifest['source_before'],'boundary_sha256':manifest['boundary_sha256']}
    return points,manifest,boundary,report

def run(path=ROOT/'cindertrace_atlas_lk_2023_pilot.zip'):
    points,manifest,boundary,report=verify_bundle(path)
    out=ROOT/'web/atlas-public/atlas';out.mkdir(parents=True,exist_ok=True)
    dates=pd.to_datetime(points.acq_datetime,utc=True)
    def known(value):return None if pd.isna(value) else value.item() if isinstance(value,np.generic) else value
    rows=[]
    for i,row in enumerate(points.itertuples(index=False)):
        rows.append([int(dates.iloc[i].timestamp()),round(row.audit_lon,9),round(row.audit_lat,9),SATELLITES.index(row.satellite),
            known(row.frp),str(row.confidence),known(row.confidence_pct),known(row.type),known(row.scan),known(row.track)])
    metadata={'title':'Sri Lanka','year':2023,'unit':'recorded detections','satellites':SATELLITES,
        'source_name':'NASA FIRMS via Portolan mirror','source_url':manifest['source_url'],'source_snapshot':manifest['source_before'],
        'run_id':manifest['run_id'],'bundle_sha256':report['bundle_sha256'],'row_count':len(rows),
        'columns':['acquisition_utc_seconds','longitude','latitude','satellite_index','frp_mw','native_confidence','confidence_pct','published_type','scan_native','track_native'],
        'quality':'sp','observing_coverage':'unverified','harmonization_applied':False,'bounds':list(shapely.geometry.shape(boundary['features'][0]['geometry']).bounds)}
    for name,data in [('manifest.json',metadata),('observations.json',rows),('boundary.geojson',boundary),('verification.json',report),('audit_manifest.json',manifest)]:
        (out/name).write_text(json.dumps(data,separators=(',',':'),allow_nan=False)+'\n')
    shutil.copy2(path,out/'pilot_bundle.zip')
    (ROOT/'docs/atlas_bundle_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run()
