"""
users.py — Endpoints dữ liệu người dùng: profile, favorites, lịch sử đánh giá, preferences

Favorites lưu tại data/processed/user_favorites.csv (tất cả user trong 1 file).
Lịch sử đánh giá đọc từ interactions_log.csv (nguồn duy nhất của vòng feedback MLOps).
"""

import threading
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import pandas as pd

from api.services.user_store import get_user, update_user_genres

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MOVIES_CSV = PROJECT_ROOT / "data" / "processed" / "movies_processed.csv"
FAVORITES_CSV = PROJECT_ROOT / "data" / "processed" / "user_favorites.csv"
INTERACTIONS_LOG_CSV = PROJECT_ROOT / "data" / "processed" / "interactions_log.csv"

_fav_lock = threading.Lock()


def _require_user(user_id: int) -> dict:
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Người dùng chưa đăng ký")
    return user


def _movies_df() -> pd.DataFrame:
    if not MOVIES_CSV.exists():
        raise HTTPException(status_code=500, detail="Movies database not initialized")
    return pd.read_csv(MOVIES_CSV).fillna("")


def _enrich_movies(movie_ids: list[int]) -> list[dict]:
    df = _movies_df()
    rows = []
    for mid in movie_ids:
        movie = df[df["movieId"] == mid]
        if not movie.empty:
            rows.append(movie.iloc[0].to_dict())
    return rows


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _load_favorites(user_id: int) -> list[dict]:
    df = _read_csv_safe(FAVORITES_CSV)
    if df.empty or 'userId' not in df.columns:
        return []
    df = df[df['userId'] == user_id]
    return df.to_dict("records")


def _save_favorites(user_id: int, rows: list[dict]):
    """Ghi lại toàn bộ file favorites (user hiện tại được ghi, các user khác giữ nguyên)."""
    others = _read_csv_safe(FAVORITES_CSV)
    if not others.empty and 'userId' in others.columns:
        others = others[others['userId'] != user_id]
    combined = pd.concat([others, pd.DataFrame(rows)], ignore_index=True) if rows else others
    FAVORITES_CSV.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(FAVORITES_CSV, index=False)


def _load_ratings(user_id: int) -> list[dict]:
    df = _read_csv_safe(INTERACTIONS_LOG_CSV)
    if df.empty or 'userId' not in df.columns:
        return []
    df = df[df['userId'] == user_id]
    if df.empty:
        return []
    df = df.sort_values('timestamp').drop_duplicates(subset=['movieId'], keep='last')
    return df.to_dict("records")


@router.get("/users/{user_id}/profile")
async def get_profile(user_id: int):
    """Thông tin hồ sơ người dùng (hiển thị trên màn hình Profile)."""
    user = _require_user(user_id)
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "genres": user.get("genres", []),
        "favorites_count": len(_load_favorites(user_id)),
        "ratings_count": len(_load_ratings(user_id)),
    }


@router.get("/users/{user_id}/favorites")
async def get_favorites(user_id: int):
    """Danh sách phim yêu thích (đã enrich tên, poster, ...)."""
    _require_user(user_id)
    favs = _load_favorites(user_id)
    return _enrich_movies([f["movieId"] for f in favs])


class FavoriteRequest(BaseModel):
    movieId: int = Field(..., description="ID phim")
    isFavorite: bool = Field(..., description="True = thêm yêu thích, False = bỏ")


@router.post("/users/{user_id}/favorites")
async def set_favorite(user_id: int, req: FavoriteRequest):
    """Thêm/bỏ phim yêu thích của user (upsert)."""
    _require_user(user_id)
    with _fav_lock:
        rows = [r for r in _load_favorites(user_id) if r["movieId"] != req.movieId]
        if req.isFavorite:
            rows.append({
                "userId": user_id,
                "movieId": req.movieId,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        _save_favorites(user_id, rows)
    return {"status": "success", "is_favorite": req.isFavorite}


@router.get("/users/{user_id}/ratings")
async def get_ratings_history(user_id: int):
    """Lịch sử đánh giá của user (từ interactions_log, mỗi phim giữ bản mới nhất)."""
    _require_user(user_id)
    ratings = _load_ratings(user_id)
    df = _movies_df()
    result = []
    for r in ratings:
        row = {"movieId": r["movieId"], "rating": r["rating"], "timestamp": r["timestamp"]}
        movie = df[df["movieId"] == r["movieId"]]
        if not movie.empty:
            row["title"] = movie.iloc[0]["title"]
        result.append(row)
    return result


class PreferencesRequest(BaseModel):
    genres: list[str] = Field(default_factory=list, description="Thể loại phim yêu thích")


@router.put("/users/{user_id}/preferences")
async def update_preferences(user_id: int, req: PreferencesRequest):
    """Cập nhật thể loại yêu thích (dùng cho Cold-Start theo genres)."""
    _require_user(user_id)
    updated = update_user_genres(user_id, req.genres)
    return {"status": "success", "genres": updated["genres"]}
