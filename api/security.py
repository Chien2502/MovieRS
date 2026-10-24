"""Phiên đăng nhập opaque có hạn dùng; chỉ lưu SHA-256 của token phía máy chủ."""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime,timedelta,timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError,VerificationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from api.repositories import postgres_enabled,repository
from api.database import DatabaseError

PASSWORDS=PasswordHasher()
_lock=threading.RLock()


def hash_password(password):
    return PASSWORDS.hash(password),''


def verify_password(user,password):
    stored=user['password_hash']
    if stored.startswith('$argon2'):
        try:return PASSWORDS.verify(stored,password)
        except (VerificationError,InvalidHashError):return False
    expected=hashlib.sha256(f"{user['salt']}:{password}".encode()).hexdigest()
    return hmac.compare_digest(expected,stored)


def _sessions_path():
    from api.services.user_store import USERS_FILE
    return USERS_FILE.with_name('sessions.json')


def _read_sessions():
    path=_sessions_path()
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def _write_sessions(rows):
    path=_sessions_path()
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(rows),encoding='utf-8')
    temporary.replace(path)


def issue_session(user_id):
    token=secrets.token_urlsafe(32)
    digest=hashlib.sha256(token.encode()).hexdigest()
    expires=datetime.now(timezone.utc)+timedelta(hours=12)
    if postgres_enabled():repository().create_session(digest,user_id,expires)
    else:
        with _lock:
            rows={k:v for k,v in _read_sessions().items() if datetime.fromisoformat(v['expires_at'])>datetime.now(timezone.utc)}
            rows[digest]={'user_id':user_id,'expires_at':expires.isoformat()}
            _write_sessions(rows)
    return {'access_token':token,'token_type':'bearer','expires_at':expires.isoformat()}


def get_session(token):
    if not token:return None
    digest=hashlib.sha256(token.encode()).hexdigest()
    if postgres_enabled():return repository().session(digest)
    with _lock:
        row=_read_sessions().get(digest)
    return row if row and datetime.fromisoformat(row['expires_at'])>datetime.now(timezone.utc) else None


def revoke_session(token):
    digest=hashlib.sha256(token.encode()).hexdigest()
    if postgres_enabled():repository().revoke_session(digest)
    else:
        with _lock:
            rows=_read_sessions();rows.pop(digest,None);_write_sessions(rows)


async def authorize_request(request,call_next):
    path=request.url.path
    # Reload là thao tác quản trị, tách khỏi token của tài khoản thông thường.
    if path=='/api/recommendations/reload':
        expected=os.getenv('ADMIN_API_TOKEN','')
        supplied=request.headers.get('X-Admin-Token','')
        if not expected or not hmac.compare_digest(expected,supplied):
            return JSONResponse(status_code=403,content={'detail':'Thao tác cần quyền quản trị'})
        return await call_next(request)
    private=path.startswith(('/api/users/','/api/watch/','/api/interactions/')) or path in ['/api/auth/me','/api/auth/logout']
    match=re.fullmatch(r'/api/recommendations/(\d+)',path)
    # User MovieLens ẩn danh thuộc dữ liệu công khai; tài khoản app cần quyền sở hữu.
    if match and int(match[1])>=200000:private=True
    if not private:return await call_next(request)
    auth=request.headers.get('Authorization','')
    scheme,_,value=auth.partition(' ')
    token=value.strip() if scheme.lower()=='bearer' else ''
    try:session=await run_in_threadpool(get_session,token)
    except DatabaseError:
        return JSONResponse(status_code=503,content={'detail':'Kho phiên đăng nhập tạm thời không khả dụng'})
    if session is None:return JSONResponse(status_code=401,content={'detail':'Phiên đăng nhập không hợp lệ hoặc đã hết hạn'})
    target=None
    for expression in [r'/api/users/(\d+)(?:/.*)?',r'/api/watch/progress/(\d+)(?:/.*)?',r'/api/recommendations/(\d+)']:
        m=re.fullmatch(expression,path)
        if m:target=int(m[1]);break
    if request.method in {'POST','PUT'} and (path.startswith('/api/interactions/') or path=='/api/watch/progress'):
        try:
            body=await request.json()
            if isinstance(body,dict):target=body.get('userId')
        except (ValueError,TypeError):pass
    if target is not None:
        try:valid=int(target)==int(session['user_id'])
        except (TypeError,ValueError):valid=False
        if not valid:return JSONResponse(status_code=403,content={'detail':'Không có quyền truy cập dữ liệu người dùng này'})
    request.state.user_id=int(session['user_id'])
    request.state.access_token=token
    return await call_next(request)
