"""任务进度表 — 记录每个异步分析任务的生命周期（配合 RabbitMQ 队列）

为什么需要它：
  - 任务入队后脱离 HTTP 请求，前端无法再从同步返回值拿结果
  - 这张表充当「进度公告板」：worker 每推进一个阶段就更新，前端轮询 GET /api/workflow/task/{task_id}
  - 同时是任务去重 / 审计 / 失败重放的依据

状态机： pending → received → running → success | failure
"""
from datetime import datetime
import enum
from sqlalchemy import (
    Column, Integer, String, Text, JSON, DateTime, ForeignKey, Index, func
)
from app.database import Base


class TaskStatus(str, enum.Enum):
    """分析任务状态（字符串枚举：兼容 .value 取值与直接落库两种写法）"""
    PENDING = "pending"     # 已入队，等待 worker 领取
    RECEIVED = "received"   # worker 已领取，准备执行
    RUNNING = "running"     # 执行中
    SUCCESS = "success"     # 执行成功
    FAILURE = "failure"     # 最终失败（重试已耗尽，进入死信队列）


class TaskProgress(Base):
    __tablename__ = "task_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, index=True, nullable=False)  # 队列任务ID (UUID)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), index=True, nullable=False)
    status = Column(String(20), default=TaskStatus.PENDING, nullable=False, index=True)
    progress = Column(Integer, default=0)              # 0~100 进度百分比
    current_stage = Column(String(40), default="")     # 当前节点名，如 parse_resume / classify
    stage_message = Column(String(255), default="")    # 人类可读的阶段描述
    result_payload = Column(JSON, default=None)        # 最终返回给前端的结果（状态/分数/分类）
    error = Column(Text, default=None)                 # 失败原因
    retries = Column(Integer, default=0)               # 已重试次数
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_task_progress_candidate_status", "candidate_id", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "progress": self.progress,
            "current_stage": self.current_stage,
            "stage_message": self.stage_message,
            "result": self.result_payload,
            "error": self.error,
            "retries": self.retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
