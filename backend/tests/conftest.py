"""测试共享 fixtures — 内存数据库 + Mock LLM + TestClient"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from typing import AsyncGenerator, Generator
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------
# 内存数据库 fixtures
# ---------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """为每条测试用例创建独立的内存 SQLite 数据库会话

    每次 fixture 创建全新的 engine 和表，保证测试隔离。
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.database import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------
# Mock LLM 客户端
# ---------------------------------------------------------------


@pytest.fixture
def mock_llm_client():
    """Mock LLM 客户端，避免真实 API 调用

    默认返回固定 JSON 响应。
    测试用例可以通过 mock_llm_client.chat.side_effect 自定义返回值。
    """
    with patch("app.agents.llm_client.llm_client") as mock:
        mock.chat = AsyncMock(return_value='{"result": "ok", "message": "mock response"}')
        mock.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
        yield mock


@pytest.fixture
def mock_llm_json_response():
    """返回一个工厂函数，方便构造不同的 mock 响应"""
    def _make_response(json_str: str):
        return AsyncMock(return_value=json_str)
    return _make_response


# ---------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------


@pytest_asyncio.fixture
async def test_app() -> FastAPI:
    """获取已注册所有路由的 FastAPI 应用实例"""
    from app.main import app
    return app


@pytest_asyncio.fixture
async def async_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """异步 TestClient（用于测试 API 端点）"""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------
# 样本测试数据
# ---------------------------------------------------------------


@pytest.fixture
def sample_resume_text() -> str:
    """样本简历文本"""
    return """
姓名：张三
电话：13800138000
邮箱：zhangsan@example.com
教育经历：北京大学 计算机科学与技术 本科 2018-2022
工作经历：ABC科技有限公司 Python开发工程师 2022-至今
技能：Python, FastAPI, React, Docker, MySQL, Redis
项目经验：企业级AI招聘系统开发
证书：PMP认证
"""


@pytest.fixture
def sample_policy_text() -> str:
    """样本制度文档"""
    return """
第一章 考勤制度

第一条 工作时间为周一至周五，上午9:00至12:00，下午13:00至18:00。

第二条 员工应按时上下班。迟到或早退30分钟以内的，按次扣罚50元；
超过30分钟的，按旷工半天处理。

第三条 请假须提前在OA系统提交申请。1-3天由部门主管审批，
3天以上需总监审批。

第二章 休假制度

第四条 正式员工每年享有5天带薪年假。工龄每增加一年，
年假增加1天，上限15天。

第五条 病假需提供医院证明，病假期间工资按基本工资的60%发放。

第三章 薪酬福利

第六条 工作日加班按工资的150%支付，休息日加班按200%支付，
法定节假日按300%支付。

第七条 员工每月享有餐补500元，交通补贴300元。
"""
