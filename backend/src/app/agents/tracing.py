# 【小白导读】LLM 可观测性的"记账员"：trace_llm_call 装饰器包住每次 LLM 调用，
#   自动记录输入输出、token 估算、耗时，写入 llm_logs 表（可选同步 Langfuse）。
"""LLM 调用链路追踪 — @trace_llm_call 装饰器

使用方式：
    @trace_llm_call(function_name="resume_analyze")
    async def chat(self, system, messages, ...):
        ...

自动记录：
    - 调用时间、功能名称、模型
    - 请求内容（system prompt + messages）
    - 响应内容
    - Token 用量（需 API 返回）
    - 延迟（毫秒）
"""
import time
import logging
import asyncio
from functools import wraps
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ===== Langfuse（可选）— 未配置时自动跳过，零侵入 =====
_langfuse_client = None
_langfuse_checked = False


def _get_langfuse():
    """懒加载 Langfuse 客户端；未启用或导入失败返回 None（只尝试一次，避免重复报错）"""
    global _langfuse_client, _langfuse_checked
    if _langfuse_checked:
        return _langfuse_client
    _langfuse_checked = True
    try:
        from app.config import settings
        if not settings.LANGFUSE_ENABLED:
            return None
        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        logger.info("Langfuse 已启用: %s", settings.LANGFUSE_HOST)
    except Exception as e:
        logger.warning("Langfuse 初始化失败（本次运行不再尝试）: %s", e)
        _langfuse_client = None
    return _langfuse_client

# 保存异步 DB 会话的上下文变量（由 middleware 或调用方设置）
_trace_db_session = None


def set_trace_db_session(session):
    """设置当前请求的数据库会话（用于异步写日志）"""
    global _trace_db_session
    _trace_db_session = session


async def _write_log_async(function_name: str, model: str,
                           system_prompt: str, messages: list,
                           response: str, prompt_tokens: int,
                           completion_tokens: int, total_tokens: int,
                           latency_ms: float, session_id: Optional[str] = None):
    """异步写 LLM 调用日志到数据库

    使用独立的数据库会话，避免影响主流程事务。
    """
    try:
        from app.database import async_session_factory
        from app.models.llm_log import LLMCallLog

        async with async_session_factory() as db:
            log = LLMCallLog(
                function_name=function_name,
                model=model,
                system_prompt=str(system_prompt)[:500] if system_prompt else None,
                messages=messages,
                response=str(response)[:2000] if response else None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=round(latency_ms, 2),
                session_id=session_id,
            )
            db.add(log)
            await db.commit()
        # Langfuse 追踪上报（可选，失败不影响主流程）
        # v3 SDK 手动埋点：start_span 建 trace → update_trace 关联会话 → start_generation 记录 LLM 调用
        try:
            lf = _get_langfuse()
            if lf is not None:
                trace_id = lf.create_trace_id()
                span = lf.start_span(
                    name=function_name,
                    trace_context={"trace_id": trace_id},
                    metadata={"model": model, "latency_ms": round(latency_ms, 2)},
                )
                span.update_trace(session_id=session_id, name=function_name)
                gen = span.start_generation(
                    name=function_name,
                    model=model,
                    input={"system": system_prompt, "messages": messages},
                    output=response,
                    usage_details={
                        "input": prompt_tokens,
                        "output": completion_tokens,
                        "total": total_tokens,
                    },
                )
                gen.end()
                span.end()
                lf.flush()
        except Exception as lf_err:
            logger.debug("Langfuse 导出失败（非关键）: %s", lf_err)
    except Exception as e:
        # 日志写入失败不影响主流程
        logger.warning(f"LLM trace 写入失败（非关键）: {e}")


def trace_llm_call(function_name: str = "unknown"):
    """LLM 调用追踪装饰器

    装饰 llm_client.chat() 方法，自动记录调用的输入输出、token用量、延迟。

    Args:
        function_name: 功能名称，用于区分调用来源（如 "resume_analyze" / "rag_chat"）
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(self, system: str, messages: list,
                          response_format=None,
                          temperature: float = 0.1,
                          max_tokens: int = 4096, **kwargs):
            start_time = time.time()
            model_name = getattr(self, '_model_name', 'unknown')

            # 执行原始调用
            try:
                response = await func(self, system, messages,
                                      response_format=response_format,
                                      temperature=temperature,
                                      max_tokens=max_tokens, **kwargs)
                latency = (time.time() - start_time) * 1000
            except Exception as e:
                latency = (time.time() - start_time) * 1000
                # 即使失败也记录日志
                asyncio.create_task(_write_log_async(
                    function_name=function_name,
                    model=model_name,
                    system_prompt=system,
                    messages=messages,
                    response=f"ERROR: {str(e)}",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    latency_ms=latency,
                ))
                raise

            # 估算 token 用量（OpenAI 兼容接口标准）
            combined_prompt = f"System: {system}\nMessages: {messages}"
            prompt_tokens = _estimate_tokens(combined_prompt)
            completion_tokens = _estimate_tokens(response)
            total_tokens = prompt_tokens + completion_tokens

            # 异步写日志（不阻塞主流程）
            asyncio.create_task(_write_log_async(
                function_name=function_name,
                model=model_name,
                system_prompt=system,
                messages=messages,
                response=response,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                latency_ms=latency,
            ))

            return response
        return wrapper
    return decorator


def _estimate_tokens(text) -> int:
    """粗略估算 token 数量（中文约 1.5 字符/token，英文约 4 字符/token）

    不需要精确计算，用于相对比较即可。
    """
    if isinstance(text, list):
        text = str(text)
    if not isinstance(text, str):
        text = str(text)
    # 粗略估计：中文1.5字/token，英文4字/token
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4) or 1
