from pathlib import Path
import json,tempfile,unittest,zipfile
from pipeline.atlas_history import digest
from pipeline.package_atlas_observed import package_checkpoint

class AnalysisPackageTests(unittest.TestCase):
    def test_archive_is_self_checking_and_does_not_claim_harmonization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';data.mkdir();raw=b'fixture-data'
            m={'dataset_id':'fixture','observations':1,'coverage_verified':False,'harmonization_validated':False,'production_export_enabled':False,'files':{'observations.parquet':{'bytes':len(raw),'sha256':digest(raw)}}}
            (data/'observations.parquet').write_bytes(raw);(data/'manifest.json').write_text(json.dumps(m));(root/'verification.json').write_text('{}');(root/'policy.json').write_text('{}')
            r=package_checkpoint(data,root/'verification.json',root/'policy.json',root/'out.zip')
            with zipfile.ZipFile(r['path']) as z:
                index=json.loads(z.read('analysis_bundle_manifest.json'));self.assertFalse(index['harmonization_validated'])
                for name,receipt in index['files'].items():self.assertEqual(digest(z.read(name)),receipt['sha256'])
            (data/'observations.parquet').write_bytes(b'changed')
            with self.assertRaises(ValueError):package_checkpoint(data,root/'verification.json',root/'policy.json',root/'bad.zip')
