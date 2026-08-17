"""
backfill_runtime.py — Bổ sung thời lượng phim (runtime) cho cache TMDb + movies_enriched.csv

Bối cảnh: các phim được fetch trước khi có tính năng lưu `runtime` nên cache
không có thời lượng. Script này:
  1. Đọc tmdb_cache.json, tìm phim thiếu runtime (0/None).
  2. Ưu tiên fetch runtime của N phim PHỔ BIẾN NHẤT (theo số rating trong raw)
     trước — đúng ngân sách quota, phim người dùng thực sự xem có thời lượng thật.
  3. Cập nhật cache + tái sinh movies_enriched.csv (runtime_minutes, mặc định 100).
  4. Gợi ý chạy: python src/data/preprocess.py --movies-only (không đụng ratings)

Sử dụng:
  python src/utils/backfill_runtime.py --limit 300
"""

import json
import sys
from pathlib import Path
import pandas as pd

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.fetch_tmdb import (
    CACHE_PATH, ENRICHED_DIR, RAW_DIR, TMDB_API_KEY, USE_MOCK,
    TmdbRateLimiter, fetch_movie_from_api, load_cache, save_cache,
)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backfill runtime cho cache TMDb")
    parser.add_argument("--limit", type=int, default=300,
                        help="Số phim phổ biến nhất cần fetch runtime (mặc định: 300)")
    args = parser.parse_args()

    if USE_MOCK:
        print("[✗] Không có TMDB_API_KEY hợp lệ trong .env — không thể backfill runtime.")
        sys.exit(1)

    print("=" * 60)
    print("  MovieRS — Backfill thời lượng phim (runtime)")
    print("=" * 60)

    cache = load_cache()

    # Bản đồ movieId -> tmdbId từ movies.csv + links.csv
    movies_df = pd.read_csv(RAW_DIR / "movies.csv")
    links_df = pd.read_csv(RAW_DIR / "links.csv")
    df = pd.merge(movies_df, links_df, on="movieId").dropna(subset=["tmdbId"])
    df["tmdbId"] = df["tmdbId"].astype(int)
    movie_to_tmdb = dict(zip(df["movieId"], df["tmdbId"]))

    # Số rating theo movieId (ưu tiên phim phổ biến)
    ratings_path = RAW_DIR / "ratings.csv"
    counts = pd.read_csv(ratings_path, usecols=["movieId"])["movieId"].value_counts()

    # Danh sách tmdbId thiếu runtime, sắp theo độ phổ biến
    missing = []
    for movie_id, tmdb_id in movie_to_tmdb.items():
        entry = cache.get(str(tmdb_id))
        if entry is None or not entry.get("runtime"):
            missing.append((tmdb_id, counts.get(movie_id, 0)))
    missing.sort(key=lambda x: -x[1])
    to_fetch = missing[: args.limit]

    print(f"    Phim thiếu runtime: {len(missing):,} | Sẽ fetch: {len(to_fetch):,} "
          f"(phim phổ biến nhất)")

    limiter = TmdbRateLimiter()
    ok = 0
    for i, (tmdb_id, rating_count) in enumerate(to_fetch, 1):
        meta = fetch_movie_from_api(tmdb_id, TMDB_API_KEY, limiter=limiter)
        tid = str(tmdb_id)
        if meta is not None:
            entry = cache.get(tid) or {}
            entry["runtime"] = meta.get("runtime") or 0
            cache[tid] = entry
            ok += 1
        if i % 50 == 0 or i == len(to_fetch):
            print(f"    ✓ Đã xử lý {i}/{len(to_fetch)} (runtime OK: {ok})")

    save_cache(cache)
    print(f"    ✓ Đã cập nhật cache: {CACHE_PATH}")

    # Tái sinh movies_enriched.csv với cột runtime_minutes
    enriched_path = ENRICHED_DIR / "movies_enriched.csv"
    enriched_df = pd.read_csv(enriched_path)
    runtimes = []
    for _, row in enriched_df.iterrows():
        tid = str(int(row["tmdbId"])) if pd.notna(row["tmdbId"]) else ""
        entry = cache.get(tid, {}) or {}
        runtimes.append(int(entry.get("runtime") or 0) or 100)
    enriched_df["runtime_minutes"] = runtimes
    enriched_df.to_csv(enriched_path, index=False, encoding="utf-8")
    print(f"    ✓ Đã ghi runtime_minutes vào: {enriched_path}")

    print("\n[✓] Hoàn tất backfill runtime!")
    print("    Bước tiếp theo: python src/data/preprocess.py --movies-only")


if __name__ == "__main__":
    main()
