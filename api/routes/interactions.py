"""Ghi phản hồi có nguồn; tín hiệu xem không thay thế đánh giá chủ động."""

from fastapi import APIRouter, HTTPException,Request
from pydantic import BaseModel, Field

from api.logging_config import get_logger
from api.routes.movies import get_movies_df
from api.services.feedback_store import write_feedback
from api.services.recommender import RecommenderService
from api.services.user_store import get_user

router = APIRouter()
logger = get_logger(__name__)


class RatingInteraction(BaseModel):
    user_id: int = Field(..., alias='userId', ge=1)
    movie_id: int = Field(..., alias='movieId', ge=1)
    rating: float = Field(..., ge=0.5, le=5.0, multiple_of=0.5, allow_inf_nan=False)


class FavoriteInteraction(BaseModel):
    user_id: int = Field(..., alias='userId', ge=1)
    movie_id: int = Field(..., alias='movieId', ge=1)
    is_favorite: bool = Field(..., alias='isFavorite')


class WatchInteraction(BaseModel):
    user_id: int = Field(..., alias='userId', ge=1)
    movie_id: int = Field(..., alias='movieId', ge=1)
    watch_duration_seconds: int = Field(..., alias='watchDurationSeconds', ge=0)
    total_duration_seconds: int = Field(..., alias='totalDurationSeconds', ge=1)


def require_movie(movie_id):
    """Không đưa ID phim không tồn tại vào dữ liệu huấn luyện."""
    if not (get_movies_df().movieId == movie_id).any():
        raise HTTPException(status_code=404, detail='Không tìm thấy phim')


def _invalidate_recommendation_cache(user_id):
    RecommenderService().invalidate_user(user_id)


def _write_interaction(user_id, movie_id, rating, source='explicit',idempotency_key=None):
    return write_feedback(user_id, movie_id, rating, source,idempotency_key)


def record_feedback(user_id, movie_id, rating, source='explicit',idempotency_key=None):
    """Việc lưu bền vững quyết định thành công; cập nhật online là best effort."""
    if get_user(user_id) is None:
        raise HTTPException(status_code=404, detail='Người dùng chưa đăng ký')
    require_movie(movie_id)
    changed = _write_interaction(user_id, movie_id, rating, source,idempotency_key)
    _invalidate_recommendation_cache(user_id)
    if changed:
        try:
            RecommenderService().apply_online_update(user_id, movie_id, rating)
        except Exception:
            logger.exception('Đã lưu phản hồi; chưa cập nhật được SVD trực tuyến')
    return {'status': 'success', 'changed': changed, 'source': source,
            'message': 'Đã ghi nhận phản hồi' if changed else 'Giữ phản hồi đã lưu có độ ưu tiên cao hơn hoặc tương đương'}


@router.post('/interactions/rating')
def record_rating(interaction: RatingInteraction,request:Request):
    """Sao người dùng chủ động nhập luôn ưu tiên hơn các tín hiệu mô phỏng."""
    return record_feedback(interaction.user_id, interaction.movie_id, interaction.rating,idempotency_key=request.headers.get('Idempotency-Key'))


@router.post('/interactions/favorite')
def record_favorite(interaction: FavoriteInteraction,request:Request):
    """Tương thích client cũ; dùng cùng thao tác lưu yêu thích của hồ sơ."""
    from api.routes.users import FavoriteRequest, set_favorite
    return set_favorite(interaction.user_id, FavoriteRequest(
        movieId=interaction.movie_id, isFavorite=interaction.is_favorite),request)


@router.post('/interactions/watch')
def record_watch_history(interaction: WatchInteraction,request:Request):
    """Quy tắc proxy cho demo: chỉ lượt xem >=95% là tín hiệu dương yếu.

    Không suy ra không thích từ việc rời màn hình hoặc kéo thanh tiến độ.
    Đây không phải nhãn sở thích thật hay mô hình học implicit feedback.
    """
    if get_user(interaction.user_id) is None:
        raise HTTPException(status_code=404, detail='Người dùng chưa đăng ký')
    require_movie(interaction.movie_id)
    if interaction.watch_duration_seconds > interaction.total_duration_seconds:
        raise HTTPException(status_code=422, detail='Vị trí xem vượt quá thời lượng')
    ratio = interaction.watch_duration_seconds / interaction.total_duration_seconds
    if ratio < 0.95:
        return {'status': 'success', 'changed': False, 'source': 'watch',
                'message': 'Xem dở không được quy thành đánh giá sao'}
    return record_feedback(interaction.user_id, interaction.movie_id, 4.0, 'watch_complete',request.headers.get('Idempotency-Key'))
