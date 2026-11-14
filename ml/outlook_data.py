"""Explicitly fetch/cache NASA POWER daily weather and NOAA ONI/DMI history.

python -m ml.outlook_data --fetch
No future weather or climate forecasts are used. Revisions are not historical vintages.
"""
import argparse
import calendar
import concurrent.futures
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from urllib.request import Request,urlopen

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from .events import ROOT,file_sha

BASE=ROOT/'data/outlook'
PARAMS=['T2M','PRECTOTCORR','RH2M','WS2M']
CLIMATE={
 'oni':'https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt',
 'dmi':'https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data',
}
SEASONS=['DJF','JFM','FMA','MAM','AMJ','MJJ','JJA','JAS','ASO','SON','OND','NDJ']


def choose_sites(members,n=5):
    """Five static area-weighted spatial strata, independent of fire activity."""
    lat0=members.lat.mean();xy=np.column_stack([members.lon*np.cos(np.radians(lat0)),members.lat])
    fit=KMeans(n_clusters=n,n_init=10,random_state=42).fit(xy,sample_weight=members.area_km2)
    sites=[]
    for label in range(n):
        indices=np.flatnonzero(fit.labels_==label);distance=((xy[indices]-fit.cluster_centers_[label])**2).sum(axis=1)
        selected=members.iloc[indices[np.argmin(distance)]]
        sites.append(dict(lat=float(selected.lat),lon=float(selected.lon),weight=float(members.iloc[indices].area_km2.sum()/members.area_km2.sum())))
    return sorted(sites,key=lambda s:(s['lat'],s['lon']))


def cached_download(url,path,refresh=False):
    meta=path.with_suffix(path.suffix+'.provenance.json')
    if path.exists() and meta.exists() and not refresh:
        saved=json.loads(meta.read_text())
        if saved['url']==url and saved['sha256']==file_sha(path):return path.read_bytes()
    with urlopen(Request(url,headers={'User-Agent':'EMBERLINE-outlook-research/1.0'}),timeout=180) as response:body=response.read()
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(body);temp.replace(path)
    meta.write_text(json.dumps({'url':url,'retrieved_utc':pd.Timestamp.now(tz='UTC').isoformat(),'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)},indent=2))
    return body


def parse_power(body):
    data=json.loads(body)
    if 'properties' not in data or 'parameter' not in data['properties']:raise ValueError('POWER did not return daily parameters.')
    if data['header'].get('time_standard')!='UTC':raise ValueError('Expected UTC POWER weather.')
    expected={'T2M':'C','PRECTOTCORR':'mm/day','RH2M':'%','WS2M':'m/s'}
    if any(data['parameters'][p]['units']!=unit for p,unit in expected.items()):raise ValueError('Unexpected POWER parameter units.')
    frame=pd.DataFrame(data['properties']['parameter'])[PARAMS]
    frame.index=pd.to_datetime(frame.index,format='%Y%m%d');frame=frame.sort_index().astype(float)
    frame=frame.mask(frame==float(data['header'].get('fill_value',-999)))
    frame=frame.where(np.isfinite(frame))
    # Physical invalids are missing, never replaced with zero.
    frame.loc[(frame.PRECTOTCORR<0)|(frame.RH2M<0)|(frame.RH2M>100)|(frame.WS2M<0),:]=np.nan
    rows=[]
    for month,g in frame.groupby(frame.index.to_period('M')):
        days=calendar.monthrange(month.year,month.month)[1]
        complete=len(g)==days and g.index.nunique()==days and g.notna().all().all()
        rows.append(dict(month=month.to_timestamp(),complete=bool(complete),days=len(g),
          temperature_c=float(g.T2M.mean()) if complete else np.nan,
          rain_mm=float(g.PRECTOTCORR.sum()) if complete else np.nan,
          humidity_pct=float(g.RH2M.mean()) if complete else np.nan,
          wind_mps=float(g.WS2M.mean()) if complete else np.nan))
    return pd.DataFrame(rows).set_index('month')


def parse_oni(text):
    rows=[]
    for line in text.splitlines():
        parts=line.split()
        if len(parts)==4 and parts[0] in SEASONS:
            value=float(parts[3]);month=SEASONS.index(parts[0])+1
            rows.append((pd.Timestamp(int(parts[1]),month,1),value if abs(value)<90 else np.nan))
    if not rows:raise ValueError('No ONI seasons parsed.')
    series=pd.Series(dict(rows),name='oni').sort_index()
    if len(series)!=len(rows):raise ValueError('Duplicate ONI centre months.')
    return series


def parse_dmi(text):
    rows=[]
    for line in text.splitlines():
        parts=line.split()
        if len(parts)==13 and parts[0].isdigit() and 1800<=int(parts[0])<=2200:
            for month,value in enumerate(parts[1:],1):
                number=float(value);rows.append((pd.Timestamp(int(parts[0]),month,1),number if abs(number)<90 else np.nan))
    if not rows:raise ValueError('No DMI monthly records parsed.')
    return pd.Series(dict(rows),name='dmi').sort_index()


def fetch_weather(region,start,end,refresh=False):
    members_path=ROOT/f'data/boundaries/{region}_members.parquet';members=pd.read_parquet(members_path)
    sites=choose_sites(members)
    site_spec={'region':region,'method':'5 fixed area-weighted KMeans strata / nearest member centre / seed 42','members_sha256':file_sha(members_path),'sites':sites}
    directory=BASE/'inputs'/region;directory.mkdir(parents=True,exist_ok=True)
    (directory/'sites.json').write_text(json.dumps(site_spec,indent=2))
    frames=[]
    for i,site in enumerate(sites):
        args=dict(parameters=','.join(PARAMS),community='AG',latitude=f"{site['lat']:.5f}",longitude=f"{site['lon']:.5f}",start=start,end=end,format='JSON',**{'time-standard':'UTC'})
        url='https://power.larc.nasa.gov/api/temporal/daily/point?'+urlencode(args)
        body=cached_download(url,directory/f'power-site-{i}.json',refresh)
        frame=parse_power(body);frame['site']=i;frame['weight']=site['weight'];frames.append(frame)
        print(f'{region} weather site {i+1}/5: {int(frame.complete.sum())} complete months',flush=True)
    combined=pd.concat(frames).reset_index();output=[]
    for month,g in combined.groupby('month'):
        complete=len(g)==len(sites) and g.complete.all()
        record={'month':month,'complete':bool(complete),'sites_present':len(g)}
        for col in ['temperature_c','rain_mm','humidity_pct','wind_mps']:
            record[col]=float((g[col]*g.weight).sum()) if complete else np.nan
        output.append(record)
    result=pd.DataFrame(output);result.to_parquet(directory/'weather-monthly.parquet',index=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--fetch',action='store_true');parser.add_argument('--refresh',action='store_true');parser.add_argument('--regions',nargs='+',default=['lk','ca','nsw']);parser.add_argument('--start',default='20110101');parser.add_argument('--end')
    args=parser.parse_args()
    if not args.fetch:parser.error('Use --fetch for explicit public-source downloads.')
    if any(r not in ['lk','ca','nsw'] for r in args.regions):raise ValueError('Unsupported region.')
    today=pd.Timestamp(datetime.now(ZoneInfo('Asia/Colombo')).date());last=today.replace(day=1)-pd.Timedelta(days=1)
    end=args.end or last.strftime('%Y%m%d')
    climate={}
    for name,url in CLIMATE.items():
        body=cached_download(url,BASE/f'inputs/{name}.txt',args.refresh)
        climate[name]=(parse_oni if name=='oni' else parse_dmi)(body.decode())
    pd.concat(climate.values(),axis=1).rename_axis('month').reset_index().to_parquet(BASE/'inputs/climate-monthly.parquet',index=False)
    # NASA requests are sequential within each region; at most three concurrent.
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        jobs=[executor.submit(fetch_weather,r,args.start,end,args.refresh) for r in args.regions]
        for job in jobs:job.result()


if __name__=='__main__':main()
