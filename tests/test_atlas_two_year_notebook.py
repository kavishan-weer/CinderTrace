"""Run the actual notebook offline, with explicit simulated data and no live API credentials."""
import ast,contextlib,io,json,tempfile,types,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse
import pandas as pd
from pipeline.import_atlas_pilot import verify_bundle,ROOT

class Reply:
    def __init__(self,raw=b'',headers=None):self.raw=raw;self.headers=headers or {}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return self.raw

class FakeDuckDB:
    def __init__(self,frames):self.frames=frames;self.value=None
    def execute(self,sql,params=None):
        if sql.startswith('DESCRIBE'):
            self.value=pd.DataFrame({'column_name':['geometry','acq_date'],'column_type':["GEOMETRY('OGC:CRS84')",'DATE']})
        elif params:
            year=int(params[1][:4]);self.value=len(self.frames[year]) if 'count(*)' in sql else self.frames[year].copy()
        return self
    def df(self):return self.value
    def fetchone(self):return (self.value,)
    def close(self):pass

class ExpansionNotebookTests(unittest.TestCase):
    def test_partial_archive_and_retained_nrt(self):
        self.exercise(True)

    def test_absent_noaa21_standard_source_remains_unreconciled(self):
        self.exercise(False)

    def exercise(self,advertise_noaa21):
        notebook=json.loads((ROOT/'notebooks/CinderTrace_Atlas_LK_2022_2024_Check.ipynb').read_text())
        for cell in notebook['cells']:
            if cell['cell_type']=='code' and not ''.join(cell['source']).startswith('%'):ast.parse(''.join(cell['source']))
        original,*_=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip');frames={}
        for year in [2022,2024]:
            parts=[]
            for i,satellite in enumerate(['Terra','Aqua','Suomi-NPP','NOAA-20']):
                f=original[original.satellite.eq(satellite)].head(2).copy();f['acq_datetime']=pd.to_datetime([f'{year}-01-{4+i:02} 07:30:00',f'{year}-08-{4+i:02} 19:30:00']);parts.append(f)
            if year==2024:
                for date,quality in [('2024-01-20','sp'),('2024-01-05','sp'),('2024-03-01','nrt')]:
                    f=original[original.satellite.eq('Suomi-NPP')].head(1).copy();f['satellite']='NOAA-21';f['sensor']='VIIRS_NOAA21';f['quality']=quality;f['version']='2' if quality=='sp' else '2.0NRT';f['type']=0 if quality=='sp' else pd.NA;f['acq_datetime']=pd.Timestamp(date+' 07:00:00');parts.append(f)
                f=original[original.satellite.eq('NOAA-20')].head(1).copy();f['acq_datetime']=pd.Timestamp('2024-02-29 07:30:00');parts.append(f)
            frame=pd.concat(parts,ignore_index=True);frame['year']=year;frame['acq_date']=pd.to_datetime(frame.acq_datetime).dt.normalize();frames[year]=frame
        calls=[]
        def respond(request,timeout=0):
            url=request.full_url
            if request.get_method()=='HEAD':return Reply(headers={'ETag':'"test-only-snapshot"','Content-Length':'100','Last-Modified':'Sat, 14 Nov 2026 00:00:00 GMT'})
            if 'data_availability' in url:
                raw=b'data_id,min_date,max_date\nMODIS_SP,2000-11-01,2025-12-31\nVIIRS_SNPP_SP,2012-01-20,2025-12-31\nVIIRS_NOAA20_SP,2018-04-01,2025-12-31\nVIIRS_NOAA21_SP,2024-01-17,2025-12-31\n'
                if not advertise_noaa21:raw=raw.split(b'VIIRS_NOAA21_SP')[0]
                return Reply(raw)
            if 'action=fetch_data' in url:return Reply(json.dumps({'success':True,'html':'<tr><td>2022-07-28</td><td>Suomi NPP (VIIRS)</td><td></td><td></td></tr>'}).encode())
            if 'outages_suomi_npp.html' in url:return Reply(b'<tr><td>2022-207 - 2022-208</td><td>dates</td><td>16:00:00</td><td>15:48:00</td><td>gap</td></tr><tr><td>2024-307 - 2024-311</td><td>dates</td><td>22:12:00</td><td>17:36:00</td><td>gap</td></tr>')
            if 'outages_terra.html' in url:return Reply(b'<tr><td>2022-283 - 2022-296</td><td>dates</td><td>13:00:00</td><td>22:35:00</td><td>gap</td></tr>')
            if '/content/notifications/' in url:return Reply(b'<html>Simulated notice snapshot; not live evidence.</html>')
            if '/api/area/csv/' not in url:raise AssertionError('Unexpected network destination')
            parts=urlparse(url).path.split('/');source=parts[5];a=pd.Timestamp(parts[8]);b=a+pd.Timedelta(days=int(parts[7]));year=a.year
            platforms={'MODIS_SP':['Terra','Aqua'],'VIIRS_SNPP_SP':['Suomi-NPP'],'VIIRS_NOAA20_SP':['NOAA-20'],'VIIRS_NOAA21_SP':['NOAA-21']}[source]
            f=frames[year];f=f[f.satellite.isin(platforms)&f.quality.eq('sp')&f.acq_datetime.ge(a)&f.acq_datetime.lt(b)].copy()
            f=f.rename(columns={'audit_lat':'latitude','audit_lon':'longitude'})
            f['acq_date']=f.acq_datetime.dt.strftime('%Y-%m-%d');f['acq_time']=f.acq_datetime.dt.strftime('%H%M')
            f['satellite']=f.satellite.map({'Terra':'T','Aqua':'A','Suomi-NPP':'N','NOAA-20':'N20','NOAA-21':'N21'})
            columns=['latitude','longitude','acq_date','acq_time','satellite','instrument','confidence','version','type','frp','scan','track','daynight','brightness','bright_t31','bright_ti4','bright_ti5']
            calls.append((source,str(a.date())))
            return Reply(f[columns].to_csv(index=False).encode())
        with tempfile.TemporaryDirectory() as tmp:
            def execute():
                namespace={'__name__':'simulated_notebook_test'}
                with patch.dict('sys.modules',{'duckdb':types.SimpleNamespace(__version__='1.5.6',connect=lambda:FakeDuckDB(frames))}),patch('urllib.request.urlopen',respond),patch('getpass.getpass',return_value='fixtureprivatekey0000000000000000'),patch('time.sleep',lambda x:None),contextlib.redirect_stdout(io.StringIO()):
                    for cell in notebook['cells']:
                        if cell['cell_type']!='code':continue
                        src=''.join(cell['source'])
                        if src.startswith('%'):continue
                        src=src.replace('from IPython.display import display','display=lambda value:None').replace("BASE=Path.cwd()/'atlas_lk_2022_2024'",f'BASE=Path({tmp!r})')
                        exec(compile(src,'expansion_notebook','exec'),namespace)
                return namespace
            ns=execute();self.assertEqual(len(calls),511 if advertise_noaa21 else 441)
            self.assertEqual(ns['COMPARISONS']['2022']['status'],'matched_native_records')
            self.assertEqual(ns['COMPARISONS']['2024']['status'],'matched_native_records')
            self.assertEqual(ns['COMPARISONS']['2024']['mirror_rows_not_reconciled'],2 if advertise_noaa21 else 3)
            self.assertEqual(ns['COMPARISONS']['2024']['scope_completeness'],'partial_by_advertised_archive_dates')
            daily=ns['DAILY'];self.assertEqual(len(daily),3290);self.assertEqual(len(daily[daily.date.eq('2024-02-29')]),5)
            before=daily[daily.satellite.eq('NOAA-21')&daily.date.lt('2024-01-17')]
            self.assertTrue(before.official_sp_detections.isna().all())
            self.assertTrue(daily.coverage_adjusted_activity.isna().all())
            execute();self.assertEqual(len(calls),511 if advertise_noaa21 else 441,'Resume must reuse verified requests')
            with zipfile.ZipFile(ns['ZIP_PATH']) as z:
                manifest=json.loads(z.read('checkpoint_manifest.json'))
                self.assertEqual(manifest['completed_requests'],511 if advertise_noaa21 else 441)
                for name,receipt in manifest['files'].items():
                    raw=z.read(name)
                    import hashlib
                    self.assertEqual(len(raw),receipt['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),receipt['sha256'])
                    self.assertNotIn(b'fixtureprivatekey0000000000000000',raw)
