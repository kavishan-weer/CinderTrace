"""Summarize frozen hindcasts, ablations, input coverage and the app decision.

python -m ml.report_outlook
Does not fit, select or tune a model.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .events import ROOT
from .outlook_data import BASE


def percent(value):
    return f'{100*value:+.1f}%'


def main():
    reports={r:json.loads((BASE/f'results/{r}/report.json').read_text()) for r in ['lk','ca','nsw']}
    names={'lk':'Sri Lanka','ca':'California','nsw':'NSW'}
    lines=['# Fire outlook: retrospective validation', '',
        f"Review date: {datetime.now(ZoneInfo('Asia/Colombo')).date().isoformat()} (Asia/Colombo).", '',
        '**The research pipeline is implemented and evaluated. Its forecasts remain outside the app. Numerical results below determine whether it outperforms seasonal history; current revised archives do not establish operational forecast validity.**', '',
        '## What is predicted', '',
        'One separate monthly distribution for each of the first, second and third calendar months beginning on the issue date. An issue dated 1 August predicts August, September and October, respectively; these are not cumulative 30/60/90-day totals. It cannot establish an August forecast of December or of the whole NSW summer.', '',
        'The target is **directly observed Suomi-NPP vegetation fire-active H3 resolution-6 cell-days**, nominal plus high confidence, from 2013 onward. It is not individual fire events, burned area, fire severity or danger to a particular property. Both confidence rows must be eligible and non-provisional. Missing and low-data targets are unavailable, never zero-filled.', '',
        'This deliberately narrows the original harmonized-series plan: pre-2013 transfers were calibrated on later sensor overlap, so using them as historical forecast labels would leak later information. Existing source labels are still retrospective and regional archive-availability flags remain proxies for sensor completeness. Consequently this is a **pseudo-real-time hindcast**, not a vintage-correct historical replay.', '',
        '## Public inputs and missing-data rules', '',
        '- NASA POWER daily UTC temperature (°C), corrected precipitation (mm/day), relative humidity (%) and wind speed (m/s), aggregated to monthly values. Rainfall is summed across days; other variables are averaged.',
        '- Five fixed area-weighted geographic strata per region, chosen from boundary H3 members using seed-42 KMeans and represented by their nearest member centres. Weights reflect stratum area, never fire counts. This is a regional weather approximation, not an area-integrated weather grid.',
        '- A site month requires every calendar day and all four valid variables. Regional weather requires all five sites; missing sites are not silently reweighted. Missing model inputs are never filled from a future date.',
        '- NOAA historical ONI: centred three-month ENSO index. DJF is January, NDJ is December of its stated year. The lag accounts for the centred window and publication/revision delay.',
        '- NOAA PSL monthly HadISST-based DMI for the Indian Ocean Dipole. Negative anomalies remain valid; missing sentinels remain missing.',
        '- Raw responses, retrieval timestamps, URLs, hashes, sampling sites and weights are cached locally. Each model report records input/code hashes and library versions. Refreshing an archive creates a new retrospective experiment; it does not reconstruct historical releases.', '',
        '| Region | Complete weather months | Weather range | Eligible target months | Target range |',
        '| --- | ---: | --- | ---: | --- |']
    from .outlook import fire_target
    for region in reports:
        w=pd.read_parquet(BASE/f'inputs/{region}/weather-monthly.parquet');available=w[w.complete]
        y=fire_target(pd.read_parquet(ROOT/f'data/harmonized/{region}_monthly.parquet')).dropna()
        lines.append(f'| {names[region]} | {len(available)}/{len(w)} | {available.month.min():%Y-%m}–{available.month.max():%Y-%m} | {len(y)} | {y.index.min():%Y-%m}–{y.index.max():%Y-%m} |')
    lines+=['', '## Fixed availability policy', '',
        '| Input / label | Latest month allowed at issue month T | Example for 1 August 2019 |',
        '| --- | --- | --- |',
        '| Fire predictors and training labels | T − 2 | June 2019 |',
        '| Weather | T − 3 | May 2019 |',
        '| ONI centre month | T − 5 | March 2019 (FMA window ends April) |',
        '| DMI | T − 4 | April 2019 |', '',
        'These are conservative observation lags, not forecasts of future weather. NASA documents a distinction between near-real-time and climate-analysis inputs; current ONI/DMI archives can be revised. Lags prevent later observation dates entering predictors, but cannot remove revisions already present in today’s archives. ONI is used as a historical predictor, not presented as NOAA’s current official ENSO diagnosis (monitoring moved to RONI in 2026).', '',
        '## Validation design', '',
        'Fixed expanding-window origins: January 2019–December 2025. Each origin retrains using only target months available by T−2. Leads 2 and 3 purge additional recent training rows so their labels also obey that cutoff. All three models are scored on the identical eligible origins. Targets extending beyond December 2025 are excluded, giving 84 / 83 / 82 potential cases. Training needs at least 48 eligible rows and a baseline needs at least five prior examples of the target calendar month. No random train/test split, shuffled cross-validation, test-set parameter search or weather normalization fitted on the full record is used.', '',
        'The experiment is prequential: earlier evaluation outcomes can enter later origins once available. The 2024–2025 table is a diagnostic within that same rolling evaluation, not a separate untouched holdout. Treat 2019–2025 as a development benchmark for any subsequent revisions.', '',
        '| Model | Inputs |', '| --- | --- |',
        '| Seasonal | Empirical distribution of available previous occurrences of the target calendar month |',
        '| History ML | Target-month sine/cosine; prior seasonal median/P10/P90; fire lags 2,3,4,13,14; target month last year; recent 3-month fire total |',
        '| Weather + climate ML | Same history features plus weather lags 3,4,5; ONI centre lags 5,6; DMI lags 4,5 |', '',
        'Five independent LightGBM quantile regressors predict log(1+activity), with quantiles 0.10/0.25/0.50/0.75/0.90, 64 trees, learning rate 0.04, 7 leaves, depth 3, minimum 12 child samples, L2 5, seed 42 and one worker. Predictions are transformed back, clipped at zero and sorted to repair crossing. Choices were fixed before inspecting this benchmark; no regional winner was selected after testing.', '',
        '## Interval and point performance', '',
        'WIS is a weighted interval score using the median and the central 80% interval: `(0.5 × absolute median error + 0.1 × interval score) / 1.5`, with interval score `width + 10 × distance outside the interval`. Lower is better. Five-quantile mean pinball loss, MAE, WAPE and bias are also saved. Skill is `1 − model score / baseline score`; positive means improvement. Brackets show a paired calendar-year-block bootstrap 95% interval (1,000 resamples, seed 42). Only seven year blocks are available, and intervals are descriptive rather than strong evidence of generalization.', '',
        '| Region | Lead | Cases | Seasonal WIS | Weather WIS | WIS skill [95% interval] | History ML WIS | Weather vs history WIS skill | Weather P10–P90 coverage |',
        '| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |']
    for region,r in reports.items():
        for lead in [1,2,3]:
            scores={m['model']:m for m in r['metrics'] if m['lead']==lead}
            if len(scores)!=3:continue
            b,w,h=[scores[k] for k in ['seasonal','weather_climate_ml','history_ml']]
            skill=r['paired_skills'][str(lead)]['wis'];lo,hi=skill['year_block_bootstrap_95']
            lines.append(f"| {names[region]} | {lead} | {w['n']} | {b['WIS']:.1f} | {w['WIS']:.1f} | {percent(skill['skill'])} [{percent(lo)}, {percent(hi)}] | {h['WIS']:.1f} | {percent(1-w['WIS']/h['WIS'])} | {100*w['coverage80']:.1f}% |")
    lines+=['', '## Above-normal probability performance', '',
        '“Above normal” means strictly greater than the available previous same-month median at that origin. Seasonal probabilities use observed exceedance frequency with Beta(1,1) smoothing; ML probabilities interpolate the five predicted quantiles and cap tails at 0.1–0.9. These are not separately calibrated probabilities. Ties can make the seasonal exceedance probability less than 0.5. Brier score measures squared probability error; lower is better. Equal-width reliability bins, sample counts and observed frequencies are saved in each report. Do not advertise a “70% chance” as calibrated on this evidence.', '',
        '| Region | Lead | Seasonal Brier | History ML Brier | Weather Brier | Weather Brier skill [95% interval] | Numerical gate |',
        '| --- | ---: | ---: | ---: | ---: | --- | --- |']
    for region,r in reports.items():
        for lead in [1,2,3]:
            scores={m['model']:m for m in r['metrics'] if m['lead']==lead}
            if len(scores)!=3:continue
            b,w,h=[scores[k] for k in ['seasonal','weather_climate_ml','history_ml']]
            skill=r['paired_skills'][str(lead)]['brier'];lo,hi=skill['year_block_bootstrap_95']
            lines.append(f"| {names[region]} | {lead} | {b['Brier']:.3f} | {h['Brier']:.3f} | {w['Brier']:.3f} | {percent(skill['skill'])} [{percent(lo)}, {percent(hi)}] | {'pass' if r['numerical_skill_gate'][str(lead)] else 'fail'} |")
    lines+=['', '## Recent rolling diagnostic (2024–2025)', '',
        '| Region | Lead | Cases | Seasonal WIS | Weather WIS | Seasonal Brier | Weather Brier |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for region,r in reports.items():
        for lead in [1,2,3]:
            scores={m['model']:m for m in r['rolling_2024_2025_diagnostic'] if m['lead']==lead}
            if len(scores)!=3:continue
            b,w=scores['seasonal'],scores['weather_climate_ml']
            lines.append(f"| {names[region]} | {lead} | {w['n']} | {b['WIS']:.1f} | {w['WIS']:.1f} | {b['Brier']:.3f} | {w['Brier']:.3f} |")
    nsw=pd.read_parquet(BASE/'results/nsw/hindcasts.parquet')
    case=nsw[nsw.issue==pd.Timestamp('2019-08-01')]
    case.to_csv(BASE/'results/nsw/august-2019-case.csv',index=False)
    lines+=['', '## NSW August 2019 story check', '',
        'The strategy’s proposed Black Summer early-warning claim must follow the evidence. An August issue covers August–October only. The complete output for that issue, including both comparators and actuals, is saved in `data/outlook/results/nsw/august-2019-case.csv`; it was not used to select parameters.', '',
        '| Target | Seasonal median | Weather median | Weather P10–P90 | Observed | Weather P(above prior median) |',
        '| --- | ---: | ---: | --- | ---: | ---: |']
    for row in case[case.model=='weather_climate_ml'].itertuples():
        b=case[(case.model=='seasonal')&(case.lead==row.lead)].iloc[0]
        lines.append(f'| {row.target:%Y-%m} | {b.q50:,.0f} | {row.q50:,.0f} | {row.q10:,.0f}–{row.q90:,.0f} | {row.actual:,.0f} | {100*row.p_above_normal:.0f}% |')
    lines+=['', '## Decision and remaining work', '',
        'A lead passes the preliminary numerical gate only if it has at least 60 scored cases, positive lower bootstrap bounds for both WIS and Brier improvement over the seasonal baseline, and empirical 80% interval coverage between 65% and 95%. This exploratory gate is necessary but insufficient: no historical-vintage validation, spatial transfer test or operational release test has been completed. `app_ready` and `operationally_validated` remain false for every region.', '',
        f"Numerical passes: {sum(sum(r['numerical_skill_gate'].values()) for r in reports.values())}/9 region–lead combinations. Do not integrate a claimed validated early-warning product based on this run.", '',
        'Before considering app integration: obtain historical input release vintages or prospectively log forecasts; assess calibration using training-only splits; evaluate any revised model on a newly reserved period; test weather-grid representativeness and sensitivity to lag choices; retain seasonal history as the comparator and fallback. Improvements should be motivated scientifically and re-evaluated without tuning on the same benchmark. Regional results do not support arbitrary polygons, districts or other source/confidence categories.', '',
        '## Latest research availability', '',
        'The latest issue is generated separately and explicitly marked unavailable when any required lagged input is missing. No stale-value substitution is used. Latest predictions, where present, inherit the same research-only cautions.', '',
        '| Region | Issue | Available leads | Unavailable reason |', '| --- | --- | --- | --- |']
    for region in reports:
        latest=json.loads((BASE/f'results/{region}/latest-research.json').read_text())
        ready=sorted({x['lead'] for x in latest['forecasts'] if x.get('model')=='weather_climate_ml'})
        reasons=sorted({x['reason'] for x in latest['forecasts'] if x.get('status')=='unavailable'})
        lines.append(f"| {names[region]} | {latest['issue'][:10]} | {', '.join(map(str,ready)) or 'none'} | {'; '.join(reasons) or '—'} |")
    lines+=['', '## Reproduce locally', '',
        '```sh', '.venv/bin/python -m ml.outlook_data --fetch', '.venv/bin/python -m unittest tests.test_outlook -v', '.venv/bin/python -m ml.outlook', '.venv/bin/python -m ml.validate_outlook', '.venv/bin/python -m ml.report_outlook', '```', '',
        'The first command makes public agency downloads and resumes matching cached inputs. Use `--refresh` only deliberately to obtain revised source responses. Generated data remain under ignored `data/outlook/`; no frontend assets or app endpoints are added.', '',
        'Machine-readable outputs per region: `hindcasts.parquet`, `hindcasts.csv`, `report.json`, `latest-research.json`. They include every comparison model, prediction quantiles, target/issue dates, availability cutoffs, training counts and proper scores. The source/parameter identity is in `report.json`.', '',
        '## Primary source documentation', '',
        '- [NASA POWER meteorology sources and near-real-time caveats](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/)',
        '- [NASA POWER data FAQ and latency](https://power.larc.nasa.gov/docs/faqs/data/)',
        '- [NASA POWER monthly service limitations](https://power.larc.nasa.gov/docs/services/api/temporal/monthly/)',
        '- [NOAA ONI definition, revisions and RONI transition](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/oni/v5/)',
        '- [NOAA ONI raw historical series](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt)',
        '- [NOAA PSL DMI definition and source](https://psl.noaa.gov/data/timeseries/month/DMI/)',
        '- [NOAA PSL DMI raw monthly series](https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.data)', '']
    (ROOT/'docs/fire_outlook.md').write_text('\n'.join(lines))
    print('Saved docs/fire_outlook.md and NSW August 2019 case table.')


if __name__=='__main__':main()
