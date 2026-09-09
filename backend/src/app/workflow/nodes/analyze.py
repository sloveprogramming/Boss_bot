# 【小白导读】第 3 站：3 个子 Agent 并行分析（基本信息/技能/经验），
#   各自只写 state 里自己的 key；synthesize_analysis_node 汇总三者、
#   调 scoring.py 算总分并写库。真正调 LLM 的是 services/resume_analyzer.py。
"""简历分析节点 — 3 个 Agent 并行分析 + 综合汇总

classify 之后拆成 3 路并行（基本信息、技能、经验），LangGraph 自动等 3 路都跑完
再走 synthesize 综合打分。比原来单链快，而且每个 Agent 只管一件事，prompt 更精准。
"""
import json
import re
import logging
from typing import Optional
from ..state import RecruitmentState
from ..agent_client import agent_client
from ..scoring import compute_overall, extract_dimension_scores, get_weights
from app.database import async_session_factory
from app.agents import llm_client
from app.agents.prompts import (
    PROMPT_VERSION,
    get_position_standards,
    BASIC_INFO_ANALYZER_SYSTEM, BASIC_INFO_ANALYZER_PROMPT,
    SKILL_ANALYZER_SYSTEM, SKILL_ANALYZER_PROMPT,
    EXPERIENCE_ANALYZER_SYSTEM, EXPERIENCE_ANALYZER_PROMPT,
    SYNTHESIZE_ANALYSIS_SYSTEM, SYNTHESIZE_ANALYSIS_PROMPT,
)
from langgraph.types import Send

logger = logging.getLogger(__name__)


def _position_standards(state: RecruitmentState) -> str:
    """按投递岗位+分类结果取岗位专项评分标准（无匹配返回空串）"""
    return get_position_standards(
        position=state.get("position", "") or "",
        category=state.get("job_category", "") or "",
    )


def route_to_analyzers(state: RecruitmentState):
    """把 State 同时发给 3 个子 Agent —— LangGraph 的 Send 会并行执行"""
    return [
        Send("analyze_basic_info", state),
        Send("analyze_skills", state),
        Send("analyze_experience", state),
    ]


async def analyze_basic_info_node(state: RecruitmentState) -> dict:
    """提取姓名、电话、邮箱、学历"""
    resume_text = state.get("resume_text", "")

    # 优先用远程 Agent 服务，不行再 fallback 到本地 LLM
    agent_result = await agent_client.analyze(
        state.get("job_category", "python"),
        resume_text,
        state.get("job_description", ""),
    )
    if agent_result:
        analysis = agent_result.get("analysis", {})
        basic = analysis.get("basic_info", {})
        return {"basic_info_analysis": {
            "name": basic.get("name", ""),
            "phone": basic.get("phone", ""),
            "email": basic.get("email", ""),
            "location": basic.get("location", ""),
            "education": analysis.get("education", []),
            "certifications": analysis.get("certifications", []),
            "source": "agent",
        }}

    prompt = BASIC_INFO_ANALYZER_PROMPT.format(resume_text=resume_text[:15000])
    response = await llm_client.chat(
        system=BASIC_INFO_ANALYZER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=1024,
    )
    data = _safe_json_parse(response)
    data["source"] = "inline"
    logger.info("候选人 %s 基本信息分析完成 (source=inline)", state.get("candidate_id"))
    return {"basic_info_analysis": data}


async def analyze_skills_node(state: RecruitmentState) -> dict:
    """评估技术栈与岗位的匹配度"""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", state.get("position", ""))
    standards = _position_standards(state)

    prompt = SKILL_ANALYZER_PROMPT.format(
        resume_text=resume_text[:15000],
        job_description=job_desc or "通用岗位",
    )
    response = await llm_client.chat(
        system=f"{SKILL_ANALYZER_SYSTEM}{standards}",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.15,
        max_tokens=1024,
    )
    data = _safe_json_parse(response)
    data["source"] = "inline"
    data["has_position_standards"] = bool(standards)
    logger.info(
        "候选人 %s 技能分析完成 (score=%s, position_standards=%s)",
        state.get("candidate_id"), data.get("skill_match_score"), bool(standards),
    )
    return {"skills_analysis": data}


async def analyze_experience_node(state: RecruitmentState) -> dict:
    """评估工作经历、项目经验和稳定性"""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", state.get("position", ""))
    standards = _position_standards(state)

    prompt = EXPERIENCE_ANALYZER_PROMPT.format(
        resume_text=resume_text[:15000],
        job_description=job_desc or "通用岗位",
    )
    response = await llm_client.chat(
        system=f"{EXPERIENCE_ANALYZER_SYSTEM}{standards}",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.15,
        max_tokens=1536,
    )
    data = _safe_json_parse(response)
    data["source"] = "inline"
    data["has_position_standards"] = bool(standards)
    logger.info(
        "候选人 %s 经验分析完成 (score=%s, position_standards=%s)",
        state.get("candidate_id"), data.get("experience_score"), bool(standards),
    )
    return {"experience_analysis": data}


async def synthesize_analysis_node(state: RecruitmentState) -> dict:
    """汇总 3 个子 Agent 的结果 → 综合评分（v2） → 写库

    v2 评分体系：
      - 通道A（权威）：维度分 × 可配置权重，代码计算，总分可全量重算
      - 通道B（只记录）：LLM 综合重评分，用于 diff 观察和偏差监控
      - 维度分缺失时不再默认 50 分：部分缺失按重归一化权重计算并标记，
        全部缺失才降级用 LLM 分；凡不完整 analysis_complete=False，
        路由层不自动分流，转人工复核
    """
    basic = state.get("basic_info_analysis", {})
    skills = state.get("skills_analysis", {})
    experience = state.get("experience_analysis", {})
    candidate_id = state.get("candidate_id")
    category = state.get("job_category", "python")
    standards = _position_standards(state)

    # 综合报告（LLM 通道B：定性报告 + 独立重评分，只记录不决定分流）
    prompt = SYNTHESIZE_ANALYSIS_PROMPT.format(
        basic_info=json.dumps(basic, ensure_ascii=False),
        skills_eval=json.dumps(skills, ensure_ascii=False),
        experience_eval=json.dumps(experience, ensure_ascii=False),
    )
    response = await llm_client.chat(
        system=f"{SYNTHESIZE_ANALYSIS_SYSTEM}{standards}",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=2048,
    )
    synthesized = _safe_json_parse(response)

    # ===== 通道A：维度分 × 权重（权威分） =====
    weights = get_weights(category)
    dimension_scores = extract_dimension_scores(skills, experience)
    scoring = compute_overall(dimension_scores, weights)

    overall = scoring["overall"]
    if overall is None:
        # 三个维度全缺失：降级用 LLM 重评分，但标记不完整，不自动分流
        llm_overall = _to_float(synthesized.get("overall_score"))
        overall = llm_overall if llm_overall is not None else 0.0
        scoring["source"] = "llm_fallback"

    # ===== 通道B：LLM 重评分 + diff（只记录，观察期攒数据） =====
    llm_overall = _to_float(synthesized.get("overall_score"))
    score_diff = None
    if llm_overall is not None and scoring["source"] != "llm_fallback":
        score_diff = round(abs(overall - llm_overall), 1)

    analysis_complete = scoring["complete"]
    if score_diff is not None:
        logger.info(
            "候选人 %s 评分双通道 diff=%.1f (加权=%.1f, LLM=%.1f)",
            candidate_id, score_diff, overall, llm_overall,
        )
    if not analysis_complete:
        logger.warning(
            "候选人 %s 维度分不完整 (missing=%s, source=%s)，不自动分流，转人工复核",
            candidate_id, scoring["missing"], scoring["source"],
        )

    # 构造输出结构（和旧版兼容）
    analysis = {
        "basic_info": {
            "name": basic.get("name", ""),
            "phone": basic.get("phone", ""),
            "email": basic.get("email", ""),
            "location": basic.get("location", ""),
        },
        "education": basic.get("education", []),
        "skills": skills.get("skills", []),
        "work_experience": experience.get("work_experience", []),
        "projects": experience.get("projects", []),
        "certifications": basic.get("certifications", []),
    }
    match_analysis = {
        "overall_score": overall,
        "dimensions": synthesized.get("dimensions", {}),
        "dimension_scores": dimension_scores,       # v2: 原始维度分落库（改权重可全量重算）
        "weights_used": scoring["weights_used"],    # v2: 本次计算用的权重快照
        "score_source": scoring["source"],          # weighted / weighted_partial / llm_fallback
        "analysis_complete": analysis_complete,     # v2: False → 不自动分流
        "missing_dimensions": scoring["missing"],
        "llm_overall_score": llm_overall,           # 通道B，只记录
        "score_diff": score_diff,                   # |A-B|，观察期攒数据定阈值
        "prompt_version": PROMPT_VERSION,           # v2: 提示词版本随结果落库
        "applied_position_standards": bool(standards),  # 是否命中岗位专项评分标准
        "strengths": synthesized.get("strengths", []),
        "risks": synthesized.get("risks", []),
        "recommended_questions": synthesized.get("recommended_questions", []),
    }

    # 写库
    async with async_session_factory() as db:
        try:
            from sqlalchemy import select
            from app.models import Candidate, Resume

            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if candidate:
                candidate.match_score = overall
                candidate.job_category = category
                candidate.status = "analyzed"
                if basic.get("name") and not candidate.name:
                    candidate.name = basic["name"]
                if basic.get("phone") and not candidate.phone:
                    candidate.phone = basic["phone"]
                if basic.get("email") and not candidate.email:
                    candidate.email = basic["email"]
                if skills.get("skills"):
                    candidate.tags = list(set((candidate.tags or []) + skills["skills"][:10]))

            result2 = await db.execute(
                select(Resume)
                .where(Resume.candidate_id == candidate_id)
                .order_by(Resume.created_at.desc())
                .limit(1)
            )
            resume = result2.scalar_one_or_none()
            if resume:
                resume.analysis_result = analysis
                resume.match_analysis = match_analysis
                resume.summary = synthesized.get("summary", "")
                from datetime import datetime
                resume.analyzed_at = datetime.utcnow()

            await db.commit()
            logger.info(
                "候选人 %s 分析结果已写库 (match_score=%.1f, source=%s, complete=%s, category=%s)",
                candidate_id, overall, scoring["source"], analysis_complete, category,
            )
        except Exception as e:
            await db.rollback()
            logger.error("候选人 %s 分析结果写库失败: %s", candidate_id, e)

    return {
        "analysis_result": analysis,
        "match_analysis": match_analysis,
        "match_score": overall,
        "analysis_complete": analysis_complete,
        "llm_overall_score": llm_overall,
        "score_diff": score_diff,
        "status": "analyzed",
        "pipeline_stage": "resume",
    }


def _to_float(value) -> Optional[float]:
    """安全转 float，失败返回 None"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- 工具函数 --

def _safe_json_parse(response: str) -> dict:
    """解析 LLM 返回的 JSON，如果格式不对用正则兜底"""
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        return json.loads(json_match.group()) if json_match else {}


# -- 向后兼容入口（旧代码直接调 analyze_node 也能用）--

async def analyze_node(state: RecruitmentState) -> dict:
    """兼容旧版调用，内部走一遍 3 Agent + 综合"""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", state.get("position", ""))

    basic = await analyze_basic_info_node({
        "resume_text": resume_text,
        "job_category": state.get("job_category", "python"),
        "job_description": job_desc,
    })
    skills = await analyze_skills_node({
        "resume_text": resume_text,
        "job_description": job_desc,
    })
    exp = await analyze_experience_node({
        "resume_text": resume_text,
        "job_description": job_desc,
    })

    merged = {**state, **basic, **skills, **exp}
    return await synthesize_analysis_node(merged)
