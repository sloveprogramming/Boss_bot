"""招聘流程编排API — 触发 LangGraph 工作流 + 人才池管理

LangGraph 运行在后端进程内，节点直接操作数据库，无需 HTTP 同步。

高并发防护：start / auto-process 优先把「简历分析」任务发布到 RabbitMQ 队列，
由独立 worker 进程有界并发消费；RabbitMQ 不可用时（开发/单机环境）自动降级为
内联同步执行，保证接口始终可用。任务进度写入 task_progress 表，可轮询
GET /api/workflow/task/{task_id} 获取。
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.config import settings
from app.database import get_db
from app.models import (
    Candidate, TalentPool, TalentPoolStatus, TaskProgress, Resume,
    UserRole, User,
)
from app.dependencies import (
    require_role, get_current_user,
    ensure_candidate_visible, candidate_scope_cond,
)
from app.workflow import RecruitmentState, recruitment_graph
from app.schemas import (
    TalentPoolResponse, TalentPoolListResponse,
    ReactivateRequest, TalentPoolCreateRequest,
    WorkflowStatusResponse,
)
from app.services import notification_service
from app.queue.broker import publish_analysis_task, BrokerUnavailable

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workflow",
    tags=["招聘流程"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


def _build_initial_state(candidate, resume_text: str, job_description: str) -> RecruitmentState:
    """构造 LangGraph 初始 State（start / auto-process / worker 共用）。"""
    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "position": candidate.position,
        "email": candidate.email or "",
        "phone": candidate.phone or "",
        "status": candidate.status,
        "pipeline_stage": "resume",
        "resume_text": resume_text or "",
        "job_description": job_description or candidate.position,
        "match_score": candidate.match_score or 0,
        "errors": [],
        "retry_count": 0,
        "notifications_sent": [],
        "messages": [],
    }


async def _load_latest_resume_text(db: AsyncSession, candidate_id: int) -> str:
    """取候选人最新一份简历的纯文本；无简历或空文本时返回空串。

    前端「全自动流程」只传 candidate_id，不带简历文本；
    若流程第一步拿不到文本会直接空转，这里统一回填 DB 里已存的 raw_text。
    """
    result = await db.execute(
        select(Resume.raw_text)
        .where(Resume.candidate_id == candidate_id, Resume.raw_text.isnot(None))
        .order_by(Resume.id.desc())
        .limit(1)
    )
    text = result.scalar_one_or_none()
    return (text or "").strip()


# ====================================================================
# LangGraph 工作流触发
# ====================================================================

@router.post("/start/{candidate_id}")
async def start_workflow(
    candidate_id: int,
    resume_text: str = "",
    job_description: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动/继续 LangGraph 招聘流程

    高并发防护：优先把任务发布到 RabbitMQ 队列（由 worker 有界并发消费），
    返回 task_id 供前端轮询进度；RabbitMQ 不可用时降级为内联同步执行。
    """
    # 获取候选人（越权 404）
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    # 前端未传简历文本时，自动回填该候选人最新简历（否则流程第一步即空转）
    if not resume_text.strip():
        resume_text = await _load_latest_resume_text(db, candidate_id)

    initial_state = _build_initial_state(candidate, resume_text, job_description)

    # 高并发防护：优先入队（RabbitMQ）；broker 不可用时降级为内联同步
    if settings.TASK_ENABLED:
        try:
            # 只入队，不写 task_progress：进度行统一由 worker 消费时 upsert，
            # 避免 API 与 worker 双写同一 task_id 撞唯一索引。
            task_id = await publish_analysis_task(candidate_id, resume_text, job_description)
            logger.info("候选人 %s 工作流已入队 (task_id=%s)", candidate_id, task_id)
            return {
                "candidate_id": candidate_id,
                "task_id": task_id,
                "queued": True,
                "message": "已加入分析队列，请轮询 /api/workflow/task/{task_id} 获取进度",
            }
        except BrokerUnavailable as e:
            logger.warning("RabbitMQ 不可用，降级为内联同步执行: %s", e)

    # 降级路径：直接在当前请求内执行
    result_state = await recruitment_graph.ainvoke(initial_state)
    logger.info(
        "候选人 %s 工作流内联执行完成: status=%s score=%s",
        candidate_id, result_state.get("status", candidate.status),
        result_state.get("match_score", candidate.match_score),
    )

    return {
        "candidate_id": candidate_id,
        "queued": False,
        "final_status": result_state.get("status", candidate.status),
        "match_score": result_state.get("match_score", candidate.match_score),
        "job_category": result_state.get("job_category", candidate.job_category),
        "pipeline_stage": result_state.get("pipeline_stage", ""),
        "error": result_state.get("errors", []),
    }


# ====================================================================
# 流程状态 & 自动处理
# ====================================================================

@router.get("/status/{candidate_id}")
async def get_workflow_status(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取候选人当前招聘流程进度和下一步待办"""
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    # 状态 → 阶段/操作映射
    status_stage = {
        "new":        {"stage": "简历分析",     "action": "upload_resume",      "auto": True},
        "parsed":     {"stage": "简历分析",     "action": "classify",          "auto": True},
        "classified": {"stage": "简历分析",     "action": "analyze",           "auto": True},
        "analyzed":   {"stage": "评分分流",     "action": "check_threshold",   "auto": True},
        "talent_pool":{"stage": "人才池",       "action": "wait_for_reactivate","auto": False},
        "q_sent":     {"stage": "问卷评估",     "action": "wait_for_completion","auto": False},
        "q_done":     {"stage": "面试排期",     "action": "schedule_interview", "auto": True},
        "scheduled":  {"stage": "面试阶段",     "action": "conduct_interview",  "auto": False},
        "interviewed":{"stage": "录用决策",     "action": "make_decision",     "auto": False},
        "rejected":   {"stage": "已结束",       "action": "send_rejection",    "auto": True},
        "hired":      {"stage": "已录用",       "action": "send_offer",        "auto": True},
    }

    info = status_stage.get(candidate.status, {"stage": "未知", "action": "unknown", "auto": False})

    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "current_status": candidate.status,
        "stage": info["stage"],
        "next_action": info["action"],
        "auto_available": info["auto"],
        "match_score": candidate.match_score,
    }


@router.post("/auto-process/{candidate_id}")
async def auto_process(
    candidate_id: int,
    resume_text: str = "",
    job_description: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """自动执行下一个流程步骤（触发 LangGraph 从当前状态继续执行）"""
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    # 对于简单操作（发通知），直接执行
    if candidate.status == "rejected":
        await notification_service.send(
            candidate_id=candidate_id,
            template="rejection",
            channel="email",
            db=db,
        )
        logger.info("候选人 %s 已发送拒绝通知 (auto-process)", candidate_id)
        return {"candidate_id": candidate_id, "action": "send_rejection", "status": "ok"}

    if candidate.status == "hired":
        await notification_service.send(
            candidate_id=candidate_id,
            template="offer",
            channel="email",
            db=db,
        )
        logger.info("候选人 %s 已发送录用通知 (auto-process)", candidate_id)
        return {"candidate_id": candidate_id, "action": "send_offer", "status": "ok"}

    # 对于需要流程序列的操作，优先入队（RabbitMQ），不可用时降级内联
    # 前端未传简历文本时，自动回填该候选人最新简历（否则流程第一步即空转）
    if not resume_text.strip():
        resume_text = await _load_latest_resume_text(db, candidate_id)

    initial_state = _build_initial_state(candidate, resume_text, job_description)

    if settings.TASK_ENABLED:
        try:
            # 只入队，不写 task_progress：进度行统一由 worker 消费时 upsert，
            # 避免 API 与 worker 双写同一 task_id 撞唯一索引。
            task_id = await publish_analysis_task(candidate_id, resume_text, job_description)
            logger.info("候选人 %s 自动处理已入队 (task_id=%s)", candidate_id, task_id)
            return {
                "candidate_id": candidate_id,
                "task_id": task_id,
                "queued": True,
                "action": "langgraph_flow",
                "status": "queued",
                "message": "已加入分析队列，请轮询 /api/workflow/task/{task_id} 获取进度",
            }
        except BrokerUnavailable as e:
            logger.warning("RabbitMQ 不可用，降级为内联同步执行: %s", e)

    # 降级路径：直接在当前请求内执行
    result_state = await recruitment_graph.ainvoke(initial_state)
    new_status = result_state.get("status", candidate.status)
    logger.info("候选人 %s 自动处理内联执行完成: status=%s", candidate_id, new_status)

    return {
        "candidate_id": candidate_id,
        "queued": False,
        "action": "langgraph_flow",
        "status": "ok",
        "result_status": new_status,
        "match_score": result_state.get("match_score"),
    }


@router.get("/task/{task_id}")
async def get_task_progress(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """查询异步分析任务的进度与结果（配合 RabbitMQ 队列使用）

    任务入队后返回 task_id，前端据此轮询本接口：
      - status: pending/received/running/success/failure
      - progress: 0~100
      - current_stage / stage_message: 当前所处节点
      - result: 成功时的 {final_status, match_score, job_category}
      - error: 失败原因（重试耗尽时）

    越权：任务关联的候选人不在当前 HR 名下时，一律 404（不泄露任务存在性）。
    """
    result = await db.execute(
        select(TaskProgress).where(TaskProgress.task_id == task_id)
    )
    tp = result.scalar_one_or_none()
    if not tp:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    # 候选人仍存在时校验归属；候选已被删除则不额外拦截（属历史数据）
    if tp.candidate_id:
        await ensure_candidate_visible(db, current_user, tp.candidate_id)
    return tp.to_dict()


@router.get("/pipeline")
async def get_pipeline(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取招聘管道整体概览（各阶段人数统计）；HR 仅统计自己名下候选人"""
    cond = candidate_scope_cond(current_user)

    def _apply(stmt):
        return stmt.where(cond) if cond is not None else stmt

    # 各状态人数
    status_counts = await db.execute(
        _apply(select(Candidate.status, func.count(Candidate.id)))
        .group_by(Candidate.status)
    )
    counts = dict(status_counts.all())

    # 最近20个候选人
    recent = await db.execute(
        _apply(
            select(Candidate)
            .order_by(Candidate.created_at.desc())
            .limit(20)
        )
    )
    recent_candidates = recent.scalars().all()

    return {
        "total": sum(counts.values()),
        "status_counts": counts,
        "stages": {
            "新候选人":     counts.get("new", 0),
            "简历已分析":   counts.get("analyzed", 0),
            "人才池":       counts.get("talent_pool", 0),
            "问卷已发送":   counts.get("q_sent", 0),
            "问卷已完成":   counts.get("q_done", 0),
            "面试已排期":   counts.get("scheduled", 0),
            "已面试":       counts.get("interviewed", 0),
            "已录用":       counts.get("hired", 0),
            "已拒绝":       counts.get("rejected", 0),
        },
        "recent": [
            {
                "id": c.id,
                "name": c.name,
                "position": c.position,
                "status": c.status,
                "match_score": c.match_score,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
            for c in recent_candidates
        ],
    }


# ====================================================================
# 人才池管理
# ====================================================================

@router.get("/talent-pool", response_model=TalentPoolListResponse)
async def list_talent_pool(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取人才池列表（分页）；HR 仅看自己名下候选人的人才池记录"""
    cond = candidate_scope_cond(current_user)

    query = select(TalentPool).join(Candidate, TalentPool.candidate_id == Candidate.id)
    count_query = (
        select(func.count(TalentPool.id))
        .join(Candidate, TalentPool.candidate_id == Candidate.id)
    )
    if cond is not None:
        query = query.where(cond)
        count_query = count_query.where(cond)

    if status:
        query = query.where(TalentPool.status == status)
        count_query = count_query.where(TalentPool.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(TalentPool.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return TalentPoolListResponse(
        total=total,
        items=[TalentPoolResponse.model_validate(t) for t in items],
        page=page,
        page_size=page_size,
    )


async def _load_pool_entry_visible(db, current_user: User, pool_id: int) -> TalentPool:
    """按人才池记录加载并校验其候选人可见（越权 404）"""
    result = await db.execute(select(TalentPool).where(TalentPool.id == pool_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="人才池记录不存在")
    await ensure_candidate_visible(db, current_user, entry.candidate_id)
    return entry


@router.get("/talent-pool/{pool_id}", response_model=TalentPoolResponse)
async def get_talent_pool_entry(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取人才池单条记录详情（越权 404）"""
    return await _load_pool_entry_visible(db, current_user, pool_id)


@router.put("/talent-pool/{pool_id}/contact")
async def contact_talent_pool_entry(
    pool_id: int,
    note: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记已联系人才池中的候选人"""
    entry = await _load_pool_entry_visible(db, current_user, pool_id)

    entry.status = TalentPoolStatus.CONTACTED.value
    entry.contacted_at = __import__("datetime").datetime.utcnow()
    entry.contact_note = note
    await db.flush()

    return {"status": "ok", "message": "已标记联系"}


@router.post("/talent-pool/reactivate")
async def reactivate_from_pool(
    data: ReactivateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从人才池重新激活候选人（重置为新流程）"""
    pool_entry = await _load_pool_entry_visible(db, current_user, data.talent_pool_id)
    candidate = await ensure_candidate_visible(db, current_user, pool_entry.candidate_id)

    # 重置状态
    candidate.status = "new"
    candidate.position = data.position
    candidate.talent_pool_id = None
    candidate.talent_pool_reason = None

    pool_entry.status = TalentPoolStatus.REACTIVATED.value
    pool_entry.reactivated_at = __import__("datetime").datetime.utcnow()
    pool_entry.reactivated_for = data.position

    await db.flush()

    logger.info(
        "候选人 %s 从人才池重新激活 (pool_id=%s, 新岗位=%s)",
        candidate.id, pool_entry.id, data.position,
    )

    return {
        "action": "reactivate",
        "message": f"候选人{candidate.name}已从人才池重新激活，应聘岗位: {data.position}",
        "candidate_id": candidate.id,
        "position": data.position,
    }


@router.post("/talent-pool/create")
async def create_talent_pool_entry(
    data: TalentPoolCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """由工作流自动创建人才池记录"""
    candidate = await ensure_candidate_visible(db, current_user, data.candidate_id)

    # 检查是否已有人才池记录
    existing = await db.execute(
        select(TalentPool).where(TalentPool.candidate_id == data.candidate_id)
    )
    if existing.scalar_one_or_none():
        return {"action": "talent_pool_exists", "message": "该候选人已在人才池中"}

    pool_entry = TalentPool(
        candidate_id=data.candidate_id,
        original_position=data.position,
        match_score=data.match_score,
        strengths=candidate.tags or [],
        pool_reason=f"匹配度{data.match_score}分，未达当前岗位要求但具备潜力",
        suitable_positions=[],
        skills=candidate.tags or [],
        status=TalentPoolStatus.ACTIVE.value,
    )
    db.add(pool_entry)
    await db.flush()

    candidate.status = "talent_pool"
    candidate.talent_pool_id = pool_entry.id
    candidate.talent_pool_reason = pool_entry.pool_reason
    await db.flush()

    logger.info(
        "候选人 %s 已创建人才池记录 (pool_id=%s, score=%.1f)",
        candidate.id, pool_entry.id, data.match_score,
    )

    return {
        "action": "created",
        "talent_pool_id": pool_entry.id,
        "candidate_id": data.candidate_id,
        "message": "人才池记录已创建",
    }


# ====================================================================
# MCP Tools & Function Calling 端点
# ====================================================================

from pydantic import BaseModel


class FunctionCallRequest(BaseModel):
    query: str
    system_prompt: str = ""
    session_id: Optional[str] = None      # 短期记忆会话 ID（可选）


class FunctionCallResponse(BaseModel):
    fc_result: str
    fc_tool_calls: list = []
    fc_response: str


@router.get("/mcp/tools")
async def list_mcp_tools():
    """列出所有可用的 MCP Tools（供 LLM Function Calling 使用）"""
    from app.mcp import get_tool_definitions_openai
    return {
        "tools": get_tool_definitions_openai(),
        "total": len(get_tool_definitions_openai()),
    }


@router.post("/function-call", response_model=FunctionCallResponse)
async def function_call_endpoint(
    data: FunctionCallRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """Function Calling 端点 — LLM 自主选择并执行 MCP Tools

    工作流程：
    1. 接收用户自然语言查询
    2. LLM 分析查询，自动选择合适的工具
    3. 执行工具并收集结果
    4. LLM 基于结果生成最终回复

    示例查询：
    - "帮我查一下所有 Python 岗位的候选人"
    - "查看候选人 ID 为 3 的详细信息"
    - "给我发一份仪表盘统计"
    - "发送面试邀请邮件给候选人 5"
    - "查询明天的面试安排"

    工具调用透传 current_user 做数据范围隔离（HR 只见自己名下数据）。
    """
    from app.workflow.nodes import run_function_calling
    from app.agents.session_memory import get_history, append_message

    # 短期记忆：有 session_id 时注入历史上下文（最近 N 轮）
    history = get_history(data.session_id) if data.session_id else []
    result = await run_function_calling(
        query=data.query,
        system_prompt=data.system_prompt,
        history=history,
        user=current_user,
    )
    if data.session_id:
        append_message(data.session_id, "user", data.query)
        append_message(data.session_id, "assistant", result.get("fc_response", ""))
    return result


@router.post("/function-call/graph/{candidate_id}")
async def function_call_in_graph(
    candidate_id: int,
    data: FunctionCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """在 LangGraph 工作流中执行 Function Calling

    将用户查询作为 fc_query 注入 State，通过 LangGraph 执行 Function Calling 节点。
    适合在候选人处理流程中自然语言查询相关数据。
    """
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    initial_state: RecruitmentState = {
        "candidate_id": candidate_id,
        "candidate_name": candidate.name,
        "position": candidate.position,
        "email": candidate.email or "",
        "phone": candidate.phone or "",
        "status": candidate.status,
        "pipeline_stage": "function_call",
        "resume_text": "",
        "job_description": "",
        "match_score": candidate.match_score or 0,
        "fc_query": data.query,
        "errors": [],
        "retry_count": 0,
        "notifications_sent": [],
        "messages": [],
        "user": current_user,  # 透传给工具做数据隔离
    }

    from app.workflow.nodes import function_calling_node
    result_state = await function_calling_node(initial_state)

    return {
        "candidate_id": candidate_id,
        "query": data.query,
        "fc_result": result_state.get("fc_result", ""),
        "fc_tool_calls": result_state.get("fc_tool_calls", []),
        "fc_response": result_state.get("fc_response", ""),
    }


# ====================================================================
# SSE 流式输出端点
# ====================================================================

from fastapi.responses import StreamingResponse
from app.utils import (
    token_event, progress_event, done_event, error_event, sse_event,
)


@router.post("/function-call/stream")
async def function_call_stream(
    data: FunctionCallRequest,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """Function Calling SSE 流式端点（ReAct 多轮工具循环）

    流式输出整个 Function Calling 过程：
    1. progress: 思考阶段（正在分析查询）
    2. 循环: LLM 决定工具 → tool_call / tool_result 事件 → 结果回填 → 再思考
       （最多 MAX_TOOL_ROUNDS 轮，LLM 认为信息足够即停止）
    3. token: 逐 token 流式输出最终回复
    4. done: 完成

    工具调用透传当前 HR/admin 身份做数据隔离。SSE 响应是延迟执行的
    generator，进入流前先快照用户身份，避免在响应期间访问已释放的 ORM 会话。
    """
    import json
    from types import SimpleNamespace
    from app.mcp import get_tool_definitions_openai, execute_tool_directly
    from app.config import settings
    from openai import AsyncOpenAI
    from app.agents.session_memory import get_history, append_message

    MAX_TOOL_ROUNDS = 5

    # 快照发起者身份（id/username/role），供 generate() 内工具调用透传
    viewer = SimpleNamespace(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
    )

    async def generate():
        tools = get_tool_definitions_openai()
        system = data.system_prompt or FC_SYSTEM_PROMPT_STREAM

        # 短期记忆：有 session_id 时注入该会话最近的历史消息
        history = get_history(data.session_id) if data.session_id else []
        messages = list(history) + [{"role": "user", "content": data.query}]

        # 阶段 1: 分析查询
        yield progress_event("analysis", "running", "正在分析您的查询...", 10)

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        tool_call_records = []
        used_tools = False
        final_text = ""

        # ===== 阶段 2: ReAct 循环 —— 调工具 → 看结果 → 决定下一步 =====
        for round_i in range(MAX_TOOL_ROUNDS):
            pct = min(25 + round_i * 10, 60)
            yield progress_event(
                "tool_selection", "running",
                f"AI 正在思考第 {round_i + 1} 步...", pct,
            )

            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=4096,
            )

            message = response.choices[0].message

            # LLM 认为信息足够 → 跳出循环，生成最终回复
            if not message.tool_calls:
                break

            used_tools = True

            # 把本轮 assistant 的工具调用决策追加进上下文
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            })

            # 执行本轮每个工具调用
            for i, tc in enumerate(message.tool_calls):
                yield progress_event(
                    f"executing_{tc.function.name}", "running",
                    f"正在执行: {tc.function.name}...", min(pct + 5 + i * 5, 65),
                )

                try:
                    func_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.warning("工具 %s 参数 JSON 解析失败，使用空参数: %s",
                                   tc.function.name, tc.function.arguments)
                    func_args = {}

                result = await execute_tool_directly(
                    tc.function.name, func_args, user=viewer
                )

                tool_call_records.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": func_args,
                })

                # 发送工具调用事件
                yield sse_event("tool_call", {
                    "name": tc.function.name,
                    "arguments": func_args,
                })
                yield sse_event("tool_result", {
                    "tool": tc.function.name,
                    "summary": result[:300] + ("..." if len(result) > 300 else ""),
                })

                # 工具结果回填进对话，供下一轮 LLM 使用
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            logger.warning("Function Calling 达到最大工具轮数 %d，强制生成最终回复", MAX_TOOL_ROUNDS)

        # ===== 阶段 3: 最终回复，逐 token 流式输出 =====
        yield progress_event("generating", "running", "正在生成回复...", 75)

        if not used_tools:
            # 无需工具：第一轮回复已是最终答案，直接分块流式输出（省一次 LLM 调用）
            final_text = response.choices[0].message.content or ""
            for i in range(0, len(final_text), 16):
                yield token_event(final_text[i:i + 16])
        else:
            # 有工具结果：基于完整对话上下文流式生成最终回复
            stream_response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                temperature=0.3,
                max_tokens=4096,
                stream=True,
            )
            async for chunk in stream_response:
                content = chunk.choices[0].delta.content
                if content:
                    final_text += content
                    yield token_event(content)

        # 短期记忆：保存本轮对话（下次同 session_id 请求可解析上下文指代）
        if data.session_id:
            append_message(data.session_id, "user", data.query)
            append_message(data.session_id, "assistant", final_text)

        yield done_event("任务完成", {
            "tool_calls": tool_call_records,
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓存
        },
    )


FC_SYSTEM_PROMPT_STREAM = """你是 AI 招聘助手的智能调度器。你可以使用以下工具来回答用户关于招聘系统的问题。

规则：
1. 根据用户的问题，选择合适的工具
2. 如果需要候选人信息，先查候选人列表，再查详情
3. 制度/规章类问题（年假、试用期、报销、考勤、加班、福利、入离职等）必须调用 query_policy_docs 工具查询知识库；若工具返回 error，向用户说明制度知识库服务暂不可用
4. 如果用户问"最近"或"今天"，使用日期相关的筛选
5. 发送邮件前，先确认候选人存在
6. 如果用户的问题不需要工具，直接回答即可
7. 用户要找 XX 岗位的 JD / 岗位职责 / 招聘要求模板参考时，调用 jd_reference_search 工具；若工具返回 error，向用户说明全网搜索功能暂不可用
8. 回答制度问题时，如工具结果包含 cited_sources，在回复末尾附上引用的文档名
9. 始终返回清晰、结构化的中文回复"""


@router.post("/start/{candidate_id}/stream")
async def start_workflow_stream(
    candidate_id: int,
    resume_text: str = "",
    job_description: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动 LangGraph 招聘流程（SSE 流式输出）

    流式输出每个节点的执行状态：
    1. parse_resume → 2. classify → 3. analyze → 4. 分流决策 → ...

    每个节点执行时发送 progress 事件，完成时发送 done 事件。
    """
    candidate = await ensure_candidate_visible(db, current_user, candidate_id)

    # 节点列表及其描述
    workflow_steps = [
        ("parse_resume", "解析简历", 10, 30),
        ("classify", "岗位分类", 30, 45),
        ("analyze", "智能分析匹配度", 45, 70),
        ("decision", "分流决策", 70, 85),
        ("finalize", "完成处理", 85, 100),
    ]

    async def generate():
        initial_state: RecruitmentState = {
            "candidate_id": candidate_id,
            "candidate_name": candidate.name,
            "position": candidate.position,
            "email": candidate.email or "",
            "phone": candidate.phone or "",
            "status": candidate.status,
            "pipeline_stage": "resume",
            "resume_text": resume_text or "",
            "job_description": job_description or candidate.position,
            "match_score": candidate.match_score or 0,
            "errors": [],
            "retry_count": 0,
            "notifications_sent": [],
            "messages": [],
        }

        # 使用 LangGraph astream_events 获取节点级别的进度
        try:
            async for event in recruitment_graph.astream_events(
                initial_state,
                version="v2",
            ):
                event_type = event.get("event", "")
                if event_type == "on_chain_start":
                    name = event.get("name", "")
                    # 查找匹配的步骤
                    for step_name, step_desc, pct_start, pct_end in workflow_steps:
                        if step_name == name or name in step_name:
                            yield progress_event(
                                name, "running",
                                f"正在{step_desc}...", pct_start,
                            )
                            break

                elif event_type == "on_chain_end":
                    name = event.get("name", "")
                    for step_name, step_desc, pct_start, pct_end in workflow_steps:
                        if step_name == name or name in step_name:
                            yield progress_event(
                                name, "done",
                                f"{step_desc}完成", pct_end,
                            )
                            break

        except Exception as e:
            yield error_event("工作流执行失败", str(e))
            return

        # 读取最终状态
        yield done_event("招聘流程处理完成", {
            "candidate_id": candidate_id,
            "status": candidate.status,
            "match_score": candidate.match_score,
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
