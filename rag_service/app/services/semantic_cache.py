"""热点问题语义缓存 — Redis + embedding 相似度匹配

工作原理：
  1. 问题到来 → 计算 embedding
  2. 从 Redis 加载所有缓存的 embedding → 逐一计算 cosine similarity
  3. 最高相似度 > 阈值(默认0.92) → 返回缓存的 answer
  4. 否则 → 执行 RAG + LLM → 结果写入 Redis

存储结构（Redis HASH）:
  key:  semantic_cache:{md5_of_question}
  fields:
    question: 原始问题
    answer: LLM 回答
    embedding: base64 编码的向量
    timestamp: 缓存时间
    hit_count: 命中次数

降级策略：
  - Redis 不可用时自动跳过缓存，不影响主流程
  - 通过配置 SEMANTIC_CACHE_ENABLED 开关控制
"""
import json
import base64
import hashlib
import logging
import numpy as np
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SemanticCache:
    """语义缓存：基于 embedding 相似度的问答缓存"""

    def __init__(self):
        self._redis = None
        self._redis_available = False
        self._prefix = "semantic_cache:"

    def _get_redis(self):
        """延迟初始化 Redis 连接"""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                from config import settings

                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self._redis_available = True
                logger.info("语义缓存: Redis 连接成功")
            except Exception as e:
                logger.warning(f"语义缓存: Redis 连接失败（降级为无缓存）: {e}")
                self._redis_available = False
        return self._redis

    async def _embed(self, text: str) -> Optional[list]:
        """计算文本的 embedding 向量

        复用 BGE-M3 embedding 函数（与 RAG 系统一致）。
        如果 BGE-M3 不可用，返回 None。
        """
        try:
            from milvus_model.hybrid import BGEM3EmbeddingFunction
            from app.config import settings

            ef = BGEM3EmbeddingFunction(
                model_name_or_path=settings.EMBEDDING_MODEL,
                use_fp16=False,
                device="cpu",
            )
            result = ef([text])
            return result["dense"][0].tolist()
        except Exception:
            # 降级: 尝试用 OpenAI API
            try:
                from app.agents.llm_client import llm_client
                embeddings = await llm_client.embed([text])
                return embeddings[0]
            except Exception:
                return None

    def _cosine_similarity(self, vec_a: list, vec_b: list) -> float:
        """计算余弦相似度"""
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _make_key(self, text: str) -> str:
        """生成缓存键"""
        hash_val = hashlib.md5(text.encode("utf-8")).hexdigest()
        return f"{self._prefix}{hash_val}"

    async def get(self, question: str) -> Optional[dict]:
        """语义缓存查找：找到语义相似的已缓存问答

        Args:
            question: 用户问题

        Returns:
            缓存命中时返回 {"answer": ..., "source": "cache"}，否则返回 None
        """
        from app.config import settings

        if not settings.SEMANTIC_CACHE_ENABLED:
            return None

        redis = self._get_redis()
        if not self._redis_available or redis is None:
            return None

        try:
            # 1) 计算当前问题的 embedding
            query_emb = await self._embed(question)
            if query_emb is None:
                return None

            # 2) 扫描所有缓存键
            cursor = 0
            best_match = None
            best_score = 0.0

            while True:
                cursor, keys = await redis.scan(cursor=cursor, match=f"{self._prefix}*", count=100)
                for key in keys:
                    # 获取缓存的 embedding
                    cached_emb_b64 = await redis.hget(key, "embedding")
                    if not cached_emb_b64:
                        continue

                    cached_emb = json.loads(base64.b64decode(cached_emb_b64).decode("utf-8"))
                    score = self._cosine_similarity(query_emb, cached_emb)

                    if score > best_score:
                        best_score = score
                        best_match = key

                if cursor == 0:
                    break

            # 3) 判断是否命中
            threshold = settings.CACHE_SIMILARITY_THRESHOLD
            if best_match and best_score >= threshold:
                cached_answer = await redis.hget(best_match, "answer")
                cached_question = await redis.hget(best_match, "question")

                # 增加命中次数
                await redis.hincrby(best_match, "hit_count", 1)

                logger.info(
                    f"语义缓存命中: score={best_score:.4f}, "
                    f"原问题='{cached_question}', 当前问题='{question}'"
                )
                return {
                    "answer": cached_answer,
                    "cached_question": cached_question,
                    "similarity": round(best_score, 4),
                    "source": "cache",
                }

            logger.debug(f"语义缓存未命中: best_score={best_score:.4f}, threshold={threshold}")
            return None

        except Exception as e:
            logger.warning(f"语义缓存查询失败（降级）: {e}")
            return None

    async def set(self, question: str, answer: str, ttl: int = None) -> bool:
        """写入语义缓存

        Args:
            question: 用户问题
            answer: LLM 回答
            ttl: 过期时间（秒），默认使用配置

        Returns:
            是否写入成功
        """
        from app.config import settings

        if not settings.SEMANTIC_CACHE_ENABLED:
            return False

        redis = self._get_redis()
        if not self._redis_available or redis is None:
            return False

        try:
            query_emb = await self._embed(question)
            if query_emb is None:
                return False

            key = self._make_key(question)
            emb_b64 = base64.b64encode(json.dumps(query_emb).encode("utf-8")).decode("utf-8")

            await redis.hset(key, mapping={
                "question": question,
                "answer": answer,
                "embedding": emb_b64,
                "timestamp": datetime.utcnow().isoformat(),
                "hit_count": 0,
            })

            expire = ttl or settings.SEMANTIC_CACHE_TTL
            await redis.expire(key, expire)

            logger.info(f"语义缓存写入: question='{question[:50]}...', ttl={expire}s")
            return True

        except Exception as e:
            logger.warning(f"语义缓存写入失败（非关键）: {e}")
            return False


# 全局单例
semantic_cache = SemanticCache()
