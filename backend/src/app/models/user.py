"""用户与角色模型 — JWT 认证 + RBAC 权限管理"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    """用户角色枚举"""
    ADMIN = "admin"               # 管理员：全部权限
    HR = "hr"                     # HR：候选人/问卷/面试管理
    INTERVIEWER = "interviewer"   # 面试官：提交面试反馈
    CANDIDATE = "candidate"       # 候选人：查看自己信息


class User(Base):
    """用户ORM模型，对应数据库 users 表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)  # 登录用户名
    hashed_password = Column(String(255), nullable=False)                    # bcrypt 哈希后的密码
    role = Column(String(20), default=UserRole.HR.value, nullable=False)     # 角色
    email = Column(String(200), nullable=True)                               # 邮箱
    display_name = Column(String(100), nullable=True)                        # 显示姓名（空则展示端回退 username）
    is_active = Column(Boolean, default=True)                                # 是否启用

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
