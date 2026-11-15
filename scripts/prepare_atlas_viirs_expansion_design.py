"""Freeze a calendar-only sample. No science/metadata downloads or model fitting."""
from pathlib import Path
import json,hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parent.parent
base=ROOT/'data/atlas/canonical_lk_2000_2024_v1'
d=pd.read_parquet(base/'daily_status.parquet');f=d[d.satellite.isin(['Suomi-NPP','NOAA-20'])].copy()
f['eligible']=f.recorded_detections.notna()&~f.upstream_lists_missing_standard_data&~f.documented_global_gap_on_date
eligible=f.pivot(index='date',columns='satellite',values='eligible').fillna(False).all(axis=1)
pilot=set(json.loads((ROOT/'data/atlas/observation_evidence_pilot_v1/inventory.json').read_text())['policy']['days'])
seed='cindertrace_lk_seasonal_validation_v1_20261115';rows=[];unavailable=[]
for year in range(2018,2025):
    for quarter in range(1,5):
        start=pd.Timestamp(year=year,month=quarter*3-2,day=1);end=start+pd.DateOffset(months=3);mid=start+pd.Timedelta(days=(end-start).days//2);previous=None
        for half,(a,b) in enumerate([(start,mid),(mid,end)],1):
            dates=[x.strftime('%Y-%m-%d') for x in pd.date_range(a,b-pd.Timedelta(days=1))]
            candidates=[x for x in dates if eligible.get(x,False) and x not in pilot and (previous is None or (pd.Timestamp(x)-pd.Timestamp(previous)).days>=14)]
            slot={'year':year,'quarter':quarter,'half_quarter':half}
            if not candidates:
                unavailable.append({**slot,'status':'no_eligible_calendar_candidate_not_zero_activity'});continue
            chosen=min(candidates,key=lambda x:hashlib.sha256((seed+'|'+x).encode()).hexdigest());previous=chosen
            rows.append({**slot,'date':chosen,'partition':'fit' if year<=2020 else 'calibration' if year<=2022 else 'evaluation','selection_basis':'calendar and availability only; no detection count ranking'})
plan={'study_id':'lk_viirs_expansion_design_v1','status':'frozen_design_not_a_validated_model','seed':seed,
 'pilot_results_zip_sha256':'dea71170261cd155b5ff7515b12b3078bba08b280cd2204c48dd23ca5ac46de3',
 'observed_manifest_sha256':hashlib.sha256((base/'manifest.json').read_bytes()).hexdigest(),
 'dates':rows,'unavailable_calendar_slots':unavailable,'date_counts_by_partition':pd.DataFrame(rows).partition.value_counts().to_dict(),
 'eligibility':'Both archives available; conservatively exclude upstream missing standard dates and documented global gap dates. Not verified local observing coverage.',
 'sampling':'One hashed date per half-quarter, at least fourteen days apart within a quarter; exclude pilot dates; no detection count ranking. Unsupported slots remain absent. NOAA-20 standard archive starts April 2018 in this checkpoint.',
 'prior_information':'Aggregate regional metrics and pilot results were inspected. Expanded pass-level evaluation is not a blind independent replication or physical fire-truth validation.',
 'paired_observation_diagnostic':{'target':'sensor-specific observed activity on explicit matched support','selection':'evaluate geometry/support eligibility for all time candidates before one-to-one assignment; never select using fire counts','caution':'S-NPP shared-support masks cannot be used as prediction inputs during a real S-NPP outage'},
 'simulated_outage_test':{'target':'S-NPP observed regional activity on eligible archived dates, not total true fires','features':'NOAA-20 observations and its own quality/geometry plus calendar only','prohibited_features':'S-NPP counts, masks, clear-support selection, viewing information or reference-derived pairing','split':'fit 2018–2020, calibrate 2021–2022, evaluate 2023–2024; whole dates/passes remain together','caution':'Reference availability qualifies evaluation labels only, not deployment predictors. Outage covariate shift remains unverified.'},
 'uncertainty':'Separate calibration date blocks. Minimum twelve supported calibration dates before exploratory 80/90 percent intervals; evaluate date-level coverage and width. Pixels and sensitivity variants are not independent samples. Withhold unsupported intervals; no annual/monthly uncertainty claims from sampled passes.',
 'next_execution':'Public metadata inventory and volume estimate first; reuse existing cache and prepare resumable processing. This step downloads no science files.',
 'replacement_enabled':False,'early_history_bands_enabled':False,'coverage_verified':False,'frontend_changed':False}
(ROOT/'docs/atlas_viirs_expansion_design_v1.json').write_text(json.dumps(plan,indent=2,allow_nan=False)+'\n')
pd.DataFrame(rows).to_csv(ROOT/'docs/atlas_viirs_expansion_dates_v1.csv',index=False)
print('Frozen:',len(rows),'dates;',plan['date_counts_by_partition'],'unavailable slots:',unavailable)
