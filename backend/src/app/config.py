"""应用配置 — 使用Pydantic Settings从项目根目录的.env文件加载"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


def _find_root_env() -> str:
    """从当前文件位置向上查找项目根目录的 .env 文件

    backend/src/app/config.py → ../../../.env  （项目根）
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
    APP_NAME: str = "智聘云"  # 应用名称
    DEBUG: bool = False                      # 调试模式仅应在本地显式开启
    LOG_LEVEL: str = "INFO"                  # 日志级别: DEBUG/INFO/WARNING/ERROR

    # 数据库配置
    DATABASE_URL: str = "mysql+aiomysql://root:123456@localhost:3306/recruit_ai?charset=utf8mb4"  # MySQL异步数据库URL

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

    # 向量数据库（Milvus）
    MILVUS_HOST: str = "localhost"  # Milvus服务地址
    MILVUS_PORT: str = "19530"      # Milvus服务端口

    # 评分阈值（用于自动分流）
    SCORE_THRESHOLD_FAST_TRACK: float = 80.0   # 快速通道：>=80分直接进入面试
    SCORE_THRESHOLD_QUESTIONNAIRE: float = 60.0  # 问卷通道：>=60分发问卷
    SCORE_THRESHOLD_TALENT_POOL: float = 40.0    # 人才池：>=40分进人才库
    # <40分：自动拒绝

    # ===== 评分权重（v2 评分体系：维度分落库，总分按权重派生） =====
    # 总分 = Σ(维度分 × 权重)，改权重后历史候选人可全量重算，无需重跑 LLM
    # 合法性：所有权重 > 0 且求和 ≈ 1，非法时自动回退默认值
    SCORE_WEIGHTS_DEFAULT: dict = {"skill": 0.4, "experience": 0.4, "stability": 0.2}
    # 按岗位类别覆盖权重，如 {"销售": {"skill": 0.3, "experience": 0.4, "stability": 0.3}}
    # 2026-09 按在招岗位价值说明书设定：
    #   销售类（资源/结果导向，稳定性权重上调）；研发类（专业深度权重上调）；
    #   支持/翻译类（技能硬门槛，保持默认）；运营管理类（经验与管理年限权重上调）
    SCORE_WEIGHTS_BY_CATEGORY: dict = {
        "市场主管": {"skill": 0.35, "experience": 0.4, "stability": 0.25},
        "采购主管": {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        "食品研发工程师": {"skill": 0.45, "experience": 0.35, "stability": 0.2},
        "销售内勤": {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        "城市经理": {"skill": 0.3, "experience": 0.4, "stability": 0.3},
        "大宗贸易销售": {"skill": 0.3, "experience": 0.4, "stability": 0.3},
        "俄语外贸业务员": {"skill": 0.35, "experience": 0.4, "stability": 0.25},
        "英语翻译（总秘）": {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        "电商运营经理": {"skill": 0.35, "experience": 0.4, "stability": 0.25},
        "电商资深运营": {"skill": 0.4, "experience": 0.4, "stability": 0.2},
        "视频号商务BD": {"skill": 0.3, "experience": 0.4, "stability": 0.3},
    }
    # diff 闸门：加权分与 LLM 重评分的偏差阈值；None = 只记录不拦截（观察期模式）
    SCORE_DIFF_ALERT_THRESHOLD: Optional[float] = None

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


    # ===== JWT 认证 =====
    JWT_SECRET: str = ""                    # 必须通过环境变量注入，避免误用默认密钥
    JWT_ALGORITHM: str = "HS256"                            # JWT加密算法
    JWT_EXPIRE_HOURS: int = 24                              # Token过期时间（小时）

    # 外部考试平台回调签名密钥。为空时不接受回调，避免匿名写入招聘数据。
    EXAM_WEBHOOK_TOKEN: Optional[str] = None


    # 面试相关默认值
    DEFAULT_INTERVIEW_DURATION: int = 60         # 默认面试时长（分钟）
    MIN_INTERVAL_BETWEEN_INTERVIEWS: int = 15    # 面试最小间隔（分钟）
    MAX_INTERVIEWS_PER_DAY: int = 5              # 每天最大面试数

    # ===== RabbitMQ / 异步任务队列（高并发防护）=====
    # 用消息队列把"简历分析"这类重负载从 HTTP 请求中剥离，配合有界并发 + 重试退避，
    # 避免几千份简历同时分析时瞬间打爆 LLM API 与数据库。
    # 若 RabbitMQ 不可达或 aio_pika 未安装，系统自动降级为内联同步执行（TASK_ENABLED 控制总开关）。
    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672//"  # RabbitMQ 连接地址
    TASK_EXCHANGE: str = "recruit_tasks"          # 任务主题交换机
    TASK_QUEUE_NAME: str = "resume_analysis"      # 简历分析队列名
    TASK_PREFETCH_COUNT: int = 8                  # 单 worker 并发消费上限（背压核心参数）
    TASK_MAX_RETRIES: int = 5                     # 单任务最大重试次数（重试耗尽进死信队列）
    TASK_RETRY_BACKOFF: float = 2.0               # 指数退避基数（秒）
    TASK_RETRY_BACKOFF_MAX: float = 60.0          # 退避上限（秒）
    TASK_RATE_LIMIT_PER_MIN: int = 300            # 软限速参考值（配合多 worker 横向扩展）
    TASK_ENABLED: bool = True                     # False → 全部走内联同步（降级模式）

    model_config = SettingsConfigDict(
        env_file=_find_root_env(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


# 全局设置实例
settings = Settings()
