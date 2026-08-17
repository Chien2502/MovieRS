"""
user_store.py — Lưu trữ người dùng đăng ký (data/processed/users.json)

Prototype-level: file JSON đơn giản + khóa threading.Lock cho ghi đồng thời.
Mật khẩu được băm SHA-256 kèm salt (không lưu plaintext).
User ID tự tăng bắt đầu từ 200000 — cao hơn hẳn user ID của MovieLens ml-25m
(1-162.541) để tránh trùng khi gộp interactions_log vào tập huấn luyện.
"""

import hashlib
import json
import secrets
import threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
USERS_FILE = PROJECT_ROOT / "data" / "processed" / "users.json"

USER_ID_START = 200000

_lock = threading.Lock()


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Băm mật khẩu SHA-256 với salt; trả về (digest, salt)."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return digest, salt


def _load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_users(users: dict):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def register_user(username: str, password: str, genres: list[str] | None = None) -> dict:
    """Đăng ký user mới; raise ValueError nếu username trùng hoặc không hợp lệ."""
    username = username.strip()
    if not username or len(username) < 3:
        raise ValueError("Tên người dùng phải có ít nhất 3 ký tự")
    if not password or len(password) < 4:
        raise ValueError("Mật khẩu phải có ít nhất 4 ký tự")

    with _lock:
        users = _load_users()
        if any(u["username"].lower() == username.lower() for u in users.values()):
            raise ValueError("Tên người dùng đã tồn tại")

        next_id = max((int(uid) for uid in users), default=USER_ID_START - 1) + 1
        digest, salt = _hash_password(password)
        user = {
            "user_id": next_id,
            "username": username,
            "password_hash": digest,
            "salt": salt,
            "genres": genres or [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        users[str(next_id)] = user
        _save_users(users)
        return user


def authenticate(username: str, password: str) -> dict | None:
    """Kiểm tra đăng nhập; trả về user nếu hợp lệ, ngược lại None."""
    username = username.strip()
    users = _load_users()
    for user in users.values():
        if user["username"].lower() == username.lower():
            digest, _ = _hash_password(password, user["salt"])
            if digest == user["password_hash"]:
                return user
            return None
    return None


def get_user(user_id: int) -> dict | None:
    """Lấy user theo id (None nếu chưa đăng ký)."""
    return _load_users().get(str(user_id))


def update_user_genres(user_id: int, genres: list[str]) -> dict | None:
    """Cập nhật thể loại yêu thích của user; trả về user mới hoặc None."""
    with _lock:
        users = _load_users()
        user = users.get(str(user_id))
        if user is None:
            return None
        user["genres"] = list(genres)
        _save_users(users)
        return user
