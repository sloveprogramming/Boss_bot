"""LangGraph StateGraph — 招聘流程状态图（后端内嵌版）

取代：
- agents/orchestrator/app/graph.py（独立编排服务）
- backend/app/services/workflow.py（后端状态机）

每个节点直接操作数据库，LangGraph 的 RecruitmentState 对象贯穿全流程。
"""
from langgraph.graph import StateGraph, END
from .state import RecruitmentState
from .nodes.parse_resume import parse_resume_node
from .nodes.classify import classify_node
from .nodes.analyze import analyze_node
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
from .nodes.decision import make_decision_node
from .nodes.talent_pool import move_to_talent_pool_node
from .nodes.function_calling import function_calling_node
from app.config import settings


# ========== 条件路由函数 ==========

def should_classify(state: RecruitmentState) -> str:
    """简历解析后：有文本则分类，否则结束"""
    if state.get("resume_text"):
        return "classify"
    return END


def should_send_questionnaire(state: RecruitmentState) -> str:
    """分析后：根据 match_score 分流
    - >=80: 快速通道 → 直接面试排期
    - >=60: 问卷通道 → 生成问卷
    - >=40: 人才池
    - <40:  拒绝
    """
    score = state.get("match_score", 0) or 0

    if score >= settings.SCORE_THRESHOLD_FAST_TRACK:
        return "schedule_interview"        # 快速通道
    elif score >= settings.SCORE_THRESHOLD_QUESTIONNAIRE:
        return "generate_questionnaire"    # 问卷通道
    elif score >= settings.SCORE_THRESHOLD_TALENT_POOL:
        return "talent_pool"               # 人才池
    return END                              # 拒绝（END）


def should_score_questionnaire(state: RecruitmentState) -> str:
    """问卷等待完成后的路由"""
    q_status = state.get("questionnaire_status")
    if q_status == "completed":
        return "score_questionnaire"
    return END  # 等待外部输入


def should_schedule(state: RecruitmentState) -> str:
    """问卷通过后排面试，不通过则拒绝"""
    passed = state.get("questionnaire_passed", False)
    if passed:
        return "schedule_interview"
    return END  # 问卷未通过 → 拒绝


def should_decide(state: RecruitmentState) -> str:
    """面试安排后做决策"""
    return "make_decision"


# ========== 构建图 ==========

def build_recruitment_graph() -> StateGraph:
    """构建招聘流程 StateGraph"""
    workflow = StateGraph(RecruitmentState)

    # ---- 注册节点 ----
    workflow.add_node("parse_resume", parse_resume_node)
    workflow.add_node("classify", classify_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("function_calling", function_calling_node)  # NEW: Function Calling
    workflow.add_node("generate_questionnaire", generate_questionnaire_node)
    workflow.add_node("wait_questionnaire", wait_questionnaire_node)
    workflow.add_node("score_questionnaire", score_questionnaire_node)
    workflow.add_node("schedule_interview", schedule_interview_node)
    workflow.add_node("confirm_interview", confirm_interview_node)
    workflow.add_node("complete_interview", complete_interview_node)
    workflow.add_node("make_decision", make_decision_node)
    workflow.add_node("move_to_talent_pool", move_to_talent_pool_node)

    # ---- 设置入口 ----
    workflow.set_entry_point("parse_resume")

    # ---- 条件边 ----
    # ① 简历解析 → 分类/结束
    workflow.add_conditional_edges(
        "parse_resume",
        should_classify,
        {"classify": "classify", END: END},
    )

    # ② 分类 → 分析（始终）
    workflow.add_edge("classify", "analyze")

    # ③ 分析 → 分流
    workflow.add_conditional_edges(
        "analyze",
        should_send_questionnaire,
        {
            "schedule_interview": "schedule_interview",     # 快速通道
            "generate_questionnaire": "generate_questionnaire",  # 问卷通道
            "talent_pool": "move_to_talent_pool",            # 人才池
            END: END,                                         # 拒绝
        },
    )

    # ④ 人才池 → 结束
    workflow.add_edge("move_to_talent_pool", END)

    # ⑤ 问卷生成 → 等待完成
    workflow.add_edge("generate_questionnaire", "wait_questionnaire")

    # ⑥ 等待完成 → 评分/继续等待
    workflow.add_conditional_edges(
        "wait_questionnaire",
        should_score_questionnaire,
        {"score_questionnaire": "score_questionnaire", END: END},
    )

    # ⑦ 评分 → 面试/拒绝
    workflow.add_conditional_edges(
        "score_questionnaire",
        should_schedule,
        {"schedule_interview": "schedule_interview", END: END},
    )

    # ⑧ 面试排期 → 确认 → 完成 → 决策
    workflow.add_edge("schedule_interview", "confirm_interview")
    workflow.add_edge("confirm_interview", "complete_interview")

    # ⑨ 完成 → 最终决策
    workflow.add_conditional_edges(
        "complete_interview",
        should_decide,
        {"make_decision": "make_decision"},
    )

    # ⑩ 决策 → 结束
    workflow.add_edge("make_decision", END)

    return workflow.compile()


# 编译图（全局单例）
recruitment_graph = build_recruitment_graph()
