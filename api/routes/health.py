"""
health.py — Endpoint kiểm tra trạng thái hoạt động của hệ thống
"""

import time
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()
START_TIME = time.time()


@router.get("/health")
async def health_check():
    """Kiểm tra sức khỏe của API và trạng thái tải mô hình."""
    # Kiểm tra xem file model đã tồn tại chưa
    model_path = Path("models/model_latest.pkl")
    model_status = "Not Found"
    
    if model_path.exists():
        model_status = "Available"
        
    uptime = time.time() - START_TIME
    
    return {
        "status": "healthy",
        "uptime_seconds": int(uptime),
        "model_status": model_status,
        "api_version": "1.0.0"
    }
