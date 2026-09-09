"""数据库连接与会话管理 — SQLAlchemy 异步引擎 + 会话工厂

【小白导读】这个文件解决一个问题：后端 Python 代码怎么和 MySQL 数据库打交道？

核心概念（第一次接触后端必备）：
1. ORM（对象关系映射）：SQLAlchemy 是 Python 最流行的 ORM 库。
   没有它你要手写 SQL："INSERT INTO candidates (name) VALUES ('张三')"；
   有了它你只操作 Python 对象：Candidate(name="张三")，存库、查询都自动转成 SQL。
   models/ 目录下 class Candidate(Base) 的 Base 就是从这里导出的。
2. 异步（async）：普通方式查数据库时，整个程序要"原地等待"数据库返回；
   异步方式在等待期间可以去服务其他请求，高并发时吞吐量高得多。
   这就是为什么本项目所有数据库函数都带 async/await 关键字。
3. 连接池：每建一个数据库连接都很耗时，所以提前建好 20 个放在"池子"里复用，
   高峰期不够用还能临时再借最多 40 个（见下方参数）。
4. 会话（Session）：可以理解为"一次数据库操作的上下文"，
   你在会话里做的增删改查，最后 commit（提交）才真正写进数据库。
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


# ---- 第 1 步：创建异步数据库引擎（engine = 与数据库的"总连接管理器"）----
# 高并发防护：显式配置连接池，避免几千个并发任务把数据库连接打满（"Too many connections"）或使用到被服务端关闭的陈旧连接。
DB_URL = settings.DATABASE_URL
engine = create_async_engine(
    DB_URL,
    echo=settings.DEBUG,     # DEBUG 模式下把每条生成的 SQL 打印到日志，学习时很有用
    pool_size=20,            # 常驻连接数：平时池子里保持 20 条连接随时可用
    max_overflow=40,         # 高峰可临时借用的最大连接数（20 + 40 = 60 条封顶）
    pool_pre_ping=True,      # 每次取连接前先 ping 一下数据库，丢掉已断开的"死连接"
    pool_recycle=1800,       # 连接用满 30 分钟就强制换新，避开 MySQL 的 wait_timeout 踢连接
    pool_timeout=30,         # 池子被占满时，最多等 30 秒；再拿不到就报错
)
# ---- 第 2 步：创建异步会话工厂（每次请求来了，用它"生产"一个新会话）----
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
# expire_on_commit=False：commit 后不把对象属性标记为"过期"，
# 避免 commit 之后再用对象属性时又偷偷发一次查询（新手常见的性能坑）


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。

    models/ 目录下的每个 class Xxx(Base) 都继承它，
    SQLAlchemy 靠这个继承关系把"Python 类"登记成"数据库表"。
    """
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：每个需要数据库的接口自动获得一个会话

    【小白导读】在 router 文件里会看到函数参数写成：
        db: AsyncSession = Depends(get_db)
    意思是：调用这个接口时，FastAPI 自动执行 get_db() 并把会话传进来。
    本函数用 yield 实现了"自动收尾"：
      - 请求处理成功 → 自动 commit（把改动写进数据库）
      - 处理中抛异常 → 自动 rollback（撤销本次所有改动，防止写脏数据）
      - 无论成败     → 最后自动 close（把连接还给池子）
    路由代码只管写业务逻辑，完全不用操心这些。
    """
    async with async_session_factory() as session:
        try:
            yield session           # ← 把会话"借"给接口函数用
            await session.commit()   # 正常结束则提交
        except Exception:
            await session.rollback()  # 异常则回滚
            raise
        finally:
            await session.close()     # 最终关闭会话


async def init_db():
    """初始化数据库表结构（首次运行时创建所有表）

    原理：把 models/ 下所有模块 import 进来（import 的副作用是模型注册到 Base.metadata），
    然后 create_all 一次性建出所有不存在的表。已存在的表不会被改动。
    生产环境一般改用 Alembic 迁移（见 migrations/ 目录），这里作为开发兜底。
    """
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
            task_progress, # 异步任务进度模型（RabbitMQ 队列）
            scoring_iteration,  # 评分权重迭代模型
            notification_template,  # 可配置邮件模板模型
            position_jd,    # 可配置岗位JD库模型
        )
        # 创建所有已注册模型的数据库表
        await conn.run_sync(Base.metadata.create_all)
