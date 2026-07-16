"""LangGraph 招聘流程编排 — 后端内嵌版

取代旧的 agents/orchestrator/（独立编排服务）和 services/workflow.py（后端状态机）。
LangGraph 运行在 Backend 进程内，各节点直接操作数据库，无需 HTTP 同步。

架构：
  ┌─ LangGraph Runtime ──────────────────────────────────┐
  │  StateGraph(RecruitmentState) ← 单个 State 贯穿全程  │
  │                                                       │
  │  parse_resume → classify → analyze → questionnaire → │
  │  schedule → interview → decision                      │
  │       │         │         │                           │
  │       ▼         ▼         ▼                           │
  │  节点内：调用独立 Agent HTTP / 或内联执行              │
  │  状态变更直接持久化到 SQLite                           │
  └───────────────────────────────────────────────────────┘
"""
from app.workflow.state import RecruitmentState
from app.workflow.graph import build_recruitment_graph, recruitment_graph
from app.workflow.utils import get_candidate, candidate_session
from app.workflow.agent_client import AgentClient, agent_client
from app.workflow import nodes  # 节点子包（已 re-export 所有 node）

__all__ = [
    "RecruitmentState",
    "build_recruitment_graph", "recruitment_graph",
    "get_candidate", "candidate_session",
    "AgentClient", "agent_client",
    "nodes",
]
