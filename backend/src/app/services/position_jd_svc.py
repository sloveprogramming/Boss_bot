# ═══════════════════════════════════════════════════════════════
# 【小白导读】岗位 JD 库的"大脑"：负责把内置 JD 播种进数据库、
#   简历分析前按候选人「应聘岗位」自动匹配一份 JD 文本喂给大模型。
#   匹配优先级：HR 手填 JD（manual）> 库内该岗位 JD > 岗位名兜底。
#   自动发送/分析的所有入口都走 resolve_jd_with_manual，保证行为一致。
# ═══════════════════════════════════════════════════════════════
"""可配置岗位JD服务 — 播种 / 按岗位匹配 / 手填优先解析

设计原则：
  - 内置 JD 唯一事实来源 = services/position_jd_data.py 的 SEED_JDS（由脚本生成），
    本文件只负责"缺失即播种、不覆盖已编辑行"。
  - 自动分析解析顺序：manual(手填非空) → DB 生效岗位JD → candidate.position。
"""
import re
from typing import Optional

from sqlalchemy import select

from app.database import async_session_factory
from app.models.position_jd import PositionJd
from app.services.position_jd_data import SEED_JDS

# 别名分隔符：兼容顿号/逗号/分号/竖线等 HR 输入习惯
_ALIAS_SPLIT = re.compile(r"[，,、;；/|]+")


def builtin_jd(position: str) -> Optional[dict]:
    """查内置 SEED_JDS 里某岗位的默认内容（供「恢复默认」用）"""
    for item in SEED_JDS:
        if item["position"] == position:
            return item
    return None


def _split_aliases(aliases: str) -> list:
    """把别名串拆成列表（去空去重保序）"""
    out, seen = [], set()
    for a in _ALIAS_SPLIT.split(aliases or ""):
        a = a.strip()
        if a and a not in seen:
            seen.add(a)
            out.append(a)
    return out


def format_jd(row) -> str:
    """把一条岗位 JD 拼成喂给大模型的招聘标准文本（不含薪资）"""
    parts = [f"【岗位名称】{row.position}"]
    if row.responsibilities:
        parts.append(f"【岗位职责】\n{row.responsibilities}")
    if row.requirements:
        parts.append(f"【任职要求】\n{row.requirements}")
    return "\n\n".join(parts)


async def ensure_default_position_jds(db) -> tuple:
    """把内置 SEED_JDS 播种进数据库（仅缺失时插入，绝不覆盖用户已编辑的记录）。

    Returns:
        (inserted_count, existed_count)
    """
    if not SEED_JDS:
        return 0, 0
    result = await db.execute(select(PositionJd.position))
    existing = {row[0] for row in result.all()}

    inserted = 0
    for item in SEED_JDS:
        position = item["position"]
        if position in existing:
            continue
        db.add(PositionJd(
            position=position,
            aliases=item.get("aliases", ""),
            category=item.get("category", "other"),
            responsibilities=item.get("responsibilities", ""),
            requirements=item.get("requirements", ""),
            salary=item.get("salary", "面议"),
            is_system=True,
            is_active=True,
        ))
        inserted += 1
    if inserted:
        await db.flush()
    return inserted, len(existing)


async def match_position_row(db, position: str):
    """在给定会话里做最长命中匹配，返回命中的 PositionJd 行（未命中 None）。

    匹配规则：对行内 [position + 别名] 每个词做最长命中打分——
      完全相等 > 词是候选人填写的子串 > 候选人是词的子串（缩写，如去掉括号备注）。
    只匹配 is_active=True 的行；同分行按 id 小者优先。
    """
    pos = (position or "").strip()
    if not pos:
        return None
    result = await db.execute(
        select(PositionJd).where(PositionJd.is_active.is_(True)).order_by(PositionJd.id)
    )
    rows = result.scalars().all()

    best = None
    best_score = 0
    for row in rows:
        tokens = [row.position] + _split_aliases(row.aliases)
        for tok in tokens:
            tok = (tok or "").strip()
            if not tok:
                continue
            if tok == pos:
                score = 10000 + len(tok)   # 完全相等最优先
            elif tok in pos:
                score = len(tok)            # 库名是候选人填写的子串
            elif pos in tok:
                score = len(pos)            # 候选人是库名的缩写（如去掉括号备注）
            else:
                continue
            if score > best_score:
                best_score = score
                best = row
    return best


async def _resolve_position_jd(db, position: str) -> str:
    """在给定会话里按岗位解析 JD 文本（无会话时由外层 resolve_position_jd 开）。"""
    row = await match_position_row(db, position)
    return format_jd(row) if row is not None else ""


async def resolve_position_jd(db, position: str) -> str:
    """按候选人「应聘岗位」解析库内对应岗位的 JD 文本；未命中返回空串。

    db 可传 None（worker 等无会话场景会自开会话），也可传现有会话（复用连接）。
    """
    if db is not None:
        return await _resolve_position_jd(db, position)
    async with async_session_factory() as session:
        return await _resolve_position_jd(session, position)


async def resolve_jd_with_manual(db, position: str, manual: str) -> str:
    """统一解析实际喂给模型的岗位描述：

    manual 非空 → 原样用它（HR 手填优先）；
    否则 → 查库内该岗位 JD（匹配不到 → 岗位名兜底，保持历史行为）。
    """
    if manual and manual.strip():
        return manual.strip()
    resolved = await resolve_position_jd(db, position)
    return resolved if resolved else (position or "")
