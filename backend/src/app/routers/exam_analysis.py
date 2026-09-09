# ═══════════════════════════════════════════════════════════════
# 【小白导读】试卷分析：接收外部考试系统（Workmenul）的 webhook 推送 / 定时同步，
#   提供分析列表、手动导入、报告下载。业务逻辑在 services/exam_analysis_svc.py。
# ═══════════════════════════════════════════════════════════════
"""试卷分析路由 — 轻速云回调 + 看板列表"""
import asyncio
import logging
import secrets
from typing import Optional
from urllib.parse import quote

import httpx
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.dependencies import require_role
from app.models import ExamAnalysis, UserRole
from app.schemas import (
    ExamAnalysisResponse, ExamAnalysisListResponse,
    ExamImportRequest, ExamImportResponse,
)
from app.services import exam_analysis_service
from app.services.workmenul_sync import sync_from_workmenul

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


def _verify_webhook_token(webhook_token: Optional[str]) -> None:
    """校验外部系统回调/导入令牌（未配置或失配一律 401）"""
    if not settings.EXAM_WEBHOOK_TOKEN or not webhook_token or not secrets.compare_digest(
        webhook_token, settings.EXAM_WEBHOOK_TOKEN
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")


@router.post("/webhook", status_code=200)
async def exam_webhook(
    data: WebhookRequest,
    db: AsyncSession = Depends(get_db),
    webhook_token: Optional[str] = Header(None, alias="X-Webhook-Token"),
):
    """轻速云考试结果回调入口"""
    _verify_webhook_token(webhook_token)
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
    _: object = Depends(require_role([UserRole.ADMIN, UserRole.HR, UserRole.INTERVIEWER])),
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


@router.post("/import", response_model=ExamImportResponse)
async def import_analysis(
    data: ExamImportRequest,
    db: AsyncSession = Depends(get_db),
    webhook_token: Optional[str] = Header(None, alias="X-Webhook-Token"),
):
    """自研答题系统导入已分析结果（幂等 upsert，不触发 Dify）"""
    _verify_webhook_token(webhook_token)
    record_id, created = await exam_analysis_service.import_or_update(
        db, data.model_dump(exclude_none=True)
    )
    return ExamImportResponse(id=record_id, created=created)


@router.post("/sync")
async def sync_from_workmenul_endpoint(
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_role([UserRole.ADMIN, UserRole.HR, UserRole.INTERVIEWER])),
):
    """手动触发：从 Workmenul 拉取终态答卷并幂等导入（返回本次统计）"""
    stats = await sync_from_workmenul(db)
    if stats.get("checked") == 0:
        return {**stats, "message": "Workmenul 未配置或无可用记录"}
    return stats


_DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("/{analysis_id}/download-report")
async def download_report(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_role([UserRole.ADMIN, UserRole.HR, UserRole.INTERVIEWER])),
):
    """下载与 Workmenul 看板一致的 Word 分析报告（反代其 /report 接口）

    报告 docx 由 Workmenul 侧 Dify 生成并转存，本接口不落库、不重生成，
    直接转发上游文件，保证下载到的与看板「报告」链接是同一份。
    """
    record = await db.get(ExamAnalysis, analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not record.external_id:
        raise HTTPException(status_code=400, detail="该记录并非来自 Workmenul，无原版 Word 报告可下载")
    base = (settings.WORKMENUL_API_BASE or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="未配置 WORKMENUL_API_BASE，无法访问 Workmenul")

    url = f"{base}/api/v1/analysis/{record.external_id}/report"
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url)
    except Exception as e:
        logger.warning("[ExamReport] 拉取 Workmenul 报告失败 id=%s: %s", analysis_id, e)
        raise HTTPException(status_code=502, detail="访问 Workmenul 报告服务失败，请稍后重试") from e

    if resp.status_code != 200:
        detail = "Workmenul 侧暂无该报告文件（可能签名链接已过期）"
        try:
            remote_detail = resp.json().get("detail")
            if isinstance(remote_detail, str) and remote_detail:
                detail = remote_detail
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if resp.status_code == 404 else status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )

    if not resp.content.startswith(b"PK"):
        logger.warning("[ExamReport] Workmenul 返回非 docx 内容 id=%s", analysis_id)
        raise HTTPException(status_code=502, detail="Workmenul 返回的不是有效 Word 文件")

    headers = {}
    cd = resp.headers.get("Content-Disposition")
    if cd:
        headers["Content-Disposition"] = cd
    else:
        fname = f"{record.candidate_name or '考生'}_测评分析报告.docx"
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return Response(content=resp.content, media_type=_DOCX_MEDIA, headers=headers)
