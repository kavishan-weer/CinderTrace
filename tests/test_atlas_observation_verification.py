import hashlib,json,tempfile,unittest,zipfile
from pathlib import Path
import pandas as pd
from pipeline.verify_atlas_observation_evidence import read_verified_bundle,nonnegative_integers

class VerificationTests(unittest.TestCase):
    def test_bundle_hashes_and_unlisted_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bundle.zip';raw=b'original';manifest={'results/table':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}
            def write(payload,extra=False):
                with zipfile.ZipFile(p,'w') as z:
                    z.writestr('results/table',payload);z.writestr('bundle_manifest.json',json.dumps(manifest))
                    if extra:z.writestr('unlisted',b'x')
            write(raw);self.assertEqual(read_verified_bundle(p)['results/table'],raw)
            write(b'changed')
            with self.assertRaises(ValueError):read_verified_bundle(p)
            write(raw,True)
            with self.assertRaises(ValueError):read_verified_bundle(p)
    def test_counts_reject_missing_negative_and_fractional_values(self):
        nonnegative_integers(pd.DataFrame({'count':[0,1,5]}),['count'])
        for bad in [-1,.5,float('nan')]:
            with self.assertRaises(ValueError):nonnegative_integers(pd.DataFrame({'count':[bad]}),['count'])

if __name__=='__main__':unittest.main()
