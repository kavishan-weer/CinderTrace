import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import h3
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from ml.events import Config, cluster_points, EARTH_KM, load_points, summarize, audit_catalog
from ml.validate_events import support


def points(records):
    return pd.DataFrame([{'acq_datetime':pd.Timestamp('2020-12-31T12:00Z')+pd.Timedelta(hours=hour),'lat':lat,'lon':lon} for hour,lat,lon in records])


def partition(labels):
    return {frozenset(np.flatnonzero(labels==label)) for label in set(labels)}


class EventClusteringTests(unittest.TestCase):
    def test_separate_locations_and_time_gaps_do_not_merge(self):
        data=points([(0,8,80),(1,8,80.01),(1,8,80.1),(50,8,80)])
        labels,_=cluster_points(data,Config(2,48),batch_size=1)
        self.assertEqual(partition(labels),{frozenset([0,1]),frozenset([2]),frozenset([3])})

    def test_inclusive_radius_time_boundary_crosses_new_year(self):
        longitude=2/EARTH_KM*180/np.pi
        data=points([(0,0,0),(48,0,longitude),(96.0001,0,longitude)])
        labels,_=cluster_points(data,Config(2,48),1)
        self.assertEqual(partition(labels),{frozenset([0,1]),frozenset([2])})

    def test_chaining_is_explicit_and_old_connections_survive_window_eviction(self):
        # A persistent branching event reconnects its branches after the old
        # bridge disappears from the sliding time window.
        data=points([(0,0,0),(1,0,.015),(1,0,-.015),(40,0,.015),(40,0,-.015),(70,0,.015),(70,0,-.015)])
        labels,_=cluster_points(data,Config(2,48),2)
        self.assertEqual(len(set(labels)),1)
        self.assertGreater((data.acq_datetime.max()-data.acq_datetime.min()).total_seconds()/3600,48)

    def test_duplicate_observations_remain_assigned_and_input_order_does_not_change_partition(self):
        data=points([(0,8,80),(0,8,80),(2,8,80.01),(2,8,81)])
        labels,_=cluster_points(data,batch_size=2)
        shuffled=np.array([3,1,0,2]);other,_=cluster_points(data.iloc[shuffled],batch_size=1)
        restored=np.empty(4,dtype=int);restored[shuffled]=other
        self.assertEqual(partition(labels),partition(restored));self.assertEqual(len(labels),4)

    def test_batch_algorithm_matches_independent_all_pairs_haversine_oracle(self):
        rng=np.random.default_rng(83)
        for center in [0,40,-34]:
            data=points(list(zip(rng.uniform(0,200,120),center+rng.uniform(-.04,.04,120),80+rng.uniform(-.04,.04,120))))
            lat,lon=np.radians(data.lat.to_numpy()),np.radians(data.lon.to_numpy())
            distance=2*EARTH_KM*np.arcsin(np.minimum(1,np.sqrt(np.sin((lat[:,None]-lat)/2)**2+np.cos(lat[:,None])*np.cos(lat)*np.sin((lon[:,None]-lon)/2)**2)))
            times=data.acq_datetime.dt.as_unit('ns').astype('int64').to_numpy()/3.6e12
            a,b=np.where((distance<=2)&(np.abs(times[:,None]-times)<=48))
            _,expected=connected_components(coo_matrix((np.ones(len(a)),(a,b)),shape=(len(data),len(data))),directed=False)
            for batch in [1,7,1024]:
                actual,_=cluster_points(data,Config(2,48),batch)
                self.assertEqual(partition(actual),partition(expected))

    def test_dateline_and_high_latitude_distances_are_spherical(self):
        labels,_=cluster_points(points([(0,80,179.99),(1,80,-179.99)]),Config(2,48),1)
        self.assertEqual(len(set(labels)),1)

    def test_empty_and_invalid_inputs(self):
        labels,_=cluster_points(points([]).reindex(columns=['acq_datetime','lat','lon']))
        self.assertEqual(len(labels),0)
        for config in [(0,48),(2,float('nan')),(2,0)]:
            with self.assertRaises(ValueError):Config(*config)
        with self.assertRaises(ValueError):cluster_points(points([(0,91,80)]))

    def test_satellite_filters_raw_lineage_and_event_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for folder in ['data/raw/lk','data/boundaries','data/harmonized']:(root/folder).mkdir(parents=True)
            cell=h3.latlng_to_cell(8,80,6)
            pd.DataFrame([dict(h3_cell=cell,sub=0)]).to_parquet(root/'data/boundaries/lk_members.parquet')
            pd.DataFrame([dict(h3_cell=cell,cat='veg')]).to_parquet(root/'data/harmonized/lk_cells.parquet')
            rows=[]
            for satellite,conf,source,frp,hour in [('Suomi-NPP','n',0,8,0),('Suomi-NPP','h',None,20,24),('Suomi-NPP','l',0,1,1),('Suomi-NPP',None,0,1,1),('Suomi-NPP','n',2,1,1),('NOAA-20','h',0,1000,1)]:
                rows.append(dict(satellite=satellite,sensor='VIIRS',confidence=conf,confidence_pct=None,type=source,frp=frp,lat=8.,lon=80.,acq_datetime=pd.Timestamp('2020-12-31T12:00')+pd.Timedelta(hours=hour)))
            pd.DataFrame(rows).to_parquet(root/'data/raw/lk/2020.parquet')
            with patch('ml.events.ROOT',root):
                data,audit=load_points('lk','Suomi-NPP');labels,_=cluster_points(data)
                events,members,daily=summarize(data,labels,'lk','Suomi-NPP','test')
                self.assertTrue(all(audit_catalog(events,members,daily,2).values()))
                event=events.iloc[0]
                self.assertEqual(event.peak_detection_frp_mw,20)
                self.assertEqual(event.observed_span_hours,24)
                self.assertEqual(event.observed_dates,2)
                self.assertEqual(event.calendar_span_days,2)
                self.assertTrue(members.detection_id.str.startswith('lk:2020.parquet:').all())
                self.assertEqual(audit['excluded_low_or_unknown_individual_confidence'],2)
                self.assertEqual(audit['excluded_source_category_or_type'],1)
                self.assertEqual(audit['raw_satellite_rows'],5)
                shuffled=data.sample(frac=1,random_state=7).reset_index(drop=True)
                labels,_=cluster_points(shuffled);again,_,_=summarize(shuffled,labels,'lk','Suomi-NPP','test')
                self.assertEqual(events.event_id.tolist(),again.event_id.tolist())
                wrong=events.copy();wrong.loc[0,'detection_count']=3
                with self.assertRaises(AssertionError):audit_catalog(wrong,members,daily,2)
                empty=data.iloc[:0];e,m,d=summarize(empty,np.array([],dtype=int),'lk','Suomi-NPP','test')
                self.assertTrue(all(audit_catalog(e,m,d,0).values()))

    def test_independent_satellite_support_is_directional_and_time_limited(self):
        ref=points([(0,8,80),(0,8,81)])
        other=points([(1,8,80),(49,8,81)])
        result=support(ref,np.array([0,1]),other,np.array([True,True]),temporal_hours=24)
        self.assertEqual(result['reference_core_point_support_fraction'],.5)
        self.assertEqual(result['noaa20_point_match_fraction'],.5)
        self.assertEqual(result['core_candidates_with_noaa20_support'],1)


if __name__=='__main__':unittest.main()
