"""
recommendations.py — Endpoint chính cung cấp các gợi ý phim cá nhân hóa cho từng user
"""

import time
from fastapi import APIRouter, Query, HTTPException
from api.services.recommender import RecommenderService

router = APIRouter()
recommender_service = RecommenderService()


@router.get("/recommendations/{user_id}")
async def get_recommendations(
    user_id: int,
    limit: int = Query(10, ge=1, le=50, description="Số lượng phim cần gợi ý")
):
    """Lấy danh sách các bộ phim gợi ý cá nhân hóa cho user.
    
    Quy trình xử lý:
      1. Đọc và kiểm tra in-memory cache kết quả.
      2. Nếu là User mới (Cold-Start): Chuyển sang giải pháp Popularity Recommender.
      3. Nếu là User cũ (Warm/Heavy): Sử dụng mô hình SVD dự đoán rating của user với các phim chưa xem.
      4. Đính kèm thông tin metadata từ TMDb (poster, thể loại, tóm tắt) và trả về.
    """
    start_time = time.time()
    
    try:
        recommendations = recommender_service.get_recommendations(user_id, limit=limit)
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Thêm metadata về lượt gợi ý phục vụ đo lường hiệu năng
        return {
            "user_id": user_id,
            "count": len(recommendations),
            "latency_ms": round(latency_ms, 2),
            "recommendations": recommendations
        }
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=500, detail=str(fnf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống khi tạo gợi ý: {str(e)}")


@router.post("/recommendations/reload")
async def reload_recommender_model():
    """Endpoint yêu cầu nạp lại mô hình từ đĩa (dành cho Retraining Pipeline)."""
    try:
        recommender_service.reload_model()
        return {"status": "success", "message": "Model reloaded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi nạp lại mô hình: {str(e)}")
