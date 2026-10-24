"""Khuyến nghị kết hợp SVD, thể loại, Bayesian popularity và đa dạng MMR."""

import threading
import os
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

from api.logging_config import get_logger
from api.services.feedback_store import read_feedback
from api.services.user_store import get_user
from src.models.baseline import PopularityRecommender
from src.models.hybrid import genre_profile, parse_genres, rank_hybrid
from src.models.svd_surprise import SurpriseSVDRecommender
from src.models.research import percentile

logger = get_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models/model_latest.pkl"
MOVIES_CSV = PROJECT_ROOT / "data/processed/movies_processed.csv"
TRAIN_RATINGS_CSV = PROJECT_ROOT / "data/processed/ratings_train.csv"


class RecommenderService:
    """Một snapshot nhất quán; reload chỉ thay snapshot sau khi tải thành công."""

    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.initialized = False
                cls._instance._lock = threading.RLock()
        return cls._instance

    def initialize(self, force=False):
        with self._lock:
            if self.initialized and not force:
                return
            movies = pd.read_csv(MOVIES_CSV).fillna("")
            train = pd.read_csv(TRAIN_RATINGS_CSV) if TRAIN_RATINGS_CSV.exists() else pd.DataFrame(
                columns=['userId', 'movieId', 'rating'])
            ranking_model,serving_name,serving_version=None,None,None
            pointer=os.getenv('MOVIERS_SERVING_POINTER','').strip()
            if pointer:
                from api.services.serving import load_bundle
                bundle,serving_manifest=load_bundle(PROJECT_ROOT/pointer)
                train=bundle['history']
                ranking_model=bundle['model']
                serving_name=bundle['spec']['family']
                serving_version=serving_manifest['version']
                canonical=bundle.get('catalog')
                if canonical is not None:
                    metadata=movies.set_index('movieId')
                    raw=canonical.set_index('movieId')
                    missing=raw.loc[~raw.index.isin(metadata.index)].reset_index()
                    if len(missing):
                        missing=missing.assign(poster_path='',overview='Chưa có mô tả phim.',vote_average=0,
                                               runtime_minutes=100,runtime_source='simulation_default')
                        movies=pd.concat([movies,missing],ignore_index=True).fillna('')
                    for field in ['title','genres']:
                        movies[field]=movies.movieId.map(raw[field]).fillna(movies[field])
            records = {int(row['movieId']): row for row in movies.to_dict('records')}
            popularity = PopularityRecommender().fit(train) if not train.empty else None
            model = None
            if ranking_model is not None:
                model=ranking_model if isinstance(ranking_model,SurpriseSVDRecommender) else None
            elif MODEL_PATH.exists():
                try:
                    model = SurpriseSVDRecommender.load(MODEL_PATH)
                except Exception:
                    if force and self.initialized and self.model is not None:
                        raise
                    logger.exception("Không tải được SVD; phục vụ bằng độ phổ biến và thể loại")
            elif force and self.initialized and self.model is not None:
                raise FileNotFoundError("Không tìm thấy mô hình mới; giữ snapshot đang phục vụ")
            # Một lượt trên các tuple tránh tạo hơn 130 nghìn DataFrame theo user.
            histories = defaultdict(list)
            for uid, mid, rating in train[['userId', 'movieId', 'rating']].itertuples(index=False, name=None):
                histories[int(uid)].append((int(mid), float(rating)))
            self.movies_df, self.movies = movies, records
            self.movie_genres = {mid: parse_genres(row.get('genres', '')) for mid, row in records.items()}
            self.model, self.popularity_model = model, popularity
            self.ranking_model,self.serving_name,self.serving_version=ranking_model,serving_name,serving_version
            self.histories, self.known_users = histories, set(histories)
            self.all_movie_ids = sorted(records)
            self.candidate_ids = sorted(set(train.movieId.astype(int)) & records.keys()) if popularity else self.all_movie_ids
            self.recommendations_cache = {}
            self.cache_expiry_seconds = 300
            self.initialized = True

    def invalidate_user(self, user_id):
        with self._lock:
            if self.initialized:
                for key in list(self.recommendations_cache):
                    if key[0] == user_id:
                        self.recommendations_cache.pop(key, None)

    def apply_online_update(self, user_id, movie_id, rating):
        self.initialize()
        with self._lock:
            self.invalidate_user(user_id)
            if self.model is None:
                return False
            return self.model.online_update(user_id, movie_id, rating)

    def get_popular_movies(self, limit=10):
        self.initialize()
        with self._lock:
            if self.popularity_model:
                ids = [mid for mid in self.popularity_model.popular_movies if mid in self.movies]
                counts = self.popularity_model.popular_movies_df.set_index('movieId').rating_count.to_dict()
                return [{**self.movies[mid], 'rating_count': int(
                    counts[mid])}
                        for mid in ids[:limit]]
            return [self.movies[mid] for mid in self.all_movie_ids[:limit]]

    def get_recommendation_result(self, user_id, limit=10, explore=False):
        self.initialize()
        with self._lock:
            now = time.monotonic()
            cache_key = (user_id, bool(explore))
            cached = self.recommendations_cache.get(cache_key)
            if cached and now - cached[0] < self.cache_expiry_seconds:
                return {**cached[1], 'recommendations': cached[1]['recommendations'][:limit]}
            user = get_user(user_id) or {}
            feedback = read_feedback(user_id)
            recent = feedback[feedback.userId == user_id]
            history = dict(self.histories.get(user_id, []))
            history.update({int(row.movieId): float(row.rating) for row in recent.itertuples()})
            seen = set(history)
            profile = genre_profile(history.items(), self.movie_genres, user.get('genres', []))
            has_svd = False
            trained_user = False
            if self.model is not None:
                try:
                    self.model.model.trainset.to_inner_uid(user_id)
                    trained_user = True
                except ValueError:
                    pass
                has_svd = trained_user or user_id in self.model.extra_users
            strategy = 'hybrid_svd' if has_svd else ('genre_popularity' if profile else 'popularity')
            stage = 'personalized' if trained_user else ('learning' if history else 'cold_start')
            candidates = [mid for mid in self.candidate_ids if mid not in seen]
            if self.ranking_model is not None:
                scores=.5+4.5*percentile(self.ranking_model.score_items(user_id,candidates))
                strategy=self.serving_name+'_onboarding_rerank'
            elif has_svd:
                scores = self.model.score_items(user_id, candidates)
            elif self.popularity_model:
                scores = [self.popularity_model.predict(user_id, mid) for mid in candidates]
            else:
                scores = [3.0] * len(candidates)
                strategy = 'catalog_fallback'
            # MMR là lựa chọn khám phá; mặc định không dùng vì NDCG validation thấp hơn.
            diversity = 0.1 if explore else 0.0
            ranked = rank_hybrid(candidates, scores, self.movie_genres, profile, n=50,
                                 genre_weight=0.2, diversity_weight=diversity)
            recommendations = []
            for item in ranked:
                mid = item['movieId']
                matching = sorted(g for g in self.movie_genres[mid] if profile.get(g, 0) > 0)
                reason = ('Điểm dự đoán SVD từ lịch sử tương tác' if has_svd
                          else 'Điểm cộng đồng có điều chỉnh theo số lượt đánh giá')
                if self.ranking_model is not None:
                    reason=f'Xếp hạng {self.serving_name}, chọn trên validation'
                if strategy == 'catalog_fallback':
                    reason = 'Khám phá danh mục; chưa có mô hình hoặc thống kê đánh giá'
                if matching:
                    reason += '; phù hợp với ' + ', '.join(matching[:3])
                if self.ranking_model is not None and not getattr(self.ranking_model,'supports_rating_prediction',False):
                    item['predicted_rating']=None
                recommendations.append({**self.movies[mid], **item, 'strategy': strategy,
                                        'reason': reason, 'matched_genres': matching})
            result = {'strategy': strategy, 'stage': stage, 'history_count': len(history),
                      'model_available': self.model is not None, 'candidate_count': len(candidates),
                      'genre_weight': 0.2, 'diversity_weight': diversity,
                      'recommendations': recommendations}
            if len(self.recommendations_cache) >= 1000:
                self.recommendations_cache.pop(next(iter(self.recommendations_cache)))
            self.recommendations_cache[cache_key] = (now, result)
            return {**result, 'recommendations': recommendations[:limit]}

    def get_recommendations(self, user_id, limit=10):
        return self.get_recommendation_result(user_id, limit)['recommendations']

    def reload_model(self):
        self.initialize(force=True)
