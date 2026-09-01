"""
watch_store.py — Lưu trữ tiến độ xem phim (Watch Progress) của người dùng

Dữ liệu nằm tại data/moviers.db bảng watch_progress.
"""

from datetime import datetime

from api.logging_config import get_logger
from api.services.database import get_db

logger = get_logger(__name__)

# Ngưỡng xác định trạng thái
FINISH_RATIO = 0.95   # Xem >= 95% coi là xem xong
MIN_TRACK_RATIO = 0.05  # Xem dưới 5% không đáng hiện trong "Tiếp tục xem"


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

    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        INSERT OR REPLACE INTO watch_progress (user_id, movie_id, position_seconds, duration_seconds, ratio, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, movie_id, position, duration, round(ratio, 4), status, now)
    )
    conn.commit()

    return {"ratio": ratio, "status": status, "finished": status == "finished"}


def get_progress(user_id: int) -> list[dict]:
    """Danh sách phim đang xem dở của user (hàng "Tiếp tục xem").

    Điều kiện: status = in_progress và 5% <= ratio < 95%, sắp xếp theo
    updated_at giảm dần (phim xem gần nhất đứng đầu).
    """
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, movie_id, position_seconds, duration_seconds, ratio, status, updated_at
        FROM watch_progress
        WHERE user_id = ? AND status = 'in_progress' AND ratio >= ? AND ratio < ?
        ORDER BY updated_at DESC
        """,
        (user_id, MIN_TRACK_RATIO, FINISH_RATIO)
    )
    rows = c.fetchall()
    
    # Map to dict keys expected by caller: userId, movieId
    return [
        {
            "userId": r[0],
            "movieId": r[1],
            "position_seconds": r[2],
            "duration_seconds": r[3],
            "ratio": r[4],
            "status": r[5],
            "updated_at": r[6]
        }
        for r in rows
    ]


def get_progress_for_movie(user_id: int, movie_id: int) -> dict | None:
    """Tiến độ xem của 1 phim cụ thể (dùng để resume đúng vị trí)."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT user_id, movie_id, position_seconds, duration_seconds, ratio, status, updated_at
        FROM watch_progress
        WHERE user_id = ? AND movie_id = ?
        """,
        (user_id, movie_id)
    )
    r = c.fetchone()
    if r is None:
        return None
    return {
        "userId": r[0],
        "movieId": r[1],
        "position_seconds": r[2],
        "duration_seconds": r[3],
        "ratio": r[4],
        "status": r[5],
        "updated_at": r[6]
    }


def remove_progress(user_id: int, movie_id: int) -> bool:
    """Xoá tiến độ xem của 1 phim (người dùng tự bỏ khỏi "Tiếp tục xem")."""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM watch_progress WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
    changes = c.rowcount
    conn.commit()
    return changes > 0
