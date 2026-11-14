"""Write the calibrated outlook holdout report, without selecting a model."""
import json

from .calibrate_outlook import OUT, REGIONS, load_protocol
from .events import ROOT


def main():
    protocol=load_protocol();report=json.loads((OUT/'report.json').read_text())
    names={'lk':'Sri Lanka','ca':'California','nsw':'NSW'}
    lines=['# Outlook probability calibration and new 2026 holdout', '',
        '**Calibration is implemented and tested on January–September 2026, which was excluded from the original 2019–2025 benchmark. The outlook remains outside the app: nine months per region/lead cannot establish generalization across complete fire seasons.**', '',
        '## What “fresh” means here', '',
        'This is a newly scored temporal holdout from the existing revised archive, not newly collected observations or a prospective forecast trial. The previous run printed recent target values and generated a November research outlook, but did not score 2026 forecasts. Neither calibration method nor hyperparameters were selected from 2026 performance. Treat this period as consumed after this evaluation; subsequent model development needs a new holdout or prospectively recorded forecasts.', '',
        f"The protocol was frozen at `{protocol['frozen_at']}` before scoring. It locks code/input hashes and the holdout period. Evaluation as of {protocol['as_of_date'][:10]} uses targets through September because the established two-month fire-observation maturity rule excludes October, even where archive totals exist. Later issue dates with missing/provisional inputs remain unavailable.", '',
        '## Fixed method and temporal isolation', '',
        'Each region and lead has a monotone sigmoid mapping `sigmoid(a × logit(p) + b)`. Fit minimizes summed binary log loss plus `0.5 × ((a−1)² + b²)`, shrinking towards the identity mapping. Slope is constrained to [0,10], intercept to [−10,10], with fixed penalty 1. No parameter or method search was performed. A minimum of 36 calibration cases and eight examples of each class is required; insufficient history or failed optimization explicitly retains the original probabilities.', '',
        'The calibration examples are the original expanding-window out-of-sample forecasts from 2019–2025. For each forecast issue, only examples with issue dates strictly earlier and target months no later than `min(issue−2 months, December 2025)` may fit the map. **No 2026 outcome trains calibration**, even after that outcome matures. Late-2025 issues predicting early-2026 months obey their own earlier maturity cutoff. This is per-issue historical calibration, not one fit using all of December 2025 before it existed.', '',
        'The base LightGBM parameters, activity target, weather sampling and lag policy are unchanged. Its expanding training window may use earlier 2026 fire labels only after they mature at a later forecast origin; this is the predeclared rolling evaluation, not a fixed-model test. Weather and climate archive revisions and retrospective fire-category labels remain limitations.', '',
        'The same calibration procedure is applied to seasonal probabilities as a control. History-only ML is also retained. All five alternatives share the same target, definition of above-normal, issue and eligible cases. Calibration changes only the binary probability of exceeding the available prior same-month median; it does **not** calibrate the P10–P90 activity fan chart or change WIS. The probability and original fan chart are separate estimates and should not be presented as one fully calibrated distribution.', '',
        'Small calibration samples motivate a low-parameter sigmoid rather than flexible isotonic fits; the requirement for out-of-sample calibration data follows the [scikit-learn calibration guidance](https://scikit-learn.org/stable/modules/calibration.html). This implementation uses a constrained, regularized logistic map rather than calling CalibratedClassifierCV.', '',
        '## New holdout: probability scores', '',
        'Brier score is squared probability error; lower is better. Positive skill means `1 − calibrated weather Brier / comparator Brier` is positive. Scores on nine monthly cases are descriptive, not evidence of a stable improvement. No year-block confidence interval is reported for a single partial calendar year.', '',
        '| Region | Lead | Cases | Seasonal Brier | Calibrated seasonal | Raw weather | Calibrated weather | Skill vs seasonal | Skill vs raw weather |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for region in REGIONS:
        for lead in [1,2,3]:
            scores={m['model']:m for m in report['metrics'] if m['region']==region and m['lead']==lead}
            if not scores:continue
            seasonal,seasonal_cal,raw,cal=[scores[m] for m in ['seasonal','seasonal_calibrated','weather_climate_ml','weather_climate_ml_calibrated']]
            skill=lambda baseline:100*(1-cal['Brier']/baseline['Brier']) if baseline['Brier'] else float('nan')
            lines.append(f"| {names[region]} | {lead} | {cal['n']} | {seasonal['Brier']:.3f} | {seasonal_cal['Brier']:.3f} | {raw['Brier']:.3f} | {cal['Brier']:.3f} | {skill(seasonal):+.1f}% | {skill(raw):+.1f}% |")
    lines+=['', '## Reliability and remaining interval performance', '',
        'Each report records five fixed probability bins, sample counts, average predicted probabilities and observed frequencies with Wilson 95% intervals. Empty bins stay empty. ECE5 summarizes the bin gaps but is unstable with nine cases; it is not a model-selection score or release criterion. Log loss is included as a second proper probability score. The original prediction intervals are unchanged.', '',
        '| Region | Lead | Calibrated mean probability | Observed above-normal rate | Calibrated log loss | Calibrated ECE5 | Raw seasonal WIS | Weather WIS | Weather 80% interval coverage |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for region in REGIONS:
        for lead in [1,2,3]:
            scores={m['model']:m for m in report['metrics'] if m['region']==region and m['lead']==lead}
            if not scores:continue
            s,c=scores['seasonal'],scores['weather_climate_ml_calibrated']
            lines.append(f"| {names[region]} | {lead} | {100*c['mean_probability']:.1f}% | {100*c['observed_rate']:.1f}% | {c['log_loss']:.3f} | {c['ECE5']:.3f} | {s['WIS']:.1f} | {c['WIS']:.1f} | {100*c['coverage80']:.1f}% |")
    lines+=['', '## Decision', '',
        '**App ready: false. Operationally validated: false.** All nine combinations remain below the minimum fresh-sample requirement. The frozen gate requires at least 60 cases across at least three calendar years, positive lower year-block uncertainty bounds for calibrated Brier improvement against both seasonal and raw weather probabilities, positive WIS skill against seasonal history, and 65–95% empirical coverage of the nominal 80% interval. These are preliminary necessary conditions, not a complete release standard.', '',
        'Do not pool the three leads as 27 independent observations: their targets overlap. Do not pool the three regions to make a local confidence claim. Improvements for one region/lead do not authorize an app-wide forecast or district/polygon forecasts. No best-performing calibration method was chosen after testing.', '',
        'Next evidence should come from genuinely future, time-stamped research forecasts and later eligible outcomes, including complete seasons. A local November research snapshot preserves the frozen protocol identity, raw/calibrated probabilities and original quantiles. It was recorded after the nominal November 1 issue date and is labelled accordingly; it is not a vintage-correct November 1 forecast. No automation, external upload, warning endpoint or app panel was added.', '',
        '## Verification and reproduction', '',
        'New unit tests cover date-cutoff isolation, future-label perturbations, per-lead target maturity, monotonicity, small/single-class fallback, failed optimization, invalid data, reliability bins and frozen-input changes. The persisted-output audit recomputes calibrators and probabilities, checks unchanged quantiles/scores, verifies all comparisons share cases, and rejects changed protocol inputs. Passing software checks does not establish forecast skill.', '',
        '```sh', '.venv/bin/python -m unittest tests.test_outlook_calibration -v',
        '.venv/bin/python -m ml.calibrate_outlook --prepare',
        '.venv/bin/python -m ml.calibrate_outlook --evaluate',
        '.venv/bin/python -m ml.validate_outlook_calibration',
        '.venv/bin/python -m ml.report_outlook_calibration', '```', '',
        'Preparation retains an existing protocol; evaluation refuses changed code or inputs. Keep this version and create a new experiment version for later archive refreshes or methodological changes. The app and original v1 benchmark are untouched.', '',
        'Local outputs in `data/outlook/calibration-v1/`: frozen `protocol.json`, paired `fresh-holdout.parquet` / `.csv`, `report.json` (all five models, proper scores, comparisons and reliability), `artifact-audit.json`, and the recorded research snapshot. The original method is in [fire_outlook.md](fire_outlook.md).', '']
    (ROOT/'docs/outlook_calibration.md').write_text('\n'.join(lines))
    print('Saved docs/outlook_calibration.md')


if __name__=='__main__':main()
