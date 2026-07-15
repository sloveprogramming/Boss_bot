"""日历集成 — 钉钉日程自动创建 / 会议邀请"""

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

    def __init__(self):
        self.dingtalk_token_url = "https://oapi.dingtalk.com/gettoken"          # 获取token的API
        self.dingtalk_calendar_url = "https://oapi.dingtalk.com/topapi/calendar/v2/event/create"  # 创建日程的API
        self.app_key = None       # 钉钉应用Key
        self.app_secret = None    # 钉钉应用Secret
        self._access_token = None        # 缓存的access_token
        self._token_expires_at = 0       # token过期时间戳

    def configure(self, app_key: Optional[str], app_secret: Optional[str]):
        """配置钉钉应用凭证"""
        self.app_key = app_key
        self.app_secret = app_secret

    async def _get_access_token(self) -> str:
        """获取钉钉access_token（带缓存，过期自动刷新）"""
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        if not self.app_key or not self.app_secret:
            raise ValueError("钉钉应用未配置，请设置DINGTALK_APP_KEY和DINGTALK_APP_SECRET")

        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.dingtalk_token_url,
                params={"appkey": self.app_key, "appsecret": self.app_secret},
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"获取钉钉token失败: {data.get('errmsg')}")

            self._access_token = data.get("access_token")
            self._token_expires_at = now + data.get("expires_in", 7200)
            return self._access_token

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
        """创建钉钉日程事件

        Args:
            summary: 日程标题
            description: 日程描述
            start_time: 开始时间
            end_time: 结束时间
            attendees: 参与人列表
            location: 地点
            remind_minutes: 提前提醒分钟数

        Returns:
            API响应（未配置时返回mock数据）
        """
        # 未配置时输出mock日志
        if not self.app_key or not self.app_secret:
            logger.info(f"[日历·钉钉MOCK] 创建日程: {summary}")
            logger.info(f"  时间: {start_time} - {end_time}")
            logger.info(f"  参与人: {attendees or []}")
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
                    f"{self.dingtalk_calendar_url}?access_token={token}",
                    json=payload,
                )
                data = resp.json()
                if data.get("errcode") != 0:
                    raise RuntimeError(f"创建钉钉日程失败: {data.get('errmsg')}")

                logger.info(
                    f"[钉钉日程] 已创建: {summary}, event_id={data.get('event_id')}"
                )
                return data

        except Exception as e:
            logger.error(f"[钉钉日程] 创建失败: {e}")
            raise

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
        """为面试创建钉钉日程（封装好格式描述）

        Args:
            candidate_name: 候选人姓名
            position: 应聘岗位
            interview_time: 面试时间
            duration_minutes: 面试时长
            interviewers: 面试官列表
            location: 面试地点
            meeting_link: 会议链接

        Returns:
            create_event的响应
        """
        end_time = interview_time.replace(
            minute=interview_time.minute + duration_minutes
        )

        # 构建日程描述（Markdown格式）
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


# 全局单例
calendar_service = CalendarService()
"""全局日历服务实例"""
