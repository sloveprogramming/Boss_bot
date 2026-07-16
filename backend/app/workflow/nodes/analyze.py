"""简历分析节点 — LLM 结构化提取 + 8 维度匹配度评分

先尝试调用独立 Analyzer Agent（HTTP），不可用时降级为内联 LLM 分析。
分析结果写回 Candidate 和 Resume 表。
"""
from ..state import RecruitmentState                                # 流程状态对象
from ..agent_client import agent_client                            # Agent HTTP 客户端（可降级）
from app.database import async_session_factory                     # 异步数据库会话工厂
from app.agents import llm_client, RESUME_ANALYSIS_SYSTEM, RESUME_ANALYSIS_PROMPT  # 全局 LLM 客户端 + 提示词


async def analyze_node(state: RecruitmentState) -> dict:
    """分析简历 — 从 State 取简历文本和岗位描述 → LLM 打分 → 写入数据库"""
    resume_text = state.get("resume_text", "")                     # 候选人的简历原文
    job_desc = state.get("job_description", state.get("position", ""))  # 岗位描述（没传就用职位名）
    category = state.get("job_category", "python")                 # 上一步分类出的岗位类别
    candidate_id = state.get("candidate_id")                       # 候选人 ID

    agent_result = await agent_client.analyze(category, resume_text, job_desc)
    if agent_result:  # Agent 可用，直接用远程结果
        match = agent_result.get("match_analysis", {})             # 匹配度详细分析
        analysis = agent_result.get("analysis", {})                # 结构化提取结果
        score = match.get("overall_score", 50)                     # 总体匹配分（默认 50）
    else:
        analysis, match, score = await _inline_analyze(resume_text, job_desc)

    # 步骤 2：将分析结果写回数据库
    async with async_session_factory() as db:                      # 创建独立数据库会话
        try:
            from sqlalchemy import select
            from app.models import Resume

            # 更新候选人记录：匹配分、类别、状态
            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()
            if candidate:                                           # 候选人存在则更新
                candidate.match_score = score                       # 写入总体匹配分
                candidate.job_category = category                   # 写入岗位类别
                candidate.status = "analyzed"                       # 状态流转到"已分析"

                if analysis:
                    basic = analysis.get("basic_info", {})          # 姓名/电话/邮箱
                    skills = analysis.get("skills", [])             # 技能列表
                    if basic.get("name") and not candidate.name:    # 简历中提取到姓名且数据库没有
                        candidate.name = basic["name"]
                    if basic.get("phone") and not candidate.phone:  # 简历中提取到电话
                        candidate.phone = basic.get("phone")
                    if basic.get("email") and not candidate.email:  # 简历中提取到邮箱
                        candidate.email = basic.get("email")
                    if skills:                                      # 合并技能标签（去重，最多 10 个）
                        candidate.tags = list(set((candidate.tags or []) + skills[:10]))

            result2 = await db.execute(
                select(Resume)
                .where(Resume.candidate_id == candidate_id)
                .order_by(Resume.created_at.desc())
                .limit(1)
            )
            resume = result2.scalar_one_or_none()
            if resume:                                              # 简历存在则写入分析
                resume.analysis_result = analysis                   # 结构化提取的 JSON
                resume.match_analysis = match                       # 8 维度匹配度 + 优势/风险
                resume.summary = analysis.get("summary", "") if isinstance(analysis, dict) else ""
                from datetime import datetime
                resume.analyzed_at = datetime.utcnow()              # 记录分析时间

            await db.commit()                                       # 提交事务
        except Exception:
            await db.rollback()                                     # 出错回滚，不阻塞流程

    return {
        "analysis_result": analysis,                                # 结构化提取
        "match_analysis": match,                                    # 匹配度详细分析
        "match_score": score,                                       # 总体分数（0-100）
        "status": "analyzed",                                       # 新状态
        "pipeline_stage": "resume",
    }


async def _inline_analyze(resume_text: str, job_description: str) -> tuple:
    """内联 LLM 分析 — 降级方案，直接调 DeepSeek 打分"""
    import json                                                    # 用于解析 LLM 返回的 JSON
    import re                                                      # 正则提取 JSON（容错）

    truncated = resume_text[:15000]                                # LLM 上下文有限，截断到 15000 字
    prompt = RESUME_ANALYSIS_PROMPT.format(                        # 填模板：简历文本 + 岗位描述
        resume_text=truncated,
        job_description=job_description or "通用岗位",
    )

    response = await llm_client.chat(
        system=RESUME_ANALYSIS_SYSTEM,                             # 系统提示："你是资深AI招聘助手"
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},                   # 强制 JSON 输出
        temperature=0.2,                                           # 低温度 → 稳定输出
        max_tokens=4096,
    )

    try:
        data = json.loads(response)                                # 正常解析
    except json.JSONDecodeError:                                   # JSON 格式不对
        json_match = re.search(r'\{.*\}', response, re.DOTALL)    # 用正则提取 {...} 部分
        data = json.loads(json_match.group()) if json_match else {}

    analysis = data.get("analysis", {})                            # 结构化信息
    match_analysis = data.get("match_analysis", {})                # 匹配度分析
    score = match_analysis.get("overall_score", 50)                # 总体分，默认 50

    if isinstance(analysis, dict) and "summary" not in analysis:
        analysis["summary"] = data.get("summary", "")              # 补上摘要

    return analysis, match_analysis, score                         # 返回三元组
