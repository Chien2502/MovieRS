"""
preprocess.py — Tiền xử lý dữ liệu phim và đánh giá (ratings)

Script này thực hiện:
  1. Đọc dữ liệu phim đã được làm giàu (movies_enriched.csv) và dữ liệu ratings (ratings.csv).
  2. Trích xuất năm phát hành (release_year) từ tiêu đề phim (ví dụ: "Toy Story (1995)" -> 1995).
  3. Làm sạch dữ liệu ratings (xử lý giá trị trùng lặp, giá trị null, định dạng timestamp).
  4. Lưu dữ liệu đã làm sạch vào data/processed/.

Sử dụng:
  python src/data/preprocess.py                    # Xử lý toàn bộ ratings
  python src/data/preprocess.py --max-ratings 2000000  # Giới hạn số ratings (cân đối thời gian train)
  python src/data/preprocess.py --min-user-ratings 10  # Chỉ giữ user có >= N ratings (dày lịch sử, SVD học tốt hơn)
"""

import re
import sys
from pathlib import Path
import pandas as pd

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RAW_DIR = PROJECT_ROOT / "data" / "raw"
ENRICHED_DIR = PROJECT_ROOT / "data" / "enriched"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def extract_year(title: str) -> int:
    """Trích xuất năm phát hành từ tiêu đề phim (ví dụ: 'Toy Story (1995)' -> 1995)."""
    match = re.search(r'\((\d{4})\)', title)
    if match:
        return int(match.group(1))
    return 0  # Giá trị mặc định nếu không tìm thấy năm


def preprocess_movies(movies_path: Path) -> pd.DataFrame:
    """Tiền xử lý dữ liệu movies_enriched."""
    print("[🎬] Đang tiền xử lý dữ liệu phim...")
    df = pd.read_csv(movies_path)
    
    # 1. Trích xuất năm phát hành từ tiêu đề
    df['release_year'] = df['title'].apply(extract_year)
    
    # Nếu cột release_date từ TMDb có thông tin năm, có thể ưu tiên lấy năm từ đó
    # nếu không trích xuất được từ tiêu đề
    def fill_year_from_date(row):
        if row['release_year'] == 0 and pd.notna(row['release_date']):
            date_str = str(row['release_date'])
            if len(date_str) >= 4:
                return int(date_str[:4])
        return row['release_year']
        
    df['release_year'] = df.apply(fill_year_from_date, axis=1)
    
    # 2. Xử lý giá trị null ở overview và poster_path
    df['overview'] = df['overview'].fillna("Không có thông tin mô tả phim.")
    df['poster_path'] = df['poster_path'].fillna("")
    
    # 2b. Thời lượng phim (phút) — dùng cho player "Tiếp tục xem"; mặc định 100 nếu thiếu
    if 'runtime_minutes' not in df.columns:
        df['runtime_minutes'] = 100
    df['runtime_minutes'] = df['runtime_minutes'].fillna(100).astype(int).clip(lower=30)
    
    # 3. Chuẩn hóa thể loại (genres) thành dạng list/array ngăn cách bằng dấu phẩy thay vì '|'
    df['genres'] = df['genres'].apply(lambda x: x.replace('|', ', ') if isinstance(x, str) else "")
    
    print(f"    ✓ Tổng số phim: {len(df):,}")
    print(f"    ✓ Khoảng năm phát hành: {df[df['release_year'] > 0]['release_year'].min()} - {df['release_year'].max()}")
    return df


def preprocess_ratings(ratings_path: Path, max_ratings: int | None = None,
                       min_user_ratings: int | None = None,
                       min_movie_ratings: int | None = None) -> pd.DataFrame:
    """Tiền xử lý dữ liệu ratings (có thể giới hạn số rating để cân đối thời gian train)."""
    print("[⭐] Đang tiền xử lý dữ liệu ratings...")
    df = pd.read_csv(ratings_path)
    initial_len = len(df)

    # 1. Lọc user có lịch sử dày (đuôi dài làm SVD học kém, RMSE val khó so sánh):
    #    chỉ giữ user có >= N ratings.
    if min_user_ratings is not None:
        counts = df['userId'].value_counts()
        keep_users = counts[counts >= min_user_ratings].index
        df = df[df['userId'].isin(keep_users)]
        print(f"    ⚠ Chỉ giữ user có >= {min_user_ratings} ratings: "
              f"{len(df):,} ratings từ {len(keep_users):,} users.")

    # 2. Lọc phim phổ biến: chỉ giữ ratings của phim có >= N ratings.
    #    Mẫu ngẫu nhiên từ toàn bộ 25M ratings rải mỏng trên hàng nghìn phim đuôi dài
    #    khiến SVD học kém. Ưu tiên phim được xem nhiều -> dữ liệu dày, RMSE ổn định.
    if min_movie_ratings is not None:
        counts = df['movieId'].value_counts()
        keep_movies = counts[counts >= min_movie_ratings].index
        df = df[df['movieId'].isin(keep_movies)]
        print(f"    ⚠ Chỉ giữ phim có >= {min_movie_ratings} ratings: "
              f"{len(df):,} ratings từ {len(keep_movies):,} phim.")

    # 3. Giới hạn số lượng ratings (ngẫu nhiên, tái lập được) — phục vụ dự án học thuật:
    #    dataset quá lớn (ml-25m = 25M rows) làm thời gian huấn luyện SVD không khả thi.
    if max_ratings is not None and len(df) > max_ratings:
        df = df.sample(n=max_ratings, random_state=42)
        print(f"    ⚠ Dataset quá lớn: giới hạn còn {len(df):,} ratings (từ {initial_len:,} ban đầu) "
              f"để cân đối thời gian huấn luyện.")

    # 4. Kiểm tra các giá trị null
    before_null_check = len(df)
    df = df.dropna(subset=['userId', 'movieId', 'rating', 'timestamp'])
    if len(df) < before_null_check:
        print(f"    ⚠ Đã xóa {before_null_check - len(df)} dòng bị thiếu thông tin.")

    # 5. Xử lý trùng lặp (nếu một user đánh giá một phim nhiều lần, chỉ giữ lại đánh giá cuối cùng)
    df = df.sort_values(by='timestamp')
    df = df.drop_duplicates(subset=['userId', 'movieId'], keep='last')

    # 6. Chuẩn hóa timestamp sang định dạng ngày tháng để dễ đọc/phân tích
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

    print(f"    ✓ Tổng số rating đã làm sạch: {len(df):,}")
    print(f"    ✓ Số lượng users độc nhất: {df['userId'].nunique():,}")
    print(f"    ✓ Số lượng phim đã được đánh giá: {df['movieId'].nunique():,}")
    return df


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Tiền xử lý dữ liệu phim & ratings")
    parser.add_argument("--max-ratings", type=int, default=None,
                        help="Giới hạn số ratings đưa vào huấn luyện (ví dụ 2000000). "
                             "Mặc định: dùng toàn bộ.")
    parser.add_argument("--min-user-ratings", type=int, default=None,
                        help="Chỉ giữ user có ít nhất N ratings (lọc đuôi dài, SVD học tốt hơn).")
    parser.add_argument("--min-movie-ratings", type=int, default=None,
                        help="Chỉ giữ ratings của phim có ít nhất N ratings (dữ liệu dày, RMSE ổn định).")
    parser.add_argument("--movies-only", action="store_true",
                        help="Chỉ tái tạo movies_processed.csv (KHÔNG đụng ratings) — dùng khi "
                             "thay đổi metadata phim mà không muốn re-sample ratings.")
    args = parser.parse_args()

    print(f"{'='*60}")
    print("  MovieRS — Tiền xử lý dữ liệu phim & ratings")
    print(f"{'='*60}")
    
    movies_enriched_path = ENRICHED_DIR / "movies_enriched.csv"
    ratings_raw_path = RAW_DIR / "ratings.csv"
    
    if not movies_enriched_path.exists():
        print(f"[✗] Không tìm thấy file: {movies_enriched_path}")
        print("    Vui lòng chạy script làm giàu dữ liệu trước: python src/data/fetch_tmdb.py")
        sys.exit(1)

    # Chế độ --movies-only: chỉ tái sinh movies_processed.csv, ratings giữ nguyên
    if args.movies_only:
        print("[🎬] Chế độ --movies-only: chỉ xử lý phim (ratings không bị thay đổi)...")
        processed_movies_df = preprocess_movies(movies_enriched_path)
        movies_out = PROCESSED_DIR / "movies_processed.csv"
        processed_movies_df.to_csv(movies_out, index=False, encoding="utf-8")
        print(f"\n[✓] Đã lưu thông tin phim: {movies_out} ({len(processed_movies_df):,} phim)")
        print("    Ratings giữ nguyên — không cần retrain lại mô hình.")
        return
        
    if not ratings_raw_path.exists():
        print(f"[✗] Không tìm thấy file: {ratings_raw_path}")
        sys.exit(1)
        
    # Xử lý
    processed_movies_df = preprocess_movies(movies_enriched_path)
    processed_ratings_df = preprocess_ratings(
        ratings_raw_path,
        max_ratings=args.max_ratings,
        min_user_ratings=args.min_user_ratings,
        min_movie_ratings=args.min_movie_ratings,
    )
    
    # Lưu kết quả
    movies_out = PROCESSED_DIR / "movies_processed.csv"
    ratings_out = PROCESSED_DIR / "ratings_processed.csv"
    
    processed_movies_df.to_csv(movies_out, index=False, encoding="utf-8")
    processed_ratings_df.to_csv(ratings_out, index=False, encoding="utf-8")
    
    print(f"\n[✓] Tiền xử lý hoàn tất!")
    print(f"    - Đã lưu thông tin phim: {movies_out}")
    print(f"    - Đã lưu ratings: {ratings_out}")
    print("    Bước tiếp theo: python src/data/split.py")


if __name__ == "__main__":
    main()
