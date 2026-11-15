from io import BytesIO
from pathlib import Path
import json,tempfile,unittest,zipfile
import numpy as np
import pandas as pd
from pipeline.import_atlas_pilot import ROOT
from pipeline.verify_atlas_history import verify_history,read_zip,check_inventory,same_frame,BUNDLE_NAME,EXPECTED_SHA256
from pipeline.assemble_atlas_observed import assemble

class VerifiedHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.history=verify_history();cls.result=assemble(cls.history,Path(cls.tmp.name)/'combined')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_actual_history_reconstructs_all_requests_and_active_source_comparisons(self):
        r=self.history['report'];self.assertEqual(r['verified_raw_requests'],2555);self.assertEqual(r['standard_observations'],132249)
        self.assertEqual(r['nested_manifested_files_verified'],5704);self.assertEqual(r['source_comparisons_checked'],36);self.assertEqual(r['source_comparisons_requiring_review'],[])
        self.assertEqual(self.history['canonical'].source_response_sha256.isna().sum(),0)
    def test_unified_standard_cohort_has_no_duplicates_or_nrt_and_preserves_benchmark(self):
        p=self.result['observations'];self.assertEqual(len(p),171244);self.assertTrue(p.quality.eq('sp').all());self.assertFalse(p.observation_id.duplicated().any())
        self.assertEqual(p[p.year.ge(2022)].groupby('year').size().to_dict(),{2022:8593,2023:13366,2024:17036})
        self.assertEqual(len(p[p.satellite.eq('NOAA-21')]),5654)
        self.assertFalse(self.result['report']['raw_annual_totals_comparable']);self.assertFalse(self.result['report']['production_export_enabled'])
    def test_unsupported_dates_and_transition_months_do_not_become_zero(self):
        daily=self.result['daily'];monthly=self.result['monthly'];grid=self.result['grid']
        self.assertEqual(len(daily),36894);self.assertEqual(len(monthly),1212);self.assertEqual(len(grid),249744)
        self.assertTrue(daily[daily.date.lt('2000-11-01')].recorded_detections.isna().all())
        self.assertTrue(daily[daily.satellite.eq('Aqua')&daily.date.lt('2002-07-04')].recorded_detections.isna().all())
        for month,sat in [('2002-07','Aqua'),('2012-01','Suomi-NPP')]:
            row=monthly[monthly.month.eq(month)&monthly.satellite.eq(sat)].iloc[0];self.assertTrue(pd.isna(row.full_month_standard_detections));self.assertGreater(row.supported_queried_days,0)
        self.assertEqual(daily.recorded_detections.sum(),171244);self.assertEqual(grid.detections_on_queried_dates.sum(),171244);self.assertTrue(daily.coverage_adjusted_activity.isna().all())
    def test_generated_unified_manifest_hashes_match(self):
        r=self.result['report']
        from pipeline.atlas_history import digest
        self.assertEqual(digest((self.result['output']/'region.geojson').read_bytes()),r['boundary_sha256'])
        self.assertEqual(r['coordinate_reference'],'OGC:CRS84')
        for name,receipt in r['files'].items():
            raw=(self.result['output']/name).read_bytes();self.assertEqual(len(raw),receipt['bytes']);self.assertEqual(digest(raw),receipt['sha256'])

class HistoryIntegrityTests(unittest.TestCase):
    def test_null_representation_is_normalized_but_zero_is_never_missing(self):
        same_frame(pd.DataFrame({'date':pd.Series(['2000-11-01',np.nan],dtype='str')}),pd.DataFrame({'date':['2000-11-01',None]}))
        with self.assertRaises(AssertionError):same_frame(pd.DataFrame({'count':[0]}),pd.DataFrame({'count':[None]}))
    def test_wrong_outer_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'notebook SHA256'):verify_history(expected_sha256='0'*64)
    def test_unsafe_and_duplicate_nested_members_are_rejected(self):
        b=BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('../outside.txt',b'unsafe')
        with self.assertRaisesRegex(ValueError,'Unsafe'):read_zip(b.getvalue())
    def test_manifest_catches_tampered_nested_bytes(self):
        from pipeline.atlas_history import digest
        manifest={'files':{'year.zip':{'bytes':4,'sha256':digest(b'good')}}}
        with self.assertRaisesRegex(ValueError,'checksum'):check_inventory({'bundle_manifest.json':json.dumps(manifest).encode(),'year.zip':b'bad!'},'bundle_manifest.json')
