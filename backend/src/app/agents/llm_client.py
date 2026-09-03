"""统一的 LLM 客户端 — OpenAI 兼容接口 + 全链路追踪 + 流式输出

所有 LLM 调用的唯一入口，提供三种调用模式：
  chat()          — 普通同步调用，等完整回复【简历分析、面试排期】
  stream_chat()   — 流式逐 token 产出【SSE 推给前端逐字渲染】
  stream_chat_json() — 流式累积后一次性返回完整 JSON【JSON 不能逐字拼】

依赖注入：
  构造器可接受 openai_client 和 model_name 参数，支持测试替换。
  未传入时自动从全局 settings 创建（兼容旧代码）。
"""
from typing import Optional, AsyncGenerator
from app.config import settings
from app.agents.tracing import trace_llm_call


class LLMClient:
    """统一的 LLM 调用接口 — 支持依赖注入"""

    def __init__(self, openai_client=None, model_name: Optional[str] = None):
        """构造 LLM 客户端

        Args:
            openai_client: AsyncOpenAI 客户端实例（可选，用于注入 mock）
            model_name: 模型名（可选，默认从 settings 读取）
        """
        self._injected_client = openai_client      # 外部注入的客户端（优先级最高）
        self._lazy_client = None                   # 内部 lazy 创建的客户端
        self._model_name = model_name or settings.OPENAI_MODEL

    def _get_openai(self):
        """获取 OpenAI 客户端（注入优先 → lazy 创建回退）

        注入优先：如果构造器传入了 openai_client 则直接使用。
        否则首次调用时从 settings 创建（兼容旧代码）。
        """
        if self._injected_client is not None:
            return self._injected_client
        if self._lazy_client is None:
            from openai import AsyncOpenAI
            self._lazy_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )
        return self._lazy_client

    @trace_llm_call(function_name="llm_chat")
    async def chat(self, system: str, messages: list,
                   response_format: Optional[dict] = None,
                   temperature: float = 0.1,
                   max_tokens: int = 4096) -> str:
        """普通同步调用 — 等待完整回复返回

        适用于：简历分析（需要完整 JSON）、面试排期、制度问答等
        """
        return await self._chat_openai(system, messages, response_format, temperature, max_tokens)

    async def _chat_openai(self, system: str, messages: list,
                           response_format: Optional[dict],
                           temperature: float, max_tokens: int) -> str:
        """实际调用 OpenAI 兼容 API"""
        client = self._get_openai()
        kwargs = {
            "model": self._model_name,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        resp = await client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本向量嵌入 — 用于 RAG 语义检索"""
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
        """流式 chat — 逐 token yield 文本块

        前端通过 SSE 接收，每个 token 到来时立刻渲染，形成"打字机"效果。
        适用于：Function Calling 回复、简历分析摘要、制度问答
        """
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

    async def stream_chat_json(
        self, system: str, messages: list,
        temperature: float = 0.1, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式 JSON 输出 — 缓冲完整 JSON 后一次性 yield

        JSON 不能逐 token 拼接（会破坏结构），所以全部 token 收齐后再一次性返回。
        """
        client = self._get_openai()
        kwargs: dict = {
            "model": self._model_name,
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


# 全局单例 — 无参数构造，从 settings 自动读取配置（兼容旧代码）
llm_client = LLMClient()
