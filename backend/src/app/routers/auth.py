"""认证 API — 注册 / 登录 / 当前用户 / 修改密码"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserRole
from app.schemas import (
    LoginRequest, TokenResponse, UserCreate, UserResponse,
    ChangePasswordRequest, SetupAdminRequest,
)
from app.dependencies import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_role,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role([UserRole.ADMIN])),
):
    """由管理员创建 HR 或面试官账号。

    首个管理员只能通过 ``/api/auth/setup`` 创建；后续账号必须由已认证的
    管理员创建，避免公开注册接口被滥用。
    """
    # 管理员只能在此创建 HR 和 INTERVIEWER 角色
    if data.role not in (UserRole.HR, UserRole.INTERVIEWER):
        raise HTTPException(
            status_code=400,
            detail="自助注册仅支持 HR 或 interviewer 角色",
        )

    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建用户
    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=data.role.value,
        email=data.email,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    logger.info("管理员创建账号: username=%s role=%s", user.username, user.role)
    return user


@router.post("/setup", status_code=201)
async def setup_admin(data: SetupAdminRequest, db: AsyncSession = Depends(get_db)):
    """初始化系统管理员（仅当系统中无任何管理员时可用）

    首次部署时调用此端点创建第一个管理员账号。
    已有管理员后此端点将被禁用。
    """
    # 检查是否已存在管理员
    admin_count = await db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.ADMIN.value)
    )
    if admin_count > 0:
        raise HTTPException(
            status_code=403,
            detail="系统已初始化，管理员已存在。请使用 /api/auth/login 登录。",
        )

    # 检查用户名是否已存在
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 创建管理员
    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        role=UserRole.ADMIN.value,
        email=data.email,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    logger.info("系统初始化: 首个管理员已创建 username=%s", user.username)
    return {
        "message": "管理员创建成功",
        "username": user.username,
        "role": user.role,
    }


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 JWT token"""
    # 查找用户
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning("登录失败: username=%s (密码错误或用户不存在)", data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    if not user.is_active:
        logger.warning("登录被拒: username=%s (账号已禁用)", data.username)
        raise HTTPException(status_code=403, detail="账号已被禁用")

    # 生成 token
    token = create_access_token(data={"sub": user.username, "role": user.role})
    logger.info("登录成功: username=%s role=%s", user.username, user.role)
    return TokenResponse(
        access_token=token,
        username=user.username,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    if not current_user:
        raise HTTPException(status_code=401, detail="未认证")
    return current_user


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(
        [UserRole.ADMIN, UserRole.HR, UserRole.INTERVIEWER]
    )),
):
    """修改当前用户的密码（需提供旧密码验证）"""
    # 验证旧密码
    if not verify_password(data.old_password, current_user.hashed_password):
        logger.warning("修改密码失败: username=%s (旧密码错误)", current_user.username)
        raise HTTPException(status_code=400, detail="旧密码不正确")

    # 更新密码
    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()

    logger.info("修改密码成功: username=%s", current_user.username)
    return {"message": "密码修改成功"}
