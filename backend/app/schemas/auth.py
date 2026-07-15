"""认证相关 Pydantic Schema"""
from pydantic import BaseModel, Field
from typing import Optional
from app.models.user import UserRole


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=2, max_length=100, description="用户名")
    password: str = Field(..., min_length=4, max_length=128, description="密码")


class TokenResponse(BaseModel):
    """登录成功返回"""
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserCreate(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=4, max_length=128)
    role: UserRole = UserRole.HR
    email: Optional[str] = None


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    role: str
    email: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True
