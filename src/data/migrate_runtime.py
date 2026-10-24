"""Nhập dữ liệu ứng dụng vào PostgreSQL, có dry-run, backup và đối soát."""

import argparse
import json
import os
import shutil
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

from api.database import database_connection
from src.experiments.artifacts import sha256,utc_now,write_json
from src.experiments.config import ROOT
from src.models.hybrid import parse_genres

RUNTIME_FILES=['users.json','interactions_log.csv','user_favorites.csv','watch_progress.csv']


def legacy_time(value,zone='Asia/Ho_Chi_Minh'):
    """Chuỗi có timezone giữ nguyên; chuỗi prototype naive dùng múi giờ dự án đã khai báo."""
    if isinstance(value,(int,float)):
        timestamp=pd.to_datetime(value,unit='s',utc=True)
    else:timestamp=pd.Timestamp(value)
    if pd.isna(timestamp):raise ValueError('Timestamp runtime bị thiếu')
    if timestamp.tzinfo is None:timestamp=timestamp.tz_localize(ZoneInfo(zone))
    return timestamp.to_pydatetime()


def read_legacy(folder):
    folder=Path(folder)
    users_path=folder/'users.json'
    users=json.loads(users_path.read_text(encoding='utf-8')) if users_path.exists() else {}
    tables={}
    for name in RUNTIME_FILES[1:]:
        path=folder/name
        tables[name]=pd.read_csv(path) if path.exists() and path.stat().st_size else pd.DataFrame()
    return users,tables


def migrate(folder=ROOT/'data/processed',apply=False,canonical_catalog=None):
    folder=Path(folder)
    users,tables=read_legacy(folder)
    movies=pd.read_csv(folder/'movies_processed.csv').fillna('')
    canonical_hash=None
    if canonical_catalog is not None:
        canonical_catalog=Path(canonical_catalog)
        canonical_hash=sha256(canonical_catalog)
        canonical=pd.read_csv(canonical_catalog)
        missing=canonical[~canonical.movieId.isin(movies.movieId)].copy()
        if len(missing):
            missing=missing.assign(poster_path='',overview='Chưa có mô tả phim.',runtime_minutes=100)
            movies=pd.concat([movies,missing],ignore_index=True).fillna('')
    valid_users={int(key) for key in users}
    valid_movies=set(movies.movieId.astype(int))
    quarantined={}
    for name,frame in tables.items():
        if frame.empty:continue
        invalid=(~frame.userId.isin(valid_users))|(~frame.movieId.isin(valid_movies))
        quarantined[name]=frame[invalid].copy()
        if invalid.any():quarantined[name]['quarantine_reason']='Không có tài khoản hoặc phim tham chiếu'
        tables[name]=frame[~invalid].copy()
    hashes={n:sha256(folder/n) for n in [*RUNTIME_FILES,'movies_processed.csv'] if (folder/n).exists()}
    counts={'users':len(users),'movies':len(movies),**{n:len(f) for n,f in tables.items()}}
    report={'created_at':utc_now(),'mode':'apply' if apply else 'dry_run','source_sha256':hashes,'counts':counts,
            'legacy_naive_timezone':'Asia/Ho_Chi_Minh',
            'canonical_catalog_sha256':canonical_hash,
            'quarantined_counts':{n:len(f) for n,f in quarantined.items()},
            'quarantine_policy':'Giữ nguyên file nguồn; bản ghi không có FK được cách ly trong backup, không tạo tài khoản giả'}
    if not apply:return report
    backup=ROOT/'artifacts/migrations'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(parents=True)
    for name in hashes:shutil.copy2(folder/name,backup/name)
    if canonical_catalog is not None:shutil.copy2(canonical_catalog,backup/'canonical_movies.csv')
    for name,frame in quarantined.items():
        if not frame.empty:frame.to_csv(backup/('quarantine_'+name),index=False)
    write_json(backup/'source_manifest.json',report)
    with database_connection() as con:
        con.execute('SELECT pg_advisory_xact_lock(%s)',(716200001,))
        con.execute('CREATE TEMP TABLE import_movies (LIKE moviers.movies INCLUDING DEFAULTS) ON COMMIT DROP')
        with con.cursor().copy('COPY import_movies(movie_id,title,genres,poster_path,overview,runtime_minutes) FROM STDIN') as copy:
            for row in movies.to_dict('records'):
                runtime=row.get('runtime_minutes',100)
                copy.write_row((int(row['movieId']),str(row['title']),sorted(parse_genres(row.get('genres',''))),
                                str(row.get('poster_path','')),str(row.get('overview','')),int(runtime) if str(runtime).strip() else 100))
        con.execute('INSERT INTO moviers.movies SELECT * FROM import_movies ON CONFLICT(movie_id) DO NOTHING')
        for key,user in users.items():
            uid=int(user['user_id'])
            if uid<200000 or int(key)!=uid:raise ValueError('Miền ID tài khoản không hợp lệ')
            existing=con.execute('SELECT username FROM moviers.app_users WHERE user_id=%s',(uid,)).fetchone()
            if existing and existing['username'].lower()!=user['username'].lower():
                raise ValueError('Xung đột ID với tài khoản PostgreSQL')
            con.execute('INSERT INTO moviers.app_users(user_id,username,password_hash,salt,genres,created_at) '
                        'VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id) DO NOTHING',
                        (uid,user['username'],user['password_hash'],user.get('salt',''),user.get('genres',[]),
                         legacy_time(user['created_at']) if user.get('created_at') else datetime.now(timezone.utc)))
        con.execute("SELECT setval(pg_get_serial_sequence('moviers.app_users','user_id'),"
                    "greatest(coalesce(max(user_id),199999),199999),true) FROM moviers.app_users")
        for row in tables['interactions_log.csv'].to_dict('records'):
            source=row.get('source','legacy_unknown')
            if pd.isna(source):source='legacy_unknown'
            con.execute('INSERT INTO moviers.feedback(user_id,movie_id,rating,source,updated_at) VALUES(%s,%s,%s,%s,%s) '
                        'ON CONFLICT(user_id,movie_id) DO NOTHING',
                        (int(row['userId']),int(row['movieId']),float(row['rating']),source,legacy_time(row['timestamp'])))
        for row in tables['user_favorites.csv'].to_dict('records'):
            con.execute('INSERT INTO moviers.favorites(user_id,movie_id,added_at) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',
                        (int(row['userId']),int(row['movieId']),legacy_time(row['added_at'])))
        for row in tables['watch_progress.csv'].to_dict('records'):
            con.execute('INSERT INTO moviers.watch_progress(user_id,movie_id,position_seconds,duration_seconds,updated_at) '
                        'VALUES(%s,%s,%s,%s,%s) ON CONFLICT(user_id,movie_id) DO NOTHING',
                        (int(row['userId']),int(row['movieId']),int(row['position_seconds']),int(row['duration_seconds']),legacy_time(row['updated_at'])))
        # Sửa riêng timestamp legacy naive đã được import theo UTC ở lượt cũ.
        # Điều kiện bằng giá trị cũ bảo vệ mọi cập nhật mới đã ghi sau cutover.
        fixes=0
        sources=[('app_users','created_at',[dict(u) for u in users.values()]),
                 ('feedback','timestamp',tables['interactions_log.csv'].to_dict('records')),
                 ('favorites','added_at',tables['user_favorites.csv'].to_dict('records')),
                 ('watch_progress','updated_at',tables['watch_progress.csv'].to_dict('records'))]
        for table,field,rows in sources:
            target_field='updated_at' if field=='timestamp' else field
            for row in rows:
                value=row.get(field)
                if value is None:continue
                timestamp=pd.Timestamp(value)
                if timestamp.tzinfo is not None:continue
                old=timestamp.tz_localize('UTC').to_pydatetime()
                uid=int(row['user_id'] if table=='app_users' else row['userId'])
                where='user_id=%s'+(' AND movie_id=%s' if table!='app_users' else '')
                keys=(uid,int(row['movieId'])) if table!='app_users' else (uid,)
                fixes+=con.execute(f'UPDATE moviers.{table} SET {target_field}=%s WHERE {where} AND {target_field}=%s',
                                   (legacy_time(value),*keys,old)).rowcount
        report['legacy_timezone_rows_corrected']=fixes
        target={}
        for table in ['app_users','movies','feedback','favorites','watch_progress']:
            target[table]=con.execute(f'SELECT count(*) AS n FROM moviers.{table}').fetchone()['n']
        if any(sha256(folder/n)!=value for n,value in hashes.items()):
            raise ValueError('Nguồn thay đổi giữa lúc import; transaction rollback, cần dừng ghi trước migration')
        if canonical_hash and sha256(canonical_catalog)!=canonical_hash:raise ValueError('Canonical catalog thay đổi khi import')
        report['target_counts']=target
    report['status']='committed'
    report['backup']=str(backup.relative_to(ROOT))
    write_json(backup/'result.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description='Migration runtime: mặc định chỉ đọc kiểm kê')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--source',type=Path,default=ROOT/'data/processed')
    parser.add_argument('--export-to',type=Path,default=None,help='Xuất snapshot nhất quán để diễn tập rollback về file')
    parser.add_argument('--canonical-catalog',type=Path,default=ROOT/'data/raw/movies.csv')
    args=parser.parse_args()
    load_dotenv(ROOT/'.env')
    if args.export_to:
        if args.apply:parser.error('Không dùng --apply và --export-to cùng lúc')
        print(json.dumps(export_runtime(args.export_to),ensure_ascii=False))
    else:print(json.dumps(migrate(args.source,args.apply,args.canonical_catalog if args.canonical_catalog.exists() else None),ensure_ascii=False))


def export_runtime(destination):
    """Xuất sang thư mục mới; không ghi đè bản file đang dùng hoặc rollback âm thầm."""
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    with database_connection() as con:
        con.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        users=con.execute('SELECT * FROM moviers.app_users ORDER BY user_id').fetchall()
        for user in users:user['created_at']=user['created_at'].isoformat()
        write_json(destination/'users.json',{str(u['user_id']):u for u in users})
        definitions={
            'interactions_log.csv':('feedback','user_id AS "userId",movie_id AS "movieId",rating,updated_at AS timestamp,source'),
            'user_favorites.csv':('favorites','user_id AS "userId",movie_id AS "movieId",added_at'),
            'watch_progress.csv':('watch_progress','user_id AS "userId",movie_id AS "movieId",position_seconds,duration_seconds,ratio,status,updated_at')}
        counts={'users':len(users)}
        for name,(table,columns) in definitions.items():
            cursor=con.execute(f'SELECT {columns} FROM moviers.{table} ORDER BY user_id,movie_id')
            rows=cursor.fetchall()
            pd.DataFrame(rows,columns=[c.name for c in cursor.description]).to_csv(destination/name,index=False)
            counts[name]=len(rows)
    manifest={'created_at':utc_now(),'counts':counts,'sessions_exported':False,
              'files':{p.name:sha256(p) for p in destination.iterdir()}}
    write_json(destination/'export_manifest.json',manifest)
    return manifest


if __name__=='__main__':main()
