"""
database.py — Quản lý kết nối SQLite và khởi tạo schema
"""

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "moviers.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Khởi tạo schema bằng một connection dùng 1 lần
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT,
            salt TEXT,
            genres TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS interactions (
            user_id INTEGER,
            movie_id INTEGER,
            rating REAL,
            timestamp TEXT,
            UNIQUE(user_id, movie_id)
        );
        CREATE INDEX IF NOT EXISTS idx_interactions_user_id ON interactions(user_id);

        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            movie_id INTEGER,
            added_at TEXT,
            UNIQUE(user_id, movie_id)
        );
        CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);

        CREATE TABLE IF NOT EXISTS watch_progress (
            user_id INTEGER,
            movie_id INTEGER,
            position_seconds INTEGER,
            duration_seconds INTEGER,
            ratio REAL,
            status TEXT,
            updated_at TEXT,
            UNIQUE(user_id, movie_id)
        );
        CREATE INDEX IF NOT EXISTS idx_watch_progress_user_id ON watch_progress(user_id);

        CREATE TABLE IF NOT EXISTS movies (
            movie_id INTEGER PRIMARY KEY,
            title TEXT,
            genres TEXT,
            release_year INTEGER,
            overview TEXT,
            poster_path TEXT,
            runtime_minutes INTEGER,
            release_date TEXT
        );
    """)
    conn.commit()
    conn.close()

def get_db() -> sqlite3.Connection:
    """Trả về một connection độc lập cho mỗi thread/request để tránh race condition."""
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# Initialize DB when module is imported
init_db()
