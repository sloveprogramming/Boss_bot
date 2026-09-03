"""认证相关 Pydantic Schema"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from app.models import UserRole


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
    """创建用户请求（自助注册）"""
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=4, max_length=128)
    role: UserRole = UserRole.HR
    email: Optional[str] = None


class SetupAdminRequest(BaseModel):
    """系统初始化 — 创建首个管理员"""
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=128, description="管理员密码（至少6位）")
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., min_length=4, max_length=128)
    new_password: str = Field(..., min_length=4, max_length=128)


class UserResponse(BaseModel):
    """用户信息响应"""
    id: int
    username: str
    role: str
    email: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
