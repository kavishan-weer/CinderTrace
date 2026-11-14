import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import h3
import pandas as pd
from pipeline import harmonize as hz
from pipeline.grid import cell_metadata


class H3PipelineTests(unittest.TestCase):
    def test_predictive_metrics_penalize_offset(self):
        scores = hz.metrics([1, 2, 3], [11, 12, 13])
        self.assertEqual(scores['MAE'], 10)
        self.assertLess(scores['R2'], 0)

    def test_cell_day_dedup_categories_and_membership(self):
        cell = h3.latlng_to_cell(7, 80, 6)
        meta = cell_metadata(cell)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'data/boundaries').mkdir(parents=True)
            (root/'raw/lk').mkdir(parents=True)
            pd.DataFrame([{**meta, 'sub': 4}]).to_parquet(root/'data/boundaries/lk_members.parquet')
            rows = []
            for satellite, date, confidence in [('Terra','2010-01-01',50), ('Aqua','2010-01-01',90), ('Aqua','2010-01-02',50)]:
                rows.append(dict(lon=meta['lon'],lat=meta['lat'],satellite=satellite,
                                 acq_date=pd.Timestamp(date).date(),sensor='MODIS',confidence_pct=confidence,
                                 confidence=None,type=0,frp=10.0))
            # Outside membership must not leak into the selected region.
            rows.append({**rows[0], 'lon': 0.0, 'lat': 0.0})
            pd.DataFrame(rows).to_parquet(root/'raw/lk/test.parquet')
            with patch.object(hz,'ROOT',root), patch.object(hz,'RAW',root/'raw'), patch.object(hz,'OUT',root/'out'):
                cells = hz.build_cells('lk')
            modis = cells[cells.fam=='modis']
            self.assertEqual(modis.cell_days.sum(), 2)
            self.assertEqual(modis.detections.sum(), 3)
            self.assertEqual(modis.frp.sum(), 30)
            self.assertEqual(set(modis.conf), {2,3})
            self.assertEqual(set(cells.cat), {'veg'})
            self.assertEqual(set(cells['sub']), {4})
            self.assertEqual(set(cells.h3_cell), {cell})
            self.assertTrue((cells.area_km2 > 0).all())

if __name__ == '__main__':
    unittest.main()
