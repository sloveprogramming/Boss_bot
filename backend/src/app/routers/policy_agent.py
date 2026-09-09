# ═══════════════════════════════════════════════════════════════
# 【小白导读】制度问答（RAG）的后端入口：
#   · 上传制度文档 → 转发 rag_service(:18003) 索引进 Milvus
#   · 问答（含 SSE 流式）→ 转发 rag_service，并把会话历史记在数据库
#   本文件是"调度员"，真正检索/生成逻辑在 rag_service/src/app/services/policy_rag.py。
# ═══════════════════════════════════════════════════════════════
"""企业制度文档管理 API — 文档入库 + 自动索引 + 简单问答 + 账号会话历史"""
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import PolicyDocument, PolicyChatHistory, UserRole, User
from app.dependencies import require_role
from pydantic import BaseModel
from typing import Optional

router = APIRouter(
    prefix="/api/policy",
    tags=["制度文档"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)

# 向量化统一由 rag_service 负责（bge-m3 混合检索，服务名 rag-service 于 docker 网络内可达）
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service:18003")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


async def _index_via_rag(doc_id: int) -> dict:
    """把文档交给 rag_service 做真实向量化（返回 {chunks, parents}）"""
    import httpx
    url = f"{RAG_SERVICE_URL}/api/documents/index/{doc_id}"
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url)
        resp.raise_for_status()
        return resp.json()


# ========== 文档入库 ==========

@router.post("/documents/upload")
async def upload_document(
    title: str = Form(...),
    category: str = Form(""),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """上传制度文档并存储到数据库

    仅做文件解析 + 数据库入库。
    向量索引由 rag_service (端口 18003) 负责:
      POST http://localhost:18003/api/documents/reindex
    """
    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    # 根据文件类型解析文本
    if ext == "txt":
        text = content.decode("utf-8", errors="replace")
    elif ext == "pdf":
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    elif ext == "docx":
        import docx
        from io import BytesIO
        doc_obj = docx.Document(BytesIO(content))
        text = "\n".join(p.text for p in doc_obj.paragraphs)
    else:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")

    # 保存文档记录
    doc_record = PolicyDocument(
        title=title,
        category=category or "未分类",
        file_name=file.filename,
        content=text,
    )
    db.add(doc_record)
    await db.flush()
    await db.refresh(doc_record)

    # 先提交，让 rag_service 能读到这条新文档，再由它做真实向量化（bge-m3）
    await db.commit()

    index_ok, chunk_count = False, 0
    warning = None
    try:
        r = await _index_via_rag(doc_record.id)
        index_ok, chunk_count = True, int(r.get("chunks", 0))
    except Exception as e:
        warning = f"文档已保存，但向量索引未完成（rag_service 不可用或失败）：{str(e)}"

    return {
        "id": doc_record.id,
        "title": doc_record.title,
        "category": doc_record.category,
        "file_name": doc_record.file_name,
        "indexed": index_ok,
        "chunk_count": chunk_count,
        "message": "文档已保存并完成索引" if index_ok else "文档已保存（向量索引未完成）",
        "warning": warning,
    }


# ========== 文档列表 ==========

@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    """获取所有已入库的制度文档列表"""
    result = await db.execute(
        select(PolicyDocument).order_by(PolicyDocument.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        {
            "id": d.id,
            "title": d.title,
            "category": d.category,
            "file_name": d.file_name,
            "indexed": d.indexed,
            "chunk_count": d.chunk_count,
            "created_at": d.created_at.isoformat() if d.created_at else "",
        }
        for d in docs
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """删除指定制度文档

    文档记录与 Milvus 向量分块统一交给 rag_service 级联删除，
    保证删除后 RAG 不再引用该文档内容。
    """
    import httpx
    url = f"{RAG_SERVICE_URL}/api/documents/{doc_id}"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.delete(url)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="文档不存在")
        resp.raise_for_status()
        return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"删除失败（rag_service 不可用或向量清理失败）：{str(e)}")


# ========== 简单问答（关键词匹配，不依赖 Milvus） ==========

@router.post("/chat")
async def chat_with_docs(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    """基于已入库文档的关键词匹配问答"""
    # 从 MySQL 搜索包含关键词的文档片段
    keywords = data.message.strip()
    if len(keywords) < 2:
        return {"answer": "请输入更具体的问题。", "cited_sources": []}

    result = await db.execute(
        select(PolicyDocument).where(
            PolicyDocument.content.contains(keywords[:50])
        ).limit(3)
    )
    docs = result.scalars().all()

    if not docs:
        # 尝试用 LLM 直接回答
        from app.agents import llm_client
        answer = await llm_client.chat(
            system="你是一个企业制度助手。如果知识库中没有相关信息，请诚实告知。",
            messages=[{"role": "user", "content": data.message}],
            temperature=0.3, max_tokens=1024,
        )
        return {
            "answer": answer,
            "cited_sources": [],
            "confidence": "low",
        }

    # 拼接检索到的内容
    context = "\n\n".join(d.content[:2000] for d in docs if d.content)
    from app.agents import llm_client
    answer = await llm_client.chat(
        system="你是企业制度助手。请基于提供的文档内容回答问题，引用来源时注明文档标题。",
        messages=[{"role": "user", "content": f"参考文档:\n{context}\n\n问题: {data.message}"}],
        temperature=0.3, max_tokens=1024,
    )

    return {
        "answer": answer,
        "cited_sources": [{"title": d.title, "category": d.category} for d in docs],
        "confidence": "medium",
    }


@router.post("/chat/stream")
async def chat_with_docs_stream(data: ChatRequest, db: AsyncSession = Depends(get_db)):
    """SSE 流式问答"""
    import json

    async def generate():
        keywords = data.message.strip()
        if len(keywords) < 2:
            yield f"event: done\ndata: {json.dumps({'answer': '请输入更具体的问题。'}, ensure_ascii=False)}\n\n"
            return

        # 从 MySQL 搜索
        result = await db.execute(
            select(PolicyDocument).where(
                PolicyDocument.content.contains(keywords[:50])
            ).limit(3)
        )
        docs = result.scalars().all()

        if not docs:
            from app.agents import llm_client
            async for chunk in llm_client.stream_chat(
                system="你是一个企业制度助手。如果知识库中没有相关信息，请诚实告知。",
                messages=[{"role": "user", "content": data.message}],
                temperature=0.3,
            ):
                yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'message': '完成'}, ensure_ascii=False)}\n\n"
            return

        context = "\n\n".join(d.content[:2000] for d in docs if d.content)
        yield f"event: sources\ndata: {json.dumps({'sources': [{'title': d.title} for d in docs]}, ensure_ascii=False)}\n\n"

        from app.agents import llm_client
        async for chunk in llm_client.stream_chat(
            system="你是企业制度助手。请基于提供的文档内容回答问题。",
            messages=[{"role": "user", "content": f"参考文档:\n{context}\n\n问题: {data.message}"}],
            temperature=0.3,
        ):
            yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

        yield f"event: done\ndata: {json.dumps({'message': '完成', 'sources': [{'title': d.title} for d in docs]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ========== 会话历史（按账号隔离，主后端持久化） ==========
# RAG 服务(:18003)只负责流式回答，不落库；
# 前端在提问/回答完成后调用这里写入 policy_chat_history，读取时一律按当前账号过滤。

class HistoryMessageIn(BaseModel):
    session_id: str
    role: str = "user"                       # user / assistant
    content: str
    cited_sources: Optional[list] = None


@router.get("/sessions")
async def list_policy_sessions(
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
    db: AsyncSession = Depends(get_db),
):
    """当前账号的全部制度问答会话（按最近活跃倒序）"""
    rows = (
        await db.execute(
            select(PolicyChatHistory)
            .where(PolicyChatHistory.username == current_user.username)
            .order_by(PolicyChatHistory.id.asc())
        )
    ).scalars().all()

    # 升序遍历：标题取最早一条 user 消息；预览与 last_id 持续覆盖 -> 最新一条
    by_sid: dict[str, dict] = {}
    for r in rows:
        s = by_sid.setdefault(r.session_id, {
            "session_id": r.session_id,
            "count": 0,
            "title": "",
            "last_preview": "",
            "last_id": r.id,
        })
        s["count"] += 1
        s["last_preview"] = (r.content or "")[:100]
        s["last_id"] = r.id
        if r.role == "user" and not s["title"]:
            s["title"] = (r.content or "").replace("\n", " ").strip()[:40]

    sessions = sorted(by_sid.values(), key=lambda s: s["last_id"], reverse=True)
    return {
        "sessions": [
            {
                "session_id": s["session_id"],
                "title": s["title"] or "新会话",
                "last_preview": s["last_preview"],
                "count": s["count"],
            }
            for s in sessions
        ]
    }


@router.get("/history")
async def get_policy_history(
    session_id: str = Query(...),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
    db: AsyncSession = Depends(get_db),
):
    """读取某个会话的消息（仅限本账号）"""
    rows = (
        await db.execute(
            select(PolicyChatHistory)
            .where(
                PolicyChatHistory.username == current_user.username,
                PolicyChatHistory.session_id == session_id,
            )
            .order_by(PolicyChatHistory.id.asc())
        )
    ).scalars().all()
    return {
        "session_id": session_id,
        "messages": [
            {
                "role": r.role,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


@router.post("/messages")
async def add_policy_message(
    data: HistoryMessageIn,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
    db: AsyncSession = Depends(get_db),
):
    """追加一条消息到某会话（归属当前账号）"""
    rec = PolicyChatHistory(
        username=current_user.username,
        session_id=data.session_id.strip()[:100],
        role=data.role if data.role in ("user", "assistant") else "user",
        content=(data.content or "").strip()[:4000],
        cited_sources=data.cited_sources,
    )
    if not rec.content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    db.add(rec)
    await db.flush()
    return {"id": rec.id}


@router.delete("/sessions/{session_id}")
async def delete_policy_session(
    session_id: str,
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
    db: AsyncSession = Depends(get_db),
):
    """删除某个会话的全部消息（仅限本账号）"""
    result = await db.execute(
        delete(PolicyChatHistory).where(
            PolicyChatHistory.username == current_user.username,
            PolicyChatHistory.session_id == session_id,
        )
    )
    await db.flush()
    return {"deleted": result.rowcount}
