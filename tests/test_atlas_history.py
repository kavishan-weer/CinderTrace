from pathlib import Path
from io import BytesIO
import json,tempfile,unittest
import pandas as pd
from pipeline.atlas_two_year import availability_table
from pipeline.atlas_history import history_plan,history_grids,history_canonical,history_evidence,verify_year_files,digest

AVAILABLE=availability_table(b'data_id,min_date,max_date\nMODIS_SP,2000-11-01,2025-12-31\nVIIRS_SNPP_SP,2012-01-20,2025-12-31\nVIIRS_NOAA20_SP,2018-04-01,2025-12-31\n')
class HistoryHelpersTests(unittest.TestCase):
    def empty(self):return history_canonical([])
    def evidence(self):
        return pd.DataFrame(columns=['satellite','start_utc','end_utc']),pd.DataFrame(columns=['date','satellite'])
    def test_history_plan_does_not_query_before_archive_or_touch_benchmark(self):
        plans,windows=history_plan(AVAILABLE,[2000,2001,2002])
        self.assertEqual(len(windows),159);self.assertEqual(windows[0],(2000,'MODIS_SP','2000-11-01','2000-11-06'))
        self.assertFalse(any(s!='MODIS_SP' for _,s,_,_ in windows))
        with self.assertRaises(ValueError):history_plan(AVAILABLE,[2022])
        with self.assertRaises(ValueError):history_plan(AVAILABLE,[2000,2000])
    def test_pre_archive_and_pre_aqua_are_null_not_zero(self):
        for year in [2000,2002]:
            plans,_=history_plan(AVAILABLE,[year]);gaps,missing=self.evidence();daily,monthly,grid=history_grids(year,self.empty(),plans,gaps,missing)
            a=daily[daily.satellite.eq('Aqua')&daily.date.lt('2002-07-04')];self.assertTrue(a.recorded_detections.isna().all())
            viirs=daily[daily.satellite.isin(['Suomi-NPP','NOAA-20'])];self.assertTrue(viirs.recorded_detections.isna().all())
            if year==2000:
                self.assertTrue(daily[daily.date.lt('2000-11-01')].recorded_detections.isna().all())
                nov=monthly[monthly.month.eq('2000-11')&monthly.satellite.eq('Terra')].iloc[0];self.assertEqual(nov.full_month_standard_detections,0)
            if year==2002:
                july=monthly[monthly.month.eq('2002-07')&monthly.satellite.eq('Aqua')].iloc[0]
                self.assertEqual(july.supported_queried_days,28);self.assertTrue(pd.isna(july.full_month_standard_detections));self.assertEqual(july.detections_on_queried_dates,0)
            self.assertEqual(len(grid),9984);self.assertTrue(daily.coverage_adjusted_activity.isna().all())
    def test_viirs_partial_first_month_and_leap_day(self):
        plans,_=history_plan(AVAILABLE,[2012]);gaps,missing=self.evidence();daily,monthly,_=history_grids(2012,self.empty(),plans,gaps,missing)
        self.assertEqual(len(daily[daily.date.eq('2012-02-29')]),4)
        jan=monthly[monthly.month.eq('2012-01')&monthly.satellite.eq('Suomi-NPP')].iloc[0]
        self.assertEqual(jan.supported_queried_days,12);self.assertTrue(pd.isna(jan.full_month_standard_detections))
    def test_malformed_notice_row_is_retained_not_silently_dropped(self):
        raw=b'<tr><td>2001-001</td><td>Jan 1</td><td>12:00:00</td><td>11:00:00</td><td>ambiguous</td></tr>'
        public={'terra':raw,'snpp':b'','missing':json.dumps({'success':True,'html':''}).encode()}
        gaps,missing,unparsed=history_evidence(public,[2001]);self.assertEqual(len(gaps),0);self.assertEqual(len(unparsed),1);self.assertIn('non-positive',unparsed.iloc[0].reason)
    def test_completed_year_checksum_guard_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'data.txt').write_bytes(b'original');m={'files':{'data.txt':{'bytes':8,'sha256':digest(b'original')}}};(p/'year_manifest.json').write_text(json.dumps(m))
            self.assertEqual(verify_year_files(p),m)
            (p/'data.txt').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):verify_year_files(p)

class EmptyHistoricalYearTests(unittest.TestCase):
    def test_header_only_success_is_an_empty_standard_year_with_proper_null_support(self):
        import shapely
        from pipeline.atlas_source_compare import parse_official_csv
        raw=b'latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,type,frp,scan,track,daynight,brightness,bright_t31\n'
        f=parse_official_csv(raw,'MODIS_SP','2000-11-01','2000-11-06',shapely.box(79,5,82,10))
        f['source_stream']='MODIS_SP';f['source_response_sha256']=digest(raw);f['source_row_ordinal']=f.index.to_numpy()
        canonical=history_canonical([f]);self.assertEqual(len(canonical),0);self.assertEqual(str(canonical.observation_id.dtype),'string')
        plans,_=history_plan(AVAILABLE,[2000]);gaps=pd.DataFrame(columns=['satellite','start_utc','end_utc']);missing=pd.DataFrame(columns=['date','satellite'])
        daily,monthly,grid=history_grids(2000,canonical,plans,gaps,missing)
        self.assertEqual(daily.recorded_detections.sum(),0);self.assertTrue(daily[daily.satellite.ne('Terra')].recorded_detections.isna().all())
        self.assertTrue(monthly[monthly.month.lt('2000-11')].full_month_standard_detections.isna().all())
        with tempfile.TemporaryDirectory() as tmp:canonical.to_parquet(Path(tmp)/'empty.parquet',index=False)
