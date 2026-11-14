import json
import unittest
import importlib.util
import numpy as np
from pipeline.lk_observation_analysis import grid_geometry,select_files,summarize_day

class ObservationAnalysisTests(unittest.TestCase):
    def test_package_overlapping_month_boundary_is_retained(self):
        m={'science_files':[
            {'time_start':'2000-12-26T00:00:00Z','time_end':'2001-01-02T23:59:59Z'},
            {'time_start':'2001-02-02T00:00:00Z','time_end':'2001-02-09T23:59:59Z'}]}
        self.assertEqual(select_files(m,['2001-01']),m['science_files'][:1])

    def test_missing_cloud_unknown_and_nonfire_remain_separate(self):
        fire=np.arange(10,dtype=np.uint8).reshape(2,5)
        qa=np.full((2,5),2,dtype=np.uint8);qa[1,0]=3
        r=summarize_day(fire,qa,np.ones((2,5),dtype=bool))
        self.assertEqual(r['region_pixels'],10)
        self.assertEqual(r['fire_pixels'],3)
        self.assertEqual(r['cloud'],1)
        self.assertEqual(r['missing_input'],1)
        self.assertEqual(r['unknown'],1)
        self.assertEqual(r['nonfire_land'],1)
        self.assertEqual(r['usable_class_pixels'],4) # Water + three fires, QA-missing land excluded.

    def test_spatial_mask_excludes_outside_pixels(self):
        f=np.array([[9,9],[5,0]],dtype=np.uint8)
        mask=np.array([[False,False],[True,True]])
        r=summarize_day(f,np.full((2,2),2),mask)
        self.assertEqual(r['fire_pixels'],0)
        self.assertEqual(r['region_pixels'],2)
        self.assertEqual(r['missing_input'],1)

    def test_hdf_grid_orientation_and_resolution_from_metadata(self):
        s='UpperLeftPointMtrs=(100.0,200.0) LowerRightMtrs=(140.0,160.0)'
        self.assertEqual(grid_geometry(s,2,4),(100.,200.,10.,-20.))
        with self.assertRaises(ValueError):grid_geometry(s.replace('160.0','240.0'),2,4)

    @unittest.skipUnless(importlib.util.find_spec("pyhdf") and importlib.util.find_spec("pyproj"), "Optional observation readers are not installed")
    def test_real_hdf_reader_clips_package_days_at_month_boundary(self):
        import tempfile
        from pathlib import Path
        from pyhdf.SD import SD,SDC
        from pyproj import CRS,Transformer
        from pipeline.lk_observation_analysis import analyze,ROOT
        inverse=Transformer.from_crs(4326,CRS.from_proj4('+proj=sinu +R=6371007.181 +nadgrids=@null +wktext'),always_xy=True)
        x,y=inverse.transform(80.,8.)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as tmp:
            p=Path(tmp)/'synthetic.hdf'
            h=SD(str(p),SDC.WRITE|SDC.CREATE)
            metadata=f'UpperLeftPointMtrs=({x-1000},{y+1000}) LowerRightMtrs=({x+1000},{y-1000})'
            h.attr('StructMetadata.0').set(SDC.CHAR,metadata)
            f=h.create('FireMask',SDC.UINT8,(8,2,2));f[:]=np.full((8,2,2),5,dtype=np.uint8);f.endaccess()
            q=h.create('QA',SDC.UINT8,(8,2,2));q[:]=np.full((8,2,2),2,dtype=np.uint8);q.endaccess();h.end()
            records=[dict(path=str(p.relative_to(ROOT)),producer_granule_id='MOD14A1.A2000361.h25v08.061.example',
                time_start='2000-12-26T00:00:00Z',time_end='2001-01-02T23:59:59Z',id='synthetic',product='MOD14A1')]
            frame,_=analyze(records,['2001-01'])
            self.assertEqual(frame.date.dt.strftime('%Y-%m-%d').tolist(),['2001-01-01','2001-01-02'])
            self.assertEqual(frame.nonfire_land.tolist(),[4,4])
            self.assertEqual(frame.fire_pixels.sum(),0)
            overlapping={**records[0],'time_start':'2001-01-01T00:00:00Z','time_end':'2001-01-08T23:59:59Z','id':'overlapping'}
            merged,_=analyze(records+[overlapping],['2001-01'])
            self.assertEqual(len(merged),8)
            self.assertEqual(merged.attrs['identical_overlap_rows_removed'],2)
            self.assertIn('overlapping',merged.equivalent_source_granules.iloc[0])
            h=SD(str(p),SDC.WRITE);f=h.select('FireMask');f[6,:,:]=np.full((2,2),9,dtype=np.uint8);f.endaccess();h.end()
            from pipeline.lk_observation_analysis import PilotError
            with self.assertRaisesRegex(PilotError,'Conflicting daily'):
                analyze(records+[overlapping],['2001-01'])

    def test_transient_download_error_retries_and_reuses_verified_cache(self):
        import io,tempfile,urllib.error
        from pathlib import Path
        from unittest.mock import Mock,patch
        from contextlib import redirect_stdout
        from pipeline.lk_observation_analysis import download_one
        payload=b'\x0e\x03\x13\x01'+b'science-data'
        class Response(io.BytesIO):status=200
        record={'download_url':'https://example.org/test.hdf','size_mb_catalogue':len(payload)/1048576}
        session=Mock();session.open.side_effect=[urllib.error.URLError('sensitive URL must not be displayed'),Response(payload)]
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.lk_observation_analysis.time.sleep'),redirect_stdout(io.StringIO()) as output:
            p=download_one(record,Path(tmp),session)
            self.assertEqual(p.read_bytes(),payload)
            self.assertEqual(session.open.call_count,2)
            self.assertEqual(download_one(record,Path(tmp),session),p)
            self.assertEqual(session.open.call_count,2)
            self.assertNotIn('sensitive URL',output.getvalue())
            self.assertFalse(list(Path(tmp).glob('*.partial')))

    def test_truncated_hdf_header_is_not_accepted_as_complete(self):
        import io,tempfile
        from pathlib import Path
        from unittest.mock import Mock,patch
        from contextlib import redirect_stdout
        from pipeline.lk_observation_analysis import download_one,PilotError
        class Response(io.BytesIO):status=200
        record={'download_url':'https://example.org/test.hdf','size_mb_catalogue':100/1048576}
        session=Mock();session.open.side_effect=[Response(b'\x0e\x03\x13\x01') for _ in range(2)]
        with tempfile.TemporaryDirectory() as tmp,patch('pipeline.lk_observation_analysis.time.sleep'),redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(PilotError,'incomplete file'):
                download_one(record,Path(tmp),session,attempts=2)
            self.assertFalse(list(Path(tmp).glob('*')))
