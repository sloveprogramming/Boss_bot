"""问卷管理API — 简化版：仅发送固定链接

不再支持题目生成、评分、催填。
发送后将候选人在轻速云的问卷链接通过邮件发出。
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Questionnaire, Candidate, UserRole
from app.dependencies import require_role
from app.services import questionnaire_service, QUESTIONNAIRE_LINK
from app.schemas import QuestionnaireResponse as QResponse

router = APIRouter(
    prefix="/api/questionnaires",
    tags=["问卷管理"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


class SendLinkRequest(BaseModel):
    candidate_id: int


@router.post("/send-link")
async def send_questionnaire_link(
    data: SendLinkRequest,
    db: AsyncSession = Depends(get_db),
):
    """向候选人发送固定的问卷链接（轻速云）"""
    try:
        q = await questionnaire_service.send_questionnaire_link(
            candidate_id=data.candidate_id,
            channel="email",
            db=db,
        )
        await db.commit()
        return {
            "status": "sent",
            "questionnaire_id": q.id,
            "link": QUESTIONNAIRE_LINK,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_questionnaires(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="发送状态筛选：sent / completed"),
    search: Optional[str] = Query(None, description="按候选人姓名 / 手机模糊搜索"),
    db: AsyncSession = Depends(get_db),
):
    """问卷发送记录全量总览（跨候选人，join 候选人信息，带分页/筛选/搜索）"""
    conds = []
    if status:
        conds.append(Questionnaire.status == status)
    if search:
        like = f"%{search.strip()}%"
        conds.append(or_(Candidate.name.like(like), Candidate.phone.like(like)))

    base = select(Questionnaire, Candidate).join(Candidate, Questionnaire.candidate_id == Candidate.id)
    if conds:
        base = base.where(*conds)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar() or 0

    rows = (await db.execute(
        base.order_by(Questionnaire.created_at.desc())
            .offset((page - 1) * page_size).limit(page_size)
    )).all()

    items = [{
        "id": q.id,
        "candidate_id": q.candidate_id,
        "candidate_name": cand.name if cand else "",
        "candidate_phone": cand.phone if cand else "",
        "position": cand.position if cand else "",
        "title": q.title,
        "status": q.status,
        "sent_at": q.sent_at,
        "completed_at": q.completed_at,
        "deadline": q.deadline,
    } for q, cand in rows]

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/{qid}", response_model=QResponse)
async def get_questionnaire(qid: int, db: AsyncSession = Depends(get_db)):
    """获取问卷发送记录"""
    result = await db.execute(
        select(Questionnaire).where(Questionnaire.id == qid)
    )
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(status_code=404, detail="问卷记录不存在")
    return q


@router.get("/candidate/{candidate_id}")
async def get_candidate_questionnaires(
    candidate_id: int, db: AsyncSession = Depends(get_db)
):
    """获取指定候选人的问卷发送记录"""
    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.candidate_id == candidate_id)
        .order_by(Questionnaire.created_at.desc())
    )
    questionnaires = result.scalars().all()
    return [QResponse.model_validate(q) for q in questionnaires]
