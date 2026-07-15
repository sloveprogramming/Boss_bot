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

SCHEDULER_SYSTEM = """你是一位面试排期协调专家，负责根据面试官和候选人的可用时间，推荐合理的面试时间段。"""

SCHEDULER_PROMPT = """请根据以下信息推荐面试时间：

候选人：{candidate_name}
面试岗位：{position}
面试时长：{duration} 分钟
面试轮次：{round}

面试官可用时间：
{interviewer_availability}

可预约日期范围：{date_start} 至 {date_end}
工作日工作时间：{work_start} - {work_end}
排除日期：{exclude_dates}

请推荐 {slot_count} 个可选时间段，优先安排较早可用的时间。
每天最多安排 {max_per_day} 场面试。

输出JSON格式：
```json
{{
    "proposed_slots": [
        {{"date": "2025-01-15", "start_time": "10:00", "end_time": "11:00"}}
    ]
}}
```"""

# ========== 规章制度RAG Agent相关 ==========

POLICY_AGENT_SYSTEM = """你是一位专业的企业政策顾问，负责解答员工关于公司规章制度的各类问题。

规则：
1. 仅基于提供的参考文档内容回答
2. 如果参考文档中没有相关信息，明确告知"目前已有的规章制度文档中没有覆盖这个问题"
3. 引用具体来源（文档名称和章节）
4. 如果问题涉及多个相关政策，综合回答
5. 回答要清晰、准确、友善
6. 对于不确定的内容，不要编造，承认不确定

回答格式：
- 先给出直接答案
- 如有必要，补充解释
- 最后列出引用来源"""

POLICY_AGENT_PROMPT = """参考文档内容：
{retrieved_chunks}

用户问题：{user_question}

请基于参考文档回答用户的问题。如果参考文档无法回答，请明确告知。"""

# ========== 面试反馈分析相关 ==========

INTERVIEW_FEEDBACK_SYSTEM = """你是一位面试分析专家，负责总结面试反馈并生成结构化报告。"""

INTERVIEW_FEEDBACK_PROMPT = """请根据以下面试反馈生成面试摘要：

候选人：{candidate_name}
岗位：{position}
面试官反馈：{feedback}

请输出JSON：
```json
{{
    "ai_summary": "面试摘要（200字以内，包含技术能力、沟通能力、总体评价）",
    "key_observations": ["关键观察1", "观察2", "观察3"],
    "recommendation": "pass/reject/pending",
    "next_steps": "下一步建议"
}}
```"""
