"""LLM 客户端 — RAG 服务专用

支持 OpenAI 兼容接口 + 流式输出 + 依赖注入。
"""
from typing import Optional, AsyncGenerator
from config import settings


class LLMClient:
    """统一的 LLM 调用接口 — 支持依赖注入"""

    def __init__(self, openai_client=None, model_name: Optional[str] = None):
        """构造 LLM 客户端

        Args:
            openai_client: AsyncOpenAI 客户端实例（可选，用于注入 mock）
            model_name: 模型名（可选，默认从 settings 读取）
        """
        self._injected_client = openai_client
        self._lazy_client = None
        self._model_name = model_name or settings.OPENAI_MODEL

    def _get_openai(self):
        """获取 OpenAI 客户端（注入优先 → lazy 创建回退）"""
        if self._injected_client is not None:
            return self._injected_client
        if self._lazy_client is None:
            from openai import AsyncOpenAI
            self._lazy_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        return self._lazy_client

    async def chat(self, system: str, messages: list,
                   response_format: Optional[dict] = None,
                   temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """同步 chat 调用"""
        client = self._get_openai()
        kwargs: dict = {
            "model": self._model_name,
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
            model=self._model_name,
            messages=[{"role": "system", "content": system}] + messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content


# 全局单例 — 无参数构造，从 settings 自动读取配置（兼容旧代码）
llm_client = LLMClient()
