"""试卷分析相关 Pydantic Schema"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class ExamAnalysisResponse(BaseModel):
    """试卷分析记录的响应体"""
    id: int
    candidate_name: str
    candidate_phone: Optional[str] = None
    exam_title: str
    exam_score: Optional[float] = None
    exam_total: Optional[float] = None
    exam_duration: Optional[int] = None
    analysis_status: str
    analysis_result: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    analyzed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExamAnalysisListResponse(BaseModel):
    """试卷分析列表响应体"""
    total: int
    items: list[ExamAnalysisResponse]
    page: int
    page_size: int
