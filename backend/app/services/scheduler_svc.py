"""面试排期引擎 — 基于约束求解的时间段生成 + 钉钉日历集成"""
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.candidate import Candidate
from app.models.interview import Interview, InterviewStatus
from app.services.calendar_svc import calendar_service
from app.config import settings
from datetime import date, time, datetime

class InterviewScheduler:
    """面试排期引擎：生成可选时间段、确认时间、提交反馈"""

    async def generate_slots(
        self,
        candidate_id: int, # 候选人ID
        interviewers: List[str], # 面试官列表
        duration_minutes: int, # 面试时长（分钟）
        round_name: str, # 面试轮次
        date_start: str, # 可选日期范围-开始
        date_end: str, # 可选日期范围-结束
        work_start: str, # 工作日开始时间
        work_end: str, # 工作日结束时间
        exclude_dates: List[str], # 排除日期列表
        db: AsyncSession,   # 数据库会话
        slot_count: int = 3, # 生成的时间段数量
        max_per_day: int = 3, # 每天最多安排几场面试
    ) -> dict:
        """生成可选的面试时间段并创建面试记录

        Args:
            candidate_id: 候选人ID
            interviewers: 面试官列表
            duration_minutes: 面试时长（分钟）
            round_name: 面试轮次
            date_start: 可选日期范围-开始
            date_end: 可选日期范围-结束
            work_start: 工作日开始时间
            work_end: 工作日结束时间
            exclude_dates: 排除日期列表
            db: 数据库会话
            slot_count: 生成的时间段数量
            max_per_day: 每天最多安排几场

        Returns:
            {"interview_id": int, "proposed_slots": [...]}
        """
        # 验证候选人存在性
        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        if not candidate:
            raise ValueError(f"候选人不存在: {candidate_id}")

        # 创建面试记录（初始状态为pending）
        interview = Interview(
            candidate_id=candidate_id,
            round=round_name,
            status=InterviewStatus.PENDING.value,
            interviewers=interviewers,
            duration_minutes=duration_minutes,
        )
        db.add(interview)
        await db.flush()

        # 核心排期算法：计算推荐时间段
        slots = self._compute_slots(
            date_start=date_start,
            date_end=date_end,
            work_start=work_start,
            work_end=work_end,
            duration_minutes=duration_minutes,
            exclude_dates=exclude_dates,
            max_per_day=max_per_day,
            slot_count=slot_count,
        )

        # 保存生成的时间段到面试记录
        interview.proposed_slots = slots
        await db.flush()

        return {
            "interview_id": interview.id,
            "proposed_slots": slots,
        }

    def _compute_slots(
        self,
        date_start: str, # 可选日期范围-开始
        date_end: str, # 可选日期范围-结束
        work_start: str, # 工作日开始时间
        work_end: str, # 工作日结束时间
        duration_minutes: int, # 面试时长（分钟）
        exclude_dates: List[str], # 排除日期列表
        max_per_day: int, # 每天最多安排几场面试
        slot_count: int, # 生成的时间段数量
    ) -> list:
        """核心排期算法：在工作日内均匀分布推荐时间段

        算法逻辑：
        1. 遍历日期范围内的每一天
        2. 跳过周末和排除日期
        3. 每个工作日生成均匀间隔的时间段
        4. 不超过每天最大场次和总数量限制
        """
        # 导入必要的时间模块
        start_date = date.fromisoformat(date_start) # 开始日期
        end_date = date.fromisoformat(date_end) # 结束日期
        ws_h, ws_m = map(int, work_start.split(":")) # 工作开始时间
        we_h, we_m = map(int, work_end.split(":")) # 工作结束时间
        work_start_time = time(ws_h, ws_m)   # 工作开始时间
        work_end_time = time(we_h, we_m)     # 工作结束时间
        exclude_set = set(exclude_dates) # 排除日期集合

        duration = timedelta(minutes=duration_minutes) # 面试时长（分钟）
        result = [] # 结果列表
        current_date = start_date # 当前日期，从开始日期开始

        while current_date <= end_date and len(result) < slot_count:
            date_str = current_date.isoformat()

            # 跳过排除日期和周日（weekday()=6是周日）
            if date_str not in exclude_set and current_date.weekday() < 6:
                day_start = datetime.combine(current_date, work_start_time)
                day_end = datetime.combine(current_date, work_end_time)
                available_minutes = int((day_end - day_start).total_seconds() / 60)

                # 确保可用时间足够一次面试
                if available_minutes >= duration_minutes:
                    slots_for_day = min(max_per_day, slot_count - len(result))
                    gap = available_minutes // slots_for_day  # 均匀间隔

                    for i in range(slots_for_day):
                        slot_start = day_start + timedelta(minutes=i * gap)
                        slot_end = slot_start + duration

                        if slot_end <= day_end and len(result) < slot_count:
                            result.append({
                                "date": date_str,
                                "start_time": slot_start.strftime("%H:%M"),
                                "end_time": slot_end.strftime("%H:%M"),
                            })

            current_date += timedelta(days=1)

        return result[:slot_count]

    async def confirm_slot(self, interview_id: int, selected_slot: dict,
                           location: Optional[str], meeting_link: Optional[str],
                           db: AsyncSession) -> Interview:
        """候选人确认选定的面试时间

        Args:
            interview_id: 面试记录ID
            selected_slot: 选中的时间段 {date, start_time, end_time}
            location: 面试地点
            meeting_link: 会议链接
            db: 数据库会话

        Returns:
            更新后的Interview对象
        """
        # 查找面试记录
        result = await db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise ValueError(f"面试记录不存在: {interview_id}")

        # 解析时间
        from datetime import datetime
        start_dt = datetime.fromisoformat(
            f"{selected_slot['date']}T{selected_slot['start_time']}"
        )
        end_dt = datetime.fromisoformat(
            f"{selected_slot['date']}T{selected_slot['end_time']}"
        )

        # 更新面试记录
        interview.confirmed_start = start_dt
        interview.confirmed_end = end_dt
        interview.status = InterviewStatus.CONFIRMED.value
        interview.location = location
        interview.meeting_link = meeting_link

        # 更新候选人状态
        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == interview.candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        if candidate:
            candidate.status = "scheduled"

        await db.flush()

        # 异步创建钉钉日历日程（不阻塞主流程）
        try:
            calendar_service.configure(
                settings.DINGTALK_APP_KEY,
                settings.DINGTALK_APP_SECRET,
            )
            await calendar_service.create_interview_event(
                candidate_name=candidate.name if candidate else "候选人",
                position=candidate.position if candidate else "",
                interview_time=start_dt,
                duration_minutes=interview.duration_minutes,
                interviewers=interview.interviewers or [],
                location=location,
                meeting_link=meeting_link,
            )
        except Exception as e:
            # 日历创建失败不影响主流程
            import logging
            logging.getLogger(__name__).warning(
                f"[日历集成] 创建日程失败（非关键）: {e}"
            )

        return interview

    async def submit_feedback(self, interview_id: int, feedback: dict,
                              db: AsyncSession) -> dict:
        """提交面试反馈并更新候选人状态

        Args:
            interview_id: 面试记录ID
            feedback: 反馈数据 {interviewer, rating, strengths, weaknesses, decision, detail}
            db: 数据库会话

        Returns:
            操作结果 {"status": "ok", "interview_id": ...}
        """
        # 查找面试记录
        result = await db.execute(
            select(Interview).where(Interview.id == interview_id)
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise ValueError(f"面试记录不存在: {interview_id}")

        # 保存反馈并更新状态
        interview.feedback = feedback
        interview.status = InterviewStatus.COMPLETED.value

        # 根据面试决策更新候选人状态
        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == interview.candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        if candidate:
            decision = feedback.get("decision", "")
            if decision == "pass":
                candidate.status = "interviewed"  # 通过→待录用决策
            elif decision == "reject":
                candidate.status = "rejected"     # 拒绝

        await db.flush()
        return {"status": "ok", "interview_id": interview_id}

    def check_conflicts(self, proposed_slots: list,
                        existing_interviews: list) -> list:
        """检查提议时间段是否与已有面试安排冲突

        Args:
            proposed_slots: 建议的时间段列表
            existing_interviews: 已有的面试记录列表

        Returns:
            冲突列表
        """
        conflicts = []
        for slot in proposed_slots:
            slot_start = f"{slot['date']}T{slot['start_time']}"
            slot_end = f"{slot['date']}T{slot['end_time']}"
            for existing in existing_interviews:
                if existing.get("confirmed_start") and existing.get("confirmed_end"):
                    es = existing["confirmed_start"].isoformat()[:16]
                    ee = existing["confirmed_end"].isoformat()[:16]
                    # 时间段重叠检测
                    if slot_start < ee and slot_end > es:
                        conflicts.append({
                            "slot": slot,
                            "conflict_with": existing.get("id"),
                        })
        return conflicts


# 全局单例
scheduler = InterviewScheduler()
