"""日历集成 — 钉钉日程自动创建 / 会议邀请

依赖注入：
  __init__ 可接受 httpx_client、app_key、app_secret 参数。
  未传入时回退到延迟创建和 settings 读取（兼容旧代码）。
"""
import json
import time
import hmac
import hashlib
import base64
import logging
from urllib.parse import quote_plus
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class CalendarService:
    """日历服务 — 支持钉钉日程自动创建"""

    # ---- 构造器依赖注入 ----
    def __init__(self,
                 httpx_client=None,
                 app_key: Optional[str] = None,
                 app_secret: Optional[str] = None,
                 token_url: Optional[str] = None,
                 calendar_url: Optional[str] = None):
        """构造日历服务

        Args:
            httpx_client: httpx.AsyncClient 实例（可选，注入后复用连接池）
            app_key:     钉钉应用 Key（可选，默认从 settings 读取）
            app_secret:  钉钉应用 Secret（可选，默认从 settings 读取）
            token_url:   获取 token 的 API URL（可选）
            calendar_url: 创建日程的 API URL（可选）
        """
        self._httpx_client = httpx_client
        self._app_key = app_key
        self._app_secret = app_secret
        self.token_url = token_url or "https://oapi.dingtalk.com/gettoken"
        self.calendar_url = calendar_url or "https://oapi.dingtalk.com/topapi/calendar/v2/event/create"
        self._access_token = None
        self._token_expires_at = 0

    # ---- 凭证属性（兼容旧的 configure() 调用） ----
    @property
    def app_key(self):
        if self._app_key is not None:
            return self._app_key
        from app.config import settings
        return settings.DINGTALK_APP_KEY

    @app_key.setter
    def app_key(self, val):
        self._app_key = val

    @property
    def app_secret(self):
        if self._app_secret is not None:
            return self._app_secret
        from app.config import settings
        return settings.DINGTALK_APP_SECRET

    @app_secret.setter
    def app_secret(self, val):
        self._app_secret = val

    def configure(self, app_key: Optional[str], app_secret: Optional[str]):
        """配置钉钉应用凭证（兼容旧接口）"""
        self._app_key = app_key
        self._app_secret = app_secret

    def _get_client(self, timeout: int = 10):
        """获取 HTTP 客户端 — 注入优先，否则临时创建"""
        if self._httpx_client is not None:
            return self._httpx_client
        import httpx
        return httpx.AsyncClient(timeout=timeout)

    # ---- 获取 Access Token ----
    async def _get_access_token(self) -> str:
        """获取钉钉 access_token（带缓存，过期自动刷新）"""
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        if not self.app_key or not self.app_secret:
            raise ValueError("钉钉应用未配置，请设置 DINGTALK_APP_KEY 和 DINGTALK_APP_SECRET")

        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.token_url,
                params={"appkey": self.app_key, "appsecret": self.app_secret},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"获取钉钉token失败: {data.get('errmsg')}")

            self._access_token = data.get("access_token")
            self._token_expires_at = now + data.get("expires_in", 7200)
            return self._access_token

    # ---- 创建日程 ----
    async def create_event(
        self,
        summary: str,
        description: str,
        start_time: datetime,
        end_time: datetime,
        attendees: Optional[list[str]] = None,
        location: Optional[str] = None,
        remind_minutes: int = 30,
    ) -> dict:
        """创建钉钉日程事件"""
        if not self.app_key or not self.app_secret:
            logger.info(f"[日历·钉钉MOCK] 创建日程: {summary}")
            return {
                "status": "mock",
                "event_id": f"mock_{int(time.time())}",
                "summary": summary,
            }

        try:
            token = await self._get_access_token()
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)

            payload = {
                "summary": summary,
                "description": description,
                "start": {"timestamp": start_ms},
                "end": {"timestamp": end_ms},
                "remind_type": "app",
                "remind_minutes_before_start": remind_minutes,
                "calendar_type": "personal",
            }
            if location:
                payload["location"] = location

            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.calendar_url}?access_token={token}",
                    json=payload,
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    raise RuntimeError(f"创建钉钉日程失败: {data.get('errmsg')}")
                logger.info(f"[钉钉日程] 已创建: {summary}, event_id={data.get('event_id')}")
                return data

        except Exception as e:
            logger.error(f"[钉钉日程] 创建失败: {e}")
            raise

    # ---- 面试日程快捷方法 ----
    async def create_interview_event(
        self,
        candidate_name: str,
        position: str,
        interview_time: datetime,
        duration_minutes: int,
        interviewers: list[str],
        location: Optional[str] = None,
        meeting_link: Optional[str] = None,
    ) -> dict:
        """为面试创建钉钉日程（封装好格式描述）"""
        end_time = interview_time.replace(
            minute=interview_time.minute + duration_minutes
        )

        summary = f"面试 - {candidate_name} ({position})"
        description_parts = [
            f"### 面试信息",
            f"- **候选人**: {candidate_name}",
            f"- **岗位**: {position}",
            f"- **面试官**: {', '.join(interviewers)}",
            f"- **时间**: {interview_time.strftime('%Y-%m-%d %H:%M')} ({duration_minutes}分钟)",
        ]
        if location:
            description_parts.append(f"- **地点**: {location}")
        if meeting_link:
            description_parts.append(f"- **会议链接**: {meeting_link}")
        description_parts.append("")
        description_parts.append("*由AI招聘助手自动创建*")

        return await self.create_event(
            summary=summary,
            description="\n".join(description_parts),
            start_time=interview_time,
            end_time=end_time,
            attendees=interviewers,
            location=location or meeting_link,
            remind_minutes=30,
        )


# 全局单例 — 无参数构造，默认从 settings 读取（兼容旧代码）
calendar_service = CalendarService()
