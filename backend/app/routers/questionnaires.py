"""问卷管理API — 简化版：仅发送固定链接

不再支持题目生成、评分、催填。
发送后将候选人在轻速云的问卷链接通过邮件发出。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.questionnaire import Questionnaire
from app.services.questionnaire_svc import questionnaire_service, QUESTIONNAIRE_LINK
from app.schemas.questionnaire import QuestionnaireResponse as QResponse

router = APIRouter(prefix="/api/questionnaires", tags=["问卷管理"])


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
