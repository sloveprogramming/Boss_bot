"""企业制度文档管理 API — 文档入库 + 自动索引 + 简单问答"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import PolicyDocument, UserRole
from app.dependencies import require_role
from pydantic import BaseModel
from typing import Optional

router = APIRouter(
    prefix="/api/policy",
    tags=["制度文档"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


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

    # 后台异步索引到 Milvus
    import asyncio
    asyncio.create_task(_index_document_bg(doc_record.id))

    return {
        "id": doc_record.id,
        "title": doc_record.title,
        "category": doc_record.category,
        "file_name": file.filename,
        "message": "文档已保存，正在后台索引到向量库...",
    }


async def _index_document_bg(doc_id: int):
    """后台任务：在线程中执行同步索引（避免 asyncio 冲突）"""
    import asyncio
    from app.services import index_document_sync

    loop = asyncio.get_event_loop()
    try:
        chunks = await loop.run_in_executor(None, index_document_sync, doc_id)
        print(f"[索引完成] doc_id={doc_id}, chunks={chunks}")
    except Exception as e:
        print(f"[索引失败] doc_id={doc_id}: {e}")


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
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """删除指定制度文档"""
    result = await db.execute(
        select(PolicyDocument).where(PolicyDocument.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    await db.delete(doc)
    await db.flush()
    return {"status": "deleted", "doc_id": doc_id}


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
