"""候选人管理API — CRUD操作"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Candidate
from app.models import UserRole
from app.dependencies import require_role
from app.schemas import (
    CandidateCreate, CandidateUpdate, CandidateResponse, CandidateListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/candidates",
    tags=["候选人管理"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


@router.post("", response_model=CandidateResponse)
async def create_candidate(data: CandidateCreate, db: AsyncSession = Depends(get_db)):
    """创建新候选人记录"""
    candidate = Candidate(**data.model_dump())  # 用请求数据创建模型实例
    db.add(candidate)
    await db.flush()
    await db.refresh(candidate)  # 刷新获取自增ID
    logger.info("创建候选人: id=%s name=%s position=%s", candidate.id, candidate.name, candidate.position)
    return candidate


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    page: int = Query(1, ge=1),               # 页码，默认第1页
    page_size: int = Query(20, ge=1, le=100), # 每页条数，默认20
    status: Optional[str] = None,             # 按状态筛选
    position: Optional[str] = None,           # 按岗位筛选
    search: Optional[str] = None,             # 按姓名/邮箱搜索
    db: AsyncSession = Depends(get_db),
):
    """获取候选人列表（支持分页、过滤、搜索）"""
    # 构建查询
    query = select(Candidate)
    count_query = select(func.count(Candidate.id))

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


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """获取单个候选人详情"""
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")
    return candidate


@router.put("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(
    candidate_id: int, data: CandidateUpdate, db: AsyncSession = Depends(get_db)
):
    """更新候选人信息（部分更新）"""
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

    # 只更新请求中包含的字段
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(candidate, key, value)

    await db.flush()
    await db.refresh(candidate)
    logger.info("更新候选人: id=%s 字段=%s", candidate_id, list(data.model_dump(exclude_unset=True).keys()))
    return candidate


@router.delete("/{candidate_id}")
async def delete_candidate(candidate_id: int, db: AsyncSession = Depends(get_db)):
    """删除候选人及其所有关联记录"""
    from app.models import Resume, Questionnaire, QuestionnaireResponse, Interview, Notification, TalentPool

    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

    # 按依赖顺序删除关联记录
    # 1. 问卷回复
    await db.execute(
        select(QuestionnaireResponse).where(QuestionnaireResponse.candidate_id == candidate_id)
    )
    responses = (await db.execute(
        select(QuestionnaireResponse).where(QuestionnaireResponse.candidate_id == candidate_id)
    )).scalars().all()
    for r in responses:
        await db.delete(r)

    # 2. 问卷
    qs = (await db.execute(
        select(Questionnaire).where(Questionnaire.candidate_id == candidate_id)
    )).scalars().all()
    for q in qs:
        await db.delete(q)

    # 3. 面试记录
    interviews = (await db.execute(
        select(Interview).where(Interview.candidate_id == candidate_id)
    )).scalars().all()
    for i in interviews:
        await db.delete(i)

    # 4. 简历
    resumes = (await db.execute(
        select(Resume).where(Resume.candidate_id == candidate_id)
    )).scalars().all()
    for r in resumes:
        await db.delete(r)

    # 5. 通知记录（解除关联）
    notifs = (await db.execute(
        select(Notification).where(Notification.candidate_id == candidate_id)
    )).scalars().all()
    for n in notifs:
        n.candidate_id = None

    # 6. 人才池记录
    pools = (await db.execute(
        select(TalentPool).where(TalentPool.candidate_id == candidate_id)
    )).scalars().all()
    for p in pools:
        await db.delete(p)

    # 7. 最后删除候选人
    await db.delete(candidate)
    await db.flush()
    logger.info(
        "删除候选人: id=%s name=%s (级联清理问卷/面试/简历/人才池)",
        candidate_id, candidate.name,
    )
    return {"status": "deleted"}
