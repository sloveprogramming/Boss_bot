"""试卷分析相关 Pydantic Schema"""
from datetime import datetime
from typing import Optional, Any, Literal
from pydantic import BaseModel


class ExamAnalysisResponse(BaseModel):
    """试卷分析记录的响应体"""
    id: int
    candidate_name: str
    candidate_phone: Optional[str] = None
    candidate_position: Optional[str] = None
    external_id: Optional[str] = None
    exam_title: str
    exam_score: Optional[float] = None
    exam_total: Optional[float] = None
    exam_duration: Optional[int] = None
    analysis_status: str
    analysis_result: Optional[Any] = None
    raw_data: Optional[Any] = None
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


class ExamImportRequest(BaseModel):
    """自研答题系统导入请求体（由 Workmenul 推送，幂等）"""
    external_id: str
    candidate_name: str
    exam_title: str
    candidate_phone: Optional[str] = None
    candidate_position: Optional[str] = None
    exam_score: Optional[float] = None
    exam_total: Optional[float] = None
    exam_duration: Optional[int] = None   # 分钟
    analysis_status: Literal["pending", "analyzing", "completed", "failed"] = "completed"
    analysis_result: Optional[Any] = None
    raw_data: Optional[Any] = None
    error_message: Optional[str] = None

    model_config = {"extra": "allow"}


class ExamImportResponse(BaseModel):
    """导入（幂等 upsert）响应体"""
    id: int
    created: bool
