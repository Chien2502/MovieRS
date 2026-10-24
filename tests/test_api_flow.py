"""Kiểm tra luồng API trên tệp tạm; không ghi tài khoản, model hoặc CSV thật."""

import os
from concurrent.futures import ThreadPoolExecutor

os.environ['AUTO_RETRAIN'] = '0'

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import movies, users, watch
from api.services import feedback_store, user_store, watch_store
from api.services.recommender import RecommenderService
import api.services.recommender as recommender


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    catalog = pd.DataFrame([{'movieId': i, 'title': f'Phim {i}', 'genres': 'Drama' if i > 25 else 'Action',
                             'poster_path': '', 'overview': 'Mô tả', 'vote_average': 0, 'runtime_minutes': 100}
                            for i in range(1, 61)])
    movie_path = tmp_path / 'movies.csv'
    catalog.to_csv(movie_path, index=False)
    train = pd.DataFrame({'userId': [1] * 60, 'movieId': list(range(1, 61)), 'rating': [4.5] * 25 + [4] * 34 + [5]})
    train_path = tmp_path / 'train.csv'
    train.to_csv(train_path, index=False)
    monkeypatch.setattr(recommender, 'MOVIES_CSV', movie_path)
    monkeypatch.setattr(recommender, 'TRAIN_RATINGS_CSV', train_path)
    monkeypatch.setattr(recommender, 'MODEL_PATH', tmp_path / 'missing.pkl')
    monkeypatch.setattr(movies, 'MOVIES_CSV', movie_path)
    monkeypatch.setattr(movies, 'movies_df', None)
    monkeypatch.setattr(users, 'MOVIES_CSV', movie_path)
    monkeypatch.setattr(watch, 'MOVIES_CSV', movie_path)
    monkeypatch.setattr(user_store, 'USERS_FILE', tmp_path / 'users.json')
    monkeypatch.setattr(users, 'FAVORITES_CSV', tmp_path / 'favorites.csv')
    monkeypatch.setattr(feedback_store, 'INTERACTIONS_LOG_CSV', tmp_path / 'feedback.csv')
    monkeypatch.setattr(watch_store, 'WATCH_PROGRESS_CSV', tmp_path / 'watch.csv')
    service = RecommenderService()
    monkeypatch.setattr(service, 'initialized', False)
    with TestClient(app) as client:
        response = client.post('/api/auth/register', json={'username': 'tester', 'password': '12345678', 'genres': ['Drama']})
        assert response.status_code == 201
        client.headers['Authorization']='Bearer '+response.json()['access_token']
        yield client, response.json()['user_id'], service


def test_onboarding_limit_cache_preferences_and_catalog(runtime):
    client, uid, service = runtime
    first = client.get(f'/api/recommendations/{uid}?limit=2').json()
    assert first['strategy'] == 'genre_popularity'
    assert first['stage'] == 'cold_start'
    assert all('Drama' in movie['genres'] for movie in first['recommendations'])
    larger = client.get(f'/api/recommendations/{uid}?limit=35').json()
    assert larger['count'] == 35
    assert larger['recommendations'][:2] == first['recommendations']
    client.put(f'/api/users/{uid}/preferences', json={'genres': ['Action']})
    changed = client.get(f'/api/recommendations/{uid}').json()
    assert changed['recommendations'][0]['movieId'] != first['recommendations'][0]['movieId']
    assert changed['recommendations'][0]['genres'] == 'Action'
    assert client.get('/api/movies/popular').json()['results'][0]['movieId'] == 60


def test_file_idempotency_replay_does_not_undo_newer_state(runtime):
    client,uid,_=runtime
    body={'userId':uid,'movieId':2,'rating':1.5}
    header={'Idempotency-Key':'file-rating-first'}
    assert client.post('/api/interactions/rating',json=body,headers=header).status_code==200
    assert client.post('/api/interactions/rating',json={**body,'rating':4.5}).status_code==200
    assert client.post('/api/interactions/rating',json=body,headers=header).json()['changed'] is False
    assert feedback_store.read_feedback().iloc[0].rating==4.5
    assert client.post('/api/interactions/rating',json={**body,'rating':2},headers=header).status_code==409


def test_v2_catalog_keeps_movie_without_tmdb_metadata(runtime,monkeypatch):
    _,_,service=runtime
    from src.models.research import ItemStatistics
    import api.services.serving as serving
    history=pd.DataFrame({'userId':[1]*61,'movieId':range(1,62),'rating':[4]*61})
    catalog=pd.DataFrame({'movieId':range(1,62),'title':[f'Gốc {i}' for i in range(1,62)],'genres':['Drama']*61})
    bundle={'model':ItemStatistics('count').fit(history),'history':history,'spec':{'family':'MostPopular'},'catalog':catalog}
    monkeypatch.setenv('MOVIERS_SERVING_POINTER','test/current.json')
    monkeypatch.setattr(serving,'load_bundle',lambda *args:(bundle,{'version':'fixture'}))
    service.initialize(force=True)
    assert 61 in service.candidate_ids
    assert service.movies[61]['runtime_source']=='simulation_default'
    assert service.movies[1]['title']=='Gốc 1'
    assert 61 in movies.get_movies_df().movieId.to_list()


def test_explicit_rating_survives_watch_favorite_and_retry(runtime):
    client, uid, service = runtime
    rating = {'userId': uid, 'movieId': 30, 'rating': 1.5}
    assert client.post('/api/interactions/rating', json=rating).status_code == 200
    assert client.post(f'/api/users/{uid}/favorites', json={'movieId': 30, 'isFavorite': True}).status_code == 200
    progress = {'userId': uid, 'movieId': 30, 'positionSeconds': 95, 'durationSeconds': 100}
    for _ in range(3):
        assert client.put('/api/watch/progress', json=progress).status_code == 200
    rows = feedback_store.read_feedback()
    assert len(rows) == 1
    assert rows.iloc[0].rating == 1.5 and rows.iloc[0].source == 'explicit'
    assert client.get(f'/api/users/{uid}/ratings').json()[0]['rating'] == 1.5
    assert all(m['movieId'] != 30 for m in client.get(f'/api/recommendations/{uid}').json()['recommendations'])


def test_watch_proxy_is_not_shown_as_a_user_rating_and_not_applied_twice(runtime, monkeypatch):
    client, uid, service = runtime
    calls = []
    monkeypatch.setattr(service, 'apply_online_update', lambda *args: calls.append(args))
    payload = {'userId': uid, 'movieId': 32, 'positionSeconds': 95, 'durationSeconds': 100}
    for _ in range(2):
        client.put('/api/watch/progress', json=payload)
    assert len(calls) == 1
    assert client.get(f'/api/users/{uid}/ratings').json() == []
    assert feedback_store.read_feedback().iloc[0].source == 'watch_complete'


def test_favorite_single_request_updates_both_views_and_can_remove_last_row(runtime):
    client, uid, _ = runtime
    url = f'/api/users/{uid}/favorites'
    client.post(url, json={'movieId': 4, 'isFavorite': True})
    assert client.get(url).json()[0]['movieId'] == 4
    assert feedback_store.read_feedback().iloc[0].source == 'favorite'
    assert client.get(f'/api/users/{uid}/ratings').json() == []
    client.post(url, json={'movieId': 4, 'isFavorite': False})
    assert client.get(url).json() == []
    assert feedback_store.read_feedback().empty


def test_watch_resume_validation_and_literal_search(runtime):
    client, uid, _ = runtime
    progress = {'userId': uid, 'movieId': 3, 'positionSeconds': 30, 'durationSeconds': 100}
    assert client.put('/api/watch/progress', json=progress).status_code == 200
    assert client.get(f'/api/watch/progress/{uid}').json()[0]['position_seconds'] == 30
    assert client.get(f'/api/watch/progress/{uid}/3').json()['position_seconds'] == 30
    assert feedback_store.read_feedback().empty
    assert client.put('/api/watch/progress', json={**progress, 'positionSeconds': 110}).status_code == 422
    assert client.put('/api/watch/progress', json={**progress, 'movieId': 999}).status_code == 404
    assert client.post('/api/interactions/rating', json={'userId': 999, 'movieId': 3, 'rating': 4}).status_code == 403
    assert client.get('/api/movies/search', params={'q': '['}).status_code == 200
    assert client.get('/api/health').json()['status'] == 'degraded'


def test_atomic_feedback_writes_do_not_lose_concurrent_users(runtime):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda uid: feedback_store.write_feedback(uid, 1, 4), range(200000, 200020)))
    assert len(feedback_store.read_feedback()) == 20


def test_reload_failure_retains_old_snapshot(runtime, monkeypatch):
    _, _, service = runtime
    service.initialize()
    old_movies = service.movies
    monkeypatch.setattr(recommender, 'MOVIES_CSV', recommender.MOVIES_CSV.with_name('missing.csv'))
    with pytest.raises(FileNotFoundError):
        service.reload_model()
    assert service.initialized and service.movies is old_movies


def test_legacy_feedback_is_preserved_and_its_unknown_source_is_visible(runtime):
    client, uid, _ = runtime
    pd.DataFrame([{'userId': uid, 'movieId': 4, 'rating': 2.5, 'timestamp': '2026-01-01'}]).to_csv(
        feedback_store.INTERACTIONS_LOG_CSV, index=False)
    profile = client.get(f'/api/users/{uid}/profile').json()
    assert profile['legacy_feedback_count'] == 1
    assert profile['ratings_count'] == 0
    client.put('/api/watch/progress', json={'userId': uid, 'movieId': 4, 'positionSeconds': 95, 'durationSeconds': 100})
    assert feedback_store.read_feedback().iloc[0].rating == 2.5
