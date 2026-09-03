"""评分权重迭代模型 — 记录每次"按面试通过率调整权重"的应用历史"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON
from app.database import Base


class ScoringIteration(Base):
    """评分权重迭代记录

    权重应用本身只写 settings 进程内存（重启回退 .env，与 dashboard /scoring-weights
    一致），但每次应用都会落一张历史表，形成可追溯的迭代记录。
    """
    __tablename__ = "scoring_iterations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), default="", nullable=False)  # "" 表示默认权重
    from_weights = Column(JSON, nullable=False)                 # 应用前的权重
    to_weights = Column(JSON, nullable=False)                   # 应用后的权重
    note = Column(String(500), nullable=True)                   # 本次迭代说明
    applied_by = Column(String(50), nullable=True)              # 操作人用户名
    created_at = Column(DateTime, default=datetime.utcnow)      # 应用时间
