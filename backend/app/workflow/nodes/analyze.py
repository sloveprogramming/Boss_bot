"""简历分析节点 — 3 个 Agent 并行分析 + 综合汇总

classify 之后拆成 3 路并行（基本信息、技能、经验），LangGraph 自动等 3 路都跑完
再走 synthesize 综合打分。比原来单链快，而且每个 Agent 只管一件事，prompt 更精准。
"""
import json
import re
from ..state import RecruitmentState
from ..agent_client import agent_client
from app.database import async_session_factory
from app.agents import llm_client
from app.agents.prompts import (
    BASIC_INFO_ANALYZER_SYSTEM, BASIC_INFO_ANALYZER_PROMPT,
    SKILL_ANALYZER_SYSTEM, SKILL_ANALYZER_PROMPT,
    EXPERIENCE_ANALYZER_SYSTEM, EXPERIENCE_ANALYZER_PROMPT,
    SYNTHESIZE_ANALYSIS_SYSTEM, SYNTHESIZE_ANALYSIS_PROMPT,
)
from langgraph.types import Send


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
    return {"basic_info_analysis": data}


async def analyze_skills_node(state: RecruitmentState) -> dict:
    """评估技术栈与岗位的匹配度"""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", state.get("position", ""))

    prompt = SKILL_ANALYZER_PROMPT.format(
        resume_text=resume_text[:15000],
        job_description=job_desc or "通用岗位",
    )
    response = await llm_client.chat(
        system=SKILL_ANALYZER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.15,
        max_tokens=1024,
    )
    data = _safe_json_parse(response)
    data["source"] = "inline"
    return {"skills_analysis": data}


async def analyze_experience_node(state: RecruitmentState) -> dict:
    """评估工作经历、项目经验和稳定性"""
    resume_text = state.get("resume_text", "")
    job_desc = state.get("job_description", state.get("position", ""))

    prompt = EXPERIENCE_ANALYZER_PROMPT.format(
        resume_text=resume_text[:15000],
        job_description=job_desc or "通用岗位",
    )
    response = await llm_client.chat(
        system=EXPERIENCE_ANALYZER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.15,
        max_tokens=1536,
    )
    data = _safe_json_parse(response)
    data["source"] = "inline"
    return {"experience_analysis": data}


async def synthesize_analysis_node(state: RecruitmentState) -> dict:
    """汇总 3 个子 Agent 的结果 → 综合评分 → 写库"""
    basic = state.get("basic_info_analysis", {})
    skills = state.get("skills_analysis", {})
    experience = state.get("experience_analysis", {})
    candidate_id = state.get("candidate_id")
    category = state.get("job_category", "python")

    # 综合打分
    prompt = SYNTHESIZE_ANALYSIS_PROMPT.format(
        basic_info=json.dumps(basic, ensure_ascii=False),
        skills_eval=json.dumps(skills, ensure_ascii=False),
        experience_eval=json.dumps(experience, ensure_ascii=False),
    )
    response = await llm_client.chat(
        system=SYNTHESIZE_ANALYSIS_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=2048,
    )
    synthesized = _safe_json_parse(response)

    # 加权算分：技能 40% + 经验 40% + 稳定性 20%
    skill_score = skills.get("skill_match_score", 50)
    experience_score = experience.get("experience_score", 50)
    stability_score = experience.get("stability_score", 50)
    try:
        overall = float(skill_score) * 0.4 + float(experience_score) * 0.4 + float(stability_score) * 0.2
    except (ValueError, TypeError):
        overall = synthesized.get("overall_score", 50)

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
        except Exception:
            await db.rollback()

    return {
        "analysis_result": analysis,
        "match_analysis": match_analysis,
        "match_score": overall,
        "status": "analyzed",
        "pipeline_stage": "resume",
    }


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
