"""
movies.py — Các endpoints quản lý và tìm kiếm danh mục phim
"""

import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
import pandas as pd

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MOVIES_CSV = PROJECT_ROOT / "data" / "processed" / "movies_processed.csv"

# Cache DataFrame trong bộ nhớ để truy vấn nhanh
movies_df = None


def get_movies_df():
    """Tải movies_processed.csv vào bộ nhớ (singleton)."""
    global movies_df
    if movies_df is None:
        if not MOVIES_CSV.exists():
            raise HTTPException(
                status_code=500,
                detail="Movies database not initialized. Please run preprocessing first."
            )
        movies_df = pd.read_csv(MOVIES_CSV)
        # Điền null cho an toàn
        movies_df = movies_df.fillna("")
    return movies_df


@router.get("/movies/search")
async def search_movies(
    q: str = Query(..., description="Từ khóa tìm kiếm tiêu đề hoặc thể loại"),
    limit: int = Query(20, ge=1, le=100)
):
    """Tìm kiếm phim theo tên hoặc thể loại."""
    df = get_movies_df()
    
    # Tìm kiếm không phân biệt chữ hoa chữ thường
    mask = (
        df['title'].str.contains(q, case=False, na=False) | 
        df['genres'].str.contains(q, case=False, na=False)
    )
    
    results = df[mask].head(limit)
    return results.to_dict(orient="records")


@router.get("/movies/{movie_id}")
async def get_movie_detail(movie_id: int):
    """Lấy thông tin chi tiết của một bộ phim cụ thể."""
    df = get_movies_df()
    movie = df[df['movieId'] == movie_id]
    
    if movie.empty:
        raise HTTPException(status_code=404, detail="Movie not found")
        
    return movie.iloc[0].to_dict()


@router.get("/movies")
async def get_movies(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Lấy danh sách phim phân trang."""
    df = get_movies_df()
    results = df.iloc[offset:offset+limit]
    return {
        "total": len(df),
        "limit": limit,
        "offset": offset,
        "results": results.to_dict(orient="records")
    }
