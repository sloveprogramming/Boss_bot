"""Function Calling 节点 — ReAct 多轮工具循环

核心改进（相对旧版固定 2 步）：
  旧版：LLM 选工具 → 执行 → 再调一次 LLM 生成回复（无论信息够不够）
  新版：while 循环 —— LLM 决定调工具 → 执行 → 结果回填上下文 → 再问 LLM
        直到 LLM 认为信息足够（不再要求调工具）或达到 MAX_TOOL_ROUNDS 上限

这样"把 90 分以上的候选人简历发给 HR"这类复合任务可以自然拆解为：
  查列表 → 逐个查详情 → 发邮件  （3+ 轮自主决策）
"""
import json                                                         # 解析 LLM 的 JSON 参数
import logging
from app.workflow import RecruitmentState                     # 流程状态对象
from app.mcp import get_tool_definitions_openai, execute_tool_directly  # 工具定义 + 执行
from openai import AsyncOpenAI  # 延迟导入，避免循环依赖
from app.config import settings

logger = logging.getLogger(__name__)

# 单次请求最多工具轮数（防止死循环 / 失控成本）
MAX_TOOL_ROUNDS = 5

# ===== Function Calling 系统提示词 =====
FC_SYSTEM_PROMPT = """你是 AI 招聘助手的智能调度器。你可以使用以下工具来回答用户关于招聘系统的问题。

规则：
1. 根据用户的问题选择合适的工具；一次调用信息不够时，可以继续调用其他工具补充
2. 如果需要候选人信息，先查候选人列表，再查详情
3. 复合任务请拆解步骤执行，例如"把90分以上的候选人简历发给HR"：
   先查候选人列表 → 逐个查详情 → 再发邮件
4. 如果用户问"最近"或"今天"，使用日期相关的筛选
5. 制度/规章类问题（年假、试用期、报销、考勤等）必须调用 query_policy_docs 工具查询知识库；若工具返回 error，向用户说明制度知识库服务暂不可用
6. 发送邮件前，先确认候选人存在
7. 如果用户的问题不需要工具，直接回答即可
8. 对话中可能包含历史消息，注意上下文指代（如"他"、"那个人"、"刚才那个候选人"）
9. 始终返回清晰、结构化的中文回复"""

# ===== Function Calling 节点入口 =====
async def function_calling_node(state: RecruitmentState) -> dict:
    # 从 State 读取 fc_query，执行自然语言查询
    query = state.get("fc_query", "")                               # 用户自然语言查询
    if not query:                                                   # 没有查询 → 直接返回
        return {
            "fc_result": json.dumps({"info": "没有查询请求"}, ensure_ascii=False),
            "fc_response": "未接收到查询请求。",
        }

    # 透传发起者（HR/admin）做工具数据隔离；工作流/后台任务无 user 保持全量
    return await run_function_calling(query, user=state.get("user"))  # 委托核心函数


# ===== Function Calling 核心函数（ReAct 多轮循环） =====
async def run_function_calling(
    query: str,
    system_prompt: str = "",
    history: list | None = None,
    user=None,
) -> dict:
    """ReAct 多轮工具循环

    Args:
        query: 用户本次输入
        system_prompt: 可选自定义系统提示词
        history: 可选历史消息 [{"role": "user"/"assistant", "content": "..."}]
                 由 session_memory 注入，让"刚才那个人"这类指代可解析
        user: 发起者（用于工具数据范围隔离）；None=受信全量
    """
    tools = get_tool_definitions_openai()
    system = system_prompt or FC_SYSTEM_PROMPT

    # 历史上下文 + 本次输入
    messages: list = list(history or []) + [{"role": "user", "content": query}]

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    tool_call_records: list = []                                    # 跨轮累计的工具调用记录
    used_tools = False
    rounds_used = 0

    # ===== ReAct 循环 =====
    for round_i in range(MAX_TOOL_ROUNDS):
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            tools=tools,
            tool_choice="auto",                                     # LLM 自主决定调不调工具
            temperature=0.1,
            max_tokens=4096,
        )

        message = response.choices[0].message
        rounds_used = round_i + 1

        # LLM 认为信息足够 → 不再调用工具，直接给出最终回复
        if not message.tool_calls:
            return {
                "fc_result": json.dumps({
                    "mode": "direct_answer" if not used_tools else "tool_calling",
                    "rounds": rounds_used,
                    "tool_count": len(tool_call_records),
                    "results_summary": [
                        {"name": r["name"], "arguments": r["arguments"]}
                        for r in tool_call_records
                    ],
                }, ensure_ascii=False),
                "fc_tool_calls": tool_call_records,
                "fc_response": message.content or "",
            }

        used_tools = True

        # 把本轮 assistant 的工具调用决策追加进对话上下文
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ],
        })

        # 执行本轮的每个工具调用，结果逐条回填
        for tc in message.tool_calls:
            func_name = tc.function.name
            try:
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning("工具 %s 参数 JSON 解析失败，使用空参数: %s",
                               func_name, tc.function.arguments)
                func_args = {}

            result = await execute_tool_directly(func_name, func_args, user=user)
            tool_call_records.append({
                "id": tc.id, "name": func_name, "arguments": func_args,
            })

            # 工具结果回填进 messages → 下一轮 LLM 能看到执行结果
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # 达到最大轮数仍想调工具 → 去掉 tools 参数强制 LLM 生成最终回复（兜底）
    logger.warning("Function Calling 达到最大工具轮数 %d，强制生成最终回复", MAX_TOOL_ROUNDS)
    final_response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[{"role": "system", "content": system}] + messages,
        temperature=0.3,
        max_tokens=4096,
    )
    final_text = final_response.choices[0].message.content or ""

    return {
        "fc_result": json.dumps({
            "mode": "tool_calling",
            "rounds": rounds_used,
            "tool_count": len(tool_call_records),
            "forced_final": True,
            "results_summary": [
                {"name": r["name"], "arguments": r["arguments"]}
                for r in tool_call_records
            ],
        }, ensure_ascii=False),
        "fc_tool_calls": tool_call_records,
        "fc_response": final_text,
    }
