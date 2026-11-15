import unittest,tempfile,json
from pathlib import Path
import pandas as pd
import numpy as np
from pipeline import atlas_cached_pixel_audit as p

class MatchingTests(unittest.TestCase):
    def test_mutual_nearest_is_one_to_one(self):
        a=pd.DataFrame({'latitude':[7,7,8],'longitude':[80,80.0001,81]});b=pd.DataFrame({'latitude':[7,8],'longitude':[80,81]})
        ix,iy,d=p.mutual_neighbours(a,b);self.assertEqual(len(ix),2);self.assertEqual(len(set(iy)),2);self.assertTrue((d==0).all())
        self.assertEqual(len(p.mutual_neighbours(a,b.iloc[:0])[0]),0)
    def test_zero_shared_support_is_unavailable_not_zero_fire(self):
        a=pd.DataFrame({'latitude':[7.],'longitude':[80.],'fire':[True],'sensor_zenith_degrees':[30.],'solar_zenith_degrees':[45.]})
        b=a.copy();b['longitude']=81.
        result=p.pair_diagnostics(a,b);self.assertTrue(result.mutual_nearest_clear_centre_pairs.eq(0).all());self.assertTrue(result.snpp_fire_centres_on_support.isna().all())
        result=p.pair_diagnostics(a,a);self.assertTrue(result.snpp_fire_centres_on_support.eq(1).all())
    def test_type_match_is_unique_and_time_restricted(self):
        n=pd.DataFrame([{'latitude':7.,'longitude':80.,'satellite':'Suomi-NPP','time_start':'2021-08-19T07:00:00Z','time_end':'2021-08-19T07:06:00Z'}])
        a=pd.DataFrame([{'latitude':7.,'longitude':80.,'satellite':'Suomi-NPP','acq_datetime':pd.Timestamp('2021-08-19T07:00:00Z'),'type':0,'observation_id':'one'}])
        self.assertEqual(p.archive_match(n,a).iloc[0].archive_match_status,'unique_standard_observation')
        self.assertTrue(p.archive_match(n,pd.concat([a,a],ignore_index=True)).archive_match_status.eq('ambiguous').all())
        self.assertTrue(p.archive_match(pd.concat([n,n],ignore_index=True),a).archive_match_status.eq('ambiguous').all())
        a['acq_datetime']=pd.Timestamp('2021-08-19T07:06:00Z');self.assertEqual(p.archive_match(n,a).iloc[0].archive_match_status,'unmatched')
    def test_pass_grouping_and_one_to_one_maximum_cardinality(self):
        records=[]
        for id,sat,start,end in [('a','Suomi-NPP','07:00','07:06'),('a2','Suomi-NPP','07:06','07:12'),('b','Suomi-NPP','08:42','08:48'),('c','NOAA-20','07:54','08:00')]:
            records.append({'id':id,'kind':'fire','satellite':sat,'date':'2021-08-19','day_night':'DAY','time_start':f'2021-08-19T{start}:00Z','time_end':f'2021-08-19T{end}:00Z'})
        members=p.group_passes(records);self.assertEqual(members.pass_id.nunique(),3)
        self.assertEqual(members[members.fire_id.eq('a')].iloc[0].pass_id,members[members.fire_id.eq('a2')].iloc[0].pass_id)
        passes=[]
        for pid,f in members.groupby('pass_id'):
            start=min(pd.Timestamp(x) for x in f.time_start);end=max(pd.Timestamp(x) for x in f.time_end)
            passes.append({'pass_id':pid,'satellite':f.iloc[0].satellite,'date':'2021-08-19','day_night':'DAY','midpoint_utc':(start+(end-start)/2).isoformat(),'complete_science_screen':True,'local_centres':10})
        matched,un=p.pair_passes(pd.DataFrame(passes),60);self.assertEqual(len(matched),1);self.assertEqual(len(un),1)
        self.assertEqual(matched.snpp_pass.nunique(),len(matched));self.assertEqual(matched.noaa20_pass.nunique(),len(matched))
        self.assertEqual(len(p.pair_passes(pd.DataFrame(passes),30)[0]),0)

class RealFormatTests(unittest.TestCase):
    def fixture(self,folder,prefix):
        from netCDF4 import Dataset
        f=folder/(prefix+'fire.nc');g=folder/(prefix+'geo.nc')
        with Dataset(f,'w') as ds:
            ds.createDimension('line',2);ds.createDimension('sample',3);ds.createDimension('fire',1)
            ds.createVariable('fire mask','u1',('line','sample'))[:]=[[4,5,5],[6,8,5]]
            ds.createVariable('algorithm QA','u4',('line','sample'))[:]=0
            for name,value,kind in [('FP_line',1,'u2'),('FP_sample',1,'u2'),('FP_latitude',7.01,'f4'),('FP_longitude',80.01,'f4'),('FP_confidence',8,'u1'),('FP_ViewZenAng',30.,'f4'),('FP_SolZenAng',45.,'f4')]:ds.createVariable(name,kind,('fire',))[:]=value
        with Dataset(g,'w') as ds:
            ds.createDimension('line',2);ds.createDimension('sample',3);group=ds.createGroup('geolocation_data')
            for name,values in [('latitude',[[7.,7.,7.],[7.01,7.01,7.01]]),('longitude',[[80.,80.01,80.02],[80.,80.01,80.02]]),('sensor_zenith',np.full((2,3),30.)),('solar_zenith',np.full((2,3),45.))]:
                var=group.createVariable(name,'f4',('line','sample'));var.units='degrees';var[:]=values
        return f,g
    def test_extracts_geometry_and_rejects_sparse_inconsistency(self):
        from netCDF4 import Dataset
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as tmp:
            f,g=self.fixture(Path(tmp),'');record={'id':'f','satellite':'Suomi-NPP','date':'2021-08-19','time_start':'2021-08-19T07:00:00Z','time_end':'2021-08-19T07:06:00Z','day_night':'DAY'}
            summary,n,s,b=p.extract_granule(f,g,record,box(79,6,82,9));self.assertEqual(len(n),1);self.assertEqual(len(s),4);self.assertEqual(n.iloc[0].sensor_zenith_degrees,30);self.assertEqual(summary['raw_fire_centres'],1)
            with Dataset(f,'a') as ds:ds.variables['FP_confidence'][0]=9
            with self.assertRaises(ValueError):p.extract_granule(f,g,record,box(79,6,82,9))
    def test_complete_offline_workflow_and_resume(self):
        from pipeline import atlas_observation_evidence as e
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache';cache.mkdir();records=[];receipts=[];joins=[];previous=[];archive=[]
            for sat,prefix,time in [('Suomi-NPP','s','07:00'),('NOAA-20','n','07:24')]:
                f,g=self.fixture(cache,prefix);start=f'2021-08-19T{time}:00Z';stop=(pd.Timestamp(start)+pd.Timedelta(minutes=6)).isoformat();fid=prefix+'f';gid=prefix+'g'
                for path,id,kind in [(f,fid,'fire'),(g,gid,'geolocation')]:
                    records.append({'id':id,'name':path.name,'download_url':'https://example.invalid/'+path.name,'satellite':sat,'date':'2021-08-19','day_night':'DAY','time_start':start,'time_end':stop,'kind':kind})
                    receipts.append({'id':id,'bytes':path.stat().st_size,'sha256':p.file_sha(path)})
                joins.append({'fire_id':fid,'geo_id':gid,'status':'unique_catalogue_companion'});previous.append({'fire_id':fid,'local_geolocated_centres':6,'nominal_clear_centres':4,'screened_fire_centres':1,'class_7':0,'class_8':1,'class_9':0})
                archive.append({'latitude':7.01,'longitude':80.01,'satellite':sat,'acq_datetime':pd.Timestamp(start),'type':0,'observation_id':sat+'one'})
            inv={'records':records,'companions':joins};boundary=(e.ROOT/'data/atlas/canonical_lk_2000_2024_v1/region.geojson').read_bytes()
            args=(inv,receipts,boundary,pd.DataFrame(archive),pd.DataFrame(previous),cache,root/'results',root/'derived','method')
            report=p.run(*args);self.assertEqual(report['unique_archive_matches'],2);self.assertEqual(report['network_downloads'],0);self.assertEqual(report['granules_failed'],0)
            report=p.run(*args);self.assertEqual(report['unique_archive_matches'],2)
            with f.open('ab') as handle:handle.write(b'changed')
            with self.assertRaises(ValueError):p.run(*args)


class NotebookTests(unittest.TestCase):
    def test_embedded_method_inputs_and_single_zip_export(self):
        import ast,zipfile,hashlib
        from pipeline import atlas_observation_evidence as e
        root=Path(e.ROOT);nb=json.loads((root/'notebooks/CinderTrace_Atlas_LK_Cached_Pixel_Pass_Audit.ipynb').read_text())
        for c in nb['cells']:
            if c['cell_type']=='code' and not ''.join(c['source']).startswith('%pip'):ast.parse(''.join(c['source']))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);results=folder/'results';results.mkdir()
            ns={'OUTPUT_ROOT':folder,'RESULTS':results,'IN_COLAB':False}
            exec('from pathlib import Path\nimport json,hashlib,base64,zlib,zipfile',ns)
            for c in nb['cells']:
                if c['cell_type']!='code':continue
                code=''.join(c['source'])
                if code.startswith('INPUT_BYTES=') or code.startswith('import types'):exec(compile(code,'notebook','exec'),ns)
            self.assertEqual(ns['AUDIT_METHOD_SOURCE'],Path(p.__file__).read_text());self.assertEqual(len(ns['ARCHIVE']),335)
            self.assertFalse(ns['audit_namespace']['POLICY']['network_downloads'])
            exec(compile(''.join(nb['cells'][-1]['source']),'export','exec'),ns)
            with zipfile.ZipFile(ns['archive_path']) as z:
                manifest=json.loads(z.read('bundle_manifest.json'));json.loads(z.read('runtime_versions.json'))
                for name,r in manifest.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),r['sha256'])
                self.assertFalse(any('science_cache' in name or 'derived_' in name for name in z.namelist()))

if __name__=='__main__':unittest.main()
