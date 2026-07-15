"""仪表盘API — 统计数据"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.database import get_db
from app.models.candidate import Candidate

router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """获取仪表盘统计数据：
    - 候选人总数
    - 今日新增
    - 平均匹配分
    - 录取率
    - 状态分布
    - 本周趋势
    """
    # 候选人总数
    total = (await db.execute(select(func.count(Candidate.id)))).scalar() or 0

    # 各状态候选人数量分布
    status_result = await db.execute(
        select(Candidate.status, func.count(Candidate.id))
        .group_by(Candidate.status)
    )
    status_counts = dict(status_result.all())

    # 今日新增候选人
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_new = (await db.execute(
        select(func.count(Candidate.id))
        .where(Candidate.created_at >= today_start)
    )).scalar() or 0

    # 所有已评分候选人的平均匹配分
    avg_score = (await db.execute(
        select(func.avg(Candidate.match_score))
        .where(Candidate.match_score.isnot(None))
    )).scalar() or 0

    # 本周每天新增候选人趋势
    week_start = today_start - timedelta(days=today_start.weekday())
    trends = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        next_day = day + timedelta(days=1)
        count = (await db.execute(
            select(func.count(Candidate.id))
            .where(Candidate.created_at >= day)
            .where(Candidate.created_at < next_day)
        )).scalar() or 0
        trends.append({
            "date": day.strftime("%Y-%m-%d"),
            "count": count,
        })

    # 录取率（已决定候选人中的录用比例）
    interviewed = status_counts.get("interviewed", 0)
    hired = status_counts.get("hired", 0)
    rejected = status_counts.get("rejected", 0)
    total_decided = hired + rejected
    hire_rate = round(hired / total_decided * 100, 1) if total_decided > 0 else 0

    return {
        "total_candidates": total,
        "today_new": today_new,
        "average_match_score": round(float(avg_score), 1),
        "hire_rate": hire_rate,
        "status_distribution": {
            "new": status_counts.get("new", 0),
            "analyzed": status_counts.get("analyzed", 0),
            "talent_pool": status_counts.get("talent_pool", 0),
            "q_sent": status_counts.get("q_sent", 0),
            "q_done": status_counts.get("q_done", 0),
            "scheduled": status_counts.get("scheduled", 0),
            "interviewed": status_counts.get("interviewed", 0),
            "hired": status_counts.get("hired", 0),
            "rejected": status_counts.get("rejected", 0),
            "archived": status_counts.get("archived", 0),
        },
        "weekly_trend": trends,
    }
