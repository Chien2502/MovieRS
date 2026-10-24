"""So sánh ghép cặp theo user; seed không được coi là user độc lập."""

import numpy as np
import pandas as pd


def paired_comparison(frame, candidate, baseline, metric='ndcg', resamples=2000, seed=2026):
    selected = frame[frame.model.isin([candidate, baseline])]
    means = selected.groupby(['model','user_id'])[metric].mean().unstack('model')
    if candidate not in means or baseline not in means or means[[candidate,baseline]].isna().any().any():
        raise ValueError('So sánh yêu cầu cùng user ở cả hai mô hình')
    # Trước bootstrap phải kiểm tra mỗi seed chấm cùng tập user.
    expected = set(means.index)
    for _, group in selected.groupby(['model','seed'], dropna=False):
        if set(group.user_id) != expected or group.user_id.duplicated().any():
            raise ValueError('Thiếu hoặc trùng user theo model/seed')
    delta = (means[candidate] - means[baseline]).to_numpy()
    rng = np.random.default_rng(seed)
    # Batch tránh cấp phát resamples × users khi mẫu lớn.
    bootstrap = [float(delta[rng.integers(0,len(delta),len(delta))].mean()) for _ in range(resamples)]
    ci = np.quantile(bootstrap,[.025,.975]).tolist()
    base = float(means[baseline].mean())
    return {'candidate':candidate,'baseline':baseline,'metric':metric,'users':len(delta),
            'delta':float(delta.mean()),'relative_delta':float(delta.mean()/base) if base else None,
            'ci95':ci,'improvement_supported':bool(ci[0]>0),
            'method':'paired_user_bootstrap_after_averaging_training_seeds', 'resamples':resamples,
            'interpretation':('Có bằng chứng cải thiện' if ci[0]>0 else
                              ('Có bằng chứng giảm chất lượng xếp hạng' if ci[1]<0 else 'Chưa đủ bằng chứng cải thiện'))}


def model_intervals(frame,metric='ndcg',resamples=2000,seed=2026):
    """CI của trung bình từng model; quyết định cải tiến vẫn cần CI của paired delta."""
    rows=[]
    for name,group in frame.groupby('model'):
        values=group.groupby('user_id')[metric].mean().to_numpy()
        rng=np.random.default_rng(seed)
        means=[float(values[rng.integers(0,len(values),len(values))].mean()) for _ in range(resamples)]
        lo,hi=np.quantile(means,[.025,.975])
        rows.append({'model':name,'mean':float(values.mean()),'lower':float(lo),'upper':float(hi),'users':len(values)})
    return pd.DataFrame(rows)
