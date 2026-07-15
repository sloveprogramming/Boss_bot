"""MCP 数据库查询 Tools — 候选人、面试、仪表盘统计

所有函数返回结构化 JSON 字符串，供 LLM 消费。
工具函数可被 MCP Server (stdio) 或 LangGraph Function Calling 节点直接调用。

所有导入均为懒加载，避免导入链触发 services/__init__.py。
"""
from typing import Optional
import json


async def _get_db():
    """创建独立的数据库会话（MCP 工具内部使用）"""
    from app.database import async_session_factory
    return async_session_factory()


# ===== 候选人查询 =====

async def query_candidates(
    name: Optional[str] = None,
    position: Optional[str] = None,
    status: Optional[str] = None,
    job_category: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """搜索/筛选候选人列表。

    支持按姓名、岗位、状态、类别、匹配度范围筛选。

    Args:
        name: 候选人姓名（模糊匹配）
        position: 应聘岗位（模糊匹配）
        status: 状态：new/analyzed/talent_pool/q_sent/q_done/scheduled/interviewed/hired/rejected
        job_category: 岗位类别：python/java/product/ai/frontend/ops/test
        min_score: 最低匹配度分数
        max_score: 最高匹配度分数
        page: 页码（从1开始）
        page_size: 每页条数（默认20）

    Returns:
        JSON 字符串：{total, page, page_size, candidates: [...]}
    """
    from sqlalchemy import select, func
    from app.models.candidate import Candidate

    db = await _get_db()
    try:
        query = select(Candidate)
        count_query = select(func.count(Candidate.id))

        if name:
            query = query.where(Candidate.name.contains(name))
            count_query = count_query.where(Candidate.name.contains(name))
        if position:
            query = query.where(Candidate.position.contains(position))
            count_query = count_query.where(Candidate.position.contains(position))
        if status:
            query = query.where(Candidate.status == status)
            count_query = count_query.where(Candidate.status == status)
        if job_category:
            query = query.where(Candidate.job_category == job_category)
            count_query = count_query.where(Candidate.job_category == job_category)
        if min_score is not None:
            query = query.where(Candidate.match_score >= min_score)
            count_query = count_query.where(Candidate.match_score >= min_score)
        if max_score is not None:
            query = query.where(Candidate.match_score <= max_score)
            count_query = count_query.where(Candidate.match_score <= max_score)

        total = (await db.execute(count_query)).scalar() or 0
        query = query.order_by(Candidate.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        candidates = result.scalars().all()

        items = []
        for c in candidates:
            items.append({
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "position": c.position,
                "status": c.status,
                "job_category": c.job_category,
                "match_score": c.match_score,
                "tags": c.tags or [],
                "source": c.source,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            })

        return json.dumps({
            "total": total,
            "page": page,
            "page_size": page_size,
            "candidates": items,
        }, ensure_ascii=False)
    finally:
        await db.close()


async def get_candidate_detail(candidate_id: int) -> str:
    """获取候选人完整信息，包括简历分析结果、面试记录、通知历史。

    Args:
        candidate_id: 候选人 ID

    Returns:
        JSON 字符串：候选人完整信息
    """
    from sqlalchemy import select
    from app.models.candidate import Candidate
    from app.models.resume import Resume
    from app.models.interview import Interview
    from app.models.notification import Notification

    db = await _get_db()
    try:
        result = await db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            return json.dumps({"error": f"候选人不存在: {candidate_id}"}, ensure_ascii=False)

        # 查询简历分析
        resume_result = await db.execute(
            select(Resume).where(Resume.candidate_id == candidate_id)
        )
        resume = resume_result.scalar_one_or_none()

        # 查询面试记录
        interview_result = await db.execute(
            select(Interview).where(Interview.candidate_id == candidate_id)
        )
        interviews = interview_result.scalars().all()

        # 查询通知历史
        notif_result = await db.execute(
            select(Notification)
            .where(Notification.candidate_id == candidate_id)
            .order_by(Notification.created_at.desc())
            .limit(10)
        )
        notifications = notif_result.scalars().all()

        return json.dumps({
            "candidate": {
                "id": candidate.id,
                "name": candidate.name,
                "email": candidate.email,
                "phone": candidate.phone,
                "position": candidate.position,
                "status": candidate.status,
                "job_category": candidate.job_category,
                "match_score": candidate.match_score,
                "experience_years": candidate.experience_years,
                "tags": candidate.tags or [],
                "source": candidate.source,
                "source_url": candidate.source_url,
                "created_at": candidate.created_at.isoformat() if candidate.created_at else "",
                "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else "",
            },
            "resume": {
                "id": resume.id,
                "raw_text": resume.raw_text[:500] if resume and resume.raw_text else "",
                "analysis_result": resume.analysis_result if resume else None,
                "match_analysis": resume.match_analysis if resume else None,
                "summary": resume.summary if resume else "",
            } if resume else None,
            "interviews": [
                {
                    "id": i.id,
                    "round": i.round,
                    "status": i.status,
                    "interviewers": i.interviewers or [],
                    "confirmed_start": i.confirmed_start.isoformat() if i.confirmed_start else None,
                    "location": i.location,
                    "meeting_link": i.meeting_link,
                    "feedback": i.feedback,
                    "ai_summary": i.ai_summary,
                }
                for i in interviews
            ],
            "recent_notifications": [
                {
                    "id": n.id,
                    "type": n.type,
                    "template": n.template,
                    "status": n.status,
                    "subject": n.subject,
                    "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                }
                for n in notifications
            ],
        }, ensure_ascii=False)
    finally:
        await db.close()


# ===== 面试查询 =====

async def query_interviews(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    round_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """查询面试安排列表。

    Args:
        status: 面试状态：pending/awaiting_confirm/confirmed/completed/cancelled
        date_from: 面试日期起始 (ISO 格式，如 "2026-07-01")
        date_to: 面试日期截止
        round_filter: 面试轮次：first/technical/hr/final
        page: 页码
        page_size: 每页条数

    Returns:
        JSON 字符串：{total, interviews: [...]}
    """
    from datetime import datetime as dt
    from sqlalchemy import select, func
    from app.models.interview import Interview
    from app.models.candidate import Candidate

    db = await _get_db()
    try:
        query = select(Interview)
        count_query = select(func.count(Interview.id))

        if status:
            query = query.where(Interview.status == status)
            count_query = count_query.where(Interview.status == status)
        if round_filter:
            query = query.where(Interview.round == round_filter)
            count_query = count_query.where(Interview.round == round_filter)
        if date_from:
            d = dt.fromisoformat(date_from)
            query = query.where(Interview.confirmed_start >= d)
            count_query = count_query.where(Interview.confirmed_start >= d)
        if date_to:
            d = dt.fromisoformat(date_to)
            query = query.where(Interview.confirmed_start <= d)
            count_query = count_query.where(Interview.confirmed_start <= d)

        total = (await db.execute(count_query)).scalar() or 0
        query = query.order_by(Interview.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        interviews = result.scalars().all()

        items = []
        for i in interviews:
            # 获取候选人姓名
            cand_result = await db.execute(
                select(Candidate.name).where(Candidate.id == i.candidate_id)
            )
            cand_name = cand_result.scalar_one_or_none() or "未知"

            items.append({
                "id": i.id,
                "candidate_id": i.candidate_id,
                "candidate_name": cand_name,
                "round": i.round,
                "status": i.status,
                "interviewers": i.interviewers or [],
                "confirmed_start": i.confirmed_start.isoformat() if i.confirmed_start else None,
                "confirmed_end": i.confirmed_end.isoformat() if i.confirmed_end else None,
                "location": i.location,
                "meeting_link": i.meeting_link,
                "feedback": i.feedback,
                "ai_summary": i.ai_summary,
            })

        return json.dumps({
            "total": total,
            "page": page,
            "page_size": page_size,
            "interviews": items,
        }, ensure_ascii=False)
    finally:
        await db.close()


# ===== 仪表盘统计 =====

async def get_dashboard_stats() -> str:
    """获取招聘仪表盘统计数据。

    Returns:
        JSON 字符串：{total_candidates, status_distribution, avg_match_score,
                       today_new, weekly_trend, job_category_distribution}
    """
    from datetime import datetime as dt, timedelta
    from sqlalchemy import select, func
    from app.models.candidate import Candidate
    from app.models.interview import Interview

    db = await _get_db()
    try:
        today = dt.utcnow().date()

        # 总数
        total = (await db.execute(select(func.count(Candidate.id)))).scalar() or 0

        # 今日新增
        today_start = dt.combine(today, dt.min.time())
        today_new = (await db.execute(
            select(func.count(Candidate.id))
            .where(Candidate.created_at >= today_start)
        )).scalar() or 0

        # 状态分布
        status_result = await db.execute(
            select(Candidate.status, func.count(Candidate.id))
            .group_by(Candidate.status)
        )
        status_dist = {row[0]: row[1] for row in status_result.all()}

        # 平均匹配度
        avg_score = (await db.execute(
            select(func.avg(Candidate.match_score))
            .where(Candidate.match_score.isnot(None))
        )).scalar() or 0
        avg_score = round(float(avg_score), 1)

        # 岗位类别分布
        cat_result = await db.execute(
            select(Candidate.job_category, func.count(Candidate.id))
            .where(Candidate.job_category.isnot(None))
            .group_by(Candidate.job_category)
        )
        job_categories = {row[0]: row[1] for row in cat_result.all()}

        # 录用率
        hired_count = status_dist.get("hired", 0)
        completed = sum(status_dist.values()) - status_dist.get("new", 0) - status_dist.get("archived", 0)
        hire_rate = round(hired_count / completed * 100, 1) if completed > 0 else 0

        # 本周趋势
        week_ago = today - timedelta(days=7)
        week_start = dt.combine(week_ago, dt.min.time())
        weekly_new = (await db.execute(
            select(func.count(Candidate.id))
            .where(Candidate.created_at >= week_start)
        )).scalar() or 0

        # 面试待办
        interviews_pending = (await db.execute(
            select(func.count(Interview.id))
            .where(Interview.status.in_(["pending", "awaiting_confirm", "confirmed"]))
        )).scalar() or 0

        return json.dumps({
            "total_candidates": total,
            "today_new": today_new,
            "status_distribution": status_dist,
            "avg_match_score": avg_score,
            "hire_rate": hire_rate,
            "weekly_new": weekly_new,
            "interviews_pending": interviews_pending,
            "job_category_distribution": job_categories,
        }, ensure_ascii=False)
    finally:
        await db.close()
