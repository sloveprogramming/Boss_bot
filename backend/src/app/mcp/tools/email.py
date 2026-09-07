"""MCP 邮件发送 Tool — 基于现有 NotificationService 封装

所有导入均为懒加载，避免触发 services/__init__.py 全量导入链。
"""
import time
import logging
from typing import Optional
import json

logger = logging.getLogger(__name__)


async def send_email(
    candidate_id: int,
    template: str = "interview_invite",
    subject: Optional[str] = None,
    body: Optional[str] = None,
    extra_vars: Optional[dict] = None,
    user=None,
) -> str:
    """发送邮件给指定候选人。

    支持预置模板和自定义内容两种模式。

    Args:
        candidate_id: 候选人 ID
        template: 预置模板：interview_invite/interview_confirmed/interview_reminder/
                  questionnaire_invite/questionnaire_reminder/rejection/offer
                  设为 "custom" 使用自定义 subject + body
        subject: 自定义邮件主题（仅在 template="custom" 时使用）
        body: 自定义邮件正文（仅在 template="custom" 时使用，支持 {name} {position} 变量）
        extra_vars: 模板额外变量，如 {"survey_link": "...", "deadline": "..."}
        user: 调用者（HR/admin/interviewer）；None=受信全量

    Returns:
        JSON 字符串：发送结果
    """
    _start = time.perf_counter()
    from app.database import async_session_factory
    db = await async_session_factory()
    try:
        # 越权访问校验（不泄露存在性）；None/admin 直接放行
        from app.dependencies.scope import candidate_accessible
        if not await candidate_accessible(db, user, candidate_id):
            logger.warning(
                "[MCP审计] send_email 拒绝越权访问: candidate_id=%s", candidate_id,
            )
            return json.dumps({
                "success": False,
                "error": f"候选人不存在或无权访问: {candidate_id}",
            }, ensure_ascii=False)
        if template == "custom":
            if not subject or not body:
                logger.warning("[MCP审计] send_email 参数缺失: candidate_id=%s template=custom", candidate_id)
                return json.dumps({
                    "success": False,
                    "error": "自定义邮件需要同时提供 subject 和 body 参数",
                }, ensure_ascii=False)

            # 使用 notification_service 的通用发送能力
            # 先获取候选人信息以渲染变量
            from sqlalchemy import select
            from app.models import Candidate
            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if not candidate:
                logger.warning("[MCP审计] send_email 候选人不存在: candidate_id=%s", candidate_id)
                return json.dumps({
                    "success": False,
                    "error": f"候选人不存在: {candidate_id}",
                }, ensure_ascii=False)

            # 渲染自定义模板变量
            var_context = {
                "candidate_name": candidate.name,
                "position": candidate.position,
                **(extra_vars or {}),
            }
            rendered_subject = subject.format(**var_context)
            rendered_body = body.format(**var_context)

            # 直接调用 SMTP 发送
            try:
                from app.services.notification import notification_service
                await notification_service._send_email(
                    to=candidate.email or "",
                    subject=rendered_subject,
                    body=rendered_body,
                )
                logger.info(
                    "[MCP审计] send_email 成功: candidate_id=%s recipient=%s subject=%s (%.0fms)",
                    candidate_id, candidate.email, rendered_subject,
                    (time.perf_counter() - _start) * 1000,
                )
                return json.dumps({
                    "success": True,
                    "candidate_id": candidate_id,
                    "candidate_name": candidate.name,
                    "recipient": candidate.email,
                    "subject": rendered_subject,
                    "message": "邮件已发送",
                }, ensure_ascii=False)
            except Exception as e:
                logger.error("[MCP审计] send_email 失败: candidate_id=%s error=%s", candidate_id, e)
                return json.dumps({
                    "success": False,
                    "error": f"邮件发送失败: {str(e)}",
                }, ensure_ascii=False)
        else:
            # 使用预置模板
            try:
                from app.services.notification import notification_service
                notification = await notification_service.send(
                    candidate_id=candidate_id,
                    template=template,
                    channel="email",
                    db=db,
                    extra=extra_vars,
                )
                await db.flush()

                logger.info(
                    "[MCP审计] send_email 成功: candidate_id=%s template=%s status=%s (%.0fms)",
                    candidate_id, template, notification.status,
                    (time.perf_counter() - _start) * 1000,
                )
                return json.dumps({
                    "success": notification.status == "sent",
                    "candidate_id": candidate_id,
                    "template": template,
                    "recipient": notification.recipient,
                    "subject": notification.subject,
                    "status": notification.status,
                    "message": "邮件已发送" if notification.status == "sent" else f"发送失败: {notification.error_message}",
                }, ensure_ascii=False)
            except ValueError as e:
                logger.warning("[MCP审计] send_email 参数错误: candidate_id=%s template=%s error=%s", candidate_id, template, e)
                return json.dumps({
                    "success": False,
                    "error": str(e),
                }, ensure_ascii=False)
    finally:
        await db.close()
