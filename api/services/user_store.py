"""
user_store.py — Lưu trữ người dùng đăng ký (SQLite)

Prototype-level: SQLite users table.
Mật khẩu được băm SHA-256 kèm salt (không lưu plaintext).
User ID tự tăng bắt đầu từ 200000 — cao hơn hẳn user ID của MovieLens ml-25m
(1-162.541) để tránh trùng khi gộp interactions_log vào tập huấn luyện.
"""

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime

from api.services.database import get_db

USER_ID_START = 200000


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Băm mật khẩu SHA-256 với salt; trả về (digest, salt)."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return digest, salt


def _row_to_dict(row: sqlite3.Row) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    # Parse genres back to list
    if d.get("genres"):
        try:
            d["genres"] = json.loads(d["genres"])
        except json.JSONDecodeError:
            d["genres"] = []
    else:
        d["genres"] = []
    return d


def register_user(username: str, password: str, genres: list[str] | None = None) -> dict:
    """Đăng ký user mới; raise ValueError nếu username trùng hoặc không hợp lệ."""
    username = username.strip()
    if not username or len(username) < 3:
        raise ValueError("Tên người dùng phải có ít nhất 3 ký tự")
    if not password or len(password) < 4:
        raise ValueError("Mật khẩu phải có ít nhất 4 ký tự")

    db = get_db()

    # Conflict detection on username (case-insensitive)
    existing = db.execute(
        "SELECT 1 FROM users WHERE LOWER(username) = ?", 
        (username.lower(),)
    ).fetchone()
    if existing:
        raise ValueError("Tên người dùng đã tồn tại")

    digest, salt = _hash_password(password)
    genres_json = json.dumps(genres or [], ensure_ascii=False)
    created_at = datetime.now().isoformat(timespec="seconds")

    # Get max ID or start from USER_ID_START
    max_id_row = db.execute("SELECT MAX(user_id) FROM users").fetchone()
    next_id = (max_id_row[0] or (USER_ID_START - 1)) + 1

    try:
        db.execute(
            """INSERT INTO users (user_id, username, password_hash, salt, genres, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (next_id, username, digest, salt, genres_json, created_at)
        )
        db.commit()
    except sqlite3.IntegrityError:
        # Fallback if there's a concurrent insert with same username (UNIQUE constraint)
        raise ValueError("Tên người dùng đã tồn tại")

    return {
        "user_id": next_id,
        "username": username,
        "password_hash": digest,
        "salt": salt,
        "genres": genres or [],
        "created_at": created_at,
    }


def authenticate(username: str, password: str) -> dict | None:
    """Kiểm tra đăng nhập; trả về user nếu hợp lệ, ngược lại None."""
    username = username.strip()
    db = get_db()
    row = db.execute(
        "SELECT * FROM users WHERE LOWER(username) = ?", 
        (username.lower(),)
    ).fetchone()
    
    if not row:
        return None

    user = _row_to_dict(row)
    digest, _ = _hash_password(password, user["salt"])
    if digest == user["password_hash"]:
        return user
    return None


def get_user(user_id: int) -> dict | None:
    """Lấy user theo id (None nếu chưa đăng ký)."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_dict(row)


def update_user_genres(user_id: int, genres: list[str]) -> dict | None:
    """Cập nhật thể loại yêu thích của user; trả về user mới hoặc None."""
    db = get_db()
    
    # Check if user exists first
    existing = get_user(user_id)
    if not existing:
        return None
        
    genres_json = json.dumps(genres, ensure_ascii=False)
    db.execute(
        "UPDATE users SET genres = ? WHERE user_id = ?", 
        (genres_json, user_id)
    )
    db.commit()
    
    return get_user(user_id)
