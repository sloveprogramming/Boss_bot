"""JD 全网参考核心编排 —— JD 生成页与 MCP 工具共用

职责边界：
- prepare_jd_reference()          → 搜集 ReferenceMaterials（搜索 + 可选内部知识库 + 拼素材块）
- build_markdown_system()         → JD 页 reference 模式的 system 提示词（流式逐 token 输出用）
- build_reference_user_prompt()   → JD 页 reference 模式的 user 提示词
- generate_jd_reference_json()    → MCP 工具一次性返回完整 JSON 字符串

设计约束：
- 不 import 任何 MCP 模块（避免 agents/services ↔ mcp 层级循环）。
- 内部知识库检索用 httpx 直连 RAG，URL 解析与 mcp/tools/policy.py 保持一致。
- 所有失败优雅降级：搜索失败 → 空素材；内部 KB 失败 → None 静默跳过；
  generate_jd_reference_json 外层 try/except 失败返回 {"error"}，绝不向调用方抛异常。
"""
import json
import logging
import os
from dataclasses import dataclass, field

import httpx

from app.agents.company_profile import (
    format_company_profile_block,
    JD_COMPLIANCE_REDLINES,
)
from app.agents.llm_client import llm_client
from app.agents.prompts import get_position_standards
from app.config import settings
from app.services.web_search import search_web, SearchResult, enrich_with_page_text

logger = logging.getLogger(__name__)

# RAG 地址解析（与 mcp/tools/policy.py 相同优先级：docker 网络名 → env → 本地默认）
def _rag_chat_url() -> str:
    base = (
        os.getenv("RAG_SERVICE_URL")
        or os.getenv("POLICY_RAG_URL")
        or "http://localhost:18003"
    ).rstrip("/")
    return f"{base}/api/chat"


@dataclass
class ReferenceMaterials:
    """一次"全网参考"搜集到的素材集合"""
    query: str = ""
    search_results: list[SearchResult] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)   # [{title,url,snippet,type:"web"|"internal"}]
    reference_block: str = ""                            # 已拼好的素材文本块（直接塞 prompt）
    internal_kb_used: bool = False


def _build_query(position: str, extra: str) -> str:
    """岗位 → 搜索词：岗位名 + 固定关键词 + 截断的补充说明（去重保序）"""
    parts = [position, "招聘", "岗位职责", "任职要求"]
    if extra:
        parts.append(extra[: settings.JD_REF_MAX_EXTRA_QUERY_CHARS])
    return " ".join(dict.fromkeys(p for p in parts if p and p.strip()))


async def _try_internal_kb(question: str) -> dict | None:
    """可选：检索公司内部制度知识库相关岗位说明。任何异常 → None（静默降级）。

    Returns:
        {"answer": str, "sources": [...]}，回答为空也返回 None
    """
    try:
        async with httpx.AsyncClient(timeout=settings.JD_REF_INTERNAL_KB_TIMEOUT) as client:
            resp = await client.post(_rag_chat_url(), json={"message": question})
            resp.raise_for_status()
            data = resp.json()
        answer = (data.get("answer") or "").strip()
        if not answer:
            return None
        return {"answer": answer, "sources": data.get("cited_sources") or []}
    except Exception as e:
        logger.warning("JD 参考内部知识库检索失败（静默跳过）: %s", e)
        return None


async def prepare_jd_reference(
    position: str,
    extra: str = "",
    max_results: int | None = None,
) -> ReferenceMaterials:
    """核心编排：搜索 →（可选）抓正文 →（可选）内部 KB → 拼 reference_block/sources"""
    if not settings.JD_REF_ENABLED:
        return ReferenceMaterials()

    query = _build_query(position, extra)
    results = await search_web(
        query, limit=max_results or settings.JD_REF_MAX_RESULTS,
    )
    if settings.JD_REF_FETCH_PAGE_BODY and results:
        await enrich_with_page_text(results, limit=settings.JD_REF_FETCH_PAGE_LIMIT)

    web_sources = [
        {
            "title": r.title,
            "url": r.url,
            "snippet": (r.page_text or r.snippet)[:300],
            "type": "web",
        }
        for r in results
    ]

    kb = await _try_internal_kb(position) if settings.JD_REF_USE_INTERNAL_KB else None
    internal_sources: list[dict] = []
    if kb:
        for s in kb.get("sources") or []:
            if isinstance(s, dict):
                title = s.get("title") or s.get("filename") or s.get("source") or "内部文档"
            else:
                title = str(s)
            internal_sources.append({
                "title": title,
                "url": "",
                "snippet": "",
                "type": "internal",
            })

    # 拼素材文本块
    parts: list[str] = []
    if web_sources:
        lines = ["【全网同类 JD 素材】"]
        for idx, s in enumerate(web_sources, 1):
            lines.append(
                f"{idx}. {s['title']}\n"
                f"   链接：{s['url']}\n"
                f"   摘要：{s['snippet'] or '（无摘要）'}"
            )
        parts.append("\n".join(lines))
    if kb:
        parts.append("【公司内部知识库相关说明】\n" + (kb.get("answer") or "")[:1500])
    block = "\n\n".join(parts)

    return ReferenceMaterials(
        query=query,
        search_results=results,
        sources=web_sources + internal_sources,
        reference_block=block,
        internal_kb_used=kb is not None,
    )


# ===== Prompt 构造 =====

# 借鉴约束：外部素材只准借结构，不得照抄可能含歧视/夸大薪资的具体表述
REFERENCE_USAGE_INSTRUCTION = (
    "以下是你搜集到的【全网同类真实 JD 参考片段】。它们可能含性别/年龄/地域/学历限定或"
    "夸大薪资等表述——你只允许借鉴其【职责划分、技能点、条理结构、常见能力要求】；"
    "任何具体表述都必须先过我司合规红线，并据【我司公司档案】改写成符合我司招聘风格的草稿。\n"
    "{block}"
)

# JD 撰写基础要求（与 jd_generator.JD_SYSTEM_PROMPT 前半部分一致）
_JD_MD_BASE = """你是一位资深招聘专家，为企业撰写高质量、合规的岗位 JD（Job Description）。

输出要求：
1. 使用 Markdown 格式，结构固定为四个二级标题，依次为：
   ## 岗位职责
   ## 任职要求
   ## 加分项
   ## 薪资福利
2. 岗位职责 5-8 条，任职要求 4-7 条，加分项 2-4 条；每条以 "- " 开头，一句话聚焦一个职责/要求。
3. 语言简洁专业、有吸引力，突出岗位价值、技术挑战与成长空间；避免空洞套话。

"""


def build_markdown_system() -> str:
    """JD 页 reference 模式 system：四段式 + 公司档案 + 合规红线"""
    return (
        _JD_MD_BASE
        + format_company_profile_block()
        + "\n\n"
        + JD_COMPLIANCE_REDLINES
    )


def build_reference_user_prompt(
    position: str,
    salary: str,
    education: str,
    extra: str,
    materials: ReferenceMaterials,
    standards: str,
) -> str:
    """JD 页 reference 模式 user（素材块非空时使用）"""
    return (
        f"请为以下岗位参考全网同类 JD 生成一份适配我司的 JD：\n"
        f"- 岗位名称：{position}\n"
        f"- 薪资范围：{salary or '面议'}\n"
        f"- 学历要求：{education or '不限'}\n"
        f"- 补充说明：{extra or '无'}{standards}\n\n"
        + REFERENCE_USAGE_INSTRUCTION.format(block=materials.reference_block)
        + "\n直接输出 Markdown JD，不要输出任何解释性文字。"
    )


# ===== MCP 工具用：一次性完整 JSON =====

_JSON_SYSTEM = (
    "你是资深招聘专家。根据参考的同类 JD 与我司公司档案，输出一份适配我司的参考 JD 草稿。\n"
    "只允许借鉴外部 JD 的职责/技能结构；具体表述必须过我司合规红线。\n"
    + JD_COMPLIANCE_REDLINES
    + """
\n严格输出 JSON（不要输出 JSON 以外的文字），字段如下：
{
  "position": "岗位名称",
  "department": "该岗位在我司归口的部门（不确定则为空字符串）",
  "jd_markdown": "四段式 Markdown JD（## 岗位职责 / ## 任职要求 / ## 加分项 / ## 薪资福利）",
  "highlights": ["这份草稿相对市场同类 JD 的本司化亮点/调整要点"],
  "notes": ["写作说明，如学历按用户给定呈现、以正式发布为准"]
}
注意：jd_markdown 中薪资必须写具体范围或"面议"；学历要求只能照用户给定或"不限"；
不要编造我司不存在的公司名/规模/福利。"""
)


async def generate_jd_reference_json(
    position: str,
    extra: str = "",
    max_results: int = 8,
) -> str:
    """MCP 工具入口：搜索 + LLM 综合 → 一次性返回完整 JSON 字符串。

    Returns:
        成功 → {"position","department","jd_markdown","sources","highlights","notes"}
        任何失败 → {"error": "..."}（优雅降级，不抛异常）
    """
    try:
        if not position or not position.strip():
            return json.dumps({"error": "岗位名称不能为空"}, ensure_ascii=False)

        materials = await prepare_jd_reference(
            position.strip(), extra or "", max_results,
        )
        standards = get_position_standards(position)

        if materials.reference_block:
            user = (
                f"岗位名称：{position}；补充需求：{extra or '无'}{standards}\n\n"
                + REFERENCE_USAGE_INSTRUCTION.format(block=materials.reference_block)
            )
        else:
            user = (
                f"岗位名称：{position}；补充需求：{extra or '无'}{standards}\n\n"
                + "（本次未获取到外部参考素材，请凭你的行业知识并结合我司公司档案生成草稿。）"
            )

        full = ""
        async for chunk in llm_client.stream_chat_json(
            _JSON_SYSTEM,
            [{"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=2500,
        ):
            full = chunk

        data = json.loads(full)
        data.setdefault("department", "")
        data.setdefault("highlights", [])
        data.setdefault("notes", [])
        data["sources"] = materials.sources
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        logger.exception("JD 全网参考生成失败: position=%s", position)
        return json.dumps({"error": f"生成参考 JD 失败：{e}"}, ensure_ascii=False)
