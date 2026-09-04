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


@asynccontextmanager
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
    # ==== 启动阶段 ====
    setup_logging()
    if not settings.JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be configured before starting the API")
    os.makedirs("uploads/resumes", exist_ok=True)  # 简历上传目录
    os.makedirs("dco_document", exist_ok=True)     # 制度文档目录

    await init_db()  # 初始化数据库表
    logger.info("[%s] 数据库初始化完成", settings.APP_NAME)
    logger.info("[%s] LLM提供商: %s", settings.APP_NAME, settings.LLM_PROVIDER)

    # 启动后台定时任务（每5分钟检查一次）
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:18016", "http://127.0.0.1:18016"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
from app.routers import candidates, resumes, questionnaires, interviews, policy_agent, workflow, dashboard, auth, llm_observability, exam_analysis, scoring

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
