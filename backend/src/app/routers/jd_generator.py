# ═══════════════════════════════════════════════════════════════
# 【小白导读】JD（职位描述）生成：SSE 流式接口，边生成边往前端推字。
#   增强：services/jd_reference_service.py 联网搜同类 JD 作参考。
#   SSE 概念：HTTP 长连接，服务器可持续往客户端"推"文本事件，适合打字机效果。
# ═══════════════════════════════════════════════════════════════
"""JD 生成 API — 岗位描述智能生成（SSE 流式输出）

市场主流做法（Moka EVA / 北森）：少量结构化输入 → LLM 生成结构化 JD 草稿 → 人工编辑采纳。
本实现：
  输入：岗位、薪资、学历（+ 可选补充说明）
  输出：Markdown 结构化 JD（岗位职责 / 任职要求 / 加分项 / 薪资福利），SSE 逐字推送
  合规：提示词内置《就业促进法》反歧视红线，禁止性别/年龄/婚育/地域等限定表述
         （红线抽为共享常量 agents/company_profile.JD_COMPLIANCE_REDLINES，与"全网参考"共用）
  一致性：注入 get_position_standards() 岗位专项标准，使 JD 与简历评分锚点保持一致
  全网参考（reference=true）：先抓取全网同类真实 JD 作素材，再结合公司档案适配本司草稿，
         SSE 事件顺序：{"sources"} →（可选 {"notes"}）→ {"text"}* → data:[DONE]
"""
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.agents.company_profile import JD_COMPLIANCE_REDLINES
from app.agents.llm_client import llm_client
from app.agents.prompts import get_position_standards
from app.config import settings
from app.dependencies import require_role
from app.models import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/jd",
    tags=["JD生成"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


class JdGenerateRequest(BaseModel):
    """JD 生成请求 — 最小结构化输入"""
    position: str = Field(..., min_length=1, max_length=100, description="岗位名称，如：Python后端工程师")
    salary: str = Field("", max_length=100, description="薪资范围，如：20-35K·14薪")
    education: str = Field("", max_length=50, description="学历要求，如：本科")
    extra: Optional[str] = Field(None, max_length=500, description="补充说明（团队亮点/技术栈/福利等）")
    reference: bool = Field(False, description="True = 先全网搜同类真实 JD 作为素材，再按公司档案适配生成")


JD_SYSTEM_PROMPT = f"""你是一位资深招聘专家，为企业撰写高质量、合规的岗位 JD（Job Description）。

输出要求：
1. 使用 Markdown 格式，结构固定为四个二级标题，依次为：
   ## 岗位职责
   ## 任职要求
   ## 加分项
   ## 薪资福利
2. 岗位职责 5-8 条，任职要求 4-7 条，加分项 2-4 条；每条以 "- " 开头，一句话聚焦一个职责/要求。
3. 语言简洁专业、有吸引力，突出岗位价值、技术挑战与成长空间；避免空洞套话。

{JD_COMPLIANCE_REDLINES}"""


def _sse_event(data: str) -> str:
    """封装一条 SSE 事件（与 workflow SSE 相同的 data: JSON 协议）"""
    return f"data: {data}\n\n"


@router.post("/generate/stream")
async def generate_jd_stream(req: JdGenerateRequest):
    """JD 生成（SSE 流式）— 逐 token 推送 Markdown 文本

    事件协议：data: {"text": "..."}，结束时 data: [DONE]
    reference=true 时先发 data: {"sources": [...]}（+ 可选 {"notes"}），再开始 text 流。
    """
    position = req.position.strip()
    if not position:
        return StreamingResponse(
            iter([_sse_event(json.dumps({"error": "岗位名称不能为空"}, ensure_ascii=False)), "data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    async def generate():
        try:
            if req.reference:
                # 全网参考：搜索 +（可选内部 KB）→ 素材块；耗时较长，进流后执行，首事件即 sources
                from app.services.jd_reference_service import (
                    prepare_jd_reference,
                    build_markdown_system,
                    build_reference_user_prompt,
                )
                materials = await prepare_jd_reference(
                    position, req.extra or "", max_results=settings.JD_REF_MAX_RESULTS,
                )
                yield _sse_event(json.dumps({"sources": materials.sources}, ensure_ascii=False))
                if not materials.sources:
                    yield _sse_event(json.dumps(
                        {"notes": ["未获取到外部参考，已按公司档案与岗位标准生成，请人工核对"]},
                        ensure_ascii=False,
                    ))

                system = build_markdown_system()
                standards = get_position_standards(position)
                if materials.reference_block:
                    user_prompt = build_reference_user_prompt(
                        position, req.salary, req.education, req.extra or "", materials, standards,
                    )
                else:
                    user_prompt = (
                        f"请为以下岗位生成一份适配我司的 JD：\n\n"
                        f"- 岗位名称：{position}\n"
                        f"- 薪资范围：{req.salary or '面议'}\n"
                        f"- 学历要求：{req.education or '不限'}\n"
                        f"- 补充说明：{req.extra or '无'}{standards}\n"
                        f"（本次未获取到外部参考素材，凭你的行业知识并结合公司档案生成。）\n\n"
                        f"直接输出 Markdown JD，不要输出任何解释性文字。"
                    )
            else:
                # 普通生成：保持原逻辑
                system = JD_SYSTEM_PROMPT
                standards = get_position_standards(position)
                user_prompt = f"""请为以下岗位生成 JD：

- 岗位名称：{position}
- 薪资范围：{req.salary or "面议"}
- 学历要求：{req.education or "不限"}
- 补充说明：{req.extra or "无"}{standards}

直接输出 Markdown JD，不要输出任何解释性文字。"""

            messages = [{"role": "user", "content": user_prompt}]
            full = ""
            async for delta in llm_client.stream_chat(
                system, messages, temperature=0.7, max_tokens=2048,
            ):
                full += delta
                yield _sse_event(json.dumps({"text": delta}, ensure_ascii=False))
            logger.info("JD 生成完成: position=%s reference=%s len=%d", position, req.reference, len(full))
        except Exception as e:
            logger.exception("JD 生成失败: position=%s", position)
            yield _sse_event(json.dumps({"error": f"生成失败：{e}"}, ensure_ascii=False))
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
