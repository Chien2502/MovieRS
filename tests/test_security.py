"""Đăng nhập, quyền sở hữu, hết phiên và nâng hash trên tài khoản tạm."""

import hashlib
import json
from datetime import datetime,timedelta,timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.security import get_session
from api.services import user_store


@pytest.fixture
def accounts(tmp_path,monkeypatch):
    monkeypatch.setattr(user_store,'USERS_FILE',tmp_path/'users.json')
    with TestClient(app) as client:
        first=client.post('/api/auth/register',json={'username':'first','password':'abcdefgh'}).json()
        second=client.post('/api/auth/register',json={'username':'second','password':'abcdefgh'}).json()
        yield client,first,second


def test_ownership_logout_and_hash_at_rest(accounts):
    client,first,second=accounts
    assert client.get('/api/auth/me').status_code==401
    client.headers['Authorization']='Bearer '+first['access_token']
    assert client.get('/api/auth/me').json()['user_id']==first['user_id']
    assert client.get(f"/api/users/{second['user_id']}/profile").status_code==403
    assert client.put('/api/watch/progress',json={'userId':second['user_id'],'movieId':1,
                                                'positionSeconds':1,'durationSeconds':100}).status_code==403
    assert client.post('/api/recommendations/reload').status_code==403
    assert first['access_token'] not in user_store.USERS_FILE.with_name('sessions.json').read_text()
    users=json.loads(user_store.USERS_FILE.read_text())
    assert users[str(first['user_id'])]['password_hash'].startswith('$argon2id$')
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/auth/me').status_code==401


def test_legacy_hash_upgrades_after_valid_login(tmp_path,monkeypatch):
    path=tmp_path/'users.json'
    monkeypatch.setattr(user_store,'USERS_FILE',path)
    user={'user_id':200000,'username':'legacy','salt':'old','genres':[],
          'password_hash':hashlib.sha256(b'old:legacy-password').hexdigest()}
    path.write_text(json.dumps({'200000':user}))
    assert user_store.authenticate('legacy','wrong') is None
    assert user_store.authenticate('legacy','legacy-password') is not None
    assert json.loads(path.read_text())['200000']['password_hash'].startswith('$argon2id$')


def test_expired_token_denied(accounts):
    _,first,_=accounts
    path=user_store.USERS_FILE.with_name('sessions.json')
    sessions=json.loads(path.read_text())
    digest=hashlib.sha256(first['access_token'].encode()).hexdigest()
    sessions[digest]['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    path.write_text(json.dumps(sessions))
    assert get_session(first['access_token']) is None
