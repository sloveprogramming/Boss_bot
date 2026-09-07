"""MCP Server — 将数据库查询和邮件发送封装为 MCP Tools

支持：
- stdio transport（独立进程模式，可被任意 MCP Client 连接）
- 可被 LangGraph Function Calling 节点通过 MCP Client 调用
"""
import json
import asyncio
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from app.mcp.tools import (
    query_policy_docs,
    query_candidates,
    get_candidate_detail,
    query_interviews,
    get_dashboard_stats,
    send_email,
)

# ===== MCP Server 实例 =====
server = Server("boos-bot-recruitment")


# ===== 工具定义（OpenAI Function Calling 兼容格式）=====

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "query_candidates",
        "description": "搜索/筛选候选人列表。可通过姓名、岗位、状态、类别、匹配度范围等条件筛选。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "候选人姓名（模糊匹配）",
                },
                "position": {
                    "type": "string",
                    "description": "应聘岗位（模糊匹配）",
                },
                "status": {
                    "type": "string",
                    "enum": ["new", "analyzed", "talent_pool", "q_sent", "q_done",
                             "scheduled", "interviewed", "hired", "rejected"],
                    "description": "候选人状态",
                },
                "job_category": {
                    "type": "string",
                    "description": "岗位类别，如 python/java/product/ai/frontend/ops/test/erp/外贸运营/数据分析/项目管理/销售/人力资源/运营",
                },
                "min_score": {
                    "type": "number",
                    "description": "最低匹配度分数（0-100）",
                },
                "max_score": {
                    "type": "number",
                    "description": "最高匹配度分数（0-100）",
                },
                "page": {
                    "type": "integer",
                    "description": "页码（从1开始，默认1）",
                    "default": 1,
                },
                "page_size": {
                    "type": "integer",
                    "description": "每页条数（默认20）",
                    "default": 20,
                },
            },
        },
    },
    {
        "name": "get_candidate_detail",
        "description": "获取候选人完整信息，包括简历分析结果、面试记录、通知历史。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "integer",
                    "description": "候选人 ID",
                },
            },
            "required": ["candidate_id"],
        },
    },
    {
        "name": "query_interviews",
        "description": "查询面试安排列表，可按状态、日期范围、轮次筛选。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "awaiting_confirm", "confirmed", "completed",
                             "cancelled", "no_show"],
                    "description": "面试状态",
                },
                "date_from": {
                    "type": "string",
                    "description": "面试日期起始（ISO格式，如 2026-07-01）",
                },
                "date_to": {
                    "type": "string",
                    "description": "面试日期截止（ISO格式，如 2026-07-31）",
                },
                "round_filter": {
                    "type": "string",
                    "enum": ["first", "technical", "hr", "final"],
                    "description": "面试轮次",
                },
                "page": {"type": "integer", "description": "页码", "default": 1},
                "page_size": {"type": "integer", "description": "每页条数", "default": 20},
            },
        },
    },
    {
        "name": "get_dashboard_stats",
        "description": "获取招聘仪表盘统计数据：候选人总数、今日新增、状态分布、平均匹配分、录用率、岗位分布、待办面试数。",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "send_email",
        "description": "发送邮件给指定候选人。支持预置模板（面试邀请/确认/提醒、问卷邀请/提醒、拒信、录用通知）和自定义内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "integer",
                    "description": "候选人 ID",
                },
                "template": {
                    "type": "string",
                    "enum": ["interview_invite", "interview_confirmed", "interview_reminder",
                             "questionnaire_invite", "questionnaire_reminder",
                             "rejection", "offer", "custom"],
                    "description": "邮件模板。选 custom 时需提供 subject 和 body",
                    "default": "interview_invite",
                },
                "subject": {
                    "type": "string",
                    "description": "自定义邮件主题（template=custom 时必填）",
                },
                "body": {
                    "type": "string",
                    "description": "自定义邮件正文（template=custom 时必填），支持 {candidate_name} {position} 变量",
                },
                "extra_vars": {
                    "type": "object",
                    "description": "模板额外变量，如 {'survey_link': '...', 'deadline': '...'}",
                },
            },
            "required": ["candidate_id"],
        },
    },
    {
        "name": "query_policy_docs",
        "description": "查询企业制度/规章/政策知识库（年假、试用期、报销、考勤、加班、福利、入职、离职等）。返回制度答案与引用来源文档。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "要查询的制度问题，如：年假有几天？试用期多久？",
                },
            },
            "required": ["question"],
        },
    },
]


# ===== MCP 协议处理器 =====

@server.list_tools()
async def list_tools() -> list[Tool]:
    """MCP 标准：列出所有可用工具"""
    return [
        Tool(
            name=td["name"],
            description=td["description"],
            inputSchema=td["inputSchema"],
        )
        for td in TOOL_DEFINITIONS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """MCP 标准：执行指定工具"""
    tool_map = {
        "query_candidates": query_candidates,
        "get_candidate_detail": get_candidate_detail,
        "query_interviews": query_interviews,
        "get_dashboard_stats": get_dashboard_stats,
                "send_email": send_email,
        "query_policy_docs": query_policy_docs,
    }

    tool_fn = tool_map.get(name)
    if not tool_fn:
        return [TextContent(type="text", text=json.dumps(
            {"error": f"未知工具: {name}"}, ensure_ascii=False
        ))]

    try:
        result = await tool_fn(**arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps(
            {"error": f"工具执行失败 [{name}]: {str(e)}"}, ensure_ascii=False
        ))]


# ===== 启动函数 =====

def run_mcp_server():
    """启动 MCP Server（stdio transport）

    用法（命令行）：
        python -m app.mcp.server
    """
    async def _run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    run_mcp_server()
