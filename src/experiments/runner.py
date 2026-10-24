"""VAL chọn cấu hình → khóa → refit → TEST; mỗi stage có checkpoint riêng."""

import gc
import importlib.metadata
import json
import os
import platform
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.snapshots import load_snapshot
from src.evaluation.protocol import EvaluationContext, evaluate_ranker, rating_evaluation
from src.evaluation.statistics import paired_comparison
from src.experiments.artifacts import identity, read_json, sha256, source_provenance, utc_now, write_json, verify_files
from src.experiments.config import ROOT
from src.experiments.resources import ResourceMonitor
from src.models.hybrid import parse_genres
from src.models.research import GenreContent, HybridRanker, ItemStatistics, SparseItemKNN
from src.models.svd_surprise import SurpriseSVDRecommender


class MemoizedScores:
    """Chỉ cache điểm trên candidate set cố định của cùng phase."""
    def __init__(self, model):
        self.model, self.cache = model, {}

    def score_items(self, uid, ids):
        key = (int(uid), identity(np.asarray(ids).tolist()))
        if key not in self.cache:
            self.cache[key] = self.model.score_items(uid, ids)
        return self.cache[key]


def _svd(parameters, seed):
    f, e, r = parameters
    return SurpriseSVDRecommender(n_factors=int(f), n_epochs=int(e), reg_all=r, random_state=seed)


def _trial_id(family, parameters):
    return family + '_' + identity(parameters)[:12]


def run_experiment(config, snapshot, profile='research', resume=None):
    snapshot = Path(snapshot)
    data = load_snapshot(snapshot)
    provenance = source_provenance(ROOT)
    code_hash = identity(provenance['source_sha256'])
    key = {'config':config.fingerprint(), 'dataset':data['dataset_id'], 'code':code_hash}
    base = config.path(config.run_dir)
    base.mkdir(parents=True, exist_ok=True)
    run = Path(resume) if resume else base / ('run_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if resume:
        old = read_json(run / 'manifest.json')
        if old['resume_key'] != key:
            raise ValueError('Không resume khi code, config hoặc dataset đã thay đổi')
        verify_files(run,old)
        if old['status'] == 'complete':
            from dashboard.services.artifacts import load_run
            load_run(run)
            return run
    run.mkdir(parents=True, exist_ok=True)
    verified_cache=old.get('files',{}) if resume else {}
    def reusable(path):
        relative=str(path.relative_to(run))
        return path.exists() and relative in verified_cache and sha256(path)==verified_cache[relative]
    lock = base / '.research.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError('Đang có job nghiên cứu hoặc lock chưa được xử lý; kiểm tra PID trong .research.lock') from None
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    monitor = ResourceMonitor(config.resources, config.profiles[profile].minutes)
    manifest = {'schema_version':2,'run_id':run.name,'dataset_id':data['dataset_id'], 'status':'running',
                'created_at':utc_now(),'worker_pid':os.getpid(),'resume_key':key,'config':config.model_dump(mode='json'),
                'snapshot':str(snapshot.resolve()), 'provenance':provenance,
                'environment':{'python':platform.python_version(), 'platform':platform.platform(),
                               'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','scipy','scikit-surprise','pyarrow','psutil']}},
                'protocol':{'id':'global_temporal_refit_v2','task':'static_future_window_topk',
                            'fit_for_test':'train_plus_validation','candidate_policy':'all_fit_items_minus_prior_history',
                            'unavailable_positives':'included_in_primary','threshold':config.threshold,'k':config.k,
                            't1':config.t1.isoformat(),'t2':config.t2.isoformat(),
                            'negative_item_sampling':False,'app_feedback':False},
                'files':{}}
    write_json(run / 'manifest.json', manifest)
    def checkpoint(stage):
        manifest['stage'] = stage
        manifest['files']={str(p.relative_to(run)):sha256(p) for p in run.rglob('*')
                           if p.is_file() and p.name!='manifest.json' and '.tmp' not in p.name}
        write_json(run / 'manifest.json', manifest)
        write_json(run / 'resource_usage.json', monitor.report())
        monitor.check()
        print(f'[Nghiên cứu] {stage}', flush=True)
    try:
        with monitor:
            if not reusable(run/'source_code.zip'):
                with zipfile.ZipFile(run/'source_code.zip','w',zipfile.ZIP_DEFLATED) as archive:
                    for relative,expected in provenance['source_sha256'].items():
                        source=ROOT/relative
                        if sha256(source)!=expected:raise ValueError('Mã nguồn thay đổi khi tạo snapshot code')
                        archive.write(source,relative)
            train = pd.read_parquet(snapshot / 'train.parquet')
            val = pd.read_parquet(snapshot / 'validation.parquet')
            movies = pd.read_parquet(snapshot / 'movies.parquet')
            genres = {int(r.movieId):parse_genres(r.genres) for r in movies.itertuples()}
            vc = EvaluationContext(train,val,genres,config.validation_users,threshold=config.threshold)
            trials = []
            def trial(family, parameters, factory):
                path = run / 'trials' / (_trial_id(family,parameters)+'.json')
                if reusable(path):
                    result = read_json(path)
                    if result['status'] != 'complete':
                        raise ValueError('Trial lỗi cần một run mới sau khi sửa nguyên nhân')
                else:
                    checkpoint('validation/' + _trial_id(family,parameters))
                    started = time.monotonic()
                    result = {'family':family,'parameters':parameters,'status':'running'}
                    try:
                        model = factory()
                        summary, _ = evaluate_ranker(model,vc,family,k=config.k,check=monitor.check)
                        result.update(status='complete',ndcg=summary['ndcg'],duration_seconds=time.monotonic()-started)
                    except Exception as error:
                        result.update(status='failed',error_type=type(error).__name__)
                        write_json(path,result)
                        raise
                    write_json(path,result)
                trials.append(result)
                return result
            selection_path = run / 'selection.json'
            if reusable(selection_path):
                selection = read_json(selection_path)
            else:
                for mode,name in [('count','MostPopular'),('bayesian','BayesianItemMean')]:
                    trial(name,{},lambda mode=mode:ItemStatistics(mode).fit(train))
                trial('GenreContent',{},lambda:GenreContent(movies).fit(train))
                for params in config.search.svd:
                    trial('BiasedSVD',list(params),lambda params=params:_svd(params,config.seeds[0]).fit(train))
                    gc.collect()
                for params in config.search.knn:
                    trial('SparseItemKNN',list(params),lambda params=params:SparseItemKNN(*params,check=monitor.check).fit(train))
                    gc.collect()
                best_svd = max([t for t in trials if t['family']=='BiasedSVD'],key=lambda t:t['ndcg'])
                best_knn = max([t for t in trials if t['family']=='SparseItemKNN'],key=lambda t:t['ndcg'])
                fitted_svd = _svd(best_svd['parameters'],config.seeds[0]).fit(train)
                content = GenreContent(movies).fit(train)
                pop = ItemStatistics().fit(train)
                cached = MemoizedScores(fitted_svd)
                for tau in config.search.tau:
                    for beta in config.search.beta:
                        trial('AdaptiveHybrid',{'tau':tau,'beta':beta},
                              lambda tau=tau,beta=beta:HybridRanker(cached,content,pop,vc.counts,tau,beta))
                hybrid_trial = max([t for t in trials if t['family']=='AdaptiveHybrid'],key=lambda t:t['ndcg'])
                hybrid = HybridRanker(cached,content,pop,vc.counts,**hybrid_trial['parameters'])
                mmrs = []
                for weight in config.search.mmr:
                    checkpoint('validation/MMR/' + str(weight))
                    metric, _ = evaluate_ranker(hybrid,vc,'MMR',k=config.k,mmr=weight,check=monitor.check)
                    mmrs.append({'weight':weight,'ndcg':metric['ndcg'],'diversity':metric['diversity']})
                baseline = max([t for t in trials if t['family']!='AdaptiveHybrid'],key=lambda t:t['ndcg'])
                selection = {'frozen_at':utc_now(),'criterion':'validation_macro_ndcg_at_10',
                             'svd':best_svd['parameters'],'knn':best_knn['parameters'],
                             'hybrid':hybrid_trial['parameters'],'mmr_weight':max(mmrs,key=lambda t:t['ndcg'])['weight'],
                             'mmr_validation':mmrs,'primary_baseline':baseline['family'],'trials':trials,
                             'test_opened_before_freeze':False}
                write_json(selection_path,selection)
                del fitted_svd,content,pop,cached,hybrid
                gc.collect()
            checkpoint('configuration_frozen_before_test')
            # TEST chỉ được đọc sau khi selection đã ghi bền vững.
            test = pd.read_parquet(snapshot / 'test.parquet')
            fit = pd.concat([train,val],ignore_index=True)
            tc = EvaluationContext(fit,test,genres,config.ranking_users,threshold=config.threshold)
            manifest['evaluation_users_sha256'] = identity(tc.users)
            manifest['split_hashes'] = {n:data['files'][n+'.parquet'] for n in ['train','validation','test']}
            summaries = {}
            def final(name, seed, factory, mmr=0, measured_fit_seconds=None):
                label = name + (f'/seed={seed}' if seed is not None else '')
                directory = run / 'models' / label.replace('/','_')
                directory.mkdir(parents=True, exist_ok=True)
                output = directory / 'metrics.json'
                rows_path = directory / 'per_user.parquet'
                if reusable(output) and reusable(rows_path):
                    summaries[label] = read_json(output)
                    return
                checkpoint('test/' + label)
                started = time.monotonic()
                model = factory()
                fitted_in = time.monotonic()-started if measured_fit_seconds is None else measured_fit_seconds
                metrics, rows = evaluate_ranker(model,tc,name,seed,k=config.k,mmr=mmr,check=monitor.check)
                metrics['rating'] = rating_evaluation(model,fit,test,monitor.check)
                metrics.update(model=name,seed=seed,fit_seconds=fitted_in)
                temporary = rows_path.with_suffix('.tmp.parquet')
                rows.to_parquet(temporary,index=False)
                temporary.replace(rows_path)
                write_json(output,metrics)
                summaries[label] = metrics
            for mode,name in [('mean','GlobalMean'),('bias','RegularizedBias'),('count','MostPopular'),('bayesian','BayesianItemMean')]:
                final(name,None,lambda mode=mode:ItemStatistics(mode).fit(fit))
            content = GenreContent(movies).fit(fit)
            pop = ItemStatistics().fit(fit)
            final('GenreContent',None,lambda:content)
            final('SparseItemKNN',None,lambda:SparseItemKNN(*selection['knn'],check=monitor.check).fit(fit))
            for seed in config.seeds:
                checkpoint(f'fit/SVD/seed={seed}')
                started=time.monotonic()
                svd = _svd(selection['svd'],seed).fit(fit)
                fit_seconds=time.monotonic()-started
                final('BiasedSVD',seed,lambda:svd,measured_fit_seconds=fit_seconds)
                cached=MemoizedScores(svd)
                params=selection['hybrid']
                for name,mode,beta in [('SVDSharedFallback','svd_fallback',0),('FixedHybrid','fixed',params['beta']),
                                       ('AdaptiveWithoutGenre','adaptive',0),('AdaptiveHybrid','adaptive',params['beta'])]:
                    final(name,seed,lambda mode=mode,beta=beta:HybridRanker(cached,content,pop,tc.counts,params['tau'],beta,mode))
                final('AdaptiveMMR',seed,lambda:HybridRanker(cached,content,pop,tc.counts,**params),selection['mmr_weight'])
                del svd,cached
                gc.collect()
            checkpoint('paired_statistics')
            frames = [pd.read_parquet(p) for p in sorted((run/'models').glob('*/per_user.parquet'))]
            rows=pd.concat(frames,ignore_index=True)
            rows.to_parquet(run/'per_user_metrics.parquet',index=False)
            comparisons=paired_comparison(rows,'AdaptiveHybrid',selection['primary_baseline'],resamples=config.bootstrap_samples)
            write_json(run/'comparisons.json',comparisons)
            from src.evaluation.statistics import model_intervals
            write_json(run/'intervals.json',model_intervals(rows,resamples=config.bootstrap_samples).to_dict('records'))
            write_json(run/'ablations.json',[{**paired_comparison(rows,'AdaptiveHybrid',baseline,resamples=config.bootstrap_samples),
                                             'claim_type':'exploratory_no_multiple_testing_correction'}
                                            for baseline in ['BiasedSVD','SVDSharedFallback','FixedHybrid','AdaptiveWithoutGenre']])
            families={}
            for name in sorted({m['model'] for m in summaries.values()}):
                entries=[m for m in summaries.values() if m['model']==name]
                metrics={m:float(np.mean([e[m] for e in entries])) for m in ['ndcg','precision','recall','hit_rate','coverage','diversity','novelty']}
                metrics['ndcg_std_across_seeds']=float(np.std([e['ndcg'] for e in entries],ddof=1)) if len(entries)>1 else None
                metrics['RMSE']=float(np.mean([e['rating']['RMSE'] for e in entries])) if entries[0]['rating'] else None
                metrics['MAE']=float(np.mean([e['rating']['MAE'] for e in entries])) if entries[0]['rating'] else None
                families[name]=metrics
            write_json(run/'metrics.json',{'families':families,'entries':summaries})
            pd.DataFrame([{'model':name,**metrics} for name,metrics in families.items()]).to_csv(run/'summary.csv',index=False)
            (run/'model_card.md').write_text(
                '# MovieRS: benchmark hồi cứu\n\n'+comparisons['interpretation']+'\n\n'
                'Primary comparator chọn bằng VAL trước TEST. CI theo user, có điều kiện trên snapshot.\n'
                'Không đo hài lòng thực tế, không dùng phản hồi app. Không tự triển khai mô hình từ kết quả TEST.\n',encoding='utf-8')
            manifest.update(status='complete',completed_at=utc_now(),stage='complete')
    except BaseException as error:
        manifest.update(status='cancelled' if isinstance(error,KeyboardInterrupt) else 'failed',error_type=type(error).__name__)
        raise
    finally:
        write_json(run/'resource_usage.json',monitor.report())
        manifest['files']={str(p.relative_to(run)):sha256(p) for p in run.rglob('*') if p.is_file() and p.name!='manifest.json' and '.tmp' not in p.name}
        write_json(run/'manifest.json',manifest)
        lock.unlink(missing_ok=True)
    return run
