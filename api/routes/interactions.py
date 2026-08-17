"""
interactions.py — Ghi nhận hành vi và phản hồi từ người dùng (MLOps feedback loop)

Feedback được lưu vào data/processed/interactions_log.csv (tách khỏi train set).
Đầu chu kỳ retrain, merge_interactions.py sẽ gộp log này vào dữ liệu và tái chia split.
"""

from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import pandas as pd

from api.logging_config import get_logger
from api.services.recommender import RecommenderService
from api.services.user_store import get_user

logger = get_logger(__name__)

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INTERACTIONS_LOG_CSV = PROJECT_ROOT / "data" / "processed" / "interactions_log.csv"


class RatingInteraction(BaseModel):
    user_id: int = Field(..., alias="userId", description="ID của người dùng")
    movie_id: int = Field(..., alias="movieId", description="ID của bộ phim")
    rating: float = Field(..., ge=0.5, le=5.0, description="Đánh giá từ 0.5 đến 5.0 sao")


class FavoriteInteraction(BaseModel):
    user_id: int = Field(..., alias="userId")
    movie_id: int = Field(..., alias="movieId")
    is_favorite: bool = Field(..., alias="isFavorite")


class WatchInteraction(BaseModel):
    user_id: int = Field(..., alias="userId")
    movie_id: int = Field(..., alias="movieId")
    watch_duration_seconds: int = Field(..., alias="watchDurationSeconds")
    total_duration_seconds: int = Field(..., alias="totalDurationSeconds")


def _invalidate_recommendation_cache(user_id: int):
    """Xóa cache gợi ý của user để nhận kết quả mới ngay sau khi có tương tác."""
    service = RecommenderService()
    # Cache chỉ tồn tại sau khi RecommenderService.initialize() được gọi (lần đầu có request gợi ý)
    cache = getattr(service, "recommendations_cache", None)
    if cache is None:
        return
    removed = cache.pop(user_id, None)
    if removed is not None:
        logger.info(f"Đã xóa cache gợi ý cho user {user_id} sau khi có tương tác mới.")


def _write_interaction(user_id: int, movie_id: int, rating: float):
    """Append/upsert một rating vào interactions_log.csv (không đụng vào train set)."""
    new_row = {
        "userId": user_id,
        "movieId": movie_id,
        "rating": rating,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if INTERACTIONS_LOG_CSV.exists():
        df = pd.read_csv(INTERACTIONS_LOG_CSV)
        mask = (df['userId'] == user_id) & (df['movieId'] == movie_id)
        if mask.any():
            df.loc[mask, 'rating'] = rating
            df.loc[mask, 'timestamp'] = new_row['timestamp']
            logger.info(f"Đã cập nhật interaction user {user_id} - movie {movie_id} (rating={rating})")
        else:
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            logger.info(f"Đã thêm interaction mới user {user_id} - movie {movie_id} (rating={rating})")
        df.to_csv(INTERACTIONS_LOG_CSV, index=False)
    else:
        pd.DataFrame([new_row]).to_csv(INTERACTIONS_LOG_CSV, index=False)
        logger.info(f"Đã tạo interactions_log.csv và ghi interaction user {user_id} - movie {movie_id}")


@router.post("/interactions/rating")
async def record_rating(interaction: RatingInteraction):
    """Ghi nhận đánh giá sao tường minh (Explicit Feedback).

    Rating mới được lưu vào interactions_log.csv, chu kỳ retrain tiếp theo sẽ
    merge log này vào dữ liệu huấn luyện (xem src/data/merge_interactions.py).
    """
    # Chỉ user đã đăng ký mới được ghi dữ liệu vào vòng lặp MLOps
    if get_user(interaction.user_id) is None:
        raise HTTPException(status_code=404, detail="Người dùng chưa đăng ký")

    try:
        _write_interaction(interaction.user_id, interaction.movie_id, interaction.rating)
        _invalidate_recommendation_cache(interaction.user_id)
        # Online Learning: cập nhật tức thời vector ẩn của user để khuyến nghị
        # phản ánh đúng hành vi mới nhất mà không cần chờ chu kỳ retrain.
        RecommenderService().apply_online_update(
            interaction.user_id, interaction.movie_id, interaction.rating
        )
        return {"status": "success", "message": "Đã ghi nhận đánh giá thành công."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi lưu rating: {str(e)}")


@router.post("/interactions/favorite")
async def record_favorite(interaction: FavoriteInteraction):
    """Ghi nhận hành động nhấn Yêu thích/Bỏ thích (Implicit Feedback).

    Quy đổi hành vi:
      - is_favorite = True  -> Quy đổi tương đương rating = 4.5 sao
      - is_favorite = False -> Quy đổi tương đương rating = 2.5 sao
      Thành phần Implicit Feedback được convert thành Explicit Rating để huấn luyện SVD.
    """
    mapped_rating = 4.5 if interaction.is_favorite else 2.5

    rating_payload = RatingInteraction(
        userId=interaction.user_id,
        movieId=interaction.movie_id,
        rating=mapped_rating
    )
    return await record_rating(rating_payload)


@router.post("/interactions/watch")
async def record_watch_history(interaction: WatchInteraction):
    """Ghi nhận lịch sử xem phim và tính toán Implicit Feedback dựa trên thời lượng xem.

    Công thức quy đổi Confidence Score sang Rating:
      - Watch Ratio >= 80% -> rating = 5.0 sao
      - Watch Ratio >= 50% -> rating = 4.0 sao
      - Watch Ratio >= 20% -> rating = 3.0 sao
      - Watch Ratio < 20%  -> rating phạt 1.5 sao
    """
    if interaction.total_duration_seconds <= 0:
        raise HTTPException(status_code=400, detail="Thời lượng phim không hợp lệ.")

    watch_ratio = interaction.watch_duration_seconds / interaction.total_duration_seconds

    if watch_ratio >= 0.8:
        mapped_rating = 5.0
    elif watch_ratio >= 0.5:
        mapped_rating = 4.0
    elif watch_ratio >= 0.2:
        mapped_rating = 3.0
    else:
        mapped_rating = 1.5  # Phạt

    logger.info(f"User {interaction.user_id} xem phim {interaction.movie_id} được {watch_ratio*100:.1f}%. Quy đổi rating = {mapped_rating}")

    rating_payload = RatingInteraction(
        userId=interaction.user_id,
        movieId=interaction.movie_id,
        rating=mapped_rating
    )
    return await record_rating(rating_payload)
