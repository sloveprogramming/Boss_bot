"""简历分析节点

调用独立 Analyzer Agent → 或 → 用 Backend ResumeAnalyzer 内联分析+评分

合并了旧系统中两个分散的"分析"逻辑：
1. agents/orchestrator 通过 HTTP 调用 Analyzer Agent
2. backend/app/services/resume_analyzer.py 的 analyze_resume()
"""
from ..state import RecruitmentState
from ..agent_client import agent_client
from app.database import async_session_factory
from app.agents.llm_client import llm_client
from app.agents.prompts import RESUME_ANALYSIS_SYSTEM, RESUME_ANALYSIS_PROMPT


async def analyze_node(state: RecruitmentState) -> dict:
    """分析简历并给出匹配度评分"""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", state.get("position", ""))
    category = state.get("job_category", "python")
    candidate_id = state.get("candidate_id")

    # 尝试调用独立 Analyzer Agent
    agent_result = await agent_client.analyze(category, resume_text, job_desc)
    if agent_result:
        match = agent_result.get("match_analysis", {})
        analysis = agent_result.get("analysis", {})
        score = match.get("overall_score", 50)
    else:
        # 降级：内联 LLM 分析
        analysis, match, score = await _inline_analyze(resume_text, job_desc)

    # 写入数据库
    async with async_session_factory() as db:
        try:
            from sqlalchemy import select, update
            from app.models.candidate import Candidate
            from app.models.resume import Resume

            # 更新候选人
            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if candidate:
                candidate.match_score = score
                candidate.job_category = category
                candidate.status = "analyzed"

                # 从分析结果中提取基本信息和技能
                if analysis:
                    basic = analysis.get("basic_info", {})
                    skills = analysis.get("skills", [])
                    if basic.get("name") and not candidate.name:
                        candidate.name = basic["name"]
                    if basic.get("phone") and not candidate.phone:
                        candidate.phone = basic.get("phone")
                    if basic.get("email") and not candidate.email:
                        candidate.email = basic.get("email")
                    if skills:
                        candidate.tags = list(set((candidate.tags or []) + skills[:10]))

            # 更新最近的简历记录
            result2 = await db.execute(
                select(Resume)
                .where(Resume.candidate_id == candidate_id)
                .order_by(Resume.created_at.desc())
                .limit(1)
            )
            resume = result2.scalar_one_or_none()
            if resume:
                resume.analysis_result = analysis
                resume.match_analysis = match
                resume.summary = analysis.get("summary", "") if isinstance(analysis, dict) else ""
                from datetime import datetime
                resume.analyzed_at = datetime.utcnow()

            await db.commit()
        except Exception:
            await db.rollback()

    return {
        "analysis_result": analysis,
        "match_analysis": match,
        "match_score": score,
        "status": "analyzed",
        "pipeline_stage": "resume",
    }


async def _inline_analyze(resume_text: str, job_description: str) -> tuple:
    """内联 LLM 分析（同 Backend ResumeAnalyzer 逻辑）"""
    import json
    import re

    truncated = resume_text[:15000]
    prompt = RESUME_ANALYSIS_PROMPT.format(
        resume_text=truncated,
        job_description=job_description or "通用岗位",
    )

    response = await llm_client.chat(
        system=RESUME_ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=4096,
    )

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        data = json.loads(json_match.group()) if json_match else {}

    analysis = data.get("analysis", {})
    match_analysis = data.get("match_analysis", {})
    score = match_analysis.get("overall_score", 50)

    if isinstance(analysis, dict) and "summary" not in analysis:
        analysis["summary"] = data.get("summary", "")

    return analysis, match_analysis, score
