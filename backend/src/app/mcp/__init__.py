"""MCP Server — 将数据库查询、邮件发送封装为 MCP Tools

- 工具注册：server.py 中 @mcp.tool() 装饰器自动注册（FastMCP）
- 独立 MCP Server (stdio transport)，可被任意 MCP Client 连接：python -m app.mcp.server
- Backend 内部（LangGraph 节点）走 execute_tool_directly 直连通道（支持 user 注入做行级权限）
"""
from app.mcp.mcp_app import mcp
from app.mcp.server import run_mcp_server
from app.mcp.client import (
    DIRECT_TOOLS,
    get_tool_definitions_openai,
    execute_tool_directly,
)
from app.mcp.tools import (
    query_policy_docs,
    query_candidates,
    get_candidate_detail,
    query_interviews,
    get_dashboard_stats,
    send_email,
    jd_reference_search,
)

__all__ = [
    "mcp", "run_mcp_server",
    "DIRECT_TOOLS", "get_tool_definitions_openai", "execute_tool_directly",
    "query_candidates", "get_candidate_detail", "query_interviews",
    "get_dashboard_stats", "send_email", "query_policy_docs", "jd_reference_search",
]
