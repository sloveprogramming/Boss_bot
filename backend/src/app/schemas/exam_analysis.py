# 【小白导读】schemas = Pydantic 模型，负责 API 的"进出门安检"：
#   请求进来先按这里的类校验字段（类型不对直接返回 422），响应出去也按它序列化。
#   和 models 的区别：models 描述数据库表长什么样，schemas 描述接口的请求/响应长什么样。
# 本文件：试卷分析数据的进出格式。

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
