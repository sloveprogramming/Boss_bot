"""招聘流程编排API — 触发 LangGraph 工作流 + 人才池管理

LangGraph 运行在后端进程内，节点直接操作数据库，无需 HTTP 同步。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.database import get_db
from app.models import Candidate, TalentPool, TalentPoolStatus
from app.workflow import RecruitmentState, recruitment_graph
from app.schemas import (
    TalentPoolResponse, TalentPoolListResponse,
    ReactivateRequest, TalentPoolCreateRequest,
    WorkflowStatusResponse,
)
from app.services import notification_service

router = APIRouter(prefix="/api/workflow", tags=["招聘流程"])


# ====================================================================
# LangGraph 工作流触发
# ====================================================================

@router.post("/start/{candidate_id}")
async def start_workflow(
    candidate_id: int,
    resume_text: str = "",
    job_description: str = "",
    db: AsyncSession = Depends(get_db),
):
    """启动/继续 LangGraph 招聘流程

    LangGraph 从入口节点开始执行，逐节点运行直到遇到等待点（END）。
    各节点直接操作数据库，无需额外同步。
    """
    # 获取候选人
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

    # 构造初始 State（从数据库加载当前状态）
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

    # 执行 LangGraph
    result_state = await recruitment_graph.ainvoke(initial_state)

    return {
        "candidate_id": candidate_id,
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
):
    """获取候选人当前招聘流程进度和下一步待办"""
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

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
):
    """自动执行下一个流程步骤（触发 LangGraph 从当前状态继续执行）"""
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

    # 对于简单操作（发通知），直接执行
    if candidate.status == "rejected":
        await notification_service.send(
            candidate_id=candidate_id,
            template="rejection",
            channel="email",
            db=db,
        )
        return {"candidate_id": candidate_id, "action": "send_rejection", "status": "ok"}

    if candidate.status == "hired":
        await notification_service.send(
            candidate_id=candidate_id,
            template="offer",
            channel="email",
            db=db,
        )
        return {"candidate_id": candidate_id, "action": "send_offer", "status": "ok"}

    # 对于需要流程序列的操作，触发 LangGraph
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

    result_state = await recruitment_graph.ainvoke(initial_state)
    new_status = result_state.get("status", candidate.status)

    return {
        "candidate_id": candidate_id,
        "action": "langgraph_flow",
        "status": "ok",
        "result_status": new_status,
        "match_score": result_state.get("match_score"),
    }


@router.get("/pipeline")
async def get_pipeline(db: AsyncSession = Depends(get_db)):
    """获取招聘管道整体概览（各阶段人数统计）"""
    # 各状态人数
    status_counts = await db.execute(
        select(Candidate.status, func.count(Candidate.id))
        .group_by(Candidate.status)
    )
    counts = dict(status_counts.all())

    # 最近20个候选人
    recent = await db.execute(
        select(Candidate)
        .order_by(Candidate.created_at.desc())
        .limit(20)
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
):
    """获取人才池列表（分页）"""
    query = select(TalentPool)
    count_query = select(func.count(TalentPool.id))

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


@router.get("/talent-pool/{pool_id}", response_model=TalentPoolResponse)
async def get_talent_pool_entry(pool_id: int, db: AsyncSession = Depends(get_db)):
    """获取人才池单条记录详情"""
    result = await db.execute(select(TalentPool).where(TalentPool.id == pool_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="人才池记录不存在")
    return entry


@router.put("/talent-pool/{pool_id}/contact")
async def contact_talent_pool_entry(
    pool_id: int,
    note: str = "",
    db: AsyncSession = Depends(get_db),
):
    """标记已联系人才池中的候选人"""
    result = await db.execute(select(TalentPool).where(TalentPool.id == pool_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="人才池记录不存在")

    entry.status = TalentPoolStatus.CONTACTED.value
    entry.contacted_at = __import__("datetime").datetime.utcnow()
    entry.contact_note = note
    await db.flush()

    return {"status": "ok", "message": "已标记联系"}


@router.post("/talent-pool/reactivate")
async def reactivate_from_pool(
    data: ReactivateRequest,
    db: AsyncSession = Depends(get_db),
):
    """从人才池重新激活候选人（重置为新流程）"""
    result = await db.execute(
        select(TalentPool).where(TalentPool.id == data.talent_pool_id)
    )
    pool_entry = result.scalar_one_or_none()
    if not pool_entry:
        raise HTTPException(status_code=400, detail="人才池记录不存在")

    result = await db.execute(
        select(Candidate).where(Candidate.id == pool_entry.candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=400, detail="候选人不存在")

    # 重置状态
    candidate.status = "new"
    candidate.position = data.position
    candidate.talent_pool_id = None
    candidate.talent_pool_reason = None

    pool_entry.status = TalentPoolStatus.REACTIVATED.value
    pool_entry.reactivated_at = __import__("datetime").datetime.utcnow()
    pool_entry.reactivated_for = data.position

    await db.flush()

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
):
    """由工作流自动创建人才池记录"""
    result = await db.execute(
        select(Candidate).where(Candidate.id == data.candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=400, detail=f"候选人不存在: {data.candidate_id}")

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
async def function_call_endpoint(data: FunctionCallRequest):
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
    """
    from app.workflow.nodes import run_function_calling
    result = await run_function_calling(
        query=data.query,
        system_prompt=data.system_prompt,
    )
    return result


@router.post("/function-call/graph/{candidate_id}")
async def function_call_in_graph(
    candidate_id: int,
    data: FunctionCallRequest,
    db: AsyncSession = Depends(get_db),
):
    """在 LangGraph 工作流中执行 Function Calling

    将用户查询作为 fc_query 注入 State，通过 LangGraph 执行 Function Calling 节点。
    适合在候选人处理流程中自然语言查询相关数据。
    """
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

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
async def function_call_stream(data: FunctionCallRequest):
    """Function Calling SSE 流式端点

    流式输出整个 Function Calling 过程：
    1. progress: 思考阶段（正在分析查询）
    2. progress: 工具选择（LLM 决定调用哪些工具）
    3. tool_call: 工具调用详情
    4. tool_result: 工具执行结果摘要
    5. progress: 生成回复阶段
    6. token: 逐 token 流式输出最终回复
    7. done: 完成
    """
    import json
    from app.mcp import get_tool_definitions_openai, execute_tool_directly
    from app.config import settings
    from openai import AsyncOpenAI

    async def generate():
        tools = get_tool_definitions_openai()
        system = data.system_prompt or FC_SYSTEM_PROMPT_STREAM
        messages = [{"role": "user", "content": data.query}]

        # 阶段 1: 分析查询
        yield progress_event("analysis", "running", "正在分析您的查询...", 10)

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        # 阶段 2: LLM 决定工具
        yield progress_event("tool_selection", "running", "AI 正在选择合适的工具...", 25)

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=4096,
        )

        choice = response.choices[0]
        message = choice.message

        if not message.tool_calls:
            # 无工具调用，直接流式输出回复
            yield progress_event("generating", "running", "正在生成回复...", 50)
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
                    yield token_event(content)
            yield done_event("回复完成")
            return

        # 阶段 3: 执行工具
        tool_call_records = []
        tool_results = []
        for i, tc in enumerate(message.tool_calls):
            yield progress_event(
                f"executing_{tc.function.name}", "running",
                f"正在执行: {tc.function.name}...", 40 + i * 10,
            )

            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            result = await execute_tool_directly(tc.function.name, func_args)

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

            tool_results.append({
                "tool_call_id": tc.id,
                "role": "tool",
                "content": result,
            })

        # 阶段 4: 基于工具结果流式生成最终回复
        yield progress_event("generating", "running", "正在基于结果生成回复...", 70)

        final_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": data.query},
        ]
        final_messages.append({
            "role": "assistant",
            "content": message.content,
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
        final_messages.extend(tool_results)

        stream_response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=final_messages,
            temperature=0.3,
            max_tokens=4096,
            stream=True,
        )

        async for chunk in stream_response:
            content = chunk.choices[0].delta.content
            if content:
                yield token_event(content)

        yield done_event("任务完成", {
            "tool_calls": tool_call_records,
        })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


FC_SYSTEM_PROMPT_STREAM = """你是 AI 招聘助手的智能调度器。你可以使用以下工具来回答用户关于招聘系统的问题。

规则：
1. 根据用户的问题，选择合适的工具
2. 如果需要候选人信息，先查候选人列表，再查详情
3. 如果用户问"最近"或"今天"，使用日期相关的筛选
4. 发送邮件前，先确认候选人存在
5. 如果用户的问题不需要工具，直接回答即可
6. 始终返回清晰、结构化的中文回复"""


@router.post("/start/{candidate_id}/stream")
async def start_workflow_stream(
    candidate_id: int,
    resume_text: str = "",
    job_description: str = "",
    db: AsyncSession = Depends(get_db),
):
    """启动 LangGraph 招聘流程（SSE 流式输出）

    流式输出每个节点的执行状态：
    1. parse_resume → 2. classify → 3. analyze → 4. 分流决策 → ...

    每个节点执行时发送 progress 事件，完成时发送 done 事件。
    """
    result = await db.execute(
        select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")

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
