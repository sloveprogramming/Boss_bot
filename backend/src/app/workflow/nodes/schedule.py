# 【小白导读】面试三节点：schedule（AI 生成可选时段+发邀请）→
#   confirm（候选人选定时间后锁定）→ complete（标记完成，触发后续评审）。
"""面试排期节点 — 生成时间段/确认/完成

合并了旧系统中：
1. agents/orchestrator 的占位节点
2. backend/app/services/scheduler_svc.py 的功能
"""
import logging
from ..state import RecruitmentState
from app.config import settings
from app.database import async_session_factory
from app.services import scheduler, notification_service
from datetime import date, timedelta

logger = logging.getLogger(__name__)


async def schedule_interview_node(state: RecruitmentState) -> dict:
    """安排面试 — 生成可选时间段"""
    candidate_id = state.get("candidate_id")
    candidate_name = state.get("candidate_name", "候选人")
    position = state.get("position", "")

    if not candidate_id:
        return {"errors": ["缺少 candidate_id"]}

    async with async_session_factory() as db:
        try:
            today = date.today()
            slots = await scheduler.generate_slots(
                candidate_id=candidate_id,
                interviewers=["面试官"],
                duration_minutes=60,
                round_name="first",
                date_start=today.isoformat(),
                date_end=(today + timedelta(days=7)).isoformat(),
                work_start="09:00",
                work_end="18:00",
                exclude_dates=[],
                slot_count=3,
                db=db,
            )

            # 发送面试邀请通知
            try:
                proposed_text = "\n".join(
                    f"  {s['date']} {s['start_time']}-{s['end_time']}"
                    for s in slots.get("proposed_slots", [])
                )
                front_base = (settings.PUBLIC_BASE_URL or "http://localhost:5173").rstrip("/")
                await notification_service.send(
                    candidate_id=candidate_id,
                    template="interview_invite",
                    channel="email",
                    db=db,
                    extra={
                        "candidate_name": candidate_name,
                        "proposed_slots": proposed_text,
                        "selection_link": f"{front_base}/interview/{slots.get('interview_id', '')}",
                    },
                )
                logger.info(
                    "候选人 %s 面试邀请已发送 (interview_id=%s, 时段数=%d)",
                    candidate_id, slots.get("interview_id", 0),
                    len(slots.get("proposed_slots", [])),
                )
            except Exception as e:
                logger.error("候选人 %s 面试邀请通知发送失败: %s", candidate_id, e)

            await db.commit()
            logger.info(
                "候选人 %s 面试排期完成 (interview_id=%s, status=scheduled)",
                candidate_id, slots.get("interview_id", 0),
            )

            return {
                "interview_id": slots.get("interview_id", 0),
                "interview_status": "pending",
                "status": "scheduled",
                "pipeline_stage": "interview",
            }
        except Exception as e:
            await db.rollback()
            logger.error("候选人 %s 面试排期失败: %s", candidate_id, e)
            return {
                "errors": [f"面试排期失败: {str(e)}"],
            }


async def confirm_interview_node(state: RecruitmentState) -> dict:
    """确认面试时间（等待外部确认）"""
    # 该节点等待候选人/HR 确认时间，不主动做事
    return {
        "interview_status": "confirmed",
    }


async def complete_interview_node(state: RecruitmentState) -> dict:
    """完成面试（等待外部反馈）"""
    return {
        "interview_status": "completed",
        "status": "interviewed",
    }
