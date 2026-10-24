"""Kiểm tra phản ví dụ của giao thức, không phụ thuộc dữ liệu MovieLens local."""

import numpy as np
import pandas as pd
import pytest

from src.data.protocol import normalize_ratings, temporal_split
from src.models.baseline import MeanRecommender, PopularityRecommender
from src.models.evaluate import evaluate_ranking, ranking_metrics
from src.models.hybrid import parse_genres, rank_hybrid
from src.models.svd_surprise import SurpriseSVDRecommender
from src.pipeline.retrain import promotion_decision
from src.models.train_pipeline import run_experiment


def test_temporal_ties_are_not_split():
    df = pd.DataFrame({'userId': range(1, 21), 'movieId': range(1, 21),
                       'rating': [4] * 20, 'timestamp': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 16, 18, 19, 20]})
    train, val, test = temporal_split(df)
    assert train.timestamp.max() < val.timestamp.min() < test.timestamp.min()
    assert len(train) + len(val) + len(test) == len(df)
    assert temporal_split(df.sample(frac=1, random_state=7))[0].equals(train)


def test_mixed_epoch_and_iso_timestamps():
    df = pd.DataFrame({'userId': [1, 2], 'movieId': [1, 2], 'rating': [3, 4],
                       'timestamp': [946684800, '2001-01-01T00:00:00+00:00']})
    assert normalize_ratings(df).timestamp.dt.year.tolist() == [2000, 2001]


@pytest.mark.parametrize('field,value', [('rating', np.nan), ('rating', 5.5), ('userId', 1.5), ('timestamp', 'invalid')])
def test_bad_data_is_rejected(field, value):
    row = {'userId': 1, 'movieId': 1, 'rating': 4, 'timestamp': '2000-01-01'}
    row[field] = value
    with pytest.raises((ValueError, TypeError)):
        normalize_ratings(pd.DataFrame([row]))


def test_no_positive_recall_is_zero():
    assert ranking_metrics([1, 2], set(), 2)['recall'] == 0
    assert ranking_metrics([1, 9], {1, 2}, 2) == pytest.approx(
        {'precision': 0.5, 'recall': 0.5, 'ndcg': 1 / (1 + 1 / np.log2(3)), 'hit_rate': 1})


def test_ranking_must_compete_with_unobserved_catalog_items():
    train = pd.DataFrame({'userId': [1, 2, 2], 'movieId': [1, 2, 3], 'rating': [5, 1, 5]})
    heldout = pd.DataFrame({'userId': [1], 'movieId': [2], 'rating': [5]})
    class Model:
        def predict(self, uid, mid):
            return {1: 5, 2: 3, 3: 4}[mid]
    result = evaluate_ranking(Model(), train, heldout, {}, k=1)
    assert result['recall'] == 0  # Chỉ xếp hạng các dòng TEST sẽ cho recall=1 sai.
    assert result['catalog_size'] == 3


def test_validation_history_is_excluded_from_test_candidates():
    train = pd.DataFrame({'userId': [1, 2, 2], 'movieId': [1, 2, 3], 'rating': [5, 1, 5]})
    val = pd.DataFrame({'userId': [1], 'movieId': [3], 'rating': [5]})
    test = pd.DataFrame({'userId': [1], 'movieId': [2], 'rating': [5]})
    result = evaluate_ranking(MeanRecommender().fit(train), train, test, {}, k=1, exclude_df=val)
    assert result['recall'] == 1


def test_popularity_can_return_more_than_twenty_movies():
    frame = pd.DataFrame({'userId': [1] * 40, 'movieId': range(40), 'rating': [4] * 40})
    assert len(PopularityRecommender().fit(frame).recommend(2, n=35)) == 35


def test_genre_preferences_search_the_whole_candidate_pool():
    genres = {1: parse_genres('Action, Comedy'), 2: parse_genres('Drama'), 3: parse_genres('Drama|Romance')}
    ranked = rank_hybrid([1, 2, 3], [4.9, 4.0, 3.9], genres, {'Drama': 1}, genre_weight=0.8, diversity_weight=0)
    assert ranked[0]['movieId'] == 2
    assert len(ranked) == 3


def test_mmr_can_reduce_genre_repetition_and_is_deterministic():
    genres = {1: parse_genres('Action'), 2: parse_genres('Action'), 3: parse_genres('Drama')}
    plain = rank_hybrid([1, 2, 3], [4.8, 4.7, 4.6], genres, {}, n=2, diversity_weight=0)
    diverse = rank_hybrid([1, 2, 3], [4.8, 4.7, 4.6], genres, {}, n=2, diversity_weight=0.3)
    assert [v['movieId'] for v in plain] == [1, 2]
    assert [v['movieId'] for v in diverse] == [1, 3]


@pytest.mark.parametrize('new,old,accepted', [({}, {}, False), ({'RMSE': np.nan}, {'RMSE': 1}, False),
    ({'RMSE': 0.9}, {'RMSE': 1}, True), ({'RMSE': 1.1}, {'RMSE': 1}, False),
    ({'RMSE': 1}, None, True), ({'RMSE': 1}, {'RMSE': np.inf}, False)])
def test_promotion_gate_requires_finite_comparable_metrics(new, old, accepted):
    assert bool(promotion_decision(new, old)) is accepted


def test_svd_vectorized_scores_match_scalar_for_unknown_items_and_online_users():
    df = pd.DataFrame({'userId': [1, 1, 2, 2], 'movieId': [1, 2, 1, 3], 'rating': [5, 4, 1, 2]})
    model = SurpriseSVDRecommender(n_factors=3, n_epochs=2).fit(df)
    model.online_update(200000, 1, 5)
    for uid in [1, 200000, 999]:
        scores = model.score_items(uid, [1, 2, 999])
        assert scores == pytest.approx([model.predict(uid, mid) for mid in [1, 2, 999]])
        assert np.isfinite(scores).all()
        assert ((0.5 <= scores) & (scores <= 5)).all()


def test_experiment_is_reproducible_without_mutating_source_data(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    pairs = [(uid, mid) for uid in range(1, 5) for mid in range(1, 11)]
    np.random.default_rng(42).shuffle(pairs)
    frame = pd.DataFrame([{'userId': uid, 'movieId': mid, 'rating': 4, 'timestamp': 946684800 + i}
                          for i, (uid, mid) in enumerate(pairs)])
    ratings_path = data / 'ratings_processed.csv'
    frame.to_csv(ratings_path, index=False)
    pd.DataFrame({'movieId': range(1, 11), 'genres': ['Drama'] * 10}).to_csv(data / 'movies_processed.csv', index=False)
    before = ratings_path.read_bytes()
    first = run_experiment(data, tmp_path / 'one', seeds=[42], ranking_users=4, epochs=1, factors=2)
    second = run_experiment(data, tmp_path / 'two', seeds=[42], ranking_users=4, epochs=1, factors=2)
    assert first['results'] == second['results']
    assert first['dataset'] == second['dataset']
    assert before == ratings_path.read_bytes()
    assert list(data.glob('ratings_train.csv')) == []
    assert (tmp_path / 'one/latest.json').exists()


def test_runtime_feedback_does_not_repartition_or_write_holdout(tmp_path, monkeypatch):
    import src.data.merge_interactions as merge
    base = pd.DataFrame({'userId': range(1, 21), 'movieId': [1] * 20,
                         'rating': [4] * 20, 'timestamp': range(946684800, 946684820)})
    source = tmp_path / 'ratings_processed.csv'
    base.to_csv(source, index=False)
    for name in ['val', 'test']:
        (tmp_path / f'ratings_{name}.csv').write_bytes(b'holdout-do-not-rewrite')
    feedback = pd.DataFrame([{'userId': 200000, 'movieId': 1, 'rating': 4.5,
                              'timestamp': '2026-10-15', 'source': 'explicit'}])
    monkeypatch.setattr(merge, 'RATINGS_PROCESSED_CSV', source)
    monkeypatch.setattr(merge, 'PROCESSED_DIR', tmp_path)
    monkeypatch.setattr(merge, 'read_feedback', lambda: feedback)
    _, expected_val, expected_test = temporal_split(base)
    train, val, test = merge.build_runtime_data()
    assert 200000 in train.userId.values
    assert val.equals(expected_val) and test.equals(expected_test)
    merge.merge_and_split(verbose=False)
    merge.merge_and_split(verbose=False)
    assert len(pd.read_csv(tmp_path / 'ratings_train.csv')) == 17
    for name in ['val', 'test']:
        assert (tmp_path / f'ratings_{name}.csv').read_bytes() == b'holdout-do-not-rewrite'
