"""简历解析节点

调独立 resume-parser Agent → 或 → 用 Backend ResumeAnalyzer 内联解析
"""
from ..state import RecruitmentState
from ..agent_client import agent_client
from app.database import async_session_factory
from app.services.resume_analyzer import resume_analyzer


async def parse_resume_node(state: RecruitmentState) -> dict:
    """解析简历文件为文本，存入数据库"""
    resume_text = state.get("resume_text", "")
    candidate_id = state.get("candidate_id")

    if not resume_text:
        return {
            "status": "new",
            "pipeline_stage": "resume",
            "errors": ["请先上传简历文件"],
        }

    # 写入数据库（更新候选人状态）
    async with async_session_factory() as db:
        try:
            from sqlalchemy import select
            from app.models.candidate import Candidate

            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if candidate:
                candidate.status = "parsed"
                await db.commit()
        except Exception as e:
            await db.rollback()
            return {
                "status": "new",
                "errors": [f"数据库更新失败: {str(e)}"],
            }

    return {
        "status": "parsed",
        "pipeline_stage": "resume",
        "resume_text": resume_text,
    }
