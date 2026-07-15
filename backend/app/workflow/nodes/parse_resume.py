"""简历解析节点 — 招聘流程的第一个自动化步骤"""

from ..state import RecruitmentState  # 工作流全局状态定义
from ..agent_client import agent_client  # 外部 Agent 微服务调用客户端（备用）
from app.database import async_session_factory  # 异步数据库会话工厂
from app.services.resume_analyzer import resume_analyzer  # 简历分析服务实例（备用）


async def parse_resume_node(state: RecruitmentState) -> dict:
    """解析简历文件为文本，校验并更新候选人状态到数据库"""
    resume_text = state.get("resume_text", "")  # 从工作流状态中取出简历原始文本
    candidate_id = state.get("candidate_id")  # 取出当前候选人 ID

    if not resume_text:  # 防御：简历文本为空则中断流程
        return {
            "status": "new",  # 回退状态，表示简历尚未解析
            "pipeline_stage": "resume",  # 停留当前阶段
            "errors": ["请先上传简历文件"],  # 反馈错误信息给前端
        }

    # 写入数据库：将候选人状态标记为"已解析"
    async with async_session_factory() as db:  # 获取异步数据库会话
        try:
            from sqlalchemy import select  # 延迟导入，避免循环依赖
            from app.models.candidate import Candidate  # 候选人 ORM 模型

            result = await db.execute(  # 执行查询
                select(Candidate).where(Candidate.id == candidate_id)
            )
            candidate = result.scalar_one_or_none()  # 取唯一结果，不存在则返回 None
            if candidate:
                candidate.status = "parsed"  # 标记候选人状态为已解析
                await db.commit()  # 提交事务
        except Exception as e:
            await db.rollback()  # 异常时回滚事务
            return {
                "status": "new",  # 回退状态
                "errors": [f"数据库更新失败: {str(e)}"],  # 携带具体错误信息
            }

    return {
        "status": "parsed",  # 解析成功
        "pipeline_stage": "resume",  # 当前阶段
        "resume_text": resume_text,  # 透传简历文本，供下游节点使用
    }