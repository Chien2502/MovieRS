"""Giải thích từ payload đã fit; không huấn luyện hoặc dùng nhãn TEST."""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.experiments.artifacts import read_json,sha256
from src.experiments.config import ROOT
from src.models.research import percentile


def explain_list(run,fit,user_id,name,seed,ids):
    folder=Path(run['folder'])
    profile_dir=ROOT/'artifacts/resource_profiles'/folder.name
    profile_path=profile_dir/'profile.json'
    if not profile_path.exists():return None
    profile=read_json(profile_path)
    if profile['selection_sha256']!=sha256(folder/'selection.json'):
        raise ValueError('Payload giải thích khác cấu hình đã khóa')
    entry=next((r for r in profile['measurements'] if r['model']==name and
                (r['seed'] is None or (pd.notna(seed) and r['seed']==int(seed)))),None)
    if entry is None:return None
    suffix=f"_{entry['seed']}" if entry['seed'] is not None else ''
    payload=profile_dir/(name+suffix+'.joblib')
    if sha256(payload)!=entry['sha256']:raise ValueError('Payload giải thích sai checksum')
    model=joblib.load(payload)
    history=fit[fit.userId==user_id]
    candidates=np.array(sorted(set(fit.movieId.astype(int))-set(history.movieId.astype(int))))
    scores=model.score_items(int(user_id),candidates)
    expected=candidates[np.lexsort((candidates,-scores))[:len(ids)]].tolist()
    if expected!=list(ids):raise ValueError('Payload không tái tạo danh sách đã ghi; không hiển thị điểm')
    table=pd.DataFrame({'movieId':candidates,'ranking_score':scores})
    if name=='AdaptiveHybrid':
        n=model.counts.get(int(user_id),0)
        if not n:
            table['đóng góp fallback']=percentile(model.popularity.score_items(int(user_id),candidates))
            table['lý do']='Chưa có lịch sử trước cutoff; Bayesian fallback'
        else:
            w=n/(n+model.tau)
            beta=model.beta if int(user_id) in model.content.profiles else 0
            table['đóng góp SVD']=w*percentile(model.svd.score_items(int(user_id),candidates))
            table['đóng góp genre']=(1-w)*beta*percentile(model.content.score_items(int(user_id),candidates))
            table['đóng góp popularity']=(1-w)*(1-beta)*percentile(model.popularity.score_items(int(user_id),candidates))
            table['lý do']=f'{n} rating trước cutoff; trọng số SVD={w:.4f}, beta={beta:.2f}'
    elif name=='MostPopular':
        table['lý do']='Số rating trong TRAIN+VAL; không dùng mức phổ biến tương lai'
    elif name=='BiasedSVD':
        table['lý do']='Điểm factorization và bias từ TRAIN+VAL'
    else:table['lý do']='Điểm mô hình đã fit trên TRAIN+VAL'
    return table.set_index('movieId').loc[list(ids)].reset_index()
