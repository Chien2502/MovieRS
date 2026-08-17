"""
recommender.py — Service thực thi logic gợi ý phim (Recommendation Service)

Các tính năng:
  1. Tải và giám sát mô hình SVD (SurpriseSVDRecommender).
  2. Xử lý bài toán Cold-Start: Gợi ý các phim phổ biến (Popularity-based) cho user mới.
  3. Làm giàu thông tin phim (Merge với movies_processed.csv để lấy title, genres, poster_path, overview).
  4. Cơ chế Caching in-memory giúp giảm latency < 10ms.
"""

import threading
import time
from pathlib import Path
import pandas as pd
from api.logging_config import get_logger
from api.services.user_store import get_user
from src.models.svd_surprise import SurpriseSVDRecommender
from src.models.baseline import PopularityRecommender

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "model_latest.pkl"
MOVIES_CSV = PROJECT_ROOT / "data" / "processed" / "movies_processed.csv"
TRAIN_RATINGS_CSV = PROJECT_ROOT / "data" / "processed" / "ratings_train.csv"
INTERACTIONS_LOG_CSV = PROJECT_ROOT / "data" / "processed" / "interactions_log.csv"


class RecommenderService:
    """Service singleton phục vụ khuyến nghị phim."""
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RecommenderService, cls).__new__(cls, *args, **kwargs)
            cls._instance.initialized = False
        return cls._instance

    def initialize(self):
        if self.initialized:
            return
            
        logger.info("[🧠] Đang khởi tạo RecommenderService...")
        self.model = None
        self.movies_df = None
        self.popularity_model = None
        
        # Load movies catalog
        if MOVIES_CSV.exists():
            self.movies_df = pd.read_csv(MOVIES_CSV).fillna("")
            self.all_movie_ids = self.movies_df['movieId'].tolist()
        else:
            raise FileNotFoundError(f"Không tìm thấy file danh mục phim: {MOVIES_CSV}")
            
        # Load SVD model
        if MODEL_PATH.exists():
            try:
                self.model = SurpriseSVDRecommender.load(MODEL_PATH)
            except Exception as e:
                logger.warning(f"[⚠] Lỗi tải mô hình SVD: {e}. Hệ thống sẽ sử dụng Popularity Recommender làm mặc định.")
        else:
            logger.warning("[⚠] Không tìm thấy mô hình SVD tại models/. Vui lòng chạy train_pipeline.py trước.")
            
        # Huấn luyện Popularity Recommender để dự phòng (fallback) và giải quyết Cold-Start
        if TRAIN_RATINGS_CSV.exists():
            train_df = pd.read_csv(TRAIN_RATINGS_CSV)
            self.popularity_model = PopularityRecommender().fit(train_df)
            self.known_users = set(train_df['userId'].unique())
        else:
            self.known_users = set()
            
        # In-memory Cache kết quả: {user_id: (timestamp, recommendations_list)}
        self.recommendations_cache = {}
        self.cache_expiry_seconds = 300  # Cache hết hạn sau 5 phút

        # Cache phim đã tương tác (từ interactions_log) — {user_id: (timestamp, set)}
        # Giúp loại NGAY phim vừa xem/đánh giá khỏi gợi ý mà không cần chờ retrain.
        self.recent_activity = {}
        self.recent_activity_ttl = 60  # Làm mới tối đa mỗi 60 giây

        # Khóa đồng bộ cho online update (tránh ghi đè đồng thời từ nhiều request)
        self._online_lock = threading.Lock()
        
        self.initialized = True
        logger.info("[🧠] Khởi tạo RecommenderService hoàn tất.")

    def _get_recent_activity(self, user_id: int) -> set:
        """Danh sách phim user đã tương tác gần đây (đọc từ interactions_log, cache 60s).

        Phim nằm trong danh sách này sẽ bị loại khỏi mọi gợi ý — kể cả khi user
        vẫn "lạnh" với mô hình (chưa vào trainset) cho tới chu kỳ retrain tiếp theo.
        """
        now = time.time()
        cached = self.recent_activity.get(user_id)
        if cached is not None and now - cached[0] < self.recent_activity_ttl:
            return cached[1]

        watched: set = set()
        if INTERACTIONS_LOG_CSV.exists():
            try:
                df = pd.read_csv(INTERACTIONS_LOG_CSV)
                watched = set(
                    df[df['userId'] == user_id]['movieId'].dropna().astype(int).tolist()
                )
            except Exception as e:
                logger.warning(f"[⚠] Không đọc được interactions_log cho user {user_id}: {e}")
        self.recent_activity[user_id] = (now, watched)
        return watched

    def apply_online_update(self, user_id: int, movie_id: int, rating: float) -> bool:
        """Cập nhật TỨC THỜI vector ẩn của user theo tương tác mới (Online Learning).

        Chỉ 1 bước SGD trên user duy nhất (~ms) — không retrain toàn bộ model.
        Đồng thời làm mới cache phim đã xem của user để gợi ý tiếp theo loại bỏ
        đúng phim vừa tương tác.
        """
        self.initialize()
        if self.model is None:
            return False
        try:
            with self._online_lock:
                updated = self.model.online_update(user_id, movie_id, rating)
            if updated:
                # Vô hiệu hóa cache gợi ý + danh sách phim đã xem của user
                self.recommendations_cache.pop(user_id, None)
                self.recent_activity.pop(user_id, None)
                logger.info(f"[⚡ Online Update] user {user_id} — movie {movie_id} (r={rating})")
            return updated
        except Exception as e:
            logger.warning(f"[⚠] Online update thất bại user {user_id}: {e}")
            return False

    def get_recommendations(self, user_id: int, limit: int = 10) -> list:
        """Sinh ra danh sách Top-N phim gợi ý cho user."""
        self.initialize()
        
        # 1. Kiểm tra cache
        current_time = time.time()
        if user_id in self.recommendations_cache:
            cached_time, cached_recs = self.recommendations_cache[user_id]
            if current_time - cached_time < self.cache_expiry_seconds:
                logger.info(f"[⚡ Cache Hit] Trả về kết quả từ cache cho user {user_id}")
                return cached_recs[:limit]
                
        # 2. Xử lý Cold-Start User
        # Nếu user chưa từng xuất hiện trong tập Train, gợi ý các phim phổ biến nhất (Popularity)
        is_cold = user_id not in self.known_users

        # Phim đã tương tác gần đây (log) — loại khỏi gợi ý ngay, không chờ retrain
        recent_watched = self._get_recent_activity(user_id)

        start_time = time.time()
        
        if is_cold or self.model is None:
            logger.info(f"[❄ Cold-Start] User {user_id} chưa có lịch sử. Sử dụng Popularity Recommender...")
            if self.popularity_model is not None:
                top_movie_ids = self.popularity_model.recommend(user_id, n=limit*2)
                # Cold-Start theo sở thích: ưu tiên phim đúng thể loại user đã đăng ký
                user = get_user(user_id)
                user_genres = user.get("genres", []) if user else []
                if user_genres:
                    top_movie_ids = self._prefer_genres(top_movie_ids, user_genres, limit*2)
                # Loại bỏ phim user đã xem/đánh giá gần đây
                top_movie_ids = [m for m in top_movie_ids if m not in recent_watched]
            else:
                # Fallback cuối cùng nếu không có cả popularity model: lấy bừa trong catalog
                top_movie_ids = [m for m in self.all_movie_ids[:limit*2] if m not in recent_watched]
        else:
            # User ấm: Sử dụng mô hình SVD để dự đoán
            logger.info(f"[🔥 SVD Recommend] Đang tính toán gợi ý cá nhân hóa cho user {user_id}...")
            # Lấy danh sách các phim user đã đánh giá để loại bỏ khỏi danh sách gợi ý
            # Đọc từ tập train + gộp với phim đã tương tác gần đây (log)
            train_df = pd.read_csv(TRAIN_RATINGS_CSV)
            rated_movies = train_df[train_df['userId'] == user_id]['movieId'].tolist()
            rated_movies = set(rated_movies) | recent_watched
            
            # Dự đoán Top N phim tốt nhất
            recs_with_score = self.model.recommend(
                user_id=user_id,
                all_movie_ids=self.all_movie_ids,
                rated_movie_ids=list(rated_movies),
                n=limit*2
            )
            top_movie_ids = [mid for mid, _ in recs_with_score]
            
        # 3. Làm giàu dữ liệu phim (Merge với metadata để lấy poster, mô tả)
        recommended_movies = []
        for mid in top_movie_ids:
            movie_row = self.movies_df[self.movies_df['movieId'] == mid]
            if not movie_row.empty:
                movie_dict = movie_row.iloc[0].to_dict()
                recommended_movies.append(movie_dict)
                
        # 4. Tiêm tính đa dạng (Diversity Injection) để tránh Filter Bubble
        # Đảm bảo trong top gợi ý có 1-2 phim thuộc thể loại khác hoàn toàn sở thích
        # (Ở đây ta chỉ lấy tối đa đúng số lượng limit sau khi xử lý)
        final_recs = recommended_movies[:limit]
        
        latency = (time.time() - start_time) * 1000
        logger.info(f"    ✓ Gợi ý hoàn tất cho user {user_id} trong {latency:.2f}ms")
        
        # 5. Lưu vào cache
        self.recommendations_cache[user_id] = (current_time, recommended_movies)
        
        return final_recs
        
    def _prefer_genres(self, movie_ids: list, genres: list, n: int) -> list:
        """Sắp xếp lại danh sách phim: phim trùng thể loại yêu thích lên đầu (giữ thứ tự popularity)."""
        if not genres or self.movies_df is None:
            return movie_ids[:n]

        genre_scores = {}
        for mid in movie_ids:
            row = self.movies_df[self.movies_df['movieId'] == mid]
            if row.empty:
                genre_scores[mid] = 0
                continue
            movie_genres = str(row.iloc[0].get('genres', ''))
            genre_scores[mid] = sum(
                1 for g in genres if g.lower() in movie_genres.lower()
            )

        ordered = sorted(movie_ids, key=lambda mid: -genre_scores.get(mid, 0))
        return ordered[:n]

    def reload_model(self):
        """Buộc nạp lại mô hình SVD khi có retraining."""
        self.initialized = False
        self.recommendations_cache.clear()
        self.initialize()
        logger.info("[🧠] Đã nạp lại mô hình mới thành công!")
