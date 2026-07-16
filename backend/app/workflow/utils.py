"""工作流节点通用工具 — 数据库会话管理、候选人查询等"""

from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session_factory
from app.models import Candidate


async def get_candidate(db: AsyncSession, candidate_id: int) -> Optional[Candidate]:
    """按 ID 查询候选人，不存在返回 None"""
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


@asynccontextmanager
async def candidate_session(
    candidate_id: int, # 候选人 ID
    suppress_errors: bool = False, # 是否吞掉异常不抛出（用于非关键操作）
) -> AsyncGenerator[tuple[AsyncSession, Optional[Candidate]], None]: # 异步生成器，返回数据库会话和候选人对象
    """上下文管理器：自动处理 开会话 → 查候选人 → 提交/回滚

    Args:
        candidate_id: 候选人 ID
        suppress_errors: True 时吞掉异常不抛出（用于非关键操作）

    Yields:
        (db_session, candidate) 元组

    用法:
        async with candidate_session(candidate_id) as (db, candidate):
            if candidate:
                candidate.status = "classified"
    """
    async with async_session_factory() as db:
        try:
            candidate = await get_candidate(db, candidate_id)
            yield db, candidate
            await db.commit()
        except Exception:
            await db.rollback()
            if not suppress_errors:
                raise
