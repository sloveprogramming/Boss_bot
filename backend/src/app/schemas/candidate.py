"""候选人与人才池相关Pydantic Schema（数据校验与序列化）"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class CandidateCreate(BaseModel):
    """创建候选人的请求体"""
    name: str                          # 姓名（必填）
    phone: Optional[str] = None        # 电话
    email: Optional[str] = None        # 邮箱
    position: str                      # 应聘岗位（必填）
    source: str = "manual"             # 来源：manual(手动)/boss(直聘)/linkedin/referral(内推)
    source_url: Optional[str] = None   # 外部来源URL
    experience_years: Optional[float] = None  # 工作年限
    tags: List[str] = []               # 技能标签列表
    owner_user_id: Optional[int] = None  # 负责人HR id（仅 admin 指派有效；HR 建默认自己，忽略传入）


class CandidateOwnerUpdate(BaseModel):
    """改派候选人负责人的请求体（仅 admin 可操作）"""
    owner_user_id: int                 # 新负责人用户 id（须为存在且启用的 admin/hr）


class CandidateUpdate(BaseModel):
    """更新候选人信息的请求体（全部可选）"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    position: Optional[str] = None
    status: Optional[str] = None           # 更新状态
    match_score: Optional[float] = None    # 更新匹配分
    tags: Optional[List[str]] = None       # 更新标签
    experience_years: Optional[float] = None
    job_category: Optional[str] = None     # 岗位分类


class CandidateResponse(BaseModel):
    """候选人信息响应体"""
    id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str
    position: str
    experience_years: Optional[float] = None
    job_category: Optional[str] = None
    status: str
    match_score: Optional[float] = None
    tags: List[str] = []
    talent_pool_id: Optional[int] = None
    talent_pool_reason: Optional[str] = None
    owner_user_id: Optional[int] = None  # 负责人HR用户id
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}  # 允许从ORM模型实例化


class CandidateListResponse(BaseModel):
    """候选人列表响应体（含分页）"""
    total: int                       # 总记录数
    items: List[CandidateResponse]   # 候选人列表
    page: int                        # 当前页码
    page_size: int                   # 每页条数


class TalentPoolResponse(BaseModel):
    """人才池记录响应体"""
    id: int
    candidate_id: int
    original_position: str
    match_score: Optional[float] = None
    strengths: List[str] = []
    risks: List[str] = []
    pool_reason: Optional[str] = None
    suitable_positions: List[str] = []
    skills: List[str] = []
    status: str
    reactivated_at: Optional[datetime] = None
    reactivated_for: Optional[str] = None
    contacted_at: Optional[datetime] = None
    contact_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TalentPoolListResponse(BaseModel):
    """人才池列表响应体（含分页）"""
    total: int
    items: List[TalentPoolResponse]
    page: int
    page_size: int


class ReactivateRequest(BaseModel):
    """从人才池重新激活的请求体"""
    talent_pool_id: int    # 人才池记录ID
    position: str          # 重新激活后应聘的岗位


class TalentPoolCreateRequest(BaseModel):
    """从工作流自动创建人才池记录的请求体"""
    candidate_id: int
    position: str
    match_score: Optional[float] = None
