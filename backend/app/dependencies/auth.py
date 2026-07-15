"""认证与权限依赖注入 — JWT 解析 + Role-Based Access Control

使用方式：
    # 在路由中获取当前用户
    @router.get("/candidates")
    async def list_candidates(current_user: User = Depends(get_current_user)):
        ...

    # 限制角色访问
    @router.post("/documents")
    async def create_document(_, current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR]))):
        ...
"""
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole

# ================================================================
# 密码工具
# ================================================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """密码哈希"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验密码"""
    return pwd_context.verify(plain_password, hashed_password)


# ================================================================
# JWT 工具
# ================================================================


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT access token

    Args:
        data: 要编码的数据（至少包含 "sub" 字段）
        expires_delta: 过期时间，默认使用配置的 JWT_EXPIRE_HOURS

    Returns:
        JWT token 字符串
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=settings.JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """从 JWT token 解析当前用户

    如果 token 不存在或无效，返回 None（不报错，方便公开路由使用）。
    受保护的路由应使用 require_role() 代替。
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    return user


def require_role(roles: List[UserRole]):
    """角色权限依赖：要求当前用户拥有指定角色之一

    Args:
        roles: 允许的角色列表

    Returns:
        与 Depends() 配合使用的依赖函数

    Raises:
        HTTPException 401/403: 未认证或权限不足

    Usage:
        @router.get("/api/documents")
        async def list_docs(current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR]))):
            ...
    """
    async def _role_checker(current_user: Optional[User] = Depends(get_current_user)) -> User:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="未认证，请先登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要角色: {[r.value for r in roles]}",
            )
        return current_user
    return _role_checker
