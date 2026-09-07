# 【小白导读】问卷业务逻辑：按岗位生成题目、候选人提交后 AI 批卷算分。
#   被工作流的 questionnaire 节点调用。
"""问卷服务 — 简化版：仅记录发送固定链接

不再生成题目、评分、催填，只记录向候选人发送了问卷链接。
"""
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Questionnaire, Candidate
from app.services.notification import notification_service


# 固定的问卷链接
QUESTIONNAIRE_LINK = "https://www.qingsuyun.com/h5/251261/18081878897/"


class QuestionnaireService:
    """问卷服务 — 仅记录发送固定链接"""

    async def send_questionnaire_link(self, candidate_id: int, channel: str,
                                      db: AsyncSession) -> Questionnaire:
        """向候选人发送固定问卷链接，创建发送记录"""
        # 获取候选人
        result = await db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )
        candidate = result.scalar_one_or_none()
        if not candidate:
            raise ValueError(f"候选人不存在: {candidate_id}")

        # 创建问卷发送记录
        q = Questionnaire(
            candidate_id=candidate_id,
            title="技术能力评估",
            questions=[],  # 无题目，只有链接
            status="sent",
            sent_at=datetime.utcnow(),
            deadline=datetime.utcnow() + timedelta(days=7),
        )
        db.add(q)
        await db.flush()

        # 更新候选人状态
        candidate.status = "q_sent"

        # 发送通知（含固定链接）
        notif = await notification_service.send(
            candidate_id=candidate_id,
            template="questionnaire_invite",
            channel=channel,
            db=db,
            recipient=candidate.email,
            extra={
                "candidate_name": candidate.name,
                "survey_link": QUESTIONNAIRE_LINK,
                "deadline": q.deadline.strftime("%Y-%m-%d"),
            }
        )
        # 邮件实际发送失败（SMTP 连不上/被拒等）时直接抛错，避免前端误报“已发送”
        if getattr(notif, "status", None) == "failed":
            raise ValueError(
                f"问卷邮件发送失败（{notif.error_message or '未知 SMTP 错误'}），请检查服务器 SMTP 配置"
            )

        await db.flush()
        return q


# 全局单例
questionnaire_service = QuestionnaireService()
