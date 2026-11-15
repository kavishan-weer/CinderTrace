import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from pipeline.import_atlas_pilot import verify_bundle,ROOT

class AtlasBundleTests(unittest.TestCase):
    def test_checked_pilot_reconciles_geometry_counts_and_native_confidence(self):
        points,manifest,boundary,report=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip')
        self.assertEqual(len(points),13366)
        self.assertEqual(report['satellite_totals']['Suomi-NPP'],6432)
        self.assertFalse(report['harmonization_applied'])
        self.assertFalse(report['observing_coverage_verified'])

    def test_wrong_outer_receipt_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Bundle SHA256'):
            verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip',expected_sha256='0'*64)

    def test_tampered_inner_csv_is_rejected_even_if_outer_hash_is_recomputed(self):
        original=ROOT/'cindertrace_atlas_lk_2023_pilot.zip'
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'changed.zip'
            with zipfile.ZipFile(original) as source,zipfile.ZipFile(target,'w') as out:
                for name in source.namelist():
                    payload=source.read(name)
                    if name=='monthly_observed_counts.csv':payload+=b'changed'
                    out.writestr(name,payload)
            with self.assertRaisesRegex(ValueError,'Inner checksum'):
                verify_bundle(target,expected_sha256=hashlib.sha256(target.read_bytes()).hexdigest())

    def test_extra_zip_member_cannot_write_outside_import_directory(self):
        original=ROOT/'cindertrace_atlas_lk_2023_pilot.zip'
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'extra.zip'
            with zipfile.ZipFile(original) as source,zipfile.ZipFile(target,'w') as out:
                for name in source.namelist():out.writestr(name,source.read(name))
                out.writestr('../untrusted.txt',b'no')
            with self.assertRaisesRegex(ValueError,'ZIP members'):
                verify_bundle(target,expected_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
