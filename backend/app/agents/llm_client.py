"""统一的 LLM 客户端 — OpenAI 兼容接口 + 全链路追踪 + 流式输出

所有 LLM 调用的唯一入口，提供三种调用模式：
  chat()          — 普通同步调用，等完整回复【简历分析、面试排期】
  stream_chat()   — 流式逐 token 产出【SSE 推给前端逐字渲染】
  stream_chat_json() — 流式累积后一次性返回完整 JSON【JSON 不能逐字拼】
"""
from typing import Optional, AsyncGenerator                        # AsyncGenerator: 流式 async for 的类型标注
from app.config import settings                                    # 全局配置（API Key、模型名等）
from app.agents.tracing import trace_llm_call                     # 调用追踪装饰器（记录耗时/token）


class LLMClient:
    """统一的 LLM 调用接口 — 全局单例"""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER                      # LLM 提供商（目前 openai）
        self._openai_client = None                                 # 延迟初始化的 OpenAI 异步客户端
        self._model_name = settings.OPENAI_MODEL                   # 模型名（DeepSeek V4 Flash）

    def _get_openai(self):
        """延迟初始化 — 首次调用时才创建客户端，避免启动时连接"""
        if self._openai_client is None:                            # 还没创建过
            from openai import AsyncOpenAI                         # 延迟导入
            self._openai_client = AsyncOpenAI(                     # 创建异步客户端
                api_key=settings.OPENAI_API_KEY,                   # API 密钥
                base_url=settings.OPENAI_BASE_URL,                 # 接口地址（支持 DeepSeek 等兼容接口）
            )
        return self._openai_client

    @trace_llm_call(function_name="llm_chat")                      # 装饰器：自动记录调用耗时、token
    async def chat(self, system: str, messages: list,
                   response_format: Optional[dict] = None,         # 强制 JSON 输出：{"type": "json_object"}
                   temperature: float = 0.1,                       # 采样温度：0.1=稳定，1.0=随机
                   max_tokens: int = 4096) -> str:                 # 最大输出长度
        """普通同步调用 — 等待完整回复返回

        适用于：简历分析（需要完整 JSON）、面试排期、制度问答等
        """
        return await self._chat_openai(system, messages, response_format, temperature, max_tokens)

    async def _chat_openai(self, system: str, messages: list,
                           response_format: Optional[dict],
                           temperature: float, max_tokens: int) -> str:
        """实际调用 OpenAI 兼容 API"""
        client = self._get_openai()                                # 获取客户端
        kwargs = {                                                 # 构建请求参数
            "model": settings.OPENAI_MODEL,                        # 模型名
            "messages": [{"role": "system", "content": system}] + messages,  # 系统提示词 + 对话
            "temperature": temperature,                            # 采样温度
            "max_tokens": max_tokens,                              # 最大 token
        }
        if response_format:                                        # 需要 JSON 输出
            kwargs["response_format"] = response_format

        resp = await client.chat.completions.create(**kwargs)      # 调 API
        return resp.choices[0].message.content or ""               # 返回文本内容

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """获取文本向量嵌入 — 用于 RAG 语义检索"""
        client = self._get_openai()
        resp = await client.embeddings.create(                     # 调 embedding API
            model=settings.EMBEDDING_MODEL,                        # 嵌入模型（text-embedding-3-small）
            input=texts,                                           # 待向量化的文本列表
        )
        return [item.embedding for item in resp.data]              # 返回向量列表

    async def stream_chat(
        self, system: str, messages: list,
        temperature: float = 0.1, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式 chat — 逐 token yield 文本块

        前端通过 SSE 接收，每个 token 到来时立刻渲染，形成"打字机"效果。
        适用于：Function Calling 回复、简历分析摘要、制度问答

        Yields: 每段文本增量
        """
        client = self._get_openai()
        response = await client.chat.completions.create(           # 开流式请求
            model=settings.OPENAI_MODEL,
            messages=[{"role": "system", "content": system}] + messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,                                           # 关键：开启流式
        )

        async for chunk in response:                               # 逐块接收
            content = chunk.choices[0].delta.content               # 提取文本增量
            if content:
                yield content                                      # yield 出去给 SSE

    async def stream_chat_json(
        self, system: str, messages: list,
        temperature: float = 0.1, max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式 JSON 输出 — 缓冲完整 JSON 后一次性 yield

        JSON 不能逐 token 拼接（会破坏结构 "{ \"name\": \"张" 非法）。
        所以全部 token 收齐后再一次性返回。
        """
        client = self._get_openai()
        kwargs: dict = {
            "model": settings.OPENAI_MODEL,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,                                        # 开流式
            "response_format": {"type": "json_object"},            # 强制 JSON 输出
        }
        response = await client.chat.completions.create(**kwargs)

        buffer = []                                                # 缓冲所有 token
        async for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                buffer.append(content)
        yield "".join(buffer)                                      # 一次性返回完整 JSON


# 全局单例 — 整个应用共享同一个 LLM 客户端（避免重复创连接）
llm_client = LLMClient()
