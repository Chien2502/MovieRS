"""Chạy thật luồng gate và publish trên tệp tạm, không train mô hình lớn."""

import json

import pandas as pd
import pytest

import src.pipeline.retrain as retrain


@pytest.mark.parametrize('new_rmse,promoted', [(1.1, False), (0.8, True)])
def test_retrain_scores_incumbent_on_same_holdout_and_protects_live_model(tmp_path, monkeypatch, new_rmse, promoted):
    model_dir = tmp_path / 'models'
    model_dir.mkdir()
    latest = model_dir / 'model_latest.pkl'
    latest.write_bytes(b'incumbent')
    (tmp_path / 'data/processed').mkdir(parents=True)
    train = pd.DataFrame({'userId': [1], 'movieId': [1], 'rating': [4], 'timestamp': ['2000-01-01']})
    val = pd.DataFrame({'userId': [2], 'movieId': [1], 'rating': [3], 'timestamp': ['2001-01-01']})
    evaluated = []
    class Model:
        def __init__(self, old=False, **kwargs):
            self.old = old
        def fit(self, frame):
            assert frame is train
            return self
        def evaluate_test(self, frame):
            assert frame is val
            evaluated.append('incumbent' if self.old else 'candidate')
            return {'RMSE': 0.9 if self.old else new_rmse, 'MAE': 0.7}
        def save(self, path):
            path.write_bytes(b'candidate')
        @staticmethod
        def load(path):
            assert path == latest
            return Model(old=True)
    monkeypatch.setattr(retrain, 'MODEL_DIR', model_dir)
    monkeypatch.setattr(retrain, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(retrain, 'build_runtime_data', lambda: (train, val, val))
    monkeypatch.setattr(retrain, 'SurpriseSVDRecommender', Model)
    class Response:
        status_code = 200
    monkeypatch.setattr(retrain.requests, 'post', lambda *args, **kwargs: Response())
    result = retrain.run_retrain()
    assert evaluated == ['candidate', 'incumbent']
    assert result['promoted'] is promoted
    assert latest.read_bytes() == (b'candidate' if promoted else b'incumbent')
    assert (tmp_path / 'data/processed/ratings_train.csv').exists() is promoted
    metadata = json.loads(next(model_dir.glob('model_v_*.json')).read_text(encoding='utf-8'))
    assert metadata['metrics']['validation_sha256']
    assert metadata['metrics']['incumbent_on_same_validation']['RMSE'] == 0.9
