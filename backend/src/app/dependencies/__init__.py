"""依赖注入包"""
from app.dependencies.auth import (
    oauth2_scheme,
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_role,
)
from app.dependencies.scope import (
    is_admin,
    candidate_visible_ids_subq,
    candidate_scope_cond,
    interview_scope_cond,
    ensure_candidate_visible,
    ensure_interview_visible,
    candidate_accessible,
)

__all__ = [
    "oauth2_scheme",
    "hash_password",
    "verify_password",
    "create_access_token",
    "get_current_user",
    "require_role",
    # scope — HR 数据行级隔离
    "is_admin",
    "candidate_visible_ids_subq",
    "candidate_scope_cond",
    "interview_scope_cond",
    "ensure_candidate_visible",
    "ensure_interview_visible",
    "candidate_accessible",
]
