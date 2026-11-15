from io import BytesIO
from pathlib import Path
import hashlib,json,tempfile,unittest,zipfile
import pandas as pd
from pipeline.import_atlas_pilot import ROOT
from pipeline.build_atlas_canonical import build,POLICY
from pipeline.verify_atlas_two_year import verify_two_year,BUNDLE_NAME,EXPECTED_SHA256
from pipeline.atlas_source_compare import parse_official_csv
import shapely

class CanonicalObservedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.result=build(Path(cls.tmp.name)/'benchmark')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_noaa21_standard_stream_is_selected_and_nrt_retained_separately(self):
        p=self.result['canonical'];self.assertEqual(len(p),38995);self.assertTrue(p.quality.eq('sp').all())
        n21=p[p.satellite.eq('NOAA-21')];self.assertEqual(len(n21),5654)
        self.assertEqual(n21.type.value_counts().to_dict(),{0:5603,2:44,3:7})
        archive=pd.read_parquet(self.result['output']/'audit/noaa21_mirror_nrt_2024.parquet')
        self.assertEqual(len(archive),5775);self.assertTrue(archive.quality.eq('nrt').all());self.assertTrue(archive.type.isna().all())
        self.assertEqual(self.result['report']['NOAA21_exact_native_keys_shared'],1848)
        self.assertEqual(self.result['report']['NOAA21_shared_key_changed_fields']['frp'],32)
    def test_grids_reconcile_without_promoting_zeros_to_coverage(self):
        r=self.result
        self.assertEqual(len(r['daily']),4750);self.assertEqual(len(r['monthly']),156);self.assertEqual(len(r['grid']),30096)
        for frame in [r['daily'],r['monthly'],r['grid']]:self.assertEqual(frame.recorded_detections.sum(),38995);self.assertTrue(frame.observing_coverage.eq('unverified').all())
        self.assertTrue(r['daily'].coverage_adjusted_activity.isna().all())
        day=r['daily'][r['daily'].date.eq('2023-07-19')&r['daily'].satellite.eq('NOAA-20')].iloc[0]
        self.assertEqual(day.recorded_detections,0);self.assertTrue(day.upstream_lists_missing_standard_data)
        self.assertFalse(POLICY['cross_year_raw_totals_comparable']);self.assertFalse(POLICY['production_export_enabled'])
    def test_sample_records_trace_to_original_nasa_response_and_ordinal(self):
        p=self.result['canonical'];region=shapely.geometry.shape(json.loads((self.result['output']/'region.geojson').read_text())['features'][0]['geometry'])
        archives={self.result['report']['source_checkpoints']['2023']:ROOT/'cindertrace_atlas_lk_2023_official_check.zip',EXPECTED_SHA256:ROOT/BUNDLE_NAME}
        for _,group in p.groupby(['year','source_stream']):
            for row in [group.iloc[0],group.iloc[-1]]:
                with zipfile.ZipFile(archives[row.source_checkpoint_sha256]) as z:raw=z.read(row.source_relative_path)
                self.assertEqual(hashlib.sha256(raw).hexdigest(),row.source_response_sha256)
                frame=parse_official_csv(raw,row.source_stream,row.request_start_utc,row.request_end_utc_exclusive,region)
                native=frame.loc[row.source_row_ordinal]
                self.assertEqual(native.satellite,row.satellite);self.assertEqual(native.acq_datetime,row.acq_datetime)
                self.assertEqual(native.audit_lon,row.longitude);self.assertEqual(native.audit_lat,row.latitude)
                self.assertEqual(native.confidence,row.confidence);self.assertEqual(native.frp,row.frp)
        self.assertFalse(p.observation_id.duplicated().any())
    def test_manifest_hashes_every_generated_file(self):
        out=self.result['output'];m=json.loads((out/'manifest.json').read_text())
        for name,r in m['files'].items():
            raw=(out/name).read_bytes();self.assertEqual(len(raw),r['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),r['sha256'])
    def test_verifier_reproduces_documented_quality_difference(self):
        r=self.result['two_year_verification'];self.assertEqual(r['verified_requests'],515);self.assertEqual(r['manifested_files_verified'],1064)
        self.assertEqual(r['year_results']['2022']['status'],'matched_native_records');self.assertEqual(r['year_results']['2024']['status'],'review_required')

class TwoYearZipIntegrityTests(unittest.TestCase):
    def test_wrong_outer_hash_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'ZIP differs'):verify_two_year(expected_sha256='0'*64)
    def test_inner_hash_catches_changed_response_after_rehashing_outer_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'changed.zip'
            with zipfile.ZipFile(ROOT/BUNDLE_NAME) as src,zipfile.ZipFile(target,'w') as dst:
                for name in src.namelist():
                    raw=src.read(name)
                    if name=='cache/MODIS_SP_2022-01-01_2022-01-06.csv':raw+=b'tampered'
                    dst.writestr(name,raw)
            with self.assertRaisesRegex(ValueError,'file hash or byte size'):verify_two_year(target,hashlib.sha256(target.read_bytes()).hexdigest())
    def test_unlisted_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'extra.zip'
            with zipfile.ZipFile(ROOT/BUNDLE_NAME) as src,zipfile.ZipFile(target,'w') as dst:
                for name in src.namelist():dst.writestr(name,src.read(name))
                dst.writestr('unlisted.txt',b'extra')
            with self.assertRaisesRegex(ValueError,'inventory differs'):verify_two_year(target,hashlib.sha256(target.read_bytes()).hexdigest())
