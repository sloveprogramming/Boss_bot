# 【小白导读】工具：让 AI 能查询公司制度（内部转发 RAG 服务的问答接口）。
"""MCP Tool — 制度文档 RAG 检索（桥接 RAG Service :18003）

把 RAG 服务作为 Function Calling 的一个工具暴露：
  HR 问制度类问题 → LLM 选择本工具 → 内部调用 RAG /api/chat → 返回答案与引用来源
RAG 服务不可用时返回 error JSON，由 LLM 转告用户（不抛异常打断对话）。
"""
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# 地址解析优先级：RAG_SERVICE_URL（docker 网络名）→ POLICY_RAG_URL → 本地默认 :18003
def _rag_chat_url() -> str:
    base = (
        os.getenv("RAG_SERVICE_URL")
        or os.getenv("POLICY_RAG_URL")
        or "http://localhost:18003"
    ).rstrip("/")
    return f"{base}/api/chat"


async def query_policy_docs(question: str) -> str:
    """查询企业制度知识库（RAG 混合检索 + LLM 生成回答）

    Args:
        question: 制度类问题，如"年假有几天""试用期多久"

    Returns:
        JSON 字符串：{"answer", "cited_sources", "confidence"} 或 {"error"}
    """
    if not question or not question.strip():
        return json.dumps({"error": "制度问题不能为空"}, ensure_ascii=False)

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                _rag_chat_url(),
                json={"message": question.strip()},
            )
            resp.raise_for_status()
            data = resp.json()

        result = {
            "answer": data.get("answer", ""),
            "cited_sources": data.get("cited_sources", []),
            "confidence": data.get("confidence"),
        }
        if data.get("disclaimer"):
            result["disclaimer"] = data["disclaimer"]
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:  # 服务未启动 / 超时 / 5xx —— 优雅降级
        logger.warning("RAG 制度检索失败: %s", e)
        return json.dumps(
            {"error": "制度知识库服务暂不可用（RAG Service 未启动或超时），请告知用户稍后再试。"},
            ensure_ascii=False,
        )
