"""Download attributed, dated NASA GIBS example frames; reject invalid images."""
import concurrent.futures,hashlib,http.client,json,urllib.request
from pathlib import Path
from io import BytesIO
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'web/site-public/context'
CASES={'lk':('2023-07-15','2023-08-15',[79.65,5.92,81.88,9.84]),'ca':('2020-09-03','2020-09-08',[-119.65,36.8,-118.7,37.8]),'nsw':('2019-11-01','2019-12-31',[149.3,-36.8,153.7,-31.2])}
def job(item):
 rid,(before,after,bbox)=item;result={'before':before,'after':after,'bbox':bbox,'layer':'terra','width':1000,'height':800,'source':'NASA GIBS / MODIS daily corrected-reflectance true colour','requests':[]}
 for label,date in [('before',before),('after',after)]:
  file=f'imagery-{rid}-{label}.jpg';path=OUT/file
  url='https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor&STYLES=&FORMAT=image/jpeg&SRS=EPSG:4326&BBOX='+','.join(map(str,bbox))+'&WIDTH=1000&HEIGHT=800&TIME='+date
  if path.exists():raw=path.read_bytes()
  else:
   with urllib.request.urlopen(url,timeout=70) as r:
    try:raw=r.read()
    except http.client.IncompleteRead as e:raw=e.partial
   im=Image.open(BytesIO(raw));im.verify();path.write_bytes(raw)
  result[label+'_file']=file;result['requests'].append({'date':date,'url':url,'sha256':hashlib.sha256(raw).hexdigest()});print(rid,label,len(raw),flush=True)
 return rid,result
if __name__=='__main__':
 OUT.mkdir(exist_ok=True,parents=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=dict(pool.map(job,CASES.items()))
 (OUT/'imagery-presets.json').write_text(json.dumps(results,indent=2))
