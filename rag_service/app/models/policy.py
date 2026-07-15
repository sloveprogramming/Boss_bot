"""企业制度相关模型 — 独立 RAG 服务版"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean
from app.database import Base


class PolicyDocument(Base):
    """企业规章制度文档模型"""
    __tablename__ = "policy_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=True)
    file_name = Column(String(500), nullable=True)
    content = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    indexed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PolicyChatHistory(Base):
    """规章制度 Agent 对话历史"""
    __tablename__ = "policy_chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    retrieved_chunks = Column(JSON, nullable=True)
    confidence = Column(String(20), nullable=True)
    cited_sources = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
