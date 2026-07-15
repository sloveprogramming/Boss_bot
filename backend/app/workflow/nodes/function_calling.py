"""Function Calling 节点 — LLM 自主选择并调用 MCP Tools

工作流中的"智能调度"节点：
1. 接收用户自然语言查询（"帮我查 Python 候选人"）
2. 查询 + 可用工具列表（5 个 MCP Tools）发给 LLM
3. LLM 决定调用哪些工具 → 执行 → 收集结果
4. 基于结果生成最终回复 → 写回 State

可在 LangGraph 流程中注册，也可通过 API 直接调用。
"""
import json                                                         # 解析 LLM 的 JSON 参数
from typing import Optional
from app.workflow.state import RecruitmentState                     # 流程状态对象
from app.mcp.client import get_tool_definitions_openai, execute_tool_directly  # 工具定义 + 执行
from app.agents.llm_client import llm_client                        # 全局 LLM 客户端


# ===== Function Calling 系统提示词 =====
FC_SYSTEM_PROMPT = """你是 AI 招聘助手的智能调度器。你可以使用以下工具来回答用户关于招聘系统的问题。

规则：
1. 根据用户的问题，选择合适的工具
2. 如果需要候选人信息，先查候选人列表，再查详情
3. 如果用户问"最近"或"今天"，使用日期相关的筛选
4. 发送邮件前，先确认候选人存在
5. 如果用户的问题不需要工具，直接回答即可
6. 始终返回清晰、结构化的中文回复"""


async def function_calling_node(state: RecruitmentState) -> dict:
    """LangGraph 节点入口 — 从 State 读取 fc_query，执行 Function Calling"""
    query = state.get("fc_query", "")                               # 用户自然语言查询
    if not query:                                                   # 没有查询 → 直接返回
        return {
            "fc_result": json.dumps({"info": "没有查询请求"}, ensure_ascii=False),
            "fc_response": "未接收到查询请求。",
        }
    return await run_function_calling(query)                        # 委托核心函数


async def run_function_calling(query: str, system_prompt: str = "") -> dict:
    """执行 Function Calling 完整流程 — LLM 选工具 → 执行 → 生成回复

    返回 {fc_result, fc_tool_calls, fc_response}
    """
    tools = get_tool_definitions_openai()                           # 获取 5 个 MCP Tool 的 OpenAI 格式定义
    messages = [{"role": "user", "content": query}]                 # 用户消息
    system = system_prompt or FC_SYSTEM_PROMPT                      # 系统提示词

    # ===== 第 1 轮 LLM 调用：决定用不用工具、用哪个 =====
    from openai import AsyncOpenAI                                  # 延迟导入，避免循环依赖
    from app.config import settings

    client = AsyncOpenAI(                                           # 创建临时 OpenAI 客户端
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    response = await client.chat.completions.create(                # 调 LLM
        model=settings.OPENAI_MODEL,
        messages=[{"role": "system", "content": system}] + messages,
        tools=tools,                                                # 传入 5 个工具定义
        tool_choice="auto",                                         # LLM 自动决定是否用工具
        temperature=0.1,                                            # 低温度 → 稳定选择
        max_tokens=4096,
    )

    choice = response.choices[0]
    message = choice.message                                        # LLM 的回复消息

    # LLM 决定不调工具 → 直接返回纯文本回复
    if not message.tool_calls:
        return {
            "fc_result": json.dumps({"mode": "direct_answer"}, ensure_ascii=False),
            "fc_tool_calls": [],
            "fc_response": message.content or "",
        }

    # ===== 第 2 步：逐个执行 LLM 选择的工具 =====
    tool_results = []                                               # 工具执行结果（给 LLM 第二轮的 context）
    tool_call_records = []                                          # 工具调用记录（返回给前端/日志）
    for tc in message.tool_calls:                                   # 遍历每个工具调用
        func_name = tc.function.name                                # 工具名
        try:
            func_args = json.loads(tc.function.arguments)           # 解析 LLM 传的参数
        except json.JSONDecodeError:                                # JSON 解析失败
            func_args = {}
        result = await execute_tool_directly(func_name, func_args)  # 直接调工具（无 MCP 协议开销）

        tool_call_records.append({                                  # 记录这次调用
            "id": tc.id, "name": func_name, "arguments": func_args,
        })
        tool_results.append({                                       # 工具结果（OpenAI 要求的格式）
            "tool_call_id": tc.id, "role": "tool", "content": result,
        })

    # ===== 第 2 轮 LLM 调用：基于工具结果生成最终回复 =====
    final_messages = [
        {"role": "system", "content": system},                      # 系统提示词
        {"role": "user", "content": query},                         # 原始用户问题
    ]
    final_messages.append({                                         # 补上 assistant 的 tool_calls 消息
        "role": "assistant",
        "content": message.content,
        "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in message.tool_calls
        ],
    })
    final_messages.extend(tool_results)                             # 补上工具执行结果

    final_response = await client.chat.completions.create(          # 再调一次 LLM 生成最终回复
        model=settings.OPENAI_MODEL,
        messages=final_messages,
        temperature=0.3,                                            # 稍高温度 → 回复更自然
        max_tokens=4096,
    )

    final_text = final_response.choices[0].message.content or ""    # 最终回复文本

    return {
        "fc_result": json.dumps({                                   # 工具执行摘要
            "mode": "tool_calling",
            "tool_count": len(tool_call_records),
            "results_summary": [tr["content"][:200] + "..." for tr in tool_results],
        }, ensure_ascii=False),
        "fc_tool_calls": tool_call_records,                         # 工具调用记录
        "fc_response": final_text,                                  # LLM 最终回复
    }
