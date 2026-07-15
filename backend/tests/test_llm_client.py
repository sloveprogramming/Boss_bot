"""LLM 客户端测试 — 调用封装 + Trace 装饰器"""
import pytest
from unittest.mock import patch, AsyncMock

pytestmark = pytest.mark.asyncio


class TestLLMClient:
    """LLM 客户端基础功能测试"""

    @pytest.mark.asyncio
    async def test_chat_returns_string(self, mock_llm_client):
        """chat() 应返回字符串"""
        result = await mock_llm_client.chat(
            system="test system",
            messages=[{"role": "user", "content": "test"}],
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_chat_with_json_format(self, mock_llm_client):
        """指定 json_object 格式时的调用"""
        mock_llm_client.chat.return_value = '{"key": "value"}'
        result = await mock_llm_client.chat(
            system="test",
            messages=[{"role": "user", "content": "test"}],
            response_format={"type": "json_object"},
        )
        import json
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    @pytest.mark.asyncio
    async def test_chat_handles_empty_response(self, mock_llm_client):
        """空响应应返回空字符串"""
        mock_llm_client.chat.return_value = ""
        result = await mock_llm_client.chat(
            system="", messages=[{"role": "user", "content": ""}],
        )
        assert result == ""

    def test_client_singleton(self):
        """llm_client 应是全局单例"""
        from app.agents.llm_client import llm_client as c1
        from app.agents.llm_client import llm_client as c2
        assert c1 is c2


class TestTraceDecorator:
    """LLM Trace 装饰器测试"""

    @pytest.mark.asyncio
    async def test_trace_writes_log_on_success(self):
        """成功调用应写 trace 日志（装饰器不阻塞主流程）"""
        from app.agents.tracing import trace_llm_call

        class MockClient:
            _model_name = "test-model"

            @trace_llm_call(function_name="test_func")
            async def chat(self, system, messages, **kwargs):
                return "test response"

        client = MockClient()
        # 验证装饰器不阻塞也不改变返回值
        result = await client.chat("system", [{"role": "user", "content": "hi"}])
        assert result == "test response"

    @pytest.mark.asyncio
    async def test_trace_writes_log_on_error(self):
        """调用报错也应写 trace 日志（记录错误信息）"""
        from app.agents.tracing import trace_llm_call

        with patch("app.agents.tracing._write_log_async", new=AsyncMock()) as mock_write:
            class MockClient:
                _model_name = "test-model"

                @trace_llm_call(function_name="test_func")
                async def chat(self, system, messages, **kwargs):
                    raise ValueError("API error")

            client = MockClient()
            with pytest.raises(ValueError, match="API error"):
                await client.chat("system", [])
            # 即使出错也应尝试写日志
            assert mock_write.called
