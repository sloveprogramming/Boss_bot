"""数据库连接与会话管理 — SQLAlchemy异步引擎 + 会话工厂"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


# SQLite需要特殊处理：将标准sqlite:///替换为异步支持的sqlite+aiosqlite:///
DB_URL = settings.DATABASE_URL
if DB_URL.startswith("sqlite:///") and not DB_URL.startswith("sqlite+aiosqlite"):
    DB_URL = DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
if DB_URL.startswith("sqlite:///"):
    DB_URL = DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

# 创建异步数据库引擎（echo=DEBUG时打印SQL语句）
engine = create_async_engine(DB_URL, echo=settings.DEBUG)
# 创建异步会话工厂
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有ORM模型的基类，SQLAlchemy声明式映射的基础"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI依赖注入：获取数据库会话

    在每个请求中自动管理：
    - 成功时提交事务
    - 异常时回滚
    - 请求结束时关闭会话
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()   # 正常结束则提交
        except Exception:
            await session.rollback()  # 异常则回滚
            raise
        finally:
            await session.close()     # 最终关闭会话


async def init_db():
    """初始化数据库表结构（首次运行时创建所有表）"""
    async with engine.begin() as conn:
        from app.models import (
            candidate,    # 候选人模型
            resume,       # 简历模型
            questionnaire, # 问卷模型
            interview,    # 面试模型
            policy,       # 制度文档模型
            notification, # 通知模型
            talent_pool,  # 人才池模型
            user,         # 用户模型
            llm_log,      # LLM调用日志模型
            exam_analysis, # 试卷分析模型
        )
        # 创建所有已注册模型的数据库表
        await conn.run_sync(Base.metadata.create_all)
