"""Pydantic Schemas — API 请求/响应数据模型"""
from app.schemas.auth import (
    LoginRequest, TokenResponse, UserCreate,
    SetupAdminRequest, ChangePasswordRequest, UserResponse,
)
from app.schemas.candidate import (
    CandidateCreate, CandidateUpdate, CandidateResponse, CandidateListResponse,
    TalentPoolResponse, TalentPoolListResponse,
    ReactivateRequest, TalentPoolCreateRequest,
)
from app.schemas.resume import (
    ResumeUploadResponse, ResumeAnalysisResult, MatchAnalysis,
    ResumeAnalysisResponse, ResumeAnalysisRequest,
)
from app.schemas.interview import (
    TimeSlot, InterviewSlotRequest, InterviewSlotResponse,
    SlotConfirm, InterviewResponse, InterviewFeedback,
)
from app.schemas.notification import (
    NotificationRequest, NotificationResponse, WorkflowStatusResponse,
)
from app.schemas.questionnaire import (
    QuestionItem, QuestionnaireResponse,
)
from app.schemas.exam_analysis import (
    ExamAnalysisResponse, ExamAnalysisListResponse,
    ExamImportRequest, ExamImportResponse,
)

__all__ = [
    # auth
    "LoginRequest", "TokenResponse", "UserCreate",
    "SetupAdminRequest", "ChangePasswordRequest", "UserResponse",
    # candidate / talent pool
    "CandidateCreate", "CandidateUpdate", "CandidateResponse", "CandidateListResponse",
    "TalentPoolResponse", "TalentPoolListResponse",
    "ReactivateRequest", "TalentPoolCreateRequest",
    # resume
    "ResumeUploadResponse", "ResumeAnalysisResult", "MatchAnalysis",
    "ResumeAnalysisResponse", "ResumeAnalysisRequest",
    # interview
    "TimeSlot", "InterviewSlotRequest", "InterviewSlotResponse",
    "SlotConfirm", "InterviewResponse", "InterviewFeedback",
    # notification
    "NotificationRequest", "NotificationResponse", "WorkflowStatusResponse",
    # questionnaire
    "QuestionItem", "QuestionnaireResponse",
    # exam
    "ExamAnalysisResponse", "ExamAnalysisListResponse",
    "ExamImportRequest", "ExamImportResponse",
]
