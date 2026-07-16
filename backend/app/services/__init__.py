"""业务服务层 — 所有核心业务逻辑的入口"""

# 简历分析
from app.services.resume_analyzer import ResumeAnalyzer, resume_analyzer

# 招聘流程引擎（已迁移至 app.workflow 使用 LangGraph）
# from app.services.workflow import RecruitmentWorkflow, workflow

# 问卷服务
from app.services.questionnaire_svc import QuestionnaireService, questionnaire_service, QUESTIONNAIRE_LINK

# 面试排期引擎
from app.services.scheduler_svc import InterviewScheduler, scheduler

# 多渠道通知
from app.services.notification import NotificationService, notification_service

# 制度问答 RAG Agent — 已迁移至 rag_service (端口 18003)
# from app.services.policy_rag import PolicyRAGAgent, policy_rag_agent

# 钉钉日历集成
from app.services.calendar_svc import CalendarService, calendar_service

# 定时任务
from app.services.scheduler_tasks import ScheduledTasks

# 试卷分析
from app.services.exam_analysis_svc import ExamAnalysisService, exam_analysis_service

# Milvus 索引
from app.services.milvus_indexer import index_document_sync

# 中文分句器
from app.services.chinese_text_splitter import (
    ChineseRecursiveTextSplitter,
    create_chinese_splitter,
)

__all__ = [
    # 简历分析
    "ResumeAnalyzer", "resume_analyzer",
    # 问卷
    "QuestionnaireService", "questionnaire_service", "QUESTIONNAIRE_LINK",
    # 面试排期
    "InterviewScheduler", "scheduler",
    # 通知
    "NotificationService", "notification_service",
    # 日历
    "CalendarService", "calendar_service",
    # 定时任务
    "ScheduledTasks",
    # 试卷分析
    "ExamAnalysisService", "exam_analysis_service",
    # Milvus 索引
    "index_document_sync",
    # 中文分句
    "ChineseRecursiveTextSplitter", "create_chinese_splitter",
]
