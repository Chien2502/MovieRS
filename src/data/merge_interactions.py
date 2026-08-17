"""
merge_interactions.py — Gộp feedback log (interactions_log.csv) vào dữ liệu ratings và tái chia split

Quy trình:
  1. Đọc ratings_processed.csv (dữ liệu gốc đã xử lý) và interactions_log.csv (feedback mới từ API).
  2. Gộp, dedupe (giữ rating mới nhất theo cặp user-movie), sắp xếp theo timestamp.
  3. Tái chia Temporal Split 80/10/10 và ghi lại ratings_train/val/test.csv.
  4. Feedback từ interactions_log được chuyển vào TRAIN để user mới tương tác
     trở thành "user ấm" sau mỗi chu kỳ retrain (nếu để temporal split thuần túy,
     các bản ghi mới nhất sẽ luôn rơi vào TEST và vòng phản hồi vô hiệu).

Sử dụng:
  python src/data/merge_interactions.py

Lưu ý:
  - Script idempotent: chạy lại nhiều lần an toàn.
  - Được gọi tự động ở đầu retrain.py để vòng lặp feedback luôn được đưa vào huấn luyện
    mà không trộn lẫn dữ liệu thô với train set.
"""

import sys
from pathlib import Path
import pandas as pd

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RATINGS_PROCESSED_CSV = PROCESSED_DIR / "ratings_processed.csv"
INTERACTIONS_LOG_CSV = PROCESSED_DIR / "interactions_log.csv"


def _normalize_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hóa cột timestamp về dạng datetime (hỗ trợ cả epoch seconds và chuỗi datetime)."""
    if 'timestamp' not in df.columns:
        return df
    ts = pd.to_datetime(df['timestamp'], errors='coerce', unit='s')
    # Với các giá trị không phải epoch (chuỗi datetime), thử parse lại không có unit
    invalid_mask = ts.isna() & df['timestamp'].notna()
    if invalid_mask.any():
        ts.loc[invalid_mask] = pd.to_datetime(df.loc[invalid_mask, 'timestamp'], errors='coerce')
    df['timestamp'] = ts
    return df


def merge_and_split(verbose: bool = True) -> dict:
    """Gộp interactions_log vào ratings_processed và tái tạo các tập train/val/test."""
    if not RATINGS_PROCESSED_CSV.exists():
        raise FileNotFoundError(f"Không tìm thấy file dữ liệu đã xử lý: {RATINGS_PROCESSED_CSV}. "
                                f"Vui lòng chạy: python src/data/preprocess.py")

    base_df = pd.read_csv(RATINGS_PROCESSED_CSV)
    n_base = len(base_df)

    log_df = pd.DataFrame(columns=['userId', 'movieId', 'rating', 'timestamp'])
    if INTERACTIONS_LOG_CSV.exists():
        log_df = pd.read_csv(INTERACTIONS_LOG_CSV)
    n_log = len(log_df)

    if verbose:
        print("=" * 60)
        print("  MovieRS — Gộp Feedback Log & Tái chia Split")
        print("=" * 60)
        print(f"[📥] Dữ liệu gốc (processed) : {n_base:,} ratings")
        print(f"[📥] Feedback log           : {n_log:,} ratings")

    if n_log == 0:
        combined = base_df.copy()
    else:
        combined = pd.concat([base_df, log_df], ignore_index=True)

    combined = _normalize_timestamps(combined)

    # Dedupe: với cặp user-movie trùng, giữ bản ghi có timestamp mới nhất
    combined = combined.sort_values(by='timestamp', na_position='last')
    combined = combined.drop_duplicates(subset=['userId', 'movieId'], keep='last')
    combined = combined.reset_index(drop=True)

    if verbose:
        print(f"[🧮] Sau khi gộp & dedupe     : {len(combined):,} ratings")

    # Temporal Split 80/10/10 (giống split.py)
    total = len(combined)
    train_end = int(total * 0.8)
    val_end = int(total * 0.9)

    train_df = combined.iloc[:train_end]
    val_df = combined.iloc[train_end:val_end]
    test_df = combined.iloc[val_end:]

    # Feedback mới từ interactions_log luôn được đưa vào TRAIN (không phải TEST):
    # Vì temporal split xếp các bản ghi mới nhất vào cuối → chúng rơi vào TEST,
    # khiến user mới tương tác không bao giờ trở thành "user ấm".
    # Chuyển toàn bộ cặp user-movie có trong log sang TRAIN để vòng phản hồi
    # thực sự cải thiện cá nhân hóa (val/test giữ nguyên lịch sử).
    if n_log > 0:
        log_keys = set(zip(log_df['userId'], log_df['movieId']))
        log_mask = combined.apply(
            lambda r: (r['userId'], r['movieId']) in log_keys, axis=1
        )
        val_df = val_df[~val_df.apply(
            lambda r: (r['userId'], r['movieId']) in log_keys, axis=1
        )]
        test_df = test_df[~test_df.apply(
            lambda r: (r['userId'], r['movieId']) in log_keys, axis=1
        )]
        train_df = pd.concat([train_df, combined[log_mask]], ignore_index=True)
        # Dedupe trong TRAIN: giữ bản ghi có timestamp mới nhất (bản log)
        train_df = train_df.sort_values(by='timestamp', na_position='last')
        train_df = train_df.drop_duplicates(
            subset=['userId', 'movieId'], keep='last'
        ).reset_index(drop=True)

    train_df.to_csv(PROCESSED_DIR / "ratings_train.csv", index=False)
    val_df.to_csv(PROCESSED_DIR / "ratings_val.csv", index=False)
    test_df.to_csv(PROCESSED_DIR / "ratings_test.csv", index=False)

    if verbose:
        print(f"[✓] Đã ghi lại các tập split:")
        print(f"    - TRAIN (80%): {len(train_df):,}")
        print(f"    - VAL   (10%): {len(val_df):,}")
        print(f"    - TEST  (10%): {len(test_df):,}")
        print(f"{'=' * 60}")

    return {
        "base_ratings": n_base,
        "log_ratings": n_log,
        "total_ratings": len(combined),
        "train": len(train_df),
        "val": len(val_df),
        "test": len(test_df),
    }


def main():
    try:
        merge_and_split()
    except FileNotFoundError as e:
        print(f"[✗] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
