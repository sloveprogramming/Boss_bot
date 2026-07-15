"""RecruitmentState — 贯穿 LangGraph 全流程的单一状态对象

所有节点读/写同一个 RecruitmentState 字典，LangGraph 自动将返回值
合并回 State 后传给下一节点。节点也可以直接从数据库读取最新状态。
"""
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph.message import add_messages


class RecruitmentState(TypedDict, total=False):
    """招聘流程状态 — 唯一的贯穿对象"""

    # === 候选人身份 ===
    candidate_id: int
    candidate_name: str
    position: str
    email: str
    phone: Optional[str]

    # === 当前工作流位置 ===
    status: str       # new → parsed → classified → analyzed → q_sent → q_done → scheduled → interviewed → hired/rejected
    pipeline_stage: str  # resume | questionnaire | interview | decision

    # === 简历处理 ===
    resume_text: Optional[str]          # 解析后的简历文本
    job_description: Optional[str]      # 岗位描述

    # === 分类结果 ===
    job_category: Optional[str]         # python | java | product | ai | ...
    category_confidence: Optional[float]

    # === 分析结果 ===
    analysis_result: Optional[dict]
    match_analysis: Optional[dict]
    match_score: Optional[float]        # 总体评分 0-100

    # === 问卷 ===
    questionnaire_id: Optional[int]
    questionnaire_status: Optional[str]  # draft | sent | completed
    questionnaire_score: Optional[float]
    questionnaire_passed: Optional[bool]

    # === 面试 ===
    interview_id: Optional[int]
    interview_status: Optional[str]      # pending | confirmed | completed
    interview_decision: Optional[str]    # pass | reject

    # === Function Calling ===
    fc_query: Optional[str]              # 用户自然语言查询
    fc_result: Optional[str]             # 工具执行结果（JSON）
    fc_tool_calls: Optional[list]        # LLM 产生的工具调用记录
    fc_response: Optional[str]           # LLM 最终回复文本

    # === 控制 ===
    errors: List[str]
    retry_count: int
    notifications_sent: List[str]

    # === LangGraph 内置 ===
    messages: Annotated[list, add_messages]
