"""Ràng buộc idempotency key vào thao tác; ledger SQL commit cùng dữ liệu nghiệp vụ."""

import hashlib
import json
import threading
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone

from fastapi import HTTPException

_file_lock=threading.RLock()


def fingerprints(key,payload):
    if not key:return None,None
    if not 8<=len(key)<=128:
        raise HTTPException(status_code=422,detail='Idempotency-Key cần từ 8 đến 128 ký tự')
    return hashlib.sha256(key.encode()).hexdigest(),hashlib.sha256(
        json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def claim_sql(connection,user_id,key,payload):
    digest,body=fingerprints(key,payload)
    if digest is None:return False
    connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'idem:{user_id}:{digest}',))
    old=connection.execute('SELECT payload_hash FROM moviers.idempotency_keys '
                           'WHERE user_id=%s AND key_hash=%s AND expires_at>now()',
                           (user_id,digest)).fetchone()
    if old:
        if old['payload_hash']!=body:
            raise HTTPException(status_code=409,detail='Idempotency-Key đã dùng cho nội dung khác')
        return True
    connection.execute("INSERT INTO moviers.idempotency_keys(user_id,key_hash,payload_hash,expires_at) "
                       "VALUES(%s,%s,%s,now()+interval '24 hours') ON CONFLICT(user_id,key_hash) "
                       'DO UPDATE SET payload_hash=excluded.payload_hash,expires_at=excluded.expires_at',
                       (user_id,digest,body))
    return False


@contextmanager
def file_operation(user_id,key,payload):
    """Adapter demo một tiến trình; ledger file được ghi sau khi thao tác thành công."""
    digest,body=fingerprints(key,payload)
    if digest is None:
        yield False
        return
    from api.services.user_store import USERS_FILE
    path=USERS_FILE.with_name('idempotency.json')
    with _file_lock:
        rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        now=datetime.now(timezone.utc)
        rows={k:v for k,v in rows.items() if datetime.fromisoformat(v['expires_at'])>now}
        identifier=f'{user_id}:{digest}'
        old=rows.get(identifier)
        if old:
            if old['payload_hash']!=body:raise HTTPException(status_code=409,detail='Idempotency-Key đã dùng cho nội dung khác')
            yield True
            return
        yield False
        rows[identifier]={'payload_hash':body,'expires_at':(now+timedelta(hours=24)).isoformat()}
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(rows),encoding='utf-8')
        temporary.replace(path)
