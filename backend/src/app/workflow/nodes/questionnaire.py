# 【小白导读】问卷通道三节点：generate（AI 出题入库+发邮件）→
#   wait（轮询数据库等候选人提交）→ score（AI 批卷、写分数、决定是否及格）。
"""问卷节点 """
import logging
from ..state import RecruitmentState
from ..utils import candidate_session
from app.database import async_session_factory
from app.services import questionnaire_service, QUESTIONNAIRE_LINK
from app.config import settings
from app.models import CandidateStatus

logger = logging.getLogger(__name__)


async def generate_questionnaire_node(state: RecruitmentState) -> dict:
    """生成并发送问卷（固定链接）给候选人"""
    candidate_id = state.get("candidate_id")
    match_score = state.get("match_score", 0)

    if not candidate_id:
        return {"errors": ["缺少 candidate_id"]}

    if match_score >= settings.SCORE_THRESHOLD_FAST_TRACK:
        async with candidate_session(candidate_id, suppress_errors=True) as (db, candidate):
            if candidate:
                candidate.status = CandidateStatus.INTERVIEW_SCHEDULED.value
        logger.info("候选人 %s 走快速通道（score=%.1f），跳过问卷直接排期", candidate_id, match_score)
        return {
            "questionnaire_status": "skipped",
            "status": "q_done",
            "pipeline_stage": "questionnaire",
            "questionnaire_passed": True,
            "notification": "快速通道：直接进入面试排期",
        }

    async with async_session_factory() as db:
        try:
            q = await questionnaire_service.send_questionnaire_link(
                candidate_id=candidate_id,
                channel="email",
                db=db,
            )
            await db.commit()
            logger.info("候选人 %s 问卷已发送 (questionnaire_id=%s)", candidate_id, q.id)

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
            logger.error("候选人 %s 问卷发送失败: %s", candidate_id, e)
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
