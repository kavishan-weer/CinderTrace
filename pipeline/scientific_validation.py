"""Versioned scientific audit. Never promotes a candidate replacement automatically.

Retrospective category masks and detection-based availability remain limitations.
Outputs are distinct from earlier dataset results. Run after repair_release.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from .harmonize import ROOT, CATS, CONF, slice_series, fit_models, loyo, metrics
from .coverage import attach_coverage


def select_fit(train):
    if len(train)<24 or train.index.year.nunique()<3 or train.modis.sum()<=0:
        return None
    val,resid,_=loyo(train)
    model=min(('strat','loglog'),key=lambda m:val[m]['WAPE'])
    return model,fit_models(train)[model],np.quantile(resid[model],[.1,.9])


def predict(fit,x):
    model,fn,q=fit
    p=np.maximum(fn(x.modis.values,x.index.month),0)
    lo=np.minimum(p,np.maximum(0,np.expm1(np.log1p(p)+q[0])))
    hi=np.maximum(p,np.expm1(np.log1p(p)+q[1]))
    return p,lo,hi


def nested(d,kind='regional'):
    rows=[]
    for year in sorted(d.index.year.unique()):
        train,test=d[d.index.year!=year],d[d.index.year==year]
        fit=select_fit(train)
        if fit is None: continue
        p,lo,hi=predict(fit,test)
        rows.extend(dict(month=m,observed=float(y),prediction=float(v),lo=float(l),hi=float(h),
            held_out_year=int(year),model=fit[0],kind=kind,training_months=len(train))
            for m,y,v,l,h in zip(test.index,test.snpp,p,lo,hi))
    return pd.DataFrame(rows)


def summary(frame):
    f=frame.dropna(subset=['observed','prediction'])
    if f.empty:return {'n':0,'status':'no_evaluable_predictions'}
    r={'n':len(f),**metrics(f.observed,f.prediction)}
    intervals=f.dropna(subset=['lo','hi'])
    r['interval_n']=len(intervals)
    r['empirical_P10_P90_coverage']=float(((intervals.observed>=intervals.lo)&(intervals.observed<=intervals.hi)).mean()) if len(intervals) else None
    r['mean_interval_width']=float((intervals.hi-intervals.lo).mean()) if len(intervals) else None
    return r


def district_predictions(cells,members,regional):
    """Outer training S-NPP seasonal prior compared with current MODIS shares.
    Candidate fixed a priori: 90% current support / 10% seasonal prior, or
    100% prior when no MODIS denominator exists. Never fitted to test labels.
    This district benchmark cannot certify arbitrary polygon/cell accuracy.
    """
    out=[]
    subs=sorted(members['sub'].unique())
    for (cat,conf),r in regional.groupby(['cat','conf']):
        s=cells[(cells.cat==cat)&(cells.conf==conf)]
        counts={fam:s[s.fam==fam].groupby(['month','sub']).cell_days.sum().unstack('sub',fill_value=0).reindex(columns=subs,fill_value=0) for fam in ('modis','snpp')}
        for row in r.itertuples():
            prior_rows=r[(r.held_out_year!=row.held_out_year)&(r.month.dt.month==row.month.month)].month
            # Limit priors to eligible outer-training months, exclude target year.
            prior=counts['snpp'].reindex(prior_rows,fill_value=0).sum()
            if prior.sum()==0: continue
            prior=prior/prior.sum()
            m=counts['modis'].reindex([row.month],fill_value=0).iloc[0]
            actual=counts['snpp'].reindex([row.month],fill_value=0).iloc[0]
            share=m/m.sum() if m.sum()>0 else m*np.nan
            candidate=.9*share+.1*prior if m.sum()>0 else prior
            assert np.isclose(candidate.sum(),1)
            for method,weights in [('current_modis_share',share),('seasonal_prior_candidate',candidate)]:
                for sub in subs:
                    out.append(dict(month=row.month,cat=cat,conf=conf,sub=int(sub),method=method,
                        observed=float(actual[sub]),prediction=row.prediction*weights[sub],
                        lo=row.lo*weights[sub],hi=row.hi*weights[sub],zero_denominator=bool(m.sum()==0),
                        interval_method='scaled regional bounds; local coverage unvalidated'))
    return pd.DataFrame(out)


def run():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'data/scientific_validation'/stamp;out.mkdir(parents=True,exist_ok=False)
    all_preds=[];districts=[];coverage_audit=[];inputs=[]
    for region in ('lk','ca','nsw'):
        base=ROOT/'data/harmonized'
        paths=[base/f'{region}_{s}.parquet' for s in ('cells','monthly','coverage')]
        for path in paths:
            inputs.append({'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        cells,monthly,cov=[pd.read_parquet(p) for p in paths]
        idx=pd.DatetimeIndex(sorted(monthly.month.unique()))
        coverage_audit.append(dict(region=region,verified_complete_months=int(cov.archive_complete.sum()),
            missing_months=int((cov.status=='missing').sum()),provisional_months=int((cov.status=='provisional').sum()),
            missing_zero_evidence=int(((cov.detections==0)&~cov.archive_complete).sum())))
        region_preds=[]
        for cat in CATS:
            for conf in CONF:
                d=attach_coverage(slice_series(cells,cat,conf,idx),cov)
                overlap=d[(d.index>='2012-02-01')&(d.index<'2026-01-01')&d.training_ok].dropna(subset=['modis','snpp'])
                if overlap.empty or overlap.snpp.sum()==0:continue
                r=nested(overlap)
                if r.empty:continue
                r['cat']=cat;r['conf']=conf;r['region']=region
                region_preds.append(r);all_preds.append(r)
                early=overlap[overlap.index.year<=2019];late=overlap[overlap.index.year>=2020]
                fit=select_fit(early)
                if fit is not None and len(late):
                    p,lo,hi=predict(fit,late)
                    f=pd.DataFrame(dict(month=late.index,observed=late.snpp.values,prediction=p,lo=lo,hi=hi,
                        cat=cat,conf=conf,region=region,kind='early_window_2012_2019',model=fit[0]))
                    all_preds.append(f)
                # End-to-end Terra -> combined -> VIIRS, outer target excluded
                # from stage 2; stage 1 uses only pre-overlap 2003-2011.
                hist=d[(d.index>='2003-01-01')&(d.index<'2012-01-01')&(d.modis_status=='inferred_available')]
                ratios=hist.groupby(hist.index.month).apply(lambda g:g.modis.sum()/g.terra.sum() if g.terra.sum()>=20 else np.nan)
                for year in sorted(overlap.index.year.unique()):
                    tr,te=overlap[overlap.index.year!=year],overlap[overlap.index.year==year].copy()
                    fit=select_fit(tr)
                    if fit is None:continue
                    te['modis']=[v*ratios.get(m.month,np.nan) for m,v in zip(te.index,te.terra)]
                    te=te.dropna(subset=['modis'])
                    if te.empty:continue
                    p,_,_=predict(fit,te)
                    # Calibrate residuals for the entire chain using training-only
                    # year-held-out stage-2 fits and the fixed pre-overlap stage 1.
                    residuals=[]
                    for inner_year in sorted(tr.index.year.unique()):
                        inner_train=tr[tr.index.year!=inner_year]
                        inner_test=tr[tr.index.year==inner_year].copy()
                        inner_test['modis']=[v*ratios.get(m.month,np.nan) for m,v in zip(inner_test.index,inner_test.terra)]
                        inner_test=inner_test.dropna(subset=['modis'])
                        fn=fit_models(inner_train)[fit[0]]
                        ip=fn(inner_test.modis.values,inner_test.index.month)
                        residuals.extend(np.log1p(inner_test.snpp)-np.log1p(ip))
                    q=np.quantile(residuals,[.1,.9]) if len(residuals)>=24 else [np.nan,np.nan]
                    lo=np.minimum(p,np.maximum(0,np.expm1(np.log1p(p)+q[0])))
                    hi=np.maximum(p,np.expm1(np.log1p(p)+q[1]))
                    all_preds.append(pd.DataFrame(dict(month=te.index,observed=te.snpp.values,prediction=p,lo=lo,hi=hi,
                        cat=cat,conf=conf,region=region,kind='terra_chain',model=fit[0],held_out_year=year)))
        if region_preds:
            members=pd.read_parquet(ROOT/f'data/boundaries/{region}_members.parquet')
            f=district_predictions(cells,members,pd.concat(region_preds,ignore_index=True));f['region']=region;districts.append(f)
        print(region,'evaluated',flush=True)
    predictions=pd.concat(all_preds,ignore_index=True)
    predictions['residual']=predictions.prediction-predictions.observed
    predictions.to_parquet(out/'predictions.parquet',index=False)
    district=pd.concat(districts,ignore_index=True);district.to_parquet(out/'district-predictions.parquet',index=False)
    scores=[]
    for key,f in predictions.groupby(['region','cat','conf','kind']):
        scores.append(dict(zip(['region','cat','conf','kind'],key))|summary(f))
    dscores=[]
    for key,f in district.groupby(['region','cat','conf','method']):
        dscores.append(dict(zip(['region','cat','conf','method'],key))|summary(f)|{'unavailable_predictions':int(f.prediction.isna().sum())})
    # Compare candidates on identical rows; unsupported rows form their own cohort.
    district_cohorts=[]
    for key,f in district.groupby(['region','cat','conf','method','zero_denominator']):
        district_cohorts.append(dict(zip(['region','cat','conf','method','zero_denominator'],key))|summary(f))
    paired_windows=[]
    for key,f in predictions[predictions.kind=='regional'].groupby(['region','cat','conf']):
        early=predictions[(predictions.region==key[0])&(predictions.cat==key[1])&(predictions.conf==key[2])&
                          (predictions.kind=='early_window_2012_2019')]
        paired=f[f.month.isin(early.month)]
        if len(paired):paired_windows.append(dict(zip(['region','cat','conf'],key))|
            {'paired_n':len(paired),'early_window':summary(early),'full_overlap_outer':summary(paired)})
    # Annual sums require 12 eligible paired months and are validated separately.
    annual=[]
    reg=predictions[predictions.kind=='regional'].copy();reg['year']=reg.month.dt.year
    for key,f in reg.groupby(['region','cat','conf','year']):
        if len(f)==12:
            annual.append(dict(zip(['region','cat','conf','year'],key))|{'observed':float(f.observed.sum()),'prediction':float(f.prediction.sum())})
    pd.DataFrame(annual).to_csv(out/'annual-predictions.csv',index=False)
    report={'release_status':'research_only_blocked_on_observation_evidence','coverage_audit':coverage_audit,
        'regional_scores':scores,'district_scores':dscores,'district_cohorts':district_cohorts,'paired_training_windows':paired_windows,
        'production_promotions':[], 'historical_results':'Earlier validation directories are unchanged; their scores describe earlier datasets.',
        'limits':['Availability remains inferred except where independently verified evidence is supplied.',
        'Nested outer years exclude target observations from selection and residual calibration; masks are retrospective.',
        'Terra chain intervals are tested on later overlap; early-era representativeness remains unvalidated, so production early bands remain withheld.',
        'District candidate must be assessed on matched support and zero-denominator cohorts; no automatic promotion.',
        'Scaled regional intervals do not establish local or joint-filter uncertainty. Annual ranks are not validated.']}
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    code=[ROOT/'pipeline'/n for n in ('scientific_validation.py','harmonize.py','coverage.py','outages.py','analytics.py')]+[ROOT/'docs/outage_inventory.json']+list((ROOT/'data/boundaries').glob('*_members.parquet'))
    inputs.extend({'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in code)
    (out/'protocol.json').write_text(json.dumps({'created_at':stamp,'inputs':inputs,
        'intervals':'Inner LOYO log1p residual P10/P90; outer targets excluded. Chain residuals propagate both transfers on later overlap only.',
        'period':'Eligible 2012-02 through 2025-12; all nonempty category/confidence slices independently',
        'candidate':'Fixed 90% MODIS / 10% training-only S-NPP same-calendar-month district prior; prior-only without MODIS support.'},indent=2)+'\n')
    print(out,flush=True)
    return out

if __name__=='__main__':run()
