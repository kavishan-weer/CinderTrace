import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import h3
import pandas as pd
from shapely.geometry import Point, shape
from pipeline import local_api as api


class AreaAndRawExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'data/raw/lk').mkdir(parents=True)
        (self.root/'data/boundaries').mkdir(parents=True)
        (self.root/'data/boundaries/lk_subs.geojson').write_text('{"features":[{"properties":{"id":0}}]}')
        self.cell=h3.latlng_to_cell(8,80.5,6)
        lat,lon=h3.cell_to_latlng(self.cell);self.lat,self.lon=lat,lon
        members=pd.DataFrame([dict(h3_cell=self.cell,sub=0,area_km2=36,lat=lat,lon=lon)])
        cells=pd.DataFrame([dict(h3_cell=self.cell,sub=0,cat='veg',conf=3,month=pd.Timestamp('2020-01-01'),fam='modis',cell_days=1)])
        monthly=pd.DataFrame([dict(month=pd.Timestamp('2020-01-01'),cat='veg',conf=3,modis_raw=1.,viirs_snpp_raw=0.,harmonized=5.,lo=2.,hi=8.,source='modis_transferred',period_status='inferred_available',modis_status='inferred_available',snpp_status='missing',comparison_eligible=True,low_data=False)])
        self.data=(cells,monthly,members)
        rows=[]
        for satellite,sensor,confidence,pct,dx,date in [
            ('Terra','MODIS',None,20,0,'2020-01-01'),('Aqua','MODIS',None,90,.005,'2020-01-01'),
            ('Suomi-NPP','VIIRS','n',None,0,'2020-01-01'),('NOAA-20','VIIRS','h',None,0,'2020-01-01'),
            ('NOAA-21','VIIRS','n',None,0,'2020-01-01'),('Terra','MODIS',None,20,0,'2020-01-02'),
            ('Suomi-NPP','VIIRS','n',None,0,'2020-02-01')]:
            self.assertEqual(h3.latlng_to_cell(lat,lon+dx,6),self.cell)
            rows.append(dict(satellite=satellite,sensor=sensor,confidence=confidence,confidence_pct=pct,lat=lat,lon=lon+dx,acq_date=pd.Timestamp(date).date(),frp=12.5,type=0))
        pd.DataFrame(rows).to_parquet(self.root/'data/raw/lk/2020.parquet')
        self.polygon={'type':'Polygon','coordinates':[[[lon-.001,lat-.001],[lon+.001,lat-.001],[lon+.001,lat+.001],[lon-.001,lat+.001],[lon-.001,lat-.001]]]}
        self.request=dict(region='lk',polygon=self.polygon,start='2020-01',end='2020-01',cats=['veg'],confs=[2,3])
        self.patch_root=patch.object(api,'ROOT',self.root);self.patch_root.start()
        self.patch_data=patch.object(api,'dataset',return_value=self.data);self.patch_data.start()

    def tearDown(self):
        self.patch_data.stop();self.patch_root.stop();self.tmp.cleanup()

    def test_raw_point_clip_preserves_original_rows_and_daily_confidence(self):
        output=self.root/'raw.csv'
        count=api.export_hotspots(self.request,output)
        with output.open() as f: rows=list(csv.DictReader(f))
        self.assertEqual(count,4)
        self.assertEqual(len(rows),4)
        self.assertEqual({r['satellite'] for r in rows},{'Terra','Suomi-NPP','NOAA-20','NOAA-21'})
        terra=next(r for r in rows if r['satellite']=='Terra')
        self.assertEqual(float(terra['confidence_pct']),20)
        self.assertEqual(terra['cell_day_confidence'],'3')
        self.assertTrue(all(shape(self.polygon).covers(Point(float(r['lon']),float(r['lat']))) for r in rows))
        self.assertTrue(all(r['record_kind']=='original satellite detection; not harmonized' for r in rows))

    def test_unclipped_export_retains_each_satellite_once(self):
        output=self.root/'region.csv';request={**self.request,'polygon':None}
        self.assertEqual(api.export_hotspots(request,output),5)
        with output.open() as f: self.assertEqual(len({r['satellite'] for r in csv.DictReader(f)}),5)

    def test_area_selection_and_tiny_polygon(self):
        result=api.area_result(self.request)
        self.assertEqual(result['cell_count'],1)
        self.assertEqual(result['rows'][0]['harmonized'],5)
        tiny={'type':'Polygon','coordinates':[[[self.lon+.003,self.lat],[self.lon+.004,self.lat],[self.lon+.004,self.lat+.001],[self.lon+.003,self.lat+.001],[self.lon+.003,self.lat]]]}
        result=api.area_result({**self.request,'polygon':tiny})
        self.assertEqual(result['cell_count'],0)
        self.assertIsNone(result['rows'][0]['harmonized'])
        self.assertFalse(result['rows'][0]['comparison_eligible'])

    def test_invalid_inputs_and_empty_csv(self):
        with self.assertRaises(ValueError):api.area_result({**self.request,'region':'../../etc'})
        with self.assertRaises(ValueError):api.month_range({**self.request,'start':'2020-02'})
        with self.assertRaises(ValueError):api.export_hotspots({**self.request,'confs':[]},self.root/'bad.csv')
        output=self.root/'empty.csv'
        self.assertEqual(api.export_hotspots({**self.request,'cats':['static']},output),0)
        self.assertIn('satellite',output.read_text().splitlines()[0])
        with self.assertRaises(ValueError):api.selection_geometry({**self.request,'polygon':{'type':'Polygon','coordinates':[[[80,7],[81,8],[80,8],[81,7],[80,7]]]}},'lk')

if __name__=='__main__':unittest.main()
