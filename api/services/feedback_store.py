"""Lưu phản hồi có nguồn gốc; đánh giá chủ động ưu tiên hơn tín hiệu mô phỏng."""

import threading
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from api.repositories import postgres_enabled, repository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTERACTIONS_LOG_CSV = PROJECT_ROOT / "data/processed/interactions_log.csv"
COLUMNS = ["userId", "movieId", "rating", "timestamp", "source"]
PRIORITY = {"legacy_unknown": 3, "explicit": 3, "favorite": 2, "watch": 1, "watch_complete": 1}
_lock = threading.RLock()


def read_feedback(user_id=None) -> pd.DataFrame:
    """Bản ghi cũ không có source được giữ nguyên, không giả định là sao chủ động."""
    if postgres_enabled():return repository().feedback(user_id)
    with _lock:
        if not INTERACTIONS_LOG_CSV.exists() or INTERACTIONS_LOG_CSV.stat().st_size == 0:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.read_csv(INTERACTIONS_LOG_CSV)
        if "source" not in df:
            df["source"] = "legacy_unknown"
        df["source"] = df["source"].fillna("legacy_unknown")
        df['timestamp'] = df['timestamp'].astype(str)
        df['rating'] = df['rating'].astype(float)
        return df if user_id is None else df[df.userId==user_id]


def write_feedback(user_id: int, movie_id: int, rating: float, source="explicit",idempotency_key=None) -> bool:
    """Upsert atomic trong một tiến trình; trả False khi trùng hoặc có nguồn mạnh hơn."""
    if postgres_enabled():return repository().write_feedback(user_id,movie_id,rating,source,idempotency_key)
    from api.idempotency import file_operation
    with file_operation(user_id,idempotency_key,['feedback',movie_id,float(rating),source]) as replayed:
        return False if replayed else _write_file_feedback(user_id,movie_id,rating,source)


def _write_file_feedback(user_id,movie_id,rating,source):
    if source not in PRIORITY or not 0.5 <= rating <= 5:
        raise ValueError("Nguồn hoặc điểm phản hồi không hợp lệ")
    with _lock:
        df = read_feedback()
        mask = (df.userId == user_id) & (df.movieId == movie_id)
        if mask.any():
            old = df.loc[mask].iloc[-1]
            if PRIORITY.get(old.source, 3) > PRIORITY[source]:
                return False
            if old.source == source and float(old.rating) == float(rating):
                return False
        row = {"userId": user_id, "movieId": movie_id, "rating": float(rating),
               "timestamp": datetime.now(timezone.utc).isoformat(), "source": source}
        if mask.any():
            for column, value in row.items():
                df.loc[mask, column] = value
        else:
            df = pd.DataFrame([row]) if df.empty else pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        INTERACTIONS_LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
        tmp = INTERACTIONS_LOG_CSV.with_suffix(".csv.tmp")
        df.to_csv(tmp, index=False)
        tmp.replace(INTERACTIONS_LOG_CSV)
        return True


def remove_favorite_feedback(user_id: int, movie_id: int) -> bool:
    """Bỏ lưu phim không có nghĩa ghét phim; chỉ rút tín hiệu favorite trước đó."""
    if postgres_enabled():return repository().remove_favorite_feedback(user_id,movie_id)
    with _lock:
        df = read_feedback()
        mask = (df.userId == user_id) & (df.movieId == movie_id) & (df.source == "favorite")
        if not mask.any():
            return False
        tmp = INTERACTIONS_LOG_CSV.with_suffix(".csv.tmp")
        df.loc[~mask].to_csv(tmp, index=False)
        tmp.replace(INTERACTIONS_LOG_CSV)
        return True
