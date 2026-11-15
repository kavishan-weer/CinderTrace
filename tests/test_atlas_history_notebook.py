"""Exercise the generated earlier-history notebook using simulated public responses only."""
import ast,contextlib,io,json,tempfile,types,unittest,zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from unittest.mock import patch
import pandas as pd
from pipeline.import_atlas_pilot import ROOT,verify_bundle
from test_atlas_two_year_notebook import Reply,FakeDuckDB

class HistoryNotebookTests(unittest.TestCase):
    def test_partial_failure_resumes_same_batch_and_packs_each_year(self):
        notebook=json.loads((ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb').read_text())
        for cell in notebook['cells']:
            if cell['cell_type']=='code' and not ''.join(cell['source']).startswith('%'):ast.parse(''.join(cell['source']))
        original,*_=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip');frames={}
        for year in [2000,2001,2002]:
            parts=[]
            dates=['2000-11-05','2000-12-15'] if year==2000 else [f'{year}-01-05',f'{year}-08-05']
            for date in dates:
                f=original[original.satellite.eq('Terra')].head(1).copy();f['acq_datetime']=pd.Timestamp(date+' 04:30:00');parts.append(f)
            if year==2000:
                f=original[original.satellite.eq('Terra')].head(1).copy();f['acq_datetime']=pd.Timestamp('2000-10-05 04:30:00');parts.append(f)
                f=f.copy();f['acq_datetime']=pd.Timestamp('2000-11-22 04:30:00');f['quality']='nrt';f['version']='6.1NRT';f['type']=pd.NA;parts.append(f)
            if year==2002:
                for date in ['2002-07-04','2002-09-04']:
                    f=original[original.satellite.eq('Aqua')].head(1).copy();f['acq_datetime']=pd.Timestamp(date+' 08:10:00');parts.append(f)
            frame=pd.concat(parts,ignore_index=True);frame['acq_date']=pd.to_datetime(frame.acq_datetime).dt.normalize();frame['year']=year;frames[year]=frame
        successful=[];faults=[];interrupt={'enabled':True}
        def response(request,timeout=0):
            url=request.full_url
            if request.get_method()=='HEAD':return Reply(headers={'ETag':'"simulated-history"','Content-Length':'100','Last-Modified':'Sat, 14 Nov 2026 00:00:00 GMT'})
            if 'data_availability' in url:return Reply(b'data_id,min_date,max_date\nMODIS_SP,2000-11-01,2025-12-31\nVIIRS_SNPP_SP,2012-01-20,2025-12-31\nVIIRS_NOAA20_SP,2018-04-01,2025-12-31\n')
            if 'action=fetch_data' in url:return Reply(json.dumps({'success':True,'html':'<tr><td>2001-02-01</td><td>Terra (MODIS)</td><td></td><td></td></tr>'}).encode())
            if 'outages_suomi_npp' in url:return Reply(b'')
            if 'outages_terra' in url:return Reply(b'<tr><td>2001-001</td><td>date</td><td>12:00:00</td><td>11:00:00</td><td>unparseable window</td></tr>')
            if '/content/notifications/' in url:return Reply(b'<html>Simulated notice; not live evidence.</html>')
            if '/api/area/csv/' not in url:raise AssertionError('Unexpected destination')
            parts=urlparse(url).path.split('/');source=parts[5];a=pd.Timestamp(parts[8]);b=a+pd.Timedelta(days=int(parts[7]))
            if str(a.date())=='2001-02-05' and interrupt['enabled']:
                faults.append(str(a.date()));raise HTTPError(url,403,'simulated interruption',None,None)
            f=frames[a.year];f=f[f.quality.eq('sp')&f.acq_datetime.ge(a)&f.acq_datetime.lt(b)].copy()
            f=f.rename(columns={'audit_lat':'latitude','audit_lon':'longitude'});f['acq_date']=f.acq_datetime.dt.strftime('%Y-%m-%d');f['acq_time']=f.acq_datetime.dt.strftime('%H%M')
            f['satellite']=f.satellite.map({'Terra':'T','Aqua':'A'})
            cols=['latitude','longitude','acq_date','acq_time','satellite','instrument','confidence','version','type','frp','scan','track','daynight','brightness','bright_t31']
            successful.append((source,str(a.date())))
            return Reply(f[cols].to_csv(index=False).encode())
        with tempfile.TemporaryDirectory() as tmp:
            def execute():
                ns={'__name__':'simulated_history_notebook'}
                with patch.dict('sys.modules',{'duckdb':types.SimpleNamespace(__version__='1.5.6',connect=lambda:FakeDuckDB(frames))}),patch('urllib.request.urlopen',response),patch('getpass.getpass',return_value='fixturehistoryprivate000000000000'),patch('time.sleep',lambda x:None),contextlib.redirect_stdout(io.StringIO()):
                    for cell in notebook['cells']:
                        if cell['cell_type']!='code':continue
                        code=''.join(cell['source'])
                        if code.startswith('%'):continue
                        code=code.replace('from IPython.display import display','display=lambda value:None').replace("BASE=Path.cwd()/'atlas_lk_history_2000_2021'",f'BASE=Path({tmp!r})')
                        exec(compile(code,'simulated_history_notebook','exec'),ns)
                return ns
            with self.assertRaisesRegex(RuntimeError,'HTTP 403') as failure:execute()
            self.assertNotIn('fixturehistoryprivate',str(failure.exception));self.assertEqual(len(faults),1)
            run=Path(tmp)/(Path(tmp)/'active_run.txt').read_text().strip()
            self.assertTrue((run/'years/2000/year_manifest.json').is_file());self.assertFalse((run/'years/2001/year_manifest.json').exists())
            self.assertEqual(json.loads((run/'active_batch.json').read_text()),[2000,2001,2002])
            interrupt['enabled']=False;ns=execute()
            self.assertEqual(ns['NEXT_YEARS'],[2000,2001,2002]);self.assertEqual(ns['progress']['completed_years'],[2000,2001,2002])
            self.assertEqual(len(successful),159);self.assertEqual(len(set(successful)),159,'Verified windows must not be downloaded twice')
            self.assertFalse((run/'years/2003').exists());self.assertFalse((run/'years/2022').exists())
            for year,count in [(2000,2),(2001,2),(2002,4)]:
                folder=run/'years'/str(year);m=json.loads((folder/'year_manifest.json').read_text());self.assertEqual(m['canonical_standard_rows'],count)
                self.assertFalse(m['coverage_verified']);self.assertFalse(m['frontend_changed'])
                p=pd.read_parquet(folder/'observations_standard.parquet');self.assertTrue(p.quality.eq('sp').all());self.assertFalse(p.observation_id.duplicated().any())
                self.assertIn('source_row_ordinal',p.columns)
                daily=pd.read_parquet(folder/'daily_status.parquet')
                self.assertTrue(daily[daily.satellite.isin(['Suomi-NPP','NOAA-20'])].recorded_detections.isna().all())
                z=next(run.glob(f'cindertrace_atlas_lk_history_{year}_*.zip'))
                with zipfile.ZipFile(z) as archive:
                    self.assertEqual(set(archive.namelist()),set(m['files'])|{'year_manifest.json'})
                    for name,r in m['files'].items():
                        raw=archive.read(name);import hashlib
                        self.assertEqual(len(raw),r['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),r['sha256'])
                        self.assertNotIn(b'fixturehistoryprivate000000000000',raw)
            excluded=pd.read_parquet(run/'years/2000/mirror_not_reconciled.parquet');self.assertEqual(len(excluded),2)
            self.assertEqual(set(excluded.not_reconciled_reason),{'NRT_audit_only','outside_advertised_standard_interval'})
            aqua=pd.read_parquet(run/'years/2002/monthly_status.parquet').query("satellite=='Aqua' and month=='2002-07'").iloc[0]
            self.assertEqual(aqua.detections_on_queried_dates,1);self.assertTrue(pd.isna(aqua.full_month_standard_detections))
            self.assertEqual(len(pd.read_parquet(run/'unparsed_outage_evidence.parquet')),1)
