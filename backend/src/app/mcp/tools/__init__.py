"""MCP Tools — 数据库查询 + 邮件发送 + 制度 RAG 检索 + JD 全网参考"""
from app.mcp.tools.database import (
    query_candidates,
    get_candidate_detail,
    query_interviews,
    get_dashboard_stats,
)
from app.mcp.tools.email import send_email
from app.mcp.tools.policy import query_policy_docs
from app.mcp.tools.jd_reference import jd_reference_search

__all__ = [
    "query_candidates",
    "get_candidate_detail",
    "query_interviews",
    "get_dashboard_stats",
    "send_email",
    "query_policy_docs",
    "jd_reference_search",
]
