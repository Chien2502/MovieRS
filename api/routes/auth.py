"""
auth.py — Endpoints đăng ký / đăng nhập người dùng

Prototype: xác thực bằng username + mật khẩu, trả về user_id để app lưu local.
Không dùng token phiên (giữ gọn cho prototype).
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.logging_config import get_logger
from api.services.user_store import register_user, authenticate

logger = get_logger(__name__)

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Tên đăng nhập")
    password: str = Field(..., min_length=4, max_length=100, description="Mật khẩu")
    genres: list[str] = Field(default_factory=list, description="Thể loại phim yêu thích (Cold-Start)")


class LoginRequest(BaseModel):
    username: str = Field(..., description="Tên đăng nhập")
    password: str = Field(..., description="Mật khẩu")


@router.post("/auth/register", status_code=201)
async def register(req: RegisterRequest):
    """Đăng ký tài khoản mới; trả về user_id dùng cho mọi API call sau đó."""
    try:
        user = register_user(req.username, req.password, req.genres)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.info(f"Đăng ký thành công: {user['username']} (user_id={user['user_id']})")
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "genres": user["genres"],
    }


@router.post("/auth/login")
async def login(req: LoginRequest):
    """Đăng nhập; trả về user_id nếu tên đăng nhập + mật khẩu đúng."""
    user = authenticate(req.username, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")
    logger.info(f"Đăng nhập thành công: {user['username']} (user_id={user['user_id']})")
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "genres": user["genres"],
    }
