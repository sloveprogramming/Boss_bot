# 【小白导读】schemas = Pydantic 模型，负责 API 的"进出门安检"：
#   请求进来先按这里的类校验字段（类型不对直接返回 422），响应出去也按它序列化。
#   和 models 的区别：models 描述数据库表长什么样，schemas 描述接口的请求/响应长什么样。
# 本文件：注册/登录/改密码等接口的请求体定义。

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
    display_name: Optional[str] = None  # 显示姓名（可选）


class SetupAdminRequest(BaseModel):
    """系统初始化 — 创建首个管理员"""
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=128, description="管理员密码（至少6位）")
    email: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    """更新当前用户资料请求（仅 display_name；空串=清除，回退登录名）"""
    display_name: Optional[str] = Field(None, max_length=100, description="显示姓名")


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
    display_name: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
