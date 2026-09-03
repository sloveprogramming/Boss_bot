"""LLM 调用可观测性 API — 查询调用日志和聚合统计

提供接口用于监控和调试 LLM 调用情况，包括：
  - 每次调用的输入/输出/延迟/Token用量
  - 按功能聚合统计（平均延迟、总Token、调用次数）
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.models import LLMCallLog, UserRole
from app.dependencies import require_role

router = APIRouter(
    prefix="/api/llm",
    tags=["LLM可观测性"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


@router.get("/logs")
async def list_llm_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    function_name: Optional[str] = Query(None, description="按功能名称过滤"),
    db: AsyncSession = Depends(get_db),
):
    """查询 LLM 调用日志（分页）"""
    query = select(LLMCallLog)

    if function_name:
        query = query.where(LLMCallLog.function_name == function_name)

    # 总数
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # 分页查询（按时间倒序）
    query = query.order_by(LLMCallLog.timestamp.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [log.to_dict() for log in logs],
    }


@router.get("/logs/{log_id}")
async def get_llm_log_detail(log_id: int, db: AsyncSession = Depends(get_db)):
    """查询单条 LLM 调用详情（含完整请求和响应）"""
    result = await db.execute(select(LLMCallLog).where(LLMCallLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="日志不存在")

    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat() if log.timestamp else "",
        "session_id": log.session_id,
        "function_name": log.function_name,
        "model": log.model,
        "system_prompt": log.system_prompt,
        "messages": log.messages,
        "response": log.response,
        "prompt_tokens": log.prompt_tokens,
        "completion_tokens": log.completion_tokens,
        "total_tokens": log.total_tokens,
        "latency_ms": log.latency_ms,
    }


@router.get("/stats")
async def get_llm_stats(db: AsyncSession = Depends(get_db)):
    """获取 LLM 调用聚合统计

    按 function_name 分组统计：
      - 调用次数 / 总Token / 平均延迟
    """
    query = select(
        LLMCallLog.function_name,
        func.count(LLMCallLog.id).label("call_count"),
        func.sum(LLMCallLog.total_tokens).label("total_tokens"),
        func.avg(LLMCallLog.latency_ms).label("avg_latency_ms"),
        func.max(LLMCallLog.latency_ms).label("max_latency_ms"),
        func.sum(LLMCallLog.prompt_tokens).label("total_prompt_tokens"),
        func.sum(LLMCallLog.completion_tokens).label("total_completion_tokens"),
    ).group_by(LLMCallLog.function_name)

    result = await db.execute(query)
    rows = result.all()

    stats = []
    for row in rows:
        stats.append({
            "function_name": row.function_name,
            "call_count": row.call_count,
            "total_tokens": row.total_tokens or 0,
            "total_prompt_tokens": row.total_prompt_tokens or 0,
            "total_completion_tokens": row.total_completion_tokens or 0,
            "avg_latency_ms": round(row.avg_latency_ms, 2) if row.avg_latency_ms else 0,
            "max_latency_ms": row.max_latency_ms or 0,
        })

    # 全局汇总
    total_tokens = sum(s["total_tokens"] for s in stats)
    total_calls = sum(s["call_count"] for s in stats)

    return {
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "estimated_cost": round(total_tokens * 0.000002, 4),  # 按 $2/M tokens 估算
        "by_function": stats,
    }
