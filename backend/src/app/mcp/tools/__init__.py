"""MCP Tools — 数据库查询 + 邮件发送"""
from app.mcp.tools.database import (
    query_candidates,
    get_candidate_detail,
    query_interviews,
    get_dashboard_stats,
)
from app.mcp.tools.email import send_email

__all__ = [
    "query_candidates",
    "get_candidate_detail",
    "query_interviews",
    "get_dashboard_stats",
    "send_email",
]
