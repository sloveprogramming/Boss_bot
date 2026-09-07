"""面试排期API — 时间段生成、确认、反馈提交"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Interview, Candidate, UserRole, User
from app.dependencies import (
    require_role, get_current_user,
    ensure_candidate_visible, ensure_interview_visible, interview_scope_cond,
)
from app.services import scheduler
from app.schemas import (
    InterviewSlotRequest, InterviewSlotResponse,
    SlotConfirm, InterviewResponse, InterviewFeedback,
    ManualScheduleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/interviews",
    tags=["面试管理"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR, UserRole.INTERVIEWER]))],
)


@router.post("/generate-slots", response_model=InterviewSlotResponse)
async def generate_slots(
    data: InterviewSlotRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """根据约束条件生成可选的面试时间段（HR/admin；interviewer 不可排期）"""
    await ensure_candidate_visible(db, current_user, data.candidate_id)
    try:
        result = await scheduler.generate_slots(
            candidate_id=data.candidate_id,
            interviewers=data.interviewers,
            duration_minutes=data.duration_minutes,
            round_name=data.round,
            date_start=data.date_range_start,
            date_end=data.date_range_end,
            work_start=data.working_hours_start,
            work_end=data.working_hours_end,
            exclude_dates=data.exclude_dates,
            slot_count=3,
            db=db,
        )
        logger.info(
            "生成面试时段: candidate_id=%s round=%s 时段数=%d",
            data.candidate_id, data.round, len(result["proposed_slots"]),
        )
        return InterviewSlotResponse(
            interview_id=result["interview_id"],
            proposed_slots=result["proposed_slots"],
        )
    except ValueError as e:
        logger.warning("生成面试时段失败: candidate_id=%s error=%s", data.candidate_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm-slot", response_model=InterviewResponse)
async def confirm_slot(
    data: SlotConfirm,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """候选人确认选定的面试时间（须为可见面试）"""
    await ensure_interview_visible(db, current_user, data.interview_id)
    try:
        interview = await scheduler.confirm_slot(
            interview_id=data.interview_id,
            selected_slot=data.selected_slot.model_dump(),
            location=data.location,
            meeting_link=data.meeting_link,
            db=db,
        )
        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == interview.candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        logger.info(
            "面试时段已确认: interview_id=%s candidate_id=%s 时间=%s",
            interview.id, interview.candidate_id,
            interview.confirmed_start,
        )
        return InterviewResponse(
            id=interview.id,
            candidate_id=interview.candidate_id,
            candidate_name=candidate.name if candidate else "",
            round=interview.round,
            status=interview.status,
            interviewers=interview.interviewers or [],
            confirmed_start=interview.confirmed_start,
            confirmed_end=interview.confirmed_end,
            location=interview.location,
            meeting_link=interview.meeting_link,
        )
    except ValueError as e:
        logger.warning("确认面试时段失败: interview_id=%s error=%s", data.interview_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/manual", response_model=InterviewResponse)
async def manual_schedule(
    data: ManualScheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """HR 手动指定面试时间直接排期（不依赖 AI 生成时段）"""
    await ensure_candidate_visible(db, current_user, data.candidate_id)
    try:
        interview = await scheduler.schedule_manual(
            candidate_id=data.candidate_id,
            interviewers=data.interviewers,
            round_name=data.round,
            date=data.date,
            start_time=data.start_time,
            end_time=data.end_time,
            location=data.location,
            meeting_link=data.meeting_link,
            db=db,
        )
        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == interview.candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        logger.info(
            "手动排期面试: interview_id=%s candidate_id=%s 时间=%s %s-%s",
            interview.id, interview.candidate_id,
            data.date, data.start_time, data.end_time,
        )
        return InterviewResponse(
            id=interview.id,
            candidate_id=interview.candidate_id,
            candidate_name=candidate.name if candidate else "",
            round=interview.round,
            status=interview.status,
            interviewers=interview.interviewers or [],
            confirmed_start=interview.confirmed_start,
            confirmed_end=interview.confirmed_end,
            location=interview.location,
            meeting_link=interview.meeting_link,
        )
    except ValueError as e:
        logger.warning("手动排期面试失败: candidate_id=%s error=%s", data.candidate_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/feedback")
async def submit_feedback(
    data: InterviewFeedback,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交面试反馈（面试官填写；仅本人参与/HR 名下面试可提交）"""
    await ensure_interview_visible(db, current_user, data.interview_id)
    try:
        result = await scheduler.submit_feedback(
            interview_id=data.interview_id,
            feedback=data.model_dump(),
            db=db,
        )
        logger.info("提交面试反馈: interview_id=%s", data.interview_id)
        return result
    except ValueError as e:
        logger.warning("提交面试反馈失败: interview_id=%s error=%s", data.interview_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/candidate/{candidate_id}")
async def get_candidate_interviews(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定候选人的所有面试记录

    - HR：仅候选人归属自己的面试
    - interviewer：仅本人作为面试官参与的场次（看不到同候选人其他面试官的场次）
    """
    await ensure_candidate_visible(db, current_user, candidate_id)
    query = select(Interview).where(Interview.candidate_id == candidate_id)
    if current_user.role == UserRole.INTERVIEWER.value:
        query = query.where(
            func.json_contains(
                Interview.interviewers,
                func.json_quote(current_user.username),
            )
        )
    query = query.order_by(Interview.created_at.desc())
    result = await db.execute(query)
    interviews = result.scalars().all()

    cand_result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = cand_result.scalar_one_or_none()

    return [
        InterviewResponse(
            id=i.id,
            candidate_id=i.candidate_id,
            candidate_name=candidate.name if candidate else "",
            round=i.round,
            status=i.status,
            interviewers=i.interviewers or [],
            proposed_slots=i.proposed_slots,
            confirmed_start=i.confirmed_start,
            confirmed_end=i.confirmed_end,
            location=i.location,
            meeting_link=i.meeting_link,
            feedback=i.feedback,
            ai_summary=i.ai_summary,
        )
        for i in interviews
    ]


@router.get("/calendar")
async def get_calendar_interviews(
    start: str = Query(..., description="开始日期 YYYY-MM-DD（含）"),
    end: str = Query(..., description="结束日期 YYYY-MM-DD（含）"),
    candidate_id: Optional[int] = Query(None, description="按候选人过滤（缺省全部）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """月历数据：指定日期范围内已确认时间的面试 + 待确认（未排时间）的面试

    数据范围：HR 仅看自己名下候选人的面试；interviewer 仅看本人在名单的场次。
    必须声明在 GET /{interview_id} 之前，避免 'calendar' 被当作 int 路径参数。
    """
    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)  # 含 end 当天
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式须为 YYYY-MM-DD")

    scope_cond = interview_scope_cond(current_user)

    filters = [
        Interview.confirmed_start.isnot(None),
        Interview.confirmed_start >= start_dt,
        Interview.confirmed_start < end_dt,
    ]
    if scope_cond is not None:
        filters.append(scope_cond)
    if candidate_id is not None:
        filters.append(Interview.candidate_id == candidate_id)

    result = await db.execute(
        select(Interview, Candidate)
        .join(Candidate, Interview.candidate_id == Candidate.id)
        .where(*filters)
        .order_by(Interview.confirmed_start)
    )
    items = []
    for interview, cand in result.all():
        fb = interview.feedback if isinstance(interview.feedback, dict) else {}
        items.append({
            "id": interview.id,
            "candidate_id": interview.candidate_id,
            "candidate_name": cand.name if cand else "",
            "position": cand.position if cand else "",
            "round": interview.round,
            "status": interview.status,
            "confirmed_start": interview.confirmed_start,
            "confirmed_end": interview.confirmed_end,
            "location": interview.location,
            "meeting_link": interview.meeting_link,
            "interviewers": interview.interviewers or [],
            "ai_summary": interview.ai_summary,
            "feedback": fb or None,
            "has_feedback": bool(fb.get("decision")),
        })

    # 待确认/未排期：无 confirmed_start 但已有拟议时段（可能在流程中途）
    u_filters = [
        Interview.confirmed_start.is_(None),
        Interview.status.in_(["pending", "awaiting_confirm", "rescheduling"]),
    ]
    if scope_cond is not None:
        u_filters.append(scope_cond)
    if candidate_id is not None:
        u_filters.append(Interview.candidate_id == candidate_id)

    u_result = await db.execute(
        select(Interview, Candidate)
        .join(Candidate, Interview.candidate_id == Candidate.id)
        .where(*u_filters)
        .order_by(Interview.created_at.desc())
    )
    unconfirmed = []
    for interview, cand in u_result.all():
        slots = interview.proposed_slots if isinstance(interview.proposed_slots, list) else []
        if not slots:
            continue
        unconfirmed.append({
            "id": interview.id,
            "candidate_id": interview.candidate_id,
            "candidate_name": cand.name if cand else "",
            "round": interview.round,
            "status": interview.status,
            "proposed_slots": slots,
        })

    return {"items": items, "unconfirmed": unconfirmed}


@router.post("/{interview_id}/cancel")
async def cancel_interview(
    interview_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """取消面试（HR/admin；可取消状态见 InterviewScheduler.cancel_interview）"""
    await ensure_interview_visible(db, current_user, interview_id)
    try:
        result = await scheduler.cancel_interview(interview_id=interview_id, db=db)
        logger.info("面试已取消: interview_id=%s", interview_id)
        return result
    except ValueError as e:
        logger.warning("取消面试失败: interview_id=%s error=%s", interview_id, e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单条面试记录的详情（越权 404）"""
    interview = await ensure_interview_visible(db, current_user, interview_id)

    cand_result = await db.execute(
        select(Candidate).where(Candidate.id == interview.candidate_id)
    )
    candidate = cand_result.scalar_one_or_none()

    return InterviewResponse(
        id=interview.id,
        candidate_id=interview.candidate_id,
        candidate_name=candidate.name if candidate else "",
        round=interview.round,
        status=interview.status,
        interviewers=interview.interviewers or [],
        proposed_slots=interview.proposed_slots,
        confirmed_start=interview.confirmed_start,
        confirmed_end=interview.confirmed_end,
        location=interview.location,
        meeting_link=interview.meeting_link,
        feedback=interview.feedback,
        ai_summary=interview.ai_summary,
    )
