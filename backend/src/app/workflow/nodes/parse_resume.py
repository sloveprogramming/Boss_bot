"""简历解析节点 — 招聘流程的第一个自动化步骤"""
import logging
from ..state import RecruitmentState
from ..agent_client import agent_client
from ..utils import candidate_session
from app.services import resume_analyzer

logger = logging.getLogger(__name__)


async def parse_resume_node(state: RecruitmentState) -> dict:
    """解析简历文件为文本，校验并更新候选人状态到数据库"""
    resume_text = state.get("resume_text", "")
    candidate_id = state.get("candidate_id")

    if not resume_text:
        logger.warning("候选人 %s 无简历文本，流程回退到 new 状态", candidate_id)
        return {
            "status": "new",  # 回退状态，表示简历尚未解析
            "pipeline_stage": "resume",  # 停留当前阶段
            "errors": ["请先上传简历文件"],  # 反馈错误信息给前端
        }

    try:
        async with candidate_session(candidate_id) as (db, candidate):
            if candidate:
                candidate.status = "parsed"
        logger.info("候选人 %s 简历解析完成，状态 -> parsed", candidate_id)
    except Exception as e:
        logger.error("候选人 %s 简历解析时更新数据库失败: %s", candidate_id, e)
        return {
            "status": "new",
            "errors": [f"数据库更新失败: {str(e)}"],
        }

    return {
        "status": "parsed",  # 解析成功
        "pipeline_stage": "resume",  # 当前阶段
        "resume_text": resume_text,  # 透传简历文本，供下游节点使用
    }
