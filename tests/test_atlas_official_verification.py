import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
from pipeline.import_atlas_pilot import ROOT
from pipeline.verify_atlas_official import verify_official,expected_windows

class OfficialCheckpointTests(unittest.TestCase):
    def test_all_raw_requests_and_saved_observations_reconcile(self):
        r=verify_official(ROOT/'cindertrace_atlas_lk_2023_official_check.zip')
        self.assertEqual(r['verified_requests'],219);self.assertEqual(r['matched_observations'],13366)
        self.assertFalse(r['coverage_verified']);self.assertEqual(r['monthly_rows'],48)
    def test_wrong_zip_identity_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'ZIP differs'):
            verify_official(ROOT/'cindertrace_atlas_lk_2023_official_check.zip',expected_sha256='0'*64)
    def test_inner_response_tamper_is_detected_after_outer_hash_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'changed.zip'
            with zipfile.ZipFile(ROOT/'cindertrace_atlas_lk_2023_official_check.zip') as src,zipfile.ZipFile(path,'w') as dst:
                for name in src.namelist():
                    raw=src.read(name)
                    if name=='cache/MODIS_SP_2023-01-01_2023-01-06.csv':raw+=b'changed'
                    dst.writestr(name,raw)
            with self.assertRaisesRegex(ValueError,'checksum or byte size'):
                verify_official(path,expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def test_request_calendar_includes_leap_day_without_overlap(self):
        windows=expected_windows(2024,['MODIS_SP'])
        self.assertEqual(len(windows),74)
        import pandas as pd
        days=[]
        for _,a,b in windows:days+=list(pd.date_range(a,pd.Timestamp(b)-pd.Timedelta(days=1)).strftime('%Y-%m-%d'))
        self.assertEqual(len(days),366);self.assertEqual(len(set(days)),366);self.assertIn('2024-02-29',days)
