"""Các phép xếp hạng dùng chung cho thực nghiệm và phục vụ khuyến nghị."""

import re
from collections import Counter

import numpy as np


class HybridRatingModel:
    """SVD cho user đã học; Bayesian popularity cho user chưa có vector."""

    def __init__(self, svd, popularity, known_users):
        self.svd, self.popularity, self.known_users = svd, popularity, set(known_users)

    def predict(self, user_id, movie_id):
        model = self.svd if user_id in self.known_users else self.popularity
        return model.predict(user_id, movie_id)

    def score_items(self, user_id, movie_ids):
        if user_id in self.known_users:
            return self.svd.score_items(user_id, movie_ids)
        return np.array([self.popularity.predict(user_id, mid) for mid in movie_ids], dtype=float)


def parse_genres(value) -> frozenset[str]:
    """Đọc đúng cả định dạng MovieLens và CSV đã tiền xử lý."""
    if not isinstance(value, str):
        return frozenset()
    return frozenset(g.strip() for g in re.split(r"[|,]", value)
                     if g.strip() and g.strip() != "(no genres listed)")


def genre_profile(ratings, movie_genres, preferences=()) -> dict[str, float]:
    """Chỉ dùng lịch sử đã biết; đánh giá thấp không suy thành sở thích."""
    weights = Counter({g: 2.0 for g in preferences})
    for mid, rating in ratings:
        if rating >= 3.5:
            for genre in movie_genres.get(int(mid), ()):
                weights[genre] += float(rating) - 3.0
    return dict(weights)


def rank_hybrid(movie_ids, scores, movie_genres, profile, n=10,
                genre_weight=0.2, diversity_weight=0.1, pool_size=200):
    """Kết hợp điểm trong [0,1] và MMR trên pool; không diễn giải là xác suất.

    MMR = (1-d)*điểm_kết_hợp - d*max(Jaccard với phim đã chọn).
    Pool gồm các phim có điểm kết hợp cao nhất, không giới hạn ở top popularity.
    """
    if not 0 <= genre_weight <= 1 or not 0 <= diversity_weight <= 1:
        raise ValueError("Trọng số phải thuộc khoảng [0,1]")
    if n < 1:
        return []
    mids = np.asarray(movie_ids, dtype=int)
    values = np.asarray(scores, dtype=float)
    if len(mids) != len(values) or not np.isfinite(values).all():
        raise ValueError("Điểm phải hữu hạn và khớp số ứng viên")
    if len(mids) == 0:
        return []
    maximum = max(profile.values(), default=0.0)
    affinities = np.array([
        sum(profile.get(g, 0.0) for g in movie_genres.get(int(mid), ()))
        / (max(1, len(movie_genres.get(int(mid), ()))) * maximum)
        if maximum else 0.0 for mid in mids
    ])
    alpha = genre_weight if maximum else 0.0
    combined = (1 - alpha) * (np.clip(values, 0.5, 5) - 0.5) / 4.5 + alpha * affinities
    order = np.lexsort((mids, -combined))[:max(pool_size, n)]
    if diversity_weight == 0:
        return [{'movieId': int(mids[i]), 'predicted_rating': float(np.clip(values[i], 0.5, 5)),
                 'ranking_score': float(combined[i]), 'genre_affinity': float(affinities[i]),
                 'mmr_score': float(combined[i])} for i in order[:n]]
    remaining = order.tolist()
    selected = []
    results = []
    while remaining and len(selected) < n:
        def mmr(index):
            genres = movie_genres.get(int(mids[index]), frozenset())
            similarities = []
            for prior in selected:
                other = movie_genres.get(int(mids[prior]), frozenset())
                similarities.append(len(genres & other) / max(1, len(genres | other)))
            return (1 - diversity_weight) * combined[index] - diversity_weight * max(similarities, default=0)
        best = max(remaining, key=lambda i: (mmr(i), -int(mids[i])))
        results.append({"movieId": int(mids[best]), "predicted_rating": float(np.clip(values[best], 0.5, 5)),
                        "ranking_score": float(combined[best]), "genre_affinity": float(affinities[best]),
                        "mmr_score": float(mmr(best))})
        selected.append(best)
        remaining.remove(best)
    return results
