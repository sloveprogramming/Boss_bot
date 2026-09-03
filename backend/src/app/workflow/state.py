"""RecruitmentState — LangGraph 全程共用的状态对象

所有节点读写同一个 State，LangGraph 自动把返回值合并回去。
多 Agent 场景下，并行节点各自写独立 key，汇总节点再读合并。
"""
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph.message import add_messages


class RecruitmentState(TypedDict, total=False):

    # -- 候选人 --
    candidate_id: int
    candidate_name: str
    position: str
    email: str
    phone: Optional[str]

    # -- 流程定位 --
    status: str          # new → parsed → classified → analyzed → ... → hired/rejected
    pipeline_stage: str  # resume / questionnaire / interview / decision

    # -- 简历 --
    resume_text: Optional[str]
    job_description: Optional[str]

    # -- 分类 --
    job_category: Optional[str]
    category_confidence: Optional[float]

    # -- 分析结果（3 个子 Agent 产物 + 综合） --
    analysis_result: Optional[dict]
    match_analysis: Optional[dict]
    match_score: Optional[float]
    basic_info_analysis: Optional[dict]
    skills_analysis: Optional[dict]
    experience_analysis: Optional[dict]

    # -- 评分体系 v2（维度分派生总分 + 双通道留痕） --
    analysis_complete: Optional[bool]    # 维度分是否齐全；False 时不自动分流，转人工复核
    llm_overall_score: Optional[float]   # LLM 综合重评分（通道B，只记录不生效）
    score_diff: Optional[float]          # |加权分 - LLM重评分|，观察期攒数据定阈值

    # -- 问卷 --
    questionnaire_id: Optional[int]
    questionnaire_status: Optional[str]
    questionnaire_score: Optional[float]
    questionnaire_passed: Optional[bool]

    # -- 面试 --
    interview_id: Optional[int]
    interview_status: Optional[str]
    interview_decision: Optional[str]
    interview_feedback: Optional[str]

    # -- 面试评审（3 路评审 + supervisor 决策） --
    technical_review: Optional[dict]
    communication_review: Optional[dict]
    culture_review: Optional[dict]
    review_results: Optional[dict]
    decision_reason: Optional[str]
    decision_confidence: Optional[str]
    risk_warning: Optional[str]

    # -- Function Calling --
    fc_query: Optional[str]
    fc_result: Optional[str]
    fc_tool_calls: Optional[list]
    fc_response: Optional[str]

    # -- 流程控制 --
    errors: List[str]
    retry_count: int
    notifications_sent: List[str]

    # -- LangGraph 内置 --
    messages: Annotated[list, add_messages]
