"""
main.py — FastAPI Application Entrypoint

Chịu trách nhiệm khởi tạo ứng dụng, đăng ký các router, thiết lập middleware
API không chạy huấn luyện nền; worker vận hành có entrypoint riêng.
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Thêm thư mục gốc vào path để import src
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Tải biến môi trường
load_dotenv(PROJECT_ROOT / ".env")

from api.logging_config import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(application):
    """API chỉ phục vụ; huấn luyện do worker CLI riêng đảm nhiệm."""
    logger.info('MovieRS API V2; retrain chạy bằng worker riêng')
    try:yield
    finally:
        from api.database import close_database_pool
        close_database_pool()

# Khởi tạo FastAPI
app = FastAPI(
    title="MovieRS API",
    description="Hệ khuyến nghị phim kết hợp SVD, thể loại và độ phổ biến; trình phát mô phỏng",
    lifespan=lifespan,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

from api.security import authorize_request
from api.database import DatabaseError
app.middleware('http')(authorize_request)


@app.exception_handler(DatabaseError)
async def database_error_handler(request,error):
    return JSONResponse(status_code=503,content={'detail':'Kho dữ liệu tạm thời không khả dụng'})

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


@app.get("/")
async def root():
    return {
        "message": "Chào mừng bạn đến với MovieRS Recommendation API!",
        "docs": "/docs",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    
    print(f"Starting MovieRS API at http://{host}:{port}")
    # API_RELOAD=0 để tắt auto-reload khi chạy demo ổn định (production-like)
    uvicorn.run("api.main:app", host=host, port=port, reload=os.getenv("API_RELOAD", "1") == "1")
