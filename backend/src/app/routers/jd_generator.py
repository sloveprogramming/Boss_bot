"""JD 生成 API — 岗位描述智能生成（SSE 流式输出）

市场主流做法（Moka EVA / 北森）：少量结构化输入 → LLM 生成结构化 JD 草稿 → 人工编辑采纳。
本实现：
  输入：岗位、薪资、学历（+ 可选补充说明）
  输出：Markdown 结构化 JD（岗位职责 / 任职要求 / 加分项 / 薪资福利），SSE 逐字推送
  合规：提示词内置《就业促进法》反歧视红线，禁止性别/年龄/婚育/地域等限定表述
  一致性：注入 get_position_standards() 岗位专项标准，使 JD 与简历评分锚点保持一致
"""
import json
import logging
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from app.agents.llm_client import llm_client
from app.agents.prompts import get_position_standards
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


JD_SYSTEM_PROMPT = """你是一位资深招聘专家，为企业撰写高质量、合规的岗位 JD（Job Description）。

输出要求：
1. 使用 Markdown 格式，结构固定为四个二级标题，依次为：
   ## 岗位职责
   ## 任职要求
   ## 加分项
   ## 薪资福利
2. 岗位职责 5-8 条，任职要求 4-7 条，加分项 2-4 条；每条以 "- " 开头，一句话聚焦一个职责/要求。
3. 语言简洁专业、有吸引力，突出岗位价值、技术挑战与成长空间；避免空洞套话。

合规红线（最高优先级，违反即输出无效）：
- 不得出现性别、年龄、婚育状况、户籍/地域、民族、宗教、身材外貌等歧视性或限定性表述；
- 学历要求只能按用户输入原样呈现，不得自行提高或附加"全日制"等限定；
- 薪资必须写明具体范围或"面议"，不得使用"高薪""薪资上不封顶"等模糊承诺作为唯一描述。"""


def _sse_event(data: str) -> str:
    """封装一条 SSE 事件（与 workflow SSE 相同的 data: JSON 协议）"""
    return f"data: {data}\n\n"


@router.post("/generate/stream")
async def generate_jd_stream(req: JdGenerateRequest):
    """JD 生成（SSE 流式）— 逐 token 推送 Markdown 文本

    事件协议：data: {"text": "..."}，结束时 data: [DONE]
    """
    position = req.position.strip()
    if not position:
        return StreamingResponse(
            iter([_sse_event(json.dumps({"error": "岗位名称不能为空"}, ensure_ascii=False)), "data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    # 注入岗位专项评分标准，保证 JD 与简历评分锚点一致
    standards = get_position_standards(position)

    user_prompt = f"""请为以下岗位生成 JD：

- 岗位名称：{position}
- 薪资范围：{req.salary or "面议"}
- 学历要求：{req.education or "不限"}
- 补充说明：{req.extra or "无"}{standards}

直接输出 Markdown JD，不要输出任何解释性文字。"""

    messages = [{"role": "user", "content": user_prompt}]

    async def generate():
        try:
            full = ""
            async for delta in llm_client.stream_chat(
                JD_SYSTEM_PROMPT, messages, temperature=0.7, max_tokens=2048,
            ):
                full += delta
                yield _sse_event(json.dumps({"text": delta}, ensure_ascii=False))
            logger.info("JD 生成完成: position=%s len=%d", position, len(full))
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
