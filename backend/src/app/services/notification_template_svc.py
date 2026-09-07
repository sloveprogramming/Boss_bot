# ═══════════════════════════════════════════════════════════════
# 【小白导读】可配置邮件模板的"大脑"：负责把内置模板播种进数据库、
#   发送时按 code 查 DB（找不到再回退内置）、以及安全渲染模板文本。
#   安全渲染的意义：HR 手写模板时若写错占位符（如 {公司名}），不会让发送
#   直接 500，而是把没匹配上的 {占位符} 原样保留在邮件里，方便发现修正。
# ═══════════════════════════════════════════════════════════════
"""可配置通知模板服务 — 播种 / 解析 / 安全渲染

设计原则：
  - 内置模板文案唯一事实来源 = services/notification.py 的 NotificationService.TEMPLATES，
    本文件不复制文案，只补充每个 code 的显示名与分类（META）。
  - 自动发送解析顺序：DB 生效记录 → 内置默认 → None（发送方抛"不支持的模板"）。
"""
import re
import string
from typing import Optional

from sqlalchemy import select

from app.models.notification_template import NotificationTemplate


# ── 内置模板的显示名 / 分类（文案本体仍复用 notification.TEMPLATES，不重复维护） ──
TEMPLATE_META = {
    "questionnaire_invite":    {"name": "问卷邀请",       "category": "questionnaire"},
    "questionnaire_reminder":  {"name": "问卷催填提醒",   "category": "questionnaire"},
    "interview_invite":        {"name": "面试邀约",       "category": "interview"},
    "interview_confirmed":     {"name": "面试确认",       "category": "interview"},
    "interview_reminder":      {"name": "面试提醒",       "category": "interview"},
    "offer":                   {"name": "录用通知 Offer", "category": "result"},
    "rejection":               {"name": "婉拒通知",       "category": "result"},
}

# 各 code 的常用占位符白名单（用于 AI 生成约束与前端提示）
# send() 的 context 基础键是 candidate_name / position，extra 里再带渠道相关变量。
TEMPLATE_VARIABLES = {
    "questionnaire_invite":   ["candidate_name", "survey_link", "deadline"],
    "questionnaire_reminder": ["candidate_name", "reminder_count", "survey_link", "deadline"],
    "interview_invite":       ["candidate_name", "proposed_slots", "selection_link"],
    "interview_confirmed":    ["candidate_name", "position", "interview_time", "location_or_link"],
    "interview_reminder":     ["candidate_name", "position", "interview_time", "location_or_link"],
    "offer":                  ["candidate_name", "position"],
    "rejection":              ["candidate_name"],
}

CATEGORY_LABELS = {
    "questionnaire": "问卷类",
    "interview":     "面试类",
    "result":        "结果通知",
    "other":         "其他",
}


class _SafeFormatter(string.Formatter):
    """缺失占位符时原样保留 {key}，而不是抛 KeyError"""

    def get_field(self, field_name, args, kwargs):
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, IndexError):
            return "{" + field_name + "}", field_name


_SAFE_FORMATTER = _SafeFormatter()


def extract_placeholders(text: str) -> list:
    """提取模板文本里的 {占位符} 名称（去重保序）"""
    if not text:
        return []
    seen, out = set(), []
    for m in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", text):
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def render_text(text: str, context: dict) -> str:
    """安全渲染模板文本：提供的占位符替换，未提供的 {x} 原样保留。

    模板本身花括号不配对等非法格式时，直接返回原文（宁可字面展示，不崩发送）。
    """
    if not text:
        return text or ""
    try:
        return _SAFE_FORMATTER.format(text, **context)
    except (KeyError, IndexError, ValueError):
        return text


def render_preview(subject: str, body: str,
                   candidate_name: Optional[str] = None,
                   position: Optional[str] = None,
                   extra: Optional[dict] = None) -> dict:
    """用样例值渲染 subject/body，返回渲染结果与未覆盖占位符（预览用）"""
    context = {
        "candidate_name": candidate_name or "候选人",
        "position": position or "应聘岗位",
        # 渠道相关样例值：没被模板引用就无副作用
        "survey_link": "https://survey.example.com/fill/xxxx",
        "deadline": "2026-09-30",
        "reminder_count": "2",
        "proposed_slots": "周一 10:00、周二 14:00、周三 16:00",
        "selection_link": "https://interview.example.com/pick/xxxx",
        "interview_time": "2026-09-10 10:00",
        "location_or_link": "腾讯会议（链接以确认邮件为准）",
    }
    if extra:
        context.update(extra)
    rendered_subject = render_text(subject or "", context)
    rendered_body = render_text(body or "", context)
    remaining = sorted(set(extract_placeholders(rendered_subject))
                       | set(extract_placeholders(rendered_body)))
    return {
        "subject": rendered_subject,
        "body": rendered_body,
        "remaining_placeholders": remaining,
    }


async def ensure_default_templates(db) -> tuple:
    """把 7 套内置模板播种进数据库（仅缺失时插入，绝不覆盖用户已编辑的记录）。

    Returns:
        (inserted_count, existed_count)
    """
    from app.services.notification import NotificationService

    builtin = NotificationService.TEMPLATES
    result = await db.execute(select(NotificationTemplate.code))
    existing = {row[0] for row in result.all()}

    inserted = 0
    for code, content in builtin.items():
        if code in existing:
            continue
        meta = TEMPLATE_META.get(code, {"name": code, "category": "other"})
        db.add(NotificationTemplate(
            code=code,
            name=meta["name"],
            category=meta["category"],
            subject=content.get("subject", ""),
            body=content.get("body", ""),
            is_system=True,
            is_active=True,
        ))
        inserted += 1
    if inserted:
        await db.flush()
    return inserted, len(existing)


async def resolve_template(db, code: str) -> Optional[dict]:
    """按 code 解析模板内容：DB 生效记录 → 内置默认 → None。

    Returns:
        {"subject": str, "body": str}；没有可用模板返回 None。
    """
    from app.services.notification import NotificationService

    result = await db.execute(
        select(NotificationTemplate)
        .where(NotificationTemplate.code == code,
               NotificationTemplate.is_active.is_(True))
        .order_by(NotificationTemplate.id.desc())
    )
    row = result.scalars().first()
    if row is not None:
        return {"subject": row.subject, "body": row.body}
    builtin = NotificationService.TEMPLATES.get(code)
    return dict(builtin) if builtin else None
