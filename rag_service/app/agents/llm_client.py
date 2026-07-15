"""LLM 客户端 — RAG 服务专用

支持 OpenAI 兼容接口 + 流式输出。
"""
from typing import Optional, AsyncGenerator
from config import settings


class LLMClient:
    """统一的 LLM 调用接口"""

    def __init__(self):
        self._openai_client = None

    def _get_openai(self):
        if self._openai_client is None:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        return self._openai_client

    async def chat(self, system: str, messages: list,
                   response_format: Optional[dict] = None,
                   temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """同步 chat 调用"""
        client = self._get_openai()
        kwargs: dict = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def stream_chat(
        self, system: str, messages: list,
        temperature: float = 0.1, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式 chat — 逐 token 产出"""
        client = self._get_openai()
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content


llm_client = LLMClient()
