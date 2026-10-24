"""
health.py — Endpoint kiểm tra trạng thái hoạt động của hệ thống
"""

import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()
START_TIME = time.time()


@router.get('/health/database')
def database_health_check():
    """Kiểm tra kết nối SQL riêng; để trống DATABASE_URL vẫn chạy demo local."""
    from api.database import database_status
    status = database_status()
    return JSONResponse(status_code=503 if status['status'] == 'unavailable' else 200, content=status)


@router.get("/health")
def health_check():
    """Kiểm tra sức khỏe của API và trạng thái tải mô hình."""
    from api.services.recommender import RecommenderService
    service = RecommenderService()
    try:
        service.initialize()
        ready=service.model is not None or service.ranking_model is not None
        model_status = 'Loaded' if ready else 'Fallback'
        status = 'healthy' if ready else 'degraded'
        catalog_size = len(service.all_movie_ids)
    except Exception:
        model_status, status, catalog_size = 'Unavailable', 'unavailable', 0
        
    uptime = time.time() - START_TIME
    
    return {
        "status": status,
        "uptime_seconds": int(uptime),
        "model_status": model_status,
        "api_version": "2.0.0",
        "catalog_size": catalog_size,
        'player_mode': 'simulation',
        'serving_model':getattr(service,'serving_name',None),
        'serving_version':getattr(service,'serving_version',None),
        'training_mode':'external_worker_manual',
        'recommendation_cache':{'entries':len(getattr(service,'recommendations_cache',{})),
                                'ttl_seconds':getattr(service,'cache_expiry_seconds',300)},
    }
