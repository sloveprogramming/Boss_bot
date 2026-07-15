"""Function Calling 节点 — LLM 自主选择并调用 MCP Tools

该节点是整个工作流中的"智能调度"节点：
1. 接收用户自然语言查询
2. 将查询 + 可用工具列表发给 LLM
3. LLM 判断需要调用哪些工具，返回 tool_calls
4. 执行工具并收集结果
5. 将结果写回 State，供后续节点使用

使用方式：
- 在 LangGraph 中作为独立节点注册
- 也可通过 API 直接调用（GET/POST /api/workflow/function-call）
"""
import json
from typing import Optional
from app.workflow.state import RecruitmentState
from app.mcp.client import get_tool_definitions_openai, execute_tool_directly
from app.agents.llm_client import llm_client


# Function Calling 系统提示词
FC_SYSTEM_PROMPT = """你是 AI 招聘助手的智能调度器。你可以使用以下工具来回答用户关于招聘系统的问题。

规则：
1. 根据用户的问题，选择合适的工具
2. 如果需要候选人信息，先查候选人列表，再查详情
3. 如果用户问"最近"或"今天"，使用日期相关的筛选
4. 发送邮件前，先确认候选人存在
5. 如果用户的问题不需要工具，直接回答即可
6. 始终返回清晰、结构化的中文回复"""


async def function_calling_node(state: RecruitmentState) -> dict:
    """Function Calling 工作流节点

    从 state 中读取 fc_query（用户查询），让 LLM 自主选择工具执行。

    写入 state：
        - fc_result: 工具执行结果
        - fc_tool_calls: LLM 产生的工具调用记录
        - fc_response: LLM 的最终回复文本
    """
    query = state.get("fc_query", "")
    if not query:
        return {
            "fc_result": json.dumps({"info": "没有查询请求"}, ensure_ascii=False),
            "fc_response": "未接收到查询请求。",
        }

    return await run_function_calling(query)


async def run_function_calling(query: str, system_prompt: str = "") -> dict:
    """执行 Function Calling 循环

    Args:
        query: 用户查询
        system_prompt: 自定义系统提示词（可选，默认使用 FC_SYSTEM_PROMPT）

    Returns:
        {fc_result, fc_tool_calls, fc_response}
    """
    tools = get_tool_definitions_openai()
    messages = [{"role": "user", "content": query}]
    system = system_prompt or FC_SYSTEM_PROMPT

    # 第一次 LLM 调用：决定是否使用工具
    from openai import AsyncOpenAI
    from app.config import settings

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            *messages,
        ],
        tools=tools,
        tool_choice="auto",
        temperature=0.1,
        max_tokens=4096,
    )

    choice = response.choices[0]
    message = choice.message

    # 如果 LLM 决定不调用工具，直接返回回复
    if not message.tool_calls:
        return {
            "fc_result": json.dumps({"mode": "direct_answer"}, ensure_ascii=False),
            "fc_tool_calls": [],
            "fc_response": message.content or "",
        }

    # 执行工具调用
    tool_results = []
    tool_call_records = []
    for tc in message.tool_calls:
        func_name = tc.function.name
        try:
            func_args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            func_args = {}

        result = await execute_tool_directly(func_name, func_args)

        tool_call_records.append({
            "id": tc.id,
            "name": func_name,
            "arguments": func_args,
        })
        tool_results.append({
            "tool_call_id": tc.id,
            "role": "tool",
            "content": result,
        })

    # 第二次 LLM 调用：基于工具结果生成最终回复
    final_messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": query},
    ]
    # 添加 assistant 的 tool_calls 消息
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
    # 添加工具执行结果
    final_messages.extend(tool_results)

    final_response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=final_messages,
        temperature=0.3,
        max_tokens=4096,
    )

    final_text = final_response.choices[0].message.content or ""

    return {
        "fc_result": json.dumps({
            "mode": "tool_calling",
            "tool_count": len(tool_call_records),
            "results_summary": [tr["content"][:200] + "..." for tr in tool_results],
        }, ensure_ascii=False),
        "fc_tool_calls": tool_call_records,
        "fc_response": final_text,
    }
