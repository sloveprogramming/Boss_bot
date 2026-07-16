"""面试排期API — 时间段生成、确认、反馈提交"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Interview, Candidate
from app.services import scheduler
from app.schemas import (
    InterviewSlotRequest, InterviewSlotResponse,
    SlotConfirm, InterviewResponse, InterviewFeedback,
)

router = APIRouter(prefix="/api/interviews", tags=["面试管理"])


@router.post("/generate-slots", response_model=InterviewSlotResponse)
async def generate_slots(data: InterviewSlotRequest,
                          db: AsyncSession = Depends(get_db)):
    """根据约束条件生成可选的面试时间段"""
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
        return InterviewSlotResponse(
            interview_id=result["interview_id"],
            proposed_slots=result["proposed_slots"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/confirm-slot", response_model=InterviewResponse)
async def confirm_slot(data: SlotConfirm, db: AsyncSession = Depends(get_db)):
    """候选人确认选定的面试时间"""
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
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/feedback")
async def submit_feedback(data: InterviewFeedback,
                           db: AsyncSession = Depends(get_db)):
    """提交面试反馈（面试官填写）"""
    try:
        result = await scheduler.submit_feedback(
            interview_id=data.interview_id,
            feedback=data.model_dump(),
            db=db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/candidate/{candidate_id}")
async def get_candidate_interviews(
    candidate_id: int, db: AsyncSession = Depends(get_db)
):
    """获取指定候选人的所有面试记录"""
    result = await db.execute(
        select(Interview)
        .where(Interview.candidate_id == candidate_id)
        .order_by(Interview.created_at.desc())
    )
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


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: int, db: AsyncSession = Depends(get_db)):
    """获取单条面试记录的详情"""
    result = await db.execute(
        select(Interview).where(Interview.id == interview_id)
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="面试记录不存在")

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
