"""Các baseline và hybrid nghiên cứu dùng chung candidate set, không đọc holdout."""

from collections import defaultdict

import numpy as np
from scipy import sparse
from scipy.stats import rankdata

from src.models.hybrid import parse_genres
from src.models.interfaces import SerializableModel


def percentile(scores):
    values = np.asarray(scores, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Điểm mô hình không hữu hạn')
    return (rankdata(values, method='average') - 1) / max(1, len(values) - 1)


class ItemStatistics(SerializableModel):
    supports_rating_prediction = True

    def __init__(self, mode='bayesian'):
        self.mode = mode
        self.supports_rating_prediction = mode in {'bayesian', 'mean', 'bias'}

    def fit(self, ratings):
        self.mean = float(ratings.rating.mean())
        groups = ratings.groupby('movieId').rating.agg(['count', 'mean'])
        if self.mode == 'count':
            self.scores = groups['count'].to_dict()
        elif self.mode == 'bayesian':
            self.scores = ((groups['count'] * groups['mean'] + 5 * self.mean) / (groups['count'] + 5)).to_dict()
        else:
            self.scores = {}
        self.user_bias, self.item_bias = {}, {}
        if self.mode == 'bias':
            # Ước lượng luân phiên có regularization, chỉ từ dữ liệu fit.
            work = ratings[['userId', 'movieId', 'rating']].copy()
            for _ in range(10):
                residual = work.rating - self.mean - work.userId.map(self.user_bias).fillna(0)
                sums = residual.groupby(work.movieId).sum()
                self.item_bias = (sums / (work.movieId.value_counts() + 10)).to_dict()
                residual = work.rating - self.mean - work.movieId.map(self.item_bias).fillna(0)
                sums = residual.groupby(work.userId).sum()
                self.user_bias = (sums / (work.userId.value_counts() + 10)).to_dict()
        return self

    def score_items(self, user_id, movie_ids):
        if self.mode == 'bias':
            return np.clip([self.mean + self.user_bias.get(user_id, 0) + self.item_bias.get(int(i), 0)
                            for i in movie_ids], .5, 5)
        if self.mode == 'mean':
            return np.full(len(movie_ids), self.mean)
        return np.array([self.scores.get(int(i), 0 if self.mode == 'count' else self.mean) for i in movie_ids])

    def predict(self, user_id, movie_id):
        return float(self.score_items(user_id, [movie_id])[0])


class GenreContent(SerializableModel):
    supports_rating_prediction = False

    def __init__(self, movies):
        self.movie_genres = {int(r.movieId): parse_genres(r.genres) for r in movies.itertuples()}

    def fit(self, ratings):
        self.catalog = sorted(ratings.movieId.unique().astype(int))
        self.index = {m: i for i, m in enumerate(self.catalog)}
        vocabulary = sorted(set().union(*(self.movie_genres.get(m, set()) for m in self.catalog)))
        self.vocabulary = vocabulary
        self.features = np.array([[float(g in self.movie_genres.get(m, set())) for g in vocabulary]
                                  for m in self.catalog], dtype=np.float32)
        norms = np.linalg.norm(self.features, axis=1, keepdims=True)
        self.features /= np.maximum(norms, 1)
        self.profiles = {}
        positives = ratings[ratings.rating >= 3.5]
        for uid, group in positives.groupby('userId', sort=False):
            indices = [self.index[int(mid)] for mid in group.movieId]
            vector = (self.features[indices] * (group.rating.to_numpy() - 3)[:, None]).sum(axis=0)
            self.profiles[int(uid)] = vector / max(float(np.linalg.norm(vector)), 1e-12)
        self.fallback = ItemStatistics().fit(ratings)
        return self

    def score_items(self, user_id, movie_ids):
        if user_id not in self.profiles:
            return self.fallback.score_items(user_id, movie_ids)
        indices = np.array([self.index[int(m)] for m in movie_ids], dtype=int)
        return self.features[indices] @ self.profiles[user_id]


class SparseItemKNN(SerializableModel):
    supports_rating_prediction = False

    def __init__(self, neighbors=100, shrinkage=10, check=lambda: None):
        self.neighbors, self.shrinkage, self.check = neighbors, shrinkage, check

    def fit(self, ratings):
        self.catalog = sorted(ratings.movieId.unique().astype(int))
        self.index = {m: i for i, m in enumerate(self.catalog)}
        self.users = {int(u): i for i, u in enumerate(sorted(ratings.userId.unique()))}
        positives = ratings[ratings.rating >= 3.5]
        ui = sparse.csr_matrix((np.ones(len(positives), dtype=np.float32),
                               (positives.userId.map(self.users), positives.movieId.map(self.index))),
                              shape=(len(self.users), len(self.catalog)))
        item_user = ui.T.tocsr()
        norms = np.sqrt(item_user.getnnz(axis=1)).astype(np.float32)
        rows, columns, values = [], [], []
        # Bloc 64 × danh mục; không tạo similarity dense toàn cục.
        for start in range(0, len(self.catalog), 64):
            self.check()
            block = (item_user[start:start+64] @ item_user.T).tocsr()
            for local in range(block.shape[0]):
                row = start + local
                begin, end = block.indptr[local:local+2]
                indices, counts = block.indices[begin:end], block.data[begin:end]
                mask = indices != row
                indices, counts = indices[mask], counts[mask]
                scores = counts / np.maximum(norms[row] * norms[indices], 1)
                scores *= counts / (counts + self.shrinkage)
                if len(scores) > self.neighbors:
                    selected = np.argpartition(-scores, self.neighbors - 1)[:self.neighbors]
                    # Bao gồm tie ở ngưỡng để tie-break theo ID luôn tái lập.
                    selected = np.flatnonzero(scores >= scores[selected].min())
                else:
                    selected = np.arange(len(scores))
                selected = selected[np.lexsort((indices[selected], -scores[selected]))[:self.neighbors]]
                rows.extend([row] * len(selected))
                columns.extend(indices[selected].tolist())
                values.extend(scores[selected].tolist())
        self.similarity = sparse.csr_matrix((np.array(values, dtype=np.float32), (rows, columns)),
                                            shape=(len(self.catalog), len(self.catalog)))
        self.histories = ui
        self.fallback = ItemStatistics().fit(ratings)
        return self

    def score_items(self, user_id, movie_ids):
        if user_id not in self.users:
            return self.fallback.score_items(user_id, movie_ids)
        history = self.histories[self.users[user_id]]
        if not history.nnz:
            return self.fallback.score_items(user_id, movie_ids)
        scores = (history @ self.similarity).toarray().ravel()
        return scores[[self.index[int(mid)] for mid in movie_ids]]


class HybridRanker(SerializableModel):
    supports_rating_prediction = False

    def __init__(self, svd, content, popularity, counts, tau=20, beta=.5, mode='adaptive'):
        self.svd, self.content, self.popularity = svd, content, popularity
        self.counts, self.tau, self.beta, self.mode = counts, tau, beta, mode

    def score_items(self, user_id, movie_ids):
        n = self.counts.get(user_id, 0)
        pop = self.popularity.score_items(user_id, movie_ids)
        if self.mode == 'svd_fallback':
            return self.svd.score_items(user_id, movie_ids) if n else pop
        if not n:
            return percentile(pop)
        w = .8 if self.mode == 'fixed' else n / (n + self.tau)
        beta = self.beta if user_id in self.content.profiles else 0
        return (w * percentile(self.svd.score_items(user_id, movie_ids))
                + (1-w) * (beta * percentile(self.content.score_items(user_id, movie_ids))
                           + (1-beta) * percentile(pop)))
