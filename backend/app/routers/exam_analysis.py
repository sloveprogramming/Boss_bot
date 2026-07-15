"""试卷分析路由 — 轻速云回调 + 看板列表"""
import asyncio
import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.exam_analysis import ExamAnalysis
from app.schemas.exam_analysis import ExamAnalysisResponse, ExamAnalysisListResponse
from app.services.exam_analysis_svc import exam_analysis_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exam-analysis", tags=["试卷分析"])


class WebhookRequest(BaseModel):
    """轻速云回调请求体"""
    candidate_name: str
    exam_title: str
    candidate_phone: Optional[str] = None
    score: Optional[float] = None
    total: Optional[float] = None
    duration: Optional[int] = None

    model_config = {"extra": "allow"}  # 允许接收额外字段


@router.post("/webhook", status_code=200)
async def exam_webhook(data: WebhookRequest, db: AsyncSession = Depends(get_db)):
    """轻速云考试结果回调入口"""
    record = ExamAnalysis(
        candidate_name=data.candidate_name,
        candidate_phone=data.candidate_phone,
        exam_title=data.exam_title,
        exam_score=data.score,
        exam_total=data.total,
        exam_duration=data.duration,
        raw_data=data.model_dump(),
        analysis_status="pending",
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)

    # 后台异步触发 Dify 分析
    asyncio.create_task(
        exam_analysis_service.trigger_analysis(db, record.id)
    )

    return {
        "id": record.id,
        "status": "pending",
        "message": "考试结果已接收，分析任务已提交",
    }


@router.get("", response_model=ExamAnalysisListResponse)
async def list_analyses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取试卷分析记录列表（按时间倒序）"""
    # 查询总数
    count_q = select(func.count(ExamAnalysis.id))
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    # 查询分页数据
    q = (
        select(ExamAnalysis)
        .order_by(ExamAnalysis.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(q)
    items = result.scalars().all()

    return ExamAnalysisListResponse(
        total=total,
        items=[ExamAnalysisResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
    )
