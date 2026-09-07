# ═══════════════════════════════════════════════════════════════
# 【小白导读】候选人管理：增删改查 + 导出 Excel。
#   · 列表查询会用 dependencies/scope.py 做数据权限过滤（HR 只看到自己的候选人）。
#   · 候选人状态的其他变更入口在工作流/面试/问卷模块，这里只是手工管理入口。
# ═══════════════════════════════════════════════════════════════
"""候选人管理API — CRUD操作"""
import logging
from datetime import datetime
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Candidate, User
from app.models import UserRole
from app.dependencies import (
    require_role, get_current_user, ensure_candidate_visible, candidate_scope_cond,
)
from app.schemas import (
    CandidateCreate, CandidateUpdate, CandidateResponse, CandidateListResponse,
    CandidateOwnerUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/candidates",
    tags=["候选人管理"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


@router.post("", response_model=CandidateResponse)
async def create_candidate(
    data: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新候选人记录

    归属规则：HR 建档归属自己（忽略 body.owner_user_id）；admin 可用
    ``data.owner_user_id`` 指派给某 HR/admin，缺省归属自己。
    """
    # 归属校验：admin 指定目标负责人时必须存在且启用、为 HR/admin 角色
    owner_user_id = current_user.id
    if (
        current_user.role == UserRole.ADMIN.value
        and data.owner_user_id is not None
    ):
        target = (await db.execute(
            select(User).where(User.id == data.owner_user_id)
        )).scalar_one_or_none()
        if (
            not target or not target.is_active
            or target.role not in (UserRole.ADMIN.value, UserRole.HR.value)
        ):
            raise HTTPException(status_code=400, detail="指定的负责人不存在或不是 HR/admin")
        owner_user_id = target.id

    candidate = Candidate(**data.model_dump(exclude={"owner_user_id"}))
    candidate.owner_user_id = owner_user_id
    db.add(candidate)
    await db.flush()
    await db.refresh(candidate)  # 刷新获取自增ID
    logger.info(
        "创建候选人: id=%s name=%s position=%s owner_user_id=%s",
        candidate.id, candidate.name, candidate.position, owner_user_id,
    )
    return candidate


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    page: int = Query(1, ge=1),               # 页码，默认第1页
    page_size: int = Query(20, ge=1, le=100), # 每页条数，默认20
    status: Optional[str] = None,             # 按状态筛选
    position: Optional[str] = None,           # 按岗位筛选
    search: Optional[str] = None,             # 按姓名/邮箱搜索
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取候选人列表（支持分页、过滤、搜索）

    HR 仅能看到自己负责的候选人；admin 全量。
    """
    # 构建查询
    query = select(Candidate)
    count_query = select(func.count(Candidate.id))

    # 数据范围：HR 只看自己名下；admin 不过滤
    cond = candidate_scope_cond(current_user)
    if cond is not None:
        query = query.where(cond)
        count_query = count_query.where(cond)

    # 按状态过滤
    if status:
        query = query.where(Candidate.status == status)
        count_query = count_query.where(Candidate.status == status)
    # 按岗位模糊搜索
    if position:
        query = query.where(Candidate.position.ilike(f"%{position}%"))
        count_query = count_query.where(Candidate.position.ilike(f"%{position}%"))
    # 按姓名或邮箱全局搜索
    if search:
        query = query.where(
            Candidate.name.ilike(f"%{search}%") |
            Candidate.email.ilike(f"%{search}%")
        )
        count_query = count_query.where(
            Candidate.name.ilike(f"%{search}%") |
            Candidate.email.ilike(f"%{search}%")
        )

    # 执行查询
    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Candidate.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    candidates = result.scalars().all()

    return CandidateListResponse(
        total=total,
        items=[CandidateResponse.model_validate(c) for c in candidates],
        page=page,
        page_size=page_size,
    )


@router.get("/export")
async def export_candidates_xlsx(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出候选人 Excel（姓名 / 岗位 / 联系方式 / 负责 HR）

    - 范围：当前账号可见的候选人（HR 仅自己名下；admin 全量），与列表接口同隔离。
    - 联系方式：优先手机号，缺省回退邮箱。
    - 负责 HR：候选人归属负责人（candidates.owner_user_id → users.username）。
    - 路由须先于 /{candidate_id} 注册，避免 "export" 被路径参数吞掉。
    """
    # 负责 HR 列：姓名优先（display_name），空则回退登录名
    owner_name_col = func.coalesce(
        func.nullif(User.display_name, ""), User.username
    ).label("owner_name")
    stmt = (
        select(Candidate, owner_name_col)
        .outerjoin(User, Candidate.owner_user_id == User.id)
    )
    cond = candidate_scope_cond(current_user)
    if cond is not None:
        stmt = stmt.where(cond)
    stmt = stmt.order_by(Candidate.created_at.desc())
    rows = (await db.execute(stmt)).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "候选人"
    headers = ["姓名", "岗位", "联系方式", "负责 HR"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for cand, owner_name in rows:
        contact = (cand.phone or "").strip() or (cand.email or "").strip()
        ws.append([cand.name, cand.position, contact, owner_name or ""])

    for idx, width in enumerate([14, 40, 32, 20], start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    buf = BytesIO()
    wb.save(buf)
    filename = f"候选人名单_{datetime.now():%Y%m%d}.xlsx"
    logger.info("导出候选人 Excel: 行数=%d user=%s", len(rows), current_user.username)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个候选人详情（越权一律 404）"""
    return await ensure_candidate_visible(db, current_user, candidate_id)


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: int,
    data: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新候选人信息（部分更新）—— 仅限本人名下（admin 全量）"""
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    # 只更新请求中包含的字段
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)

    await db.flush()
    await db.refresh(candidate)
    logger.info("更新候选人: id=%s 字段=%s", candidate_id, list(data.model_dump(exclude_unset=True).keys()))
    return candidate


@router.put("/{candidate_id}/owner")
async def reassign_candidate_owner(
    candidate_id: int,
    data: CandidateOwnerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """改派候选人负责人（仅 admin）。

    改派后数据即时对原 HR 不可见（所有读路径动态按 owner 过滤，无缓存副本）。
    """
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    target = (await db.execute(
        select(User).where(User.id == data.owner_user_id)
    )).scalar_one_or_none()
    if (
        not target or not target.is_active
        or target.role not in (UserRole.ADMIN.value, UserRole.HR.value)
    ):
        raise HTTPException(status_code=400, detail="目标负责人不存在或不是 HR/admin")

    previous_owner_id = candidate.owner_user_id
    previous_owner_name = None
    if previous_owner_id:
        prev = (await db.execute(
            select(User).where(User.id == previous_owner_id)
        )).scalar_one_or_none()
        previous_owner_name = (prev.display_name or prev.username) if prev else None

    candidate.owner_user_id = target.id
    await db.flush()
    await db.refresh(candidate)
    logger.info(
        "改派候选人负责人: candidate_id=%s %s -> %s",
        candidate_id, previous_owner_name, target.username,
    )
    return {
        "candidate_id": candidate.id,
        "previous_owner_user_id": previous_owner_id,
        "previous_owner_name": previous_owner_name,
        "owner_user_id": candidate.owner_user_id,
        "owner_name": target.display_name or target.username,
    }


@router.delete("/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除候选人及其所有关联记录"""
    from app.models import (
        Resume, Questionnaire, QuestionnaireResponse, Interview, Notification,
        TalentPool, TaskProgress,
    )

    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    # 显式按外键依赖顺序清理（每条 delete/update 立即执行），最后删候选人本身。
    # 之前依赖 SQLAlchemy ORM 一次性 flush 会自动排序，但缺少 relationship 时可能与
    # MySQL 外键顺序不一致 → 删除候选人先于其子表被 MySQL 拒绝（1451）。
    # 1. 任务进度（auto-process 流水；candidate_id NOT NULL 引用 candidates）
    await db.execute(
        delete(TaskProgress).where(TaskProgress.candidate_id == candidate_id)
    )
    # 2. 面试记录（candidate_id NOT NULL 引用 candidates）——此前“面试候选人删不掉”的元凶
    await db.execute(
        delete(Interview).where(Interview.candidate_id == candidate_id)
    )
    # 3. 简历
    await db.execute(
        delete(Resume).where(Resume.candidate_id == candidate_id)
    )
    # 4. 问卷回复 + 问卷
    await db.execute(
        delete(QuestionnaireResponse).where(QuestionnaireResponse.candidate_id == candidate_id)
    )
    await db.execute(
        delete(Questionnaire).where(Questionnaire.candidate_id == candidate_id)
    )
    # 5. 通知记录：解除外键（candidate_id 可空 → 置 NULL 保留历史发送记录）
    await db.execute(
        update(Notification)
        .where(Notification.candidate_id == candidate_id)
        .values(candidate_id=None)
    )
    # 6. 人才池记录
    pools = (await db.execute(
        select(TalentPool).where(TalentPool.candidate_id == candidate_id)
    )).scalars().all()
    for p in pools:
        await db.delete(p)
    # 7. 候选人本身
    await db.delete(candidate)
    await db.flush()
    logger.info(
        "删除候选人: id=%s name=%s (显式级联清理任务进度/问卷/面试/简历/人才池)",
        candidate_id, candidate.name,
    )
    return {"status": "deleted"}
