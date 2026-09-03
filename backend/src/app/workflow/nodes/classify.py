"""岗位分类节点调独立 Classifier Agent → 或 → 用内联关键词+LLM 分类"""
import logging
from ..state import RecruitmentState
from ..agent_client import agent_client
from app.database import async_session_factory
from app.models import Candidate

logger = logging.getLogger(__name__)


async def classify_node(state: RecruitmentState) -> dict:
    """判断候选人岗位类别"""
    resume_text = state.get("resume_text", "") # 候选人简历文本
    position = state.get("position", "") # 岗位描述
    candidate_id = state.get("candidate_id") # 候选人ID

    # 调用独立 Classifier Agent（主分类器）
    agent_result = await agent_client.classify(resume_text, position)
    # 判断是否成功获取分类结果
    if agent_result:
        # 主分类器分类成功
        category = agent_result.get("category", "python")
        # 主分类器置信度
        confidence = agent_result.get("confidence", 0.7)
        source = "agent"
    else:
        # 降级：使用自己设置的分类关键词分类
        category, confidence = _inline_classify(resume_text, position)
        source = "inline"

    # 写入数据库
    async with async_session_factory() as db:
        try:
            from sqlalchemy import select
            # 从数据库查询候选人
            # 如果候选人不存在，跳过
            result = await db.execute(
                select(Candidate).where(Candidate.id == candidate_id)
            )
            # 这个地方如果不清楚candidate中包含了哪些字段可以问一下ai，或者查一下数据库
            candidate = result.scalar_one_or_none()
            # 如果候选人存在，更新分类结果
            if candidate:
                # 更新分类结果
                candidate.job_category = category
                # 更新分类置信度
                candidate.category_confidence = confidence
                # 更新状态为已分类
                candidate.status = "classified"
                # 提交事务
                await db.commit()
            logger.info(
                "候选人 %s 岗位分类完成: %s (confidence=%.2f, source=%s)",
                candidate_id, category, confidence, source,
            )
        except Exception as e:
            await db.rollback()
            logger.error("候选人 %s 岗位分类写库失败: %s", candidate_id, e)

    return {
        "job_category": category, # 岗位分类
        "category_confidence": confidence, # 分类置信度
        "status": "classified", # 状态
        "pipeline_stage": "resume",
    }


def _inline_classify(resume_text: str, position: str) -> tuple:
    """内联关键词分类（兜底方案，同 Classifier Agent 逻辑）"""
    SUBJECT_KEYWORDS = {
        "python": ["python", "django", "flask", "fastapi", "pandas", "numpy", "celery", "sqlalchemy"],
        "java": ["java", "spring", "springboot", "mybatis", "jvm", "微服务", "kafka"],
        "product": ["产品经理", "产品设计", "axure", "需求分析", "prd", "数据分析"],
        "ai": ["机器学习", "深度学习", "神经网络", "大模型", "llm", "nlp", "pytorch"],
        "frontend": ["前端", "react", "vue", "angular", "typescript", "javascript", "css"],
        "ops": ["运维", "devops", "docker", "kubernetes", "k8s", "linux", "ci/cd"],
        "test": ["测试", "自动化测试", "selenium", "junit", "pytest", "接口测试", "性能测试"],
        "erp": ["erp", "sap", "oracle", "用友", "金蝶", "crm", "供应链"],
        "外贸运营": ["外贸", "跨境", "亚马逊", "速卖通", "shopify", "独立站"],
        "数据分析": ["数据分析", "数据挖掘", "bi", "sql", "tableau", "powerbi", "etl"],
        "项目管理": ["项目经理", "pmp", "敏捷开发", "scrum", "jira", "项目管理"],
        "销售": ["销售", "客户经理", "bd", "商务拓展", "大客户", "售前"],
        "人力资源": ["hr", "人力资源", "招聘", "培训", "薪酬", "绩效", "hrbp"],
        "运营": ["运营", "用户运营", "内容运营", "社群运营", "新媒体", "公众号", "短视频"],
        "财务": ["财务", "会计", "出纳", "审计", "税务", "cpa", "财务报表"],
        "法务": ["法务", "律师", "合同", "合规", "知识产权", "诉讼"],
        # ---- 2026-09 按在招岗位价值说明书新增 ----
        "市场主管": ["市场主管", "市场经理", "市场营销", "市场推广", "市场策划", "品牌推广", "竞品分析"],
        "采购主管": ["采购主管", "采购经理", "采购", "供应商管理", "供应链管理", "寻源", "商务谈判"],
        "食品研发工程师": ["食品研发", "研发工程师", "配方师", "食品工程师", "风味", "感官评价", "流变", "质构"],
        "销售内勤": ["销售内勤", "销售助理", "销售支持", "内勤", "订单处理", "开票"],
        "城市经理": ["城市经理", "区域经理", "渠道经理", "区域销售", "动销", "铺货"],
        "大宗贸易销售": ["大宗贸易", "大宗商品", "贸易销售", "原料销售"],
        "俄语外贸业务员": ["俄语", "俄语外贸", "俄语业务", "俄语市场", "俄罗斯"],
        "英语翻译（总秘）": ["英语翻译", "总秘", "董事长秘书", "翻译", "雅思", "商务英语"],
        "电商运营经理": ["电商运营经理", "电商负责人", "品类运营", "运营总监", "电商总监"],
        "电商资深运营": ["电商运营", "京东运营", "天猫运营", "店铺运营", "资深运营", "万相台", "直通车", "淘客"],
        "视频号商务BD": ["视频号", "达人", "商务bd", "直播bd", "主播", "带货"],
    }

    text_lower = f"{position} {resume_text[:2000]}".lower()
    scores = {}
    for cat, keywords in SUBJECT_KEYWORDS.items():
        # 长关键词（>=4字，如"电商运营经理"）计 2 分：具体类别应压过宽泛类别（如"运营"）
        scores[cat] = sum(2 if len(kw) >= 4 else 1
                          for kw in keywords if kw.lower() in text_lower)

    best = max(scores, key=scores.get)
    return best, scores[best] / 5.0 if max(scores.values()) else 0.5
