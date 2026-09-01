"""
users.py — Endpoints dữ liệu người dùng: profile, favorites, lịch sử đánh giá, preferences

Favorites và Interactions (Ratings) được đọc từ SQLite (bảng favorites và interactions).
"""

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.services.database import get_db
from api.services.user_store import get_user, update_user_genres

router = APIRouter()

def _require_user(user_id: int) -> dict:
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Người dùng chưa đăng ký")
    return user


def _enrich_movies(movie_ids: list[int]) -> list[dict]:
    if not movie_ids:
        return []
        
    conn = get_db()
    placeholders = ",".join(["?"] * len(movie_ids))
    df = pd.read_sql(f"SELECT movie_id AS movieId, title, genres, release_year, overview, poster_path, runtime_minutes, release_date FROM movies WHERE movie_id IN ({placeholders})", conn, params=movie_ids)
    return df.fillna("").to_dict(orient="records")


def _load_favorites(user_id: int) -> list[dict]:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, movie_id, added_at FROM favorites WHERE user_id = ?", (user_id,))
    rows = c.fetchall()
    return [{"userId": r[0], "movieId": r[1], "added_at": r[2]} for r in rows]


def _load_ratings(user_id: int) -> list[dict]:
    conn = get_db()
    c = conn.cursor()
    # dedupe the latest rating per movie happens in SQLite since interactions table has UNIQUE(user_id, movie_id)
    c.execute("SELECT movie_id, rating, timestamp FROM interactions WHERE user_id = ? ORDER BY timestamp DESC", (user_id,))
    rows = c.fetchall()
    return [{"movieId": r[0], "rating": r[1], "timestamp": r[2]} for r in rows]


@router.get("/users/{user_id}/profile")
def get_profile(user_id: int):
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
def get_favorites(user_id: int):
    """Danh sách phim yêu thích (đã enrich tên, poster, ...)."""
    _require_user(user_id)
    favs = _load_favorites(user_id)
    return _enrich_movies([f["movieId"] for f in favs])


class FavoriteRequest(BaseModel):
    movieId: int = Field(..., description="ID phim")
    isFavorite: bool = Field(..., description="True = thêm yêu thích, False = bỏ")


@router.post("/users/{user_id}/favorites")
def set_favorite(user_id: int, req: FavoriteRequest):
    """Thêm/bỏ phim yêu thích của user (upsert)."""
    _require_user(user_id)
    
    conn = get_db()
    c = conn.cursor()
    
    if req.isFavorite:
        added_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT OR IGNORE INTO favorites (user_id, movie_id, added_at) VALUES (?, ?, ?)",
            (user_id, req.movieId, added_at)
        )
    else:
        c.execute(
            "DELETE FROM favorites WHERE user_id = ? AND movie_id = ?",
            (user_id, req.movieId)
        )
        
    conn.commit()
    return {"status": "success", "is_favorite": req.isFavorite}


@router.get("/users/{user_id}/ratings")
def get_ratings_history(user_id: int):
    """Lịch sử đánh giá của user (từ interactions, mỗi phim giữ bản mới nhất)."""
    _require_user(user_id)
    ratings = _load_ratings(user_id)
    
    if not ratings:
        return []
        
    movie_ids = [r["movieId"] for r in ratings]
    enriched_movies = _enrich_movies(movie_ids)
    
    # Tạo map movieId -> title để tra cứu nhanh
    title_map = {m["movieId"]: m["title"] for m in enriched_movies if "title" in m}
    
    result = []
    for r in ratings:
        row = {"movieId": r["movieId"], "rating": r["rating"], "timestamp": r["timestamp"]}
        if r["movieId"] in title_map:
            row["title"] = title_map[r["movieId"]]
        result.append(row)
    return result


class PreferencesRequest(BaseModel):
    genres: list[str] = Field(default_factory=list, description="Thể loại phim yêu thích")


@router.put("/users/{user_id}/preferences")
def update_preferences(user_id: int, req: PreferencesRequest):
    """Cập nhật thể loại yêu thích (dùng cho Cold-Start theo genres)."""
    _require_user(user_id)
    updated = update_user_genres(user_id, req.genres)
    return {"status": "success", "genres": updated["genres"]}
