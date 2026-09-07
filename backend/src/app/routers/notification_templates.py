# ═══════════════════════════════════════════════════════════════
# 【小白导读】邮件模板管理 API：HR/Admin 提前把问卷、面试、Offer 等通知模板
#   写好后存进 notification_templates 表；自动发送时系统会优先用这套文案，
#   删掉某条记录就自动回退到代码里的内置默认文案。
#   本文件还提供：AI 生成草稿（写用途→出模板，不落库，人工微调后保存）。
# ═══════════════════════════════════════════════════════════════
"""可配置邮件模板管理 API

权限：仅 ADMIN / HR（新建/编辑/停用/删除/预览/AI 生成）。
设计：
  - code 唯一（场景编码）；7 个内置 code 与业务发送点一一对应。
  - 删除/停用某 code → 自动发送回退 services/notification.py 的内置默认。
  - AI 生成返回草稿不落库，由前端填入编辑器，用户微调后保存。
"""
import json
import logging
import re
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.company_profile import (
    COMPANY_NAME, format_company_profile_block, JD_COMPLIANCE_REDLINES,
)
from app.agents.llm_client import llm_client
from app.database import get_db
from app.dependencies import require_role
from app.models import UserRole, User
from app.models.notification_template import NotificationTemplate
from app.services import notification_template_svc as tpl_svc
from app.services.notification_template_svc import (
    TEMPLATE_META, TEMPLATE_VARIABLES, CATEGORY_LABELS,
    ensure_default_templates, extract_placeholders,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/templates",
    tags=["邮件模板"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)

CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
ALL_VARIABLES = sorted({v for vs in TEMPLATE_VARIABLES.values() for v in vs})


# ── 请求体 ──────────────────────────────────────────────────────
class TemplateCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, description="场景编码，如 questionnaire_invite")
    name: str = Field(..., min_length=1, max_length=100, description="模板显示名")
    category: str = Field("other", max_length=40, description="分类: questionnaire/interview/result/other")
    subject: str = Field(..., min_length=1, max_length=255, description="邮件主题（可含 {占位符}）")
    body: str = Field(..., min_length=1, description="邮件正文（可含 {占位符}）")
    is_active: bool = True


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=40)
    subject: Optional[str] = Field(None, max_length=255)
    body: Optional[str] = None
    is_active: Optional[bool] = None


class RenderPreviewRequest(BaseModel):
    template_id: Optional[int] = None
    code: Optional[str] = Field(None, max_length=64)
    subject: Optional[str] = Field(None, max_length=255, description="直接传入未保存草稿的主题（与 body 同时传时优先于 template_id/code）")
    body: Optional[str] = None
    candidate_name: Optional[str] = Field(None, max_length=50)
    position: Optional[str] = Field(None, max_length=100)
    extra: Optional[dict] = None


class TemplateGenerateRequest(BaseModel):
    focus: str = Field(..., min_length=2, max_length=500, description="用途说明，如：给通过初面的候选人发二面邀约")
    code: Optional[str] = Field(None, max_length=64, description="目标场景编码（可选）")
    candidate_name: Optional[str] = Field(None, max_length=50, description="样例称呼（可选）")


def _validate_category(category: str) -> str:
    """分类入参兼容英文 key 与中文标签（如 '面试' → 'interview'）"""
    label_to_key = {label: key for key, label in CATEGORY_LABELS.items()}
    category = (category or "other").strip() or "other"
    if category not in CATEGORY_LABELS:
        category = label_to_key.get(category, "")
    if category not in CATEGORY_LABELS:
        raise HTTPException(status_code=400, detail=f"非法的分类，可选: {', '.join(CATEGORY_LABELS)}")
    return category


async def _get_row_or_404(db: AsyncSession, template_id: int) -> NotificationTemplate:
    result = await db.execute(
        select(NotificationTemplate).where(NotificationTemplate.id == template_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"模板不存在: {template_id}")
    return row


def _serialize(row: NotificationTemplate) -> dict:
    return row.to_dict()


# ── 列表 / 新建 ────────────────────────────────────────────────
@router.get("")
async def list_templates(category: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """模板列表（可选按分类过滤），按 分类→编码 排序"""
    stmt = select(NotificationTemplate).order_by(
        NotificationTemplate.category, NotificationTemplate.code,
    )
    if category:
        stmt = stmt.where(NotificationTemplate.category == category)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


@router.post("", status_code=201)
async def create_template(
    req: TemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """新建模板（自定义 code；code 已存在返回 409）"""
    code = req.code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(
            status_code=400,
            detail="code 需以字母开头，仅含字母/数字/下划线（最长 64）",
        )
    category = _validate_category(req.category)

    exists = await db.execute(
        select(NotificationTemplate.id).where(NotificationTemplate.code == code).limit(1)
    )
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"模板编码已存在: {code}（如需修改请直接编辑该模板）")

    row = NotificationTemplate(
        code=code,
        name=req.name.strip(),
        category=category,
        subject=req.subject.strip(),
        body=req.body.strip(),
        is_system=False,
        is_active=req.is_active,
        created_by=user.id if user else None,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)  # 读取 server_default 时间列，避免序列化时惰性加载
    return _serialize(row)


# ── 详情操作 ───────────────────────────────────────────────────
@router.put("/{template_id}")
async def update_template(
    template_id: int,
    req: TemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新模板（code 不可改；传哪个字段就更新哪个）"""
    row = await _get_row_or_404(db, template_id)
    payload = req.model_dump(exclude_unset=True)

    if "category" in payload and payload["category"] is not None:
        payload["category"] = _validate_category(payload["category"])
    for field in ("name", "subject", "body"):
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field].strip()
            if field in ("name", "subject") and not payload[field]:
                raise HTTPException(status_code=400, detail=f"{field} 不能为空")

    for field, value in payload.items():
        setattr(row, field, value)
    await db.flush()
    await db.refresh(row)
    return _serialize(row)


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """删除模板；删除后该 code 的自动发送回退内置默认文案"""
    row = await _get_row_or_404(db, template_id)
    code = row.code
    await db.delete(row)
    await db.flush()
    return {"success": True, "id": template_id, "code": code}


@router.post("/{template_id}/reset")
async def reset_template(template_id: int, db: AsyncSession = Depends(get_db)):
    """系统内置模板：一键恢复默认文案（自定义模板无默认可恢复则 409）"""
    from app.services.notification import NotificationService

    row = await _get_row_or_404(db, template_id)
    builtin = NotificationService.TEMPLATES.get(row.code)
    if builtin is None:
        raise HTTPException(status_code=409, detail="该模板不是系统内置模板，无默认文案可恢复")
    meta = TEMPLATE_META.get(row.code, {"name": row.code, "category": "other"})
    row.name = meta["name"]
    row.category = meta["category"]
    row.subject = builtin.get("subject", "")
    row.body = builtin.get("body", "")
    row.is_active = True
    await db.flush()
    await db.refresh(row)
    return _serialize(row)


@router.post("/restore-defaults")
async def restore_defaults(db: AsyncSession = Depends(get_db)):
    """重新补齐缺失的内置模板（不覆盖用户已编辑过的记录）"""
    inserted, existed = await ensure_default_templates(db)
    return {"success": True, "inserted": inserted, "existed": existed}


# ── 预览 / AI 生成 ─────────────────────────────────────────────
@router.post("/render-preview")
async def render_preview(req: RenderPreviewRequest, db: AsyncSession = Depends(get_db)):
    """预览：取 DB 或内置模板，用样例值渲染 subject/body，返回未识别占位符"""
    # 直接给 subject+body 用于预览「尚未保存的草稿」；否则按 template_id/code 取库内模板
    if req.subject is not None and req.body is not None:
        subject, body = req.subject, req.body
    elif req.template_id is not None:
        row = await _get_row_or_404(db, req.template_id)
        subject, body = row.subject, row.body
    elif req.code:
        resolved = await tpl_svc.resolve_template(db, req.code.strip())
        if not resolved:
            raise HTTPException(status_code=404, detail=f"模板不可用: {req.code}")
        subject, body = resolved["subject"], resolved["body"]
    else:
        raise HTTPException(status_code=400, detail="需要提供 subject+body、template_id 或 code")

    return tpl_svc.render_preview(
        subject, body,
        candidate_name=req.candidate_name,
        position=req.position,
        extra=req.extra,
    )


def _extract_json(text: str) -> dict:
    """稳健解析模型 JSON（容忍代码围栏 / 前后缀文字）"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[A-Za-z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("模型未返回有效 JSON")
        return json.loads(m.group(0))


@router.post("/generate")
async def generate_template(req: TemplateGenerateRequest):
    """AI 生成模板草稿（不落库，仅返回草稿供人工微调后保存）"""
    focus = req.focus.strip()
    code = (req.code or "").strip() or None

    # 占位符白名单：指定内置 code 则限定其白名单；否则放开全部占位符
    whitelist = TEMPLATE_VARIABLES.get(code) if code else ALL_VARIABLES
    scope_desc = ""
    if code:
        meta = TEMPLATE_META.get(code)
        scope_desc = f"\n目标场景编码：{code}" + (f"（{meta['name']}）" if meta else "")
    profile_block = format_company_profile_block()
    company_line = f"公司名称：{COMPANY_NAME}\n" if COMPANY_NAME else ""
    if profile_block:
        company_line += profile_block

    system_prompt = f"""你是一位资深的招聘邮件文案专家，为 HR 撰写发给候选人的正式邮件模板。

硬性要求：
1. 占位符只允许使用这些（{名称} 形式），绝对不得发明新占位符：
   {whitelist}
   正文需要插入候选人名、链接、时间等动态内容时，必须用上面占位符表示。
2. 输出两项：subject（邮件主题，一句话）+ body（邮件正文，多行，用 \\n 换行，不用 Markdown 符号）。
3. 语气专业、得体、亲切，中文；内容完整可直接使用。
4. 只输出一个 JSON 对象，结构为：
   {{"name": "模板显示名", "category": "questionnaire|interview|result|other", "subject": "...", "body": "...", "used_variables": ["..."]}}
   不要输出 JSON 以外的任何文字，不要用代码围栏。

{company_line}
{JD_COMPLIANCE_REDLINES}"""

    user_prompt = f"用途说明：{focus}{scope_desc}"
    if req.candidate_name:
        user_prompt += f"\n收件人样例称呼：{req.candidate_name}"

    try:
        raw = await llm_client.chat(
            system_prompt,
            [{"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"},
            temperature=0.6,
            max_tokens=1600,
        )
        data = _extract_json(raw)
    except Exception as e:
        logger.exception("AI 模板生成失败: focus=%s", focus)
        raise HTTPException(status_code=502, detail=f"AI 生成失败: {e}")

    name = str(data.get("name") or (TEMPLATE_META.get(code, {}).get("name") if code else "") or focus[:30]).strip()
    category = _validate_category(str(data.get("category") or "other"))
    subject = str(data.get("subject", "")).strip()
    body = str(data.get("body", "")).strip()
    if not subject or not body:
        raise HTTPException(status_code=502, detail="AI 返回的模板不完整（缺主题或正文），请重试")

    used_vars = list(dict.fromkeys(extract_placeholders(subject) + extract_placeholders(body)))
    unexpected = sorted(set(used_vars) - set(whitelist))
    return {
        "draft": {
            "name": name,
            "code": code,
            "category": category,
            "subject": subject,
            "body": body,
            "used_variables": used_vars,
        },
        "whitelist": whitelist,
        "unexpected_variables": unexpected,
    }
