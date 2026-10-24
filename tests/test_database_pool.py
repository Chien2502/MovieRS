"""Pool cấu hình sai phải fail closed trước khi tạo kết nối mạng."""

import pytest

from api.database import DatabaseError,database_connection


def test_pool_size_is_bounded(monkeypatch):
    monkeypatch.setenv('DATABASE_URL','postgresql://postgres:placeholder@host.example/postgres')
    monkeypatch.setenv('DATABASE_POOL_SIZE','999')
    with pytest.raises(DatabaseError):
        with database_connection():pytest.fail('Không được kết nối với pool quá lớn')
