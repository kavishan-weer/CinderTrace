import json,unittest
import numpy as np
import pandas as pd
from pipeline.atlas_transfer_research import activity_sets,qualify_months,fit_model,predict_model,predict_candidate,evaluate_split,empirical_radius,annual_evaluation

class TransferResearchTests(unittest.TestCase):
    def sample(self):
        rows=[]
        for year in range(2003,2025):
            for month in range(1,13):
                x=float((month*7+year%7)%50+1);rows.append({'year':year,'month_number':month,'month':f'{year}-{month:02}','common_calendar_days':28,'calendar_fraction':.9,
                  'terra':x,'aqua':x/2,'modis':x*1.5+2,'snpp':x*2.4+5,'noaa20':x*2.3+4})
        return pd.DataFrame(rows)
    def test_holdout_target_changes_do_not_change_selection_predictions_or_bounds(self):
        f=self.sample();a,audit=evaluate_split(f,'modis_to_snpp',[2020]);g=f.copy();g.loc[g.year.eq(2020),'snpp']*=100
        b,_=evaluate_split(g,'modis_to_snpp',[2020])
        for x,y in zip(a,b):
            self.assertEqual(x['prediction'],y['prediction']);self.assertEqual(x['lower_90'],y['lower_90']);self.assertEqual(x['upper_90'],y['upper_90'])
        self.assertFalse(set(audit['fit_years'])&set(audit['calibration_years']));self.assertNotIn(2020,audit['fit_years']+audit['calibration_years'])
    def test_calibration_labels_change_intervals_but_not_point_model_or_selection(self):
        f=self.sample();a,audit=evaluate_split(f,'modis_to_snpp',[2024]);g=f.copy();g.loc[g.year.isin(audit['calibration_years']),'snpp']*=10
        b,other=evaluate_split(g,'modis_to_snpp',[2024]);self.assertEqual(audit['selected_model'],other['selected_model'])
        self.assertEqual([r['prediction'] for r in a],[r['prediction'] for r in b]);self.assertNotEqual(a[0]['upper_90'],b[0]['upper_90'])
    def test_chronological_and_training_windows_never_include_test_or_calibration(self):
        rows,audit=evaluate_split(self.sample(),'terra_chain_to_snpp',[2022,2023,2024],'last5',True)
        self.assertEqual(len(audit['fit_years']),5);self.assertTrue(all(y<2022 for y in audit['fit_years']+audit['calibration_years']))
        self.assertTrue(all(r['year']>=2022 for r in rows));self.assertEqual(len(rows),108)
    def test_union_target_is_never_below_observed_terra(self):
        f=self.sample();bad={'kind':'positive_affine','intercept':0.,'slope':.1}
        p=predict_candidate(bad,f,'terra_to_modis');self.assertTrue((p>=f.terra).all())
        chain=predict_candidate((bad,{'kind':'global_ratio','ratio':2.}),f,'terra_chain_to_snpp');np.testing.assert_allclose(chain,f.terra*2)
    def test_zero_predictor_does_not_fabricate_a_ratio_or_force_reference_to_zero(self):
        f=self.sample();f['modis']=0.
        self.assertIsNone(fit_model(f,'modis','snpp','global_ratio'))
        model=fit_model(f,'modis','snpp','positive_affine');self.assertTrue((predict_model(model,f,'modis')>0).all())
        f['snpp']=0.;self.assertIsNone(fit_model(f,'modis','snpp','positive_affine'))
    def test_too_little_calibration_support_withholds_interval(self):
        self.assertIsNone(empirical_radius(np.ones(16),np.ones(16),.9));self.assertEqual(empirical_radius(np.ones(24),np.ones(24),.9),0.)
    def test_sensor_cell_days_deduplicate_within_sensor_and_union_not_across_days(self):
        p=pd.DataFrame({'type':[0]*4,'satellite':['Terra','Terra','Aqua','Terra'],'latitude':[7.]*4,'longitude':[80.]*4,'acq_date':['2003-01-01']*3+['2003-01-02'],'confidence':['50']*4,'confidence_pct':[50]*4})
        sets,stats=activity_sets(p,8,'vegetation_all_confidence');self.assertEqual(stats['sensor_cell_days'],3)
        self.assertEqual(len(sets[('2003-01-01','Terra')]|sets[('2003-01-01','Aqua')]),1)
    def test_annual_metrics_require_all_twelve_months_and_withhold_intervals(self):
        rows,_=evaluate_split(self.sample(),'modis_to_snpp',[2020]);p=pd.DataFrame(rows);p['configuration']='test'
        annual,summary=annual_evaluation(p);self.assertEqual(len(annual),3);self.assertTrue(annual.annual_interval_status.str.startswith('withheld').all())
        a,_=annual_evaluation(p[p.month.ne('2020-01')]);self.assertEqual(len(a),0)
    def test_common_calendar_support_is_not_observing_coverage_and_keeps_true_zeros(self):
        records=[]
        for date in pd.date_range('2003-01-01','2003-01-31').strftime('%Y-%m-%d'):
            for s in ['Terra','Aqua','Suomi-NPP','NOAA-20']:records.append({'date':date,'satellite':s,'recorded_detections':0 if s in ['Terra','Aqua'] else pd.NA,'upstream_lists_missing_standard_data':False,'documented_global_gap_on_date':False})
        q=qualify_months(pd.DataFrame(records),{},'all_documented_global_gap_dates')
        t=q[q.task.eq('terra_to_modis')].iloc[0];self.assertTrue(t.eligible_month);self.assertEqual(t.modis,0);self.assertFalse(t.observing_opportunities_verified)
        v=q[q.task.eq('modis_to_snpp')].iloc[0];self.assertFalse(v.eligible_month);self.assertTrue(pd.isna(v.snpp))
