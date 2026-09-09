# ═══════════════════════════════════════════════════════════════
# 【小白导读】岗位 JD 库管理 API：HR/Admin 把每个在招岗位的标准 JD
#   （岗位职责 + 任职要求）存进 position_jds 表；简历分析前系统按候选人
#   应聘岗位自动匹配一份 JD 喂给大模型，HR 不再每次手填招聘标准。
#   页面操作与「邮件模板」一致：列表分组 / 新建 / 编辑 / 停用 / 删除 /
#   恢复内置默认；另提供「匹配测试」，输入一个职位名看会命中哪份 JD。
# ═══════════════════════════════════════════════════════════════
"""可配置岗位JD库管理 API

权限：仅 ADMIN / HR（新建/编辑/停用/删除/恢复默认/匹配测试）。
设计：
  - position 唯一（岗位名）；内置 11 条与业务在招岗位一一对应。
  - 删除/停用某岗位 → 自动套用该岗位时不再命中（退回岗位名兜底）。
  - 分析入口统一走 position_jd_svc.resolve_jd_with_manual：手填 JD > 库内 JD > 岗位名。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role
from app.models import UserRole, User
from app.models.position_jd import PositionJd
from app.services import position_jd_svc as jd_svc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/position-jds",
    tags=["岗位JD库"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


# ── 请求体 ──────────────────────────────────────────────────────
class PositionJdCreateRequest(BaseModel):
    position: str = Field(..., min_length=1, max_length=100, description="岗位名，如 电商运营经理")
    aliases: str = Field("", max_length=255, description="匹配别名，顿号分隔（可空）")
    category: str = Field("other", max_length=40, description="分类，如 运营/销售/市场")
    responsibilities: str = Field("", description="岗位职责正文")
    requirements: str = Field("", description="任职要求正文")
    salary: str = Field("面议", max_length=50, description="薪资说明（仅展示）")
    is_active: bool = True


class PositionJdUpdateRequest(BaseModel):
    position: Optional[str] = Field(None, min_length=1, max_length=100)
    aliases: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = Field(None, max_length=40)
    responsibilities: Optional[str] = None
    requirements: Optional[str] = None
    salary: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


def _clean_str(value, field: str, required: bool = False) -> str:
    """去首尾空白；必填时不允许为空"""
    text = (value or "").strip()
    if required and not text:
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")
    return text


async def _get_row_or_404(db: AsyncSession, jd_id: int) -> PositionJd:
    result = await db.execute(select(PositionJd).where(PositionJd.id == jd_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"岗位JD不存在: {jd_id}")
    return row


async def _assert_position_free(db: AsyncSession, position: str, exclude_id: Optional[int] = None):
    """position 唯一校验（更新时可排除自身），冲突返回 409"""
    stmt = select(PositionJd.id).where(PositionJd.position == position).limit(1)
    if exclude_id is not None:
        stmt = select(PositionJd.id).where(
            PositionJd.position == position,
            PositionJd.id != exclude_id,
        ).limit(1)
    exists = await db.execute(stmt)
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"岗位已存在: {position}（如需修改请直接编辑该岗位）",
        )


# ── 列表 / 匹配测试 / 新建 ──────────────────────────────────────
@router.get("")
async def list_position_jds(
    category: Optional[str] = None,
    q: Optional[str] = Query(None, description="按岗位名/别名模糊过滤"),
    db: AsyncSession = Depends(get_db),
):
    """岗位 JD 列表（可选按分类/关键词过滤），按 分类→岗位名 排序"""
    stmt = select(PositionJd)
    if category:
        stmt = stmt.where(PositionJd.category == category)
    if q:
        kw = q.strip()
        stmt = stmt.where(
            PositionJd.position.like(f"%{kw}%")
            | PositionJd.aliases.like(f"%{kw}%")
        )
    stmt = stmt.order_by(PositionJd.category, PositionJd.position)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {"items": [r.to_dict() for r in rows], "total": len(rows)}


@router.get("/match")
async def match_position_jd(
    position: str = Query(..., max_length=100, description="要测试的应聘岗位，如 电商运营经理"),
    db: AsyncSession = Depends(get_db),
):
    """匹配测试：输入一个应聘岗位，返回会命中哪份库内 JD（含命中的岗位名）"""
    row = await jd_svc.match_position_row(db, position)
    if row is None:
        return {"matched": False, "position": position, "jd": "", "row": None}
    return {
        "matched": True,
        "position": position,
        "jd": jd_svc.format_jd(row),
        "row": row.to_dict(),
    }


@router.post("", status_code=201)
async def create_position_jd(
    req: PositionJdCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role([UserRole.ADMIN, UserRole.HR])),
):
    """新建岗位 JD（position 已存在返回 409）"""
    position = _clean_str(req.position, "岗位名", required=True)
    await _assert_position_free(db, position)

    row = PositionJd(
        position=position,
        aliases=_clean_str(req.aliases, "别名"),
        category=_clean_str(req.category, "分类") or "other",
        responsibilities=_clean_str(req.responsibilities, "岗位职责"),
        requirements=_clean_str(req.requirements, "任职要求"),
        salary=_clean_str(req.salary, "薪资") or "面议",
        is_system=False,
        is_active=req.is_active,
        created_by=user.id if user else None,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row.to_dict()


# ── 详情操作 ───────────────────────────────────────────────────
@router.put("/{jd_id}")
async def update_position_jd(
    jd_id: int,
    req: PositionJdUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """更新岗位 JD（传哪个字段就更新哪个；岗位名不可与其它行重复）"""
    row = await _get_row_or_404(db, jd_id)
    payload = req.model_dump(exclude_unset=True)

    if "position" in payload:
        new_pos = _clean_str(payload["position"], "岗位名", required=True)
        if new_pos != row.position:
            await _assert_position_free(db, new_pos, exclude_id=jd_id)
        row.position = new_pos
    for field in ("aliases", "category", "responsibilities", "requirements", "salary"):
        if field in payload and isinstance(payload[field], str):
            setattr(row, field, _clean_str(payload[field], field))
    if "is_active" in payload and payload["is_active"] is not None:
        row.is_active = bool(payload["is_active"])

    await db.flush()
    await db.refresh(row)
    return row.to_dict()


@router.delete("/{jd_id}")
async def delete_position_jd(jd_id: int, db: AsyncSession = Depends(get_db)):
    """删除岗位 JD；删除后该岗位的自动套用不再命中（退回岗位名兜底）"""
    row = await _get_row_or_404(db, jd_id)
    position = row.position
    await db.delete(row)
    await db.flush()
    return {"success": True, "id": jd_id, "position": position}


@router.post("/{jd_id}/reset")
async def reset_position_jd(jd_id: int, db: AsyncSession = Depends(get_db)):
    """系统内置岗位：一键恢复汇总 docx 的默认文案（非内置则 409）"""
    row = await _get_row_or_404(db, jd_id)
    builtin = jd_svc.builtin_jd(row.position)
    if builtin is None:
        raise HTTPException(status_code=409, detail="该岗位不是系统内置岗位，无默认 JD 可恢复")
    row.aliases = builtin.get("aliases", "")
    row.category = builtin.get("category", "other")
    row.responsibilities = builtin.get("responsibilities", "")
    row.requirements = builtin.get("requirements", "")
    row.salary = builtin.get("salary", "面议")
    row.is_system = True
    row.is_active = True
    await db.flush()
    await db.refresh(row)
    return row.to_dict()


@router.post("/restore-defaults")
async def restore_defaults(db: AsyncSession = Depends(get_db)):
    """重新补齐缺失的内置岗位 JD（不覆盖用户已编辑过的记录）"""
    inserted, existed = await jd_svc.ensure_default_position_jds(db)
    return {"success": True, "inserted": inserted, "existed": existed}
