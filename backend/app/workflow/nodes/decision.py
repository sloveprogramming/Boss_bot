"""录用决策节点 — 最终录用/拒绝

合并了旧系统中：
1. agents/orchestrator 的 make_decision_node
2. backend/app/services/workflow.py 的录用决策逻辑
"""
from ..state import RecruitmentState
from app.database import async_session_factory
from app.services.notification import notification_service


async def make_decision_node(state: RecruitmentState) -> dict:
    """做出录用/拒绝决策并发送通知"""
    candidate_id = state.get("candidate_id")
    score = state.get("match_score", 50)
    q_passed = state.get("questionnaire_passed", False)
    interview_decision = state.get("interview_decision", "")

    # 决策逻辑
    if interview_decision == "pass" or (score >= 60 and q_passed):
        final_status = "hired"
        notification_template = "offer"
    else:
        final_status = "rejected"
        notification_template = "rejection"

    # 写入数据库 + 发送通知
    async with async_session_factory() as db:
        try:
            from sqlalchemy import select
            from app.models.candidate import Candidate

            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if candidate:
                candidate.status = final_status
                await db.flush()

            # 发送通知
            try:
                await notification_service.send(
                    candidate_id=candidate_id,
                    template=notification_template,
                    channel="email",
                    db=db,
                )
            except Exception:
                pass

            await db.commit()
        except Exception as e:
            await db.rollback()
            return {
                "errors": [f"决策更新失败: {str(e)}"],
            }

    return {
        "status": final_status,
        "pipeline_stage": "decision",
        "interview_decision": "pass" if final_status == "hired" else "reject",
    }
