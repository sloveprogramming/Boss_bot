# ═══════════════════════════════════════════════════════════════
# 【小白导读】问卷两张表：
#   · Questionnaire：发给候选人的问卷实例（题目是 JSON 列，AI 动态生成的）。
#   · QuestionnaireResponse：候选人的作答 + AI 批卷结果（score/passed）。
#   一份问卷对应一条回复记录，通过 questionnaire_id 关联。
# ═══════════════════════════════════════════════════════════════
"""问卷相关模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Float, Boolean
from app.database import Base


class Questionnaire(Base):
    """发送给候选人的问卷实例"""
    __tablename__ = "questionnaires"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)  # 关联候选人
    template_id = Column(Integer, nullable=True)  # 关联的模板ID（可选）

    title = Column(String(200), default="技术能力评估问卷")  # 问卷标题
    questions = Column(JSON, nullable=False)  # 题目列表 [{id, type, question, options?, language?}]

    status = Column(String(20), default="draft")  # 状态：draft(草稿)/sent(已发送)/completed(已完成)/expired(已过期)
    sent_at = Column(DateTime, nullable=True)      # 发送时间
    completed_at = Column(DateTime, nullable=True) # 完成时间
    deadline = Column(DateTime, nullable=True)     # 截止时间

    reminder_count = Column(Integer, default=0)   # 催填提醒次数
    last_reminder_at = Column(DateTime, nullable=True)  # 最后一次催填时间

    created_at = Column(DateTime, default=datetime.utcnow)  # 创建时间


class QuestionnaireResponse(Base):
    """问卷回复/作答记录"""
    __tablename__ = "questionnaire_responses"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"), nullable=False, index=True)  # 关联问卷
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)         # 关联候选人

    answers = Column(JSON, nullable=True)                     # 答案内容 {question_id: answer_value}
    score = Column(Float, nullable=True)                      # AI评定的总分
    score_breakdown = Column(JSON, nullable=True)             # 每题得分明细
    overall_comment = Column(Text, nullable=True)              # AI整体评价
    passed = Column(Boolean, nullable=True)                    # 是否通过（及格线60分）

    submitted_at = Column(DateTime, nullable=True)  # 提交时间
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
