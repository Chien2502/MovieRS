"""Đo payload mô hình độc lập bằng cấu hình đã khóa; không dùng metric TEST để chọn."""

import argparse
import gc
import os
import time
from pathlib import Path

from src.experiments.artifacts import read_json,sha256,utc_now,write_json
from src.experiments.config import ROOT,load_config


def profile_models(run,config):
    import joblib
    import pandas as pd
    from src.data.snapshots import load_snapshot
    from src.experiments.resources import ResourceMonitor
    from src.models.research import GenreContent,HybridRanker,ItemStatistics,SparseItemKNN
    from src.models.svd_surprise import SurpriseSVDRecommender
    run=Path(run)
    manifest=read_json(run/'manifest.json')
    selection=read_json(run/'selection.json')
    snapshot=Path(manifest['snapshot'])
    load_snapshot(snapshot)
    fit=pd.concat([pd.read_parquet(snapshot/'train.parquet'),pd.read_parquet(snapshot/'validation.parquet')],ignore_index=True)
    movies=pd.read_parquet(snapshot/'movies.parquet')
    out=ROOT/'artifacts/resource_profiles'/run.name
    out.mkdir(parents=True,exist_ok=False)
    measurements=[]
    with ResourceMonitor(config.resources,20) as monitor:
        def measure(name,factory,seed=None):
            started=time.monotonic();model=factory();monitor.check()
            fitted=time.monotonic()-started
            if hasattr(model,'check'):model.check=None
            path=out/(name+(f'_{seed}' if seed is not None else '')+'.joblib')
            joblib.dump(model,path,compress=3)
            measurements.append({'model':name,'seed':seed,'fit_seconds':round(fitted,4),
                                 'serialized_bytes':path.stat().st_size,'sha256':sha256(path),
                                 'serialization':'joblib_compress_3_excluding_evaluation_score_cache'})
            return model
        for mode,name in [('mean','GlobalMean'),('bias','RegularizedBias'),('count','MostPopular'),('bayesian','BayesianItemMean')]:
            model=measure(name,lambda mode=mode:ItemStatistics(mode).fit(fit))
            del model
        content=measure('GenreContent',lambda:GenreContent(movies).fit(fit))
        pop=ItemStatistics().fit(fit)
        model=measure('SparseItemKNN',lambda:SparseItemKNN(*selection['knn'],check=monitor.check).fit(fit))
        del model;gc.collect()
        for seed in config.seeds:
            f,e,r=selection['svd']
            svd=measure('BiasedSVD',lambda:SurpriseSVDRecommender(n_factors=f,n_epochs=e,reg_all=r,random_state=seed).fit(fit),seed)
            hybrid=measure('AdaptiveHybrid',lambda:HybridRanker(svd,content,pop,fit.userId.value_counts().to_dict(),**selection['hybrid']),seed)
            del svd,hybrid;gc.collect()
        report={'created_at':utc_now(),'run_id':run.name,'dataset_id':manifest['dataset_id'],
                'selection_sha256':sha256(run/'selection.json'),'purpose':'Independent resource profiling, not another TEST selection',
                'training':'TRAIN+VAL, no app feedback','measurements':measurements,'resources':monitor.report()}
    write_json(out/'profile.json',report)
    return out


def main():
    parser=argparse.ArgumentParser(description='Đo kích thước payload mô hình từ selection đã khóa')
    parser.add_argument('--run',required=True)
    args=parser.parse_args()
    config=load_config()
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]=str(config.resources.threads)
    print(profile_models(args.run,config),flush=True)


if __name__=='__main__':main()
