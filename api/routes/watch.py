"""
watch.py — Endpoints tiến độ xem phim (Watch Progress / Continue Watching)

Phục vụ tính năng "Tiếp tục xem" chuẩn các app streaming (FPT Play, Netflix):
  1. PUT /api/watch/progress          — Heartbeat tiến độ từ player (mỗi ~5 giây).
  2. GET  /api/watch/progress/{uid}   — Danh sách phim đang xem dở (hàng tiếp tục xem).
  3. GET  /api/watch/progress/{uid}/{mid} — Vị trí resume của 1 phim.
  4. DELETE /api/watch/progress/{uid}/{mid} — Người dùng xoá phim khỏi danh sách.

Khi heartbeat đạt ratio >= 95% → đánh dấu "finished", đồng thời quy đổi thành
tín hiệu watch hoàn thành (rating = 5.0 theo quy tắc interactions) và kích hoạt
online update để khuyến nghị cá nhân hóa ngay lập tức.
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import pandas as pd

from api.logging_config import get_logger
from api.services import watch_store
from api.services.user_store import get_user
from api.services.recommender import RecommenderService
from api.routes.interactions import _write_interaction, _invalidate_recommendation_cache

logger = get_logger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MOVIES_CSV = PROJECT_ROOT / "data" / "processed" / "movies_processed.csv"

WATCH_FINISH_RATING = 5.0  # Quy đổi "xem xong" thành rating (theo mapping watch >= 80%)


class WatchProgressRequest(BaseModel):
    user_id: int = Field(..., alias="userId", description="ID người dùng")
    movie_id: int = Field(..., alias="movieId", description="ID bộ phim")
    position_seconds: int = Field(..., ge=0, alias="positionSeconds",
                                  description="Vị trí xem hiện tại (giây)")
    duration_seconds: int = Field(..., ge=1, alias="durationSeconds",
                                  description="Tổng thời lượng phim (giây)")


def _require_user(user_id: int):
    """Chỉ user đã đăng ký mới được ghi tiến độ (nhất quán với interactions)."""
    if get_user(user_id) is None:
        raise HTTPException(status_code=404, detail="Người dùng chưa đăng ký")
    return user_id


def _enrich(rows: list[dict]) -> list[dict]:
    """Gắn thêm title/poster/genres cho từng phim trong danh sách tiến độ."""
    if not rows or not MOVIES_CSV.exists():
        return rows
    df = pd.read_csv(MOVIES_CSV).fillna("")
    result = []
    for r in rows:
        movie = df[df["movieId"] == r["movieId"]]
        if movie.empty:
            continue
        row = dict(r)
        row["title"] = movie.iloc[0]["title"]
        row["genres"] = movie.iloc[0].get("genres", "")
        row["poster_path"] = movie.iloc[0].get("poster_path", "")
        # numpy scalar phải đổi sang kiểu native để FastAPI serialize được
        runtime = movie.iloc[0].get("runtime_minutes", 100)
        if pd.notna(runtime) and str(runtime).strip() != "":
            row["runtime_minutes"] = int(runtime)
        else:
            row["runtime_minutes"] = 100
        result.append(row)
    return result


@router.put("/watch/progress")
async def save_watch_progress(req: WatchProgressRequest):
    """Ghi nhận tiến độ xem (heartbeat từ player).

    - ratio >= 95% → đánh dấu finished + quy đổi thành rating 5.0 vào vòng
      feedback + online update tức thời.
    - ratio < 95% → chỉ cập nhật vị trí để hiển thị trong "Tiếp tục xem".
    """
    _require_user(req.user_id)

    result = watch_store.upsert_progress(
        req.user_id, req.movie_id, req.position_seconds, req.duration_seconds
    )

    if result["finished"]:
        # Xem xong → chuyển thành tín hiệu huấn luyện (như interactions/watch >= 80%)
        try:
            _write_interaction(req.user_id, req.movie_id, WATCH_FINISH_RATING)
            _invalidate_recommendation_cache(req.user_id)
            RecommenderService().apply_online_update(
                req.user_id, req.movie_id, WATCH_FINISH_RATING
            )
            logger.info(
                f"[✅ Watch Finished] user {req.user_id} — movie {req.movie_id} "
                f"(ratio={result['ratio']:.2f}) → rating {WATCH_FINISH_RATING} + online update"
            )
        except Exception as e:
            logger.warning(f"[⚠] Lỗi quy đổi watch finished: {e}")

    return {
        "status": "success",
        "ratio": round(result["ratio"], 4),
        "finished": result["finished"],
    }


@router.get("/watch/progress/{user_id}")
async def get_continue_watching(user_id: int, limit: int = 20):
    """Danh sách phim đang xem dở của user (hàng "Tiếp tục xem").

    Chỉ gồm phim có 5% <= ratio < 95% (đang dở), sắp xếp theo thời gian
    xem gần nhất, tối đa `limit` phim (mặc định 20).
    """
    _require_user(user_id)
    rows = watch_store.get_progress(user_id)[:limit]
    return _enrich(rows)


@router.get("/watch/progress/{user_id}/{movie_id}")
async def get_movie_progress(user_id: int, movie_id: int):
    """Tiến độ xem của 1 phim (để player seek đúng vị trí khi mở lại)."""
    _require_user(user_id)
    row = watch_store.get_progress_for_movie(user_id, movie_id)
    if row is None:
        return {"position_seconds": 0, "duration_seconds": 0,
                "ratio": 0.0, "status": "not_started"}
    return {
        "position_seconds": int(row["position_seconds"]),
        "duration_seconds": int(row["duration_seconds"]),
        "ratio": float(row["ratio"]),
        "status": row["status"],
    }


@router.delete("/watch/progress/{user_id}/{movie_id}")
async def remove_continue_watching(user_id: int, movie_id: int):
    """Xoá phim khỏi danh sách "Tiếp tục xem" của user."""
    _require_user(user_id)
    removed = watch_store.remove_progress(user_id, movie_id)
    return {"status": "success", "removed": removed}
