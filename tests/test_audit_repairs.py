import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
from pipeline.coverage import build_coverage
from pipeline.harmonize import harmonize_slice

class AuditRepairs(unittest.TestCase):
    def test_documented_outage_month_excluded_even_when_detections_exist(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'p.parquet'
            pd.DataFrame({'satellite':['Suomi-NPP']*3,'acq_date':pd.to_datetime(['2024-06-01','2024-07-02','2024-08-31'])}).to_parquet(path)
            c=build_coverage(path,pd.date_range('2024-06-01','2024-08-01',freq='MS'),'2024-09-10')
            july=c[(c.fam=='snpp')&(c.month==pd.Timestamp('2024-07-01'))].iloc[0]
            self.assertTrue(july.known_major_outage);self.assertEqual(july.status,'provisional')

    def test_empty_reference_slice_is_zero_only_where_archive_available(self):
        dates=pd.date_range('2013-01-01',periods=3,freq='MS')
        d=pd.DataFrame({'modis':[0.,0.,np.nan],'terra':[0.,0.,np.nan],'snpp':[0.,0.,np.nan],
            'modis_status':['inferred_available','provisional','missing'],'snpp_status':['inferred_available','provisional','missing'],'training_ok':[True,False,False]},index=dates)
        out,_=harmonize_slice(d)
        self.assertEqual(out.harmonized.iloc[0],0);self.assertTrue(out.comparison_eligible.iloc[0])
        self.assertFalse(out.comparison_eligible.iloc[1]);self.assertTrue(pd.isna(out.harmonized.iloc[2]))

if __name__=='__main__':unittest.main()

class ScientificEvidenceTests(unittest.TestCase):
    def test_zero_requires_bound_archive_and_observation_evidence(self):
        import hashlib,json
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'2020.parquet'
            pd.DataFrame({'satellite':['Suomi-NPP']*2,'acq_date':pd.to_datetime(['2020-01-01','2020-03-31'])}).to_parquet(p)
            evidence=[dict(month='2020-02',fam='snpp',archive_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                ingestion_complete=True,regional_observation_manifest_complete=True,quality_review_complete=True,
                expected_observations=10,received_observations=10,ingestion_source='archive manifest',observation_source='regional granule manifest')]
            e=Path(tmp)/'coverage_evidence.json';e.write_text(json.dumps(evidence))
            idx=pd.date_range('2020-01-01','2020-03-01',freq='MS')
            c=build_coverage(p,idx,'2020-05-01').query("fam=='snpp'").set_index('month')
            self.assertEqual(c.loc['2020-02-01','status'],'inferred_available')
            self.assertTrue(c.loc['2020-02-01','archive_complete'])
            evidence[0]['received_observations']=9;e.write_text(json.dumps(evidence))
            c=build_coverage(p,idx,'2020-05-01').query("fam=='snpp'").set_index('month')
            self.assertEqual(c.loc['2020-02-01','status'],'missing')
            evidence[0]['received_observations']=10;evidence[0]['archive_sha256']='stale';e.write_text(json.dumps(evidence))
            c=build_coverage(p,idx,'2020-05-01').query("fam=='snpp'").set_index('month')
            self.assertEqual(c.loc['2020-02-01','status'],'missing')

    def test_inventory_covers_both_sensors_and_keeps_ambiguous_times(self):
        from pipeline.outage_inventory import inventory
        rows=inventory()
        self.assertEqual({r['sensor'] for r in rows},{'snpp','terra'})
        self.assertGreater(len(rows),1000)
        self.assertTrue(any(not r['timestamps_valid'] for r in rows))
        self.assertTrue(all(r['local_observation_impact']=='not_established' for r in rows))

    def test_nested_outer_labels_do_not_change_target_predictions_or_bounds(self):
        from pipeline.scientific_validation import nested
        idx=pd.date_range('2014-01-01',periods=60,freq='MS')
        d=pd.DataFrame({'modis':np.arange(60)%13+1.,'snpp':np.arange(60)%17+2.},index=idx)
        a=nested(d).query('held_out_year==2016').reset_index(drop=True)
        d.loc[d.index.year==2016,'snpp']*=100
        b=nested(d).query('held_out_year==2016').reset_index(drop=True)
        np.testing.assert_allclose(a[['prediction','lo','hi']],b[['prediction','lo','hi']])

    def test_sparse_transfer_does_not_invent_uncertainty(self):
        idx=pd.date_range('2011-01-01',periods=36,freq='MS')
        d=pd.DataFrame({'modis':2.,'terra':1.,'snpp':3.},index=idx)
        out,_=harmonize_slice(d)
        transferred=out.source=='modis_transferred'
        self.assertTrue(transferred.any())
        self.assertTrue(out.loc[transferred,['lo','hi']].isna().all().all())

    def test_missing_confidence_slice_cannot_make_comparison_total(self):
        from pipeline.analytics import now_vs_history
        m=pd.DataFrame({'month':pd.to_datetime([f'{y}-01-01' for y in range(2010,2020)]),'cat':'veg','conf':2,'harmonized':1.,'comparison_eligible':True})
        self.assertEqual(now_vs_history(m)['status'],'unavailable_or_provisional')

    def test_noaa20_matching_preserves_confidence_and_rejects_distant_passes(self):
        from pipeline.validate_noaa20 import paired_counts
        day=pd.Timestamp('2020-01-02')
        d=pd.DataFrame([dict(acq_date=day,daynight='D',satellite=s,h3_cell='a',conf=c,cat='veg',pass_time=t)
            for s,c,t in [('Suomi-NPP',3,10000),('NOAA-20',2,13000)]])
        counts,n=paired_counts(d,[pd.Timestamp('2020-01-01')])
        self.assertEqual(n,1)
        self.assertEqual(len(counts),12)
        self.assertEqual(counts.query("cat=='veg' and conf==2").snpp.iloc[0],0)
        self.assertEqual(counts.query("cat=='veg' and conf==3").snpp.iloc[0],1)
        d.loc[d.satellite=='NOAA-20','pass_time']=20000
        _,n=paired_counts(d,[pd.Timestamp('2020-01-01')]);self.assertEqual(n,0)

    def test_district_zero_denominator_candidate_conserves_total_without_target_labels(self):
        from pipeline.scientific_validation import district_predictions
        dates=pd.to_datetime(['2014-01-01','2015-01-01'])
        r=pd.DataFrame(dict(month=dates,cat='veg',conf=2,held_out_year=[2014,2015],prediction=100.,lo=50.,hi=150.))
        members=pd.DataFrame({'sub':[0,1]})
        cells=pd.DataFrame([dict(month=m,cat='veg',conf=2,sub=s,fam='snpp',cell_days=v)
            for m,s,v in [(dates[0],0,99),(dates[0],1,1),(dates[1],0,10),(dates[1],1,30)]])
        a=district_predictions(cells,members,r)
        target=a[(a.month==dates[0])&(a.method=='seasonal_prior_candidate')]
        self.assertEqual(target.prediction.tolist(),[25.,75.])
        self.assertEqual(target.prediction.sum(),100.)
        self.assertTrue(a[(a.month==dates[0])&(a.method=='current_modis_share')].prediction.isna().all())
        cells.loc[cells.month==dates[0],'cell_days']=5000
        b=district_predictions(cells,members,r)
        self.assertEqual(b[(b.month==dates[0])&(b.method=='seasonal_prior_candidate')].prediction.tolist(),[25.,75.])
