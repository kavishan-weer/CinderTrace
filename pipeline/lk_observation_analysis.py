"""Authenticate locally, download the bounded Sri Lanka pilot and read daily masks.
Passwords are prompted locally, never written by this module. Existing
local authentication can be reused; --login forces an interactive, nonpersistent
login. This screening does not certify swath/archive completeness or restore zeros.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import getpass
import os
import netrc
from http.cookiejar import CookieJar
import urllib.request
import urllib.error
import time
import http.client
import numpy as np
import pandas as pd
from shapely import contains_xy
from shapely.geometry import shape
from .harmonize import ROOT

PILOT_MONTHS=('2001-01','2002-01','2022-12','2023-12')
CLASSES={0:'missing_input',1:'obsolete_not_processed',2:'other_not_processed',3:'nonfire_water',
         4:'cloud',5:'nonfire_land',6:'unknown',7:'fire_low',8:'fire_nominal',9:'fire_high'}

class PilotError(RuntimeError):
    """A deliberately nonsecret diagnostic, safe to show in a terminal."""

def valid_download(path,record):
    if not path.exists():return False
    with path.open('rb') as f:signature=f.read(4)
    expected=round(record.get('size_mb_catalogue',0)*1048576)
    return signature==b'\x0e\x03\x13\x01' and (not expected or abs(path.stat().st_size-expected)<=2)

def download_one(record,target,session,attempts=4):
    name=record['download_url'].rsplit('/',1)[-1];path=target/name
    if valid_download(path,record):return path
    temp=path.with_suffix('.partial');reason='unknown transport failure'
    for attempt in range(1,attempts+1):
        try:
            request=urllib.request.Request(record['download_url'],headers={'Cache-Control':'no-cache'})
            with session.open(request,timeout=180) as response:
                if response.status!=200:raise PilotError(f'HTTP {response.status}')
                with temp.open('wb') as f:
                    while chunk:=response.read(128*1024):f.write(chunk)
            if not valid_download(temp,record):raise PilotError('incomplete file or unexpected response format')
            temp.replace(path)
            return path
        except urllib.error.HTTPError as error:
            reason=f'HTTP {error.code}'
        except (urllib.error.URLError,TimeoutError,http.client.HTTPException,OSError) as error:
            reason=type(error).__name__
        except PilotError as error:
            reason=str(error)
        finally:
            temp.unlink(missing_ok=True)
        if attempt<attempts:
            print(f'Retrying {name}: {reason} (attempt {attempt+1}/{attempts})',flush=True)
            time.sleep(min(2**attempt,8))
    raise PilotError(f'{name}: {reason} after {attempts} attempts. Verified files are cached. Re-run --login to resume.')


def select_files(manifest,months):
    chosen=[]
    for record in manifest['science_files']:
        first=pd.Timestamp(record['time_start']).tz_convert(None)
        last=pd.Timestamp(record['time_end']).tz_convert(None)
        if any(first<pd.Timestamp(m+'-01')+pd.offsets.MonthBegin(1) and last>=pd.Timestamp(m+'-01') for m in months):
            chosen.append(record)
    return chosen


def download(records,target,interactive=False):
    # Do not accidentally request input in an unattended agent/tool process.
    if interactive:
        if not sys.stdin.isatty():raise PilotError('Run --login directly in your local terminal.')
        username=input('Earthdata username: ')
        password=getpass.getpass('Earthdata password (hidden, not saved): ')
    else:
        if os.environ.get('EARTHDATA_USERNAME') and os.environ.get('EARTHDATA_PASSWORD'):
            username=os.environ['EARTHDATA_USERNAME'];password=os.environ['EARTHDATA_PASSWORD']
        else:
            try:configured=netrc.netrc().authenticators('urs.earthdata.nasa.gov')
            except (OSError,netrc.NetrcParseError):configured=None
            if not configured:raise PilotError('No local Earthdata authentication. Run this command with --login in your terminal.')
            username,_,password=configured
    target.mkdir(parents=True,exist_ok=True)
    # NASA's documented standard-library authentication method. Basic credentials
    # are scoped to the HTTPS Earthdata host; session cookies remain in memory.
    manager=urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None,'https://urs.earthdata.nasa.gov',username,password)
    session=urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(manager),
        urllib.request.HTTPCookieProcessor(CookieJar()))
    files=[]
    for i,r in enumerate(records,1):
        path=download_one(r,target,session);name=path.name
        files.append(dict(r,path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
        print(f'Downloaded/verified {i}/{len(records)}: {name}',flush=True)
    return files


def grid_geometry(metadata,nrows,ncols):
    def xy(field):
        match=re.search(rf'{field}\s*=\s*\(\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)\s*\)',metadata)
        if not match:raise ValueError(f'Missing {field} in HDF grid metadata')
        return tuple(map(float,match.groups()))
    x0,y0=xy('UpperLeftPointMtrs');x1,y1=xy('LowerRightMtrs')
    dx=(x1-x0)/ncols;dy=(y1-y0)/nrows
    if not dx>0 or not dy<0:raise ValueError('Unexpected grid orientation')
    return x0,y0,dx,dy


def spatial_mask(metadata,nrows,ncols,region):
    from pyproj import CRS,Transformer
    x0,y0,dx,dy=grid_geometry(metadata,nrows,ncols)
    inverse=Transformer.from_crs(CRS.from_proj4('+proj=sinu +R=6371007.181 +nadgrids=@null +wktext'),4326,always_xy=True)
    xx,yy=np.meshgrid(x0+(np.arange(ncols)+.5)*dx,y0+(np.arange(nrows)+.5)*dy)
    lon,lat=inverse.transform(xx,yy)
    return contains_xy(region,lon,lat)


def summarize_day(fire,qa,mask):
    values=(fire[mask].astype(np.uint8)&15)
    if np.any(values>9):raise ValueError('Unexpected fire-mask class')
    row={'region_pixels':int(mask.sum())}
    row.update({name:int((values==code).sum()) for code,name in CLASSES.items()})
    row['qa_land']=int(((qa[mask].astype(np.uint8)&3)==2).sum())
    row['qa_missing']=int(((qa[mask].astype(np.uint8)&3)==3).sum())
    row['fire_pixels']=sum(row[k] for k in ('fire_low','fire_nominal','fire_high'))
    usable=(np.isin(values,[3,5,7,8,9]))&((qa[mask].astype(np.uint8)&3)!=3)
    row['usable_class_pixels']=int(usable.sum())
    return row


def analyze(files,months):
    from pyhdf.SD import SD,SDC
    region=shape(json.loads((ROOT/'data/boundaries/lk_region.geojson').read_text())['features'][0]['geometry'])
    masks={};rows=[];dataset_info=[];seen_daily=set();exposure={}
    for record in files:
        path=ROOT/record['path'];hdf=SD(str(path),SDC.READ)
        try:
            names=hdf.datasets()
            if 'FireMask' not in names or 'QA' not in names:raise ValueError(f'FireMask/QA missing in {path.name}')
            fire=hdf.select('FireMask').get();qa=hdf.select('QA').get()
            if fire.ndim!=3 or fire.shape!=qa.shape or fire.shape[0]>8:
                raise ValueError(f'Unexpected daily grid dimensions {fire.shape}, {qa.shape}')
            metadata=hdf.attributes().get('StructMetadata.0','')
            tile=record['producer_granule_id'].split('.')[2]
            key=(tile,fire.shape[1:],metadata)
            if key not in masks:masks[key]=spatial_mask(metadata,*fire.shape[1:],region)
            mask=masks[key]
            start=pd.Timestamp(record['time_start']).tz_convert(None).normalize()
            # Final annual package can have fewer valid days than eight.
            end=pd.Timestamp(record['time_end']).tz_convert(None)
            for offset in range(fire.shape[0]):
                day=start+pd.Timedelta(days=offset)
                if day>end or day.strftime('%Y-%m') not in months:continue
                daily_key=(day,record['product'],tile)
                if daily_key not in seen_daily:
                    values=fire[offset][mask].astype(np.uint8)&15
                    usable=np.isin(values,[3,5,7,8,9])&((qa[offset][mask].astype(np.uint8)&3)!=3)
                    exposure_key=(day.strftime('%Y-%m'),record['product'],tile)
                    if exposure_key not in exposure:exposure[exposure_key]=np.zeros(len(values),dtype=np.uint16)
                    exposure[exposure_key]+=usable.astype(np.uint16)
                    seen_daily.add(daily_key)
                rows.append(dict(date=day,month=day.strftime('%Y-%m'),product=record['product'],tile=tile,
                    granule_id=record['id'],daily_content_sha256=hashlib.sha256(
                        fire[offset].tobytes()+qa[offset].tobytes()).hexdigest(),
                    **summarize_day(fire[offset],qa[offset],mask)))
            dataset_info.append({'file':path.name,'shape':list(fire.shape),'datasets':list(names),
                'fire_attributes':hdf.select('FireMask').attributes(),'qa_attributes':hdf.select('QA').attributes()})
        finally:hdf.end()
    frame=pd.DataFrame(rows)
    if frame.empty:raise ValueError('No daily observation rows in the pilot')
    keys=['date','product','tile']
    if frame.groupby(keys).daily_content_sha256.nunique().gt(1).any():
        raise PilotError('Conflicting daily fire-mask/QA bytes in overlapping packages; resolve before aggregation.')
    frame['equivalent_source_granules']=frame.groupby(keys).granule_id.transform(lambda ids:'|'.join(sorted(set(ids))))
    removed=int(frame.duplicated(keys).sum())
    frame=frame.drop_duplicates(keys).reset_index(drop=True)
    frame.attrs['identical_overlap_rows_removed']=removed
    support=[]
    for month,product in sorted({(m,p) for m,p,t in exposure}):
        days=np.concatenate([v for (m,p,t),v in exposure.items() if m==month and p==product])
        support.append({'month':month,'product':product,'region_pixels':len(days),
            'pixels_never_usable':int((days==0).sum()),'fraction_never_usable':float((days==0).mean()),
            'p10_usable_days':float(np.quantile(days,.1)),'median_usable_days':float(np.median(days)),
            'p90_usable_days':float(np.quantile(days,.9)),
            'unit':'distinct daily composites with usable classification per selected regional pixel'})
    frame.attrs['spatial_observation_support']=support
    return frame,dataset_info


def run(args):
    manifest_path=ROOT/'docs/lk_observation_pilot.json';manifest=json.loads(manifest_path.read_text())
    months=args.months.split(',') if args.months else list(PILOT_MONTHS)
    available={r['month'] for r in manifest['monthly_inventory']}
    if not set(months)<=available:raise ValueError('Months must belong to the public discovery manifest')
    records=select_files(manifest,months)
    base=ROOT/'data/observation_pilot/lk';cache=base/'science_files'
    output=base/('analysis_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));output.mkdir(parents=True,exist_ok=False)
    if args.analyze_only:
        files=[]
        for r in records:
            p=cache/r['download_url'].rsplit('/',1)[-1]
            if not p.exists():raise ValueError('Missing cached file; complete authenticated download first')
            files.append(dict(r,path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
    else:files=download(records,cache,interactive=args.login)
    (output/'download_manifest.json').write_text(json.dumps({'months':months,'files':files},indent=2)+'\n')
    daily,details=analyze(files,months)
    daily.to_parquet(output/'daily_tile_counts.parquet',index=False)
    (output/'science_dataset_metadata.json').write_text(json.dumps(details,indent=2)+'\n')
    numeric=['region_pixels',*CLASSES.values(),'qa_land','qa_missing','fire_pixels','usable_class_pixels']
    daily_regional=daily.groupby(['date','month','product'])[numeric].sum().reset_index()
    monthly=daily_regional.groupby(['month','product'])[numeric].sum().reset_index()
    days=daily_regional.groupby(['month','product']).date.nunique()
    summary=[]
    local=pd.read_parquet(ROOT/'data/harmonized/lk_coverage.parquet')
    for row in monthly.to_dict('records'):
        key=(row['month'],row['product']);row['days_with_catalogued_layers']=int(days.loc[key])
        row['calendar_days']=int(pd.Timestamp(row['month']+'-01').days_in_month)
        expected_tiles={r['producer_granule_id'].split('.')[2] for r in manifest['science_files'] if r['product']==row['product']}
        row['expected_tile_days']=row['calendar_days']*len(expected_tiles)
        row['received_tile_days']=int(len(daily[(daily.month==row['month'])&(daily['product']==row['product'])]))
        row['tile_day_layers_complete']=row['received_tile_days']==row['expected_tile_days']
        row['usable_class_fraction']=row['usable_class_pixels']/row['region_pixels'] if row['region_pixels'] else None
        match=local[(local.fam=='modis')&(local.month==pd.Timestamp(row['month']+'-01'))]
        row['local_combined_modis_bbox_detections']=int(match.detections.iloc[0]) if len(match) else None
        row['status']='screening_only_not_archive_certification';summary.append(row)
    report={'months':months,'science_files':len(files),'monthly_screening':summary,'production_changes':False,
        'identical_overlap_tile_day_rows_removed':daily.attrs.get('identical_overlap_rows_removed',0),
        'spatial_observation_support':daily.attrs.get('spatial_observation_support',[]),
        'limits':['Pixel/day counts from daily L3 composites are not detections, overpasses or production H3 cell-days.',
            'A daily class cannot recover all observations or cloud states within that day.',
            'Presence of every tile/day layer does not prove complete swath ingestion.',
            'Usable-class fraction is reported, not silently thresholded into a verified-zero decision.',
            'Swath reconciliation and quality review remain necessary before any zero restoration.'],
        'source_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'analysis_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'inputs':[]}
    source_paths=[ROOT/'data/boundaries/lk_region.geojson',ROOT/'data/harmonized/lk_coverage.parquet']
    source_paths.extend(ROOT/f'data/raw/lk/{year}.parquet' for year in sorted({m[:4] for m in months}))
    report['inputs']=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source_paths]
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    (ROOT/'docs/lk_observation_pixel_screening.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('Pilot analysis saved:',output,flush=True)
    for row in summary:print(row['month'],row['product'],'fire pixels',row['fire_pixels'],'usable-class fraction',round(row['usable_class_fraction'],3))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login',action='store_true',help='Prompt for Earthdata credentials locally; do not persist them')
    parser.add_argument('--analyze-only',action='store_true',help='Read already downloaded science files, without authentication')
    parser.add_argument('--months',help='Comma-separated months from the discovery manifest; defaults to the four-month pilot')
    args=parser.parse_args()
    try:run(args)
    except PilotError as error:
        print(f'Pilot stopped: {error} No credentials were saved.',file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # No exception strings from authentication clients, signed URLs or cookies
        # are exposed. Preserve only the failure type for local troubleshooting.
        print(f'Pilot stopped ({type(error).__name__}). No credentials were saved. Check login, authorized data access and the input files.',file=sys.stderr)
        sys.exit(1)
