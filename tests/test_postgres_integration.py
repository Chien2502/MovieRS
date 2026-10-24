"""Tích hợp opt-in trên PostgreSQL thật; chỉ tạo/xóa tài khoản fixture riêng."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from api.database import DatabaseError,database_connection
from api.main import app
from api.repositories.postgres import PostgresRepository
from api.services.recommender import RecommenderService

pytestmark=pytest.mark.skipif(os.getenv('MOVIERS_RUN_DB_TESTS')!='1',reason='Chỉ chạy khi bật tích hợp PostgreSQL')


@pytest.fixture
def pg_runtime(monkeypatch):
    load_dotenv('.env',override=False)
    monkeypatch.setenv('MOVIERS_STORAGE','postgres')
    service=RecommenderService()
    monkeypatch.setattr(service,'invalidate_user',lambda *args:None)
    monkeypatch.setattr(service,'apply_online_update',lambda *args:True)
    users=[]
    attempted_names=[]
    with TestClient(app) as client:
        try:
            for _ in range(2):
                name='refactor_test_'+uuid.uuid4().hex[:20]
                attempted_names.append(name)
                response=client.post('/api/auth/register',json={'username':name,'password':'temporary-pass-123'})
                assert response.status_code==201,response.text
                user=response.json();users.append((user['user_id'],name))
                if len(users)==1:
                    client.headers['Authorization']='Bearer '+user['access_token']
                    first=user
            yield client,first,users[1][0]
        finally:
            with database_connection() as con:
                for name in attempted_names:
                    con.execute('DELETE FROM moviers.app_users WHERE username=%s',(name,))


def test_real_postgres_ownership_priority_and_idempotency(pg_runtime):
    client,first,other=pg_runtime
    uid=first['user_id']
    assert client.get(f'/api/users/{other}/profile').status_code==403
    assert client.get(f'/api/users/{uid}/profile').status_code==200
    for _ in range(2):
        assert client.post(f'/api/users/{uid}/favorites',json={'movieId':1,'isFavorite':True}).status_code==200
    assert client.post('/api/interactions/rating',json={'userId':uid,'movieId':1,'rating':1.5}).status_code==200
    for _ in range(2):
        assert client.put('/api/watch/progress',json={'userId':uid,'movieId':1,'positionSeconds':95,'durationSeconds':100}).status_code==200
    with database_connection() as con:
        row=con.execute('SELECT rating,source FROM moviers.feedback WHERE user_id=%s AND movie_id=1',(uid,)).fetchone()
        assert float(row['rating'])==1.5 and row['source']=='explicit'
        assert con.execute('SELECT count(*) AS n FROM moviers.favorites WHERE user_id=%s',(uid,)).fetchone()['n']==1
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/auth/me').status_code==401


def test_favorite_and_feedback_transaction_roll_back_together(pg_runtime,monkeypatch):
    _,first,_=pg_runtime
    uid=first['user_id']
    def fail(*args,**kwargs):raise RuntimeError('Lỗi kiểm thử sau khi ghi favorite')
    monkeypatch.setattr(PostgresRepository,'_feedback',staticmethod(fail))
    with pytest.raises(RuntimeError):PostgresRepository().favorite(uid,2,True)
    with database_connection() as con:
        assert con.execute('SELECT count(*) AS n FROM moviers.favorites WHERE user_id=%s AND movie_id=2',(uid,)).fetchone()['n']==0
    with pytest.raises(RuntimeError):PostgresRepository().progress(uid,2,95,100)
    with database_connection() as con:
        assert con.execute('SELECT count(*) AS n FROM moviers.watch_progress WHERE user_id=%s AND movie_id=2',(uid,)).fetchone()['n']==0


def test_concurrent_feedback_keeps_explicit_priority(pg_runtime):
    _,first,_=pg_runtime
    uid=first['user_id']
    repo=PostgresRepository()
    actions=[(4.5,'favorite'),(4,'watch_complete'),(2,'explicit')]*3
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda x:repo.write_feedback(uid,3,*x),actions))
    with database_connection() as con:
        row=con.execute('SELECT rating,source FROM moviers.feedback WHERE user_id=%s AND movie_id=3',(uid,)).fetchone()
        assert row['source']=='explicit' and float(row['rating'])==2


def test_database_failure_does_not_fallback_to_files(pg_runtime,monkeypatch):
    client,_,_=pg_runtime
    import api.repositories.postgres as module
    def fail():raise DatabaseError('Lỗi mô phỏng')
    monkeypatch.setattr(module,'database_connection',fail)
    assert client.get('/api/auth/me').status_code==503
    # Khôi phục trước cleanup fixture để xóa đúng tài khoản kiểm thử.
    monkeypatch.setattr(module,'database_connection',database_connection)


def test_real_pool_reuses_connections_and_rolls_back(pg_runtime,monkeypatch):
    import api.database as database
    monkeypatch.setenv('DATABASE_POOL_SIZE','2')
    try:
        with database_connection() as con:
            assert con.execute('SELECT 1 AS n').fetchone()['n']==1
        with pytest.raises(RuntimeError):
            with database_connection() as con:
                con.execute('SELECT 1')
                raise RuntimeError('Mô phỏng rollback')
        with database_connection() as con:
            assert con.execute('SELECT 2 AS n').fetchone()['n']==2
        assert database._pool.get_stats()['pool_size']<=2
    finally:database.close_database_pool()


def test_server_statement_timeout_is_enforced(pg_runtime,monkeypatch):
    import time
    monkeypatch.setenv('DATABASE_STATEMENT_TIMEOUT_MS','100')
    started=time.monotonic()
    with pytest.raises(DatabaseError):
        with database_connection() as con:
            con.execute('SELECT pg_sleep(1)')
    assert time.monotonic()-started<5


def test_idempotency_replay_does_not_undo_newer_feedback(pg_runtime):
    client,first,_=pg_runtime
    uid=first['user_id']
    initial={'userId':uid,'movieId':1,'rating':1.5}
    header={'Idempotency-Key':'rating-intent-first'}
    assert client.post('/api/interactions/rating',json=initial,headers=header).status_code==200
    assert client.post('/api/interactions/rating',json={**initial,'rating':4.5},headers={'Idempotency-Key':'rating-intent-second'}).status_code==200
    replay=client.post('/api/interactions/rating',json=initial,headers=header)
    assert replay.status_code==200 and replay.json()['changed'] is False
    assert client.get(f'/api/users/{uid}/ratings').json()[0]['rating']==4.5
    assert client.post('/api/interactions/rating',json={**initial,'rating':2},headers=header).status_code==409


def test_idempotency_claim_rolls_back_on_failure(pg_runtime,monkeypatch):
    _,first,_=pg_runtime
    uid=first['user_id']
    repo=PostgresRepository()
    original=repo._feedback
    def fail(*args,**kwargs):raise RuntimeError('Mô phỏng lỗi sau ledger')
    monkeypatch.setattr(PostgresRepository,'_feedback',staticmethod(fail))
    with pytest.raises(RuntimeError):repo.favorite(uid,2,True,'favorite-transaction')
    monkeypatch.setattr(PostgresRepository,'_feedback',staticmethod(original))
    assert repo.favorite(uid,2,True,'favorite-transaction') is True


def test_idempotency_replay_preserves_newer_favorite_and_progress(pg_runtime):
    _,first,_=pg_runtime
    uid=first['user_id']
    repo=PostgresRepository()
    assert repo.favorite(uid,2,True,'favorite-old-request') is True
    assert repo.favorite(uid,2,False,'favorite-new-request') is True
    assert repo.favorite(uid,2,True,'favorite-old-request') is False
    repo.progress(uid,2,10,100,'progress-old-request')
    repo.progress(uid,2,40,100,'progress-new-request')
    repo.progress(uid,2,10,100,'progress-old-request')
    with database_connection() as con:
        assert con.execute('SELECT count(*) AS n FROM moviers.favorites WHERE user_id=%s AND movie_id=2',(uid,)).fetchone()['n']==0
        assert con.execute('SELECT position_seconds FROM moviers.watch_progress WHERE user_id=%s AND movie_id=2',(uid,)).fetchone()['position_seconds']==40
