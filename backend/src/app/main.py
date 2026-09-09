"""AI招聘助手 — FastAPI应用主入口"""
import os
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.database import init_db, async_session_factory
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

@asynccontextmanager # 异步上下文管理器，用于管理应用生命周期
# 应用生命周期管理：启动时初始化资源，关闭时清理
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化资源，关闭时清理

    启动时：
    - 初始化统一日志
    - 创建必要的目录（上传目录、政策文档目录）
    - 初始化数据库表
    - 启动后台定时任务

    关闭时：
    - 停止定时任务
    """
   # 启动日志
    setup_logging()
    # 查看是否携带JWT令牌
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be configured before starting the API")
    os.makedirs("uploads/resumes", exist_ok=True)  # 简历上传目录
    os.makedirs("dco_document", exist_ok=True)     # 制度文档目录

    # 启动各个数据库
    await init_db()  # 初始化数据库表
    logger.info("[%s] 数据库初始化完成", settings.APP_NAME)
    logger.info("[%s] LLM提供商: %s", settings.APP_NAME, settings.LLM_PROVIDER)

    # 插入七个邮件模版，有则不插入
    try:
        from app.services.notification_template_svc import ensure_default_templates
        async with async_session_factory() as seed_session:
            inserted, existed = await ensure_default_templates(seed_session)
            await seed_session.commit()
        logger.info("[%s] 邮件模板播种完成: 新增 %d 条, 已存在 %d 条", settings.APP_NAME, inserted, existed)
    except Exception:
        logger.exception("[%s] 邮件模板播种失败（不影响启动）", settings.APP_NAME)

    # 播种 11 个在招岗位的标准 JD（供简历分析自动套用；有则只补缺失、不覆盖已编辑）
    try:
        from app.services.position_jd_svc import ensure_default_position_jds
        async with async_session_factory() as seed_session:
            inserted, existed = await ensure_default_position_jds(seed_session)
            await seed_session.commit()
        logger.info("[%s] 岗位JD库播种完成: 新增 %d 条, 已存在 %d 条", settings.APP_NAME, inserted, existed)
    except Exception:
        logger.exception("[%s] 岗位JD库播种失败（不影响启动）", settings.APP_NAME)

    # 定时去拉取答题记录
    from app.services import ScheduledTasks
    task_runner = ScheduledTasks(async_session_factory)
    asyncio.create_task(task_runner.start(interval_seconds=300))
    logger.info("[%s] 定时任务已启动（间隔300s）", settings.APP_NAME)

    # 后台周期拉取 Workmenul 答卷 → 试卷分析（默认 60s，配置 WORKMENUL_API_BASE 后生效）
    from app.services.workmenul_sync import exam_sync_loop
    exam_sync_task = asyncio.create_task(
        exam_sync_loop(settings.EXAM_SYNC_INTERVAL_SECONDS)
    )
    logger.info("[%s] 启动完成", settings.APP_NAME)

    yield

    # ==== 关闭阶段 ====
    task_runner.stop()
    exam_sync_task.cancel()
    logger.info("[%s] 定时任务已停止", settings.APP_NAME)
    logger.info("[%s] 应用关闭", settings.APP_NAME)


# 创建FastAPI应用实例
app = FastAPI(
    title=settings.APP_NAME,
    description="AI驱动的智能招聘助手系统 — 简历分析、问卷评估、面试排期、制度问答",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置CORS跨域访问（允许前端开发服务器访问）
# 【小白导读】CORS = 跨源资源共享。浏览器出于安全默认禁止"网页A的JS请求B域名"，
#   除非 B 明确说"我允许A"。前端跑在 18016、后端在 18000，属于跨源，
#   所以后端必须把前端地址加进白名单，否则浏览器会拦截所有请求。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:18016", "http://127.0.0.1:18016"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 【小白导读】中间件 = 每个请求进出的"必经安检口"。
#   下面这个中间件给每个请求计时并写访问日志，是排查"哪个接口慢"的第一工具。
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """请求访问日志 — 记录方法/路径/状态码/耗时"""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.0fms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response

# ===== 注册所有API路由 =====
# 【小白导读】include_router = 把各功能模块的接口"挂"到主应用上。
#   每个 router 文件定义自己的 URL 前缀（如 /api/candidates）。
#   启动服务后打开 http://localhost:18000/docs 可视化浏览全部接口。
from app.routers import candidates, resumes, questionnaires, interviews, policy_agent, workflow, dashboard, auth, llm_observability, exam_analysis, scoring, jd_generator, notification_templates, position_jds

app.include_router(candidates.router)                # 候选人管理API
app.include_router(resumes.router)                   # 简历上传与分析API
app.include_router(questionnaires.router)             # 问卷管理API
app.include_router(interviews.router)                 # 面试排期API
app.include_router(policy_agent.router)               # 制度文档上传入库API（仅上传，RAG问答已迁移至 rag_service）
app.include_router(workflow.router)                   # 招聘流程编排API
app.include_router(dashboard.router)                  # 仪表盘统计API
app.include_router(auth.router)                       # 认证与权限API
app.include_router(llm_observability.router)          # LLM可观测性API
app.include_router(exam_analysis.router)              # 试卷分析API
app.include_router(scoring.router)                    # 评分优化API
app.include_router(jd_generator.router)               # JD生成API
app.include_router(notification_templates.router)     # 可配置邮件模板API
app.include_router(position_jds.router)               # 可配置岗位JD库API


@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    """根路径 — 返回API文档指引"""
    return {
        "message": "AI招聘助手系统",
        "docs": "/docs",       # Swagger API文档
        "api": "/api/health",  # 健康检查入口
    }


# ===== 全局异常处理 =====
# 【小白导读】异常处理器 = 接口代码抛错时的"统一善后"。
#   没有它们，用户会看到一大堆英文堆栈；有了它们，业务错误返回 4xx 带中文原因，
#   未预期错误返回 500 兜底（不泄露内部细节），同时把堆栈写进日志方便排查。

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一 HTTP 异常处理"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """统一参数错误处理"""
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局兜底异常处理 — 返回 500，避免堆栈泄露"""
    logger.exception(
        "未捕获异常: %s %s — %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )
