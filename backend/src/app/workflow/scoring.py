"""综合评分计算（v2 评分体系第一期）

设计原则：
  1. LLM 只产维度分（客观证据），总分由本模块按权重计算（业务策略）
  2. 权重从 config 读取，可按岗位类别覆盖，改权重无需重跑 LLM
  3. 维度分缺失时不静默给 50 分：
     - 部分缺失 → 用已有维度按重归一化权重计算，标记 partial
     - 全部缺失 → 不产分，由调用方决定是否降级用 LLM 重评分
     凡是缺失场景 complete=False，上流路由不应自动分流，转人工复核
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# 维度名与子 Agent 输出字段的对应关系
DIMENSION_FIELDS = {
    "skill": "skill_match_score",        # 来自技能 Agent
    "experience": "experience_score",    # 来自经验 Agent
    "stability": "stability_score",      # 来自经验 Agent
}

# 最后一道防线：config 里的默认权重本身非法时，用这份硬编码值兜底
_SAFE_DEFAULT_WEIGHTS = {"skill": 0.4, "experience": 0.4, "stability": 0.2}


def get_weights(category: Optional[str] = None) -> dict:
    """获取指定岗位类别的评分权重

    优先级：SCORE_WEIGHTS_BY_CATEGORY[category] > SCORE_WEIGHTS_DEFAULT
    合法性校验：权重必须全部 > 0 且求和 ≈ 1（容差 0.01），
    非法时回退硬编码安全默认值（而非 config 里可能同样非法的默认值）
    """
    weights = dict(settings.SCORE_WEIGHTS_DEFAULT)

    if category and settings.SCORE_WEIGHTS_BY_CATEGORY:
        override = settings.SCORE_WEIGHTS_BY_CATEGORY.get(category)
        if override:
            weights.update(override)

    if not _valid_weights(weights):
        logger.warning("岗位 %s 的权重配置非法（%s），回退安全默认权重", category, weights)
        weights = dict(_SAFE_DEFAULT_WEIGHTS)

    return weights


def _valid_weights(weights: dict) -> bool:
    if not weights:
        return False
    try:
        values = [float(v) for v in weights.values()]
    except (TypeError, ValueError):
        return False
    if not values or any(v <= 0 for v in values):
        return False
    return abs(sum(values) - 1.0) <= 0.01


def _to_score(value) -> Optional[float]:
    """把子 Agent 给的分转成 0-100 的 float，取不到/非法返回 None"""
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(100.0, score))


def extract_dimension_scores(
    skills_analysis: dict, experience_analysis: dict
) -> dict:
    """从子 Agent 结果中提取三个维度分，缺失为 None"""
    raw = {
        "skill": skills_analysis.get("skill_match_score"),
        "experience": experience_analysis.get("experience_score"),
        "stability": experience_analysis.get("stability_score"),
    }
    return {dim: _to_score(val) for dim, val in raw.items()}


def compute_overall(
    dimension_scores: dict, weights: dict
) -> dict:
    """按权重计算综合分

    Returns:
        {
            "overall": float | None,     # 综合分；全部维度缺失时为 None
            "source": str,               # weighted / weighted_partial / llm_fallback / none
            "complete": bool,            # 三个维度是否齐全
            "missing": list,             # 缺失的维度名
            "weights_used": dict,        # 实际使用的权重（partial 时为重归一化后）
        }
    """
    scores = {}
    for dim, weight in weights.items():
        score = dimension_scores.get(dim)
        if score is not None:
            scores[dim] = (score, float(weight))

    missing = [dim for dim in weights if dim not in scores]

    if not scores:
        return {
            "overall": None,
            "source": "none",
            "complete": False,
            "missing": list(weights.keys()),
            "weights_used": dict(weights),
        }

    if missing:
        # 部分缺失：按剩余维度重归一化权重（比如缺 stability 时 0.4/0.4 → 0.5/0.5）
        total_w = sum(w for _, w in scores.values())
        renormalized = {dim: w / total_w for dim, w in weights.items() if dim in scores}
        overall = sum(s * renormalized[dim] for dim, (s, _) in scores.items())
        return {
            "overall": round(overall, 1),
            "source": "weighted_partial",
            "complete": False,
            "missing": missing,
            "weights_used": {k: round(v, 4) for k, v in renormalized.items()},
        }

    overall = sum(s * w for s, w in scores.values())
    return {
        "overall": round(overall, 1),
        "source": "weighted",
        "complete": True,
        "missing": [],
        "weights_used": {k: float(v) for k, v in weights.items()},
    }
