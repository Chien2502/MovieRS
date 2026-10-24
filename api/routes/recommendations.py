"""
recommendations.py — Endpoint chính cung cấp các gợi ý phim cá nhân hóa cho từng user
"""

import time
from fastapi import APIRouter, Query, HTTPException
from api.services.recommender import RecommenderService

router = APIRouter()
recommender_service = RecommenderService()


@router.get("/recommendations/{user_id}")
def get_recommendations(
    user_id: int,
    limit: int = Query(10, ge=1, le=50, description="Số lượng phim cần gợi ý"),
    explore: bool = Query(False, description='Khám phá đa dạng với MMR')
):
    """Lấy danh sách các bộ phim gợi ý cá nhân hóa cho user.
    
    Quy trình xử lý:
      1. Đọc cache theo user và chế độ khám phá.
      2. SVD nếu đã có vector; Bayesian popularity nếu chưa có.
      3. Kết hợp sở thích thể loại, loại phim đã tương tác; MMR nếu bật explore.
      4. Đính kèm metadata, nguồn và lý do gợi ý.
    """
    start_time = time.time()
    
    try:
        result = recommender_service.get_recommendation_result(user_id, limit=limit, explore=explore)
        recommendations = result['recommendations']
        
        latency_ms = (time.time() - start_time) * 1000
        
        # Thêm metadata về lượt gợi ý phục vụ đo lường hiệu năng
        return {
            **result,
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
def reload_recommender_model():
    """Endpoint yêu cầu nạp lại mô hình từ đĩa (dành cho Retraining Pipeline)."""
    try:
        recommender_service.reload_model()
        from api.routes import movies
        movies.movies_df=None
        return {"status": "success", "message": "Model reloaded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi nạp lại mô hình: {str(e)}")
