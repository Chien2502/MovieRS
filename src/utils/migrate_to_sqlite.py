import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.services.database import get_db


def migrate_users():
    users_path = PROJECT_ROOT / "data" / "processed" / "users.json"
    if not users_path.exists():
        print("Không tìm thấy users.json")
        return
        
    with open(users_path, "r", encoding="utf-8") as f:
        users = json.load(f)
        
    conn = get_db()
    c = conn.cursor()
    count = 0
    for u in users:
        genres_str = json.dumps(u.get("genres", []), ensure_ascii=False)
        try:
            c.execute(
                "INSERT OR REPLACE INTO users (user_id, username, password_hash, salt, genres, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (u["user_id"], u["username"], u["password_hash"], u.get("salt", ""), genres_str, u.get("created_at", ""))
            )
            count += 1
        except Exception as e:
            print(f"Lỗi thêm user {u['user_id']}: {e}")
            
    conn.commit()
    print(f"Đã migrate {count} users")

def migrate_csv(file_name, table_name, df_processor):
    path = PROJECT_ROOT / "data" / "processed" / file_name
    if not path.exists():
        print(f"Không tìm thấy {file_name}")
        return
        
    df = pd.read_csv(path).fillna("")
    if df.empty:
        print(f"File {file_name} rỗng")
        return
        
    conn = get_db()
    rows = df_processor(df)
    
    if not rows:
        return
        
    placeholders = ",".join(["?"] * len(rows[0]))
    c = conn.cursor()
    c.executemany(f"INSERT OR REPLACE INTO {table_name} VALUES ({placeholders})", rows)
    conn.commit()
    print(f"Đã migrate {len(rows)} dòng vào {table_name}")

def main():
    print("Bắt đầu migrate dữ liệu sang SQLite...")
    
    migrate_users()
    
    # Interactions
    def proc_interactions(df):
        return df[['userId', 'movieId', 'rating', 'timestamp']].values.tolist()
    migrate_csv("interactions_log.csv", "interactions", proc_interactions)
    
    # Favorites
    def proc_favorites(df):
        return df[['userId', 'movieId', 'added_at']].values.tolist()
    migrate_csv("user_favorites.csv", "favorites", proc_favorites)
    
    # Watch progress
    def proc_watch(df):
        return df[['userId', 'movieId', 'position_seconds', 'duration_seconds', 'ratio', 'status', 'updated_at']].values.tolist()
    migrate_csv("watch_progress.csv", "watch_progress", proc_watch)
    
    # Movies
    def proc_movies(df):
        return df[['movieId', 'title', 'genres', 'release_year', 'overview', 'poster_path', 'runtime_minutes', 'release_date']].values.tolist()
    migrate_csv("movies_processed.csv", "movies", proc_movies)
    
    print("Hoàn tất!")

if __name__ == "__main__":
    main()
