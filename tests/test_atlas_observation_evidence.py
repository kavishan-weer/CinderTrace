import unittest
import numpy as np
import pandas as pd
from shapely.geometry import box
from pipeline.atlas_observation_evidence import acquisition,join_companions,time_candidates,screen_arrays,candidate_diagnostics

class EvidenceTests(unittest.TestCase):
    def test_acquisition_and_companion_identity(self):
        self.assertEqual(acquisition('VNP14IMG.A2021231.0718.002.2024074084526'),'2021231.0718')
        f={'id':'f','kind':'fire','satellite':'Suomi-NPP','acquisition':'2021231.0718','date':'2021-08-19','time_start':'2021-08-19T07:18:00Z','time_end':'2021-08-19T07:24:00Z'}
        self.assertEqual(join_companions([f])[0]['status'],'missing_companion')
        g={**f,'id':'g','kind':'geolocation'}
        self.assertEqual(join_companions([f,g])[0]['status'],'unique_catalogue_companion')
        self.assertEqual(join_companions([f,g,{**g,'id':'g2'}])[0]['status'],'ambiguous_companion')
        self.assertEqual(join_companions([f,{**g,'satellite':'NOAA-20'}])[0]['status'],'missing_companion')
        self.assertEqual(join_companions([f,{**g,'time_end':'2021-08-19T07:25:00Z'}])[0]['status'],'time_extent_mismatch')
    def test_quality_and_class_masks_keep_missing_distinct(self):
        m=np.array([[0,1,2,3,4,5,6,7,8,9]],dtype=np.uint8);q=np.zeros_like(m,dtype=np.uint32)
        x=screen_arrays(m,q,np.zeros(m.shape),np.zeros(m.shape),box(-1,-1,1,1))
        self.assertEqual(x['clear'].sum(),4);self.assertEqual(x['fires'].sum(),3)
        q[0,7]=1<<22;q[0,8]=1<<5
        x=screen_arrays(m,q,np.zeros(m.shape),np.zeros(m.shape),box(-1,-1,1,1))
        self.assertEqual(x['fires'].sum(),1)
        q=np.ma.array(q,mask=np.ones(q.shape,dtype=bool))
        self.assertEqual(screen_arrays(m,q,np.zeros(m.shape),np.zeros(m.shape),box(-1,-1,1,1))['clear'].sum(),0)
    def test_bad_geolocation_grid_and_classes_fail_closed(self):
        m=np.array([[5,8]],dtype=np.uint8);q=np.zeros_like(m,dtype=np.uint32)
        x=screen_arrays(m,q,np.array([[np.nan,999.]]),np.zeros(m.shape),box(-1,-1,1,1))
        self.assertEqual(x['local'].sum(),0)
        with self.assertRaises(ValueError):screen_arrays(m,q,np.zeros((2,1)),np.zeros(m.shape),box(-1,-1,1,1))
        with self.assertRaises(ValueError):screen_arrays(np.array([[255,8]]),q,np.zeros(m.shape),np.zeros(m.shape),box(-1,-1,1,1))
    def test_pair_time_thresholds_not_date_only(self):
        f={'id':'f','kind':'fire','satellite':'Suomi-NPP','date':'2021-08-19','time_start':'2021-08-19T07:00:00Z','time_end':'2021-08-19T07:06:00Z','day_night':'DAY'}
        g={**f,'id':'g','satellite':'NOAA-20','time_start':'2021-08-19T07:50:00Z','time_end':'2021-08-19T07:56:00Z'}
        c=time_candidates([f,g]);self.assertEqual(len(c),1);self.assertFalse(c[0]['within_30']);self.assertTrue(c[0]['within_60'])
        self.assertEqual(time_candidates([f,{**g,'date':'2021-08-20'}]),[])
    def test_missing_support_not_zero_fire(self):
        c=[{'snpp_id':'a','noaa20_id':'b'}]
        empty=pd.DataFrame(columns=['fire_id','cell','clear_centres','fire_centres'])
        r=candidate_diagnostics(c,empty).iloc[0]
        self.assertIsNone(r['snpp_active_cells_on_common_support'])
        cells=pd.DataFrame([{'fire_id':'a','cell':'x','clear_centres':3,'fire_centres':1},{'fire_id':'b','cell':'x','clear_centres':2,'fire_centres':0}])
        r=candidate_diagnostics(c,cells).iloc[0];self.assertEqual(r['common_clear_centre_cells'],1);self.assertEqual(r['noaa20_active_cells_on_common_support'],0)
        cells.loc[1,'cell']='y';r=candidate_diagnostics(c,cells).iloc[0]
        self.assertEqual(r['common_clear_centre_cells'],0);self.assertIsNone(r['snpp_active_cells_on_common_support'])


class NetCDFFixtureTests(unittest.TestCase):
    def test_real_format_grid_and_sparse_alignment(self):
        import tempfile
        from pathlib import Path
        from netCDF4 import Dataset
        from pipeline.atlas_observation_evidence import screen_file
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'fire.nc';g=Path(tmp)/'geo.nc'
            la=np.array([[7.,7.,7.],[8.,8.,8.]],dtype='f4');lo=np.array([[80.,80.1,80.2],[80.,80.1,80.2]],dtype='f4')
            with Dataset(f,'w') as ds:
                ds.createDimension('line',2);ds.createDimension('sample',3);ds.createDimension('nfire',1)
                ds.createVariable('fire mask','u1',('line','sample'))[:]=[[0,4,5],[6,8,5]]
                ds.createVariable('algorithm QA','u4',('line','sample'))[:]=0
                for name,value,dtype in [('FP_line',1,'u2'),('FP_sample',1,'u2'),('FP_latitude',8,'f4'),('FP_longitude',80.1,'f4')]:ds.createVariable(name,dtype,('nfire',))[:]=value
            with Dataset(g,'w') as ds:
                ds.createDimension('line',2);ds.createDimension('sample',3);group=ds.createGroup('geolocation_data')
                group.createVariable('latitude','f4',('line','sample'))[:]=la;group.createVariable('longitude','f4',('line','sample'))[:]=lo
            record={'id':'f','product':'VNP14IMG','satellite':'Suomi-NPP','date':'2021-08-19','time_start':'2021-08-19T07:00:00Z','time_end':'2021-08-19T07:06:00Z','day_night':'DAY'}
            summary,cells=screen_file(f,g,record,box(79,6,82,9))
            self.assertEqual(summary['screened_fire_centres'],1);self.assertEqual(summary['nominal_clear_centres'],3)
            self.assertEqual(summary['local_geolocated_centres'],6);self.assertEqual(cells.fire_centres.sum(),1)
            with Dataset(g,'a') as ds:ds.groups['geolocation_data'].variables['latitude'][1,1]=7.
            with self.assertRaises(ValueError):screen_file(f,g,record,box(79,6,82,9))
    def test_daily_missing_and_partial_screens_are_unavailable(self):
        from pipeline.atlas_observation_evidence import daily_screen_status
        r={'kind':'fire','date':'2021-08-15','satellite':'Suomi-NPP'}
        done={**r,'local_geolocated_centres':100,'screened_fire_centres':0,'nominal_clear_centres':50}
        inv={'records':[r]}
        table=daily_screen_status(inv,[done]);row=table[(table.date==r['date'])&(table.satellite==r['satellite'])].iloc[0]
        self.assertEqual(row.screened_fire_centres,0)
        self.assertTrue(pd.isna(table[(table.date=='2022-08-04')&(table.satellite=='Suomi-NPP')].iloc[0].screened_fire_centres))
        partial=daily_screen_status({'records':[r,r]},[done]);self.assertTrue(pd.isna(partial.iloc[0].screened_fire_centres))

class WorkflowFailureTests(unittest.TestCase):
    def test_access_denial_stops_and_partial_output_has_no_stale_counts(self):
        import tempfile,json
        from pathlib import Path
        from unittest.mock import patch
        from pipeline import atlas_observation_evidence as e
        real=Path(e.ROOT)/'data/atlas/observation_evidence_pilot_v1'
        inv=json.loads((real/'inventory.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);src=tmp/'inventory.json';src.write_text(json.dumps(inv));(tmp/'region.geojson').write_bytes((real/'region.geojson').read_bytes())
            output=tmp/'results';output.mkdir();pd.DataFrame([{'fire_id':'stale','screened_fire_centres':100}]).to_parquet(output/'granule_screening.parquet')
            with patch.object(e,'download',side_effect=e.ScienceAccessRequired('safe')) as download:
                result=e.run_science(src,object(),tmp/'cache',output)
            self.assertEqual(download.call_count,1);self.assertTrue(result['access_denial_stopped_downloads'])
            self.assertEqual(result['failed_or_unavailable'],len(inv['companions']))
            self.assertEqual(len(pd.read_parquet(output/'granule_screening.parquet')),0)
            self.assertTrue(pd.read_parquet(output/'daily_screen_status.parquet').screened_fire_centres.isna().all())
            self.assertFalse(result['coverage_verified']);self.assertFalse(result['gap_fill_enabled'])
    def test_frozen_notebook_metadata_and_method(self):
        import json,tempfile,os
        from pathlib import Path
        from pipeline import atlas_observation_evidence as e
        nb=json.loads((Path(e.ROOT)/'notebooks/CinderTrace_Atlas_LK_Observation_Evidence_Pilot.ipynb').read_text())
        import ast
        for cell in nb['cells']:
            if cell['cell_type']=='code' and not ''.join(cell['source']).startswith('%pip'):ast.parse(''.join(cell['source']))
        with tempfile.TemporaryDirectory() as tmp:
            ns={'OUTPUT_ROOT':Path(tmp),'EVIDENCE':Path(tmp)/'catalogue','RESULTS':Path(tmp)/'results'}
            ns['EVIDENCE'].mkdir();ns['RESULTS'].mkdir()
            exec('from pathlib import Path\nimport json,hashlib,zipfile,io,base64',ns)
            for cell in nb['cells']:
                if cell['cell_type']!='code':continue
                code=''.join(cell['source'])
                if code.startswith('bundle_bytes=') or code.startswith('method_namespace='):exec(compile(code.replace('from IPython.display import display','display=lambda *args:None'),'notebook','exec'),ns)
            self.assertEqual(ns['INVENTORY']['policy']['days'],e.DAYS)
            self.assertEqual(ns['METHOD_SOURCE'],Path(e.__file__).read_text().split("if __name__=='__main__':")[0])
            from unittest.mock import patch
            import zipfile,hashlib
            ns['IN_COLAB']=False
            with patch('importlib.metadata.version',return_value='fixture'):
                export=next(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code' and ''.join(c['source']).startswith('from datetime import datetime,timezone'))
                exec(compile(export,'download_cell','exec'),ns)
            with zipfile.ZipFile(ns['archive_path']) as archive:
                manifest=json.loads(archive.read('bundle_manifest.json'))
                for name,receipt in manifest.items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),receipt['sha256'])
                self.assertFalse(any('science_cache' in name for name in archive.namelist()))


if __name__=='__main__':unittest.main()
