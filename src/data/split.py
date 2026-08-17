"""
split.py — Chia dữ liệu ratings thành tập Train/Validation/Test sử dụng Temporal Split

Tại sao dùng Temporal Split thay vì Random Split?
  Trong môi trường thực tế, sở thích của người dùng thay đổi theo thời gian.
  Nếu chia ngẫu nhiên (Random Split), mô hình có thể dùng dữ liệu tương lai để dự đoán quá khứ,
  dẫn đến hiện tượng rò rỉ dữ liệu (Data Leakage) và làm sai lệch chỉ số đánh giá thực tế.
  Do đó, việc sắp xếp theo thời gian (timestamp) và cắt dữ liệu (ví dụ: 80% cũ làm train,
  10% tiếp theo làm validation, 10% mới nhất làm test) phản ánh chính xác nhất cách hệ thống hoạt động.

Sử dụng:
  python src/data/split.py
"""

import sys
from pathlib import Path
import pandas as pd

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def main():
    print(f"{'='*60}")
    print("  MovieRS — Chia dữ liệu Train/Validation/Test (Temporal Split)")
    print(f"{'='*60}")
    
    ratings_path = PROCESSED_DIR / "ratings_processed.csv"
    
    if not ratings_path.exists():
        print(f"[✗] Không tìm thấy file dữ liệu ratings đã xử lý: {ratings_path}")
        print("    Vui lòng chạy script tiền xử lý trước: python src/data/preprocess.py")
        sys.exit(1)
        
    df = pd.read_csv(ratings_path)
    
    # Chuyển timestamp về dạng DateTime nếu chưa có
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 1. Sắp xếp ratings theo dòng thời gian (từ cũ đến mới)
    print("[⏳] Đang sắp xếp dữ liệu theo dòng thời gian (timestamp)...")
    df = df.sort_values(by='timestamp').reset_index(drop=True)
    
    # 2. Tính toán điểm phân chia
    total_ratings = len(df)
    train_end = int(total_ratings * 0.8)
    val_end = int(total_ratings * 0.9)
    
    # 3. Phân tách
    train_df = df.iloc[:train_end]
    val_df = df.iloc[train_end:val_end]
    test_df = df.iloc[val_end:]
    
    print(f"[📊] Kết quả phân chia:")
    print(f"    - Tập TRAIN (80%): {len(train_df):,} dòng (Từ {train_df['timestamp'].min()} đến {train_df['timestamp'].max()})")
    print(f"    - Tập VAL   (10%): {len(val_df):,} dòng (Từ {val_df['timestamp'].min()} đến {val_df['timestamp'].max()})")
    print(f"    - Tập TEST  (10%): {len(test_df):,} dòng (Từ {test_df['timestamp'].min()} đến {test_df['timestamp'].max()})")
    
    # 4. Kiểm tra sự trùng lặp của user giữa các tập (để phân tích Cold-Start sau này)
    train_users = set(train_df['userId'])
    val_users = set(val_df['userId'])
    test_users = set(test_df['userId'])
    
    test_cold_users = test_users - train_users
    print(f"\n[ℹ] Phân tích người dùng mới (Cold-Start Users) ở tập TEST:")
    print(f"    - Số user ở tập TEST: {len(test_users):,}")
    print(f"    - Số user mới xuất hiện ở TEST (không có trong TRAIN): {len(test_cold_users):,} ({len(test_cold_users)/len(test_users)*100:.1f}%)")
    print("      → Đây chính là đối tượng dùng để kiểm nghiệm bài toán Cold-Start.")
    
    # 5. Lưu các tập dữ liệu
    train_df.to_csv(PROCESSED_DIR / "ratings_train.csv", index=False)
    val_df.to_csv(PROCESSED_DIR / "ratings_val.csv", index=False)
    test_df.to_csv(PROCESSED_DIR / "ratings_test.csv", index=False)
    
    print(f"\n[✓] Đã lưu các tập dữ liệu thành công vào: {PROCESSED_DIR}")
    print("    Bước tiếp theo: Thiết lập Baseline và xây dựng mô hình gợi ý.")


if __name__ == "__main__":
    main()
