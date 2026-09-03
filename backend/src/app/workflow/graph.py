"""LangGraph 招聘流程图（多 Agent 并行版）

节点链路：
  parse_resume → classify → [3 路并行分析] → synthesize → 分流 → 问卷/面试
  面试 → [3 路并行评审] → supervisor 决策

旧版功能已合并至此，不再需要独立的 orchestrator 服务。
"""
from langgraph.graph import StateGraph, END
from .state import RecruitmentState
from .nodes.parse_resume import parse_resume_node
from .nodes.classify import classify_node
from .nodes.analyze import (
    analyze_basic_info_node,
    analyze_skills_node,
    analyze_experience_node,
    synthesize_analysis_node,
    analyze_node,
    route_to_analyzers,
)
from .nodes.questionnaire import (
    generate_questionnaire_node,
    wait_questionnaire_node,
    score_questionnaire_node,
)
from .nodes.schedule import (
    schedule_interview_node,
    confirm_interview_node,
    complete_interview_node,
)
from .nodes.review import (
    technical_review_node,
    communication_review_node,
    culture_review_node,
    supervisor_decision_node,
    route_to_reviewers,
)
from .nodes.decision import make_decision_node
from .nodes.talent_pool import move_to_talent_pool_node
from app.config import settings


# -- 条件路由 --

def should_classify(state: RecruitmentState) -> str:
    """解析后有文本就分类，否则直接结束"""
    return "classify" if state.get("resume_text") else END


def should_send_questionnaire(state: RecruitmentState) -> str:
    """根据匹配分分流：
        分析不完整 → 不自动分流（转人工复核）
        >= 80 → 直接面试
        >= 60 → 发问卷
        >= 40 → 进人才池
         < 40 → 拒绝
    """
    # v2: 维度分缺失的候选人分数不可信，不进自动分流，等 HR 复核
    if not state.get("analysis_complete", True):
        return END

    score = state.get("match_score", 0) or 0
    if score >= settings.SCORE_THRESHOLD_FAST_TRACK:
        return "schedule_interview"
    elif score >= settings.SCORE_THRESHOLD_QUESTIONNAIRE:
        return "generate_questionnaire"
    elif score >= settings.SCORE_THRESHOLD_TALENT_POOL:
        return "talent_pool"
    return END


def should_score_questionnaire(state: RecruitmentState) -> str:
    if state.get("questionnaire_status") == "completed":
        return "score_questionnaire"
    return END


def should_schedule(state: RecruitmentState) -> str:
    if state.get("questionnaire_passed", False):
        return "schedule_interview"
    return END


# -- 构建图 --

def build_recruitment_graph() -> StateGraph:
    workflow = StateGraph(RecruitmentState)

    # 注册所有节点
    workflow.add_node("parse_resume", parse_resume_node)
    workflow.add_node("classify", classify_node)
    # 多 Agent 分析链路
    workflow.add_node("analyze_basic_info", analyze_basic_info_node)
    workflow.add_node("analyze_skills", analyze_skills_node)
    workflow.add_node("analyze_experience", analyze_experience_node)
    workflow.add_node("synthesize_analysis", synthesize_analysis_node)
    workflow.add_node("analyze", analyze_node)  # 兼容旧代码
    # 问卷 / 面试
    workflow.add_node("generate_questionnaire", generate_questionnaire_node)
    workflow.add_node("wait_questionnaire", wait_questionnaire_node)
    workflow.add_node("score_questionnaire", score_questionnaire_node)
    workflow.add_node("schedule_interview", schedule_interview_node)
    workflow.add_node("confirm_interview", confirm_interview_node)
    workflow.add_node("complete_interview", complete_interview_node)
    # 多 Agent 评审链路
    workflow.add_node("technical_review", technical_review_node)
    workflow.add_node("communication_review", communication_review_node)
    workflow.add_node("culture_review", culture_review_node)
    workflow.add_node("supervisor_decision", supervisor_decision_node)
    # 兼容旧决策
    workflow.add_node("make_decision", make_decision_node)
    workflow.add_node("move_to_talent_pool", move_to_talent_pool_node)

    workflow.set_entry_point("parse_resume")

    # 连线
    workflow.add_conditional_edges("parse_resume", should_classify, {"classify": "classify", END: END})
    # classify → 3 路并行分析（LangGraph Send 自动 fork）
    workflow.add_conditional_edges("classify", route_to_analyzers,
        ["analyze_basic_info", "analyze_skills", "analyze_experience"])
    # 3 路 → 综合汇总（LangGraph 自动等 3 路完成）
    workflow.add_edge("analyze_basic_info", "synthesize_analysis")
    workflow.add_edge("analyze_skills", "synthesize_analysis")
    workflow.add_edge("analyze_experience", "synthesize_analysis")
    # 综合打分 → 分流
    workflow.add_conditional_edges("synthesize_analysis", should_send_questionnaire, {
        "schedule_interview": "schedule_interview",
        "generate_questionnaire": "generate_questionnaire",
        "talent_pool": "move_to_talent_pool",
        END: END,
    })

    workflow.add_edge("move_to_talent_pool", END)
    workflow.add_edge("generate_questionnaire", "wait_questionnaire")
    workflow.add_conditional_edges("wait_questionnaire", should_score_questionnaire,
        {"score_questionnaire": "score_questionnaire", END: END})
    workflow.add_conditional_edges("score_questionnaire", should_schedule,
        {"schedule_interview": "schedule_interview", END: END})

    workflow.add_edge("schedule_interview", "confirm_interview")
    workflow.add_edge("confirm_interview", "complete_interview")

    # 面试完成 → 3 路并行评审
    workflow.add_conditional_edges("complete_interview", route_to_reviewers,
        ["technical_review", "communication_review", "culture_review"])
    workflow.add_edge("technical_review", "supervisor_decision")
    workflow.add_edge("communication_review", "supervisor_decision")
    workflow.add_edge("culture_review", "supervisor_decision")
    workflow.add_edge("supervisor_decision", END)

    return workflow.compile()


recruitment_graph = build_recruitment_graph()
