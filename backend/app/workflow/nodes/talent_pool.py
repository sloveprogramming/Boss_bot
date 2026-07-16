"""人才池节点"""
from ..state import RecruitmentState
from ..utils import get_candidate
from app.database import async_session_factory
from app.models import TalentPool, TalentPoolStatus


async def move_to_talent_pool_node(state: RecruitmentState) -> dict:
    """将候选人移入人才池并创建人才池记录"""
    candidate_id = state.get("candidate_id")
    match_score = state.get("match_score", 0)
    position = state.get("position", "")
    analysis = state.get("analysis_result", {})

    if not candidate_id:
        return {"errors": ["缺少 candidate_id"]}

    async with async_session_factory() as db:
        try:
            from sqlalchemy import select

            candidate = await get_candidate(db, candidate_id)
            if not candidate:
                return {"errors": ["候选人不存在"]}

            existing = await db.execute(
                select(TalentPool).where(TalentPool.candidate_id == candidate_id)
            )
            if existing.scalar_one_or_none():
                candidate.status = "talent_pool"
                await db.commit()
                return {
                    "status": "talent_pool",
                    "pipeline_stage": "talent_pool",
                }

            skills = candidate.tags or []
            if analysis and isinstance(analysis, dict):
                skills = list(set(skills + analysis.get("skills", [])))

            strengths = []
            if analysis and isinstance(analysis, dict):
                match_analysis = analysis.get("match_analysis", {}) if isinstance(analysis, dict) else {}
                strengths = match_analysis.get("strengths", []) if isinstance(match_analysis, dict) else []

            pool_entry = TalentPool(
                candidate_id=candidate_id,
                original_position=position,
                match_score=match_score,
                strengths=strengths,
                pool_reason=f"匹配度{match_score}分，未达当前岗位要求但具备潜力",
                suitable_positions=[],
                skills=skills,
                status=TalentPoolStatus.ACTIVE.value,
            )
            db.add(pool_entry)
            await db.flush()

            candidate.status = "talent_pool"
            candidate.talent_pool_id = pool_entry.id
            candidate.talent_pool_reason = pool_entry.pool_reason

            await db.commit()
        except Exception as e:
            await db.rollback()
            return {
                "status": "talent_pool",
                "errors": [f"人才池创建失败: {str(e)}"],
            }

    return {
        "status": "talent_pool",
        "pipeline_stage": "talent_pool",
    }
