"""
watch_store.py — Lưu trữ tiến độ xem phim (Watch Progress) của người dùng

Dữ liệu nằm tại data/processed/watch_progress.csv (userId, movieId,
position_seconds, duration_seconds, ratio, status, updated_at).

Quy ước:
  - status = "in_progress": đang xem dở (5% <= ratio < 95%) → hiện trong hàng
    "Tiếp tục xem" của app.
  - status = "finished": xem xong (ratio >= 95%) → ẩn khỏi hàng "Tiếp tục xem",
    được quy đổi thành tín hiệu watch hoàn thành (rating 5.0) trong vòng feedback.
  - Upsert theo cặp (userId, movieId): mỗi heartbeat mới nhất ghi đè bản cũ.
  - Ghi file an toàn: threading.Lock + ghi tạm rồi rename (atomic) để tránh hỏng
    file khi nhiều heartbeat gửi đồng thời.
"""

import threading
from datetime import datetime
from pathlib import Path
import pandas as pd

from api.logging_config import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WATCH_PROGRESS_CSV = PROJECT_ROOT / "data" / "processed" / "watch_progress.csv"

# Ngưỡng xác định trạng thái
FINISH_RATIO = 0.95   # Xem >= 95% coi là xem xong
MIN_TRACK_RATIO = 0.05  # Xem dưới 5% không đáng hiện trong "Tiếp tục xem"

_lock = threading.Lock()

COLUMNS = ["userId", "movieId", "position_seconds", "duration_seconds",
           "ratio", "status", "updated_at"]


def _read_all() -> pd.DataFrame:
    """Đọc toàn bộ watch_progress.csv (trả DataFrame rỗng nếu chưa có)."""
    if not WATCH_PROGRESS_CSV.exists() or WATCH_PROGRESS_CSV.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    try:
        return pd.read_csv(WATCH_PROGRESS_CSV)
    except Exception as e:
        logger.warning(f"[⚠] Không đọc được watch_progress.csv: {e}")
        return pd.DataFrame(columns=COLUMNS)


def _write_all(df: pd.DataFrame):
    """Ghi atomic: ghi file tạm rồi rename lên file chính."""
    WATCH_PROGRESS_CSV.parent.mkdir(parents=True, exist_ok=True)
    tmp = WATCH_PROGRESS_CSV.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(WATCH_PROGRESS_CSV)


def upsert_progress(user_id: int, movie_id: int, position_seconds: int,
                    duration_seconds: int) -> dict:
    """Ghi/ghi đè tiến độ xem của user cho một phim.

    Trả về dict {ratio, status, finished} — finished=True khi vừa xem xong
    (ratio >= 95%) trong lần ghi này.
    """
    position = max(0, int(position_seconds))
    duration = max(1, int(duration_seconds))
    position = min(position, duration)
    ratio = position / duration
    status = "finished" if ratio >= FINISH_RATIO else "in_progress"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _lock:
        df = _read_all()
        mask = (df["userId"] == user_id) & (df["movieId"] == movie_id)
        row = {
            "userId": user_id,
            "movieId": movie_id,
            "position_seconds": position,
            "duration_seconds": duration,
            "ratio": round(ratio, 4),
            "status": status,
            "updated_at": now,
        }
        if mask.any():
            # Gán từng cột (gán cả dict qua .loc[mask] gây lỗi dtype trong pandas 2.x)
            for col in COLUMNS:
                df.loc[mask, col] = row[col]
        else:
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        _write_all(df)

    return {"ratio": ratio, "status": status, "finished": status == "finished"}


def get_progress(user_id: int) -> list[dict]:
    """Danh sách phim đang xem dở của user (hàng "Tiếp tục xem").

    Điều kiện: status = in_progress và 5% <= ratio < 95%, sắp xếp theo
    updated_at giảm dần (phim xem gần nhất đứng đầu).
    """
    df = _read_all()
    if df.empty or "userId" not in df.columns:
        return []
    df = df[df["userId"] == user_id]
    if df.empty:
        return []
    df = df[
        (df["status"] == "in_progress")
        & (df["ratio"] >= MIN_TRACK_RATIO)
        & (df["ratio"] < FINISH_RATIO)
    ]
    df = df.sort_values("updated_at", ascending=False)
    return df.to_dict("records")


def get_progress_for_movie(user_id: int, movie_id: int) -> dict | None:
    """Tiến độ xem của 1 phim cụ thể (dùng để resume đúng vị trí)."""
    df = _read_all()
    if df.empty:
        return None
    row = df[(df["userId"] == user_id) & (df["movieId"] == movie_id)]
    if row.empty:
        return None
    return row.iloc[0].to_dict()


def remove_progress(user_id: int, movie_id: int) -> bool:
    """Xoá tiến độ xem của 1 phim (người dùng tự bỏ khỏi "Tiếp tục xem")."""
    with _lock:
        df = _read_all()
        before = len(df)
        df = df[~((df["userId"] == user_id) & (df["movieId"] == movie_id))]
        if len(df) != before:
            _write_all(df)
            return True
    return False
