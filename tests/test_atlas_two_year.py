import unittest
from pipeline.atlas_two_year import availability_table,plan_requests,parse_gap_evidence
from pipeline.atlas_source_compare import parse_official_csv
import shapely

class TwoYearPlanningTests(unittest.TestCase):
    def availability(self,n21=True):
        s='data_id,min_date,max_date\nMODIS_SP,2000-11-01,2025-12-31\nVIIRS_SNPP_SP,2012-01-20,2025-12-31\nVIIRS_NOAA20_SP,2018-04-01,2025-12-31\n'
        if n21:s+='VIIRS_NOAA21_SP,2024-01-17,2025-12-31\n'
        return availability_table(s.encode())
    def test_partial_noaa21_archive_is_explicit_and_plan_is_complete(self):
        plans,windows=plan_requests(self.availability())
        self.assertEqual(len(windows),511)
        n21=plans[plans.source.eq('VIIRS_NOAA21_SP')].iloc[0]
        self.assertEqual(n21.start,'2024-01-17');self.assertEqual(n21.days,350);self.assertEqual(n21.status,'partial_year_advertised')
        self.assertFalse(any(y==2022 and s=='VIIRS_NOAA21_SP' for y,s,_,_ in windows))
    def test_unadvertised_source_has_no_windows_and_no_invented_zero(self):
        plans,windows=plan_requests(self.availability(False))
        self.assertEqual(len(windows),441)
        row=plans[plans.source.eq('VIIRS_NOAA21_SP')].iloc[0]
        self.assertEqual(row.status,'standard_source_not_advertised');self.assertIsNone(row.start)
    def test_bad_availability_does_not_turn_into_empty_plan(self):
        with self.assertRaises(ValueError):availability_table(b'error\nbad key\n')
        with self.assertRaises(ValueError):availability_table(b'data_id,min_date,max_date\nMODIS_SP,2025-01-01,2024-01-01\n')
    def test_noaa21_alias_does_not_reclassify_another_stream(self):
        raw=b'latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,type,frp,scan,track,daynight,bright_ti4,bright_ti5\n7,80,2024-01-20,0430,N21,VIIRS,n,2,0,2,0.4,0.4,D,330,300\n'
        f=parse_official_csv(raw,'VIIRS_NOAA21_SP','2024-01-20','2024-01-25',shapely.box(79,6,81,8));self.assertEqual(f.iloc[0].satellite,'NOAA-21')
        with self.assertRaises(ValueError):parse_official_csv(raw,'VIIRS_SNPP_SP','2024-01-20','2024-01-25',shapely.box(79,6,81,8))
