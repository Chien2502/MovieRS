"""Gate ranking và rollback nguyên tử trên gói phục vụ tạm."""

import joblib
import pytest

from api.services.serving import load_bundle
from src.experiments.artifacts import sha256,write_json
from src.pipeline.worker import promotion_gate,rollback


def metrics(ndcg=.2,rmse=.9,latency=10):
    return {'ndcg':ndcg,'latency_ms':{'p95':latency},'cohorts':{'cold_0':{'ndcg':ndcg}},'rating':{'RMSE':rmse}}


def test_gate_requires_ranking_and_guardrails():
    assert promotion_gate(metrics(.21),metrics(.2))
    assert not promotion_gate(metrics(.19),metrics(.2))
    assert not promotion_gate(metrics(float('nan')))
    assert not promotion_gate(metrics(.21,1),metrics(.2,.9))
    assert not promotion_gate(metrics(.21,latency=1000),metrics())
    assert not promotion_gate(metrics(.21,latency=float('nan')),metrics())
    assert not promotion_gate({'ndcg':.2})


def test_bundle_integrity_and_rollback(tmp_path):
    folder=tmp_path/'model_old';folder.mkdir()
    joblib.dump({'model':'fixture'},folder/'model.joblib')
    write_json(folder/'manifest.json',{'status':'ready','files':{'model.joblib':sha256(folder/'model.joblib')}})
    rollback(tmp_path,'model_old')
    assert load_bundle(tmp_path/'current.json')[0]['model']=='fixture'
    (folder/'model.joblib').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):load_bundle(tmp_path/'current.json')
    with pytest.raises(ValueError):rollback(tmp_path,'../outside')
