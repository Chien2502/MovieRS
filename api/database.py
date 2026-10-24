"""Kết nối PostgreSQL của Supabase; chưa cấu hình thì không mở kết nối mạng."""

import os
import threading
import atexit
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urlsplit

_pool=None
_pool_key=None
_pool_lock=threading.Lock()


def close_database_pool():
    """Giải phóng kết nối khi API hoặc CLI kết thúc."""
    global _pool,_pool_key
    with _pool_lock:
        if _pool is not None:_pool.close()
        _pool,_pool_key=None,None


atexit.register(close_database_pool)


def _get_pool(settings,options,size):
    from psycopg_pool import ConnectionPool
    from psycopg.rows import dict_row
    global _pool,_pool_key
    key=(settings,size)
    with _pool_lock:
        if _pool is None or _pool_key!=key:
            if _pool is not None:_pool.close()
            _pool=ConnectionPool(settings.url,min_size=0,max_size=size,open=False,
                                 timeout=settings.connect_timeout,max_waiting=32,max_idle=60,
                                 kwargs={'sslmode':options.get('sslmode',settings.sslmode),
                                         'connect_timeout':settings.connect_timeout,'row_factory':dict_row,
                                         'application_name':'moviers','prepare_threshold':None,
                                         **connection_options(settings,options)})
            _pool.open()
            _pool_key=key
        return _pool


class DatabaseError(RuntimeError):
    """Lỗi an toàn để hiển thị, không chứa mật khẩu hoặc connection string."""


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = field(repr=False)
    sslmode: str = 'require'
    connect_timeout: int = 5
    statement_timeout_ms: int = 15000
    lock_timeout_ms: int = 5000

    @classmethod
    def from_env(cls):
        """Chỉ DATABASE_URL quyết định kết nối SQL; API key Supabase không thay nó."""
        url = os.getenv('DATABASE_URL', '').strip()
        if not url:
            return None
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {'postgres', 'postgresql'} or not parsed.hostname or not parsed.path.strip('/'):
                raise ValueError
            timeout = int(os.getenv('DATABASE_CONNECT_TIMEOUT', '5'))
            if not 1 <= timeout <= 60:
                raise ValueError
            sslmode = os.getenv('DATABASE_SSLMODE', 'require').strip()
            if sslmode not in {'require', 'verify-ca', 'verify-full', 'disable', 'prefer', 'allow'}:
                raise ValueError
            statement_timeout=int(os.getenv('DATABASE_STATEMENT_TIMEOUT_MS','15000'))
            lock_timeout=int(os.getenv('DATABASE_LOCK_TIMEOUT_MS','5000'))
            if not 100<=statement_timeout<=300000 or not 100<=lock_timeout<=300000:raise ValueError
        except ValueError:
            raise DatabaseError('Cấu hình PostgreSQL không hợp lệ. Kiểm tra DATABASE_URL và các biến DATABASE_* trong .env.') from None
        return cls(url=url, sslmode=sslmode, connect_timeout=timeout,
                   statement_timeout_ms=statement_timeout,lock_timeout_ms=lock_timeout)


def connection_options(settings, options):
    """Hạn chế query/lock phía server và bật phát hiện kết nối TCP bị mất."""
    return {'keepalives':1,'keepalives_idle':30,'keepalives_interval':10,'keepalives_count':3}


def _apply_limits(connection,settings):
    """SET LOCAL ở đúng transaction vì transaction pooler không giữ startup options."""
    connection.execute(f'SET LOCAL statement_timeout={settings.statement_timeout_ms}; '
                       f'SET LOCAL lock_timeout={settings.lock_timeout_ms}',prepare=False)


@contextmanager
def database_connection():
    """Một giao dịch mỗi context: commit khi thành công, rollback khi có lỗi."""
    settings = DatabaseSettings.from_env()
    if settings is None:
        raise DatabaseError('Chưa cấu hình DATABASE_URL trong .env.')
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
    except ImportError:
        raise DatabaseError('Thiếu psycopg. Chạy pip install -r requirements.txt.') from None
    try:
        options = conninfo_to_dict(settings.url)
        size=int(os.getenv('DATABASE_POOL_SIZE','0'))
        if not 0<=size<=8:raise ValueError('Pool size ngoài giới hạn')
    except (psycopg.Error,ValueError):
        raise DatabaseError('Cấu hình PostgreSQL không hợp lệ.') from None
    if size:
        from psycopg_pool import PoolTimeout,PoolClosed
        try:
            with _get_pool(settings,options,size).connection() as connection:
                _apply_limits(connection,settings)
                yield connection
        except (PoolTimeout,PoolClosed,psycopg.OperationalError,psycopg.errors.QueryCanceled,psycopg.errors.LockNotAvailable):
            raise DatabaseError('Kho dữ liệu tạm thời không khả dụng.') from None
        return
    try:
        connection = psycopg.connect(
            settings.url,
            sslmode=options.get('sslmode', settings.sslmode),
            connect_timeout=settings.connect_timeout,
            application_name='moviers',
            row_factory=dict_row,
            # Tương thích cả Session pooler và Transaction pooler của Supabase.
            prepare_threshold=None,
            **connection_options(settings,options),
        )
    except (psycopg.Error, ValueError):
        raise DatabaseError('Không kết nối được PostgreSQL. Kiểm tra mật khẩu database, host, SSL và kết nối mạng.') from None
    try:
        with connection:
            _apply_limits(connection,settings)
            yield connection
    except (psycopg.OperationalError,psycopg.errors.QueryCanceled,psycopg.errors.LockNotAvailable):
        raise DatabaseError('Truy vấn PostgreSQL không hoàn tất trong giới hạn hoặc mất kết nối.') from None


def database_status():
    """Kiểm tra chỉ đọc; không tạo bảng và không trả thông tin xác thực."""
    try:
        if DatabaseSettings.from_env() is None:
            return {'configured': False, 'status': 'not_configured', 'schema_ready': False}
        with database_connection() as connection:
            connection.execute('SELECT 1').fetchone()
            row = connection.execute(
                "SELECT bool_and(to_regclass(table_name) IS NOT NULL) AS schema_ready "
                "FROM unnest(ARRAY['moviers.app_users', 'moviers.movies', 'moviers.feedback', "
                "'moviers.favorites', 'moviers.watch_progress', 'moviers.schema_version', 'moviers.sessions', 'moviers.idempotency_keys']) AS expected(table_name)"
            ).fetchone()
        return {'configured': True, 'status': 'connected', 'schema_ready': bool(row['schema_ready'])}
    except DatabaseError:
        return {'configured': True, 'status': 'unavailable', 'schema_ready': False,
                'message': 'Chưa kết nối được PostgreSQL. Kiểm tra cấu hình .env hoặc driver.'}
    except Exception:
        return {'configured': True, 'status': 'unavailable', 'schema_ready': False,
                'message': 'Không kiểm tra được trạng thái PostgreSQL.'}
