# 【小白导读】RAG 服务自己的数据库连接（与主后端共用同一个 MySQL 库，
#   但这里是独立实例，两个服务互不干扰）。
"""rag_service 数据库 — SQLAlchemy 异步引擎

与主 Backend 共享同一 MySQL 数据库，
rag_service 只读/写 policy_documents 和 policy_chat_history 表。
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# 延迟导入配置
def _get_settings():
    from app.config import settings
    return settings

settings = _get_settings()
DB_URL = settings.DATABASE_URL

engine = create_async_engine(DB_URL, echo=settings.DEBUG)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """创建所有表（仅在表不存在时执行）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI 依赖：获取数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
