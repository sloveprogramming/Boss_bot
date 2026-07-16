"""工作流节点 — Backend 嵌入版"""
from app.workflow.nodes.parse_resume import parse_resume_node
from app.workflow.nodes.classify import classify_node
from app.workflow.nodes.analyze import analyze_node
from app.workflow.nodes.questionnaire import (
    generate_questionnaire_node,
    wait_questionnaire_node,
    score_questionnaire_node,
)
from app.workflow.nodes.schedule import (
    schedule_interview_node,
    confirm_interview_node,
    complete_interview_node,
)
from app.workflow.nodes.decision import make_decision_node
from app.workflow.nodes.talent_pool import move_to_talent_pool_node
from app.workflow.nodes.function_calling import (
    FC_SYSTEM_PROMPT,
    function_calling_node,
    run_function_calling,
)

__all__ = [
    "parse_resume_node",
    "classify_node",
    "analyze_node",
    "generate_questionnaire_node",
    "wait_questionnaire_node",
    "score_questionnaire_node",
    "schedule_interview_node",
    "confirm_interview_node",
    "complete_interview_node",
    "make_decision_node",
    "move_to_talent_pool_node",
    "FC_SYSTEM_PROMPT",
    "function_calling_node",
    "run_function_calling",
]
