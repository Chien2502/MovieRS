"""Worker đơn chạy thủ công; chọn bằng VAL, không đọc metric TEST để publish."""

import argparse
import os
import time
from datetime import datetime,timezone
from pathlib import Path

from src.experiments.artifacts import identity,read_json,sha256,utc_now,write_json
from src.experiments.config import ROOT,load_config


def promotion_gate(candidate,incumbent=None):
    import math
    def valid(metrics):
        try:
            values=[metrics['ndcg'],metrics['latency_ms']['p95']]
            values.extend(g['ndcg'] for g in metrics['cohorts'].values())
            if metrics.get('rating'):values.extend(metrics['rating'][k] for k in ['RMSE','MAE'] if k in metrics['rating'])
            return bool(metrics['cohorts']) and all(math.isfinite(v) and v>=0 for v in values)
        except (KeyError,TypeError,ValueError):return False
    if not valid(candidate):return False
    if incumbent is None:return True
    if not valid(incumbent) or candidate['ndcg']<incumbent['ndcg']:return False
    if candidate['latency_ms']['p95']>max(200,incumbent['latency_ms']['p95']*1.5):return False
    for name,group in incumbent['cohorts'].items():
        if candidate.get('cohorts',{}).get(name,{}).get('ndcg',-1)<group['ndcg']-.02:return False
    cr,ir=candidate.get('rating'),incumbent.get('rating')
    if cr and ir and cr['RMSE']>ir['RMSE']:return False
    return True


def train_worker(config,snapshot,selection_path,base=None):
    import gc
    import joblib
    import pandas as pd
    from api.services.feedback_store import read_feedback
    from api.services.serving import load_bundle
    from src.data.snapshots import load_snapshot
    from src.evaluation.protocol import EvaluationContext,evaluate_ranker,rating_evaluation
    from src.experiments.resources import ResourceMonitor
    from src.models.hybrid import parse_genres
    from src.models.research import GenreContent,HybridRanker,ItemStatistics,SparseItemKNN
    from src.models.svd_surprise import SurpriseSVDRecommender
    base=Path(base or ROOT/'artifacts/serving')
    base.mkdir(parents=True,exist_ok=True)
    lock=base/'.worker.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    version='model_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=base/version;folder.mkdir()
    status={'status':'running','version':version,'created_at':utc_now(),'worker_pid':os.getpid()}
    write_json(folder/'job.json',status)
    try:
        manifest=load_snapshot(snapshot)
        selection=read_json(selection_path)
        experiment=read_json(Path(selection_path).parent/'manifest.json')
        if experiment['dataset_id']!=manifest['dataset_id']:
            raise ValueError('Selection không thuộc snapshot được huấn luyện')
        if experiment['protocol']['threshold']!=config.threshold or experiment['protocol']['k']!=config.k:
            raise ValueError('Selection dùng metric hoặc relevance khác cấu hình worker')
        if not selection.get('frozen_at') or selection.get('test_opened_before_freeze') is not False:
            raise ValueError('Thiếu selection đã khóa trước TEST')
        train=pd.read_parquet(Path(snapshot)/'train.parquet')
        val=pd.read_parquet(Path(snapshot)/'validation.parquet')
        movies=pd.read_parquet(Path(snapshot)/'movies.parquet')
        genres={int(r.movieId):parse_genres(r.genres) for r in movies.itertuples()}
        trials=selection['trials']
        best=max(trials,key=lambda t:t['ndcg'])
        spec={'family':best['family'],'svd':selection['svd'],'knn':selection['knn'],'hybrid':selection['hybrid']}
        def build(spec,ratings,check):
            family=spec['family']
            if family in {'MostPopular','BayesianItemMean'}:
                return ItemStatistics('count' if family=='MostPopular' else 'bayesian').fit(ratings)
            if family=='GenreContent':return GenreContent(movies).fit(ratings)
            if family=='SparseItemKNN':return SparseItemKNN(*spec['knn'],check=check).fit(ratings)
            f,e,r=spec['svd']
            svd=SurpriseSVDRecommender(n_factors=f,n_epochs=e,reg_all=r,random_state=config.seeds[0]).fit(ratings)
            if family=='BiasedSVD':return svd
            return HybridRanker(svd,GenreContent(movies).fit(ratings),ItemStatistics().fit(ratings),
                                ratings.userId.value_counts().to_dict(),**spec['hybrid'])
        with ResourceMonitor(config.resources,config.profiles['research'].minutes) as monitor:
            context=EvaluationContext(train,val,genres,config.validation_users,threshold=config.threshold)
            candidate=build(spec,train,monitor.check)
            current,_=evaluate_ranker(candidate,context,spec['family'],k=config.k,check=monitor.check)
            current['rating']=rating_evaluation(candidate,train,val,monitor.check)
            incumbent_metrics=None
            pointer=base/'current.json'
            previous=read_json(pointer) if pointer.exists() else None
            if previous:
                old,_=load_bundle(pointer)
                old_model=build(old['spec'],train,monitor.check)
                incumbent_metrics,_=evaluate_ranker(old_model,context,'incumbent',k=config.k,check=monitor.check)
                incumbent_metrics['rating']=rating_evaluation(old_model,train,val,monitor.check)
                del old,old_model
            promoted=promotion_gate(current,incumbent_metrics)
            evidence={'candidate':current,'incumbent':incumbent_metrics,'validation_sha256':manifest['files']['validation.parquet'],
                      'training_sha256':manifest['files']['train.parquet'],'selection_sha256':sha256(selection_path),
                      'criterion':'validation_NDCG_with_latency_cohort_and_rating_guardrails','test_used':False}
            write_json(folder/'gate.json',evidence)
            if not promoted:
                status.update(status='rejected',completed_at=utc_now())
                write_json(folder/'job.json',status)
                return status
            del candidate
            gc.collect()
            history=pd.concat([train,val],ignore_index=True)
            feedback=read_feedback()
            if not feedback.empty:
                if (feedback.userId<200000).any():raise ValueError('Feedback app sai miền ID')
                live=feedback[['userId','movieId','rating']].copy()
                live['timestamp']=int(time.time())
                history=pd.concat([history,live],ignore_index=True)
            model=build(spec,history,monitor.check)
            # Check không được serialize theo monitor/thread; inference không dùng nó.
            if hasattr(model,'check'):model.check=None
            bundle={'model':model,'history':history,'spec':spec,'dataset_id':manifest['dataset_id'],
                    'catalog':movies[['movieId','title','genres']]}
            joblib.dump(bundle,folder/'model.joblib',compress=3)
            write_json(folder/'resource_usage.json',monitor.report())
            write_json(folder/'manifest.json',{'schema_version':2,'status':'ready','version':version,
                       'dataset_id':manifest['dataset_id'],'spec':spec,'previous':previous,
                       'files':{n:sha256(folder/n) for n in ['model.joblib','gate.json','resource_usage.json']}})
            write_json(pointer,{'version':version,'manifest_sha256':sha256(folder/'manifest.json')})
            status.update(status='promoted',completed_at=utc_now(),model_family=spec['family'])
            status['api_reloaded']=False
            if os.getenv('ADMIN_API_TOKEN'):
                import requests
                try:
                    response=requests.post(f"http://127.0.0.1:{int(os.getenv('API_PORT','8000'))}/api/recommendations/reload",
                                           headers={'X-Admin-Token':os.environ['ADMIN_API_TOKEN']},timeout=5)
                    status['api_reloaded']=response.status_code==200
                except requests.RequestException:pass
            write_json(folder/'job.json',status)
            return status
    except BaseException as error:
        status.update(status='failed',error_type=type(error).__name__)
        write_json(folder/'job.json',status)
        raise
    finally:lock.unlink(missing_ok=True)


def rollback(base,version):
    from api.services.serving import load_bundle
    base=Path(base).resolve()
    folder=(base/version).resolve()
    if not folder.is_relative_to(base) or not folder.is_dir():raise ValueError('Version rollback không hợp lệ')
    candidate={'version':version,'manifest_sha256':sha256(folder/'manifest.json')}
    check=base/'rollback_check.json'
    write_json(check,candidate)
    try:load_bundle(check)
    finally:check.unlink(missing_ok=True)
    write_json(base/'current.json',candidate)
    return candidate


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    parser=argparse.ArgumentParser(description='Worker serving thủ công, ngoài tiến trình API')
    parser.add_argument('--config',default=str(ROOT/'configs/research.toml'))
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--selection',required=True)
    parser.add_argument('--rollback',default=None)
    args=parser.parse_args()
    config=load_config(args.config)
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]=str(config.resources.threads)
    if args.rollback:result=rollback(ROOT/'artifacts/serving',args.rollback)
    else:result=train_worker(config,args.snapshot,args.selection)
    import json
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
