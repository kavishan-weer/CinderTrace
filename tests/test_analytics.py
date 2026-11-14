import unittest
import tempfile
from pathlib import Path
import pandas as pd
import numpy as np
from pipeline.coverage import build_coverage, attach_coverage
from pipeline.harmonize import harmonize_slice, loyo
from pipeline.analytics import selected_monthly, now_vs_history, select_members


class AnalyticsTests(unittest.TestCase):
    def test_archive_missing_partial_and_future(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data.parquet'
            pd.DataFrame({'satellite':['Suomi-NPP']*4,'acq_date':pd.to_datetime(['2020-01-02','2020-03-02','2020-04-03','2021-01-01'])}).to_parquet(path)
            idx=pd.date_range('2020-01-01','2020-05-01',freq='MS')
            c=build_coverage(path,idx,'2020-05-15')
            status=c[c.fam=='snpp'].set_index('month').status.tolist()
            self.assertEqual(status,['provisional','missing','inferred_available','provisional','missing'])
            self.assertLessEqual(c.last_detection.max(),pd.Timestamp('2020-05-15'))

    def test_zero_missing_and_fallback_are_distinct(self):
        idx=pd.date_range('2013-01-01',periods=3,freq='MS')
        d=pd.DataFrame({'modis':[5,3,4],'terra':[2,1,2],'snpp':[0,0,2]},index=idx)
        rows=[]
        for fam,statuses in [('modis',['inferred_available']*3),('snpp',['inferred_available','missing','provisional'])]:
            rows.extend(dict(month=m,fam=fam,status=s) for m,s in zip(idx,statuses))
        d=attach_coverage(d,pd.DataFrame(rows))
        out,_=harmonize_slice(d)
        self.assertEqual(out.source.tolist(),['viirs_observed','modis_transferred','viirs_observed'])
        self.assertEqual(out.harmonized.iloc[0],0)
        self.assertTrue(pd.isna(out.viirs_snpp_raw.iloc[1]))
        self.assertFalse(out.comparison_eligible.iloc[2])
        d.loc[idx[1],'modis']=np.nan
        out,_=harmonize_slice(d)
        self.assertEqual(out.source.iloc[1],'missing')
        self.assertTrue(pd.isna(out.harmonized.iloc[1]))

    def test_validation_keeps_true_zero_months_and_excludes_provisional(self):
        idx=pd.date_range('2014-01-01',periods=36,freq='MS')
        d=pd.DataFrame({'modis':np.arange(36,dtype=float)%5,'snpp':np.arange(36,dtype=float)%7,'training_ok':True},index=idx)
        d.loc[idx[-1],'training_ok']=False
        _,_,overlap=loyo(d)
        self.assertEqual(len(overlap),35)
        self.assertTrue((overlap.snpp==0).any())
        self.assertNotIn(idx[-1],overlap.index)

    def test_area_partition_and_no_input_allocation(self):
        members=pd.DataFrame({'h3_cell':['a','b'],'sub':[0,1],'area_km2':[20,30],'lon':[0,2],'lat':[0,2]})
        m=pd.Timestamp('2010-01-01')
        cells=pd.DataFrame([dict(h3_cell=c,month=m,cat='veg',conf=2,fam='modis',cell_days=n) for c,n in [('a',1),('b',3)]])
        monthly=pd.DataFrame([dict(month=m,cat='veg',conf=2,harmonized=20.,lo=10.,hi=30.,source='modis_transferred',modis_status='inferred_available',snpp_status='missing',comparison_eligible=True)])
        a=selected_monthly(cells,monthly,members,sub=0)
        b=selected_monthly(cells,monthly,members,sub=1)
        self.assertEqual(a.harmonized.iloc[0],5)
        self.assertEqual(b.harmonized.iloc[0],15)
        self.assertEqual(a.harmonized.iloc[0]+b.harmonized.iloc[0],20)
        missing=selected_monthly(cells.iloc[:0],monthly,members,sub=0)
        self.assertTrue(pd.isna(missing.harmonized.iloc[0]))
        self.assertFalse(missing.comparison_eligible.iloc[0])
        polygon={'type':'Polygon','coordinates':[[[-1,-1],[1,-1],[1,1],[-1,1],[-1,-1]]]}
        self.assertEqual(select_members(members,polygon=polygon).h3_cell.tolist(),['a'])

    def test_now_comparison_excludes_current_and_provisional(self):
        monthly=pd.DataFrame({'month':pd.to_datetime([f'{year}-01-01' for year in range(2018,2025)]),'cat':'veg','conf':2,'harmonized':[1,2,3,4,5,6,999],'comparison_eligible':[True]*6+[False]})
        self.assertEqual(now_vs_history(monthly)['status'],'unavailable_or_provisional')
        r=now_vs_history(monthly,'2023-01-01',confs=(2,))
        self.assertEqual(r['historical_median'],3)
        self.assertEqual(r['historical_years'],5)

if __name__=='__main__':
    unittest.main()
