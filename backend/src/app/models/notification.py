# ═══════════════════════════════════════════════════════════════
# 【小白导读】通知记录表——每次发邮件/短信/机器人消息都留一条底，方便追溯"发没发过"。
# ═══════════════════════════════════════════════════════════════
"""通知记录模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
from app.database import Base


class Notification(Base):
    """通知记录ORM模型，存储所有外发通知"""
    __tablename__ = "notifications"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 关联候选人（可为空，例如系统通知无需关联候选人）
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True, index=True)

    type = Column(String(50), nullable=False)   # 通知渠道：email(邮件)/sms(短信)/wework(企微)/dingtalk(钉钉)
    template = Column(String(100), nullable=False)  # 使用的模板名称
    """模板列表: questionnaire_invite(问卷邀请), reminder_1/2(催填),
       interview_invite(面试邀请), interview_confirmed(面试确认),
       interview_reminder(面试提醒), rejection(拒信), offer(录用通知)"""
    recipient = Column(String(500), nullable=False)  # 收件人地址/号码
    subject = Column(String(500), nullable=True)      # 通知主题
    content = Column(Text, nullable=True)              # 通知正文内容

    status = Column(String(20), default="pending")  # 发送状态：pending(待发送)/sent(已发送)/failed(发送失败)
    error_message = Column(Text, nullable=True)      # 发送失败时的错误信息
    sent_at = Column(DateTime, nullable=True)        # 实际发送时间

    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
