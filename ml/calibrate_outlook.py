"""Locked probability calibration and previously unscored 2026 holdout.

python -m ml.calibrate_outlook --prepare
python -m ml.calibrate_outlook --evaluate

Preparation freezes the protocol and input hashes before evaluating the holdout.
Calibration never uses 2026 outcomes. No app integration or operational claim.
"""
import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

from .events import ROOT, file_sha
from .outlook import Policy, feature_row, fire_target, fit_origin, month_shift
from .outlook_data import BASE

OUT=BASE/'calibration-v1'
REGIONS=['lk','ca','nsw']
METHOD={'name':'monotone regularized logistic calibration of probability logits',
        'penalty':1.0,'slope_prior':1.0,'intercept_prior':0.0,
        'slope_bounds':[0.,10.],'intercept_bounds':[-10.,10.],
        'min_cases':36,'min_each_class':8,'probability_clip':1e-6}


def fit_calibrator(history,issue,lead,model):
    """Only matured pre-2026 out-of-sample probabilities may train the map."""
    cutoff=min(month_shift(issue,-2),pd.Timestamp('2025-12-01'))
    selected=history[(history.lead==lead)&(history.model==model)&
        (history.target<=cutoff)&(history.issue<pd.Timestamp(issue))&
        (history.target>=pd.Timestamp('2019-01-01'))].copy()
    if selected.duplicated(['issue','lead','model']).any():raise ValueError('Duplicate calibration cases.')
    p=selected.p_above_normal.to_numpy(float);y=selected.above_normal_observed.to_numpy(float)
    if not np.isfinite(p).all() or not np.isfinite(y).all() or not np.isin(y,[0,1]).all() or not ((p>=0)&(p<=1)).all():
        raise ValueError('Invalid calibration probabilities or labels.')
    positives=int(y.sum());negatives=len(y)-positives
    meta={'calibration_n':len(selected),'calibration_positives':positives,
          'calibration_target_max':selected.target.max().isoformat() if len(selected) else None,
          'calibration_issue_max':selected.issue.max().isoformat() if len(selected) else None,
          'calibration_cutoff':cutoff.isoformat(),'slope':1.,'intercept':0.,'calibration_status':'identity_insufficient_history'}
    if len(y)<METHOD['min_cases'] or min(positives,negatives)<METHOD['min_each_class']:return meta
    x=logit(np.clip(p,METHOD['probability_clip'],1-METHOD['probability_clip']))
    def objective(params):
        a,b=params;z=a*x+b
        value=np.sum(np.logaddexp(0,z)-y*z)+.5*METHOD['penalty']*((a-1)**2+b*b)
        error=expit(z)-y
        gradient=np.array([np.dot(error,x)+METHOD['penalty']*(a-1),error.sum()+METHOD['penalty']*b])
        return value,gradient
    fit=minimize(objective,[1.,0.],jac=True,method='L-BFGS-B',bounds=[METHOD['slope_bounds'],METHOD['intercept_bounds']],options={'ftol':1e-12,'gtol':1e-8,'maxiter':1000})
    if not fit.success or not np.isfinite(fit.x).all():
        meta['calibration_status']='identity_optimizer_failure';return meta
    meta.update(slope=float(fit.x[0]),intercept=float(fit.x[1]),calibration_status='fitted')
    return meta


def apply_calibrator(probability,calibrator):
    p=np.asarray(probability,float)
    if not np.isfinite(p).all() or not ((p>=0)&(p<=1)).all():raise ValueError('Invalid probability.')
    clipped=np.clip(p,METHOD['probability_clip'],1-METHOD['probability_clip'])
    return expit(calibrator['slope']*logit(clipped)+calibrator['intercept'])


def reliability(probabilities,labels):
    p=np.asarray(probabilities,float);y=np.asarray(labels,float);rows=[]
    for lower,upper in zip([0,.2,.4,.6,.8],[.2,.4,.6,.8,1.000001]):
        mask=(p>=lower)&(p<upper);n=int(mask.sum())
        if n:
            rate=float(y[mask].mean());z=1.959963984540054;denom=1+z*z/n
            centre=(rate+z*z/(2*n))/denom
            half=z*np.sqrt(rate*(1-rate)/n+z*z/(4*n*n))/denom
            rows.append({'bin':[lower,min(upper,1)],'n':n,'mean_probability':float(p[mask].mean()),'observed_rate':rate,'observed_rate_wilson95':[max(0,centre-half),min(1,centre+half)]})
        else:rows.append({'bin':[lower,min(upper,1)],'n':0,'mean_probability':None,'observed_rate':None,'observed_rate_wilson95':None})
    return rows


def summarize(frame):
    results=[]
    for (region,lead,model),g in frame.groupby(['region','lead','model']):
        p=g.p_above_normal.to_numpy();y=g.above_normal_observed.to_numpy();bins=reliability(p,y)
        eps=METHOD['probability_clip'];clipped=np.clip(p,eps,1-eps)
        results.append({'region':region,'lead':int(lead),'model':model,'n':len(g),'Brier':float(np.mean((p-y)**2)),
            'log_loss':float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped))),
            'mean_probability':float(p.mean()),'observed_rate':float(y.mean()),
            'ECE5':float(sum(b['n']*abs(b['mean_probability']-b['observed_rate']) for b in bins if b['n'])/len(g)),
            'WIS':float(g.wis.mean()),'coverage80':float(g.covered80.mean()),'reliability':bins})
    return results


def prepare():
    path=OUT/'protocol.json'
    if path.exists():
        print('Existing frozen protocol retained; evaluation must match its hashes.');return
    now=pd.Timestamp(datetime.now(ZoneInfo('Asia/Colombo')).date())
    first=pd.Timestamp('2026-01-01');last=min(month_shift(now.replace(day=1),-2),pd.Timestamp('2026-12-01'))
    if last<first:raise ValueError('No mature 2026 holdout months yet.')
    inputs=[ROOT/'ml/calibrate_outlook.py',ROOT/'ml/outlook.py',ROOT/'ml/outlook_data.py',BASE/'inputs/climate-monthly.parquet']
    for region in REGIONS:
        inputs.extend([ROOT/f'data/harmonized/{region}_monthly.parquet',BASE/f'inputs/{region}/weather-monthly.parquet',BASE/f'results/{region}/hindcasts.parquet',BASE/f'results/{region}/report.json'])
    spec={'method':'probability-calibration-v1','frozen_at':pd.Timestamp.now(tz='UTC').isoformat(),'as_of_date':now.isoformat(),
        'calibrator':METHOD,'base_policy':asdict(Policy()),'base_model_changed':False,
        'calibration_targets':'2019-01 through min(2025-12, issue-2 months); issue strictly before test issue',
        'holdout_target_start':first.isoformat(),'holdout_target_end':last.isoformat(),
        'freshness':'2026 outcomes excluded from prior 2019-2025 scoring and all calibration fitting; same revised archive snapshot, not prospective observations.',
        'evaluation':'Target-month holdout; for each lead include late-2025 issue dates that predict early-2026 targets. Base models may learn earlier holdout labels only after the fixed issue-2 maturity cutoff.',
        'comparators':['seasonal','seasonal_calibrated','history_ml','weather_climate_ml','weather_climate_ml_calibrated'],
        'numerical_gate':{'min_cases_per_lead':60,'min_calendar_years':3,'positive_year_block_lower_bounds':['Brier vs seasonal','Brier vs raw weather','WIS vs seasonal'],'coverage80_range':[.65,.95]},
        'inputs':[{'path':str(p.relative_to(ROOT)),'sha256':file_sha(p)} for p in inputs]}
    OUT.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(spec,indent=2,allow_nan=False))
    print(f'Protocol frozen before evaluation: {path.relative_to(ROOT)}; {first:%Y-%m}–{last:%Y-%m}')


def load_protocol():
    protocol=json.loads((OUT/'protocol.json').read_text())
    if protocol['calibrator']!=METHOD:raise ValueError('Calibrator protocol changed.')
    for entry in protocol['inputs']:
        if file_sha(ROOT/entry['path'])!=entry['sha256']:raise ValueError(f"Frozen input changed: {entry['path']}; retain this experiment and create a new version.")
    return protocol


def evaluate():
    protocol=load_protocol();rows=[];skipped=[];latest=[]
    first=pd.Timestamp(protocol['holdout_target_start']);last=pd.Timestamp(protocol['holdout_target_end'])
    # Input identities are verified before any new target scoring or fitting.
    for region in REGIONS:
        history=pd.read_parquet(BASE/f'results/{region}/hindcasts.parquet')
        if (history.target>=first).any():raise ValueError('Holdout already present in calibration history.')
        y=fire_target(pd.read_parquet(ROOT/f'data/harmonized/{region}_monthly.parquet'))
        weather=pd.read_parquet(BASE/f'inputs/{region}/weather-monthly.parquet').set_index('month')
        weather.loc[~weather.complete,['temperature_c','rain_mm','humidity_pct','wind_mps']]=np.nan
        climate=pd.read_parquet(BASE/'inputs/climate-monthly.parquet').set_index('month')
        latest_issue=pd.Timestamp(protocol['as_of_date']).replace(day=1)
        for lead in [1,2,3]:
            examples=pd.DataFrame([feature_row(y,weather,climate,issue,lead) for issue in pd.date_range('2013-01-01',latest_issue,freq='MS')])
            for target in pd.date_range(first,last,freq='MS'):
                issue=month_shift(target,1-lead)
                if pd.isna(y.get(target,np.nan)):
                    skipped.append({'region':region,'issue':issue.isoformat(),'target':target.isoformat(),'lead':lead,'reason':'unavailable_or_provisional_target'});continue
                try:original=fit_origin(examples,y,issue)
                except ValueError as error:
                    skipped.append({'region':region,'issue':issue.isoformat(),'target':target.isoformat(),'lead':lead,'reason':str(error)});continue
                for record in original:
                    record.update(region=region,calibration_status='not_applied');rows.append(record)
                    if record['model'] not in ['seasonal','weather_climate_ml']:continue
                    cal=fit_calibrator(history,issue,lead,record['model'])
                    probability=float(apply_calibrator(record['p_above_normal'],cal))
                    rows.append({**record,**cal,'model':record['model']+'_calibrated','raw_probability':record['p_above_normal'],
                                 'p_above_normal':probability,'brier':(probability-record['above_normal_observed'])**2})
            # Research snapshot for future prospective verification. Do not score it here.
            try:
                original=fit_origin(examples,y,latest_issue)
                raw=next(row for row in original if row['model']=='weather_climate_ml')
                cal=fit_calibrator(history,latest_issue,lead,'weather_climate_ml')
                latest.append({**raw,**cal,'region':region,'model':'weather_climate_ml_calibrated','raw_probability':raw['p_above_normal'],
                               'p_above_normal':float(apply_calibrator(raw['p_above_normal'],cal)),'app_ready':False})
            except ValueError as error:latest.append({'region':region,'lead':lead,'issue':latest_issue,'status':'unavailable','reason':str(error)})
            print(f'{region} lead {lead}: locked calibration + fresh holdout completed',flush=True)
    frame=pd.DataFrame(rows)
    if frame.empty:raise ValueError('No fresh holdout targets were eligible.')
    metrics=summarize(frame);comparisons=[]
    for (region,lead),g in frame.groupby(['region','lead']):
        calibrated=g[g.model=='weather_climate_ml_calibrated'].set_index('target')
        for comparator in ['seasonal','weather_climate_ml','seasonal_calibrated','history_ml']:
            base=g[g.model==comparator].set_index('target');pair=calibrated[['brier']].merge(base[['brier']],left_index=True,right_index=True,suffixes=('_calibrated','_baseline'),validate='one_to_one')
            baseline=pair.brier_baseline.mean();skill=1-pair.brier_calibrated.mean()/baseline if baseline>0 else None
            comparisons.append({'region':region,'lead':int(lead),'comparator':comparator,'n':len(pair),'Brier_skill':float(skill) if skill is not None else None,
                'mean_Brier_difference':float((pair.brier_calibrated-pair.brier_baseline).mean()),
                'calendar_years':int(pair.index.year.nunique()),'year_block_95':None,
                'uncertainty_note':'One partial holdout year; no independent year-block confidence interval or release claim.'})
    report={'method':protocol['method'],'protocol_sha256':file_sha(OUT/'protocol.json'),'holdout_start':first.isoformat(),'holdout_end':last.isoformat(),
        'metrics':metrics,'comparisons':comparisons,'skipped':skipped,'app_ready':False,'operationally_validated':False,
        'numerical_gate':{f'{r}-{h}':False for r in REGIONS for h in [1,2,3]},
        'gate_reason':'At most one partial holdout calendar year and fewer than 60 cases per region/lead; required multi-year uncertainty and interval-skill evidence absent.',
        'limits':['2026 holdout is newly scored in this version but already in the current revised archive; it is not a prospective forecast replay.',
                  'Per-issue sigmoid fits use only matured, earlier 2019-2025 out-of-sample predictions, never 2026 calibration labels.',
                  'The base model updates prequentially with eligible earlier observations; no parameters or calibration choices were tuned on holdout scores.',
                  'Binary above-normal calibration leaves all activity quantiles and interval scores unchanged; it does not calibrate the fan chart.',
                  'Individual-month/region results cannot establish polygon-level skill; archive and retrospective category limitations remain.']}
    frame.to_parquet(OUT/'fresh-holdout.parquet',index=False);frame.to_csv(OUT/'fresh-holdout.csv',index=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    def clean(value):
        if isinstance(value,pd.Timestamp):return value.isoformat()
        if isinstance(value,np.generic):return value.item()
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    log=OUT/f"research-issued-{latest_issue:%Y-%m-%d}.json"
    body=json.dumps(clean({'recorded_at':protocol['frozen_at'],'protocol_sha256':report['protocol_sha256'],
        'issue':latest_issue,'status':'research_snapshot_recorded_after_issue_date_not_operational','app_ready':False,'forecasts':latest}),indent=2,allow_nan=False)
    if log.exists() and log.read_text()!=body:raise ValueError('Do not overwrite a previously recorded research snapshot.')
    log.write_text(body)
    print(f'Saved {len(frame)} fresh test forecast rows; app_ready=false.')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--evaluate',action='store_true')
    args=parser.parse_args()
    prepare() if args.prepare else evaluate()
