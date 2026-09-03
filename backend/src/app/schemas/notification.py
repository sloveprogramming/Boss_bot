"""通知相关Pydantic Schema"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NotificationRequest(BaseModel):
    """发送通知的请求体"""
    candidate_id: int                         # 目标候选人ID
    template: str                             # 模板名称（questionnaire_invite/面试等）
    channel: str = "email"                    # 发送渠道：email/sms/wework/dingtalk


class NotificationResponse(BaseModel):
    """通知记录的响应体"""
    id: int
    type: str                    # 通知类型/渠道
    template: str                # 使用的模板
    recipient: str               # 收件人
    status: str                  # 发送状态
    sent_at: Optional[datetime] = None      # 发送时间
    error_message: Optional[str] = None     # 错误信息

    model_config = {"from_attributes": True}


class WorkflowStatusResponse(BaseModel):
    """招聘流程状态响应体"""
    candidate_id: int       # 候选人ID
    candidate_name: str     # 候选人姓名
    current_stage: str      # 当前阶段
    next_action: str        # 下一步操作
    summary: dict = {}      # 附加信息
