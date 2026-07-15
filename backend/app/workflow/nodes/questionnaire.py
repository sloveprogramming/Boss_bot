"""问卷节点 — 简化版：仅发送固定链接

不再生成题目、评分、催填。发送固定问卷链接后直接标记为通过。
"""
from ..state import RecruitmentState
from app.database import async_session_factory
from app.services.questionnaire_svc import questionnaire_service, QUESTIONNAIRE_LINK
from app.config import settings
from sqlalchemy import select


async def generate_questionnaire_node(state: RecruitmentState) -> dict:
    """生成并发送问卷（固定链接）给候选人"""
    candidate_id = state.get("candidate_id")
    match_score = state.get("match_score", 0)

    if not candidate_id:
        return {"errors": ["缺少 candidate_id"]}

    # 快速通道 (>=80): 跳过问卷直接面试
    if match_score >= settings.SCORE_THRESHOLD_FAST_TRACK:
        async with async_session_factory() as db:
            try:
                from app.models.candidate import Candidate
                from app.models.candidate import CandidateStatus
                result = await db.execute(
                    select(Candidate).where(Candidate.id == candidate_id)
                )
                candidate = result.scalar_one_or_none()
                if candidate:
                    candidate.status = CandidateStatus.INTERVIEW_SCHEDULED.value
                    await db.commit()
            except Exception:
                await db.rollback()
        return {
            "questionnaire_status": "skipped",
            "status": "q_done",
            "pipeline_stage": "questionnaire",
            "questionnaire_passed": True,
            "notification": "快速通道：直接进入面试排期",
        }

    # 普通通道：发送固定链接
    async with async_session_factory() as db:
        try:
            q = await questionnaire_service.send_questionnaire_link(
                candidate_id=candidate_id,
                channel="email",
                db=db,
            )
            await db.commit()

            return {
                "questionnaire_id": q.id,
                "questionnaire_status": "sent",
                "status": "q_sent",
                "pipeline_stage": "questionnaire",
                "questionnaire_passed": True,
                "questionnaire_score": 100,
            }
        except Exception as e:
            await db.rollback()
            return {
                "questionnaire_status": "draft",
                "errors": [f"问卷发送失败: {str(e)}"],
            }


async def wait_questionnaire_node(state: RecruitmentState) -> dict:
    """等待问卷完成（外部问卷不追踪完成状态，直接标记完成）"""
    return {
        "questionnaire_status": "completed",
    }


async def score_questionnaire_node(state: RecruitmentState) -> dict:
    """问卷评分（固定链接无评分，默认通过）"""
    return {
        "questionnaire_score": 100,
        "questionnaire_passed": True,
        "questionnaire_status": "completed",
        "status": "q_done",
        "pipeline_stage": "questionnaire",
    }
