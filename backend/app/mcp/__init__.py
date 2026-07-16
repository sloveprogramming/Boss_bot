"""MCP Server — 将数据库查询、邮件发送封装为 MCP Tools

提供：
- 独立 MCP Server (stdio transport)，可被任意 MCP Client 连接
- 工具函数，可在 LangGraph Function Calling 节点中直接调用
"""
from app.mcp.server import server, TOOL_DEFINITIONS, run_mcp_server
from app.mcp.client import (
    DIRECT_TOOLS,
    get_tool_definitions_openai,
    execute_tool_directly,
)
# Tools 已在 app.mcp.tools.__init__ 集中 re-export
from app.mcp.tools import (
    query_candidates,
    get_candidate_detail,
    query_interviews,
    get_dashboard_stats,
    send_email,
)

__all__ = [
    # Server
    "server", "TOOL_DEFINITIONS", "run_mcp_server",
    # Client
    "DIRECT_TOOLS", "get_tool_definitions_openai", "execute_tool_directly",
    # Tools
    "query_candidates", "get_candidate_detail", "query_interviews",
    "get_dashboard_stats", "send_email",
]
