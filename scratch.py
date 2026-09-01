from api.services.database import get_db

conn = get_db()
c = conn.cursor()
c.execute("INSERT OR REPLACE INTO watch_progress (user_id, movie_id, ratio) VALUES (1, 1, 0.5)")
conn.commit()
print("Inserted")
print(c.execute("SELECT * FROM watch_progress").fetchall())
