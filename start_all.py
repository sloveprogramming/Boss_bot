"""一键启动所有服务

精简后架构：
  Backend (:18000) ← 内嵌 LangGraph 工作流引擎，所有节点直接读写数据库
  子 Agent (可选独立服务，LangGraph 节点通过 HTTP 调用)
  Frontend (:18016)

旧 orchestrator 服务和重复的 RecruitmentWorkflow 已合并入 Backend。
"""
import subprocess
import time
import sys
import os

BASE = "E:/agent_class/Boos_bot"

# ===== 核心服务（必启） =====
services = [
    ("Backend API (含 LangGraph)", "18000", f"{BASE}/backend",
     ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18000"]),
    ("Frontend",                  "18016", f"{BASE}/frontend",
     ["npx", "vite", "--host", "127.0.0.1", "--port", "18016"]),
]

# ===== 独立 Agent 服务（可选） =====
# LangGraph 节点优先调用独立 Agent，不可用时自动降级为内联逻辑。
# 若不需要独立部署，可注释掉下方服务以节省资源。
INDEPENDENT_AGENTS = [
    ("RAG Service",       "18003", f"{BASE}/rag_service",
     ["python", "start.py"]),
    ("Resume Parser",     "18001", f"{BASE}/agents/resume-parser",
     ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18001"]),
    ("Classifier",        "18002", f"{BASE}/agents/classifier",
     ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18002"]),
    ("Python Analyzer",   "18008", f"{BASE}/agents/analyzers/python-analyzer",
     ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18008"]),
]

# 如需启用全部 Analyzer Agent，取消下面注释
# ("Java Analyzer",     "18009", f"{BASE}/agents/analyzers/java-analyzer",
#  ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18009"]),
# ("Product Analyzer",  "18010", f"{BASE}/agents/analyzers/product-analyzer",
#  ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18010"]),
# ("AI Analyzer",       "18011", f"{BASE}/agents/analyzers/ai-analyzer",
#  ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18011"]),
# ("Frontend Analyzer",  "18012", f"{BASE}/agents/analyzers/frontend-analyzer",
#  ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18012"]),
# ("Ops Analyzer",       "18013", f"{BASE}/agents/analyzers/ops-analyzer",
#  ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18013"]),
# ("Test Analyzer",      "18014", f"{BASE}/agents/analyzers/test-analyzer",
#  ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "18014"]),

all_services = services + INDEPENDENT_AGENTS

processes = []

print("=" * 50)
print("  AI 招聘助手 - 一键启动（精简版）")
print("  LangGraph 工作流已内嵌于 Backend")
print("=" * 50)

for name, port, cwd, cmd in all_services:
    print(f"\n[{name}] Starting on :{port}...")
    try:
        p = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        processes.append((name, port, p))
        print(f"  PID: {p.pid}")
    except Exception as e:
        print(f"  FAILED: {e}")

print("\n" + "=" * 50)
print(" 所有服务启动中，请稍候...")
print("=" * 50)
time.sleep(5)

print("\n服务状态：")
for name, port, p in processes:
    status = "RUNNING" if p.poll() is None else f"EXITED ({p.returncode})"
    print(f"  :{port} [{status}] {name}")

print(f"\n 前端地址: http://localhost:18016")
print(f" API 文档: http://localhost:18000/docs")
print(f" RAG 服务: http://localhost:18003/docs")
print(f"\n注：独立 Agent 不可用时，LangGraph 节点自动降级内联逻辑，核心功能不受影响。")
print("\n按 Ctrl+C 停止所有服务\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n正在停止所有服务...")
    for name, port, p in processes:
        p.terminate()
    print("所有服务已停止")
