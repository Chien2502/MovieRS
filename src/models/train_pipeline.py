"""
train_pipeline.py — Quy trình huấn luyện, đánh giá và so sánh tất cả các mô hình

Quy trình hoạt động:
  1. Tải các tập dữ liệu ratings (Train/Val/Test) và thông tin phim đã xử lý.
  2. Huấn luyện mô hình Mean, Popularity, KNN (Baselines).
  3. Huấn luyện mô hình SVD tự viết (NumPy) và SVD thư viện (Surprise).
  4. Đánh giá chất lượng của từng mô hình bằng các metric: RMSE, MAE, Precision@10, Recall@10, NDCG@10, Catalog Coverage.
  5. In ra bảng so sánh kết quả trực quan.
  6. Lưu mô hình SVD (Surprise) tối ưu nhất làm mô hình production phục vụ API.

Sử dụng:
  python src/models/train_pipeline.py
"""

import os
import sys
from pathlib import Path
import pandas as pd

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.baseline import MeanRecommender, PopularityRecommender, SurpriseKNNRecommender
from src.models.svd_numpy import NumPyFunkSVD
from src.models.svd_surprise import SurpriseSVDRecommender
from src.models.evaluate import evaluate_model_pipeline
from src.pipeline.registry import write_metadata

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Siêu tham số SVD — lấy từ .env (fallback về giá trị mặc định đã tuning)
SVD_N_FACTORS = int(os.getenv("SVD_N_FACTORS", "50"))
SVD_LR_ALL = float(os.getenv("SVD_LR_ALL", "0.005"))
SVD_REG_ALL = float(os.getenv("SVD_REG_ALL", "0.05"))
SVD_N_EPOCHS = int(os.getenv("SVD_N_EPOCHS", "20"))


def main():
    print(f"{'='*60}")
    print("  MovieRS — Pipeline Huấn luyện & Đánh giá Mô hình")
    print(f"{'='*60}")
    
    # 1. Đọc dữ liệu
    train_path = PROCESSED_DIR / "ratings_train.csv"
    val_path = PROCESSED_DIR / "ratings_val.csv"
    test_path = PROCESSED_DIR / "ratings_test.csv"
    
    if not train_path.exists() or not test_path.exists():
        print("[✗] Không tìm thấy dữ liệu split trong data/processed/!")
        print("    Vui lòng chạy script split trước: python src/data/split.py")
        sys.exit(1)
        
    train_df = pd.read_csv(train_path)
    val_df = pd.read_csv(val_path) if val_path.exists() else None
    test_df = pd.read_csv(test_path)
    
    print(f"[✓] Đã tải dữ liệu:")
    print(f"    - Train size: {len(train_df):,}")
    print(f"    - Test size: {len(test_df):,}")
    
    results = {}
    
    # --------------------------------------------------------
    # Huấn luyện & Đánh giá các Baselines
    # --------------------------------------------------------
    # 1. Mean Recommender
    print(f"\n{'─'*50}")
    print("1. Huấn luyện Mean Recommender (Baseline)...")
    mean_model = MeanRecommender().fit(train_df)
    results["Mean Recommender"] = evaluate_model_pipeline(mean_model, train_df, test_df)
    
    # 2. Popularity Recommender
    print(f"\n{'─'*50}")
    print("2. Huấn luyện Popularity Recommender (Baseline)...")
    pop_model = PopularityRecommender().fit(train_df)
    results["Popularity Recommender"] = evaluate_model_pipeline(pop_model, train_df, test_df)
    
    # 3. KNN Recommender
    print(f"\n{'─'*50}")
    print("3. Huấn luyện KNN Recommender (Baseline)...")
    try:
        knn_model = SurpriseKNNRecommender(user_based=True, k=40).fit(train_df)
        results["KNN (User-based)"] = evaluate_model_pipeline(knn_model, train_df, test_df)
    except Exception as e:
        print(f"    [⚠] Không thể train KNN: {e}")
        
    # --------------------------------------------------------
    # Huấn luyện & Đánh giá mô hình Matrix Factorization
    # --------------------------------------------------------
    # 4. NumPy FunkSVD (Tự viết)
    print(f"\n{'─'*50}")
    print("4. Huấn luyện FunkSVD (NumPy tự viết)...")
    numpy_svd = NumPyFunkSVD(n_factors=30, lr=0.005, reg=0.05, n_epochs=15)
    numpy_svd.fit(train_df, val_df)
    results["FunkSVD (NumPy - Custom)"] = evaluate_model_pipeline(numpy_svd, train_df, test_df)
    
    # 5. Surprise SVD (Thư viện)
    print(f"\n{'─'*50}")
    print("5. Huấn luyện SVD (Surprise)...")
    surprise_svd = SurpriseSVDRecommender(
        n_factors=SVD_N_FACTORS,
        lr_all=SVD_LR_ALL,
        reg_all=SVD_REG_ALL,
        n_epochs=SVD_N_EPOCHS,
    )
    surprise_svd.fit(train_df)
    results["SVD (Surprise)"] = evaluate_model_pipeline(surprise_svd, train_df, test_df)
    
    # --------------------------------------------------------
    # Hiển thị bảng so sánh kết quả
    # --------------------------------------------------------
    print(f"\n{'='*70}")
    print("               BẢNG SO SÁNH KẾT QUẢ ĐÁNH GIÁ OFFLINE")
    print(f"{'='*70}")
    
    metrics_to_show = ["RMSE", "MAE", "Precision@10", "Recall@10", "NDCG@10", "Catalog_Coverage"]
    
    # Tạo bảng
    rows = []
    for model_name, metrics in results.items():
        row = {"Model": model_name}
        for m in metrics_to_show:
            val = metrics.get(m, 0.0)
            if m == "Catalog_Coverage":
                row[m] = f"{val*100:.2f}%"
            else:
                row[m] = f"{val:.4f}"
        rows.append(row)
        
    results_df = pd.DataFrame(rows)
    print(results_df.to_string(index=False))
    
    # Hiển thị phân tích theo nhóm User Sparsity
    print(f"\n{'─'*50}")
    print("Phân tích lỗi RMSE theo nhóm người dùng (Sparsity Analysis):")
    print(f"{'─'*50}")
    for model_name, metrics in results.items():
        if "Group_RMSE" in metrics:
            print(f" * {model_name}:")
            for group, rmse in metrics["Group_RMSE"].items():
                print(f"    - {group:30s}: RMSE = {rmse:.4f}")
                
    # 6. Lưu mô hình tốt nhất phục vụ API (SVD Surprise)
    print(f"\n{'─'*50}")
    model_output_path = MODEL_DIR / "model_latest.pkl"
    surprise_svd.save(model_output_path)
    svd_metrics = results.get("SVD (Surprise)", {})
    write_metadata(
        version_file=model_output_path,
        metrics=svd_metrics,
        params={
            "n_factors": SVD_N_FACTORS,
            "lr_all": SVD_LR_ALL,
            "reg_all": SVD_REG_ALL,
            "n_epochs": SVD_N_EPOCHS,
        },
        promoted=True,
        train_rows=int(len(train_df)),
        save_path=MODEL_DIR / "model_latest.json",
    )
    print(f"[✓] Đã deploy mô hình thành công lên production!")
    print("    Bước tiếp theo: Xây dựng FastAPI server phục vụ mô hình.")


if __name__ == "__main__":
    main()
