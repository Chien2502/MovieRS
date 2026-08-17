"""
main.py — FastAPI Application Entrypoint

Chịu trách nhiệm khởi tạo ứng dụng, đăng ký các router, thiết lập middleware
và khởi động Auto-Retrain thread (retrain định kỳ khi có đủ tương tác mới).
"""

import os
import sys
import csv
import threading
import time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Thêm thư mục gốc vào path để import src
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tải biến môi trường
load_dotenv(PROJECT_ROOT / ".env")

from api.logging_config import get_logger

logger = get_logger(__name__)

# Khởi tạo FastAPI
app = FastAPI(
    title="MovieRS API",
    description="Hệ thống Khuyến nghị Phim theo chuẩn MLOps cho dự án thực tập FPT Software",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Cấu hình CORS cho phép ứng dụng Flutter/Web gọi API
# CORS_ORIGINS: danh sách origin phân tách bằng dấu phẩy (mặc định '*' — chấp nhận mọi nguồn)
cors_origins = os.getenv("CORS_ORIGINS", "*")
allow_credentials = cors_origins != "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins.split(",")],
    allow_credentials=allow_credentials,  # '*' + credentials bị trình duyệt từ chối
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router
from api.routes import health, movies, recommendations, interactions, auth, users, watch

app.include_router(health.router, prefix="/api", tags=["System Status"])
app.include_router(auth.router, prefix="/api", tags=["Authentication"])
app.include_router(users.router, prefix="/api", tags=["User Data"])
app.include_router(movies.router, prefix="/api", tags=["Movies Catalog"])
app.include_router(interactions.router, prefix="/api", tags=["User Interactions"])
app.include_router(recommendations.router, prefix="/api", tags=["Recommendation Engine"])
app.include_router(watch.router, prefix="/api", tags=["Watch Progress"])


INTERACTIONS_LOG_CSV = PROJECT_ROOT / "data" / "processed" / "interactions_log.csv"

# Cấu hình Auto-Retrain (đọc từ .env):
#   AUTO_RETRAIN=1              — bật/tắt thread tự retrain (mặc định bật)
#   AUTO_RETRAIN_MIN_ROWS=5     — số interaction MỚI tối thiểu để kích hoạt retrain
#   AUTO_RETRAIN_MAX_IDLE=3600  — nếu chưa đủ MIN_ROWS nhưng đã có rows mới chờ
#                                 quá lâu này (giây) thì vẫn retrain
#   AUTO_RETRAIN_MIN_INTERVAL=300 — khoảng cách tối thiểu giữa 2 lần retrain (giây)
AUTO_RETRAIN = os.getenv("AUTO_RETRAIN", "1") == "1"
AUTO_RETRAIN_MIN_ROWS = int(os.getenv("AUTO_RETRAIN_MIN_ROWS", "5"))
AUTO_RETRAIN_MAX_IDLE = int(os.getenv("AUTO_RETRAIN_MAX_IDLE", "3600"))
AUTO_RETRAIN_MIN_INTERVAL = int(os.getenv("AUTO_RETRAIN_MIN_INTERVAL", "300"))
POLL_INTERVAL = 30  # chu kỳ kiểm tra log (giây)


def _count_interaction_rows() -> int:
    """Đếm số dòng trong interactions_log.csv (0 nếu chưa tồn tại)."""
    if not INTERACTIONS_LOG_CSV.exists():
        return 0
    try:
        with open(INTERACTIONS_LOG_CSV, encoding="utf-8") as f:
            return sum(1 for _ in csv.reader(f)) - 1  # trừ dòng header
    except Exception as e:
        logger.warning(f"[Auto-Retrain] Không đọc được interactions_log: {e}")
        return 0


def _auto_retrain_loop():
    """Vòng lặp nền: theo dõi interactions_log và tự retrain khi đủ điều kiện.

    Điều kiện kích hoạt:
      1. Có >= AUTO_RETRAIN_MIN_ROWS interaction mới kể từ lần retrain trước.
      2. Có interaction mới (dù chưa đủ MIN_ROWS) nhưng đã chờ hơn MAX_IDLE giây.
    Luôn tôn trọng khoảng cách tối thiểu MIN_INTERVAL giữa 2 lần retrain.
    """
    logger.info("[Auto-Retrain] Thread khởi động (poll mỗi %ds)", POLL_INTERVAL)
    rows_at_last_retrain = _count_interaction_rows()
    first_seen_new = None  # thời điểm phát hiện rows mới đầu tiên
    last_retrain_at = 0.0

    while True:
        time.sleep(POLL_INTERVAL)
        current_rows = _count_interaction_rows()
        new_rows = current_rows - rows_at_last_retrain

        if new_rows <= 0:
            first_seen_new = None
            continue

        # Điều kiện 1: đủ MIN_ROWS mới (và đã qua MIN_INTERVAL kể từ lần trước)
        enough_rows = new_rows >= AUTO_RETRAIN_MIN_ROWS
        # Điều kiện 2: có rows mới nhưng chờ quá MAX_IDLE giây
        idle_too_long = False
        if first_seen_new is None:
            first_seen_new = time.time()
        if time.time() - first_seen_new > AUTO_RETRAIN_MAX_IDLE:
            idle_too_long = True

        within_interval = time.time() - last_retrain_at < AUTO_RETRAIN_MIN_INTERVAL

        if not (enough_rows or idle_too_long) or within_interval:
            continue

        # Chờ mọi tương tác đang ghi xong rồi mới gộp (tránh đọc file nửa chừng)
        time.sleep(5)
        logger.info(
            f"[Auto-Retrain] Có {new_rows} interaction mới → bắt đầu retrain "
            f"(MIN_ROWS={AUTO_RETRAIN_MIN_ROWS}, MAX_IDLE={AUTO_RETRAIN_MAX_IDLE}s)"
        )
        try:
            from src.pipeline.retrain import run_retrain
            result = run_retrain()
            logger.info(
                f"[Auto-Retrain] Kết thúc: success={result['success']}, "
                f"promoted={result['promoted']}, RMSE={result['new_rmse']}, "
                f"train_rows={result['train_rows']}, mất {result['duration_s']}s"
            )
            rows_at_last_retrain = _count_interaction_rows()
            last_retrain_at = time.time()
            first_seen_new = None
        except Exception as e:
            logger.exception(f"[Auto-Retrain] Retrain thất bại: {e}")


def _start_auto_retrain():
    """Khởi động Auto-Retrain thread nếu được bật (.env AUTO_RETRAIN=1)."""
    if not AUTO_RETRAIN:
        logger.info("[Auto-Retrain] Đã tắt (AUTO_RETRAIN=0).")
        return
    thread = threading.Thread(target=_auto_retrain_loop, name="auto-retrain", daemon=True)
    thread.start()


@app.on_event("startup")
async def startup():
    _start_auto_retrain()


@app.get("/")
async def root():
    return {
        "message": "Chào mừng bạn đến với MovieRS Recommendation API!",
        "docs": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    
    print(f"Starting MovieRS API at http://{host}:{port}")
    # API_RELOAD=0 để tắt auto-reload khi chạy demo ổn định (production-like)
    uvicorn.run("api.main:app", host=host, port=port, reload=os.getenv("API_RELOAD", "1") == "1")
