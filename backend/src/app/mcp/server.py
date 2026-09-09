"""MCP Server — FastMCP 装饰器自动注册版

对比旧版（低层 Server API + 手工 TOOL_DEFINITIONS/tool_map）：
- 工具描述 = docstring，单一事实来源，不再菜单/实现两处维护
- 参数 schema = 类型标注自动生成，手工 JSON Schema 全部删除
- 分发 = FastMCP 内置，不再手工 tool_map
- 新增工具 = 写一个带类型标注和 docstring 的函数即可，注册零成本

启动方式不变：python -m app.mcp.server（stdio transport）
"""
from typing import Annotated, Any, Literal, Optional

from pydantic import Field

from app.mcp.mcp_app import mcp
from app.mcp.tools import (
    query_policy_docs as _query_policy_docs_impl,
    query_candidates as _query_candidates_impl,
    get_candidate_detail as _get_candidate_detail_impl,
    query_interviews as _query_interviews_impl,
    get_dashboard_stats as _get_dashboard_stats_impl,
    send_email as _send_email_impl,
    jd_reference_search as _jd_reference_search_impl,
)

# ---- 枚举别名（Literal 会自动转成 schema 里的 enum，LLM 只能填合法值）----
CandidateStatus = Literal[
    "new", "analyzed", "talent_pool", "q_sent", "q_done",
    "scheduled", "interviewed", "hired", "rejected",
]
InterviewStatus = Literal[
    "pending", "awaiting_confirm", "confirmed", "completed", "cancelled", "no_show",
]
InterviewRound = Literal["first", "technical", "hr", "final"]
EmailTemplate = Literal[
    "interview_invite", "interview_confirmed", "interview_reminder",
    "questionnaire_invite", "questionnaire_reminder",
    "rejection", "offer", "custom",
]


@mcp.tool()
async def query_candidates(
    name: Annotated[Optional[str], Field(description="候选人姓名（模糊匹配）")] = None,
    position: Annotated[Optional[str], Field(description="应聘岗位（模糊匹配）")] = None,
    status: Annotated[Optional[CandidateStatus], Field(description="候选人状态")] = None,
    job_category: Annotated[
        Optional[str],
        Field(description="岗位类别，如 python/java/product/ai/frontend/ops/test/erp/外贸运营/数据分析/项目管理/销售/人力资源/运营"),
    ] = None,
    min_score: Annotated[Optional[float], Field(description="最低匹配度分数（0-100）")] = None,
    max_score: Annotated[Optional[float], Field(description="最高匹配度分数（0-100）")] = None,
    page: Annotated[int, Field(description="页码（从1开始，默认1）")] = 1,
    page_size: Annotated[int, Field(description="每页条数（默认20）")] = 20,
) -> str:
    """搜索/筛选候选人列表。可通过姓名、岗位、状态、类别、匹配度范围等条件筛选。"""
    return await _query_candidates_impl(
        name=name, position=position, status=status, job_category=job_category,
        min_score=min_score, max_score=max_score, page=page, page_size=page_size,
    )


@mcp.tool()
async def get_candidate_detail(
    candidate_id: Annotated[int, Field(description="候选人 ID")],
) -> str:
    """获取候选人完整信息，包括简历分析结果、面试记录、通知历史。"""
    return await _get_candidate_detail_impl(candidate_id)


@mcp.tool()
async def query_interviews(
    status: Annotated[Optional[InterviewStatus], Field(description="面试状态")] = None,
    date_from: Annotated[Optional[str], Field(description="面试日期起始（ISO格式，如 2026-07-01）")] = None,
    date_to: Annotated[Optional[str], Field(description="面试日期截止（ISO格式，如 2026-07-31）")] = None,
    round_filter: Annotated[Optional[InterviewRound], Field(description="面试轮次")] = None,
    page: Annotated[int, Field(description="页码")] = 1,
    page_size: Annotated[int, Field(description="每页条数")] = 20,
) -> str:
    """查询面试安排列表，可按状态、日期范围、轮次筛选。"""
    return await _query_interviews_impl(
        status=status, date_from=date_from, date_to=date_to,
        round_filter=round_filter, page=page, page_size=page_size,
    )


@mcp.tool()
async def get_dashboard_stats() -> str:
    """获取招聘仪表盘统计数据：候选人总数、今日新增、状态分布、平均匹配分、录用率、岗位分布、待办面试数。"""
    return await _get_dashboard_stats_impl()


@mcp.tool()
async def send_email(
    candidate_id: Annotated[int, Field(description="候选人 ID")],
    template: Annotated[EmailTemplate, Field(description="邮件模板。选 custom 时需提供 subject 和 body")] = "interview_invite",
    subject: Annotated[Optional[str], Field(description="自定义邮件主题（template=custom 时必填）")] = None,
    body: Annotated[Optional[str], Field(description="自定义邮件正文（template=custom 时必填），支持 {candidate_name} {position} 变量")] = None,
    extra_vars: Annotated[Optional[dict[str, Any]], Field(description="模板额外变量，如 {'survey_link': '...', 'deadline': '...'}")] = None,
) -> str:
    """发送邮件给指定候选人。支持预置模板（面试邀请/确认/提醒、问卷邀请/提醒、拒信、录用通知）和自定义内容。"""
    return await _send_email_impl(
        candidate_id=candidate_id, template=template,
        subject=subject, body=body, extra_vars=extra_vars,
    )


@mcp.tool()
async def query_policy_docs(
    question: Annotated[str, Field(description="要查询的制度问题，如：年假有几天？试用期多久？")],
) -> str:
    """查询企业制度/规章/政策知识库（年假、试用期、报销、考勤、加班、福利、入职、离职等）。返回制度答案与引用来源文档。"""
    return await _query_policy_docs_impl(question)


@mcp.tool()
async def jd_reference_search(
    position: Annotated[str, Field(description="岗位名称，如：电商运营经理")],
    extra: Annotated[str, Field(description="补充需求/行业限定/能力侧重（可选），如：坚果食品、5年以上、擅长付费投放")] = "",
    max_results: Annotated[int, Field(description="外部参考条数上限")] = 8,
) -> str:
    """全网搜索同类岗位真实招聘 JD 并据公司档案生成适配草稿（含引用来源）。用户想找 XX 岗位的 JD / 岗位职责 / 招聘要求模板参考时使用。"""
    return await _jd_reference_search_impl(position, extra, max_results)


# ===== 启动函数 =====

def run_mcp_server():
    """启动 MCP Server（stdio transport，FastMCP 内置）

    用法（命令行）：
        python -m app.mcp.server
    """
    mcp.run()


if __name__ == "__main__":
    run_mcp_server()
