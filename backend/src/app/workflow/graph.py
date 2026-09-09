"""LangGraph 招聘流程图（多 Agent 并行版）

【小白导读】这是整个招聘流水线的"总装配图纸"。
本文件回答三个问题：
  1. 流水线有哪些工位？—— add_node() 注册的所有节点
  2. 工位怎么串联？ —— add_edge() 固定连线 + add_conditional_edges() 按 State 内容分岔
  3. 候选人怎么走完全程？—— 从入口 parse_resume 开始，一路走到 END

完整流程图（对照看下面的连线代码）：

  parse_resume（解析简历文件→纯文本）
      │  有文本？没有→END
      ▼
  classify（LLM 判断岗位类别，决定评分权重）
      │  Send 并发"分叉"成 3 路
      ├──────────────┬──────────────┐
      ▼              ▼              ▼
  analyze_basic  analyze_skills  analyze_experience   ← 3 个子 Agent 并行跑
      └──────────────┴──────────────┘
                     ▼  （LangGraph 自动等 3 路都完成）
  synthesize_analysis（scoring.py 按权重算总分）
      │  按总分分流：
      │  ≥80 → schedule_interview（直接排面试）
      │  ≥60 → generate_questionnaire（发问卷）
      │  ≥40 → move_to_talent_pool（进人才池）
      │  <40 → END（淘汰）
      ▼
  问卷通道：generate_questionnaire → wait_questionnaire → score_questionnaire
            │ 及格
            ▼
  schedule_interview（生成可选时段）→ confirm_interview（候选人确认）
      → complete_interview（面试完成）
      │  Send 并发"分叉"成 3 路评审
      ├──────────────┬──────────────┐
      ▼              ▼              ▼
  technical_review communication_review culture_review
      └──────────────┴──────────────┘
                     ▼
  supervisor_decision（汇总三路评审，给出最终录用/拒绝）→ END

两个容易迷惑的点：
  * "analyze" 节点是旧版单 Agent 分析的入口，保留只为兼容旧代码，新流程不走它。
  * 3 路并行不是多线程：LangGraph 用 Send 机制把同一份 State 复制 3 份分别执行，
    各自只写自己的 key（见 state.py），写完自动合并。
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
# 条件路由函数：输入当前 State，返回"下一个节点名"或 END。
# 它们只做判断、不写数据库，是流程的"方向盘"。

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
    # 阈值来自 config.py，可以在 .env 里调整而不用改代码
    if score >= settings.SCORE_THRESHOLD_FAST_TRACK:
        return "schedule_interview"
    elif score >= settings.SCORE_THRESHOLD_QUESTIONNAIRE:
        return "generate_questionnaire"
    elif score >= settings.SCORE_THRESHOLD_TALENT_POOL:
        return "talent_pool"
    return END


def should_score_questionnaire(state: RecruitmentState) -> str:
    """问卷完成了吗？完成了才批卷，否则等待/结束"""
    if state.get("questionnaire_status") == "completed":
        return "score_questionnaire"
    return END


def should_schedule(state: RecruitmentState) -> str:
    """问卷及格了才安排面试，否则到此为止"""
    if state.get("questionnaire_passed", False):
        return "schedule_interview"
    return END


# -- 构建图 --

def build_recruitment_graph() -> StateGraph:
    """把所有节点和连线装配成一张可执行的图

    本函数只在模块导入时执行一次（见文件末尾），
    编译产物 recruitment_graph 是全局唯一的流水线实例。
    """
    workflow = StateGraph(RecruitmentState)

    # 注册所有节点（add_node 只是"登记工位"，还没连线）
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

    # ---- 设定入口：每个候选人从解析简历开始 ----
    workflow.set_entry_point("parse_resume")

    # ---- 连线（对照文件头部的流程图看）----
    # 解析 → 有文本才分类
    workflow.add_conditional_edges("parse_resume", should_classify, {"classify": "classify", END: END})
    # classify → 3 路并行分析（LangGraph Send 自动 fork，见 route_to_analyzers 实现）
    workflow.add_conditional_edges("classify", route_to_analyzers,
        ["analyze_basic_info", "analyze_skills", "analyze_experience"])
    # 3 路 → 综合汇总（LangGraph 自动等 3 路完成才放行，天然的"汇合点"）
    workflow.add_edge("analyze_basic_info", "synthesize_analysis")
    workflow.add_edge("analyze_skills", "synthesize_analysis")
    workflow.add_edge("analyze_experience", "synthesize_analysis")
    # 综合打分 → 按总分四选一分流
    workflow.add_conditional_edges("synthesize_analysis", should_send_questionnaire, {
        "schedule_interview": "schedule_interview",
        "generate_questionnaire": "generate_questionnaire",
        "talent_pool": "move_to_talent_pool",
        END: END,
    })

    workflow.add_edge("move_to_talent_pool", END)
    # 问卷通道：生成 → 等候选人作答 → 批卷
    workflow.add_edge("generate_questionnaire", "wait_questionnaire")
    workflow.add_conditional_edges("wait_questionnaire", should_score_questionnaire,
        {"score_questionnaire": "score_questionnaire", END: END})
    workflow.add_conditional_edges("score_questionnaire", should_schedule,
        {"schedule_interview": "schedule_interview", END: END})

    # 面试三连：排期 → 候选人确认 → 完成
    workflow.add_edge("schedule_interview", "confirm_interview")
    workflow.add_edge("confirm_interview", "complete_interview")

    # 面试完成 → 3 路并行评审（同样用 Send fork）
    workflow.add_conditional_edges("complete_interview", route_to_reviewers,
        ["technical_review", "communication_review", "culture_review"])
    # 三路评审汇聚到 supervisor 做最终决策
    workflow.add_edge("technical_review", "supervisor_decision")
    workflow.add_edge("communication_review", "supervisor_decision")
    workflow.add_edge("culture_review", "supervisor_decision")
    workflow.add_edge("supervisor_decision", END)

    return workflow.compile()


# 模块导入时立即构建（main.py / worker.py / routers 都直接 import 这个实例）
recruitment_graph = build_recruitment_graph()
