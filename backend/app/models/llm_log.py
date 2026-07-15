"""LLM 调用日志模型 — 用于可观测性和成本追踪"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Float
from app.database import Base


class LLMCallLog(Base):
    """LLM调用日志ORM模型，记录每次LLM调用的全链路信息

    字段说明：
      - function_name: 调用来源标识，如 "resume_analyze" / "rag_chat" / "questionnaire_gen"
      - model: 使用的模型名称
      - system_prompt: 系统提示词（截断前500字符）
      - messages: 用户消息（JSON）
      - response: 模型回复（截断前2000字符）
      - prompt_tokens / completion_tokens / total_tokens: Token用量
      - latency_ms: 调用延迟（毫秒）
    """
    __tablename__ = "llm_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)  # 调用时间
    session_id = Column(String(100), nullable=True, index=True)         # 关联会话ID（可选）
    function_name = Column(String(50), nullable=True, index=True)       # 功能名称

    # 请求信息
    model = Column(String(100), nullable=True)                          # 模型名称
    system_prompt = Column(String(500), nullable=True)                  # 系统提示词（截断）
    messages = Column(JSON, nullable=True)                              # 用户消息

    # 响应信息
    response = Column(Text, nullable=True)                              # 模型回复

    # Token用量
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)

    # 性能指标
    latency_ms = Column(Float, default=0.0)                             # 延迟（毫秒）

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else "",
            "session_id": self.session_id,
            "function_name": self.function_name,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_ms": self.latency_ms,
        }
