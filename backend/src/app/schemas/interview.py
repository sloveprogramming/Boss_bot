"""面试相关Pydantic Schema"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class TimeSlot(BaseModel):
    """时间段数据结构"""
    date: str        # 日期 "2025-01-15"
    start_time: str  # 开始时间 "10:00"
    end_time: str    # 结束时间 "11:00"


class InterviewSlotRequest(BaseModel):
    """生成面试时间段的请求体"""
    candidate_id: int                        # 候选人ID
    interviewers: List[str] = ["面试官"]      # 面试官列表
    duration_minutes: int = 60               # 面试时长（分钟）
    round: str = "first"                     # 面试轮次
    date_range_start: str                    # 可选日期范围-开始 "2025-01-15"
    date_range_end: str                      # 可选日期范围-结束 "2025-01-20"
    working_hours_start: str = "09:00"       # 工作日开始时间
    working_hours_end: str = "18:00"         # 工作日结束时间
    exclude_dates: List[str] = []            # 需要排除的日期


class InterviewSlotResponse(BaseModel):
    """生成面试时间段的响应体"""
    interview_id: int            # 新创建的面试记录ID
    proposed_slots: List[TimeSlot]  # 推荐的时间段列表


class SlotConfirm(BaseModel):
    """确认面试时间的请求体"""
    interview_id: int               # 面试记录ID
    selected_slot: TimeSlot         # 选中的时间段
    location: Optional[str] = None  # 面试地点
    meeting_link: Optional[str] = None  # 会议链接


class ManualScheduleRequest(BaseModel):
    """手动指定面试时间请求体（HR 直接定时间，不依赖 AI 生成时段）"""
    candidate_id: int                              # 候选人ID
    interviewers: List[str] = ["面试官"]            # 面试官列表
    round: str = "first"                           # 面试轮次
    date: str                                      # 面试日期 "2025-01-15"
    start_time: str                                # 开始时间 "14:00"
    end_time: str                                  # 结束时间 "15:00"
    location: Optional[str] = None                 # 面试地点
    meeting_link: Optional[str] = None             # 会议链接


class InterviewResponse(BaseModel):
    """面试信息的响应体"""
    id: int
    candidate_id: int
    candidate_name: str = ""
    round: str                       # 面试轮次
    status: str                      # 面试状态
    interviewers: List[str] = []     # 面试官列表
    proposed_slots: Optional[List[TimeSlot]] = None  # 建议时间段
    confirmed_start: Optional[datetime] = None       # 确认的开始时间
    confirmed_end: Optional[datetime] = None         # 确认的结束时间
    location: Optional[str] = None                   # 面试地点
    meeting_link: Optional[str] = None               # 会议链接
    feedback: Optional[dict] = None                  # 面试反馈
    ai_summary: Optional[str] = None                 # AI面试摘要

    model_config = {"from_attributes": True}


class InterviewFeedback(BaseModel):
    """提交面试反馈的请求体"""
    interview_id: int              # 面试记录ID
    interviewer: str               # 面试官姓名
    rating: int                    # 评分（1-5分）
    strengths: List[str] = []      # 候选人优势
    weaknesses: List[str] = []     # 候选人不足
    decision: str                  # 决策：pass(通过)/reject(拒绝)/pending(待定)
    detail: str = ""               # 详细评价
