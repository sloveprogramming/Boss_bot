# ═══════════════════════════════════════════════════════════════
# 【小白导读】评分优化（闭环关键）：用"真实面试结果"反哺"简历评分权重"。
#   流程：收集历史样本（简历分 + 面试是否通过）→ 算各维度区分度
#   → 给出新权重建议 → HR 确认后应用 → 写入 scoring_iterations 留痕。
# ═══════════════════════════════════════════════════════════════
"""评分优化API — 根据面试结果的通过率给出简历评分权重建议，并记录迭代

数据口径：统一采样两类"面试结果标签"
  1. resume.match_analysis.interview_outcome（supervisor 决策回标 hired/rejected）
  2. interviews.feedback.decision（面试官反馈 pass/reject）
按候选人去重，优先保留带维度分（dimension_scores）的那条。

建议为可解释的启发式 v1（确定性、无黑盒），用于辅助人工调权，
迭代记录落 scoring_iterations 表；权重应用与 dashboard /scoring-weights 一致
只写 settings 进程内存（重启回退 .env）。
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.models import Resume, Interview, Candidate, User, UserRole, ScoringIteration
from app.dependencies import require_role, get_current_user
from app.workflow.scoring import _valid_weights

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/scoring",
    tags=["评分优化"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)

DIM_LABELS = {"skill": "专业能力", "experience": "经验匹配", "stability": "稳定性"}
_OUTCOMES_PASS = ("hired", "pass")


def _to_float(v) -> Optional[float]:
    """安全转 float，非法返回 None"""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bucket_of(score: float, bucket_size: int = 10) -> int:
    """分数 → 分桶下界（75.3 → 70）"""
    return int(score // bucket_size) * bucket_size


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


async def _collect_samples(db: AsyncSession) -> list[dict]:
    """聚合两类面试结果标签 → 统一样本列表（候选人去重，优先带维度分）"""
    samples: dict[int, dict] = {}

    # 1) supervisor 回标：resume.match_analysis.interview_outcome
    res = await db.execute(select(Resume).where(Resume.match_analysis.isnot(None)))
    resume_rows: list[tuple[int, dict, str]] = []
    cand_ids: set[int] = set()
    for r in res.scalars().all():
        ma = r.match_analysis or {}
        outcome = ma.get("interview_outcome")
        if outcome not in ("hired", "rejected"):
            continue
        resume_rows.append((r.candidate_id, ma, outcome))
        cand_ids.add(r.candidate_id)

    cand_map: dict[int, Candidate] = {}
    if cand_ids:
        cres = await db.execute(select(Candidate).where(Candidate.id.in_(cand_ids)))
        cand_map = {c.id: c for c in cres.scalars().all()}

    for cid, ma, outcome in resume_rows:
        cand = cand_map.get(cid)
        dims = ma.get("dimension_scores")
        samples[cid] = {
            "candidate_id": cid,
            "candidate_name": cand.name if cand else "",
            "position": cand.position if cand else "",
            "job_category": cand.job_category if cand else "",
            "outcome": "pass" if outcome in _OUTCOMES_PASS else "reject",
            "score": _to_float(ma.get("overall_score")),
            "dims": dims if isinstance(dims, dict) else {},
            "source": "回标",
        }

    # 2) 面试官反馈：interviews.feedback.decision（候选人未出现在回标采样中才补充）
    ires = await db.execute(
        select(Interview, Candidate)
        .join(Candidate, Interview.candidate_id == Candidate.id)
        .where(Interview.feedback.isnot(None))
    )
    for iv, cand in ires.all():
        fb = iv.feedback if isinstance(iv.feedback, dict) else {}
        decision = fb.get("decision")
        if decision not in ("pass", "reject"):
            continue
        if iv.candidate_id in samples:
            continue
        samples[iv.candidate_id] = {
            "candidate_id": iv.candidate_id,
            "candidate_name": cand.name if cand else "",
            "position": cand.position if cand else "",
            "job_category": cand.job_category if cand else "",
            "outcome": "pass" if decision == "pass" else "reject",
            "score": _to_float(cand.match_score),
            "dims": {},
            "source": "面试反馈",
        }

    return list(samples.values())


def _suggest_weights(
    current: dict, dim_stats: list[dict]
) -> tuple[Optional[dict], list[str]]:
    """v1 启发式：对通过/未通过两边样本数均≥3的维度，按区分度加/减权重后归一化"""
    reliable = [st for st in dim_stats if st["pass_n"] >= 3 and st["reject_n"] >= 3]
    if not reliable:
        return None, []

    base = {d: float(current.get(d, 0.0)) for d in current}
    adj: dict[str, float] = {}
    for st in reliable:
        gap = st["pass_avg"] - st["reject_avg"]  # 0-100 分制
        sign = 1.0 if gap > 0 else -1.0
        mag = min(abs(gap) / 60.0, 1.0)          # 60 分差距即满幅度
        adj[st["key"]] = sign * round(0.12 * mag, 3)

    if not adj:
        return None, []

    new_w = {d: max(0.05, base.get(d, 0.0) + adj.get(d, 0.0)) for d in base}
    total = sum(new_w.values())
    suggested = {d: round(v / total, 4) for d, v in new_w.items()}

    reasons = []
    for st in reliable:
        base_w = base.get(st["key"], 0.0)
        new_w_val = suggested.get(st["key"], base_w)
        reasons.append(
            f"{st['label']}：通过者均分 {st['pass_avg']:.0f} vs 未通过 {st['reject_avg']:.0f}，"
            f"区分度 {st['pass_avg'] - st['reject_avg']:+.0f} → 权重 {base_w:.2f} → {new_w_val:.2f}"
        )
    return suggested, reasons


@router.get("/insights")
async def get_insights(db: AsyncSession = Depends(get_db)):
    """通过率 + 分桶报表 + 各维度区分度 → 权重调整建议"""
    samples = await _collect_samples(db)
    current = dict(settings.SCORE_WEIGHTS_DEFAULT)
    dim_keys = list(current.keys())

    # 分桶聚合（复用 dashboard score-buckets 思路，样本 <30 只提示不调整）
    buckets: dict[int, list[int]] = {}
    for s in samples:
        if s["score"] is None:
            continue
        b = _bucket_of(s["score"])
        buckets.setdefault(b, [0, 0])
        buckets[b][0] += 1
        if s["outcome"] == "pass":
            buckets[b][1] += 1
    rows = []
    for b in sorted(buckets):
        total, passed = buckets[b]
        rows.append({
            "bucket": f"{b}-{b + 9}",
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
        })

    inversions = []
    for i in range(len(rows) - 1):
        lower, upper = rows[i], rows[i + 1]
        if lower["total"] >= 5 and upper["total"] >= 5 \
                and lower["pass_rate"] > upper["pass_rate"] + 10:
            inversions.append({
                "lower_bucket": lower["bucket"],
                "upper_bucket": upper["bucket"],
                "detail": f"{lower['bucket']} 通过率 {lower['pass_rate']}% "
                          f"高于 {upper['bucket']} 的 {upper['pass_rate']}%",
            })

    # 各维度区分度统计（有该维度分的样本才进入）
    acc = {d: {"pass_n": 0, "reject_n": 0, "pass_sum": 0.0, "reject_sum": 0.0}
           for d in dim_keys}
    for s in samples:
        dims = s["dims"]
        for d in dim_keys:
            v = _to_float(dims.get(d))
            if v is None:
                continue
            if s["outcome"] == "pass":
                acc[d]["pass_n"] += 1
                acc[d]["pass_sum"] += v
            else:
                acc[d]["reject_n"] += 1
                acc[d]["reject_sum"] += v

    dim_stats = []
    for d in dim_keys:
        st = acc[d]
        pass_avg = st["pass_sum"] / st["pass_n"] if st["pass_n"] else None
        reject_avg = st["reject_sum"] / st["reject_n"] if st["reject_n"] else None
        gap = (pass_avg - reject_avg) if (pass_avg is not None and reject_avg is not None) else None
        dim_stats.append({
            "key": d,
            "label": DIM_LABELS.get(d, d),
            "weight": round(float(current.get(d, 0)), 3),
            "pass_n": st["pass_n"],
            "reject_n": st["reject_n"],
            "pass_avg": round(pass_avg, 1) if pass_avg is not None else None,
            "reject_avg": round(reject_avg, 1) if reject_avg is not None else None,
            "gap": round(gap, 1) if gap is not None else None,
        })

    suggested, reasons = _suggest_weights(current, dim_stats)
    passed = sum(1 for s in samples if s["outcome"] == "pass")
    labeled_total = len(samples)

    suggestions = list(reasons)
    if labeled_total == 0:
        suggestions.append("暂无可用于评估的面试标签：请先在面试管理提交几条 pass/reject 反馈")
    elif labeled_total < 30:
        suggestions.append(
            f"标注样本仅 {labeled_total} 条（<30），统计不显著：建议值仅供参考，暂不建议应用"
        )
    elif suggested:
        suggestions.append("建议值来自各维度区分度启发式，建议人工复核后一键应用")
    else:
        suggestions.append("通过/未通过样本不足以支撑维度建议，继续积累标签")

    if inversions:
        suggestions.append(
            "检测到通过率倒挂：分数区分度存疑，建议检查对应分数段的维度分与权重"
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "labeled_total": labeled_total,
        "passed": passed,
        "pass_rate": round(passed / labeled_total * 100, 1) if labeled_total else None,
        "current_weights": {k: float(v) for k, v in current.items()},
        "suggested_weights": suggested,
        "dimension_stats": dim_stats,
        "buckets": rows,
        "inversions": inversions,
        "recent_samples": [
            {**s, "dims": {k: v for k, v in s["dims"].items() if k in dim_keys}}
            for s in samples[-20:]
        ],
        "suggestions": suggestions,
        "note": "数据来源：简历回标 interview_outcome + 面试反馈 decision；建议为启发式 v1。",
    }


class IterationApply(BaseModel):
    """应用一次权重迭代"""
    to_weights: dict
    category: str = ""
    note: str = ""


@router.post("/iterations")
async def apply_iteration(
    payload: IterationApply,
    db: AsyncSession = Depends(get_db),
    _: object = Depends(require_role([UserRole.ADMIN])),
    current_user: User = Depends(get_current_user),
):
    """应用权重为一次迭代：校验 → 落 scoring_iterations → 热更新 settings（内存）"""
    to_weights = payload.to_weights
    category = (payload.category or "").strip()
    note = (payload.note or "").strip()[:500]

    if not isinstance(to_weights, dict) or not to_weights:
        raise HTTPException(status_code=400, detail="to_weights 必须是非空字典")
    if not _valid_weights(to_weights):
        raise HTTPException(
            status_code=400,
            detail="权重非法：所有权重必须 > 0 且求和 ≈ 1",
        )

    # 记录应用前快照（category 覆盖未配置时退默认）
    if category:
        cur = dict(settings.SCORE_WEIGHTS_BY_CATEGORY.get(category, settings.SCORE_WEIGHTS_DEFAULT))
    else:
        cur = dict(settings.SCORE_WEIGHTS_DEFAULT)

    row = ScoringIteration(
        category=category,
        from_weights=cur,
        to_weights=to_weights,
        note=note,
        applied_by=current_user.username if current_user else "",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # 与 dashboard /scoring-weights 一致：写进程内存
    if category:
        by_cat = dict(settings.SCORE_WEIGHTS_BY_CATEGORY)
        by_cat[category] = to_weights
        settings.SCORE_WEIGHTS_BY_CATEGORY = by_cat
    else:
        settings.SCORE_WEIGHTS_DEFAULT = to_weights
    logger.info(
        "评分权重迭代已应用: category=%r from=%s to=%s by=%s",
        category, cur, to_weights, current_user.username if current_user else "?",
    )

    return {
        "id": row.id,
        "category": row.category,
        "from_weights": row.from_weights,
        "to_weights": row.to_weights,
        "note": row.note,
        "applied_by": row.applied_by,
        "created_at": row.created_at,
        "warning": "已写入进程内存，重启后回退 .env；历史分数重算请跑 scripts/recalc_scores.py",
    }


@router.get("/iterations")
async def list_iterations(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """评分权重迭代历史（倒序）"""
    res = await db.execute(
        select(ScoringIteration)
        .order_by(ScoringIteration.created_at.desc())
        .limit(limit)
    )
    rows = res.scalars().all()
    return [{
        "id": r.id,
        "category": r.category,
        "from_weights": r.from_weights,
        "to_weights": r.to_weights,
        "note": r.note,
        "applied_by": r.applied_by,
        "created_at": r.created_at,
    } for r in rows]
