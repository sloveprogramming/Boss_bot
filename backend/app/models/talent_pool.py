"""人才池模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, JSON, Boolean
from app.database import Base
import enum


class TalentPoolStatus(str, enum.Enum):
    """人才池状态枚举"""
    ACTIVE = "active"            # 在池中：等待机会
    REACTIVATED = "reactivated"  # 已重新激活：被召回应聘新岗位
    CONTACTED = "contacted"      # 已联系：HR已联系候选人
    ARCHIVED = "archived"        # 已归档：入池超3个月自动归档


class TalentPool(Base):
    """人才池ORM模型，存储未录用但有潜力的候选人"""
    __tablename__ = "talent_pool"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 关联候选人（唯一约束，一个候选人只有一条人才池记录）
    candidate_id = Column(Integer, nullable=False, unique=True, index=True)

    original_position = Column(String(200), nullable=False)  # 原应聘岗位
    match_score = Column(Float, nullable=True)               # 匹配度评分

    strengths = Column(JSON, default=list)  # 候选人优势列表
    risks = Column(JSON, default=list)      # 候选人风险/不足列表

    pool_reason = Column(String(500), nullable=True)  # 进入人才池的原因

    suitable_positions = Column(JSON, default=list)  # 适合的未来岗位
    skills = Column(JSON, default=list)              # 技能标签

    status = Column(String(20), default=TalentPoolStatus.ACTIVE.value, index=True)  # 人才池状态

    # 重新激活信息
    reactivated_at = Column(DateTime, nullable=True)   # 重新激活时间
    reactivated_for = Column(String(200), nullable=True)  # 激活后应聘的岗位

    # 联系信息
    contacted_at = Column(DateTime, nullable=True)  # 联系时间
    contact_note = Column(Text, nullable=True)       # 联系备注

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)               # 创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 更新时间
