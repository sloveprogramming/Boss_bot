# 【小白导读】schemas = Pydantic 模型，负责 API 的"进出门安检"：
#   请求进来先按这里的类校验字段（类型不对直接返回 422），响应出去也按它序列化。
#   和 models 的区别：models 描述数据库表长什么样，schemas 描述接口的请求/响应长什么样。
# 本文件：问卷发送/查询接口的进出格式。

"""问卷相关Pydantic Schema — 简化版"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class QuestionItem(BaseModel):
    """单道题目的数据结构"""
    id: str
    type: str
    question: str
    options: Optional[List[str]] = None
    language: Optional[str] = None


class QuestionnaireResponse(BaseModel):
    """问卷信息的响应体"""
    id: int
    candidate_id: int
    title: str
    questions: List[QuestionItem] = []
    status: str
    sent_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deadline: Optional[datetime] = None

    model_config = {"from_attributes": True}
