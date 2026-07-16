"""企业规章制度 RAG Agent — 混合检索 + 双层分块 + CrossEncoder 重排序

完整 RAG 流水线：
  index: 文档 → 双层分块(父1200/子300) → BGE-M3 向量化 → Milvus(dense+sparse)
  query: 问题 → 查询分类 → 混合检索 → 子块命中 → 父块去重 → CrossEncoder 重排 → LLM 回答

依赖注入：
  __init__ 可接受 milvus_client / embedding_func / reranker / splitter / llm_client。
  未传入时回退到内部 lazy 创建和全局 settings 读取（兼容旧代码）。
"""
import json
import os
import hashlib
import logging
import re
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import POLICY_AGENT_SYSTEM, POLICY_AGENT_PROMPT
from app.models import PolicyDocument, PolicyChatHistory

logger = logging.getLogger(__name__)


class PolicyRAGAgent:
    """企业规章制度 RAG Agent — 支持依赖注入"""

    def __init__(self,
                 milvus_client=None,
                 embedding_func=None,
                 reranker=None,
                 splitter=None,
                 llm_client=None,
                 semantic_cache=None,
                 collection_name: Optional[str] = None):
        """构造 RAG Agent

        Args:
            milvus_client:   MilvusClient 实例（注入后直接使用，跳过内部创建）
            embedding_func:  BGE-M3 嵌入函数（注入后跳过模型加载）
            reranker:        CrossEncoder 重排序模型（注入后跳过加载）
            splitter:        PolicyParentChildSplitter 实例（注入后跳过创建）
            llm_client:      LLMClient 实例（注入后用于测试替换）
            semantic_cache:  SemanticCache 实例（注入后用于测试替换）
            collection_name: Milvus 集合名（可选）
        """
        self._milvus_client = milvus_client
        self._embedding_func = embedding_func
        self._reranker = reranker
        self._splitter = splitter
        self._llm_client = llm_client
        self._semantic_cache = semantic_cache
        self._collection_name = collection_name or "policy_docs_v2"

    # ---- 获取依赖（注入优先 → lazy 回退） ----
    def _get_config(self):
        from config import settings
        return settings

    def _get_llm(self):
        if self._llm_client is not None:
            return self._llm_client
        from app.agents import llm_client
        return llm_client

    def _get_cache(self):
        if self._semantic_cache is not None:
            return self._semantic_cache
        from app.services import semantic_cache
        return semantic_cache

    async def _ensure_initialized(self):
        """确保所有组件已初始化（注入的跳过，未注入的 lazy 创建）"""
        if self._splitter is None:
            cfg = self._get_config()
            from app.services import PolicyParentChildSplitter
            self._splitter = PolicyParentChildSplitter(
                parent_chunk_size=cfg.PARENT_CHUNK_SIZE,
                child_chunk_size=cfg.CHILD_CHUNK_SIZE,
                chunk_overlap=cfg.CHUNK_OVERLAP,
            )
        if self._embedding_func is None:
            self._init_embedding()
        if self._milvus_client is None:
            self._init_milvus()
        if self._reranker is None:
            self._init_reranker()

    def _init_embedding(self):
        """初始化 BGE-M3 嵌入函数"""
        try:
            from milvus_model.hybrid import BGEM3EmbeddingFunction
            model_name = self._get_config().EMBEDDING_MODEL
            logger.info(f"加载 BGE-M3 嵌入模型: {model_name}")
            self._embedding_func = BGEM3EmbeddingFunction(
                model_name_or_path=model_name,
                use_fp16=False,
                device="cpu",
            )
            logger.info("BGE-M3 嵌入模型加载完成")
        except ImportError:
            logger.warning("milvus-model 未安装，回退到 HuggingFace Embedding（仅稠密向量）")
            self._embedding_func = None
        except Exception as e:
            logger.error(f"BGE-M3 加载失败: {e}，使用降级模式")
            self._embedding_func = None

    def _init_milvus(self):
        """初始化 Milvus 客户端并创建/加载集合"""
        from pymilvus import MilvusClient, DataType
        cfg = self._get_config()
        self._milvus_client = MilvusClient(
            uri=f"http://{cfg.MILVUS_HOST}:{cfg.MILVUS_PORT}",
        )
        self._create_or_load_collection()

    def _create_or_load_collection(self):
        """创建新版混合检索集合"""
        from pymilvus import MilvusClient, DataType
        exists = self._milvus_client.has_collection(self._collection_name)
        if not exists:
            schema = self._milvus_client.create_schema(auto_id=False, enable_dynamic_field=True)
            schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=100)
            schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT16_VECTOR, dim=768)
            schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field(field_name="parent_id", datatype=DataType.VARCHAR, max_length=100)
            schema.add_field(field_name="parent_content", datatype=DataType.VARCHAR, max_length=65535)
            schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=500)
            schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=100)
            schema.add_field(field_name="doc_id", datatype=DataType.INT64)
            index_params = self._milvus_client.prepare_index_params()
            index_params.add_index(field_name="dense_vector", index_name="dense_index",
                                   index_type="IVF_FLAT", metric_type="IP", params={"nlist": 128})
            index_params.add_index(field_name="sparse_vector", index_name="sparse_index",
                                   index_type="SPARSE_INVERTED_INDEX", metric_type="IP",
                                   params={"drop_ratio_build": 0.2})
            self._milvus_client.create_collection(
                collection_name=self._collection_name, schema=schema, index_params=index_params)
            logger.info(f"已创建混合检索集合: {self._collection_name}")
        else:
            logger.info(f"已加载集合: {self._collection_name}")
        self._milvus_client.load_collection(self._collection_name)

    def _init_reranker(self):
        """初始化 CrossEncoder 重排序模型"""
        try:
            from sentence_transformers import CrossEncoder
            model_name = self._get_config().RERANKER_MODEL
            logger.info(f"加载 CrossEncoder 重排序模型: {model_name}")
            self._reranker = CrossEncoder(model_name)
            logger.info("重排序模型加载完成")
        except Exception as e:
            logger.warning(f"CrossEncoder 加载失败 {e}，跳过重排序")
            self._reranker = None

    # ================================================================
    # 查询分类
    # ================================================================
    async def _is_policy_query(self, question: str) -> bool:
        cfg = self._get_config()
        for kw in cfg.POLICY_KEYWORDS:
            if kw in question:
                return True
        greeting_patterns = [
            r"^(你好|您好|hi|hello|嗨|hey)\s*$",
            r"^(早|早上好|下午好|晚上好|晚安)\s*$",
            r"^(再见|拜拜|bye|回见)\s*$",
            r"^(谢谢|感谢|辛苦了|好的|明白)\s*$",
        ]
        for pat in greeting_patterns:
            if re.match(pat, question.strip(), re.IGNORECASE):
                return False
        try:
            return await self._classify_with_llm(question)
        except Exception:
            return True

    async def _classify_with_llm(self, question: str) -> bool:
        llm = self._get_llm()
        classify_prompt = f"""判断以下问题是否与企业内部规章制度相关（如考勤、请假、薪酬、报销、福利、绩效等）。
只需回答"是"或"否"，不要输出其他内容。

问题：{question}
回答："""
        try:
            result = await llm.chat(
                system='你是一个企业制度分类器。只回答"是"或"否"。',
                messages=[{"role": "user", "content": classify_prompt}],
                temperature=0.0, max_tokens=10,
            )
            return "是" in result
        except Exception:
            return True

    # ================================================================
    # 索引文档
    # ================================================================
    async def index_document(self, doc_id: int, db: AsyncSession):
        """将文档进行双层分块并建立混合向量索引"""
        await self._ensure_initialized()
        result = await db.execute(select(PolicyDocument).where(PolicyDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc or not doc.content:
            raise ValueError("文档不存在或内容为空")

        from langchain_core.documents import Document as LCDocument
        lc_doc = LCDocument(
            page_content=doc.content,
            metadata={"doc_id": doc.id, "title": doc.title, "category": doc.category or ""},
        )
        child_chunks = self._splitter.split_documents([lc_doc])
        texts = [c.page_content for c in child_chunks]
        data = self._build_milvus_data(texts, child_chunks)
        if data:
            self._milvus_client.upsert(collection_name=self._collection_name, data=data)

        doc.chunk_count = len(child_chunks)
        doc.indexed = True
        await db.flush()

        parent_ids = set(c.metadata["parent_id"] for c in child_chunks)
        logger.info(f"文档索引完成: doc_id={doc_id}, 父块={len(parent_ids)}, 子块={len(child_chunks)}")
        return {"chunks": len(child_chunks), "parents": len(parent_ids)}

    def _build_milvus_data(self, texts: List[str], chunks: List) -> List[dict]:
        if self._embedding_func:
            embeddings = self._embedding_func(texts)
        else:
            logger.error("嵌入函数未初始化，无法构建向量数据")
            return []
        import numpy as np
        data = []
        for i, chunk in enumerate(chunks):
            text_hash = hashlib.md5(texts[i].encode("utf-8")).hexdigest()
            sparse_vec = {}
            row = embeddings["sparse"][i]
            for idx, val in zip(row.col, row.data):
                sparse_vec[int(idx)] = float(val)
            data.append({
                "id": text_hash,
                "text": texts[i],
                "dense_vector": embeddings["dense"][i].astype(np.float16),
                "sparse_vector": sparse_vec,
                "parent_id": chunk.metadata.get("parent_id", ""),
                "parent_content": chunk.metadata.get("parent_content", ""),
                "title": chunk.metadata.get("title", ""),
                "category": chunk.metadata.get("category", ""),
                "doc_id": chunk.metadata.get("doc_id", -1),
            })
        return data

    async def reindex_all(self, db: AsyncSession):
        """清空向量库并重新索引所有文档"""
        await self._ensure_initialized()
        result = await db.execute(select(PolicyDocument).where(PolicyDocument.indexed == True))
        docs = result.scalars().all()
        for doc in docs:
            doc.indexed = False
        try:
            self._milvus_client.drop_collection(self._collection_name)
        except Exception:
            pass
        self._create_or_load_collection()
        result = await db.execute(select(PolicyDocument))
        all_docs = result.scalars().all()
        indexed_count = 0
        for doc in all_docs:
            if doc.content:
                await self.index_document(doc.id, db)
                indexed_count += 1
        logger.info(f"全部重新索引完成: {indexed_count} 文档")
        return {"reindexed": indexed_count}

    # ================================================================
    # 检索（混合检索 + 重排序）
    # ================================================================
    async def query(self, question: str, db: AsyncSession, top_k: int = None) -> list:
        await self._ensure_initialized()
        cfg = self._get_config()
        top_k = top_k or cfg.RERANK_CANDIDATES_M

        query_embeddings = self._embedding_func([question])
        dense_vec = query_embeddings["dense"][0].astype("float16")
        sparse_vec = {}
        row = query_embeddings["sparse"][0]
        for idx, val in zip(row.col, row.data):
            sparse_vec[int(idx)] = float(val)

        retrieval_k = cfg.RETRIEVAL_TOP_K
        from pymilvus import AnnSearchRequest, WeightedRanker
        dense_req = AnnSearchRequest(
            data=[dense_vec], anns_field="dense_vector",
            param={"metric_type": "IP", "params": {"nprobe": 10}}, limit=retrieval_k)
        sparse_req = AnnSearchRequest(
            data=[sparse_vec], anns_field="sparse_vector",
            param={"metric_type": "IP"}, limit=retrieval_k)
        ranker = WeightedRanker(cfg.HYBRID_DENSE_WEIGHT, cfg.HYBRID_SPARSE_WEIGHT)
        results = self._milvus_client.hybrid_search(
            collection_name=self._collection_name, reqs=[dense_req, sparse_req],
            ranker=ranker, limit=retrieval_k,
            output_fields=["text", "parent_id", "parent_content", "title", "category"],
        )[0]

        parent_map = {}
        for hit in results:
            entity = hit["entity"]
            parent_id = entity.get("parent_id", "")
            parent_content = entity.get("parent_content", "")
            if parent_id and parent_content and parent_id not in parent_map:
                parent_map[parent_id] = {
                    "content": parent_content,
                    "title": entity.get("title", "未知"),
                    "category": entity.get("category", ""),
                }
        parent_candidates = list(parent_map.values())

        if self._reranker and len(parent_candidates) >= 2:
            pairs = [[question, p["content"]] for p in parent_candidates]
            scores = self._reranker.predict(pairs)
            scored = list(zip(scores, parent_candidates))
            scored.sort(key=lambda x: x[0], reverse=True)
            parent_candidates = [p for _, p in scored]

        parent_candidates = parent_candidates[:top_k]
        results_out = []
        for i, pc in enumerate(parent_candidates):
            results_out.append({
                "content": pc["content"][:500],
                "title": pc["title"],
                "category": pc["category"],
                "chunk_index": i,
                "relevance_score": round(1.0 - (i / max(len(parent_candidates), 1)), 3),
            })
        return results_out

    # ================================================================
    # 聊天接口
    # ================================================================
    async def chat(self, message: str, db: AsyncSession,
                   session_id: Optional[str] = None,
                   candidate_id: Optional[int] = None) -> dict:
        await self._ensure_initialized()
        import uuid

        llm = self._get_llm()
        cache = self._get_cache()

        if not session_id:
            session_id = f"policy_{uuid.uuid4().hex[:12]}"

        # 1.1) 语义缓存查找
        cached = await cache.get(message)
        if cached:
            logger.info(f"语义缓存命中: question='{message[:50]}'")
            return {
                "session_id": session_id,
                "answer": cached["answer"],
                "confidence": "high",
                "cited_sources": [{"title": "缓存命中", "category": "system"}],
                "disclaimer": None,
                "cached": True,
            }

        # 1) 查询分类
        if not await self._is_policy_query(message):
            logger.info(f"非制度问题，跳过RAG检索: {message[:50]}")
            answer = await llm.chat(
                system="你是一个友好的企业智能助手。用户的问题与公司规章制度无关，请正常回答。",
                messages=[{"role": "user", "content": message}],
                temperature=0.5, max_tokens=1024,
            )
            import asyncio
            asyncio.create_task(cache.set(message, answer))
            for role, content in [("user", message), ("assistant", answer)]:
                db.add(PolicyChatHistory(session_id=session_id, role=role, content=content[:2000]))
            await db.flush()
            return {"session_id": session_id, "answer": answer, "confidence": "high",
                    "cited_sources": [], "disclaimer": None}

        # 2) RAG 检索
        retrieved = await self.query(message, db=db)

        # 3) 构建上下文
        if retrieved:
            chunks_text = "\n\n---\n\n".join(
                f"[来源: {r['title']} - {r['category']}]\n{r['content']}" for r in retrieved)
        else:
            chunks_text = "暂无相关的企业规章制度文档。"

        # 4) LLM 生成
        prompt = POLICY_AGENT_PROMPT.format(retrieved_chunks=chunks_text, user_question=message)
        answer = await llm.chat(
            system=POLICY_AGENT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=2048,
        )

        # 5) 置信度
        if not retrieved:
            confidence = "low"
            disclaimer = "当前知识库中未找到直接相关的政策文档，以上回答基于通用认知，建议咨询HR确认。"
        elif any(r.get("relevance_score", 0) > 0.7 for r in retrieved):
            confidence = "high"
            disclaimer = None
        else:
            confidence = "medium"
            disclaimer = "以上回答仅供参考，如有疑问请咨询HR部门确认。"

        # 6) 引用来源
        cited_sources = []
        seen_titles = set()
        for r in retrieved:
            title = r["title"]
            if title and title not in seen_titles:
                seen_titles.add(title)
                cited_sources.append({"title": title, "category": r["category"]})

        # 7) 写入缓存 + 保存历史
        import asyncio
        asyncio.create_task(cache.set(message, answer))
        for role, content in [("user", message), ("assistant", answer)]:
            db.add(PolicyChatHistory(
                session_id=session_id, role=role, content=content[:2000],
                retrieved_chunks=[r["content"] for r in retrieved[:3]] if role == "assistant" else None,
                confidence=confidence if role == "assistant" else None,
                cited_sources=cited_sources if role == "assistant" else None,
            ))
        await db.flush()
        return {"session_id": session_id, "answer": answer, "confidence": confidence,
                "cited_sources": cited_sources, "disclaimer": disclaimer}

    async def get_history(self, session_id: str, db: AsyncSession, limit: int = 20) -> list:
        result = await db.execute(
            select(PolicyChatHistory)
            .where(PolicyChatHistory.session_id == session_id)
            .order_by(PolicyChatHistory.created_at.desc())
            .limit(limit)
        )
        chats = result.scalars().all()
        chats.reverse()
        return [{"role": c.role, "content": c.content, "confidence": c.confidence,
                 "cited_sources": c.cited_sources,
                 "created_at": c.created_at.isoformat() if c.created_at else ""} for c in chats]


# 全局单例 — 无参数构造，默认 lazy 创建所有依赖（兼容旧代码）
policy_rag_agent = PolicyRAGAgent()
