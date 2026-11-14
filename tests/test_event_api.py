import unittest
from unittest.mock import patch
import h3
import pandas as pd
from shapely.geometry import box
from pipeline import event_api as api


class EventMapAPITests(unittest.TestCase):
    def setUp(self):
        rows=[]
        for identifier,day,lon,frp in [('a','2020-08-31',80.5,1000),('a','2020-09-01',80,20),('a','2020-09-02',80.5,50),('b','2020-08-01',80,10),('b','2020-10-01',80,10),('c','2020-09-01',80,5)]:
            rows.append(dict(event_id=identifier,acq_datetime=pd.Timestamp(day,tz='UTC'),lat=8.,lon=lon,sub=0,frp=frp,footprint_h3=h3.latlng_to_cell(8,lon,8)))
        self.points=pd.DataFrame(rows)
        events=[]
        for identifier,g in self.points.groupby('event_id'):
            events.append(dict(event_id=identifier,start_utc=g.acq_datetime.min(),end_utc=g.acq_datetime.max(),observed_span_hours=(g.acq_datetime.max()-g.acq_datetime.min()).total_seconds()/3600,observed_dates=len(g),detection_count=len(g),peak_detection_frp_mw=g.frp.max(),singleton=len(g)==1,multi_date_support=len(g)>1,touches_region_grid_edge=False,touches_archive_time_edge=True,end_in_latest_archive_month=False,long_chain_caution=False,possible_persistent_source=False,min_lon=g.lon.min(),max_lon=g.lon.max(),min_lat=8.,max_lat=8.,calendar_span_days=(g.acq_datetime.max()-g.acq_datetime.min()).days+1,max_detection_gap_hours=24.,sampled_grid_area_km2=1.))
        self.patch=patch.object(api,'catalog',return_value=(pd.DataFrame(events),self.points,{'input_fingerprint':'test'},pd.DataFrame(),pd.DataFrame()));self.patch.start()

    def tearDown(self):self.patch.stop()

    def test_month_area_requires_observations_and_preserves_full_candidate_metrics(self):
        result=api.query_events({'region':'lk','month':'2020-09'},box(79.99,7.99,80.01,8.01))
        self.assertEqual(result['total'],1);self.assertEqual(result['hidden_singletons'],1)
        a=result['candidates'][0];self.assertEqual(a['event_id'],'a')
        self.assertEqual(a['selected_month_detections'],1);self.assertEqual(a['detection_count'],3)
        self.assertEqual(a['peak_detection_frp_mw'],1000)
        self.assertEqual(a['marker_lon'],80)
        self.assertNotIn('b',[row['event_id'] for row in result['candidates']])

    def test_singletons_are_explicit_and_month_selection_never_reclusters(self):
        result=api.query_events({'region':'lk','month':'2020-09','include_singletons':True})
        self.assertEqual(result['total'],2)
        self.assertTrue(next(c for c in result['candidates'] if c['event_id']=='c')['singleton'])
        self.assertEqual(api.query_events({'region':'lk','month':'2019-01'})['candidates'],[])

    def test_detail_timeline_is_full_history_and_day_footprint_is_observed_only(self):
        request={'region':'lk','event_id':'a'}
        detail=api.event_detail(request)
        self.assertEqual(sum(d['detections'] for d in detail['daily']),3)
        self.assertEqual(detail['daily'][0]['date'],'2020-08-31')
        self.assertEqual(detail['footprint_count'],2)
        selected=api.event_detail({**request,'day':'2020-09-01'})
        self.assertEqual(selected['footprint_hexes'],[h3.latlng_to_cell(8,80,8)])
        self.assertEqual(selected['candidate']['detection_count'],3)
        self.assertEqual(selected['reference_links'],[])

    def test_invalid_queries_and_unobserved_dates_are_rejected(self):
        for request in [{'region':'../../','month':'2020-09'},{'region':'lk','month':'2020-99'},{'region':'lk','month':'2020-09','satellite':'merged'},{'region':'lk','month':'2020-09','include_singletons':'yes'}]:
            with self.assertRaises(ValueError):api.query_events(request)
        with self.assertRaises(ValueError):api.event_detail({'region':'lk','event_id':'unknown'})
        with self.assertRaises(ValueError):api.event_detail({'region':'lk','event_id':'a','day':'2020-09-03'})


if __name__=='__main__':unittest.main()
