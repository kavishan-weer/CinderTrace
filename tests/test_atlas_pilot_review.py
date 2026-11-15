import json
from pathlib import Path
import unittest
import pandas as pd
from pipeline.atlas_pilot_review import parse_missing,parse_outages,make_tables,SOURCES,OUT,longest_zero_run
from pipeline.import_atlas_pilot import verify_bundle,ROOT
from pipeline.atlas_source_compare import compare_native,parse_official_csv
import shapely

class PilotReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.points,*_=verify_bundle(ROOT/'cindertrace_atlas_lk_2023_pilot.zip')
    def test_upstream_failure_is_not_an_empty_gap_inventory(self):
        with self.assertRaises(ValueError):parse_missing(json.dumps({'success':False,'html':''}))
    def test_standard_and_nrt_missing_dates_are_not_mixed(self):
        raw=json.dumps({'success':True,'html':'<tr><td>2023-07-19</td><td>NOAA-20 (VIIRS)</td><td>2023-06-01</td><td>Suomi NPP (VIIRS)</td></tr>'})
        result=parse_missing(raw);self.assertEqual(result.satellite.tolist(),['NOAA-20']);self.assertEqual(result.date.tolist(),['2023-07-19'])
    def test_cross_midnight_published_outage_has_correct_dates(self):
        html='<tr><td>2023-207 - 2023-208</td><td>ignored</td><td>02:00:00</td><td>19:54:00</td><td>gap</td></tr>'
        result=parse_outages(html,'Suomi-NPP','https://example.com');self.assertEqual(str(result.iloc[0].end_utc),'2023-07-27 19:54:00+00:00')
        self.assertEqual(longest_zero_run([0,0,1,0,0,0,1]),3)
    def test_complete_grid_reconciles_and_gap_evidence_never_creates_estimates(self):
        missing=parse_missing(json.dumps({'success':True,'html':'<tr><td>2023-07-19</td><td>NOAA-20 (VIIRS)</td><td></td><td></td></tr>'}))
        outages=pd.DataFrame(columns=['satellite','start_utc','end_utc'])
        tables=make_tables(self.points,missing,outages)
        self.assertEqual(len(tables['native_filter_grid']),9984)
        self.assertEqual(tables['native_filter_grid'].recorded_detections.sum(),13366)
        daily=tables['daily_observed_counts'];row=daily[daily.date.eq('2023-07-19')&daily.satellite.eq('NOAA-20')].iloc[0]
        self.assertEqual(row.recorded_detections,0);self.assertTrue(row.upstream_lists_missing_standard_data)
        self.assertTrue(daily.coverage_adjusted_activity.isna().all())
        empty=tables['native_filter_grid'].query('published_type==1');self.assertTrue(empty.category_pilot_support.eq('no_record_in_this_pilot').all())
    def test_matching_counts_cannot_hide_replaced_rows_or_changed_native_values(self):
        sample=self.points.head(2).copy();self.assertEqual(compare_native(sample,sample)['status'],'matched_native_records')
        changed=sample.copy();changed.loc[changed.index[0],'audit_lon']+=.001
        report=compare_native(sample,changed);self.assertEqual(report['official_rows_missing_in_mirror'],1);self.assertEqual(report['mirror_rows_not_in_official'],1)
        changed=sample.copy();changed.loc[changed.index[0],'frp']+=1
        self.assertEqual(compare_native(sample,changed)['native_attribute_differences'],1)
    def test_duplicates_are_preserved_and_require_review(self):
        sample=self.points.head(2);double=pd.concat([sample,sample.iloc[:1]])
        report=compare_native(sample,double);self.assertEqual(report['official_rows_missing_in_mirror'],1);self.assertTrue(report['duplicate_keys_need_review'])
    def test_failed_api_response_is_not_an_observed_zero(self):
        with self.assertRaisesRegex(ValueError,'schema'):
            parse_official_csv(b'error\ninvalid map key\n','MODIS_SP','2023-01-01','2023-01-02',shapely.box(79,5,83,11))
    def test_api_clips_to_same_polygon_and_validates_time_window(self):
        raw=b'latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,type,frp,scan,track,daynight,brightness,bright_t31\n7,80,2023-01-01,0430,T,MODIS,50,61.03,0,2,1,1,D,320,300\n7,82,2023-01-01,0430,T,MODIS,50,61.03,0,2,1,1,D,320,300\n'
        parsed=parse_official_csv(raw,'MODIS_SP','2023-01-01','2023-01-02',shapely.box(79,6,81,8));self.assertEqual(len(parsed),1);self.assertEqual(parsed.iloc[0].satellite,'Terra')
        with self.assertRaisesRegex(ValueError,'outside'):
            parse_official_csv(raw,'MODIS_SP','2023-01-02','2023-01-03',shapely.box(79,6,81,8))

class OfficialSatelliteCodesTests(unittest.TestCase):
    def csv(self,code):
        return ('latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,version,type,frp,scan,track,daynight,bright_ti4,bright_ti5\n'
                f'7,80,2023-11-02,0430,{code},VIIRS,n,2,0,2,0.4,0.4,D,330,300\n').encode()
    def test_documented_noaa20_alias_is_accepted_only_for_noaa20(self):
        f=parse_official_csv(self.csv('N20'),'VIIRS_NOAA20_SP','2023-11-01','2023-11-06',shapely.box(79,6,81,8))
        self.assertEqual(f.iloc[0].satellite,'NOAA-20')
        with self.assertRaisesRegex(ValueError,'VIIRS_SNPP_SP.*2023-11-01.*N20'):
            parse_official_csv(self.csv('N20'),'VIIRS_SNPP_SP','2023-11-01','2023-11-06',shapely.box(79,6,81,8))
    def test_unknown_and_missing_codes_show_counts_without_becoming_zero(self):
        with self.assertRaisesRegex(ValueError,'Received code counts.*unexpected'):
            parse_official_csv(self.csv('unexpected'),'VIIRS_SNPP_SP','2023-11-01','2023-11-06',shapely.box(79,6,81,8))
        with self.assertRaisesRegex(ValueError,'missing'):
            parse_official_csv(self.csv(''),'VIIRS_SNPP_SP','2023-11-01','2023-11-06',shapely.box(79,6,81,8))
    def test_outer_whitespace_is_formatting_not_another_satellite(self):
        f=parse_official_csv(self.csv(' N '),'VIIRS_SNPP_SP','2023-11-01','2023-11-06',shapely.box(79,6,81,8))
        self.assertEqual(f.iloc[0].satellite,'Suomi-NPP')
