"""Lagged 1/2/3-calendar-month activity hindcasts against seasonal history.

python -m ml.outlook [lk ca nsw]
Research only: revised archives, fixed retrospective labels, no app integration.
"""
import argparse
import json
import platform
import warnings
from dataclasses import asdict,dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import lightgbm as lgb
import numpy as np
import pandas as pd

from .events import ROOT,file_sha
from .outlook_data import BASE

QUANTILES=np.array([.1,.25,.5,.75,.9])
HISTORY_FEATURES=['target_sin','target_cos','season_median_log','season_q10_log','season_q90_log',
 'fire_log_lag2','fire_log_lag3','fire_log_lag4','fire_log_lag13','fire_log_lag14','target_last_year_log','recent_fire_3m_log']
WEATHER_FEATURES=[f'{name}_lag{lag}' for name in ['temperature_c','rain_mm','humidity_pct','wind_mps'] for lag in [3,4,5]]+['oni_center_lag5','oni_center_lag6','dmi_lag4','dmi_lag5']


@dataclass(frozen=True)
class Policy:
    fire_lag_months:int=2
    weather_lag_months:int=3
    oni_center_lag_months:int=5
    dmi_lag_months:int=4
    min_training_rows:int=48
    min_seasonal_years:int=5
    evaluation_start:str='2019-01'
    evaluation_end:str='2025-12'

    def __post_init__(self):
        # These fixed lags also define the feature names and experiment protocol.
        if (self.fire_lag_months,self.weather_lag_months,self.oni_center_lag_months,self.dmi_lag_months)!=(2,3,5,4):
            raise ValueError('Changing lags requires a new feature schema and validation protocol.')


def month_shift(month,delta):return pd.Timestamp(month)+pd.DateOffset(months=delta)


def fire_target(frame):
    """Only directly observed, eligible reference activity; no transfer targets."""
    selected=frame[(frame.cat=='veg')&frame.conf.isin([2,3])].copy()
    rows=[]
    for month,g in selected.groupby('month'):
        valid=set(g.conf)=={2,3} and len(g)==2 and g.comparison_eligible.all() and (g.period_status!='provisional').all() and (g.source=='viirs_observed').all() and not g.low_data.any() and g.viirs_snpp_raw.notna().all()
        value=float(g.viirs_snpp_raw.sum()) if valid else np.nan
        rows.append((pd.Timestamp(month),value if np.isfinite(value) and value>=0 and pd.Timestamp(month)>=pd.Timestamp('2013-01-01') else np.nan))
    return pd.Series(dict(rows),name='activity').sort_index()


def seasonal_pool(y,issue,target,policy=Policy()):
    cutoff=month_shift(issue,-policy.fire_lag_months)
    return y[(y.index<=cutoff)&(y.index.month==target.month)].dropna()


def feature_row(y,weather,climate,issue,lead,policy=Policy()):
    issue=pd.Timestamp(issue);target=month_shift(issue,lead-1)
    pool=seasonal_pool(y,issue,target,policy)
    features={'target_sin':np.sin(target.month/12*2*np.pi),'target_cos':np.cos(target.month/12*2*np.pi)}
    q=np.quantile(pool,[.1,.5,.9]) if len(pool) else np.array([np.nan]*3)
    features.update(season_median_log=np.log1p(q[1]),season_q10_log=np.log1p(q[0]),season_q90_log=np.log1p(q[2]))
    for lag in [2,3,4,13,14]:features[f'fire_log_lag{lag}']=np.log1p(y.get(month_shift(issue,-lag),np.nan))
    prior_year=month_shift(target,-12)
    if prior_year>month_shift(issue,-policy.fire_lag_months):raise AssertionError('Future fire feature.')
    features['target_last_year_log']=np.log1p(y.get(prior_year,np.nan))
    recent=[y.get(month_shift(issue,-lag),np.nan) for lag in [2,3,4]]
    features['recent_fire_3m_log']=np.log1p(sum(recent)) if np.isfinite(recent).all() else np.nan
    for lag in [3,4,5]:
        date=month_shift(issue,-lag)
        for name in ['temperature_c','rain_mm','humidity_pct','wind_mps']:
            features[f'{name}_lag{lag}']=weather[name].get(date,np.nan)
    for lag in [5,6]:features[f'oni_center_lag{lag}']=climate.oni.get(month_shift(issue,-lag),np.nan)
    for lag in [4,5]:features[f'dmi_lag{lag}']=climate.dmi.get(month_shift(issue,-lag),np.nan)
    ready=np.isfinite([features[f'{col}_lag3'] for col in ['temperature_c','rain_mm','humidity_pct','wind_mps']]+[features['oni_center_lag5'],features['dmi_lag4']]).all()
    return {**features,'issue':issue,'target':target,'lead':lead,'y':y.get(target,np.nan),
      'full_inputs_ready':bool(ready),'seasonal_n':len(pool),
      'fire_feature_cutoff':month_shift(issue,-policy.fire_lag_months),
      'weather_feature_cutoff':month_shift(issue,-policy.weather_lag_months),
      'oni_center_cutoff':month_shift(issue,-policy.oni_center_lag_months),
      'dmi_cutoff':month_shift(issue,-policy.dmi_lag_months)}


def model_quantiles(train,test,columns):
    predictions=[]
    X=train[columns].to_numpy(float);z=np.log1p(train.y.to_numpy(float));x=test[columns].to_numpy(float)
    for quantile in QUANTILES:
        model=lgb.LGBMRegressor(objective='quantile',alpha=float(quantile),n_estimators=64,learning_rate=.04,
            num_leaves=7,max_depth=3,min_child_samples=12,reg_lambda=5.,random_state=42,n_jobs=1,verbosity=-1)
        model.fit(X,z)
        # Native missing-value handling; no full-record scaling or imputation.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            predictions.append(np.maximum(0,np.expm1(model.predict(x))))
    return np.sort(np.asarray(predictions).T,axis=1)


def above_probability(quantiles,threshold):
    """Piecewise-linear quantile CDF, capped tails 0.1-0.9; not calibrated."""
    return float(1-np.interp(threshold,np.asarray(quantiles,float),QUANTILES,left=.1,right=.9))


def proper_scores(actual,quantiles):
    q=np.asarray(quantiles,float);low,median,high=q[0],q[2],q[4]
    interval=(high-low)+10*max(low-actual,0)+10*max(actual-high,0)
    wis=(.5*abs(actual-median)+.1*interval)/1.5
    errors=actual-q
    pinball=np.maximum(QUANTILES*errors,(QUANTILES-1)*errors).mean()
    return {'mae':abs(actual-median),'wis':wis,'pinball':pinball,'covered80':low<=actual<=high,'interval_width':high-low}


def fit_origin(examples,y,issue,policy=Policy()):
    issue=pd.Timestamp(issue);cutoff=month_shift(issue,-policy.fire_lag_months)
    train=examples[(examples.target<=cutoff)&examples.y.notna()&examples.full_inputs_ready]
    test=examples[examples.issue==issue]
    if len(train)<policy.min_training_rows:raise ValueError('insufficient_training_history')
    if len(test)!=1 or not test.iloc[0].full_inputs_ready:raise ValueError('missing_lagged_weather_or_climate')
    row=test.iloc[0];pool=seasonal_pool(y,issue,row.target,policy)
    if len(pool)<policy.min_seasonal_years:raise ValueError('insufficient_same_month_baseline')
    if train.issue.max()>=issue or train.target.max()>cutoff:raise AssertionError('Future training label.')
    results={'seasonal':np.quantile(pool,QUANTILES)}
    results['history_ml']=model_quantiles(train,test,HISTORY_FEATURES)[0]
    results['weather_climate_ml']=model_quantiles(train,test,HISTORY_FEATURES+WEATHER_FEATURES)[0]
    threshold=float(pool.median())
    records=[]
    for name,q in results.items():
        probability=float(((pool>threshold).sum()+1)/(len(pool)+2)) if name=='seasonal' else above_probability(q,threshold)
        record=dict(model=name,issue=issue,target=row.target,lead=int(row.lead),train_rows=len(train),
            train_target_max=train.target.max(),training_cutoff=cutoff,baseline_history_max=pool.index.max(),baseline_n=len(pool),
            normal_threshold=threshold,p_above_normal=probability,
            q10=float(q[0]),q25=float(q[1]),q50=float(q[2]),q75=float(q[3]),q90=float(q[4]))
        for col in ['fire_feature_cutoff','weather_feature_cutoff','oni_center_cutoff','dmi_cutoff']:record[col]=row[col]
        if pd.notna(row.y):
            actual=float(row.y);event=int(actual>threshold)
            record.update(actual=actual,above_normal_observed=event,brier=(probability-event)**2,**proper_scores(actual,q))
        records.append(record)
    return records


def summarize(predictions):
    results=[]
    for (lead,model),g in predictions.groupby(['lead','model']):
        bias=(g.q50.sum()-g.actual.sum())/max(g.actual.sum(),1)
        results.append(dict(lead=int(lead),model=model,n=len(g),MAE=float(g.mae.mean()),WAPE=float(g.mae.sum()/max(g.actual.sum(),1)),
            bias=float(bias),WIS=float(g.wis.mean()),pinball=float(g.pinball.mean()),Brier=float(g.brier.mean()),coverage80=float(g.covered80.mean()),mean_width=float(g.interval_width.mean())))
    return results


def paired_skill(predictions,lead,metric,model='weather_climate_ml',iterations=1000):
    subset=predictions[predictions.lead==lead]
    pair=subset[subset.model==model].set_index('target')[[metric]].merge(subset[subset.model=='seasonal'].set_index('target')[[metric]],left_index=True,right_index=True,suffixes=('_model','_baseline'),how='inner').dropna()
    if pair.empty:return None
    baseline=pair[f'{metric}_baseline'].mean();skill=1-pair[f'{metric}_model'].mean()/baseline if baseline>0 else None
    # Resample whole years, preserving within-year seasonal dependence and pairing.
    totals=pair.groupby(pair.index.year).sum().to_numpy();years=sorted(pair.index.year.unique())
    rng=np.random.default_rng(42);blocks=totals[rng.integers(0,len(years),size=(iterations,len(years)))].sum(axis=1)
    valid=blocks[:,1]>0;samples=(1-blocks[valid,0]/blocks[valid,1]).tolist()
    return {'skill':float(skill) if skill is not None else None,'year_block_bootstrap_95':np.quantile(samples,[.025,.975]).tolist() if samples else None,'years':len(years),'n':len(pair)}


def run(region,policy=Policy()):
    monthly_path=ROOT/f'data/harmonized/{region}_monthly.parquet'
    weather_path=BASE/f'inputs/{region}/weather-monthly.parquet';climate_path=BASE/'inputs/climate-monthly.parquet'
    y=fire_target(pd.read_parquet(monthly_path));weather=pd.read_parquet(weather_path).set_index('month');climate=pd.read_parquet(climate_path).set_index('month')
    # Missing regional weather is not reweighted or filled using future months.
    weather.loc[~weather.complete,['temperature_c','rain_mm','humidity_pct','wind_mps']]=np.nan
    latest_issue=pd.Timestamp(datetime.now(ZoneInfo('Asia/Colombo')).date()).replace(day=1)
    origins=pd.date_range('2013-01-01',latest_issue,freq='MS')
    rows=[];skipped=[];latest=[]
    for lead in [1,2,3]:
        examples=pd.DataFrame([feature_row(y,weather,climate,issue,lead,policy) for issue in origins])
        for issue in pd.date_range(policy.evaluation_start,policy.evaluation_end,freq='MS'):
            target=month_shift(issue,lead-1)
            if target>pd.Timestamp(policy.evaluation_end):continue
            if pd.isna(y.get(target,np.nan)):
                skipped.append(dict(issue=issue.isoformat(),lead=lead,reason='unavailable_or_provisional_reference_target'));continue
            try:rows.extend(fit_origin(examples,y,issue,policy))
            except ValueError as error:skipped.append(dict(issue=issue.isoformat(),lead=lead,reason=str(error)))
        try:latest.extend(fit_origin(examples,y,latest_issue,policy))
        except ValueError as error:latest.append({'lead':lead,'issue':latest_issue.isoformat(),'status':'unavailable','reason':str(error)})
        print(f'{region} lead {lead}: hindcasts completed',flush=True)
    predictions=pd.DataFrame(rows)
    if predictions.empty:raise ValueError('No eligible hindcasts; inspect source coverage and lag policy.')
    metrics=summarize(predictions)
    skills={str(lead):{'wis':paired_skill(predictions,lead,'wis'),'brier':paired_skill(predictions,lead,'brier')} for lead in [1,2,3]}
    calibration=[]
    for (lead,model),g in predictions.groupby(['lead','model']):
        for lower,upper in zip([0,.2,.4,.6,.8],[.2,.4,.6,.8,1.01]):
            b=g[(g.p_above_normal>=lower)&(g.p_above_normal<upper)]
            calibration.append(dict(lead=int(lead),model=model,probability_bin=[lower,min(upper,1)],n=len(b),mean_probability=float(b.p_above_normal.mean()) if len(b) else None,observed_rate=float(b.above_normal_observed.mean()) if len(b) else None))
    # Outcomes alone are insufficient for operational readiness without data vintages.
    numerical_gate={}
    for lead in [1,2,3]:
        score=next((m for m in metrics if m['lead']==lead and m['model']=='weather_climate_ml'),None)
        w,b=skills[str(lead)]['wis'],skills[str(lead)]['brier']
        numerical_gate[str(lead)]=bool(score and w and b and w['year_block_bootstrap_95'] and b['year_block_bootstrap_95'] and w['n']>=60 and w['year_block_bootstrap_95'][0]>0 and b['year_block_bootstrap_95'][0]>0 and .65<=score['coverage80']<=.95)
    inputs=[monthly_path,weather_path,climate_path,ROOT/'ml/outlook.py',ROOT/'ml/outlook_data.py',*sorted((BASE/f'inputs/{region}').glob('*.json')),*sorted((BASE/'inputs').glob('*.txt')),*sorted((BASE/'inputs').glob('*.provenance.json'))]
    identity=[{'path':str(p.relative_to(ROOT)),'sha256':file_sha(p)} for p in inputs]
    report={'method':'outlook-research-v1','region':region,'policy':asdict(policy),'quantiles':QUANTILES.tolist(),
        'runtime':{'python':platform.python_version(),'lightgbm':lgb.__version__,'pandas':pd.__version__,'numpy':np.__version__},
        'model_parameters':{'algorithm':'LightGBM quantile regression','n_estimators':64,'learning_rate':.04,'num_leaves':7,'max_depth':3,'min_child_samples':12,'reg_lambda':5,'seed':42},
        'inputs':identity,'metrics':metrics,'paired_skills':skills,'calibration':calibration,'skipped_origins':skipped,
        'rolling_2024_2025_diagnostic':summarize(predictions[predictions.target.dt.year>=2024]),
        'numerical_skill_gate':numerical_gate,'app_ready':False,'operationally_validated':False,
        'limits':['Retrospective hindcasts with revised current archives, not historical publication vintages.',
         'Target is observed eligible S-NPP vegetation nominal/high cell-days, not event counts or burned area. Pre-2013 transferred targets excluded.',
         'Existing retrospective H3 source labels and archive-availability proxies remain; historical fire observations are not a real-time vintage replay.',
         'Five static area-weighted weather sample strata approximate regional weather; local/drawn-area forecast skill is untested.',
         'Weather through issue minus 3 months; fire through minus 2; ONI centre minus 5; DMI minus 4. No target-period weather or centred-index future months enter features.',
         'Probability above available historical same-month median uses interpolated quantile CDF with capped 0.1-0.9 tails; not a separately calibrated probability.',
         'Quantiles sorted to repair crossing; P10-P90 intervals are predictive summaries, not guaranteed coverage.',
         'Evaluation 2019-2025 is expanding-window/prequential, with fixed choices and no random split or test-set tuning. Seven year blocks provide limited uncertainty evidence.']}
    directory=BASE/'results'/region;directory.mkdir(parents=True,exist_ok=True)
    predictions.to_parquet(directory/'hindcasts.parquet',index=False);predictions.to_csv(directory/'hindcasts.csv',index=False)
    (directory/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    def normalize(value):
        if isinstance(value,pd.Timestamp):return value.isoformat()
        if isinstance(value,np.generic):return value.item()
        if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
        if isinstance(value,list):return [normalize(v) for v in value]
        return value
    (directory/'latest-research.json').write_text(json.dumps(normalize({'app_ready':False,'issue':latest_issue,'forecasts':latest}),indent=2,allow_nan=False))
    print(f'{region}: saved {len(predictions)} forecast rows; numerical gates {numerical_gate}',flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('regions',nargs='*',default=['lk','ca','nsw'])
    for region in parser.parse_args().regions:
        if region not in ['lk','ca','nsw']:raise ValueError('Unsupported region')
        run(region)
