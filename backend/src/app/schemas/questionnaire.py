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
