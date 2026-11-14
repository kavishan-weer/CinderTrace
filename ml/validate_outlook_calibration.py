"""Audit frozen protocol, calibration cutoffs and paired 2026 forecast artifacts."""
import json

import numpy as np
import pandas as pd

from .calibrate_outlook import OUT, REGIONS, BASE, load_protocol, fit_calibrator, apply_calibrator


def main():
    protocol=load_protocol();frame=pd.read_parquet(OUT/'fresh-holdout.parquet')
    report=json.loads((OUT/'report.json').read_text())
    assert report['app_ready'] is False and report['operationally_validated'] is False
    assert not any(report['numerical_gate'].values())
    assert not frame.duplicated(['region','issue','lead','model']).any()
    assert frame.target.between(pd.Timestamp(protocol['holdout_target_start']),pd.Timestamp(protocol['holdout_target_end'])).all()
    assert frame.p_above_normal.between(0,1).all()
    np.testing.assert_allclose(frame.brier,(frame.p_above_normal-frame.above_normal_observed)**2)
    expected_models=set(protocol['comparators'])
    for (_,_,_),g in frame.groupby(['region','issue','lead']):
        assert set(g.model)==expected_models
        for column in ['target','actual','above_normal_observed','normal_threshold']:
            assert g[column].nunique()==1
        assert (g.train_target_max<=g.training_cutoff).all()
    audited=0
    for region in REGIONS:
        history=pd.read_parquet(BASE/f'results/{region}/hindcasts.parquet')
        assert (history.target<pd.Timestamp('2026-01-01')).all()
        selected=frame[(frame.region==region)&frame.model.str.endswith('_calibrated')]
        for row in selected.itertuples():
            model=row.model.removesuffix('_calibrated')
            raw=frame[(frame.region==region)&(frame.issue==row.issue)&(frame.lead==row.lead)&(frame.model==model)].iloc[0]
            cutoff=min(row.issue-pd.DateOffset(months=2),pd.Timestamp('2025-12-01'))
            eligible=history[(history.model==model)&(history.lead==row.lead)&(history.target<=cutoff)&(history.issue<row.issue)]
            assert len(eligible)==row.calibration_n
            assert pd.Timestamp(row.calibration_target_max)==eligible.target.max()<=cutoff
            assert pd.Timestamp(row.calibration_issue_max)==eligible.issue.max()<row.issue
            assert pd.Timestamp(row.calibration_cutoff)==cutoff
            cal=fit_calibrator(history,row.issue,row.lead,model)
            np.testing.assert_allclose([row.slope,row.intercept],[cal['slope'],cal['intercept']])
            np.testing.assert_allclose(row.p_above_normal,float(apply_calibrator(raw.p_above_normal,cal)))
            assert row.raw_probability==raw.p_above_normal
            # Binary calibration must not silently change activity distributions.
            for column in ['q10','q25','q50','q75','q90','wis','covered80']:
                assert getattr(row,column)==raw[column]
            audited+=1
    result={'status':'pass','rows':len(frame),'calibrated_rows':audited,
        'paired_cases':int(frame.groupby(['region','issue','lead']).ngroups),
        'frozen_input_hashes_verified':len(protocol['inputs']),
        'meaning':'Data lineage, pairing, arithmetic and temporal-isolation checks; not proof of forecast skill.'}
    (OUT/'artifact-audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':main()
