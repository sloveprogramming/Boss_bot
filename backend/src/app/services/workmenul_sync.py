# 【小白导读】Workmenul 对接：后台循环定时拉取外部考试系统的答卷，
#   落库为试卷分析记录（main.py 启动时作为 asyncio 任务跑起来）。
"""Workmenul（自研答题看板）拉取同步 — 把远程终态答卷导入本地「试卷分析」

背景：Workmenul bridge-service 部署在远程云上，其原生的「push 到 Boos_bot」因
回传地址指向它自身（127.0.0.1:18000）到不了本系统，导致试卷分析页一直为空。
这里改为本系统**主动拉取**远程公开查询接口（/api/v1/analysis/list、detail），
再把记录经 exam_analysis_service.import_or_update 幂等 upsert 到 exam_analyses。

只拉终态（completed/failed）；已存在且状态未变化的记录跳过，避免周期性全量重拉。
"""
import asyncio
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models import ExamAnalysis
from app.services.exam_analysis_svc import exam_analysis_service

logger = logging.getLogger(__name__)

# 只同步远程的终态；pending/processing 等分析中记录不拉
_TERMINAL_STATUS = ("completed", "failed")
_LIST_PAGE_SIZE = 100


def _collection_value(raw_callback, keywords: tuple) -> str:
    """从 raw_callback.eventBody.collection（[{fieldName, answerContent}]）里按关键词取值"""
    if not isinstance(raw_callback, dict):
        return ""
    event_body = raw_callback.get("eventBody") or {}
    collection = event_body.get("collection") if isinstance(event_body, dict) else None
    for item in collection or []:
        if not isinstance(item, dict):
            continue
        fname = item.get("fieldName") or ""
        if any(k in fname for k in keywords):
            return (item.get("answerContent") or "").strip()
    return ""


def _resolve_analysis_text(analysis_result) -> str:
    """从远程 analysisResult 解析出报告正文（兼容 Dify 新旧格式）"""
    if not isinstance(analysis_result, dict):
        return ""
    at = analysis_result.get("analysis_text") or analysis_result.get("answer") or ""
    if isinstance(at, str) and at.strip().startswith("{"):
        try:
            obj = json.loads(at)
            if isinstance(obj, dict):
                at = obj.get("answer") or obj.get("analysis_text") or at
        except Exception:
            pass
    return at


def map_detail_to_payload(detail: dict) -> Optional[dict]:
    """把远程 detail 组装成 ExamImportRequest 对齐的 payload（与 Workmenul boosbot_sync 一致）"""
    status = detail.get("analysisStatus")
    if status not in _TERMINAL_STATUS:
        return None

    raw_callback = detail.get("rawCallback") or {}
    event_body = raw_callback.get("eventBody") if isinstance(raw_callback, dict) else None

    candidate_name = _collection_value(raw_callback, ("姓名",)) or detail.get("examineeName") or "匿名考生"
    candidate_phone = _collection_value(raw_callback, ("手机", "电话", "联系")) or detail.get("examineeCode") or None
    candidate_position = _collection_value(raw_callback, ("岗位",)) or None

    seconds = detail.get("useDuration") or 0
    exam_duration = max(1, round(seconds / 60)) if seconds > 0 else None

    # 精简 analysis_result：只保留报告正文，剥离 files/raw_response 等内部字段
    analysis_result = None
    if status == "completed":
        text = _resolve_analysis_text(detail.get("analysisResult"))
        if text:
            analysis_result = {"分析报告": text}

    raw_data = None
    answer_detail = detail.get("answerDetail")
    if event_body is not None or answer_detail is not None:
        raw_data = {"eventBody": event_body, "answerDetail": answer_detail}

    return {
        "external_id": str(detail.get("id")),
        "candidate_name": candidate_name,
        "candidate_phone": candidate_phone,
        "candidate_position": candidate_position,
        "exam_title": detail.get("paperName") or "自研测评",
        "exam_score": detail.get("realScore"),
        "exam_total": detail.get("totalScore"),
        "exam_duration": exam_duration,
        "analysis_status": status,
        "analysis_result": analysis_result,
        "raw_data": raw_data,
        "error_message": detail.get("analysisError") if status == "failed" else None,
    }


async def _get_json(url: str, params: dict = None) -> Optional[dict]:
    """GET 并解析 JSON；网络异常时重试一次，仍失败返回 None"""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("[WorkmenulSync] GET %s 失败(第%s次): %s", url, attempt + 1, e)
    return None


async def sync_from_workmenul(db: AsyncSession) -> dict:
    """拉取远程终态答卷并幂等导入本地，返回本次统计"""
    base = (settings.WORKMENUL_API_BASE or "").rstrip("/")
    stats = {"checked": 0, "imported": 0, "updated": 0, "skipped": 0}
    if not base:
        return stats

    # 本地已有 external_id → 状态 映射（只认已导入的终态记录）
    existing: dict[str, str] = {}
    rows = (
        await db.execute(
            select(ExamAnalysis.external_id, ExamAnalysis.analysis_status).where(
                ExamAnalysis.external_id.isnot(None)
            )
        )
    ).all()
    for ext, st in rows:
        if ext is not None:
            existing[str(ext)] = st

    for status in _TERMINAL_STATUS:
        page = 1
        while True:
            payload = await _get_json(
                f"{base}/api/v1/analysis/list",
                {"status": status, "page": page, "page_size": _LIST_PAGE_SIZE},
            )
            if payload is None or payload.get("code") != 0:
                logger.error("[WorkmenulSync] 拉取 list 失败 status=%s page=%s", status, page)
                break
            data = payload.get("data") or {}
            items = data.get("items") or []
            for item in items:
                stats["checked"] += 1
                key = str(item.get("id"))
                remote_st = item.get("analysisStatus")
                # 已存在且状态未变化 → 跳过（数据不变，无需重拉明细）
                if key in existing and existing[key] == remote_st:
                    stats["skipped"] += 1
                    continue

                detail = await _get_json(f"{base}/api/v1/analysis/detail/{item.get('id')}")
                if detail is None or detail.get("code") != 0:
                    logger.error("[WorkmenulSync] 拉取 detail 失败 id=%s", item.get("id"))
                    continue
                mapped = map_detail_to_payload(detail.get("data") or {})
                if not mapped:
                    continue

                _, created = await exam_analysis_service.import_or_update(db, mapped)
                if created:
                    stats["imported"] += 1
                else:
                    stats["updated"] += 1
                existing[key] = remote_st

            total = data.get("total") or 0
            if page * _LIST_PAGE_SIZE >= total:
                break
            page += 1

    return stats


async def exam_sync_loop(interval_seconds: int = 60) -> None:
    """后台周期任务：每 interval 拉一次远程答卷（异常不外泄，仅记日志）"""
    if not settings.WORKMENUL_API_BASE:
        logger.info("[WorkmenulSync] WORKMENUL_API_BASE 未配置，周期拉取未启动")
        return
    logger.info("[WorkmenulSync] 周期拉取已启动，间隔 %ss，来源 %s", interval_seconds, settings.WORKMENUL_API_BASE)
    while True:
        try:
            async with async_session_factory() as db:
                stats = await sync_from_workmenul(db)
                if stats.get("checked"):
                    logger.info("[WorkmenulSync] 周期拉取完成: %s", stats)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[WorkmenulSync] 周期拉取异常: %s", e)
        await asyncio.sleep(interval_seconds)
