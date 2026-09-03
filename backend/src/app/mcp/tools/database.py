"""MCP 数据库查询 Tools — 候选人、面试、仪表盘统计

5 个工具函数，全部返回结构化 JSON 字符串。
可被 MCP Server (stdio) 或 LangGraph Function Calling 节点直接调用。
所有 SQLAlchemy 导入均为懒加载，避免触发 services/__init__.py。
"""
import time
import logging
from typing import Optional
import json                                                    # 所有返回值序列化为 JSON 字符串

logger = logging.getLogger(__name__)


async def _get_db():
    """创建独立的数据库会话 — 每次工具调用新建一个连接"""
    from app.database import async_session_factory              # 懒加载
    return async_session_factory()


def _audit(tool: str, params: dict, result_summary: str, duration_ms: float) -> None:
    """工具调用审计日志 — 记录工具名、参数、结果摘要、耗时"""
    logger.info(
        "[MCP审计] %s params=%s -> %s (%.0fms)",
        tool, json.dumps(params, ensure_ascii=False, default=str),
        result_summary, duration_ms,
    )


# ===== 工具 1: 搜候选人 =====

async def query_candidates(
    name: Optional[str] = None,                                # 姓名模糊匹配
    position: Optional[str] = None,                            # 岗位模糊匹配
    status: Optional[str] = None,                              # 状态精确匹配
    job_category: Optional[str] = None,                        # 类别精确匹配
    min_score: Optional[float] = None,                         # 最低分
    max_score: Optional[float] = None,                         # 最高分
    page: int = 1,                                             # 页码
    page_size: int = 20,                                       # 每页条数
) -> str:                                                      # 返回 JSON 字符串
    """搜索/筛选候选人列表 — 支持多条件组合 + 分页"""
    _start = time.perf_counter()
    from sqlalchemy import select, func                        # 懒加载
    from app.models import Candidate

    db = await _get_db()                                       # 建独立数据库会话
    try:
        query = select(Candidate)                              # 主查询
        count_query = select(func.count(Candidate.id))          # 计数查询（分页需要总数）

        # 逐条件叠加筛选（同名条件同时在主查询和计数查询上叠加）
        if name:                                               # 姓名模糊
            query = query.where(Candidate.name.contains(name))
            count_query = count_query.where(Candidate.name.contains(name))
        if position:                                           # 岗位模糊
            query = query.where(Candidate.position.contains(position))
            count_query = count_query.where(Candidate.position.contains(position))
        if status:                                             # 状态精确
            query = query.where(Candidate.status == status)
            count_query = count_query.where(Candidate.status == status)
        if job_category:                                       # 类别精确
            query = query.where(Candidate.job_category == job_category)
            count_query = count_query.where(Candidate.job_category == job_category)
        if min_score is not None:                              # 最低分
            query = query.where(Candidate.match_score >= min_score)
            count_query = count_query.where(Candidate.match_score >= min_score)
        if max_score is not None:                              # 最高分
            query = query.where(Candidate.match_score <= max_score)
            count_query = count_query.where(Candidate.match_score <= max_score)

        total = (await db.execute(count_query)).scalar() or 0  # 执行计数
        query = query.order_by(Candidate.created_at.desc())    # 最新在前
        query = query.offset((page - 1) * page_size).limit(page_size)  # 分页
        result = await db.execute(query)                       # 执行查询
        candidates = result.scalars().all()

        items = []                                             # 构建返回列表
        for c in candidates:
            items.append({
                "id": c.id, "name": c.name,
                "email": c.email, "phone": c.phone,
                "position": c.position, "status": c.status,
                "job_category": c.job_category,
                "match_score": c.match_score,
                "tags": c.tags or [],
                "source": c.source,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            })

        _audit("query_candidates", {
            "name": name, "position": position, "status": status,
            "job_category": job_category, "min_score": min_score,
            "max_score": max_score, "page": page, "page_size": page_size,
        }, f"total={total}, 返回{len(items)}条", (time.perf_counter() - _start) * 1000)

        return json.dumps({
            "total": total, "page": page, "page_size": page_size,
            "candidates": items,
        }, ensure_ascii=False)                                 # 中文不转义
    finally:
        await db.close()                                       # 用完关闭连接


# ===== 工具 2: 候选人详情 =====

async def get_candidate_detail(candidate_id: int) -> str:
    """获取候选人完整信息 — 简历分析 + 面试记录 + 通知历史"""
    _start = time.perf_counter()
    from sqlalchemy import select
    from app.models import Candidate
    from app.models import Resume
    from app.models import Interview
    from app.models import Notification

    db = await _get_db()
    try:
        result = await db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:                                      # 候选人不存在
            _audit("get_candidate_detail", {"candidate_id": candidate_id},
                   "候选人不存在", (time.perf_counter() - _start) * 1000)
            return json.dumps({"error": f"候选人不存在: {candidate_id}"}, ensure_ascii=False)

        # 查简历分析（可能为空）
        resume_result = await db.execute(
            select(Resume).where(Resume.candidate_id == candidate_id)
        )
        resume = resume_result.scalar_one_or_none()

        # 查所有面试记录
        interview_result = await db.execute(
            select(Interview).where(Interview.candidate_id == candidate_id)
        )
        interviews = interview_result.scalars().all()

        # 查最近 10 条通知
        notif_result = await db.execute(
            select(Notification)
            .where(Notification.candidate_id == candidate_id)
            .order_by(Notification.created_at.desc())
            .limit(10)
        )
        notifications = notif_result.scalars().all()

        return json.dumps({
            "candidate": {
                "id": candidate.id, "name": candidate.name,
                "email": candidate.email, "phone": candidate.phone,
                "position": candidate.position, "status": candidate.status,
                "job_category": candidate.job_category,
                "match_score": candidate.match_score,
                "experience_years": candidate.experience_years,
                "tags": candidate.tags or [],
                "source": candidate.source,
                "source_url": candidate.source_url,
                "created_at": candidate.created_at.isoformat() if candidate.created_at else "",
                "updated_at": candidate.updated_at.isoformat() if candidate.updated_at else "",
            },
            "resume": {                                        # 简历分析（可能为空）
                "id": resume.id,
                "raw_text": resume.raw_text[:500] if resume and resume.raw_text else "",
                "analysis_result": resume.analysis_result if resume else None,
                "match_analysis": resume.match_analysis if resume else None,
                "summary": resume.summary if resume else "",
            } if resume else None,
            "interviews": [                                    # 面试记录列表
                {
                    "id": i.id, "round": i.round, "status": i.status,
                    "interviewers": i.interviewers or [],
                    "confirmed_start": i.confirmed_start.isoformat() if i.confirmed_start else None,
                    "location": i.location, "meeting_link": i.meeting_link,
                    "feedback": i.feedback, "ai_summary": i.ai_summary,
                }
                for i in interviews
            ],
            "recent_notifications": [                          # 最近通知
                {
                    "id": n.id, "type": n.type, "template": n.template,
                    "status": n.status, "subject": n.subject,
                    "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                }
                for n in notifications
            ],
        }, ensure_ascii=False)

        _audit("get_candidate_detail", {"candidate_id": candidate_id},
               f"候选人={candidate.name}, 面试{len(interviews)}场, 通知{len(notifications)}条",
               (time.perf_counter() - _start) * 1000)
    finally:
        await db.close()


# ===== 工具 3: 查面试 =====

async def query_interviews(                                    # 同上模式，查 Interview 表
    status: Optional[str] = None,
    date_from: Optional[str] = None,                           # ISO 日期字符串 "2026-07-01"
    date_to: Optional[str] = None,
    round_filter: Optional[str] = None,                        # first/technical/hr/final
    page: int = 1,
    page_size: int = 20,
) -> str:
    """查询面试安排列表 — 按状态/日期/轮次筛选"""
    _start = time.perf_counter()
    from datetime import datetime as dt
    from sqlalchemy import select, func
    from app.models import Interview
    from app.models import Candidate

    db = await _get_db()
    try:
        query = select(Interview)
        count_query = select(func.count(Interview.id))

        if status: query = query.where(Interview.status == status); count_query = count_query.where(Interview.status == status)
        if round_filter: query = query.where(Interview.round == round_filter); count_query = count_query.where(Interview.round == round_filter)
        if date_from: d = dt.fromisoformat(date_from); query = query.where(Interview.confirmed_start >= d); count_query = count_query.where(Interview.confirmed_start >= d)
        if date_to: d = dt.fromisoformat(date_to); query = query.where(Interview.confirmed_start <= d); count_query = count_query.where(Interview.confirmed_start <= d)

        total = (await db.execute(count_query)).scalar() or 0
        query = query.order_by(Interview.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        interviews = result.scalars().all()

        items = []
        for i in interviews:
            cand_result = await db.execute(select(Candidate.name).where(Candidate.id == i.candidate_id))
            cand_name = cand_result.scalar_one_or_none() or "未知"

            items.append({
                "id": i.id, "candidate_id": i.candidate_id,
                "candidate_name": cand_name,
                "round": i.round, "status": i.status,
                "interviewers": i.interviewers or [],
                "confirmed_start": i.confirmed_start.isoformat() if i.confirmed_start else None,
                "confirmed_end": i.confirmed_end.isoformat() if i.confirmed_end else None,
                "location": i.location, "meeting_link": i.meeting_link,
                "feedback": i.feedback, "ai_summary": i.ai_summary,
            })

        _audit("query_interviews", {
            "status": status, "date_from": date_from, "date_to": date_to,
            "round_filter": round_filter, "page": page, "page_size": page_size,
        }, f"total={total}, 返回{len(items)}条", (time.perf_counter() - _start) * 1000)

        return json.dumps({"total": total, "page": page, "page_size": page_size, "interviews": items}, ensure_ascii=False)
    finally:
        await db.close()


# ===== 工具 4: 仪表盘统计 =====

async def get_dashboard_stats() -> str:
    """获取招聘仪表盘全景数据 — 总数/新增/分布/平均分/录用率/岗位分布"""
    _start = time.perf_counter()
    from datetime import datetime as dt, timedelta
    from sqlalchemy import select, func
    from app.models import Candidate
    from app.models import Interview

    db = await _get_db()
    try:
        today = dt.utcnow().date()                             # 今天日期
        today_start = dt.combine(today, dt.min.time())         # 今天 0 点
        week_ago = today - timedelta(days=7)                   # 7 天前
        week_start = dt.combine(week_ago, dt.min.time())

        # 各维度查询
        total = (await db.execute(select(func.count(Candidate.id)))).scalar() or 0
        today_new = (await db.execute(select(func.count(Candidate.id)).where(Candidate.created_at >= today_start))).scalar() or 0
        status_result = await db.execute(select(Candidate.status, func.count(Candidate.id)).group_by(Candidate.status))
        status_dist = {row[0]: row[1] for row in status_result.all()}
        avg_score = round(float((await db.execute(select(func.avg(Candidate.match_score)).where(Candidate.match_score.isnot(None)))).scalar() or 0), 1)
        cat_result = await db.execute(select(Candidate.job_category, func.count(Candidate.id)).where(Candidate.job_category.isnot(None)).group_by(Candidate.job_category))
        job_categories = {row[0]: row[1] for row in cat_result.all()}
        hired_count = status_dist.get("hired", 0)
        completed = sum(status_dist.values()) - status_dist.get("new", 0)
        hire_rate = round(hired_count / completed * 100, 1) if completed > 0 else 0
        weekly_new = (await db.execute(select(func.count(Candidate.id)).where(Candidate.created_at >= week_start))).scalar() or 0
        interviews_pending = (await db.execute(select(func.count(Interview.id)).where(Interview.status.in_(["pending", "awaiting_confirm", "confirmed"])))).scalar() or 0

        _audit("get_dashboard_stats", {},
               f"total={total}, 今日新增={today_new}, 录用率={hire_rate}%",
               (time.perf_counter() - _start) * 1000)

        return json.dumps({
            "total_candidates": total, "today_new": today_new,
            "status_distribution": status_dist,
            "avg_match_score": avg_score, "hire_rate": hire_rate,
            "weekly_new": weekly_new, "interviews_pending": interviews_pending,
            "job_category_distribution": job_categories,
        }, ensure_ascii=False)
    finally:
        await db.close()
