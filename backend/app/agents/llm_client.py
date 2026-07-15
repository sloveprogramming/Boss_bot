"""统一的LLM客户端 — 支持OpenAI兼容接口 + 全链路追踪 + 流式输出"""
from typing import Optional, AsyncGenerator
from app.config import settings
from app.agents.tracing import trace_llm_call


class LLMClient:
    """统一的LLM调用接口，支持全链路追踪"""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER  # LLM提供商
        self._openai_client = None  # OpenAI异步客户端实例
        self._model_name = settings.OPENAI_MODEL  # 模型名称（用于trace记录）

    # 获取OpenAI异步客户端
    def _get_openai(self):
        """延迟初始化OpenAI异步客户端"""
        if self._openai_client is None:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        return self._openai_client

    @trace_llm_call(function_name="llm_chat")
    async def chat(self, system: str, messages: list,
                   response_format: Optional[dict] = None,
                   temperature: float = 0.1, max_tokens: int = 4096) -> str:
        """统一的chat调用入口（带全链路追踪）

        Args:
            system: 系统提示词
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            response_format: OpenAI风格的response_format（如{"type": "json_object"}）
            temperature: 采样温度（越低越确定）
            max_tokens: 最大输出token数

        Returns:
            模型回复文本
        """
        return await self._chat_openai(system, messages, response_format, temperature, max_tokens)

    # 调用OpenAI兼容接口
    async def _chat_openai(self, system: str, messages: list,
                           response_format: Optional[dict],
                           temperature: float, max_tokens: int) -> str:
        """调用OpenAI兼容接口"""
        client = self._get_openai()
        kwargs = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    # 获取文本向量嵌入
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本向量嵌入"""
        client = self._get_openai()
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in resp.data]

    async def stream_chat(
        self, system: str, messages: list,
        temperature: float = 0.1, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式 chat 调用 — 逐 token 产出文本块

        使用 OpenAI 流式 API（stream=True），通过 async generator yield 每个 token。
        前端通过 SSE (Server-Sent Events) 逐字接收。

        Args:
            system: 系统提示词
            messages: 对话消息列表
            temperature: 采样温度
            max_tokens: 最大输出 token 数

        Yields:
            每段文本增量（可能是单个 token 或多个 token 的聚合）
        """
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

    async def stream_chat_json(
        self, system: str, messages: list,
        temperature: float = 0.1, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式 JSON 输出 — 累积完整 JSON 块后 yield

        因为 JSON 不能逐 token 拼接（会破坏 JSON 结构），
        此方法缓冲所有流式内容，解析成完整 JSON 后一次性 yield。

        Args:
            system: 系统提示词
            messages: 对话消息列表
            temperature: 采样温度
            max_tokens: 最大输出 token 数

        Yields:
            完整的 JSON 字符串
        """
        client = self._get_openai()
        kwargs: dict = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "response_format": {"type": "json_object"},
        }

        response = await client.chat.completions.create(**kwargs)

        buffer = []
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                buffer.append(content)

        yield "".join(buffer)


# 全局单例：整个应用共享同一个LLM客户端
llm_client = LLMClient()
