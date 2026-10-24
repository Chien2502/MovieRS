"""Kiểm tra cấu hình SQL trên connector giả, không dùng credential hoặc DB thật."""

from contextlib import contextmanager

import psycopg
import pytest
from fastapi.testclient import TestClient

import api.database as database
from api.main import app
import src.data.init_database as init_database


@pytest.fixture(autouse=True)
def isolated_database_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', '')
    monkeypatch.setenv('DATABASE_SSLMODE', 'require')
    monkeypatch.setenv('DATABASE_CONNECT_TIMEOUT', '5')


def test_empty_configuration_does_not_connect(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Không được mở kết nối khi chưa có DATABASE_URL')
    monkeypatch.setattr(psycopg, 'connect', forbidden)
    assert database.DatabaseSettings.from_env() is None
    assert database.database_status()['status'] == 'not_configured'
    assert TestClient(app).get('/api/health/database').json()['configured'] is False


@pytest.mark.parametrize('url', ['https://example.supabase.co', 'postgresql://', 'just-an-api-key'])
def test_an_api_key_is_not_a_postgres_url(monkeypatch, url):
    monkeypatch.setenv('DATABASE_URL', url)
    with pytest.raises(database.DatabaseError):
        database.DatabaseSettings.from_env()


def test_connection_settings_use_ssl_timeout_and_disable_prepared_statements(monkeypatch):
    url = 'postgresql://postgres.example:not-a-real-password@pooler.example.com:5432/postgres'
    monkeypatch.setenv('DATABASE_URL', url)
    arguments = {}
    class Connection:
        def execute(self,sql,**kwargs):arguments['limits_sql']=sql
        def __enter__(self):
            return self
        def __exit__(self, *args):
            arguments['closed'] = True
    def connect(dsn, **kwargs):
        arguments.update(dsn=dsn, **kwargs)
        return Connection()
    monkeypatch.setattr(psycopg, 'connect', connect)
    with database.database_connection():
        pass
    assert arguments['sslmode'] == 'require'
    assert arguments['connect_timeout'] == 5
    assert arguments['prepare_threshold'] is None
    assert arguments['closed'] is True
    assert 'statement_timeout=15000' in arguments['limits_sql']
    assert 'not-a-real-password' not in repr(database.DatabaseSettings.from_env())


def test_explicit_certificate_validation_is_not_downgraded(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://postgres:password@host.example/postgres?sslmode=verify-full')
    options = {}
    class Connection:
        def execute(self,*args,**kwargs):pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
    def connect(*args, **kwargs):
        options.update(kwargs)
        return Connection()
    monkeypatch.setattr(psycopg, 'connect', connect)
    with database.database_connection():
        pass
    assert options['sslmode'] == 'verify-full'


def test_bad_connection_never_discloses_password(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://postgres:secret-sentinel@host.example/postgres')
    def connect(*args, **kwargs):
        raise psycopg.OperationalError('Failed connection secret-sentinel')
    monkeypatch.setattr(psycopg, 'connect', connect)
    response = TestClient(app).get('/api/health/database')
    assert response.status_code == 503
    assert 'secret-sentinel' not in response.text
    assert 'postgresql://' not in response.text


def test_status_is_read_only_and_reports_missing_schema(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://postgres:password@host.example/postgres')
    statements = []
    class Result:
        def fetchone(self): return {'schema_ready': False}
    class Connection:
        def execute(self, sql):
            statements.append(sql)
            return Result()
    @contextmanager
    def connect(): yield Connection()
    monkeypatch.setattr(database, 'database_connection', connect)
    status = database.database_status()
    assert status['status'] == 'connected' and not status['schema_ready']
    assert all(sql.startswith('SELECT') for sql in statements)


def test_initializer_uses_one_transaction_and_rolls_back_on_error(monkeypatch, tmp_path):
    schema = tmp_path / 'schema.sql'
    schema.write_text('CREATE SCHEMA example;', encoding='utf-8')
    monkeypatch.setattr(init_database, 'SCHEMA_SQL', schema)
    state = {'rolled_back': False}
    class Connection:
        def execute(self, sql, *args, **kwargs):
            if sql.startswith('CREATE'):
                assert kwargs['prepare'] is False
                raise psycopg.ProgrammingError('SQL lỗi')
    @contextmanager
    def connect():
        try:
            yield Connection()
        except psycopg.Error:
            state['rolled_back'] = True
            raise
    monkeypatch.setattr(init_database, 'database_connection', connect)
    with pytest.raises(psycopg.ProgrammingError):
        init_database.initialize_database()
    assert state['rolled_back']


def test_check_command_never_initializes_schema(monkeypatch):
    monkeypatch.setattr(init_database, 'load_dotenv', lambda *args, **kwargs: None)
    def forbidden(): pytest.fail('--check không được tạo bảng')
    monkeypatch.setattr(init_database, 'initialize_database', forbidden)
    monkeypatch.setattr(init_database, 'database_status', lambda: {'status': 'not_configured'})
    assert init_database.main(['--check']) == 1
