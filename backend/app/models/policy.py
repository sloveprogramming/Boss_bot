"""企业制度相关模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, Boolean
from app.database import Base


class PolicyDocument(Base):
    """企业规章制度文档模型"""
    __tablename__ = "policy_documents"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)           # 文档标题
    category = Column(String(100), nullable=True)         # 分类：员工手册/考勤制度/薪酬福利/晋升通道
    file_name = Column(String(500), nullable=True)        # 上传的文件名
    content = Column(Text, nullable=True)                  # 文档全文内容

    # RAG（检索增强生成）相关字段
    chunk_count = Column(Integer, default=0)  # 文档分块数量
    indexed = Column(Boolean, default=False)  # 是否已完成向量化索引

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)               # 创建时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 更新时间


class PolicyChatHistory(Base):
    """规章制度Agent对话历史模型"""
    __tablename__ = "policy_chat_history"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)  # 会话ID，用于关联同一对话
    role = Column(String(20), nullable=False)                      # 角色：user(用户) 或 assistant(AI)
    content = Column(Text, nullable=False)                         # 消息内容

    # Agent内部记录信息
    retrieved_chunks = Column(JSON, nullable=True)   # 检索到的相关文档块
    confidence = Column(String(20), nullable=True)   # 回答置信度：high/medium/low
    cited_sources = Column(JSON, nullable=True)      # 引用的文档来源

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)  # 消息创建时间
