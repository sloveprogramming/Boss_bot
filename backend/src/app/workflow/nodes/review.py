# 【小白导读】面试评审：3 个评审 Agent 并行打分（技术/沟通/文化），
#   supervisor_decision_node 汇总三路意见做最终录用决策，并回写候选人状态、发通知。
#   route_to_reviewers 是 Send 并发分叉点。这是新版决策链路（旧版见 decision.py）。
"""面试评审节点 — 3 个 Agent 并行打分 + Supervisor 拍板

面试完成后拆成 3 路并行：
  技术评审（coding/架构） / 沟通评审（表达/逻辑） / 文化评审（价值观/融入）
最后 Supervisor 综合 3 路结果做录用决策。比一个人打完所有分更客观。
"""
import json
import re
import logging
from ..state import RecruitmentState
from ..utils import get_candidate
from app.database import async_session_factory
from app.agents import llm_client
from app.agents.prompts import (
    TECHNICAL_REVIEW_SYSTEM, TECHNICAL_REVIEW_PROMPT,
    COMMUNICATION_REVIEW_SYSTEM, COMMUNICATION_REVIEW_PROMPT,
    CULTURE_REVIEW_SYSTEM, CULTURE_REVIEW_PROMPT,
    SUPERVISOR_DECISION_SYSTEM, SUPERVISOR_DECISION_PROMPT,
)
from app.services import notification_service
from langgraph.types import Send

logger = logging.getLogger(__name__)


def route_to_reviewers(state: RecruitmentState):
    """把面试反馈同时发给 3 个评审 Agent"""
    return [
        Send("technical_review", state),
        Send("communication_review", state),
        Send("culture_review", state),
    ]


async def technical_review_node(state: RecruitmentState) -> dict:
    """技术能力评审"""
    feedback = _get_feedback(state)
    prompt = TECHNICAL_REVIEW_PROMPT.format(
        candidate_name=state.get("candidate_name", "候选人"),
        position=state.get("position", ""),
        feedback=feedback,
    )
    response = await llm_client.chat(
        system=TECHNICAL_REVIEW_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1024,
    )
    return {"technical_review": _safe_json(response)}


async def communication_review_node(state: RecruitmentState) -> dict:
    """沟通能力评审"""
    feedback = _get_feedback(state)
    prompt = COMMUNICATION_REVIEW_PROMPT.format(
        candidate_name=state.get("candidate_name", "候选人"),
        position=state.get("position", ""),
        feedback=feedback,
    )
    response = await llm_client.chat(
        system=COMMUNICATION_REVIEW_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1024,
    )
    return {"communication_review": _safe_json(response)}


async def culture_review_node(state: RecruitmentState) -> dict:
    """文化匹配度评审"""
    feedback = _get_feedback(state)
    prompt = CULTURE_REVIEW_PROMPT.format(
        candidate_name=state.get("candidate_name", "候选人"),
        position=state.get("position", ""),
        feedback=feedback,
    )
    response = await llm_client.chat(
        system=CULTURE_REVIEW_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=1024,
    )
    return {"culture_review": _safe_json(response)}


async def supervisor_decision_node(state: RecruitmentState) -> dict:
    """综合 3 路评审 → 最终录用决策 → 发通知"""
    tech = state.get("technical_review", {})
    comm = state.get("communication_review", {})
    culture = state.get("culture_review", {})

    prompt = SUPERVISOR_DECISION_PROMPT.format(
        technical_review=json.dumps(tech, ensure_ascii=False),
        communication_review=json.dumps(comm, ensure_ascii=False),
        culture_review=json.dumps(culture, ensure_ascii=False),
        candidate_name=state.get("candidate_name", "候选人"),
        position=state.get("position", ""),
        match_score=state.get("match_score", 50),
    )
    response = await llm_client.chat(
        system=SUPERVISOR_DECISION_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=1024,
    )
    decision_result = _safe_json(response)

    final_decision = decision_result.get("final_decision", "pending")
    candidate_id = state.get("candidate_id")

    if final_decision == "pass":
        final_status = "hired"
        template = "offer"
    elif final_decision == "reject":
        final_status = "rejected"
        template = "rejection"
    else:
        final_status = "pending"
        template = ""

    async with async_session_factory() as db:
        try:
            candidate = await get_candidate(db, candidate_id)
            if candidate:
                candidate.status = final_status
                await db.flush()

            # v2 数据闭环：把最终决策回写到评分记录，形成"分数 ↔ 结果"标签
            # （供分桶通过率报表 / 权重回归拟合使用）
            if candidate_id and final_status in ("hired", "rejected"):
                await _write_back_outcome(
                    db,
                    candidate_id=candidate_id,
                    outcome=final_status,
                    reason=decision_result.get("reason", ""),
                    confidence=decision_result.get("confidence", ""),
                )

            if template:
                try:
                    await notification_service.send(
                        candidate_id=candidate_id,
                        template=template,
                        channel="email",
                        db=db,
                    )
                    logger.info(
                        "候选人 %s 决策通知已发送 (template=%s)",
                        candidate_id, template,
                    )
                except Exception as e:
                    logger.error("候选人 %s 决策通知发送失败 (template=%s): %s", candidate_id, template, e)
            await db.commit()
            logger.info(
                "候选人 %s 录用决策完成: %s (confidence=%s)",
                candidate_id, final_decision,
                decision_result.get("confidence", ""),
            )
        except Exception as e:
            await db.rollback()
            logger.error("候选人 %s 决策更新失败: %s", candidate_id, e)
            return {"errors": [f"决策更新失败: {str(e)}"]}

    return {
        "status": final_status,
        "pipeline_stage": "decision",
        "interview_decision": final_decision,
        "decision_reason": decision_result.get("reason", ""),
        "decision_confidence": decision_result.get("confidence", ""),
        "risk_warning": decision_result.get("risk_warning", ""),
        "review_results": {
            "technical": tech,
            "communication": comm,
            "culture": culture,
            "supervisor": decision_result,
        },
        "errors": [],
    }


# -- 工具函数 --

async def _write_back_outcome(db, candidate_id: int, outcome: str,
                              reason: str = "", confidence: str = "") -> None:
    """把最终决策回写到该候选人最新简历的 match_analysis JSON

    字段：interview_outcome（hired/rejected）、outcome_at、decision_reason、
    decision_confidence。这是评分体系数据闭环的"标签生产"环节：
    分桶通过率报表和权重回归拟合都消费这里的数据。
    """
    from datetime import datetime
    from sqlalchemy import select
    from app.models import Resume

    result = await db.execute(
        select(Resume)
        .where(Resume.candidate_id == candidate_id)
        .order_by(Resume.created_at.desc())
        .limit(1)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        logger.warning("候选人 %s 回流失败：找不到简历记录", candidate_id)
        return

    analysis = dict(resume.match_analysis or {})
    analysis["interview_outcome"] = outcome
    analysis["outcome_at"] = datetime.utcnow().isoformat()
    if reason:
        analysis["decision_reason"] = reason
    if confidence:
        analysis["decision_confidence"] = confidence
    resume.match_analysis = analysis
    await db.flush()
    logger.info(
        "候选人 %s 评分标签已回流 (outcome=%s, match_score=%s)",
        candidate_id, outcome, analysis.get("overall_score"),
    )


def _get_feedback(state: RecruitmentState) -> str:
    """从 State 里取面试反馈文本"""
    fb = state.get("interview_feedback", "")
    if fb:
        return json.dumps(fb, ensure_ascii=False) if isinstance(fb, dict) else str(fb)

    messages = state.get("messages", [])
    for msg in reversed(messages):
        content = getattr(msg, "content", "")
        if content and len(content) > 20:
            return content
    return "未提供详细面试反馈"


def _safe_json(response: str) -> dict:
    """解析 LLM 返回的 JSON，格式不对就正则兜底"""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        return json.loads(json_match.group()) if json_match else {}
