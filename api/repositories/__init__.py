"""Chọn một nguồn lưu trữ; lỗi PostgreSQL không tự chuyển sang ghi file."""

import os
from typing import Protocol


class RuntimeRepository(Protocol):
    def get_user(self, user_id: int) -> dict | None: ...
    def write_feedback(self, user_id: int, movie_id: int, rating: float, source: str, idempotency_key=None) -> bool: ...
    def favorite(self, user_id: int, movie_id: int, enabled: bool, idempotency_key=None) -> bool: ...
    def progress(self, user_id: int, movie_id: int, position: int, duration: int, idempotency_key=None) -> dict: ...


def postgres_enabled():
    value=os.getenv('MOVIERS_STORAGE','files').strip()
    if value not in {'files','postgres'}:
        raise ValueError('MOVIERS_STORAGE phải là files hoặc postgres')
    return value=='postgres'


def repository():
    if not postgres_enabled():
        raise RuntimeError('Adapter PostgreSQL chưa được chọn')
    from api.repositories.postgres import PostgresRepository
    return PostgresRepository()
