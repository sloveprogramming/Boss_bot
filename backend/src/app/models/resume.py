# ═══════════════════════════════════════════════════════════════
# 【小白导读】简历表（resumes）——一位候选人可有多份简历，candidate_id 外键多对一关联。
#   · raw_text：从 PDF/Word 提取的纯文本；analysis_result：JSON 列存 AI 结构化分析结果。
#   · JSON 列的好处：字段结构不固定也能直接存，取出来就是 Python dict。
# ═══════════════════════════════════════════════════════════════
"""简历模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey
from app.database import Base


class Resume(Base):
    """简历ORM模型，对应数据库resumes表"""
    __tablename__ = "resumes"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    # 外键：关联到候选人表
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)

    # 原始文件信息
    original_filename = Column(String(500), nullable=True)  # 原始文件名
    file_path = Column(String(1000), nullable=True)          # 文件存储路径
    file_type = Column(String(10), nullable=True)            # 文件类型：pdf, docx, txt

    # 解析后的原始文本内容
    raw_text = Column(Text, nullable=True)

    # LLM分析结果（JSON格式存储结构化信息）
    analysis_result = Column(JSON, nullable=True, default=None)
    """JSON结构示例:
    {
        "basic_info": {"name": "...", "phone": "...", "email": "...", "location": "..."},
        "education": [{"school": "...", "degree": "...", "major": "...", "start": "...", "end": "..."}],
        "work_experience": [{"company": "...", "position": "...", "start": "...", "end": "...", "description": "..."}],
        "skills": ["Python", "..."],
        "projects": [{"name": "...", "description": "...", "technologies": [...]}],
        "certifications": [...]
    }
    """

    # 岗位匹配度分析结果（JSON格式）
    match_analysis = Column(JSON, nullable=True, default=None)
    """JSON结构示例:
    {
        "overall_score": 85,
        "dimensions": {"skills_match": 90, "experience_match": 80, "education_match": 100},
        "strengths": ["...", "..."],
        "risks": ["...", "..."],
        "recommended_questions": ["...", "..."]
    }
    """

    # AI生成的简短候选人总结
    summary = Column(Text, nullable=True)

    # 分析时间戳
    analyzed_at = Column(DateTime, nullable=True)       # 分析完成时间
    created_at = Column(DateTime, default=datetime.utcnow)  # 记录创建时间
