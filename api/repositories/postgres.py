"""Kho PostgreSQL: mọi thao tác liên quan phản hồi nằm trong cùng giao dịch."""

from datetime import datetime,timezone

import pandas as pd
import psycopg

from api.database import database_connection
from api.idempotency import claim_sql

PRIORITY={'explicit':3,'legacy_unknown':3,'favorite':2,'watch':1,'watch_complete':1}


def _user(row):
    if row and hasattr(row.get('created_at'),'isoformat'):
        row['created_at']=row['created_at'].isoformat()
    return row


class PostgresRepository:
    def get_user(self, user_id):
        with database_connection() as con:
            return _user(con.execute('SELECT * FROM moviers.app_users WHERE user_id=%s',(user_id,)).fetchone())

    def find_user(self, username):
        with database_connection() as con:
            return _user(con.execute('SELECT * FROM moviers.app_users WHERE lower(username)=lower(%s)',(username,)).fetchone())

    def register(self, username, password_hash, salt, genres):
        try:
            with database_connection() as con:
                return _user(con.execute('INSERT INTO moviers.app_users(username,password_hash,salt,genres) '
                                         'VALUES(%s,%s,%s,%s) RETURNING *',
                                         (username,password_hash,salt,genres)).fetchone())
        except psycopg.errors.UniqueViolation:
            raise ValueError('Tên người dùng đã tồn tại') from None

    def update_hash(self, user_id, password_hash, salt):
        with database_connection() as con:
            con.execute('UPDATE moviers.app_users SET password_hash=%s,salt=%s WHERE user_id=%s',
                        (password_hash,salt,user_id))

    def preferences(self, user_id, genres):
        with database_connection() as con:
            return _user(con.execute('UPDATE moviers.app_users SET genres=%s WHERE user_id=%s RETURNING *',
                                     (genres,user_id)).fetchone())

    def feedback(self,user_id=None):
        with database_connection() as con:
            rows=con.execute('SELECT user_id AS "userId",movie_id AS "movieId",rating, '
                             'updated_at AS timestamp,source FROM moviers.feedback '
                             + ('WHERE user_id=%s ' if user_id is not None else '')
                             + 'ORDER BY user_id,movie_id', (user_id,) if user_id is not None else ()).fetchall()
        frame=pd.DataFrame(rows,columns=['userId','movieId','rating','timestamp','source'])
        if len(frame):
            frame['rating']=frame.rating.astype(float)
            frame['timestamp']=frame.timestamp.map(lambda x:x.isoformat())
        return frame

    @staticmethod
    def _pair_lock(con, user_id, movie_id):
        # Cùng một khóa cho cả insert mới và update; tránh hai nguồn ghi đè sai ưu tiên.
        con.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(f'moviers:{user_id}:{movie_id}',))

    @staticmethod
    def _feedback(con, user_id, movie_id, rating, source):
        if source not in PRIORITY or not .5<=rating<=5:
            raise ValueError('Nguồn hoặc điểm phản hồi không hợp lệ')
        old=con.execute('SELECT rating,source FROM moviers.feedback WHERE user_id=%s AND movie_id=%s FOR UPDATE',
                        (user_id,movie_id)).fetchone()
        if old and (PRIORITY[old['source']]>PRIORITY[source] or
                    (old['source']==source and float(old['rating'])==float(rating))):
            return False
        con.execute('INSERT INTO moviers.feedback(user_id,movie_id,rating,source) VALUES(%s,%s,%s,%s) '
                    'ON CONFLICT(user_id,movie_id) DO UPDATE SET rating=excluded.rating,source=excluded.source,updated_at=now()',
                    (user_id,movie_id,rating,source))
        return True

    def write_feedback(self, user_id, movie_id, rating, source='explicit',idempotency_key=None):
        with database_connection() as con:
            self._pair_lock(con,user_id,movie_id)
            if claim_sql(con,user_id,idempotency_key,['feedback',movie_id,float(rating),source]):return False
            return self._feedback(con,user_id,movie_id,rating,source)

    def remove_favorite_feedback(self,user_id,movie_id):
        with database_connection() as con:
            self._pair_lock(con,user_id,movie_id)
            return con.execute("DELETE FROM moviers.feedback WHERE user_id=%s AND movie_id=%s AND source='favorite'",
                               (user_id,movie_id)).rowcount>0

    def favorites(self,user_id):
        with database_connection() as con:
            rows=con.execute('SELECT user_id AS "userId",movie_id AS "movieId",added_at '
                             'FROM moviers.favorites WHERE user_id=%s ORDER BY added_at DESC',(user_id,)).fetchall()
        for r in rows:r['added_at']=r['added_at'].isoformat()
        return rows

    def favorite(self,user_id,movie_id,enabled,idempotency_key=None):
        with database_connection() as con:
            self._pair_lock(con,user_id,movie_id)
            if claim_sql(con,user_id,idempotency_key,['favorite',movie_id,enabled]):return False
            if enabled:
                con.execute('INSERT INTO moviers.favorites(user_id,movie_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(user_id,movie_id))
                return self._feedback(con,user_id,movie_id,4.5,'favorite')
            con.execute('DELETE FROM moviers.favorites WHERE user_id=%s AND movie_id=%s',(user_id,movie_id))
            return con.execute("DELETE FROM moviers.feedback WHERE user_id=%s AND movie_id=%s AND source='favorite'",
                               (user_id,movie_id)).rowcount>0

    def progress(self,user_id,movie_id,position,duration,idempotency_key=None):
        if duration<=0 or not 0<=position<=duration:raise ValueError('Tiến độ không hợp lệ')
        with database_connection() as con:
            self._pair_lock(con,user_id,movie_id)
            if claim_sql(con,user_id,idempotency_key,['progress',movie_id,position,duration]):
                row=con.execute('SELECT ratio,status FROM moviers.watch_progress WHERE user_id=%s AND movie_id=%s',
                                (user_id,movie_id)).fetchone()
                return {'ratio':float(row['ratio']) if row else 0,'status':row['status'] if row else 'not_started',
                        'finished':bool(row and row['status']=='finished'),'feedback_changed':False}
            row=con.execute('INSERT INTO moviers.watch_progress(user_id,movie_id,position_seconds,duration_seconds) '
                            'VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,movie_id) DO UPDATE '
                            'SET position_seconds=excluded.position_seconds,duration_seconds=excluded.duration_seconds,updated_at=now() '
                            'RETURNING ratio,status',(user_id,movie_id,position,duration)).fetchone()
            changed=self._feedback(con,user_id,movie_id,4,'watch_complete') if row['status']=='finished' else False
        return {'ratio':float(row['ratio']),'status':row['status'],'finished':row['status']=='finished','feedback_changed':changed}

    def get_progress(self,user_id,movie_id=None):
        with database_connection() as con:
            if movie_id is None:
                rows=con.execute('SELECT user_id AS "userId",movie_id AS "movieId",position_seconds,duration_seconds,ratio,status,updated_at '
                                 'FROM moviers.watch_progress WHERE user_id=%s AND ratio>=0.05 AND ratio<0.95 '
                                 'ORDER BY updated_at DESC',(user_id,)).fetchall()
            else:
                rows=con.execute('SELECT user_id AS "userId",movie_id AS "movieId",position_seconds,duration_seconds,ratio,status,updated_at '
                                 'FROM moviers.watch_progress WHERE user_id=%s AND movie_id=%s',(user_id,movie_id)).fetchall()
        for row in rows:row['updated_at']=row['updated_at'].isoformat()
        return rows if movie_id is None else (rows[0] if rows else None)

    def remove_progress(self,user_id,movie_id):
        with database_connection() as con:
            return con.execute('DELETE FROM moviers.watch_progress WHERE user_id=%s AND movie_id=%s',(user_id,movie_id)).rowcount>0

    def create_session(self,digest,user_id,expires):
        with database_connection() as con:
            con.execute('DELETE FROM moviers.sessions WHERE expires_at<=now()')
            con.execute('INSERT INTO moviers.sessions(token_hash,user_id,expires_at) VALUES(%s,%s,%s)',(digest,user_id,expires))

    def session(self,digest):
        with database_connection() as con:
            return con.execute('SELECT user_id,expires_at FROM moviers.sessions WHERE token_hash=%s AND expires_at>now()',(digest,)).fetchone()

    def revoke_session(self,digest):
        with database_connection() as con:
            con.execute('DELETE FROM moviers.sessions WHERE token_hash=%s',(digest,))
