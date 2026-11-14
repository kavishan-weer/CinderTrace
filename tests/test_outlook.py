import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml.outlook_data import parse_power, parse_oni, parse_dmi, choose_sites
from ml.outlook import (Policy, feature_row, fire_target, seasonal_pool,
                        fit_origin, proper_scores, paired_skill, model_quantiles,
                        HISTORY_FEATURES, WEATHER_FEATURES)


def weather_payload():
    dates=pd.date_range('2020-02-01','2020-02-29').strftime('%Y%m%d')
    units={'T2M':'C','PRECTOTCORR':'mm/day','RH2M':'%','WS2M':'m/s'}
    values={'T2M':25,'PRECTOTCORR':2,'RH2M':60,'WS2M':3}
    return {'header':{'time_standard':'UTC','fill_value':-999},
            'parameters':{k:{'units':v} for k,v in units.items()},
            'properties':{'parameter':{k:dict.fromkeys(dates,v) for k,v in values.items()}}}


def histories():
    dates=pd.date_range('2011-01-01','2027-12-01',freq='MS')
    y=pd.Series(100+dates.month*10+np.arange(len(dates)),index=dates,dtype=float)
    weather=pd.DataFrame({'temperature_c':25.,'rain_mm':100.,'humidity_pct':60.,'wind_mps':3.},index=dates)
    climate=pd.DataFrame({'oni':.4,'dmi':-.2},index=dates)
    return y,weather,climate


class OutlookInputTests(unittest.TestCase):
    def test_daily_precipitation_is_summed_with_leap_calendar(self):
        result=parse_power(json.dumps(weather_payload())).iloc[0]
        self.assertTrue(result.complete)
        self.assertEqual(result.rain_mm,58)
        self.assertEqual(result.temperature_c,25)

    def test_missing_day_sentinel_and_invalid_weather_never_become_zero(self):
        for kind in ['missing_day','sentinel','invalid_humidity']:
            data=weather_payload();params=data['properties']['parameter']
            if kind=='missing_day':
                for values in params.values():del values['20200229']
            elif kind=='sentinel':params['T2M']['20200210']=-999
            else:params['RH2M']['20200210']=120
            result=parse_power(json.dumps(data)).iloc[0]
            self.assertFalse(result.complete)
            self.assertTrue(pd.isna(result.rain_mm))
        data=weather_payload();data['parameters']['PRECTOTCORR']['units']='mm'
        with self.assertRaises(ValueError):parse_power(json.dumps(data))

    def test_oni_uses_centre_month_and_dmi_retains_negative_anomalies(self):
        oni=parse_oni('SEAS YR TOTAL ANOM\nDJF 2019 27.0 -0.4\nNDJ 2019 27.1 0.7')
        self.assertEqual(oni[pd.Timestamp('2019-01-01')],-.4)
        self.assertEqual(oni[pd.Timestamp('2019-12-01')],.7)
        dmi=parse_dmi('1870 2026\n2019 -0.4 '+ ' '.join(['0.1']*10)+' -9999\n')
        self.assertEqual(dmi.iloc[0],-.4);self.assertTrue(pd.isna(dmi.iloc[-1]))
        with self.assertRaises(ValueError):parse_oni('DJF 2019 27 0.1\nDJF 2019 27 0.2')

    def test_spatial_weights_are_fixed_by_area_not_fire_counts(self):
        members=pd.DataFrame({'lat':[0,1,2,3,4,5],'lon':[10,11,12,13,14,15],'area_km2':[1,2,3,4,5,6]})
        a=choose_sites(members,2)
        b=choose_sites(members.assign(fire_detections=[1e9,0,0,0,0,0]),2)
        self.assertEqual(a,b);self.assertAlmostEqual(sum(s['weight'] for s in a),1)

    def test_target_rejects_transfer_partial_low_data_and_missing_confidence(self):
        base=[dict(month=pd.Timestamp('2020-01-01'),cat='veg',conf=c,comparison_eligible=True,
                   period_status='inferred_available',source='viirs_observed',low_data=False,viirs_snpp_raw=10.) for c in [2,3]]
        self.assertEqual(fire_target(pd.DataFrame(base)).iloc[0],20)
        for column,value in [('source','modis_transferred'),('period_status','provisional'),('low_data',True),('comparison_eligible',False),('viirs_snpp_raw',np.nan)]:
            data=pd.DataFrame(base);data.loc[0,column]=value
            self.assertTrue(pd.isna(fire_target(data).iloc[0]))
        self.assertTrue(pd.isna(fire_target(pd.DataFrame(base[:1])).iloc[0]))


class OutlookValidationTests(unittest.TestCase):
    def test_future_perturbation_cannot_change_features_at_any_lead(self):
        y,w,c=histories();issue=pd.Timestamp('2020-08-01')
        for lead in [1,2,3]:
            original=feature_row(y,w,c,issue,lead)
            altered_y=y.copy();altered_w=w.copy();altered_c=c.copy()
            altered_y.loc[altered_y.index>pd.Timestamp('2020-06-01')]=999999
            altered_w.loc[altered_w.index>pd.Timestamp('2020-05-01')]=999999
            altered_c.loc[altered_c.index>pd.Timestamp('2020-03-01'),'oni']=999999
            altered_c.loc[altered_c.index>pd.Timestamp('2020-04-01'),'dmi']=999999
            changed=feature_row(altered_y,altered_w,altered_c,issue,lead)
            np.testing.assert_equal([original[k] for k in HISTORY_FEATURES+WEATHER_FEATURES],
                                    [changed[k] for k in HISTORY_FEATURES+WEATHER_FEATURES])
            self.assertNotEqual(original['y'],changed['y'])

    def test_missing_latest_input_is_not_silently_forward_filled(self):
        y,w,c=histories();c.loc['2020-04-01','dmi']=np.nan
        row=feature_row(y,w,c,pd.Timestamp('2020-08-01'),3)
        self.assertFalse(row['full_inputs_ready'])
        self.assertTrue(pd.isna(row['dmi_lag4']))

    def test_training_purges_unavailable_labels_for_all_three_leads(self):
        y,w,c=histories();issue=pd.Timestamp('2020-08-01')
        for lead in [1,2,3]:
            examples=pd.DataFrame([feature_row(y,w,c,d,lead) for d in pd.date_range('2013-01-01','2021-12-01',freq='MS')])
            def fake(train,test,columns):
                self.assertLessEqual(train.target.max(),pd.Timestamp('2020-06-01'))
                self.assertLess(train.issue.max(),issue)
                return np.array([[50.,75.,100.,125.,150.]])
            with patch('ml.outlook.model_quantiles',side_effect=fake) as model:
                results=fit_origin(examples,y,issue)
            self.assertEqual(model.call_count,2)
            self.assertEqual(len(results),3)
            self.assertEqual(results[0]['target'],issue+pd.DateOffset(months=lead-1))
            self.assertLessEqual(results[0]['baseline_history_max'],pd.Timestamp('2020-06-01'))

    def test_baseline_is_same_month_and_only_available_history(self):
        y,_,_=histories();issue=pd.Timestamp('2020-08-01')
        pool=seasonal_pool(y,issue,pd.Timestamp('2020-10-01'))
        self.assertEqual(set(pool.index.month),{10})
        self.assertEqual(pool.index.max(),pd.Timestamp('2019-10-01'))
        with self.assertRaises(ValueError):Policy(weather_lag_months=0)

    def test_interval_score_penalizes_misses_and_bootstrap_is_paired(self):
        q=[0,2,5,8,10]
        self.assertAlmostEqual(proper_scores(5,q)['wis'],2/3)
        self.assertGreater(proper_scores(20,q)['wis'],proper_scores(5,q)['wis'])
        rows=[]
        for d in pd.date_range('2020-01-01','2022-12-01',freq='MS'):
            rows.extend([dict(lead=1,target=d,model='seasonal',wis=2),dict(lead=1,target=d,model='weather_climate_ml',wis=1)])
        skill=paired_skill(pd.DataFrame(rows),1,'wis',iterations=100)
        self.assertEqual(skill['skill'],.5)
        self.assertEqual(skill['year_block_bootstrap_95'],[.5,.5])

    def test_real_quantile_fit_is_nonnegative_ordered_with_native_missing_inputs(self):
        y,w,c=histories()
        examples=pd.DataFrame([feature_row(y,w,c,d,1) for d in pd.date_range('2013-01-01','2019-12-01',freq='MS')])
        examples.loc[:3,'fire_log_lag2']=np.nan
        q=model_quantiles(examples.iloc[:-1],examples.iloc[-1:],HISTORY_FEATURES+WEATHER_FEATURES)[0]
        self.assertTrue(np.isfinite(q).all());self.assertTrue((q>=0).all());self.assertTrue((np.diff(q)>=0).all())


if __name__=='__main__':unittest.main()
