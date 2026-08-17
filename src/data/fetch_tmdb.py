"""
fetch_tmdb.py — Làm giàu dữ liệu phim sử dụng API TMDb (The Movie Database) hoặc dữ liệu giả lập (mock)

Luồng hoạt động:
  1. Đọc data/raw/movies.csv + links.csv, merge theo movieId (ánh xạ sang tmdbId).
  2. Tải cache cục bộ data/enriched/tmdb_cache.json (nếu có) — cache này lưu metadata
     đã lấy thành công để chạy lại KHÔNG tốn thêm quota API (incremental).
     Lần đầu chạy sẽ tự "seed" từ movies_enriched.csv: các phim đã có poster thật
     (không phải ảnh unsplash mock) được coi như đã cached.
  3. Với mỗi phim CHƯA có trong cache, gọi TMDb API:
     - Song song bằng ThreadPoolExecutor (mặc định 4 workers).
     - Rate limiter theo quota free của TMDb (~40 requests / 10 giây).
     - Retry + backoff khi gặp 429/5xx; 404 (phim không tồn tại) được đánh dấu
       "missing" trong cache để không gọi lại lần sau.
     - Ngôn ngữ ưu tiên vi-VN, fallback en-US.
  4. Phim không lấy được (thiếu key, quá quota, lỗi mạng) → mock như cũ để
     pipeline phía sau không bị đứt.
  5. Ghi kết quả ra data/enriched/movies_enriched.csv + cập nhật cache.

Sử dụng:
  python src/data/fetch_tmdb.py                     # Fetch toàn bộ phim còn thiếu (4 workers)
  python src/data/fetch_tmdb.py --workers 8         # Tăng độ song song
  python src/data/fetch_tmdb.py --limit 50          # Chạy thử N phim (cache vẫn được lưu để resume)
  python src/data/fetch_tmdb.py --reset-cache       # Xoá cache, fetch lại từ đầu
"""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tải biến môi trường
load_dotenv(PROJECT_ROOT / ".env")

RAW_DIR = PROJECT_ROOT / "data" / "raw"
ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched"
ENRICHED_DIR.mkdir(parents=True, exist_ok=True)

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "your_api_key_here")
USE_MOCK = TMDB_API_KEY == "your_api_key_here" or not TMDB_API_KEY.strip()

CACHE_PATH = ENRICHED_DIR / "tmdb_cache.json"
MOCK_PLACEHOLDER = "unsplash"  # Dấu hiệu nhận biết poster giả lập trong dữ liệu cũ

# Quota free của TMDb: ~40 requests / 10 giây
RATE_LIMIT_MAX = 40
RATE_LIMIT_WINDOW = 10.0


def get_mock_metadata(row, genres_dict):
    """Sinh dữ liệu giả lập (mock) cho phim để tránh lỗi khi không có API key."""
    movie_id = row['movieId']
    title = row['title']
    genres = genres_dict.get(movie_id, "Unknown")

    mock_poster = "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=500&auto=format&fit=crop&q=60"
    mock_overview = f"Bộ phim '{title}' thuộc thể loại {genres}. Đây là một tác phẩm điện ảnh xuất sắc, mang lại nhiều cảm xúc và trải nghiệm thú vị cho người xem."

    return {
        "movieId": movie_id,
        "tmdbId": row['tmdbId'],
        "title": title,
        "genres": genres,
        "poster_path": mock_poster,
        "overview": mock_overview,
        "vote_average": 7.0,
        "vote_count": 100,
        "release_date": "2020-01-01",
        "runtime_minutes": 100,  # Thời lượng mặc định khi không có dữ liệu thật
    }


class TmdbRateLimiter:
    """Giới hạn tốc độ gọi API theo quota free của TMDb (fixed-window slots).

    Đảm bảo không bao giờ gửi quá RATE_LIMIT_MAX request trong RATE_LIMIT_WINDOW giây,
    kể cả khi chạy nhiều workers cùng lúc.
    """

    def __init__(self, max_per_window: int = RATE_LIMIT_MAX, window_seconds: float = RATE_LIMIT_WINDOW):
        self._lock = threading.Lock()
        self._slots = [0.0] * max_per_window
        self._idx = 0
        self._window = window_seconds

    def wait(self):
        """Chặn tới khi đủ quyền gửi 1 request."""
        with self._lock:
            now = time.time()
            elapsed = now - self._slots[self._idx]
            if elapsed < self._window:
                time.sleep(self._window - elapsed + 0.02)
            self._slots[self._idx] = time.time()
            self._idx = (self._idx + 1) % len(self._slots)


def _parse_movie_data(data: dict) -> dict:
    """Chuyển response JSON của TMDb thành metadata chuẩn của project."""
    poster_path = data.get("poster_path")
    full_poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
    return {
        "poster_path": full_poster_url,
        "overview": data.get("overview", "Không có mô tả phim."),
        "vote_average": data.get("vote_average", 0.0),
        "vote_count": data.get("vote_count", 0),
        "release_date": data.get("release_date", ""),
        "runtime": data.get("runtime", 0),  # Thời lượng phim (phút) — dùng cho player
    }


def fetch_movie_from_api(tmdb_id, api_key, limiter=None, max_retries=3):
    """Gọi API TMDb lấy metadata 1 phim.

    - Ưu tiên tiếng Việt (vi-VN), fallback en-US khi 404.
    - 429/5xx: retry với backoff tăng dần.
    - Các lỗi 4xx khác: trả None (phim không tồn tại).
    - Lỗi mạng: trả None sau khi retry.
    """
    url = f"https://api.themoviedb.org/3/movie/{int(tmdb_id)}"
    params = {"api_key": api_key, "language": "vi-VN"}

    for attempt in range(max_retries):
        if limiter is not None:
            limiter.wait()
        try:
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 404:
                # Thử lại với tiếng Anh nếu không tìm thấy tiếng Việt
                params["language"] = "en-US"
                response = requests.get(url, params=params, timeout=5)

            if response.status_code == 200:
                return _parse_movie_data(response.json())

            if response.status_code == 429 or response.status_code >= 500:
                backoff = 1.0 * (attempt + 1)
                time.sleep(backoff)
                continue

            return None  # 4xx khác: phim không tồn tại trên TMDb
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None


def load_cache() -> dict:
    """Nạp cache metadata. Nếu chưa có file, seed từ movies_enriched.csv
    (những phim đã có poster thật từ lần chạy trước)."""
    cache: dict = {}
    if CACHE_PATH.exists():
        try:
            cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            print(f"[ℹ] Đã nạp cache cục bộ: {len(cache):,} phim ({CACHE_PATH.name})")
            return cache
        except Exception as e:
            print(f"[⚠] Không đọc được cache ({e}), bỏ qua và seed lại từ enriched.")

    enriched_path = ENRICHED_DIR / "movies_enriched.csv"
    if enriched_path.exists():
        try:
            df = pd.read_csv(enriched_path)
            seeded = 0
            for _, row in df.iterrows():
                poster = str(row.get("poster_path", ""))
                tmdb_id = row.get("tmdbId")
                if poster and MOCK_PLACEHOLDER not in poster and pd.notna(tmdb_id):
                    cache[str(int(tmdb_id))] = {
                        "poster_path": poster,
                        "overview": str(row.get("overview", "")),
                        "vote_average": float(row.get("vote_average", 0.0) or 0.0),
                        "vote_count": int(row.get("vote_count", 0) or 0),
                        "release_date": str(row.get("release_date", "")),
                        "runtime": int(row.get("runtime_minutes", 0) or 0),
                    }
                    seeded += 1
            if seeded:
                print(f"[ℹ] Đã seed cache từ dữ liệu enriched cũ: {seeded:,} phim có poster thật.")
        except Exception as e:
            print(f"[⚠] Không seed được từ enriched ({e}).")
    return cache


def save_cache(cache: dict):
    """Ghi cache ra đĩa (mang theo metadata đã lấy được để chạy lại không tốn quota)."""
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Làm giàu dữ liệu phim với TMDb Metadata")
    parser.add_argument("--workers", type=int, default=4, help="Số luồng gọi API song song (mặc định: 4)")
    parser.add_argument("--limit", type=int, default=None, help="Chỉ gọi API cho N phim đầu tiên (thử nghiệm)")
    parser.add_argument("--prioritize-ratings", action="store_true",
                        help="Ưu tiên fetch các phim có NHIỀU rating nhất trước (kết hợp --limit để dùng đúng ngân sách quota)")
    parser.add_argument("--reset-cache", action="store_true", help="Xoá cache cục bộ và fetch lại từ đầu")
    args = parser.parse_args()

    print(f"{'='*60}")
    print("  MovieRS — Làm giàu dữ liệu phim với TMDb Metadata")
    print(f"{'='*60}")

    if args.reset_cache:
        if CACHE_PATH.exists():
            CACHE_PATH.unlink()
            print("[🗑] Đã xoá cache cục bộ.")

    movies_path = RAW_DIR / "movies.csv"
    links_path = RAW_DIR / "links.csv"

    if not movies_path.exists() or not links_path.exists():
        print("[✗] Không tìm thấy movies.csv hoặc links.csv trong thư mục data/raw/!")
        print("    Vui lòng chạy script tải dữ liệu trước: python src/data/download_movielens.py")
        sys.exit(1)

    movies_df = pd.read_csv(movies_path)
    links_df = pd.read_csv(links_path)

    # Hợp nhất links và movies
    df = pd.merge(movies_df, links_df, on="movieId")

    # Lọc bỏ các hàng thiếu tmdbId
    df = df.dropna(subset=["tmdbId"])
    df["tmdbId"] = df["tmdbId"].astype(int)

    # Tạo dictionary để tra cứu thể loại nhanh
    genres_dict = dict(zip(movies_df['movieId'], movies_df['genres']))

    if USE_MOCK:
        print("[ℹ] Đang sử dụng chế độ GIẢ LẬP (MOCK) vì không tìm thấy TMDB_API_KEY hợp lệ.")
        print("    Mẹo: Bạn có thể lấy API Key miễn phí tại themoviedb.org và điền vào file .env")
        enriched_data = [get_mock_metadata(row, genres_dict) for _, row in df.iterrows()]
        print(f"[✓] Hoàn tất (MOCK): {len(enriched_data):,} phim.")
    else:
        cache = load_cache()

        # Tìm các phim chưa có trong cache (cần gọi API)
        missing_full = []
        for idx, row in df.iterrows():
            tmdb_id = str(int(row["tmdbId"]))
            if tmdb_id not in cache:
                missing_full.append((idx, tmdb_id))

        # Ưu tiên phim nhiều rating nhất: đếm rating theo movieId từ raw ratings.csv
        if args.prioritize_ratings:
            ratings_path = RAW_DIR / "ratings.csv"
            if ratings_path.exists():
                counts = pd.read_csv(ratings_path, usecols=["movieId"])["movieId"].value_counts()
                missing_full.sort(
                    key=lambda pair: counts.get(df.at[pair[0], "movieId"], 0),
                    reverse=True,
                )
                print("    [★] Đã sắp xếp theo số lượng rating (phim phổ biến fetch trước)")

        missing = missing_full[:args.limit] if args.limit is not None else missing_full
        to_fetch = len(missing)

        print(f"[🌐] Sử dụng TMDb API thực tế ({args.workers} workers, rate-limit {RATE_LIMIT_MAX}/{int(RATE_LIMIT_WINDOW)}s)")
        print(f"    Tổng số phim: {len(df):,} | Đã có metadata trong cache: {len(df) - len(missing_full):,} "
              f"| Cần gọi API: {len(missing_full):,} | Lần này sẽ gọi: {to_fetch:,}")
        if len(missing_full):
            estimate_min = len(missing_full) * RATE_LIMIT_WINDOW / RATE_LIMIT_MAX / 60
            print(f"    Ước tính thời gian: ~{estimate_min:.0f} phút (chạy lại sẽ bỏ qua phần đã cache)")

        limiter = TmdbRateLimiter()
        fetched_ok = 0
        fetched_missing_movie = 0
        failed = 0

        def _worker(pair):
            _, tmdb_id = pair
            meta = fetch_movie_from_api(tmdb_id, TMDB_API_KEY, limiter=limiter)
            return tmdb_id, meta

        if to_fetch:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                done = 0
                for tmdb_id, meta in pool.map(_worker, missing):
                    cache[tmdb_id] = meta  # None = phim không tồn tại, cache để khỏi gọi lại
                    if meta is not None:
                        fetched_ok += 1
                    else:
                        fetched_missing_movie += 1
                    done += 1
                    if done % 100 == 0 or done == to_fetch:
                        print(f"    ✓ Đã xử lý {done}/{to_fetch} API calls "
                              f"(OK: {fetched_ok}, Không tồn tại: {fetched_missing_movie}, Lỗi: {failed})")
            save_cache(cache)
            print(f"    ✓ Đã lưu cache: {CACHE_PATH}")

        # Dựng dữ liệu enriched theo đúng thứ tự df
        enriched_data = []
        used_real = 0
        used_mock = 0
        for idx, row in df.iterrows():
            tmdb_id = str(int(row["tmdbId"]))
            entry = cache.get(tmdb_id)
            if entry:
                meta = {
                    "movieId": row["movieId"],
                    "tmdbId": row["tmdbId"],
                    "title": row["title"],
                    "genres": row["genres"],
                    "poster_path": entry["poster_path"],
                    "overview": entry["overview"],
                    "vote_average": entry["vote_average"],
                    "vote_count": entry["vote_count"],
                    "release_date": entry["release_date"],
                    "runtime_minutes": int(entry.get("runtime") or 0) or 100,
                }
                used_real += 1
            else:
                meta = get_mock_metadata(row, genres_dict)
                used_mock += 1
            enriched_data.append(meta)

        print(f"    ✓ Metadata thật: {used_real:,} | Mock: {used_mock:,}")

    # Tạo DataFrame và lưu
    enriched_df = pd.DataFrame(enriched_data)
    output_path = ENRICHED_DIR / "movies_enriched.csv"
    enriched_df.to_csv(output_path, index=False, encoding="utf-8")

    print(f"\n[✓] Hoàn tất! Đã lưu {len(enriched_df):,} phim vào: {output_path}")
    print("    Bước tiếp theo: python src/data/preprocess.py")


if __name__ == "__main__":
    main()
