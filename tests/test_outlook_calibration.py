import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml import calibrate_outlook as calibration


def history():
    dates=pd.date_range('2019-01-01','2027-12-01',freq='MS')
    return pd.DataFrame({'issue':dates,'target':dates,'lead':1,'model':'weather_climate_ml',
                         'p_above_normal':np.tile([.1,.1,.9,.9],27),
                         'above_normal_observed':np.tile([0,1,0,1],27)})


class ProbabilityCalibrationTests(unittest.TestCase):
    def test_mature_pre2026_labels_only_and_no_future_perturbation(self):
        data=history();issue=pd.Timestamp('2025-11-01')
        before=calibration.fit_calibrator(data,issue,1,'weather_climate_ml')
        data.loc[data.target>pd.Timestamp('2025-09-01'),'above_normal_observed']=1
        data.loc[data.target>pd.Timestamp('2025-09-01'),'p_above_normal']=.999
        after=calibration.fit_calibrator(data,issue,1,'weather_climate_ml')
        self.assertEqual(before,after)
        self.assertEqual(before['calibration_target_max'],'2025-09-01T00:00:00')
        later=calibration.fit_calibrator(data,pd.Timestamp('2026-09-01'),1,'weather_climate_ml')
        self.assertEqual(later['calibration_target_max'],'2025-12-01T00:00:00')
        self.assertEqual(later['calibration_n'],84)

    def test_late_2025_issues_do_not_use_unavailable_2025_labels(self):
        data=history();data['lead']=3;data['target']=data.issue+pd.DateOffset(months=2)
        cal=calibration.fit_calibrator(data,pd.Timestamp('2025-11-01'),3,'weather_climate_ml')
        self.assertLessEqual(pd.Timestamp(cal['calibration_issue_max']),pd.Timestamp('2025-07-01'))
        self.assertEqual(cal['calibration_target_max'],'2025-09-01T00:00:00')

    def test_regularization_softens_overconfident_noise_and_preserves_order(self):
        cal=calibration.fit_calibrator(history(),pd.Timestamp('2026-03-01'),1,'weather_climate_ml')
        self.assertEqual(cal['calibration_status'],'fitted')
        self.assertGreaterEqual(cal['slope'],0);self.assertLess(cal['slope'],1)
        p=calibration.apply_calibrator([.1,.9],cal)
        self.assertGreater(p[0],.1);self.assertLess(p[1],.9)
        self.assertTrue((np.diff(calibration.apply_calibrator(np.linspace(0,1,101),cal))>=0).all())

    def test_single_class_small_samples_and_optimizer_failure_are_explicit(self):
        data=history();data['above_normal_observed']=1
        cal=calibration.fit_calibrator(data,pd.Timestamp('2026-01-01'),1,'weather_climate_ml')
        self.assertEqual(cal['calibration_status'],'identity_insufficient_history')
        np.testing.assert_allclose(calibration.apply_calibrator([.1,.5,.9],cal),[.1,.5,.9])
        data=history().iloc[:12]
        self.assertEqual(calibration.fit_calibrator(data,pd.Timestamp('2026-01-01'),1,'weather_climate_ml')['calibration_status'],'identity_insufficient_history')
        with patch.object(calibration,'minimize',return_value=type('Failed',(),{'success':False})()):
            self.assertEqual(calibration.fit_calibrator(history(),pd.Timestamp('2026-01-01'),1,'weather_climate_ml')['calibration_status'],'identity_optimizer_failure')

    def test_duplicates_invalid_labels_and_probabilities_are_rejected(self):
        data=history()
        with self.assertRaises(ValueError):calibration.fit_calibrator(pd.concat([data,data.iloc[:1]]),pd.Timestamp('2026-01-01'),1,'weather_climate_ml')
        for column,value in [('p_above_normal',np.nan),('p_above_normal',1.5),('above_normal_observed',2)]:
            altered=data.copy();altered.loc[0,column]=value
            with self.assertRaises(ValueError):calibration.fit_calibrator(altered,pd.Timestamp('2026-01-01'),1,'weather_climate_ml')
        with self.assertRaises(ValueError):calibration.apply_calibrator([-.1],{'slope':1,'intercept':0})

    def test_reliability_bins_include_one_and_report_small_sample_uncertainty(self):
        bins=calibration.reliability([0,.2,.8,1],[0,1,0,1])
        self.assertEqual(sum(b['n'] for b in bins),4)
        self.assertEqual(bins[-1]['n'],2)
        self.assertIsNone(bins[2]['observed_rate'])
        low,high=bins[-1]['observed_rate_wilson95']
        self.assertLess(low,.5);self.assertGreater(high,.5)

    def test_protocol_rejects_changed_inputs_before_evaluation(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input';source.write_text('original')
            spec={'calibrator':calibration.METHOD,'inputs':[{'path':'input','sha256':calibration.file_sha(source)}]}
            (root/'protocol.json').write_text(json.dumps(spec))
            with patch.object(calibration,'OUT',root),patch.object(calibration,'ROOT',root):
                self.assertEqual(calibration.load_protocol(),spec)
                source.write_text('changed')
                with self.assertRaises(ValueError):calibration.load_protocol()


if __name__=='__main__':unittest.main()
