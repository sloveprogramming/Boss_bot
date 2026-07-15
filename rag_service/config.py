"""rag_service 配置 — 复用主项目 .env，独立运行时也可自建 .env"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """RAG 服务配置"""

    # 应用
    APP_NAME: str = "RAG Service"
    DEBUG: bool = True

    # 数据库（与主 Backend 共享 SQLite）
    DATABASE_URL: str = "sqlite+aiosqlite:///./recruit.db"

    # LLM
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"

    # Embedding
    EMBEDDING_MODEL: str = "shibing624/text2vec-base-chinese"
    EMBEDDING_DIMENSION: int = 768

    # Milvus 向量数据库
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"

    # 分块参数
    PARENT_CHUNK_SIZE: int = 1200
    CHILD_CHUNK_SIZE: int = 300
    CHUNK_OVERLAP: int = 50

    # 混合检索
    HYBRID_DENSE_WEIGHT: float = 1.0
    HYBRID_SPARSE_WEIGHT: float = 0.7
    RETRIEVAL_TOP_K: int = 10
    RERANK_CANDIDATES_M: int = 5

    # 重排序
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"

    # 查询分类关键词
    POLICY_KEYWORDS: list = [
        "考勤", "请假", "年假", "病假", "事假", "婚假", "产假",
        "薪酬", "工资", "奖金", "补贴", "加班", "调休",
        "报销", "出差", "培训", "晋升", "绩效", "考核",
        "休假", "迟到", "早退", "旷工", "离职", "入职",
        "社保", "公积金", "福利", "补贴", "餐补", "车补",
        "制度", "规定", "办法", "章程", "条例", "守则",
        "劳动合同", "试用期", "转正", "辞职", "辞退",
    ]

    # Redis 语义缓存
    REDIS_URL: str = "redis://localhost:6379/0"
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_TTL: int = 86400
    CACHE_SIMILARITY_THRESHOLD: float = 0.92

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
