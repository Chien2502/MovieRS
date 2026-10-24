"""Kiểm chứng giao thức V2 trên fixture nhỏ, không sửa raw/model vận hành."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.snapshots import load_snapshot, ordered_users, prepare_snapshot
from src.evaluation.protocol import EvaluationContext, evaluate_ranker, select_topk
from src.evaluation.statistics import paired_comparison
from src.experiments.config import load_config
from src.experiments.runner import run_experiment
from src.models.research import GenreContent, HybridRanker, ItemStatistics, SparseItemKNN


@pytest.fixture
def research_fixture(tmp_path):
    source=tmp_path/'raw'
    source.mkdir()
    movies=pd.DataFrame({'movieId':range(1,7),'title':[f'Phim {i}' for i in range(1,7)],
                         'genres':['Drama','Action','Drama','Comedy','Action','Drama']})
    movies.to_csv(source/'movies.csv',index=False)
    rows=[]
    for uid in range(1,13):
        for mid in range(1,7):
            rows.append((uid,mid,4 if (uid+mid)%3 else 2,mid*100+uid))
    pd.DataFrame(rows,columns=['userId','movieId','rating','timestamp']).to_csv(source/'ratings.csv',index=False)
    conf=load_config().model_dump(mode='json')
    conf.update(source_dir=str(source),snapshot_dir=str(tmp_path/'snapshots'),run_dir=str(tmp_path/'runs'),
                expected_source_sha256=None,expected_archive_md5=None,t1='1970-01-01T00:05:50Z',
                t2='1970-01-01T00:09:10Z',ranking_users=20,validation_users=20,seeds=[42,43],bootstrap_samples=100,
                chunk_rows=7,profiles={'test':{'users':10,'minutes':3}},
                resources={'max_rss_gib':2,'min_available_gib':0,'threads':1},
                search={'svd':[[3,2,.05]],'knn':[[2,10]],'tau':[5], 'beta':[0,.5],'mmr':[0,.1]})
    from src.experiments.config import ResearchConfig
    return ResearchConfig.model_validate(conf)


def test_config_rejects_unknown_secret_fields_and_invalid_protocol():
    from pydantic import ValidationError
    from src.experiments.config import ResearchConfig
    data=load_config().model_dump(mode='json')
    data['database_password']='must-never-be-accepted'
    with pytest.raises(ValidationError): ResearchConfig.model_validate(data)
    data.pop('database_password')
    data['t2']=data['t1']
    with pytest.raises(ValidationError): ResearchConfig.model_validate(data)


def test_snapshot_preserves_history_and_rejects_corruption(research_fixture):
    config=research_fixture
    folder=prepare_snapshot(config,'test')
    manifest=load_snapshot(folder)
    sample=pd.read_parquet(folder/'ratings.parquet')
    source=pd.read_csv(config.path(config.source_dir)/'ratings.csv')
    ids=ordered_users(source.userId,config.sample_seed)[:10]
    assert len(sample)==60
    assert set(sample.userId)==set(ids)
    assert sample.groupby('userId').size().eq(6).all()
    assert prepare_snapshot(config,'test')==folder
    assert manifest['splits']['train']['max_epoch']<manifest['splits']['validation']['min_epoch']
    (folder/'quality.json').write_text('{}')
    with pytest.raises(ValueError,match='checksum'):load_snapshot(folder)


def test_unavailable_positives_and_all_unservable_user_are_counted():
    fit=pd.DataFrame({'userId':[1,2,6],'movieId':[1,2,2],'rating':[4,5,4]})
    test=pd.DataFrame({'userId':[3,4,4],'movieId':[999,2,888],'rating':[5,5,5]})
    context=EvaluationContext(fit,test,{})
    metrics,rows=evaluate_ranker(ItemStatistics('count').fit(fit),context,'count',k=1)
    assert set(rows.user_id)=={3,4}
    assert rows.set_index('user_id').loc[3,'ndcg']==0
    assert rows.set_index('user_id').loc[4,'recall']==.5
    assert metrics['unavailable_positive_fraction']==pytest.approx(2/3)
    assert metrics['users']==2


def test_model_features_do_not_change_when_future_labels_change():
    fit=pd.DataFrame({'userId':[1,1,2,2],'movieId':[1,2,2,3],'rating':[4,2,5,4]})
    movies=pd.DataFrame({'movieId':[1,2,3],'genres':['Drama','Action','Drama']})
    for factory in [lambda:ItemStatistics('bias'),lambda:GenreContent(movies),lambda:SparseItemKNN(2,10)]:
        model=factory().fit(fit)
        before=model.score_items(1,[2,3])
        future=pd.DataFrame({'userId':[1],'movieId':[3],'rating':[5]})
        EvaluationContext(fit,future,{})
        future['rating']=.5
        assert model.score_items(1,[2,3])==pytest.approx(before)


def test_shuffled_source_keeps_identical_selected_histories(research_fixture):
    from src.experiments.artifacts import sha256
    config=research_fixture
    before=prepare_snapshot(config,'test')
    source=config.path(config.source_dir)/'ratings.csv'
    frame=pd.read_csv(source)
    frame.sample(frac=1,random_state=3).to_csv(source,index=False)
    after=prepare_snapshot(config,'test')
    assert before!=after  # Lineage file nguồn đổi, nội dung sample canonical giữ nguyên.
    assert sha256(before/'ratings.parquet')==sha256(after/'ratings.parquet')


def test_paired_ci_averages_seeds_and_rejects_missing_users():
    frame=pd.DataFrame([{'model':m,'seed':s,'user_id':u,'ndcg':value}
                        for m,seeds,value in [('proposal',[42,43],.4),('base',[None],.2)]
                        for s in seeds for u in [1,2,3]])
    result=paired_comparison(frame,'proposal','base',resamples=100)
    assert result['users']==3
    assert result['delta']==pytest.approx(.2)
    assert result['improvement_supported']
    with pytest.raises(ValueError):paired_comparison(frame.drop(index=0),'proposal','base',resamples=100)


def test_ranking_tie_break_and_nonfinite_rejection():
    assert select_topk([9,3,5],[1,1,1],2,{})==[3,5]
    with pytest.raises(ValueError):select_topk([1],[np.nan],1,{})


def test_model_serialization_preserves_scores(tmp_path):
    fit=pd.DataFrame({'userId':[1,1,2,2],'movieId':[1,2,2,3],'rating':[4.,2.,5.,4.]})
    movies=pd.DataFrame({'movieId':[1,2,3],'genres':['Drama','Action','Drama']})
    for model in [ItemStatistics().fit(fit),GenreContent(movies).fit(fit),SparseItemKNN(2).fit(fit)]:
        expected=model.score_items(1,[1,2,3])
        path=tmp_path/(type(model).__name__+'.joblib')
        model.save(path)
        actual=type(model).load(path)
        assert actual.score_items(1,[1,2,3])==pytest.approx(expected)


def test_complete_run_freezes_config_before_test_and_can_resume(research_fixture):
    snapshot=prepare_snapshot(research_fixture,'test')
    run=run_experiment(research_fixture,snapshot,'test')
    manifest=json.loads((run/'manifest.json').read_text())
    selection=json.loads((run/'selection.json').read_text())
    assert manifest['status']=='complete'
    assert selection['test_opened_before_freeze'] is False
    assert selection['frozen_at']<manifest['completed_at']
    metrics=json.loads((run/'metrics.json').read_text())['families']
    assert metrics['GenreContent']['RMSE'] is None
    assert metrics['BiasedSVD']['RMSE'] is not None
    assert (run/'per_user_metrics.parquet').exists()
    assert (run/'comparisons.json').exists()
    import zipfile
    import hashlib
    with zipfile.ZipFile(run/'source_code.zip') as archive:
        for name,expected in manifest['provenance']['source_sha256'].items():
            assert hashlib.sha256(archive.read(Path(name).as_posix())).hexdigest()==expected
    # Resume hoàn tất cần xác thực hash, triển khai loader dashboard dùng cùng contract.
    from src.experiments.artifacts import verify_files
    verify_files(run,manifest)
    assert run_experiment(research_fixture,snapshot,'test',resume=run)==run
    # Đổi toàn bộ nhãn TEST để run mới không còn positive: selection phải vẫn giữ nguyên.
    source=research_fixture.path(research_fixture.source_dir)/'ratings.csv'
    original=pd.read_csv(source)
    original['rating']=original.rating.astype(float)
    original.loc[original.timestamp>=int(research_fixture.t2.timestamp()),'rating']=.5
    original.to_csv(source,index=False)
    modified=prepare_snapshot(research_fixture,'test')
    with pytest.raises(ValueError,match='positive'):
        run_experiment(research_fixture,modified,'test')
    latest=sorted(research_fixture.path(research_fixture.run_dir).glob('*/selection.json'))[-1]
    after=json.loads(latest.read_text(encoding='utf-8'))
    for key in ['svd','knn','hybrid','mmr_weight','primary_baseline']:
        assert after[key]==selection[key]


def test_watchdog_can_stop_a_noncooperative_worker(research_fixture):
    import sys,time
    from src.experiments.resources import BudgetExceeded,supervise
    research_fixture.profiles['test'].minutes=.001
    started=time.monotonic()
    with pytest.raises(BudgetExceeded):
        supervise([sys.executable,'-c','import time;time.sleep(10)'],research_fixture,'test')
    assert time.monotonic()-started<4


def test_resume_rejects_corrupted_incomplete_checkpoint(research_fixture,monkeypatch):
    import src.experiments.runner as runner
    snapshot=prepare_snapshot(research_fixture,'test')
    original=runner.evaluate_ranker
    calls=0
    def stop(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2:raise RuntimeError('Dừng sau trial đầu để kiểm tra checkpoint')
        return original(*args,**kwargs)
    monkeypatch.setattr(runner,'evaluate_ranker',stop)
    with pytest.raises(RuntimeError):run_experiment(research_fixture,snapshot,'test')
    folder=next(research_fixture.path(research_fixture.run_dir).glob('run_*'))
    trial=next((folder/'trials').glob('*.json'))
    trial.write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError):run_experiment(research_fixture,snapshot,'test',resume=folder)


def test_watchdog_records_windows_launcher_descendant_failure(research_fixture,tmp_path):
    import sys
    from src.experiments.resources import BudgetExceeded,supervise
    research_fixture.profiles['test'].minutes=.02
    folder=research_fixture.path(research_fixture.run_dir)/'worker_fixture'
    folder.mkdir(parents=True)
    script=tmp_path/'worker.py'
    script.write_text('import json,os,sys,time\nfrom pathlib import Path\n'
                      'Path(sys.argv[1]).write_text(json.dumps({"worker_pid":os.getpid(),"status":"running"}))\n'
                      'time.sleep(20)\n')
    with pytest.raises(BudgetExceeded):
        supervise([sys.executable,str(script),str(folder/'manifest.json')],research_fixture,'test')
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status']=='failed'
    assert manifest['watchdog']['reason']
