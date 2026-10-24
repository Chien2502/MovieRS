"""Đánh giá cửa sổ tương lai tĩnh; positive ngoài catalog không bị loại khỏi headline."""

from itertools import combinations
from time import perf_counter

import numpy as np
import pandas as pd

from src.models.evaluate import ranking_metrics


def cohort(n):
    return 'cold_0' if n == 0 else ('sparse_1_4' if n < 5 else ('warm_5_19' if n < 20 else 'heavy_20_plus'))


class EvaluationContext:
    def __init__(self, fit, evaluation, movie_genres, max_users=1000, seed=42, threshold=3.5):
        self.fit, self.evaluation, self.genres = fit, evaluation, movie_genres
        self.catalog = np.array(sorted(fit.movieId.unique()), dtype=int)
        self.catalog_set = set(self.catalog.tolist())
        self.histories = {int(u): set(g.movieId.astype(int)) for u, g in fit.groupby('userId', sort=False)}
        self.counts = fit.userId.value_counts().to_dict()
        self.truth = {int(u): set(g.movieId.astype(int)) for u, g in evaluation[evaluation.rating >= threshold].groupby('userId')}
        eligible = sorted(self.truth)
        if not eligible:
            raise ValueError('Không có user có positive để chấm ranking')
        self.users = sorted(np.random.default_rng(seed).choice(eligible, size=min(max_users, len(eligible)), replace=False).tolist())
        self.eligible = len(eligible)
        self.no_positive_users = len(set(evaluation.userId) - set(eligible))
        self.popularity = fit.movieId.value_counts().to_dict()
        self.unavailable = sum(len(v - self.catalog_set) for v in self.truth.values()) / sum(map(len, self.truth.values()))

    def candidates(self, user_id):
        return self.catalog[~np.isin(self.catalog, list(self.histories.get(user_id, set())))]


def select_topk(ids, scores, k, genres, mmr=0, pool_size=200):
    ids, scores = np.asarray(ids), np.asarray(scores, dtype=float)
    if len(scores) != len(ids) or not np.isfinite(scores).all():
        raise ValueError('Điểm không hữu hạn hoặc không khớp ứng viên')
    if len(np.unique(ids)) != len(ids):
        raise ValueError('Candidate có ID trùng')
    order = np.lexsort((ids, -scores))
    if not mmr:
        return ids[order[:k]].tolist()
    remaining = order[:max(k, pool_size)].tolist()
    selected = []
    while remaining and len(selected) < k:
        def value(i):
            g = genres.get(int(ids[i]), set())
            similarity = max((len(g & genres.get(int(ids[j]), set())) /
                              max(1, len(g | genres.get(int(ids[j]), set()))) for j in selected), default=0)
            return (1-mmr) * scores[i] - mmr * similarity
        best = max(remaining, key=lambda i: (value(i), -int(ids[i])))
        selected.append(best)
        remaining.remove(best)
    return ids[selected].tolist()


def evaluate_ranker(model, context, model_name, seed=None, k=10, mmr=0, check=lambda: None):
    rows, union, times = [], set(), []
    for uid in context.users:
        check()
        ids = context.candidates(uid)
        started = perf_counter()
        scores = model.score_items(uid, ids)
        ranked = select_topk(ids, scores, max(k,20), context.genres, mmr)
        top = ranked[:k]
        times.append((perf_counter()-started)*1000)
        union.update(top)
        truth = context.truth[uid]
        main = ranking_metrics(top, truth, k)
        servable = truth & context.catalog_set
        conditional = ranking_metrics(top, servable, k) if servable else None
        distances = []
        for a, b in combinations(top, 2):
            ga, gb = context.genres.get(a, set()), context.genres.get(b, set())
            distances.append(1-len(ga & gb)/max(1, len(ga | gb)))
        secondary={f'{metric}_at_{cutoff}':value for cutoff in [5,20]
                   for metric,value in ranking_metrics(ranked,truth,cutoff).items()}
        rows.append({'model': model_name, 'seed': seed, 'user_id': uid, 'cohort': cohort(context.counts.get(uid, 0)),
                     **main, 'conditional_ndcg': conditional['ndcg'] if conditional else None,
                     **secondary,
                     'positive_count': len(truth), 'servable_positive_count': len(servable),
                     'diversity': float(np.mean(distances)) if distances else 0,
                     'novelty': float(np.mean([-np.log2(context.popularity[m]/len(context.fit)) for m in top])) if top else 0,
                     'recommended_ids': top})
    frame = pd.DataFrame(rows)
    metrics = ['ndcg','precision','recall','hit_rate','diversity','novelty']
    summary = {key: float(frame[key].mean()) for key in metrics}
    summary.update(coverage=len(union)/len(context.catalog), users=len(rows), eligible_users=context.eligible,
                   users_without_positive=context.no_positive_users, unavailable_positive_fraction=context.unavailable,
                   conditional_ndcg=float(frame.conditional_ndcg.mean()) if frame.conditional_ndcg.notna().any() else None,
                   latency_ms={'p50':float(np.quantile(times,.5)), 'p95':float(np.quantile(times,.95))},
                   cohorts={c:{'users':len(g), **{m:float(g[m].mean()) for m in metrics}}
                            for c,g in frame.groupby('cohort')})
    return summary, frame


def rating_evaluation(model, fit, evaluation, check=lambda: None):
    if not getattr(model, 'supports_rating_prediction', False):
        return None
    predictions = []
    counts = fit.userId.value_counts().to_dict()
    known_items = set(fit.movieId)
    for uid, group in evaluation.groupby('userId', sort=False):
        check()
        scores = model.score_items(int(uid), group.movieId.to_numpy())
        errors = group.rating.to_numpy() - scores
        if not np.isfinite(errors).all():
            raise ValueError('Dự đoán rating không hữu hạn')
        predictions.append(pd.DataFrame({'error':errors, 'cohort':cohort(counts.get(uid, 0)),
                                         'cold_item':~group.movieId.isin(known_items).to_numpy()}))
    frame = pd.concat(predictions, ignore_index=True)
    def stats(g):
        return {'RMSE':float(np.sqrt(np.mean(g.error**2))), 'MAE':float(np.mean(np.abs(g.error))), 'rows':len(g)}
    return {**stats(frame), 'cohorts':{c:stats(g) for c,g in frame.groupby('cohort')},
            'item_groups':{('cold' if c else 'known'):stats(g) for c,g in frame.groupby('cold_item')}}
