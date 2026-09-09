# 【小白导读】数据权限（行级过滤）：admin 看全量，普通 HR 只能看 owner 是自己
#   （或未指派）的候选人/面试。接口里调用 ensure_candidate_visible 等函数做"越权检查"。
#   这是多用户系统防数据泄露的关键层。
"""权限数据范围助手 — HR 数据行级隔离

把"当前用户能看到哪些数据"抽象为可复用的 SQLAlchemy 过滤条件与单对象访问校验，
供 HTTP handler 与 MCP/FC 工具共用：

- admin / user=None（MCP stdio、后台任务全量） → 不过滤（返回 None）
- HR → 候选人归属自己（Candidate.owner_user_id == user.id）
- interviewer → 只可见自己作为面试官（Interview.interviewers 含其 username）的
  面试场次及其关联候选人

隔离统一在 handler / 工具层应用；service、队列 worker、定时任务无用户上下文，
保持全量读写，不套 scope。

MySQL JSON 数组成员判断必须用 ``func.json_contains(col, func.json_quote(x))``；
不要用 ``JSON().contains()`` —— MySQL 下会被编译成 ``LIKE``，误匹配子串。
"""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func

from app.models import Candidate, Interview, User, UserRole


def is_admin(user: Optional[User]) -> bool:
    """是否管理员（或 None 表示受信全量上下文）"""
    return bool(user) and getattr(user, "role", None) == UserRole.ADMIN.value


def candidate_visible_ids_subq(user: Optional[User]):
    """当前用户可见的候选人主键子查询；admin / None → None（全量不过滤）"""
    if not user or is_admin(user):
        return None
    if user.role == UserRole.HR.value:
        return select(Candidate.id).where(Candidate.owner_user_id == user.id)
    if user.role == UserRole.INTERVIEWER.value:
        # 作为面试官参与过（或待参与）的面试所关联的候选人
        return select(Interview.candidate_id).where(
            func.json_contains(Interview.interviewers, func.json_quote(user.username))
        )
    # 兜底：未知角色不可见任何候选人
    return select(Candidate.id).where(func.false())


def candidate_scope_cond(user: Optional[User], cand=None):
    """候选级可见性过滤条件（列表 / count / 聚合 / 详情通用）。

    admin / None → None（调用处不追加 where）；否则返回 cand.id IN (可见子查询)。
    """
    cand = cand or Candidate
    subq = candidate_visible_ids_subq(user)
    if subq is None:
        return None
    return cand.id.in_(subq)


def interview_scope_cond(user: Optional[User], iv=None):
    """面试级可见性过滤条件。

    - admin / None → None
    - interviewer → interviewers 名单含其 username
    - HR / 其它 → 面试关联候选人归属自己
    """
    iv = iv or Interview
    if not user or is_admin(user):
        return None
    if user.role == UserRole.INTERVIEWER.value:
        return func.json_contains(iv.interviewers, func.json_quote(user.username))
    subq = select(Candidate.id).where(Candidate.owner_user_id == user.id)
    return iv.candidate_id.in_(subq)


async def ensure_candidate_visible(db, user: Optional[User], candidate_id: int) -> Candidate:
    """单对象访问控制：候选人不存在或越权一律 404（不泄露存在性）"""
    stmt = select(Candidate).where(Candidate.id == candidate_id)
    cond = candidate_scope_cond(user)
    if cond is not None:
        stmt = stmt.where(cond)
    candidate = (await db.execute(stmt)).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="候选人不存在")
    return candidate


async def candidate_accessible(db, user: Optional[User], candidate_id: int) -> bool:
    """候选人是否对当前用户可见（不抛异常，供 MCP 工具返回 JSON 错误用）"""
    cond = candidate_scope_cond(user)
    if cond is None:
        return True
    stmt = select(func.count(Candidate.id)).where(Candidate.id == candidate_id)
    stmt = stmt.where(cond)
    return ((await db.execute(stmt)).scalar() or 0) > 0


async def ensure_interview_visible(db, user: Optional[User], interview_id: int) -> Interview:
    """面试单对象访问控制：interviewer 须本人在名单；HR 须候选人归属自己。越权 404"""
    iv = (
        await db.execute(select(Interview).where(Interview.id == interview_id))
    ).scalar_one_or_none()
    if not iv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试记录不存在")
    if not user or is_admin(user):
        return iv
    if user.role == UserRole.INTERVIEWER.value:
        ok = user.username in (iv.interviewers or [])
    else:  # HR
        cand = (
            await db.execute(select(Candidate).where(Candidate.id == iv.candidate_id))
        ).scalar_one_or_none()
        ok = bool(cand and cand.owner_user_id == user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="面试记录不存在")
    return iv
