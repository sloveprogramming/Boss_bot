"""首次部署 — 创建系统管理员

使用方法:
    python seed_admin.py
    python seed_admin.py --username admin --password mypassword --email admin@example.com
"""
import asyncio
import argparse
from pathlib import Path
from sqlalchemy import select

# 添加 backend 到 Python 路径
import sys
sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))

from app.database import async_session_factory, init_db
from app.models import User, UserRole
from app.dependencies import hash_password


async def seed_admin(username: str, password: str, email: str | None = None):
    """创建管理员，如果已存在则跳过"""
    # 确保数据库表已创建
    await init_db()

    async with async_session_factory() as db:
        # 检查是否已存在管理员
        result = await db.execute(
            select(User).where(User.role == UserRole.ADMIN.value)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"[跳过] 管理员已存在: {existing.username}")
            return

        # 检查用户名冲突
        result = await db.execute(select(User).where(User.username == username))
        if result.scalar_one_or_none():
            print(f"[错误] 用户名 '{username}' 已被占用")
            return

        # 创建管理员
        user = User(
            username=username,
            hashed_password=hash_password(password),
            role=UserRole.ADMIN.value,
            email=email,
        )
        db.add(user)
        await db.commit()
        print(f"[成功] 管理员已创建: {username}")
        print(f"       角色: admin")
        print(f"       请使用 /api/auth/login 登录")


def main():
    parser = argparse.ArgumentParser(description="创建系统管理员")
    parser.add_argument("--username", default="admin", help="管理员用户名 (默认: admin)")
    parser.add_argument("--password", default="admin123", help="管理员密码 (默认: admin123)")
    parser.add_argument("--email", default=None, help="邮箱地址 (可选)")
    parser.add_argument("--db-url", default=None,
                        help="数据库连接字符串 (默认使用 .env 中的配置)")
    args = parser.parse_args()

    if args.db_url:
        import os
        os.environ["DATABASE_URL"] = args.db_url

    asyncio.run(seed_admin(args.username, args.password, args.email))


if __name__ == "__main__":
    main()
