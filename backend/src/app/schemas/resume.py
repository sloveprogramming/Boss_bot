"""简历相关Pydantic Schema"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ResumeUploadResponse(BaseModel):
    """简历上传成功的响应体"""
    id: int
    candidate_id: int
    original_filename: str
    status: str = "uploaded"
    message: str = "简历上传成功，正在分析中..."


class ResumeAnalysisResult(BaseModel):
    """简历AI分析结果的数据结构"""
    basic_info: dict = {}              # 基本信息（姓名、电话、邮箱、所在地）
    education: List[dict] = []          # 教育经历
    work_experience: List[dict] = []    # 工作经历
    skills: List[str] = []             # 技能列表
    projects: List[dict] = []          # 项目经历
    certifications: List[str] = []     # 证书列表


class MatchAnalysis(BaseModel):
    """岗位匹配度分析的数据结构"""
    overall_score: float               # 总体匹配度分数（0-100）
    dimensions: dict = {}              # 各维度评分
    strengths: List[str] = []          # 候选人优势
    risks: List[str] = []              # 潜在风险/不足
    recommended_questions: List[str] = []  # 建议的面试问题


class ResumeAnalysisResponse(BaseModel):
    """简历分析结果的响应体"""
    id: int
    candidate_id: int
    candidate_name: str = ""
    original_filename: Optional[str] = None
    analysis: Optional[ResumeAnalysisResult] = None      # 结构化信息提取结果
    match_analysis: Optional[MatchAnalysis] = None       # 匹配度分析结果
    summary: Optional[str] = None                        # AI总结
    analyzed_at: Optional[datetime] = None               # 分析时间

    model_config = {"from_attributes": True}


class ResumeAnalysisRequest(BaseModel):
    """发起简历分析的请求体"""
    candidate_id: int        # 候选人ID
    job_description: str = ""  # 岗位描述（用于匹配度分析）
