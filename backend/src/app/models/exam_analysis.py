# ═══════════════════════════════════════════════════════════════
# 【小白导读】试卷分析表——存外部考试系统（Workmenul）同步来的答卷分析结果。
#   数据来源：定时任务 workmenul_sync.py 拉取，或 exam_analysis.py 的 webhook 推送。
# ═══════════════════════════════════════════════════════════════
"""试卷分析模型 — 存储轻速云回调原始数据 + Dify 分析结果"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float
from app.database import Base


class ExamAnalysis(Base):
    """轻速云考试结果分析记录"""
    __tablename__ = "exam_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # 外部系统答卷记录ID（自研答题系统，幂等键）
    external_id = Column(String(64), nullable=True, unique=True, comment="外部系统答卷记录ID(Workmenul，幂等键)")

    # 考生信息
    candidate_name = Column(String(100), nullable=False, index=True, comment="考生姓名")
    candidate_phone = Column(String(20), nullable=True, comment="考生手机号")
    candidate_position = Column(String(100), nullable=True, comment="面试岗位(Workmenul采集)")

    # 考试信息
    exam_title = Column(String(200), nullable=False, comment="考试名称")
    exam_score = Column(Float, nullable=True, comment="考试得分")
    exam_total = Column(Float, nullable=True, comment="满分")
    exam_duration = Column(Integer, nullable=True, comment="用时（分钟）")

    # 原始回调数据 + 分析结果
    raw_data = Column(JSON, nullable=True, comment="轻速云回调原始数据")
    analysis_result = Column(JSON, nullable=True, comment="Dify 分析结果")
    analysis_status = Column(String(20), default="pending", comment="状态: pending/analyzing/completed/failed")
    error_message = Column(Text, nullable=True, comment="分析失败原因")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    analyzed_at = Column(DateTime, nullable=True, comment="分析完成时间")
