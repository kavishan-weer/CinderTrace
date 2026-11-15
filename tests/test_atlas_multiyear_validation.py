import tempfile,json,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from pipeline import atlas_multiyear_validation as v
from pipeline import atlas_observation_evidence as e
import test_atlas_cached_pixel_audit as cached_tests

class ValidationTests(unittest.TestCase):
    def sample(self):
        f=[];y=[]
        for year in range(2018,2025):
            for month in range(1,9):
                date=f'{year}-{month:02d}-10';x=month*3+year%3
                f.append({'date':date,'partition':'fit' if year<=2020 else 'calibration' if year<=2022 else 'evaluation','month_number':month,'noaa20_input_available':True,'noaa20_screened_vegetation_active_cells':x,'noaa20_native_pixels':x+3,'noaa20_nominal_clear_centres':10000,'noaa20_status':'recorded'})
                y.append({'date':date,'reference_available':True,'snpp_screened_vegetation_active_cells':x*1.5+(year%2)*3,'snpp_status':'recorded'})
        return pd.DataFrame(f,columns=v.FEATURE_COLUMNS),pd.DataFrame(y,columns=v.LABEL_COLUMNS)
    def test_heldout_labels_cannot_change_predictions_or_intervals(self):
        f,y=self.sample();a,_,audit=v.evaluate_outage_proxy(f,y)
        changed=y.copy();changed.loc[changed.date.str.startswith(('2023','2024')),'snpp_screened_vegetation_active_cells']=99999
        b,_,new=v.evaluate_outage_proxy(f,changed)
        self.assertEqual(audit,new)
        pd.testing.assert_frame_equal(a[['prediction','lower_80','upper_80','lower_90','upper_90']],b[['prediction','lower_80','upper_80','lower_90','upper_90']])
    def test_calibration_separate_and_test_label_absence_does_not_select_features(self):
        f,y=self.sample();a,_,audit=v.evaluate_outage_proxy(f,y);changed=y.copy()
        changed.loc[changed.date.str.startswith(('2021','2022')),'snpp_screened_vegetation_active_cells']*=30
        b,_,new=v.evaluate_outage_proxy(f,changed);self.assertEqual(audit['model'],new['model']);self.assertTrue(a.prediction.equals(b.prediction));self.assertFalse(a.upper_90.equals(b.upper_90))
        changed=y.copy();changed.loc[changed.date.str.startswith(('2023','2024')),'reference_available']=False
        b,metrics,_=v.evaluate_outage_proxy(f,changed);self.assertTrue(a.prediction.equals(b.prediction));self.assertTrue(metrics.scored_evaluation_dates.eq(0).all())
    def test_reference_fields_rejected_and_insufficient_support_withheld(self):
        f,y=self.sample()
        with self.assertRaises(ValueError):v.evaluate_outage_proxy(f.assign(snpp_clear_mask=1),y)
        y.loc[y.date.str.startswith('2021'),'reference_available']=False
        a,_,_=v.evaluate_outage_proxy(f,y);self.assertTrue(a.lower_90.isna().all())
        f.loc[f.partition.eq('evaluation'),'noaa20_input_available']=False
        a,_,audit=v.evaluate_outage_proxy(f,y);self.assertTrue(a.empty);self.assertEqual(audit['status'],'no_source_available_evaluation_dates')
    def test_geometry_precedes_time_and_fire_counts_never_select_pairs(self):
        passes=pd.DataFrame([{'pass_id':'s1','satellite':'Suomi-NPP','date':'2021-01-01','day_night':'DAY','complete_science_screen':True},{'pass_id':'s2','satellite':'Suomi-NPP','date':'2021-01-01','day_night':'DAY','complete_science_screen':True},{'pass_id':'n','satellite':'NOAA-20','date':'2021-01-01','day_night':'DAY','complete_science_screen':True}])
        d=pd.DataFrame([{'snpp_pass':'s1','noaa20_pass':'n','distance_cap_metres':250,'view_cap_degrees':np.nan,'separation_minutes':45,'mutual_nearest_clear_centre_pairs':0,'snpp_fire_centres_on_support':0},{'snpp_pass':'s2','noaa20_pass':'n','distance_cap_metres':250,'view_cap_degrees':np.nan,'separation_minutes':50,'mutual_nearest_clear_centre_pairs':10,'snpp_fire_centres_on_support':0}])
        a=v.select_geometry_pairs(passes,d,60,None,250);self.assertEqual(list(a.snpp_pass),['s2'])
        d['snpp_fire_centres_on_support']=999999;pd.testing.assert_frame_equal(a,v.select_geometry_pairs(passes,d,60,None,250))
    def test_missing_catalogue_not_zero_and_reference_cannot_change_source_features(self):
        slot={'date':'2018-04-19','partition':'fit'};inventory={'records':[]}
        native=pd.DataFrame(columns=['satellite','archive_match_status','confidence_agrees','archive_observation_id','archive_type','screened_fire','cell']);archive=pd.DataFrame(columns=['satellite'])
        a,b=v.daily_tables(slot,inventory,[],native,archive)
        self.assertFalse(a.iloc[0].noaa20_input_available);self.assertIsNone(a.iloc[0].noaa20_screened_vegetation_active_cells)
        self.assertFalse(b.iloc[0].reference_available)
    def test_streaming_workflow_resume_and_partial_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'original';cache.mkdir();scratch=root/'scratch';scratch.mkdir();work=root/'work';records=[];joins=[];observations=[]
            fixture=cached_tests.RealFormatTests()
            for sat,prefix,start in [('Suomi-NPP','s','2019-07-03T07:00:00Z'),('NOAA-20','n','2019-07-03T07:24:00Z')]:
                fire,geo=fixture.fixture(cache,prefix);fid=prefix+'f';gid=prefix+'g';end=(pd.Timestamp(start)+pd.Timedelta(minutes=6)).isoformat()
                for path,id,kind in [(fire,fid,'fire'),(geo,gid,'geolocation')]:
                    r={'id':id,'name':path.name,'download_url':'https://example.invalid/'+path.name,'satellite':sat,'date':'2019-07-03','day_night':'DAY','time_start':start,'time_end':end,'kind':kind,'metadata_entry_sha256':id,'catalogue_size_mb':path.stat().st_size/1024**2}
                    records.append(r);v.write_json(cache/(path.name+'.receipt.json'),{'id':id,'bytes':path.stat().st_size,'sha256':v.p.file_sha(path)})
                joins.append({'date':'2019-07-03','fire_id':fid,'geo_id':gid,'status':'unique_catalogue_companion'})
                observations.append({'latitude':7.01,'longitude':80.01,'satellite':sat,'acq_datetime':start,'confidence':'n','type':0,'observation_id':fid+'o'})
            slot={'date':'2019-07-03','year':2019,'partition':'fit'};inputs={'inventory':{'records':records,'companions':joins},'standard_observations':observations,'design':{'dates':[slot]},'boundary':(e.ROOT/'data/atlas/canonical_lk_2000_2024_v1/region.geojson').read_text()}
            result=v.run_batch(inputs,[2019],object(),cache,scratch,work,'hash');self.assertEqual(result['date_audits_complete'],1)
            with patch.object(v.e,'download',side_effect=AssertionError('must reuse checkpoint')):v.run_batch(inputs,[2019],object(),cache,scratch,work,'hash')
            self.assertTrue(all(x.exists() for x in [fire,geo]));self.assertEqual(list(scratch.iterdir()),[])
            # A failed reference swath must not remove a valid NOAA-20 predictor.
            original_process=v.process_granule
            def source_only(join,*args,**kwargs):
                if join['fire_id'].startswith('s'):raise ValueError('reference fixture failure')
                return original_process(join,*args,**kwargs)
            partial_work=root/'partial_reference'
            with patch.object(v,'process_granule',side_effect=source_only):v.process_date(slot,inputs,object(),cache,scratch,partial_work,'partial-hash')
            xf=pd.read_parquet(partial_work/'dates'/slot['date']/'noaa20_features.parquet');yl=pd.read_parquet(partial_work/'dates'/slot['date']/'reference_labels.parquet')
            self.assertTrue(xf.iloc[0].noaa20_input_available);self.assertFalse(yl.iloc[0].reference_available)
            v.process_date(slot,inputs,object(),cache,scratch,partial_work,'partial-hash')
            pd.testing.assert_frame_equal(xf,pd.read_parquet(partial_work/'dates'/slot['date']/'noaa20_features.parquet'))
            with patch.object(v,'process_granule',side_effect=v.e.ScienceAccessRequired('fixture access denied')):
                denied=v.run_batch(inputs,[2019],object(),cache,scratch,root/'denied','denied-hash')
            self.assertTrue(denied['access_denied']);self.assertEqual(denied['date_audits_complete'],0)

            report=v.finalize(inputs,work,root/'results','hash');self.assertEqual(report['dates_processed'],1);self.assertFalse(report['replacement_validated'])
            missing={**inputs,'design':{'dates':[slot,{'date':'2024-01-01','year':2024,'partition':'evaluation'}]}}
            report=v.finalize(missing,work,root/'partial','hash');self.assertEqual(report['dates_planned'],2)
            features=pd.read_parquet(root/'partial/noaa20_features.parquet');self.assertFalse(features.iloc[1].noaa20_input_available);self.assertTrue(pd.isna(features.iloc[1].noaa20_screened_vegetation_active_cells))

class TemporaryStagingTests(unittest.TestCase):
    def test_new_raw_copies_are_removed_after_commit_and_after_error(self):
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);server=root/'server';server.mkdir();original=root/'original';original.mkdir();scratch=root/'scratch';scratch.mkdir()
            fire,geo=cached_tests.RealFormatTests().fixture(server,'s');lookup={};source={}
            for file,id,kind in [(fire,'f','fire'),(geo,'g','geolocation')]:
                lookup[id]={'id':id,'name':file.name,'download_url':'https://example.invalid/'+file.name,'kind':kind,'metadata_entry_sha256':id,'catalogue_size_mb':file.stat().st_size/1024**2,'satellite':'Suomi-NPP','date':'2019-07-03','time_start':'2019-07-03T07:00:00Z','time_end':'2019-07-03T07:06:00Z','day_night':'DAY'};source[id]=file
            staged=[]
            def fake(record,session,cache):
                path=Path(cache)/record['name'];path.write_bytes(source[record['id']].read_bytes());staged.append(path)
                return path,{'id':record['id'],'bytes':path.stat().st_size,'sha256':v.p.file_sha(path)}
            join={'fire_id':'f','geo_id':'g'}
            with patch.object(v.e,'download',side_effect=fake):
                summary,_,clear,_=v.process_granule(join,lookup,object(),original,scratch,root/'derived','method',box(79,6,82,9))
            self.assertTrue(clear.exists());self.assertEqual(summary['raw_fire_centres'],1);self.assertTrue(all(not path.exists() for path in staged));self.assertTrue(fire.exists() and geo.exists())
            with patch.object(v.e,'download',side_effect=fake),patch.object(v.p,'extract_granule',side_effect=ValueError('schema')):
                with self.assertRaises(ValueError):v.process_granule(join,lookup,object(),original,scratch,root/'failed','method',box(79,6,82,9))
            self.assertEqual(list(scratch.iterdir()),[]);self.assertFalse(list((root/'failed').rglob('checkpoint.json')))

class NotebookTests(unittest.TestCase):
    def test_standalone_inputs_methods_partial_finalize_and_zip(self):
        import ast,hashlib,importlib.metadata,zipfile
        nb=json.loads((e.ROOT/'notebooks/CinderTrace_Atlas_LK_Multiyear_Validation.ipynb').read_text())
        for c in nb['cells']:
            if c['cell_type']=='code' and not ''.join(c['source']).startswith('%pip'):ast.parse(''.join(c['source']))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ns={'STUDY_ROOT':root,'IN_COLAB':False}
            exec('from pathlib import Path\nimport json,hashlib,base64,zlib,zipfile,types\nimport pandas as pd',ns)
            for c in nb['cells']:
                if c['cell_type']!='code':continue
                code=''.join(c['source'])
                if code.startswith('INPUT_BYTES=') or code.startswith('BASE_SOURCE='):exec(compile(code,'notebook','exec'),ns)
            self.assertEqual(ns['STUDY_SOURCE'],Path(v.__file__).read_text());self.assertEqual(len(ns['INPUTS']['design']['dates']),54)
            final=next(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code' and ''.join(c['source']).startswith("DECISION=study_ns['finalize']"))
            exec(compile(final.replace('from IPython.display import display','display=lambda *args:None'),'finalize_cell','exec'),ns)
            self.assertEqual(ns['DECISION']['dates_processed'],0);self.assertFalse(ns['DECISION']['replacement_validated'])
            original=importlib.metadata.version
            with patch('importlib.metadata.version',side_effect=lambda name:'not-used-in-offline-fixture' if name=='earthaccess' else original(name)):
                exec(compile(''.join(nb['cells'][-1]['source']),'export_cell','exec'),ns)
            with zipfile.ZipFile(ns['archive_path']) as z:
                manifest=json.loads(z.read('bundle_manifest.json'));json.loads(z.read('runtime_versions.json'))
                for name,r in manifest.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),r['sha256'])
                self.assertFalse(any('derived/' in name or 'science_cache' in name for name in z.namelist()))
