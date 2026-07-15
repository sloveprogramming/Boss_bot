"""定时任务 — 问卷自动催填 / 面试提醒 / 人才池周期归档"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.candidate import Candidate
from app.models.questionnaire import Questionnaire
from app.models.interview import Interview, InterviewStatus
from app.models.talent_pool import TalentPool, TalentPoolStatus
from app.services.notification import notification_service

logger = logging.getLogger(__name__)


class ScheduledTasks:
    """定时任务调度器 — 后台自动执行周期性维护任务"""
    # 初始化定时任务调度器
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory  # 数据库会话工厂
        self._running = False                   # 运行状态标志
    # 启动定时任务循环
    async def start(self, interval_seconds: int = 300):
        """启动定时任务循环（默认每5分钟检查一次）"""
        self._running = True
        logger.info(f"[ScheduledTasks] 启动定时任务循环，间隔 {interval_seconds}s")

        while self._running:
            try:
                async with self.session_factory() as db:
                    await self._check_interview_reminders(db)      # 检查面试提醒
                    await self._check_talent_pool_reactivation(db) # 检查人才池归档
            except Exception as e:
                logger.error(f"[ScheduledTasks] 执行异常: {e}")

            await asyncio.sleep(interval_seconds)
    # 停止定时任务循环
    def stop(self):
        """停止定时任务"""
        self._running = False

    # ========== 面试自动提醒 ==========
    # 检查即将到来的面试：提前约24小时发送提醒给候选人
    async def _check_interview_reminders(self, db: AsyncSession):
        """检查即将到来的面试：提前约24小时发送提醒给候选人

        仅发送一次（reminder_sent=0 → 1）
        """
        now = datetime.utcnow()
        target_time = now + timedelta(hours=24)

        # 查找已确认、未发送提醒、有开始时间的面试
        result = await db.execute(
            select(Interview)
            .where(Interview.status == InterviewStatus.CONFIRMED.value)
            .where(Interview.confirmed_start.isnot(None))
            .where(Interview.reminder_sent < 1)
        )
        interviews = result.scalars().all()

        for iv in interviews:
            if not iv.confirmed_start:
                continue

            # 检查是否正好在24小时（允许±1小时误差）
            time_diff = iv.confirmed_start - now
            if timedelta(hours=23) <= time_diff <= timedelta(hours=25):
                try:
                    cand_result = await db.execute(
                        select(Candidate).where(Candidate.id == iv.candidate_id)
                    )
                    candidate = cand_result.scalar_one_or_none()
                    if not candidate:
                        continue

                    location_or_link = iv.location or iv.meeting_link or "待定"

                    await notification_service.send(
                        candidate_id=iv.candidate_id,
                        template="interview_reminder",
                        channel="email",
                        db=db,
                        recipient=candidate.email,
                        extra={
                            "candidate_name": candidate.name,
                            "position": candidate.position,
                            "interview_time": iv.confirmed_start.strftime("%Y-%m-%d %H:%M"),
                            "location_or_link": location_or_link,
                        },
                    )

                    iv.reminder_sent = 1
                    logger.info(
                        f"[面试提醒] 已发送面试提醒给{candidate.name} (面试#{iv.id}，时间: {iv.confirmed_start})"
                    )
                except Exception as e:
                    logger.error(f"[面试提醒] 失败 interview#{iv.id}: {e}")

        await db.flush()

    # ========== 人才池周期激活 ==========
    # 定期检查人才池：入池超过3个月的记录自动归档
    async def _check_talent_pool_reactivation(self, db: AsyncSession):
        """定期检查人才池：入池超过3个月的记录自动归档"""
        now = datetime.utcnow()
        three_months_ago = now - timedelta(days=90)

        result = await db.execute(
            select(TalentPool)
            .where(TalentPool.status == TalentPoolStatus.ACTIVE.value)
            .where(TalentPool.created_at <= three_months_ago)
        )
        old_entries = result.scalars().all()

        for entry in old_entries:
            entry.status = TalentPoolStatus.ARCHIVED.value
            logger.info(
                f"[人才池归档] talent_pool#{entry.id} (candidate#{entry.candidate_id}) "
                f"入池超3个月，已自动归档"
            )

        await db.flush()


# 全局定时任务实例（在main.py中初始化）
scheduled_tasks: ScheduledTasks = None
"""全局定时任务实例，在main.py中初始化"""
