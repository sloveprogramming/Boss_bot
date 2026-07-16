"""所有LLM提示词模板 — 集中管理，便于维护和调优"""

# ========== 简历分析相关 ==========

RESUME_ANALYSIS_SYSTEM = """你是一位资深的AI招聘助手。你的任务是从简历文本中提取结构化信息，并进行分析。

请严格按照JSON格式输出。"""

RESUME_ANALYSIS_PROMPT = """请分析以下简历文本，提取结构化信息并输出JSON：

简历文本：
```
{resume_text}
```

岗位描述（用于匹配度分析）：
```
{job_description}
```

请输出以下JSON结构（不要包含其他文字）：
```json
{{
    "analysis": {{
        "basic_info": {{
            "name": "姓名（若未找到则为空字符串）",
            "phone": "电话",
            "email": "邮箱",
            "location": "所在地"
        }},
        "education": [
            {{"school": "学校", "degree": "学位/学历", "major": "专业", "start": "开始时间", "end": "结束时间"}}
        ],
        "work_experience": [
            {{"company": "公司", "position": "职位", "start": "开始时间", "end": "结束时间", "description": "工作描述"}}
        ],
        "skills": ["技能1", "技能2"],
        "projects": [
            {{"name": "项目名", "description": "描述", "technologies": ["技术栈"]}}
        ],
        "certifications": ["证书1"]
    }},
    "match_analysis": {{
        "overall_score": "总体匹配度0-100",
        "dimensions": {{
            "技能匹配": "技能匹配度0-100",
            "经验匹配": "经验匹配度0-100",
            "学历匹配": "学历匹配度0-100",
            "项目可信度": "项目可信度0-100",
            "实习时长": "实习时长匹配度0-100",
            "证书匹配": "证书匹配度0-100",
            "稳定性": "稳定性评估0-100",
            "行业背景": "行业背景匹配度0-100"
        }},
        "strengths": ["候选人优势1", "优势2", "优势3"],
        "risks": ["潜在风险/不足1", "风险2"],
        "recommended_questions": ["推荐面试问题1", "问题2", "问题3", "问题4", "问题5"]
    }},
    "summary": "一段简短的候选人总结（50字以内）"
}}
```

注意：
- 如果简历中没有明确的信息，不要编造，留空或不包含该字段
- 工作经历按时间倒序排列
- 评分要严格，不要虚高
- strengths和risks要具体，不要泛泛而谈
- recommended_questions要针对岗位和简历内容定制"""

# ========== 面试排期相关 ==========
# (以下 SCHEDULER_* 常量已废弃 — 排期功能改用算法引擎实现，LLM 仅做对话场景辅助)

# ========== 规章制度RAG Agent相关 ==========
# (以下 POLICY_AGENT_* 常量已迁移至 rag_service/app/agents/prompts.py — RAG 服务已独立拆分)

# ========== 面试反馈分析相关 ==========
# (以下 INTERVIEW_FEEDBACK_* 常量已废弃 — 功能未实现，预留位置)

# ========== 多 Agent 简历分析（并行版） ==========

BASIC_INFO_ANALYZER_SYSTEM = """你是一位简历信息提取专家。只负责从简历中提取基本信息（姓名、联系方式、学历等），不要评估技能或经验。"""
BASIC_INFO_ANALYZER_PROMPT = """从以下简历中提取基本信息，输出JSON：

简历文本：
```
{resume_text}
```

输出JSON：
```json
{{
    "name": "姓名",
    "phone": "电话",
    "email": "邮箱",
    "location": "所在地",
    "education": [
        {{"school": "学校", "degree": "学位", "major": "专业", "start": "开始时间", "end": "结束时间"}}
    ],
    "certifications": ["证书1"]
}}
```
注意：找不到的字段留空字符串。"""

SKILL_ANALYZER_SYSTEM = """你是一位技术能力评估专家。只负责评估候选人的技术栈与岗位要求的匹配度，不要评估经验和学历。"""
SKILL_ANALYZER_PROMPT = """评估候选人的技能与岗位要求的匹配度：

岗位描述：
```
{job_description}
```

简历文本：
```
{resume_text}
```

输出JSON：
```json
{{
    "skills": ["技能1", "技能2"],
    "skill_match_score": "技能匹配度0-100",
    "strengths": ["技能优势1", "优势2"],
    "gaps": ["技能缺口1", "缺口2"],
    "skill_summary": "技能评估摘要（30字以内）"
}}
```
注意：评分严格，不要虚高。"""

EXPERIENCE_ANALYZER_SYSTEM = """你是一位工作经验评估专家。只负责评估候选人的工作经历、项目经验和稳定性，不要评估技能。"""
EXPERIENCE_ANALYZER_PROMPT = """评估候选人的工作经历与岗位的匹配度：

岗位描述：
```
{job_description}
```

简历文本：
```
{resume_text}
```

输出JSON：
```json
{{
    "work_experience": [
        {{"company": "公司", "position": "职位", "duration": "时长", "description": "简述"}}
    ],
    "projects": [
        {{"name": "项目名", "technologies": ["技术栈"], "description": "简述"}}
    ],
    "experience_score": "经验匹配度0-100",
    "stability_score": "稳定性评估0-100",
    "highlights": ["亮点1", "亮点2"],
    "risks": ["风险点1"],
    "experience_summary": "经验评估摘要（30字以内）"
}}
```
注意：没有的信息不要编造。"""

SYNTHESIZE_ANALYSIS_SYSTEM = """你是一位综合评估专家。根据基本信息、技能、经验三个维度的独立评估结果，生成最终的综合评分和推荐面试问题。"""
SYNTHESIZE_ANALYSIS_PROMPT = """根据以下三个维度的独立评估结果，生成综合报告：

=== 基本信息 ===
{basic_info}

=== 技能评估 ===
{skills_eval}

=== 经验评估 ===
{experience_eval}

输出JSON：
```json
{{
    "overall_score": "综合评分0-100（加权：技能40% + 经验40% + 学历证书20%）",
    "dimensions": {{
        "技能匹配": "0-100",
        "经验匹配": "0-100",
        "学历匹配": "0-100",
        "项目可信度": "0-100",
        "稳定性": "0-100"
    }},
    "strengths": ["综合优势1", "优势2", "优势3"],
    "risks": ["综合风险1", "风险2"],
    "recommended_questions": ["推荐面试问题1", "问题2", "问题3", "问题4", "问题5"],
    "summary": "候选人综合评估（50字以内）"
}}
```
注意：综合评分要严格。"""

# ========== 多 Agent 面试评审（并行版） ==========

TECHNICAL_REVIEW_SYSTEM = """你是一位技术面试评审专家。根据面试反馈评估候选人的技术能力和架构思维。"""
TECHNICAL_REVIEW_PROMPT = """根据面试反馈评估技术能力：

候选人：{candidate_name}
岗位：{position}
面试反馈：{feedback}

输出JSON：
```json
{{
    "technical_score": "技术评分0-100",
    "coding_ability": "编码能力评估",
    "architecture_thinking": "架构思维能力评估",
    "problem_solving": "问题解决能力评估",
    "strengths": ["技术优势1", "优势2"],
    "concerns": ["技术疑虑1"],
    "verdict": "pass/reject/pending",
    "summary": "技术评审摘要（30字以内）"
}}
```"""

COMMUNICATION_REVIEW_SYSTEM = """你是一位沟通能力评审专家。根据面试反馈评估候选人的表达清晰度、逻辑思维和协作能力。"""
COMMUNICATION_REVIEW_PROMPT = """根据面试反馈评估沟通能力：

候选人：{candidate_name}
岗位：{position}
面试反馈：{feedback}

输出JSON：
```json
{{
    "communication_score": "沟通评分0-100",
    "clarity": "表达清晰度评估",
    "logic": "逻辑思维能力评估",
    "collaboration": "团队协作意识评估",
    "strengths": ["沟通优势1", "优势2"],
    "concerns": ["沟通疑虑1"],
    "verdict": "pass/reject/pending",
    "summary": "沟通评审摘要（30字以内）"
}}
```"""

CULTURE_REVIEW_SYSTEM = """你是一位文化匹配度评审专家。根据面试反馈评估候选人与公司文化的契合度。"""
CULTURE_REVIEW_PROMPT = """根据面试反馈评估文化匹配度：

候选人：{candidate_name}
岗位：{position}
面试反馈：{feedback}

输出JSON：
```json
{{
    "culture_score": "文化匹配度0-100",
    "values_alignment": "价值观匹配评估",
    "growth_mindset": "成长心态评估",
    "team_fit": "团队融入评估",
    "strengths": ["文化优势1", "优势2"],
    "concerns": ["文化疑虑1"],
    "verdict": "pass/reject/pending",
    "summary": "文化评审摘要（30字以内）"
}}
```"""

SUPERVISOR_DECISION_SYSTEM = """你是一位招聘决策主管。综合技术、沟通、文化三个维度的独立评审结果，做出最终录用决策。"""
SUPERVISOR_DECISION_PROMPT = """综合以下三个维度的评审，做出最终决策：

=== 技术评审 ===
{technical_review}

=== 沟通评审 ===
{communication_review}

=== 文化评审 ===
{culture_review}

候选人：{candidate_name}
岗位：{position}
简历匹配分：{match_score}

输出JSON：
```json
{{
    "final_decision": "pass/reject/pending",
    "confidence": "高/中/低",
    "reason": "决策理由（100字以内）",
    "risk_warning": "需要关注的风险点（如有，否则为空）",
    "suggested_salary_range": "建议薪资范围（可选，如无则留空）"
}}
```
决策规则：
- 三个维度都 pass → pass
- 两个 pass + 一个 pending → pass（带 risk_warning）
- 一个 reject → pending（除非另两个都很强才 pass）
- 两个 reject → reject"""
