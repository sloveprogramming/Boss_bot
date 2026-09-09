# 【小白导读】工具：JD 参考查询（联网搜同类岗位 JD 作参考），供 JD 生成使用。
"""MCP Tool — 全网同类真实 JD 参考检索 + 公司档案适配

供 Function Calling 对话中的 HR 使用，如"帮我找『电商运营经理』的 JD 参考"。
本工具不读候选人/面试数据，无需 user 注入（无行级隔离需求）。

返回 JSON 字符串（由上层 LLM 转述给用户）：
  {"jd_markdown", "department", "sources": [...], "highlights": [...], "notes": [...]}
异常一律优雅降级为 {"error": "..."}，不抛异常打断对话。
"""
import json
import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def jd_reference_search(
    position: str,
    extra: str = "",
    max_results: int = 8,
) -> str:
    """搜索并生成适配我司的参考 JD 草稿

    Args:
        position: 岗位名称，如"电商运营经理"
        extra: 补充需求/行业限定/能力侧重（可选），如"坚果食品、5年以上、擅长付费投放"
        max_results: 外部参考条数上限（默认 8）

    Returns:
        JSON 字符串：{jd_markdown, department, sources, highlights, notes} 或 {error}
    """
    if not settings.JD_REF_ENABLED:
        return json.dumps(
            {"error": "全网 JD 参考功能未开启（JD_REF_ENABLED=false），请使用普通 JD 生成。"},
            ensure_ascii=False,
        )
    if not position or not position.strip():
        return json.dumps({"error": "岗位名称不能为空"}, ensure_ascii=False)

    # 懒加载：避免 mcp → services 顶层 import 造成启动期耦合；真实失败已由 service 内兜底
    from app.services.jd_reference_service import generate_jd_reference_json

    return await generate_jd_reference_json(
        position.strip(), extra or "", max_results,
    )
