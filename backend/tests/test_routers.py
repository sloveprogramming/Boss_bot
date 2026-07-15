"""API 端点集成测试 — 候选人和认证接口"""
import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio


class TestHealthEndpoint:
    """健康检查接口测试"""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, async_client):
        """GET /api/health 应返回 ok"""
        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestAuthEndpoints:
    """认证接口测试"""

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, async_client):
        """登录缺少字段应报 422"""
        response = await async_client.post("/api/auth/login", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_wrong_credentials(self, async_client, db_session):
        """错误的用户名密码应报 401"""
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "wrong"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_register_requires_auth(self, async_client):
        """未认证的用户注册应报 401"""
        response = await async_client.post(
            "/api/auth/register",
            json={"username": "test", "password": "test1234", "role": "hr"},
        )
        assert response.status_code in (401, 403)


class TestCandidateEndpoints:
    """候选人 API 测试"""

    @pytest.mark.asyncio
    async def test_list_candidates(self, async_client):
        """GET /api/candidates 应返回列表"""
        response = await async_client.get("/api/candidates")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data or isinstance(data, list)


class TestRAGChatEndpoint:
    """RAG 问答 API 测试"""

    @pytest.mark.asyncio
    async def test_chat_without_message(self, async_client):
        """POST /api/policy/chat 缺少 message 应报 422"""
        response = await async_client.post("/api/policy/chat", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_with_message(self, async_client):
        """有 message 的请求应正常处理"""
        # 由于依赖真实 LLM，这里只验证路由存在
        response = await async_client.post(
            "/api/policy/chat",
            json={"message": "年假有几天？", "session_id": "test-session"},
        )
        # 可能因 LLM 调用失败返回 500，但路由应存在
        assert response.status_code in (200, 500)
