"""Single-download packaging and fixed-cell orchestration, without data retrieval."""
from pathlib import Path
import contextlib,hashlib,io,json,re,tempfile,types,unittest,zipfile
from unittest.mock import patch
from pipeline.atlas_history import HISTORY_YEARS,digest,verify_year_files
from pipeline.atlas_history_bundle import collect_history_bundle,run_fixed_history_batch
from pipeline.import_atlas_pilot import ROOT

class HistoryDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name);self.calls=[];self.run_id='simulated_batch_run'
        self.contract={'run_id':self.run_id,'target_years':HISTORY_YEARS}
        (self.out/'run_contract.json').write_text(json.dumps(self.contract))
        for name in ['region.geojson','official_history_plan.parquet','documented_global_gaps.parquet','upstream_missing_standard_dates.parquet','unparsed_outage_evidence.parquet']:(self.out/name).write_bytes(b'simulated shared evidence')
        (self.out/'snapshots').mkdir();(self.out/'snapshots/source.json').write_bytes(b'{"test_snapshot":true}')
        (self.out/'private_unrelated.txt').write_bytes(b'MUST_NOT_BE_BUNDLED')
    def process(self,year):
        self.calls.append(year);folder=self.out/'years'/str(year);folder.mkdir(parents=True)
        raw=f'simulated year {year}'.encode();(folder/'observations.parquet').write_bytes(raw)
        m={'year':year,'run_contract_sha256':digest((self.out/'run_contract.json').read_bytes()),'canonical_standard_rows':year-1999,'completed_utc':'2026-11-15T00:00:00+00:00',
          'files':{'observations.parquet':{'bytes':len(raw),'sha256':digest(raw)}}}
        (folder/'year_manifest.json').write_text(json.dumps(m));return self.package(folder)
    def package(self,folder):
        m=verify_year_files(folder);year=m['year'];name=f'cindertrace_atlas_lk_history_{year}_{self.run_id}.zip';p=self.out/name
        with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
            for name_in_zip in [*m['files'],'year_manifest.json']:z.write(folder/name_in_zip,name_in_zip)
        r={'year':year,'zip_name':name,'bytes':p.stat().st_size,'sha256':digest(p.read_bytes()),'canonical_standard_rows':m['canonical_standard_rows'],'completed_utc':m['completed_utc']}
        (self.out/f'year_{year}_zip_receipt.json').write_text(json.dumps(r));return r
    def test_partial_one_file_has_explicit_remaining_years_and_only_selected_files(self):
        for year in [2000,2001,2002]:self.process(year)
        with self.assertRaisesRegex(ValueError,'incomplete'):collect_history_bundle(self.out,HISTORY_YEARS,self.package,{},require_all=True)
        r=collect_history_bundle(self.out,HISTORY_YEARS,self.package,{},require_all=False)
        self.assertEqual(r['manifest']['capture_status'],'partial_capture');self.assertEqual(r['manifest']['completed_years'],[2000,2001,2002])
        self.assertEqual(r['manifest']['remaining_years'][0],2003)
        with zipfile.ZipFile(r['path']) as z:
            self.assertEqual(set(z.namelist()),set(r['manifest']['files'])|{'bundle_manifest.json'})
            self.assertNotIn('private_unrelated.txt',z.namelist())
            for name,receipt in r['manifest']['files'].items():
                raw=z.read(name);self.assertEqual(len(raw),receipt['bytes']);self.assertEqual(digest(raw),receipt['sha256'])
            self.assertEqual(len([n for n in z.namelist() if n.startswith('year_zips/')]),3)
    def test_corrupt_year_zip_is_rejected_before_bundling(self):
        r=self.process(2000);(self.out/r['zip_name']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'ZIP changed'):collect_history_bundle(self.out,HISTORY_YEARS,self.package,{},require_all=False)
    def test_new_notebook_runs_all_fixed_cells_and_triggers_one_download(self):
        for year in [2000,2001,2002]:self.process(year)
        self.calls=[];downloads=[]
        ns={'OUT':self.out,'HISTORY_YEARS':HISTORY_YEARS,'process_year':self.process,'package_year':self.package,
            'verify_year_files':verify_year_files,'digest':digest,'BENCHMARK_REFERENCE':{'test':'immutable'},'IN_COLAB':True}
        google=types.ModuleType('google');google.__path__=[];colab=types.ModuleType('google.colab');colab.files=types.SimpleNamespace(download=lambda p:downloads.append(p))
        book=json.loads((ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_All_Batches.ipynb').read_text())
        batch_count=0
        with patch.dict('sys.modules',{'google':google,'google.colab':colab}),contextlib.redirect_stdout(io.StringIO()):
            for cell in book['cells']:
                if cell['cell_type']!='code':continue
                source=''.join(cell['source'])
                if 'def verified_year_zip(' in source or source.startswith('def run_history_batch(') or source.startswith('batch_') or source.startswith('FINAL_BUNDLE='):
                    exec(compile(source,'single_download_notebook','exec'),ns)
                    if source.startswith('batch_'):batch_count+=1
        self.assertEqual(batch_count,8);self.assertEqual(self.calls,list(range(2003,2022)));self.assertEqual(len(downloads),1)
        result=ns['FINAL_BUNDLE'];self.assertEqual(result['manifest']['completed_years'],HISTORY_YEARS);self.assertEqual(result['manifest']['remaining_years'],[])
        with zipfile.ZipFile(result['path']) as z:self.assertEqual(len([n for n in z.namelist() if n.startswith('year_zips/')]),22)
    def test_continuation_keeps_original_data_code_with_saved_execution_outputs(self):
        old=json.loads((ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_Rebuild.ipynb').read_text());new=json.loads((ROOT/'notebooks/CinderTrace_Atlas_LK_History_2000_2021_All_Batches.ipynb').read_text())
        prefix=[]
        for cell in old['cells']:
            if cell['cell_type']=='markdown' and ''.join(cell['source']).startswith('## 6.'):break
            if cell['cell_type']=='code':prefix.append(''.join(cell['source']))
        codes=[''.join(c['source']) for c in new['cells'] if c['cell_type']=='code']
        self.assertEqual(codes[:len(prefix)],prefix)
        # User-executed notebooks are retained as evidence; never require clearing their outputs.
        self.assertTrue(all(isinstance(c.get('outputs'),list) for c in new['cells'] if c['cell_type']=='code'))
