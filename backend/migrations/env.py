"""Alembic 迁移环境 — 异步 MySQL 支持"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# 导入项目配置和所有模型 Base
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
from app.config import settings
from app.database import Base

# 导入所有模型，确保 Base.metadata 包含全部表
from app.models import (
    Candidate, Resume, Interview, Questionnaire, QuestionnaireResponse, User, LLMCallLog,
    Notification, PolicyDocument, PolicyChatHistory,
    TalentPool, ExamAnalysis,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 使用项目配置中的数据库 URL
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 所有表的元数据
target_metadata = Base.metadata


def run_migrations_offline():
    """离线模式 — 生成 SQL 语句"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    """在线模式 — 连接到数据库执行迁移"""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
