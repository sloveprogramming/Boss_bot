"""MCP 客户端 — 供 Backend 内部调用 MCP Tools

支持两种模式：
- 直接调用（嵌入式，零开销，LangGraph 节点使用）
- MCP 协议连接（stdio，外部 MCP Client 使用）
"""
import inspect
import json
from typing import Any, Optional
from app.mcp.tools import (
    query_policy_docs,
    query_candidates,
    get_candidate_detail,
    query_interviews,
    get_dashboard_stats,
    send_email,
)
from app.mcp import TOOL_DEFINITIONS

# 工具函数直连映射（无 MCP 协议开销）
DIRECT_TOOLS = {
    "query_candidates": query_candidates,
    "get_candidate_detail": get_candidate_detail,
    "query_interviews": query_interviews,
    "get_dashboard_stats": get_dashboard_stats,
    "send_email": send_email,
    "query_policy_docs": query_policy_docs,
}

# 工具定义（OpenAI Function Calling 格式）
def get_tool_definitions_openai() -> list[dict[str, Any]]:
    """获取 OpenAI Function Calling 格式的工具定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": td["name"],
                "description": td["description"],
                "parameters": td["inputSchema"],
            },
        }
        for td in TOOL_DEFINITIONS
    ]


async def execute_tool_directly(
    name: str,
    arguments: dict[str, Any],
    user: Optional[Any] = None,
) -> str:
    """直接执行工具（跳过 MCP 协议，用于 LangGraph 节点）

    Args:
        name: 工具名称
        arguments: 工具参数
        user: 调用者（User ORM / 含 id/username/role 的轻量对象）。
              仅注入给签名接受 user 的工具（候选人数据类工具做行级隔离）；
              None 表示受信全量上下文（MCP stdio / 后台任务）。

    Returns:
        工具执行结果（JSON 字符串）
    """
    tool_fn = DIRECT_TOOLS.get(name)
    if not tool_fn:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

    if user is not None and "user" in inspect.signature(tool_fn).parameters:
        arguments = {**arguments, "user": user}
    return await tool_fn(**arguments)
