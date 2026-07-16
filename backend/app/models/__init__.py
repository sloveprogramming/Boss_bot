# 数据模型 — 必须在 init_db 前全部导入，SQLAlchemy 才能建表
from app.models.candidate import Candidate, CandidateStatus
from app.models.resume import Resume
from app.models.questionnaire import Questionnaire, QuestionnaireResponse
from app.models.interview import Interview, InterviewStatus, InterviewRound
from app.models.policy import PolicyDocument, PolicyChatHistory
from app.models.notification import Notification
from app.models.talent_pool import TalentPool, TalentPoolStatus
from app.models.user import User, UserRole
from app.models.llm_log import LLMCallLog
from app.models.exam_analysis import ExamAnalysis

__all__ = [
    "Candidate", "CandidateStatus",
    "Resume",
    "Questionnaire", "QuestionnaireResponse",
    "Interview", "InterviewStatus", "InterviewRound",
    "PolicyDocument", "PolicyChatHistory",
    "Notification",
    "TalentPool", "TalentPoolStatus",
    "User", "UserRole",
    "LLMCallLog",
    "ExamAnalysis",
]
