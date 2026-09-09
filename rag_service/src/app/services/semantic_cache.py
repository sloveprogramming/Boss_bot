# 【小白导读】语义缓存：问过的问题（语义相似）直接复用之前的答案，
#   省一次 LLM 调用（省钱+提速）。判断"语义相似"用的是向量距离而非字面相同。
"""热点问题语义缓存 — Redis + embedding 相似度匹配

依赖注入：
  __init__ 可接受 redis_client 和 embedding_func 参数。
  未传入时回退到内部 lazy 创建（兼容旧代码）。
"""
import json
import base64
import hashlib
import logging
import numpy as np
from typing import Optional, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class SemanticCache:
    """语义缓存：基于 embedding 相似度的问答缓存 — 支持依赖注入"""

    def __init__(self,
                 redis_client=None,
                 embedding_func: Optional[Callable] = None,
                 cache_prefix: Optional[str] = None):
        """构造语义缓存

        Args:
            redis_client:    Redis 客户端实例（注入后直接使用）
            embedding_func:  嵌入函数 callable(text) -> list[float]（注入后复用）
            cache_prefix:    Redis key 前缀（可选）
        """
        self._redis = redis_client
        if redis_client is not None:
            self._redis_available = True
        else:
            self._redis_available = False
        self._embedding_func = embedding_func
        self._prefix = cache_prefix or "semantic_cache:"

    def _get_redis(self):
        """获取 Redis 客户端 — 注入优先 → lazy 创建回退"""
        if self._redis is not None:
            return self._redis
        if not hasattr(self, '_lazy_redis_tried'):
            self._lazy_redis_tried = True
            try:
                import redis.asyncio as aioredis
                from app.config import settings
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
        """计算文本的 embedding 向量 — 注入优先 → lazy 创建回退"""
        # 1) 注入的 embedding 函数优先
        if self._embedding_func is not None:
            try:
                return await self._embedding_func(text)
            except Exception:
                # 同步 callable 兼容
                try:
                    return self._embedding_func(text)
                except Exception:
                    return None

        # 2) Lazy 回退：BGE-M3
        try:
            from milvus_model.hybrid import BGEM3EmbeddingFunction
            from app.config import settings
            ef = BGEM3EmbeddingFunction(
                model_name_or_path=settings.EMBEDDING_MODEL,
                use_fp16=False, device="cpu",
            )
            result = ef([text])
            return result["dense"][0].tolist()
        except Exception:
            # 3) 最终降级：OpenAI API
            try:
                from app.agents import llm_client
                embeddings = await llm_client.embed([text])
                return embeddings[0]
            except Exception:
                return None

    def _cosine_similarity(self, vec_a: list, vec_b: list) -> float:
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _make_key(self, text: str) -> str:
        hash_val = hashlib.md5(text.encode("utf-8")).hexdigest()
        return f"{self._prefix}{hash_val}"

    async def get(self, question: str) -> Optional[dict]:
        """语义缓存查找"""
        from app.config import settings
        if not settings.SEMANTIC_CACHE_ENABLED:
            return None

        redis = self._get_redis()
        if not self._redis_available or redis is None:
            return None

        try:
            query_emb = await self._embed(question)
            if query_emb is None:
                return None

            cursor = 0
            best_match = None
            best_score = 0.0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match=f"{self._prefix}*", count=100)
                for key in keys:
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

            threshold = settings.CACHE_SIMILARITY_THRESHOLD
            if best_match and best_score >= threshold:
                cached_answer = await redis.hget(best_match, "answer")
                cached_question = await redis.hget(best_match, "question")
                await redis.hincrby(best_match, "hit_count", 1)
                logger.info(f"语义缓存命中: score={best_score:.4f}")
                return {
                    "answer": cached_answer,
                    "cached_question": cached_question,
                    "similarity": round(best_score, 4),
                    "source": "cache",
                }
            return None
        except Exception as e:
            logger.warning(f"语义缓存查询失败（降级）: {e}")
            return None

    async def set(self, question: str, answer: str, ttl: int = None) -> bool:
        """写入语义缓存"""
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


# 全局单例 — 无参数构造，默认 lazy 创建依赖（兼容旧代码）
semantic_cache = SemanticCache()
