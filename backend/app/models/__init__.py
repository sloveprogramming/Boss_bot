# 数据模型包 — 必须在 init_db 前全部导入以注册到 SQLAlchemy
from app.models.candidate import Candidate          # 候选人模型
from app.models.resume import Resume                 # 简历模型
from app.models.questionnaire import Questionnaire, QuestionnaireResponse  # 问卷相关模型
from app.models.interview import Interview           # 面试模型
from app.models.policy import PolicyDocument, PolicyChatHistory  # 企业制度文档与对话模型
from app.models.notification import Notification     # 通知记录模型
from app.models.talent_pool import TalentPool        # 人才池模型
from app.models.user import User, UserRole           # 用户与角色模型
from app.models.llm_log import LLMCallLog            # LLM调用日志模型
from app.models.exam_analysis import ExamAnalysis     # 试卷分析模型
