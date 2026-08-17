"""
retrain.py — Retraining Pipeline (MLOps Automation)

Mục đích:
  1. Tự động gộp dữ liệu ratings mới (interactions_log.csv) vào dữ liệu và tái chia split.
  2. Huấn luyện lại mô hình SVD (Surprise) bằng siêu tham số lấy từ môi trường (.env).
  3. Model Gate: chỉ promote lên model_latest.pkl nếu RMSE trên val set không tệ hơn bản hiện tại.
  4. Quản lý phiên bản mô hình (Model Versioning): Lưu thành model_v{timestamp}.pkl + metadata JSON.
  5. Gọi API reload `/recommendations/reload` của FastAPI để nạp mô hình mới trực tuyến (Zero-downtime).

Sử dụng:
  python src/pipeline/retrain.py
"""

import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
import requests

# Thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models.svd_surprise import SurpriseSVDRecommender
from src.data.merge_interactions import merge_and_split
from src.pipeline.registry import (
    write_metadata,
    read_metadata,
    latest_metadata_path,
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Siêu tham số SVD — lấy từ .env (fallback về giá trị mặc định đã tuning)
SVD_N_FACTORS = int(os.getenv("SVD_N_FACTORS", "50"))
SVD_LR_ALL = float(os.getenv("SVD_LR_ALL", "0.005"))
SVD_REG_ALL = float(os.getenv("SVD_REG_ALL", "0.05"))
SVD_N_EPOCHS = int(os.getenv("SVD_N_EPOCHS", "20"))

# Sai số cho phép khi so sánh RMSE với bản hiện tại (0.0 = chỉ promote khi không tệ hơn)
GATE_TOLERANCE = float(os.getenv("GATE_TOLERANCE", "0.0"))

# Lấy cấu hình từ biến môi trường
API_HOST = os.getenv("API_HOST", "localhost")
API_PORT = int(os.getenv("API_PORT", 8000))
RELOAD_URL = f"http://{API_HOST}:{API_PORT}/api/recommendations/reload"


def _evaluate_on_val(model) -> dict:
    """Đánh giá RMSE/MAE của model trên tập val."""
    val_path = PROCESSED_DIR / "ratings_val.csv"
    if not val_path.exists():
        return {}
    val_df = pd.read_csv(val_path)
    return model.evaluate_test(val_df)


def run_retrain() -> dict:
    """Chạy toàn bộ quy trình retrain (gộp feedback → train → Model Gate → promote → reload).

    Có thể gọi từ CLI (python src/pipeline/retrain.py) hoặc từ Auto-Retrain
    thread bên trong FastAPI (api/main.py) khi có đủ tương tác mới.

    Trả về dict kết quả: {success, promoted, new_rmse, train_rows, duration_s, version}
    """
    result = {"success": False, "promoted": False, "new_rmse": None,
              "train_rows": 0, "duration_s": 0.0, "version": None}

    # 0. Gộp feedback log + tái chia split (đảm bảo dữ liệu mới nhất và sạch)
    print("[🔁] Bước 0: Gộp interactions_log vào dữ liệu huấn luyện...")
    try:
        merge_and_split()
    except FileNotFoundError as e:
        print(f"[✗] {e}")
        return result

    train_path = PROCESSED_DIR / "ratings_train.csv"
    if not train_path.exists():
        print(f"[✗] Không tìm thấy dữ liệu: {train_path}")
        return result

    # 1. Tải dữ liệu mới nhất
    print("[📥] Đang tải dữ liệu huấn luyện mới nhất...")
    train_df = pd.read_csv(train_path)
    print(f"    ✓ Tổng số rating hiện tại: {len(train_df):,}")

    # 2. Huấn luyện lại mô hình SVD
    print("[🧠] Đang tái huấn luyện mô hình SVD...")
    start_time = time.time()

    print(f"    Hyperparameters: n_factors={SVD_N_FACTORS}, lr_all={SVD_LR_ALL}, "
          f"reg_all={SVD_REG_ALL}, n_epochs={SVD_N_EPOCHS}")
    new_model = SurpriseSVDRecommender(
        n_factors=SVD_N_FACTORS,
        lr_all=SVD_LR_ALL,
        reg_all=SVD_REG_ALL,
        n_epochs=SVD_N_EPOCHS,
    )
    new_model.fit(train_df)

    duration = time.time() - start_time
    print(f"    ✓ Huấn luyện xong trong {duration:.2f} giây.")
    result["duration_s"] = round(duration, 2)
    result["train_rows"] = int(len(train_df))

    # 3. Model Gate: đánh giá trên val set và so sánh với model đang deploy
    new_metrics = _evaluate_on_val(new_model)
    if new_metrics:
        print(f"    ✓ Đánh giá trên VAL: RMSE={new_metrics['RMSE']:.4f}, MAE={new_metrics['MAE']:.4f}")
    else:
        print("    [⚠] Không tìm thấy ratings_val.csv — bỏ qua Model Gate, sẽ promote trực tiếp.")

    old_meta = read_metadata(latest_metadata_path())
    old_rmse = (old_meta or {}).get("metrics", {}).get("RMSE")
    promoted = True
    if new_metrics and old_rmse is not None:
        promoted = new_metrics["RMSE"] <= old_rmse + GATE_TOLERANCE
        print(f"    So sánh RMSE: mới={new_metrics['RMSE']:.4f} vs hiện tại={old_rmse:.4f} "
              f"(tolerance={GATE_TOLERANCE})")
        if promoted:
            print("    [✓] Model mới tốt hơn/ngang bản hiện tại → Sẽ promote.")
        else:
            print("    [✗] Model mới KHÔNG tốt hơn bản hiện tại → Giữ nguyên model_latest.pkl!")

    # 4. Model Versioning (Quản lý phiên bản)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    versioned_filename = f"model_v_{timestamp}.pkl"
    versioned_path = MODEL_DIR / versioned_filename
    latest_path = MODEL_DIR / "model_latest.pkl"

    new_model.save(versioned_path)

    metrics_for_meta = {**new_metrics,
                        **({"val_rmse": new_metrics["RMSE"]} if new_metrics else {})}
    params_for_meta = {
        "n_factors": SVD_N_FACTORS,
        "lr_all": SVD_LR_ALL,
        "reg_all": SVD_REG_ALL,
        "n_epochs": SVD_N_EPOCHS,
    }
    write_metadata(
        version_file=versioned_path,
        metrics=metrics_for_meta,
        params=params_for_meta,
        promoted=promoted,
        prev_version=(old_meta or {}).get("version"),
        train_rows=int(len(train_df)),
    )
    print(f"[✓] Đã tạo phiên bản: {versioned_filename}")
    result["version"] = versioned_filename

    # 5. Promote nếu vượt qua Model Gate
    if promoted:
        shutil.copy(str(versioned_path), str(latest_path))
        write_metadata(
            version_file=versioned_path,
            metrics=metrics_for_meta,
            params=params_for_meta,
            promoted=True,
            prev_version=(old_meta or {}).get("version"),
            train_rows=int(len(train_df)),
            save_path=latest_metadata_path(),
        )
        print(f"[✓] Đã cập nhật: {latest_path}")
        result["promoted"] = True

        # 6. Trigger reload mô hình trực tuyến trên FastAPI server
        print("[🌐] Đang gửi yêu cầu nạp lại mô hình tới FastAPI...")
        try:
            response = requests.post(RELOAD_URL, timeout=60)
            if response.status_code == 200:
                print("[✓] FastAPI đã nạp lại mô hình mới thành công (Zero-downtime)!")
            else:
                print(f"[⚠] FastAPI trả về mã lỗi: {response.status_code}. Nội dung: {response.text}")
        except requests.exceptions.ConnectionError:
            print("[⚠] Không thể kết nối tới FastAPI server. Hãy đảm bảo API đang chạy.")
            print("    Mẹo: Chạy 'python api/main.py' rồi thử lại script này.")
        except Exception as e:
            print(f"[⚠] Có lỗi xảy ra khi trigger reload: {e}")
    else:
        print(f"[⛔] KHÔNG promote: giữ nguyên {latest_path.name}. "
              f"Model mới lưu tại {versioned_filename} (có thể rollback thủ công).")

    result["new_rmse"] = new_metrics.get("RMSE") if new_metrics else None
    result["success"] = True
    return result


def main():
    print(f"{'='*60}")
    print("  MovieRS — Pipeline Tái Huấn luyện Mô hình (Retrain Pipeline)")
    print(f"{'='*60}")
    result = run_retrain()
    print(f"\n{'='*60}")
    print("  Hoàn tất quy trình Retrain Pipeline!")
    print(f"  Kết quả: {result}")
    print(f"{'='*60}")
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
