"""Independent persisted-output audit; run after ml.outlook and before reporting.

python -m ml.validate_outlook
Checks prediction arithmetic, baseline provenance, matching evaluation cases,
availability cutoffs and hashes. Passing does not establish forecasting skill.
"""
import json

import numpy as np
import pandas as pd

from .events import ROOT, file_sha
from .outlook_data import BASE


def audit(region):
    directory=BASE/'results'/region
    report=json.loads((directory/'report.json').read_text())
    frame=pd.read_parquet(directory/'hindcasts.parquet')
    assert report['app_ready'] is False and report['operationally_validated'] is False
    for item in report['inputs']:
        assert file_sha(ROOT/item['path'])==item['sha256'],f"Changed input: {item['path']}"
    assert not frame.duplicated(['model','issue','lead']).any()
    assert not frame.empty
    assert frame[['q10','q25','q50','q75','q90','actual','p_above_normal']].notna().all().all()
    assert np.isfinite(frame[['q10','q25','q50','q75','q90','actual','p_above_normal']].to_numpy()).all()
    quantiles=frame[['q10','q25','q50','q75','q90']].to_numpy()
    assert (quantiles>=0).all() and (np.diff(quantiles,axis=1)>=0).all()
    assert frame.p_above_normal.between(0,1).all()
    errors=(frame.actual-frame.q50).abs()
    interval=(frame.q90-frame.q10)+10*(frame.q10-frame.actual).clip(lower=0)+10*(frame.actual-frame.q90).clip(lower=0)
    np.testing.assert_allclose(frame.wis,(.5*errors+.1*interval)/1.5)
    np.testing.assert_allclose(frame.brier,(frame.p_above_normal-(frame.actual>frame.normal_threshold).astype(int))**2)
    assert (frame.train_target_max<=frame.training_cutoff).all()
    assert (frame.baseline_history_max<=frame.fire_feature_cutoff).all()
    assert (frame.train_rows>=48).all() and (frame.baseline_n>=5).all()
    for row in frame.itertuples():
        assert row.target==row.issue+pd.DateOffset(months=row.lead-1)
        for col,lag in [('training_cutoff',2),('fire_feature_cutoff',2),('weather_feature_cutoff',3),('oni_center_cutoff',5),('dmi_cutoff',4)]:
            assert getattr(row,col)==row.issue-pd.DateOffset(months=lag)
    # Rebuild seasonal quantiles from source targets, independently of feature construction.
    from .outlook import fire_target
    y=fire_target(pd.read_parquet(ROOT/f'data/harmonized/{region}_monthly.parquet'))
    for row in frame[frame.model=='seasonal'].itertuples():
        pool=y[(y.index<=row.issue-pd.DateOffset(months=2))&(y.index.month==row.target.month)].dropna()
        assert row.baseline_n==len(pool) and row.baseline_history_max==pool.index.max()
        np.testing.assert_allclose([row.q10,row.q25,row.q50,row.q75,row.q90],np.quantile(pool,[.1,.25,.5,.75,.9]))
        assert row.actual==y[row.target]
    possible=len(pd.date_range(report['policy']['evaluation_start'],report['policy']['evaluation_end'],freq='MS'))
    for lead in [1,2,3]:
        n=possible-lead+1-sum(x['lead']==lead for x in report['skipped_origins'])
        group=frame[frame.lead==lead]
        assert group.groupby('model').size().eq(n).all()
        assert group.groupby('issue').model.nunique().eq(3).all()
        for col in ['actual','normal_threshold','train_rows','baseline_n']:
            assert group.groupby('issue')[col].nunique().eq(1).all()
    latest=json.loads((directory/'latest-research.json').read_text())
    assert latest['app_ready'] is False
    result={'region':region,'status':'pass','forecast_rows':len(frame),'paired_cases':len(frame)//3,
            'hashes_verified':len(report['inputs']),'claim':'Artifact consistency only; not forecast skill or operational validation.'}
    (directory/'artifact-audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    return result


if __name__=='__main__':
    for region in ['lk','ca','nsw']:audit(region)
