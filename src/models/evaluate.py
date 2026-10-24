"""Đánh giá rating và Top-K trên toàn bộ ứng viên TRAIN chưa tương tác.

Lấy mẫu người dùng để giới hạn chi phí, không lấy mẫu phim âm tính.
Khoảng tin cậy bootstrap người dùng chỉ phản ánh bất định trên mẫu cố định.
"""

from collections import defaultdict
from itertools import combinations

import numpy as np

from src.models.hybrid import genre_profile, rank_hybrid


def rating_metrics(model, train_df, evaluation_df):
    """RMSE/MAE và nhóm user thực sự chưa xuất hiện, ít và nhiều lịch sử."""
    if evaluation_df.empty:
        raise ValueError('Tập đánh giá không được rỗng')
    counts = train_df.userId.value_counts().to_dict()
    groups = defaultdict(list)
    errors = []
    unknown_items = set(evaluation_df.movieId) - set(train_df.movieId)
    for row in evaluation_df.itertuples():
        error = float(row.rating) - float(model.predict(int(row.userId), int(row.movieId)))
        if not np.isfinite(error):
            raise ValueError('Dự đoán không hữu hạn')
        errors.append(error)
        count = counts.get(row.userId, 0)
        group = 'cold_0' if count == 0 else ('sparse_1_4' if count < 5 else ('warm_5_20' if count <= 20 else 'heavy_21_plus'))
        groups[group].append(error)
    def summarize(values):
        values = np.asarray(values)
        return {'RMSE': float(np.sqrt(np.mean(values ** 2))), 'MAE': float(np.mean(np.abs(values))), 'ratings': len(values)}
    return {**summarize(errors), 'groups': {g: summarize(v) for g, v in groups.items()},
            'cold_item_ratings': int(evaluation_df.movieId.isin(unknown_items).sum())}


def ranking_metrics(recommended, relevant, k):
    """Relevance nhị phân; user không có positive không được tính Recall=1."""
    if k < 1:
        raise ValueError('K phải lớn hơn 0')
    if not relevant:
        return {'precision': 0.0, 'recall': 0.0, 'ndcg': 0.0, 'hit_rate': 0.0}
    hits = np.array([mid in relevant for mid in recommended[:k]], dtype=float)
    dcg = float(np.sum(hits / np.log2(np.arange(len(hits)) + 2)))
    idcg = float(np.sum(1 / np.log2(np.arange(min(k, len(relevant))) + 2)))
    return {'precision': float(hits.sum() / k), 'recall': float(hits.sum() / len(relevant)),
            'ndcg': dcg / idcg, 'hit_rate': float(hits.any())}


def _bootstrap(values, seed=42, samples=1000):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return None
    rng = np.random.default_rng(seed)
    means = np.mean(values[rng.integers(0, len(values), size=(samples, len(values)))], axis=1)
    return [float(x) for x in np.quantile(means, [0.025, 0.975])]


def evaluate_ranking(model, train_df, evaluation_df, movie_genres, *, k=10, threshold=3.5,
                     max_users=300, seed=42, genre_weight=0.0, diversity_weight=0.0,
                     exclude_df=None):
    """Dùng cùng ứng viên, user, threshold cho mọi mô hình; không nhìn nhãn tương lai."""
    if max_users < 1 or k < 1:
        raise ValueError('Số user và K phải lớn hơn 0')
    catalog = sorted(set(int(mid) for mid in train_df.movieId))
    catalog_set = set(catalog)
    histories = {int(uid): list(zip(group.movieId.astype(int), group.rating.astype(float)))
                 for uid, group in train_df.groupby('userId', sort=False)}
    exclusions = {uid: {mid for mid, _ in history} for uid, history in histories.items()}
    if exclude_df is not None:
        for uid, group in exclude_df.groupby('userId'):
            exclusions.setdefault(int(uid), set()).update(int(mid) for mid in group.movieId)
    truth = {}
    positive_count, unavailable = 0, 0
    for uid, group in evaluation_df[evaluation_df.rating >= threshold].groupby('userId'):
        positives = set(int(mid) for mid in group.movieId) - exclusions.get(int(uid), set())
        positive_count += len(positives)
        unavailable += len(positives - catalog_set)
        relevant = positives & catalog_set
        if relevant:
            truth[int(uid)] = relevant
    eligible = np.array(sorted(truth), dtype=int)
    if not len(eligible):
        raise ValueError('Không có user có positive trong danh mục TRAIN để đánh giá xếp hạng')
    users = sorted(np.random.default_rng(seed).choice(eligible, size=min(max_users, len(eligible)), replace=False).tolist())
    item_counts = train_df.movieId.value_counts().to_dict()
    total = len(train_df)
    rows, recommended_union = [], set()
    for uid in users:
        history = histories.get(uid, [])
        candidates = [mid for mid in catalog if mid not in exclusions.get(uid, set())]
        scores = model.score_items(uid, candidates) if hasattr(model, 'score_items') else [model.predict(uid, mid) for mid in candidates]
        profile = genre_profile(history, movie_genres)
        ranked = rank_hybrid(candidates, scores, movie_genres, profile, n=k,
                             genre_weight=genre_weight, diversity_weight=diversity_weight)
        ids = [item['movieId'] for item in ranked]
        metrics = ranking_metrics(ids, truth[uid], k)
        distances = []
        for a, b in combinations(ids, 2):
            ga, gb = movie_genres.get(a, frozenset()), movie_genres.get(b, frozenset())
            distances.append(1 - len(ga & gb) / max(1, len(ga | gb)))
        metrics['diversity'] = float(np.mean(distances)) if distances else 0.0
        metrics['novelty'] = float(np.mean([-np.log2(item_counts[mid] / total) for mid in ids])) if ids else 0.0
        metrics.update(user_id=uid, group='cold_0' if not history else 'known_user')
        rows.append(metrics)
        recommended_union.update(ids)
    names = ['precision', 'recall', 'ndcg', 'hit_rate', 'diversity', 'novelty']
    result = {name: float(np.mean([row[name] for row in rows])) for name in names}
    result.update(k=k, threshold=threshold, users=len(users), eligible_users=len(eligible),
                  sampled_user_ids=users, candidate_policy='all_train_items_minus_prior_history',
                  catalog_size=len(catalog), coverage=len(recommended_union) / len(catalog),
                  unavailable_positive_fraction=unavailable / positive_count if positive_count else 0,
                  ci95={name: _bootstrap([row[name] for row in rows], seed) for name in names},
                  groups={group: {'users': len(group_rows), **{
                      name: float(np.mean([r[name] for r in group_rows])) for name in names}}
                      for group in ['cold_0', 'known_user'] if (group_rows := [r for r in rows if r['group'] == group])})
    return result


def evaluate_model_pipeline(model, train_df, test_df, movie_genres=None, max_users=300):
    """Tương thích mã gọi cũ, sử dụng giao thức Top-K đã sửa."""
    rating = rating_metrics(model, train_df, test_df)
    ranking = evaluate_ranking(model, train_df, test_df, movie_genres or {}, max_users=max_users)
    return {**rating, 'Precision@10': ranking['precision'], 'Recall@10': ranking['recall'],
            'NDCG@10': ranking['ndcg'], 'Catalog_Coverage': ranking['coverage'], 'ranking': ranking}
