"""Retrain vận hành; so sánh hai mô hình trên chính cùng validation hiện tại."""

import os
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.merge_interactions import build_runtime_data
from src.data.protocol import frame_fingerprint
from src.models.svd_surprise import SurpriseSVDRecommender
from src.pipeline.registry import write_metadata

MODEL_DIR = PROJECT_ROOT / 'models'
_retrain_lock = threading.Lock()


def promotion_decision(new_metrics, incumbent_metrics=None, tolerance=0.0):
    """Fail closed nếu thiếu/NaN validation; không so với số RMSE lịch sử khác tập."""
    new = (new_metrics or {}).get('RMSE')
    if new is None or not np.isfinite(new) or tolerance < 0:
        return False
    if incumbent_metrics is None:
        return True
    old = incumbent_metrics.get('RMSE')
    return old is not None and np.isfinite(old) and new <= old + tolerance


def run_retrain():
    """Huấn luyện vào phiên bản riêng; chỉ cập nhật artifacts khi vượt gate."""
    if not _retrain_lock.acquire(blocking=False):
        return {'success': False, 'promoted': False, 'new_rmse': None, 'train_rows': 0,
                'duration_s': 0.0, 'version': None, 'reason': 'Đang có một lượt retrain'}
    started = time.monotonic()
    try:
        train, val, _ = build_runtime_data()
        if val.empty:
            raise ValueError('Không có validation; dừng retrain')
        params = {'n_factors': int(os.getenv('SVD_N_FACTORS', '50')),
                  'lr_all': float(os.getenv('SVD_LR_ALL', '0.005')),
                  'reg_all': float(os.getenv('SVD_REG_ALL', '0.05')),
                  'n_epochs': int(os.getenv('SVD_N_EPOCHS', '20')), 'random_state': 42}
        model = SurpriseSVDRecommender(**params).fit(train)
        new_metrics = model.evaluate_test(val)
        latest = MODEL_DIR / 'model_latest.pkl'
        incumbent = SurpriseSVDRecommender.load(latest) if latest.exists() else None
        incumbent_metrics = incumbent.evaluate_test(val) if incumbent is not None else None
        promoted = promotion_decision(new_metrics, incumbent_metrics,
                                      float(os.getenv('GATE_TOLERANCE', '0.0')))
        version = MODEL_DIR / ('model_v_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S%f') + '.pkl')
        model.save(version)
        evidence = {**new_metrics, 'val_rmse': new_metrics['RMSE'],
                    'validation_sha256': frame_fingerprint(val), 'incumbent_on_same_validation': incumbent_metrics,
                    'protocol': 'runtime_gate_not_academic_benchmark'}
        write_metadata(version, evidence, params, promoted, train_rows=len(train))
        reloaded = False
        if promoted:
            temporary = latest.with_suffix('.pkl.tmp')
            shutil.copyfile(version, temporary)
            temporary.replace(latest)
            write_metadata(version, evidence, params, True, train_rows=len(train),
                           save_path=MODEL_DIR / 'model_latest.json')
            # Không sửa split CSV sau gate thất bại; model.trainset là nguồn lịch sử vận hành.
            temporary_train = PROJECT_ROOT / 'data/processed/ratings_train.csv.tmp'
            train.to_csv(temporary_train, index=False)
            temporary_train.replace(temporary_train.with_suffix(''))
            host = os.getenv('API_HOST', 'localhost')
            host = 'localhost' if host == '0.0.0.0' else host
            url = f"http://{host}:{int(os.getenv('API_PORT', '8000'))}/api/recommendations/reload"
            try:
                reloaded = requests.post(url, timeout=60,headers={'X-Admin-Token':os.getenv('ADMIN_API_TOKEN','')}).status_code == 200
            except requests.RequestException:
                pass
        return {'success': True, 'promoted': promoted, 'new_rmse': new_metrics['RMSE'],
                'train_rows': len(train), 'duration_s': round(time.monotonic() - started, 2),
                'version': version.name, 'api_reloaded': reloaded}
    finally:
        _retrain_lock.release()


if __name__ == '__main__':
    print(run_retrain())
