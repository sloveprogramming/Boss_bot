# ═══════════════════════════════════════════════════════════════
# 【小白导读】可配置邮件模板表——原来 7 套邮件模板硬编码在
#   services/notification.py 里，现在迁进数据库，HR/Admin 可在界面上
#   直接改文案、停用，或让 AI 生成草稿后人工微调保存。
#   自动发送时：DB 有生效记录 → 用 DB 文案；没有/停用/删除 → 回退内置默认。
#   7 个内置 code 不变，只是把「存储位置」从代码搬到表里。
# ═══════════════════════════════════════════════════════════════
"""可配置通知模板模型 — 邮件等渠道的 subject/body 模板（DB 优先、内置兜底）

字段说明：
  - code: 场景编码，如 questionnaire_invite / interview_invite / offer / rejection …
          唯一约束；与 NotificationService.TEMPLATES 的 7 个 key 对应。
  - category: 分类（questionnaire / interview / result / other），用于界面分组。
  - subject/body: 模板内容，支持 {占位符}（见 variables 说明）。
  - is_system: 是否内置模板迁移而来（界面标记「系统」徽标，可编辑可删除）。
  - is_active: 停用后该 code 自动发送回退内置默认。
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func
)
from app.database import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, index=True, nullable=False)  # 场景编码
    name = Column(String(100), nullable=False, default="")              # 显示名
    category = Column(String(40), nullable=False, default="other")      # 分类分组
    subject = Column(String(255), nullable=False, default="")           # 邮件主题（可含占位符）
    body = Column(Text, nullable=False, default="")                     # 邮件正文（可含占位符）
    is_system = Column(Boolean, nullable=False, default=False)          # 是否内置迁移
    is_active = Column(Boolean, nullable=False, default=True)           # 停用 → 回退内置
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 管理人
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "category": self.category,
            "subject": self.subject,
            "body": self.body,
            "is_system": bool(self.is_system),
            "is_active": bool(self.is_active),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
