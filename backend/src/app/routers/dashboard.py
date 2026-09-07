"""仪表盘API — 统计数据"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from app.database import get_db
from app.config import settings
from app.models import Candidate, User
from app.models import UserRole
from app.dependencies import (
    require_role, get_current_user, candidate_scope_cond,
)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["仪表盘"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


@router.get("/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取仪表盘统计数据：
    - 候选人总数
    - 今日新增
    - 平均匹配分
    - 录取率
    - 状态分布
    - 本周趋势

    HR 仅统计自己名下候选人；admin 全量。
    """
    cond = candidate_scope_cond(current_user)

    def _apply(stmt):
        return stmt.where(cond) if cond is not None else stmt

    # 候选人总数
    total = (await db.execute(_apply(select(func.count(Candidate.id))))).scalar() or 0

    # 各状态候选人数量分布
    status_result = await db.execute(
        _apply(select(Candidate.status, func.count(Candidate.id)))
        .group_by(Candidate.status)
    )
    status_counts = dict(status_result.all())

    # 今日新增候选人
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_new = (await db.execute(
        _apply(
            select(func.count(Candidate.id))
            .where(Candidate.created_at >= today_start)
        )
    )).scalar() or 0

    # 所有已评分候选人的平均匹配分
    avg_score = (await db.execute(
        _apply(
            select(func.avg(Candidate.match_score))
            .where(Candidate.match_score.isnot(None))
        )
    )).scalar() or 0

    # 本周每天新增候选人趋势
    week_start = today_start - timedelta(days=today_start.weekday())
    trends = []
    for i in range(7):
        day = week_start + timedelta(days=i)
        next_day = day + timedelta(days=1)
        count = (await db.execute(
            _apply(
                select(func.count(Candidate.id))
                .where(Candidate.created_at >= day)
                .where(Candidate.created_at < next_day)
            )
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


# ========== v2 评分体系数据闭环 ==========

def _bucket_of(score: float, bucket_size: int = 10) -> int:
    """分数 → 分桶下界（75.3 → 70）"""
    return int(score // bucket_size) * bucket_size


@router.get("/score-buckets")
async def get_score_buckets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分桶通过率报表 — 评分体系数据闭环的核心指标

    按总分 10 分一档统计面试结果（来源：supervisor 决策回流到
    resume.match_analysis.interview_outcome 的标签），输出：
    - 每档样本量 / 通过率
    - 跨档倒挂检测（低分档通过率 ≥ 高分档 → 提示阈值/权重可能有问题）
    - 标注不足提示（样本 < 30 时只展示不建议）

    HR 仅统计自己名下候选人的标签样本；admin 全量。
    """
    from app.models import Resume

    query = select(Resume).join(Candidate, Resume.candidate_id == Candidate.id)
    cond = candidate_scope_cond(current_user)
    if cond is not None:
        query = query.where(cond)
    result = await db.execute(query.where(Resume.match_analysis.isnot(None)))
    resumes = result.scalars().all()

    # 聚合：bucket → [total, passed]
    buckets: dict[int, list[int]] = {}
    labeled_total = 0
    for resume in resumes:
        ma = resume.match_analysis or {}
        outcome = ma.get("interview_outcome")
        if outcome not in ("hired", "rejected"):
            continue
        score = ma.get("overall_score")
        if score is None:
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        b = _bucket_of(score)
        buckets.setdefault(b, [0, 0])
        buckets[b][0] += 1
        if outcome == "hired":
            buckets[b][1] += 1
        labeled_total += 1

    rows = []
    for b in sorted(buckets):
        total, passed = buckets[b]
        rows.append({
            "bucket": f"{b}-{b + 9}",
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
        })

    # 跨档倒挂检测：低分档通过率明显偏高 → 分数区分度存疑
    inversions = []
    for i in range(len(rows) - 1):
        lower, upper = rows[i], rows[i + 1]
        # 两档都有足够样本（>=5）且低档通过率比高档高 10 个百分点以上
        if lower["total"] >= 5 and upper["total"] >= 5 \
                and lower["pass_rate"] > upper["pass_rate"] + 10:
            inversions.append({
                "lower_bucket": lower["bucket"],
                "upper_bucket": upper["bucket"],
                "detail": f"{lower['bucket']} 通过率 {lower['pass_rate']}% "
                          f"高于 {upper['bucket']} 的 {upper['pass_rate']}%",
            })

    suggestions = []
    if labeled_total < 30:
        suggestions.append(
            f"标注样本仅 {labeled_total} 条（<30），统计不显著，继续积累标签，暂不做任何调整"
        )
    elif inversions:
        suggestions.append(
            "检测到通过率倒挂：分数区分度存疑，建议检查对应分数段的维度分和权重"
        )
    else:
        suggestions.append("分桶单调性正常，暂无需调整")

    return {
        "labeled_total": labeled_total,
        "buckets": rows,
        "inversions": inversions,
        "suggestions": suggestions,
        "note": "标签来源：supervisor 决策回流。建议每周看一次，单变量调整。",
    }


@router.post("/scoring-weights", dependencies=[Depends(require_role([UserRole.ADMIN]))])
async def update_scoring_weights(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """热更新评分权重（admin only，内存生效）

    接收 {"weights": {"skill": 0.4, "experience": 0.4, "stability": 0.2},
          "category": "python"（可选，缺省改默认）}
    - 校验通过后写入 settings（进程内存，立即对后续分析生效）
    - 重启后回退为 .env 配置，持久化请改 .env
    - 历史分数重算请另跑 scripts/recalc_scores.py
    """
    from fastapi import HTTPException
    weights = payload.get("weights")
    category = payload.get("category")

    if not isinstance(weights, dict) or not weights:
        raise HTTPException(status_code=400, detail="weights 必须是非空字典")

    from app.workflow.scoring import _valid_weights
    if not _valid_weights(weights):
        raise HTTPException(
            status_code=400,
            detail="权重非法：所有权重必须 > 0 且求和 ≈ 1",
        )

    if category:
        by_cat = dict(settings.SCORE_WEIGHTS_BY_CATEGORY)
        by_cat[category] = weights
        settings.SCORE_WEIGHTS_BY_CATEGORY = by_cat
    else:
        settings.SCORE_WEIGHTS_DEFAULT = weights

    return {
        "applied": True,
        "scope": f"category={category}" if category else "default",
        "weights": weights,
        "warning": "已写入进程内存，重启后回退 .env；历史分数重算请跑 scripts/recalc_scores.py",
    }
