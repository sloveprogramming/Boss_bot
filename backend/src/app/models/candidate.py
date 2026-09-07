"""候选人模型"""
# 导入datetime，用于时间戳字段的默认值
from datetime import datetime
# 导入SQLAlchemy列类型
from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Enum, JSON, ForeignKey
# 导入关系映射（可用于表关联）
from sqlalchemy.orm import relationship
# 导入数据库基类，所有ORM模型需继承它
from app.database import Base
# 导入Python枚举库
import enum


class CandidateStatus(str, enum.Enum):
    """候选人状态枚举：定义完整的生命周期状态"""
    NEW = "new"                     # 新候选人：刚录入系统，尚未处理
    RESUME_ANALYZED = "analyzed"    # 简历已分析：AI已完成简历解析和匹配度评分
    TALENT_POOL = "talent_pool"     # 已进入人才池：有潜力但未达当前岗位要求
    QUESTIONNAIRE_SENT = "q_sent"   # 问卷已发送：技术评估问卷已发给候选人
    QUESTIONNAIRE_DONE = "q_done"   # 问卷已完成：候选人已提交问卷回复
    INTERVIEW_SCHEDULED = "scheduled"   # 已安排面试：面试时间已确认
    INTERVIEWED = "interviewed"     # 已面试：面试已完成
    REJECTED = "rejected"           # 已拒绝：不符合要求
    HIRED = "hired"                 # 已录用：通过面试，已发Offer
    ARCHIVED = "archived"           # 已归档：长时间未操作


class Candidate(Base):
    """候选人ORM模型，对应数据库candidates表"""
    # 数据库表名
    __tablename__ = "candidates"
    # 主键：自增整数ID
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 姓名：必填，加索引用于搜索
    name = Column(String(100), nullable=False, index=True)
    # 电话：可选
    phone = Column(String(20), nullable=True)
    # 邮箱：可选，加索引用于搜索
    email = Column(String(200), nullable=True, index=True)

    # 来源 — 记录候选人来源渠道
    source = Column(String(50), default="manual")  # manual(手动)/boss(直聘)/linkedin/referral(内推)
    source_url = Column(Text, nullable=True)        # 外部来源URL（如Boss直聘链接）
    external_id = Column(String(200), nullable=True)  # 外部平台ID（如Boss直聘候选人ID）

    # 岗位信息
    position = Column(String(200), nullable=False, index=True)  # 应聘岗位名称
    experience_years = Column(Float, nullable=True)              # 工作年限（如3.5年）
    job_category = Column(String(50), nullable=True, index=True) # 岗位自动分类（如python/java/erp）

    # 状态与评分
    status = Column(String(20), default=CandidateStatus.NEW.value, index=True)  # 当前状态
    match_score = Column(Float, nullable=True)  # AI匹配度评分（0-100）

    # 人才池相关信息
    talent_pool_id = Column(Integer, nullable=True)         # 关联的人才池记录ID
    talent_pool_reason = Column(String(500), nullable=True)  # 进入人才池的原因

    # 归属 — 负责人 HR（NULL 表示未指派；admin 全量可见）
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 标签：存储技能标签，如["Python", "Django", "MySQL"]
    tags = Column(JSON, default=list)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)               # 创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 更新时间
