"""RAG 服务路由 — 制度问答（含 SSE 流式输出）"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.services import policy_rag_agent
from app.agents import llm_client

router = APIRouter(prefix="/api/chat", tags=["制度问答"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    candidate_id: Optional[int] = None


def sse_event(event_type: str, data: dict) -> str:
    """构建 SSE 事件"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    """制度问答（RAG 检索 + LLM 回答）"""
    try:
        result = await policy_rag_agent.chat(
            message=data.message,
            session_id=data.session_id,
            candidate_id=data.candidate_id,
            db=db,
        )
        return {
            "session_id": result["session_id"],
            "answer": result["answer"],
            "confidence": result["confidence"],
            "cited_sources": result["cited_sources"],
            "disclaimer": result.get("disclaimer"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG 处理出错: {str(e)}")


@router.post("/stream")
async def chat_stream(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    """流式制度问答（SSE）

    事件流：
    1. progress: 检索阶段
    2. sources: 引用来源
    3. token: 逐 token 生成回答
    4. done: 完成
    """
    async def generate():
        try:
            # 阶段 1: RAG 检索
            yield sse_event("progress", {
                "node": "retrieval", "status": "running",
                "message": "正在检索相关制度文档...", "progress_pct": 15,
            })

            retrieval_results = await policy_rag_agent.query(
                question=data.message, db=db, top_k=5,
            )

            cited_sources = []
            retrieved_text = ""
            for i, doc in enumerate(retrieval_results):
                retrieved_text += f"\n【文档 {i+1}】{doc.get('title', '无标题')}\n{doc.get('content', '')}\n"
                cited_sources.append({
                    "title": doc.get("title", ""),
                    "category": doc.get("category", ""),
                    "score": doc.get("relevance_score", 0),
                })

            yield sse_event("progress", {
                "node": "retrieval", "status": "done",
                "message": f"检索完成，找到 {len(retrieval_results)} 条相关文档", "progress_pct": 35,
            })

            if cited_sources:
                yield sse_event("sources", {"sources": cited_sources})

            # 阶段 2: 流式生成回答
            yield sse_event("progress", {
                "node": "generating", "status": "running",
                "message": "正在生成回答...", "progress_pct": 50,
            })

            from app.agents import POLICY_AGENT_SYSTEM, POLICY_AGENT_PROMPT
            chat_prompt = POLICY_AGENT_PROMPT.format(
                retrieved_chunks=retrieved_text,
                user_question=data.message,
            )

            full_answer = ""
            async for chunk in llm_client.stream_chat(
                system=POLICY_AGENT_SYSTEM,
                messages=[{"role": "user", "content": chat_prompt}],
                temperature=0.3,
            ):
                full_answer += chunk
                yield sse_event("token", {"text": chunk})

            # 保存聊天历史
            try:
                await policy_rag_agent.chat(
                    message=data.message,
                    session_id=data.session_id,
                    db=db,
                )
            except Exception:
                pass

            yield sse_event("done", {
                "message": "回答完成",
                "cited_sources": cited_sources,
                "session_id": data.session_id,
            })

        except Exception as e:
            yield sse_event("error", {
                "message": "问答处理出错",
                "detail": str(e),
            })

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, db: AsyncSession = Depends(get_db)):
    """获取指定会话的对话历史"""
    history = await policy_rag_agent.get_history(session_id, db)
    return {"session_id": session_id, "messages": history}
