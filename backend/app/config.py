"""应用配置 — 使用Pydantic Settings从项目根目录的.env文件加载"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


def _find_root_env() -> str:
    """从当前文件位置向上查找项目根目录的 .env 文件

    backend/app/config.py → ../../.env  （项目根）
    无论从哪个目录启动 uvicorn 都能找到同一份配置
    """
    p = Path(__file__).resolve().parent
    for _ in range(5):  # 最多向上 5 层
        candidate = p / ".env"
        if candidate.exists():
            return str(candidate)
        p = p.parent
    return ".env"  # 兜底：使用 CWD 下的 .env


class Settings(BaseSettings):
    """应用配置类，自动从项目根目录的 .env 读取"""
    # 应用基本信息
    APP_NAME: str = "AI Recruit Assistant"  # 应用名称
    DEBUG: bool = True                       # 调试模式

    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./recruit.db"  # SQLite异步数据库URL

    # LLM提供商
    LLM_PROVIDER: str = "openai"  # 仅支持 openai 兼容接口（DeepSeek、通义千问等）

    # OpenAI兼容接口配置
    OPENAI_API_KEY: Optional[str] = None     # API密钥
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"  # API基础地址（可替换为代理地址）
    OPENAI_MODEL: str = "gpt-4o"             # 模型名称

    # Dify 配置
    DIFY_API_URL: str = "http://localhost/v1"  # Dify API 地址
    DIFY_API_KEY: Optional[str] = None          # Dify API Key

    # Embedding模型（本地模型，无需API Key）
    EMBEDDING_MODEL: str = "shibing624/text2vec-base-chinese"  # 中文文本向量化模型
    EMBEDDING_DIMENSION: int = 768  # 向量维度

    # 向量数据库（Milvus）
    MILVUS_HOST: str = "localhost"  # Milvus服务地址
    MILVUS_PORT: str = "19530"      # Milvus服务端口

    # 评分阈值（用于自动分流）
    SCORE_THRESHOLD_FAST_TRACK: float = 80.0   # 快速通道：>=80分直接进入面试
    SCORE_THRESHOLD_QUESTIONNAIRE: float = 60.0  # 问卷通道：>=60分发问卷
    SCORE_THRESHOLD_TALENT_POOL: float = 40.0    # 人才池：>=40分进人才库
    # <40分：自动拒绝

    # 邮件通知配置
    SMTP_HOST: Optional[str] = None       # SMTP服务器地址
    SMTP_PORT: int = 587                  # SMTP端口
    SMTP_USER: Optional[str] = None       # SMTP用户名
    SMTP_PASSWORD: Optional[str] = None   # SMTP密码
    NOTIFICATION_EMAIL_FROM: str = "noreply@recruitai.com"  # 发件人地址

    # Twilio短信配置
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    # 企业微信机器人配置
    WEWORK_WEBHOOK_URL: Optional[str] = None

    # 钉钉机器人配置
    DINGTALK_WEBHOOK_URL: Optional[str] = None
    DINGTALK_APP_KEY: Optional[str] = None     # 钉钉应用Key（用于日历集成）
    DINGTALK_APP_SECRET: Optional[str] = None   # 钉钉应用Secret

    # 企业制度文档路径
    POLICY_DOCS_DIR: str = "./dco_document"  # 制度文档存放目录

    # ===== RAG 优化参数 =====
    # Parent-Child 分块
    PARENT_CHUNK_SIZE: int = 1200       # 父块大小（LLM上下文单位）
    CHILD_CHUNK_SIZE: int = 300         # 子块大小（检索匹配单位）
    CHUNK_OVERLAP: int = 50             # 分块重叠字符数

    # 混合检索
    HYBRID_SEARCH_ENABLED: bool = True  # 是否启用混合检索
    HYBRID_DENSE_WEIGHT: float = 1.0    # 稠密向量权重
    HYBRID_SPARSE_WEIGHT: float = 0.7   # 稀疏向量权重

    # 检索数量
    RETRIEVAL_TOP_K: int = 10           # 初始检索数
    RERANK_CANDIDATES_M: int = 5        # 重排序后返回数

    # CrossEncoder 重排序模型路径（留空则用 HuggingFace 默认路径）
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # 查询分类
    POLICY_KEYWORDS: list = [           # 制度相关关键词
        "考勤", "请假", "年假", "病假", "事假", "婚假", "产假",
        "薪酬", "工资", "奖金", "补贴", "加班", "调休",
        "报销", "出差", "培训", "晋升", "绩效", "考核",
        "休假", "迟到", "早退", "旷工", "离职", "入职",
        "社保", "公积金", "福利", "补贴", "餐补", "车补",
        "制度", "规定", "办法", "章程", "条例", "守则",
        "劳动合同", "试用期", "转正", "辞职", "辞退",
    ]

    # ===== JWT 认证 =====
    JWT_SECRET: str = "change-this-to-a-random-secret-key"  # JWT密钥（生产环境务必修改）
    JWT_ALGORITHM: str = "HS256"                            # JWT加密算法
    JWT_EXPIRE_HOURS: int = 24                              # Token过期时间（小时）

    # ===== Redis / 语义缓存 =====
    REDIS_URL: str = "redis://localhost:6379/0"             # Redis连接地址
    SEMANTIC_CACHE_ENABLED: bool = True                     # 是否启用语义缓存
    SEMANTIC_CACHE_TTL: int = 86400                         # 缓存过期时间（秒，默认24h）
    CACHE_SIMILARITY_THRESHOLD: float = 0.92                # 语义缓存命中相似度阈值

    # 面试相关默认值
    DEFAULT_INTERVIEW_DURATION: int = 60         # 默认面试时长（分钟）
    MIN_INTERVAL_BETWEEN_INTERVIEWS: int = 15    # 面试最小间隔（分钟）
    MAX_INTERVIEWS_PER_DAY: int = 5              # 每天最大面试数

    class Config:
        env_file = _find_root_env()  # 从项目根目录查找 .env（不再依赖 CWD）
        env_file_encoding = "utf-8"    # 文件编码
        # 允许 .env / 环境变量中包含未在 Settings 中声明的旧字段（如已弃用的 Agent URL），静默忽略
        # 避免新增/保留旧环境变量时导致整个应用启动失败
        extra = "ignore"


# 全局设置实例
settings = Settings()
