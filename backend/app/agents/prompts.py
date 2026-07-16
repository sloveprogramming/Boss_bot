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
