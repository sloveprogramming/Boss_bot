"""权重建议拟合 — 用"评分维度分 + 面试结果"标签拟合更优权重（只提议，不生效）

原理：以"是否录用"为标签（hired=1, rejected=0），对三个维度分做
逻辑回归，把拟合出的系数归一化成权重建议。样本量是硬前提：
  <30 条        → 拒绝拟合，输出"继续积累标签"
  30~99 条      → 可以拟合，输出但标记"置信度低"
  >=100 条      → 正常拟合
建议通过 dashboard 的 /api/dashboard/scoring-weights 接口人工确认后热生效，
历史分数用 scripts/recalc_scores.py 重算。本脚本永远不写任何配置。

使用方法（项目根目录，用 boos_bot venv 的 python）:
    python backend/scripts/fit_weights.py
    python backend/scripts/fit_weights.py --category python
"""
import argparse
import asyncio
import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select

from app.database import async_session_factory
from app.workflow.scoring import DIMENSION_FIELDS


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def fit_logistic(samples: list[tuple[float, float, float, int]],
                 epochs: int = 3000, lr: float = 0.001):
    """纯 Python 逻辑回归（3 特征 + 截距），批量梯度下降 + L2 正则

    samples: [(skill, experience, stability, label), ...] 分数已缩放到 0-1
    返回: ([w_skill, w_exp, w_stab], b)
    """
    n = len(samples)
    w = [0.0, 0.0, 0.0]
    b = 0.0
    l2 = 0.01  # 正则化：小样本防过拟合
    for _ in range(epochs):
        gw = [0.0, 0.0, 0.0]
        gb = 0.0
        for x1, x2, x3, y in samples:
            p = _sigmoid(w[0] * x1 + w[1] * x2 + w[2] * x3 + b)
            err = p - y
            gw[0] += err * x1
            gw[1] += err * x2
            gw[2] += err * x3
            gb += err
        w = [wi - lr * (gi / n + l2 * wi) for wi, gi in zip(w, gw)]
        b -= lr * gb / n
    return w, b


def auc(samples, w, b) -> float:
    """AUC：衡量权重对"录用/拒绝"的区分度（0.5=没区分度，1=完美）"""
    pos = [(w[0] * s[0] + w[1] * s[1] + w[2] * s[2] + b, s) for s in samples if s[3] == 1]
    neg = [(w[0] * s[0] + w[1] * s[1] + w[2] * s[2] + b, s) for s in samples if s[3] == 0]
    if not pos or not neg:
        return 0.5
    wins = ties = 0
    for sp, _ in pos:
        for sn, _ in neg:
            if sp > sn:
                wins += 1
            elif sp == sn:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def _current_weights_auc(samples) -> float:
    """用当前 config 权重算 AUC（不含截距，评区分度用）"""
    from app.config import settings
    cw = settings.SCORE_WEIGHTS_DEFAULT
    pos = [sum(cw[k] * s[i] for i, k in enumerate(["skill", "experience", "stability"]))
           for s in samples if s[3] == 1]
    neg = [sum(cw[k] * s[i] for i, k in enumerate(["skill", "experience", "stability"]))
           for s in samples if s[3] == 0]
    if not pos or not neg:
        return 0.5
    wins = ties = 0
    for sp in pos:
        for sn in neg:
            if sp > sn:
                wins += 1
            elif sp == sn:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


async def collect_samples(category: str | None):
    from app.models import Resume
    async with async_session_factory() as db:
        result = await db.execute(select(Resume).where(Resume.match_analysis.isnot(None)))
        resumes = result.scalars().all()

    samples = []
    skipped = 0
    for resume in resumes:
        ma = resume.match_analysis or {}
        if ma.get("interview_outcome") not in ("hired", "rejected"):
            continue
        if category and resume.match_analysis.get("job_category", ma.get("job_category")) != category:
            # job_category 存在 candidate 表上，简单起见只过滤 match_analysis 里带的
            pass
        dims = ma.get("dimension_scores") or {}
        vals = [dims.get(k) for k in ("skill", "experience", "stability")]
        if any(v is None for v in vals):
            skipped += 1
            continue
        label = 1 if ma["interview_outcome"] == "hired" else 0
        # 分数缩放到 0-1，量纲统一
        samples.append((vals[0] / 100.0, vals[1] / 100.0, vals[2] / 100.0, label))
    return samples, skipped


async def main(category: str | None, seed: int):
    samples, skipped = await collect_samples(category)
    n = len(samples)
    print(f"带标签样本: {n} 条（维度分缺失跳过 {skipped} 条）")

    if n < 30:
        print("样本 < 30：统计不显著，拒绝拟合。建议继续积累标签后再跑。")
        return

    random.Random(seed).shuffle(samples)
    # 80/20 分割：训练拟合 / 验证 AUC
    split = int(n * 0.8)
    train, valid = samples[:split], samples[split:]

    w, b = fit_logistic(train)

    # 归一化成权重（系数可能为负 → 钳位到 0.05 下限并重新归一）
    raw = [max(0.05, x) for x in w]
    total = sum(raw)
    suggested = {k: round(v / total, 3) for k, v in zip(["skill", "experience", "stability"], raw)}
    ssum = sum(suggested.values())
    suggested = {k: round(v / ssum, 3) for k, v in suggested.items()}

    train_auc = auc(train, w, b)
    valid_auc = auc(valid, w, b) if valid else 0.5
    cur_auc = _current_weights_auc(valid) if valid else 0.5

    confidence = "高" if n >= 100 else "低（样本 30~99，仅供参考）"
    print(json.dumps({
        "suggested_weights": suggested,
        "current_weights": settings_weights(),
        "train_auc": round(train_auc, 3),
        "valid_auc": round(valid_auc, 3),
        "current_weights_valid_auc": round(cur_auc, 3),
        "sample_count": n,
        "confidence": confidence,
        "verdict": _verdict(cur_auc, valid_auc),
    }, ensure_ascii=False, indent=2))


def settings_weights():
    from app.config import settings
    return settings.SCORE_WEIGHTS_DEFAULT


def _verdict(cur_auc: float, new_auc: float) -> str:
    if new_auc < 0.55:
        return "拟合 AUC 接近随机（<0.55）：维度分与录用结果基本无关，问题可能不在权重，先检查评分锚点"
    if new_auc > cur_auc + 0.05:
        return f"建议权重 AUC({new_auc:.3f}) 明显优于当前({cur_auc:.3f})，可考虑采纳（shadow 验证后人工确认）"
    if cur_auc > new_auc + 0.05:
        return "当前权重更好，无需调整"
    return "两者差异不大（<0.05），不值得动"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="用面试结果标签拟合权重建议")
    parser.add_argument("--category", default=None, help="暂不支持按类别（类别标签需落库后开放）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（保证可复现）")
    args = parser.parse_args()
    asyncio.run(main(args.category, args.seed))
