"""通知服务 — 支持邮件/短信/企业微信/钉钉多渠道统一发送

依赖注入：
  __init__ 可接受 httpx_client 参数。
  未传入时回退到临时创建（兼容旧代码）。
"""
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models import Notification
import httpx
import time
import hmac
import hashlib
import base64
from urllib.parse import quote_plus


class NotificationService:
    """统一通知发送服务 — 支持依赖注入"""

    TEMPLATES = {
        "questionnaire_invite": {
            "subject": "【AI招聘助手】请完成技术评估问卷",
            "body": """{candidate_name}，您好！

感谢您应聘我司岗位。我们已收到您的简历，现邀请您完成一份技术评估问卷。

问卷链接：{survey_link}
截止时间：{deadline}

请尽快完成，期待与您进一步沟通！

—— AI招聘助手"""
        },
        "questionnaire_reminder": {
            "subject": "【AI招聘助手】问卷填写提醒",
            "body": """{candidate_name}，您好！

您此前收到的技术评估问卷尚未完成，这是第 {reminder_count} 次提醒。

问卷链接：{survey_link}
截止时间：{deadline}

如在截止日期前未完成，将视为自动放弃本次机会。

—— AI招聘助手"""
        },
        "interview_invite": {
            "subject": "【AI招聘助手】面试邀请",
            "body": """{candidate_name}，您好！

恭喜您通过初步筛选！请从以下时间段中选择您方便的面试时间：

{proposed_slots}

请点击以下链接选择时间：{selection_link}

—— AI招聘助手"""
        },
        "interview_confirmed": {
            "subject": "【AI招聘助手】面试确认通知",
            "body": """{candidate_name}，您好！

您的面试已确认，详情如下：

岗位：{position}
时间：{interview_time}
地点/方式：{location_or_link}

请您准时参加。如有任何疑问，欢迎随时咨询我们的企业政策助手。

—— AI招聘助手"""
        },
        "interview_reminder": {
            "subject": "【AI招聘助手】面试提醒",
            "body": """{candidate_name}，您好！

提醒您，面试将在24小时后进行：

岗位：{position}
时间：{interview_time}
地点/方式：{location_or_link}

祝您面试顺利！

—— AI招聘助手"""
        },
        "rejection": {
            "subject": "【AI招聘助手】应聘结果通知",
            "body": """{candidate_name}，您好！

感谢您对我司岗位的关注。经过综合评估，我们认为您与该岗位的匹配存在一定差距，因此暂不推进后续流程。

我们会将您的资料存入人才库，未来有合适的岗位将优先联系您。

祝您求职顺利！

—— AI招聘助手"""
        },
        "offer": {
            "subject": "【AI招聘助手】录用通知",
            "body": """{candidate_name}，您好！

恭喜您！经过全面评估，我们决定录用您担任 {position} 岗位。

我们将尽快与您沟通具体的入职事宜，请保持电话畅通。

欢迎加入我们！

—— AI招聘助手"""
        },
    }

    def __init__(self, httpx_client=None):
        """构造通知服务

        Args:
            httpx_client: httpx.AsyncClient 实例（注入后复用连接池）
        """
        self._httpx_client = httpx_client

    def _get_client(self, timeout: int = 10):
        if self._httpx_client is not None:
            return self._httpx_client
        return httpx.AsyncClient(timeout=timeout)

    async def send(self, candidate_id: int, template: str, channel: str,
                   db: AsyncSession, extra: Optional[dict] = None,
                   recipient: Optional[str] = None):
        """发送通知（主入口）"""
        from app.models import Candidate
        from sqlalchemy import select

        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        if not candidate:
            raise ValueError(f"候选人不存在: {candidate_id}")

        template_body = self.TEMPLATES.get(template)
        if not template_body:
            raise ValueError(f"不支持的模板: {template}")

        if not recipient:
            if channel == "email":
                recipient = candidate.email
            elif channel == "sms":
                recipient = candidate.phone
            else:
                recipient = candidate.email
        if not recipient:
            raise ValueError(f"无法确定收件人地址，候选人{candidate_id}缺少联系方式")

        context = {"candidate_name": candidate.name, "position": candidate.position, **(extra or {})}
        subject = template_body["subject"]
        body = template_body["body"].format(**context)

        notification = Notification(
            candidate_id=candidate_id,
            type=channel,
            template=template,
            recipient=recipient,
            subject=subject,
            content=body,
            status="pending",
        )

        try:
            if channel == "email":
                await self._send_email(recipient, subject, body)
            elif channel == "sms":
                await self._send_sms(recipient, body)
            elif channel == "wework":
                await self._send_wework(subject, body)
            elif channel == "dingtalk":
                await self._send_dingtalk(subject, body)
            else:
                print(f"[NOTIFICATION] To: {recipient}, Subject: {subject}")

            notification.status = "sent"
            notification.sent_at = datetime.utcnow()
        except Exception as e:
            notification.status = "failed"
            notification.error_message = str(e)

        db.add(notification)
        await db.flush()
        return notification

    async def _send_email(self, to: str, subject: str, body: str):
        if not settings.SMTP_HOST:
            print(f"[EMAIL MOCK] To: {to}, Subject: {subject}")
            return
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.NOTIFICATION_EMAIL_FROM
        msg["To"] = to
        html_body = body.replace("\n", "<br>")
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USER:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.NOTIFICATION_EMAIL_FROM, [to], msg.as_string())

    async def _send_sms(self, to: str, body: str):
        if not settings.TWILIO_ACCOUNT_SID:
            print(f"[SMS MOCK] To: {to}, Body: {body[:100]}...")
            return
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        await client.messages.create(
            body=body, from_=settings.TWILIO_PHONE_NUMBER, to=to)

    async def _send_wework(self, subject: str, body: str):
        webhook_url = settings.WEWORK_WEBHOOK_URL
        if not webhook_url:
            print(f"[WEWORK MOCK] Subject: {subject}")
            return
        markdown_content = f"## {subject}\n\n{body}\n\n> 发送时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        payload = {"msgtype": "markdown", "markdown": {"content": markdown_content}}
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") != 0:
                raise RuntimeError(f"企业微信发送失败: {result.get('errmsg', 'unknown')}")

    async def _send_dingtalk(self, subject: str, body: str):
        webhook_url = settings.DINGTALK_WEBHOOK_URL
        if not webhook_url:
            print(f"[DINGTALK MOCK] Subject: {subject}")
            return
        full_text = f"## {subject}\n\n{body}\n\n> 发送时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
        payload = {"msgtype": "markdown", "markdown": {"title": subject, "text": full_text}}
        final_url = webhook_url
        if settings.DINGTALK_APP_SECRET:
            timestamp = str(round(time.time() * 1000))
            secret = settings.DINGTALK_APP_SECRET
            string_to_sign = f"{timestamp}\n{secret}"
            hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                                 digestmod=hashlib.sha256).digest()
            sign = quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
            final_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(final_url, json=payload, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            if result.get("errcode") != 0:
                raise RuntimeError(f"钉钉发送失败: {result.get('errmsg', 'unknown')}")


# 全局单例 — 无参数构造，默认临时创建 httpx 客户端（兼容旧代码）
notification_service = NotificationService()
