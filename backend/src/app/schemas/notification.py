# 【小白导读】schemas = Pydantic 模型，负责 API 的"进出门安检"：
#   请求进来先按这里的类校验字段（类型不对直接返回 422），响应出去也按它序列化。
#   和 models 的区别：models 描述数据库表长什么样，schemas 描述接口的请求/响应长什么样。
# 本文件：通知相关接口的进出格式。

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
