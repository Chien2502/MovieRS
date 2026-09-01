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
import numpy as np
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
ITEM_SIM_NPZ = PROJECT_ROOT / "data" / "processed" / "item_sim.npz"
ITEM_SIM_TOP_K = 300


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
        self._item_sim_index = None

        # Load movies catalog
        from api.services.database import get_db
        try:
            conn = get_db()
            self.movies_df = pd.read_sql("SELECT movie_id AS movieId, title, genres, release_year, overview, poster_path, runtime_minutes, release_date FROM movies", conn)
            self.movies_df = self.movies_df.fillna("")
            self.all_movie_ids = self.movies_df['movieId'].tolist()
            self._movie_id_to_row = {
                int(mid): i for i, mid in enumerate(self.movies_df['movieId'].astype(int))
            }
        except Exception as e:
            raise FileNotFoundError(f"Lỗi tải danh mục phim từ DB: {e}")
        if self.movies_df.empty:
            raise FileNotFoundError("Không tìm thấy dữ liệu danh mục phim trong DB")

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
            self.train_item_ids = set(train_df['movieId'].astype(int).unique())
        else:
            self.known_users = set()
            self.train_item_ids = set()

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

    def _get_recent_activity(self, user_id: int) -> tuple[set, list]:
        """Danh sách phim user đã tương tác gần đây (cache 60s). Trả về (set, list_có_thứ_tự)."""
        now = time.time()
        cached = self.recent_activity.get(user_id)
        if cached is not None and now - cached[0] < self.recent_activity_ttl:
            return cached[1]

        watched_set: set = set()
        watched_list: list = []
        try:
            from api.services.database import get_db
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT movie_id FROM interactions WHERE user_id = ? ORDER BY timestamp ASC", (user_id,))
            rows = c.fetchall()
            watched_list = [r[0] for r in rows]
            watched_set = set(watched_list)
        except Exception as e:
            logger.warning(f"[⚠] Không đọc được interactions cho user {user_id}: {e}")
        
        result = (watched_set, watched_list)
        self.recent_activity[user_id] = (now, result)
        return result

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

    def _load_item_sim_index(self):
        """Load item-item similarity index (.npz) nếu chưa có, cache in-memory."""
        if self._item_sim_index is not None:
            return self._item_sim_index
        if not ITEM_SIM_NPZ.exists():
            logger.warning("[ItemSim] Không tìm thấy %s — bỏ qua candidate retrieval.", ITEM_SIM_NPZ)
            return None
        try:
            with np.load(ITEM_SIM_NPZ, allow_pickle=False) as data:
                self._item_sim_index = {
                    "train_item_ids": data["train_item_ids"].astype(np.int32),
                    "latent_top_mids": data["latent_top_mids"].astype(np.int32),
                    "latent_top_scores": data["latent_top_scores"].astype(np.float32),
                    "cold_item_ids": data["cold_item_ids"].astype(np.int32),
                    "genre_top_mids": data["genre_top_mids"].astype(np.int32),
                    "genre_top_scores": data["genre_top_scores"].astype(np.float32),
                }
            logger.info("[ItemSim] Đã load index (%d warm, %d cold items).",
                        len(self._item_sim_index["train_item_ids"]),
                        len(self._item_sim_index["cold_item_ids"]))
            return self._item_sim_index
        except Exception as e:
            logger.warning("[ItemSim] Lỗi load index: %s", e)
            return None

    def _get_candidates_from_item_sim(self, movie_id: int, n: int = ITEM_SIM_TOP_K) -> list[int]:
        """Lấy top-N phim tương tự với movie_id (kết hợp latent + genre)."""
        sim = self._load_item_sim_index()
        if sim is None:
            return []

        mid = int(movie_id)
        train_arr = sim["train_item_ids"]
        candidates: set[int] = set()

        # Tìm movie_id trong train (latent)
        mask = train_arr == mid
        if mask.any():
            idx = int(np.flatnonzero(mask)[0])
            sim_mids = sim["latent_top_mids"][idx][:n]
            candidates.update(int(x) for x in sim_mids if x > 0)
        else:
            # Tìm trong cold items (genre)
            cold_arr = sim["cold_item_ids"]
            mask_cold = cold_arr == mid
            if mask_cold.any():
                idx_c = int(np.flatnonzero(mask_cold)[0])
                sim_mids = sim["genre_top_mids"][idx_c][:n]
                candidates.update(int(x) for x in sim_mids if x > 0)

        return list(candidates)

    def _score_candidates_svd(self, user_id: int, candidate_ids: list[int],
                               rated_movie_ids: set) -> list[tuple[int, float]]:
        """Chấm điểm danh sách ứng viên bằng SVD (chỉ những phim chưa xem)."""
        if self.model is None:
            return [(mid, 0.0) for mid in candidate_ids]

        # Lọc bỏ phim đã xem
        cands = [mid for mid in candidate_ids if mid not in rated_movie_ids]
        if not cands:
            return []

        # Dùng _recommend_vectorized nhưng chỉ với danh sách con
        try:
            recs = self.model.recommend(
                user_id=user_id,
                all_movie_ids=cands,
                rated_movie_ids=[],
                n=len(cands),
            )
            return recs
        except Exception as e:
            logger.warning("[⚠] Lỗi score candidates: %s", e)
            return [(mid, 0.0) for mid in cands]

    def get_recommendations(self, user_id: int, limit: int = 10) -> list:
        """Sinh ra danh sách Top-N phim gợi ý cho user (2-stage: retrieve + rerank)."""
        self.initialize()

        # 1. Kiểm tra cache
        current_time = time.time()
        if user_id in self.recommendations_cache:
            cached_time, cached_recs = self.recommendations_cache[user_id]
            if current_time - cached_time < self.cache_expiry_seconds:
                logger.info(f"[⚡ Cache Hit] Trả về kết quả từ cache cho user {user_id}")
                return cached_recs[:limit]

        # 2. Xử lý Cold-Start User
        has_online_profile = (
            self.model is not None
            and user_id in getattr(self.model, "extra_users", {})
        )
        is_cold = user_id not in self.known_users and not has_online_profile

        # Phim đã tương tác gần đây (log) — loại khỏi gợi ý ngay
        recent_watched, recent_watched_list = self._get_recent_activity(user_id)

        start_time = time.time()

        if is_cold or self.model is None:
            # --- Cold-Start: Popularity + Genre preference ---
            logger.info(f"[❄ Cold-Start] User {user_id} chưa có lịch sử. Sử dụng Popularity Recommender...")
            if self.popularity_model is not None:
                top_movie_ids = self.popularity_model.recommend(user_id, n=limit * 3)
                user = get_user(user_id)
                user_genres = user.get("genres", []) if user else []
                if user_genres:
                    top_movie_ids = self._prefer_genres(top_movie_ids, user_genres, limit * 3)
                top_movie_ids = [m for m in top_movie_ids if m not in recent_watched]
            else:
                top_movie_ids = [m for m in self.all_movie_ids[:limit * 3] if m not in recent_watched]
            top_movie_ids = top_movie_ids[:limit * 2]
        else:
            # --- Warm user: 2-stage retrieve + rerank ---
            logger.info(f"[🔥 SVD 2-Stage] User {user_id} — retrieve candidates từ Top 3 phim gần nhất...")
            
            sim_candidates: set = set()
            
            # Lấy tối đa 3 phim tương tác gần nhất làm hạt giống (seed)
            seed_movies = recent_watched_list[-3:] if recent_watched_list else []
            
            for seed_id in seed_movies:
                cands = self._get_candidates_from_item_sim(seed_id, n=ITEM_SIM_TOP_K)
                sim_candidates.update(cands)
                
            sim_candidates = list(sim_candidates)

            # Nếu user không có log gần đây, fallback dùng phim phổ biến hoặc toàn bộ catalog
            if not sim_candidates:
                if self.popularity_model is not None:
                    sim_candidates = self.popularity_model.recommend(user_id, n=ITEM_SIM_TOP_K * 2)
                else:
                    sim_candidates = list(self.train_item_ids)
                
            rated_movies = recent_watched
            scored = self._score_candidates_svd(user_id, sim_candidates, rated_movies)
            
            # Nếu user có chọn thể loại yêu thích (từ bước đăng ký), ta bonus điểm nhẹ cho các phim hợp gu
            user = get_user(user_id)
            user_genres = user.get("genres", []) if user else []
            if user_genres:
                top_movie_ids = self._prefer_genres([mid for mid, _ in scored], user_genres, limit * 2)
            else:
                top_movie_ids = [mid for mid, _ in scored]

        # 3. Làm giàu metadata
        recommended_movies = []
        for mid in top_movie_ids:
            movie_row = self.movies_df[self.movies_df['movieId'] == mid]
            if not movie_row.empty:
                movie_dict = movie_row.iloc[0].to_dict()
                recommended_movies.append(movie_dict)

        final_recs = recommended_movies[:limit]

        latency = (time.time() - start_time) * 1000
        n_cands = len(sim_candidates) if 'sim_candidates' in locals() else 0
        logger.info(f"    ✓ Gợi ý hoàn tất cho user {user_id} trong {latency:.2f}ms "
                    f"(candidates={n_cands})")

        # 4. Lưu vào cache
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
        self._item_sim_index = None
        self.recommendations_cache.clear()
        self.initialize()
        logger.info("[🧠] Đã nạp lại mô hình mới thành công!")
