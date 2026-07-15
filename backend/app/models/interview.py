"""面试排期模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Enum
from app.database import Base
import enum


class InterviewStatus(str, enum.Enum):
    """面试状态枚举"""
    PENDING = "pending"                     # 等待安排
    AWAITING_CONFIRM = "awaiting_confirm"   # 等待候选人确认时间
    CONFIRMED = "confirmed"                 # 时间已确认
    RESCHEDULING = "rescheduling"           # 改期中
    COMPLETED = "completed"                 # 已完成
    CANCELLED = "cancelled"                 # 已取消
    NO_SHOW = "no_show"                     # 候选人未出席


class InterviewRound(str, enum.Enum):
    """面试轮次枚举"""
    FIRST = "first"         # 初面
    TECHNICAL = "technical" # 技术面
    HR = "hr"               # HR面
    FINAL = "final"         # 终面


class Interview(Base):
    """面试ORM模型，对应数据库interviews表"""
    __tablename__ = "interviews"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 外键：关联候选人
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)

    round = Column(String(20), default=InterviewRound.FIRST.value)  # 面试轮次
    status = Column(String(20), default=InterviewStatus.PENDING.value)  # 面试状态

    # 面试人员信息
    interviewers = Column(JSON, default=list)  # 面试官列表，如 ["面试官1", "面试官2"]
    duration_minutes = Column(Integer, default=60)  # 面试时长（分钟）

    # 时间安排
    proposed_slots = Column(JSON, nullable=True)  # 推送给候选人的可选时间段 [{date, start_time, end_time}]
    confirmed_start = Column(DateTime, nullable=True)  # 确认后的开始时间
    confirmed_end = Column(DateTime, nullable=True)    # 确认后的结束时间

    # 地点/方式
    location = Column(String(500), nullable=True)     # 线下面试地址
    meeting_link = Column(String(500), nullable=True) # 线上会议链接

    # 面试结果
    feedback = Column(JSON, nullable=True)
    """JSON结构示例:
    {
        "interviewer": "xxx", "rating": 4,
        "strengths": [...], "weaknesses": [...],
        "decision": "pass/reject/pending", "detail": "..."
    }
    """
    ai_summary = Column(Text, nullable=True)  # AI自动生成的面试摘要

    # 提醒状态
    reminder_sent = Column(Integer, default=0)  # 已发送提醒的次数

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)               # 创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 更新时间
