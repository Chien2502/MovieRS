"""Tạo TRAIN vận hành bằng dữ liệu lịch sử và phản hồi, không tái chia holdout.

Thực nghiệm học thuật luôn đọc ratings_processed.csv, không đọc TRAIN vận hành.
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from api.services.feedback_store import read_feedback
from src.data.protocol import normalize_ratings, temporal_split

PROCESSED_DIR = PROJECT_ROOT / 'data/processed'
RATINGS_PROCESSED_CSV = PROCESSED_DIR / 'ratings_processed.csv'


def build_runtime_data():
    """Holdout chỉ từ lịch sử; tài khoản app thuộc miền ID riêng >=200000."""
    base = pd.read_csv(RATINGS_PROCESSED_CSV)
    train, val, test = temporal_split(base)
    feedback = read_feedback()
    if not feedback.empty:
        if (feedback.userId < 200000).any():
            raise ValueError('Phản hồi ứng dụng trùng miền ID MovieLens; cần kiểm tra trước khi retrain')
        latest = feedback.drop_duplicates(['userId', 'movieId'], keep='last')
        latest = normalize_ratings(latest)
        train = pd.concat([train, latest], ignore_index=True)
    return train, val, test


def merge_and_split(verbose=True):
    """Tương thích CLI cũ; chỉ ghi TRAIN, giữ nguyên CSV validation/test hiện có."""
    train, val, test = build_runtime_data()
    target = PROCESSED_DIR / 'ratings_train.csv'
    temporary = target.with_suffix('.csv.tmp')
    train.to_csv(temporary, index=False)
    temporary.replace(target)
    result = {'train': len(train), 'val': len(val), 'test': len(test)}
    if verbose:
        print(f'TRAIN vận hành đã cập nhật: {result}; holdout CSV không bị ghi lại')
    return result


if __name__ == '__main__':
    merge_and_split()
