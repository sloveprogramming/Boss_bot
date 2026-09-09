# 【小白导读】旧版最终决策节点：根据问卷/面试结果直接改候选人状态。
#   新流程改用 review.py 的 supervisor_decision，本节点保留兼容。
"""录用决策节点 — 最终录用/拒绝

合并了旧系统中：
1. agents/orchestrator 的 make_decision_node
2. backend/app/services/workflow.py 的录用决策逻辑
"""
import logging
from ..state import RecruitmentState
from ..utils import get_candidate
from app.database import async_session_factory
from app.services import notification_service

logger = logging.getLogger(__name__)


async def make_decision_node(state: RecruitmentState) -> dict:
    """做出录用/拒绝决策并发送通知"""
    candidate_id = state.get("candidate_id")
    score = state.get("match_score", 50)
    q_passed = state.get("questionnaire_passed", False)
    interview_decision = state.get("interview_decision", "")

    if interview_decision == "pass" or (score >= 60 and q_passed):
        final_status = "hired"
        notification_template = "offer"
    else:
        final_status = "rejected"
        notification_template = "rejection"

    async with async_session_factory() as db:
        try:
            candidate = await get_candidate(db, candidate_id)
            if candidate:
                candidate.status = final_status
                await db.flush()

            try:
                await notification_service.send(
                    candidate_id=candidate_id,
                    template=notification_template,
                    channel="email",
                    db=db,
                )
                logger.info("候选人 %s 决策通知已发送 (template=%s)", candidate_id, notification_template)
            except Exception as e:
                logger.error("候选人 %s 决策通知发送失败 (template=%s): %s", candidate_id, notification_template, e)

            await db.commit()
            logger.info("候选人 %s 录用决策完成: %s", candidate_id, final_status)
        except Exception as e:
            await db.rollback()
            logger.error("候选人 %s 决策更新失败: %s", candidate_id, e)
            return {
                "errors": [f"决策更新失败: {str(e)}"],
            }

    return {
        "status": final_status,
        "pipeline_stage": "decision",
        "interview_decision": "pass" if final_status == "hired" else "reject",
    }
