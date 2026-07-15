"""人才池节点 — 低匹配度但有潜力的候选人进入人才池

合并了旧系统中：
1. agents/orchestrator 的 move_to_talent_pool_node
2. backend/app/services/workflow.py 的 _move_to_talent_pool() 逻辑
"""
from ..state import RecruitmentState
from app.database import async_session_factory
from app.models.talent_pool import TalentPool, TalentPoolStatus


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
            from app.models.candidate import Candidate

            # 获取候选人
            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if not candidate:
                return {"errors": ["候选人不存在"]}

            # 检查是否已有人才池记录
            existing = await db.execute(
                select(TalentPool).where(TalentPool.candidate_id == candidate_id)
            )
            if existing.scalar_one_or_none():
                # 已在人才池中
                candidate.status = "talent_pool"
                await db.commit()
                return {
                    "status": "talent_pool",
                    "pipeline_stage": "talent_pool",
                }

            # 提取技能和优势
            skills = candidate.tags or []
            if analysis and isinstance(analysis, dict):
                skills = list(set(skills + analysis.get("skills", [])))

            strengths = []
            if analysis and isinstance(analysis, dict):
                match_analysis = analysis.get("match_analysis", {}) if isinstance(analysis, dict) else {}
                strengths = match_analysis.get("strengths", []) if isinstance(match_analysis, dict) else []

            # 创建人才池记录
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

            # 更新候选人
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
