"""RecruitmentState — LangGraph 全程共用的状态对象

【小白导读】可以把 RecruitmentState 想象成一张"候选人审批流转单"：
    工作流里的每个节点（解析简历、AI 分析、分流、排面试……）都拿着同一张单子，
    处理完自己在上面填几个字段，再把单子传给下一个节点。
    本文件只定义"单子上有哪些栏位"（数据结构），不含任何业务逻辑。

LangGraph 三句话入门：
1. 一条招聘流水线 = 一个"图"（graph.py），流水线上每个工位 = 一个"节点"（nodes/ 目录）。
2. 节点之间传递的就是这里定义的 State 字典。
3. 每个节点函数的返回值是一个 dict，LangGraph 自动把它 merge（合并）回 State，
   所以下一个节点立刻能看到上一个节点写了什么。

为什么用 TypedDict 而不是普通 dict？
    TypedDict 只是"带类型标注的 dict"，运行时和 dict 完全一样，
    好处是 IDE 能自动提示字段名、拼错字段会有黄色警告。
    total=False 表示所有字段都是可选的——毕竟刚进流水线时大部分栏位还是空的。

多 Agent 并行的关键：
    "3 路并行分析"会同时跑 3 个节点，它们各自只写自己专属的 key
    （basic_info_analysis / skills_analysis / experience_analysis），
    互不覆盖；最后由汇总节点 synthesize_analysis_node 读取三者合并出总分。
"""
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph.message import add_messages


class RecruitmentState(TypedDict, total=False):

    # ============ 候选人基本信息（进入流水线时由 routers/workflow.py 填入）============
    candidate_id: int                # 候选人在数据库里的主键，后续所有写库操作都靠它定位
    candidate_name: str              # 姓名（组装 LLM 提示词时用）
    position: str                    # 应聘岗位（决定评分权重、JD 匹配标准）
    email: str                       # 邮箱（发面试邀请、问卷链接用）
    phone: Optional[str]             # 手机号

    # ============ 流程定位：现在走到哪一步了 ============
    status: str          # 状态机：new → parsed → classified → analyzed → ... → hired/rejected
    pipeline_stage: str  # 大阶段：resume(简历) / questionnaire(问卷) / interview(面试) / decision(决策)

    # ============ 简历 ============
    resume_text: Optional[str]        # 从 PDF/Word 提取出来的纯文本（解析节点的产物）
    job_description: Optional[str]    # 该岗位的 JD，用来和简历做匹配度对比

    # ============ 岗位分类 ============
    job_category: Optional[str]        # 岗位类别（如 销售/研发/运营），决定用哪套评分权重
    category_confidence: Optional[float]  # 分类置信度 0~1，太低说明 LLM 也不确定

    # ============ AI 分析结果（3 个子 Agent 产物 + 综合）============
    analysis_result: Optional[dict]             # 汇总后的完整分析 JSON（会存进 resume 表）
    match_analysis: Optional[dict]              # 与 JD 的匹配分析
    match_score: Optional[float]                # 最终匹配总分 0~100（分流就按它判定）
    basic_info_analysis: Optional[dict]         # 子 Agent 1：基本信息核验（姓名/联系方式/学历真实性）
    skills_analysis: Optional[dict]             # 子 Agent 2：技能分析（含 skill_match_score 维度分）
    experience_analysis: Optional[dict]         # 子 Agent 3：经验分析（含 experience_score、stability_score）

    # ============ 评分体系 v2（维度分派生总分 + 双通道留痕）============
    # 设计思想：LLM 只负责给"维度分"（有客观证据支撑），总分由 scoring.py 按权重算出来。
    # 这样调权重不用重新花钱跑 LLM，历史候选人也能批量重算。
    analysis_complete: Optional[bool]    # 维度分是否齐全；False 时不自动分流，转人工复核
    llm_overall_score: Optional[float]   # LLM 综合重评分（通道B，只记录不生效）
    score_diff: Optional[float]          # |加权分 - LLM重评分|，观察期攒数据定阈值

    # ============ 问卷（走问卷通道时才有值）============
    questionnaire_id: Optional[int]        # 问卷记录的数据库 ID
    questionnaire_status: Optional[str]    # sent / completed / expired
    questionnaire_score: Optional[float]   # AI 批卷总分
    questionnaire_passed: Optional[bool]   # 是否达到及格线（60 分）

    # ============ 面试 ============
    interview_id: Optional[int]           # 面试记录的数据库 ID
    interview_status: Optional[str]       # 见 models/interview.py 的状态枚举
    interview_decision: Optional[str]     # 面试最终结论：pass / reject
    interview_feedback: Optional[str]     # 面试官反馈原文（评审节点的输入）

    # ============ 面试评审（3 路并行评审 + supervisor 决策）============
    technical_review: Optional[dict]      # 评审 Agent 1：技术能力
    communication_review: Optional[dict]  # 评审 Agent 2：沟通表达
    culture_review: Optional[dict]        # 评审 Agent 3：文化匹配
    review_results: Optional[dict]        # 三路汇总
    decision_reason: Optional[str]        # supervisor 给出的录用/拒绝理由
    decision_confidence: Optional[str]    # 决策置信度（high / medium / low）
    risk_warning: Optional[str]           # 风险提示（如"频繁跳槽""技能与岗位不符"）

    # ============ Function Calling（自然语言查库/发邮件等工具调用）============
    fc_query: Optional[str]        # 用户的自然语言指令，如"查一下上周面试通过的人"
    fc_result: Optional[str]       # 工具执行结果（转成文字）
    fc_tool_calls: Optional[list]  # LLM 决定调用哪些工具的原始记录
    fc_response: Optional[str]     # LLM 基于工具结果生成的最终回答

    # ============ 流程控制 ============
    errors: List[str]                   # 流程中累积的错误信息（不中断流程，最后统一上报）
    retry_count: int                    # 当前节点的重试次数
    notifications_sent: List[str]       # 已发过哪些通知（防重复发送）

    # ============ LangGraph 内置 ============
    # messages 用 Annotated+add_messages 声明"追加式合并"：
    # 普通字段是"覆盖式合并"（新值替换旧值），而 messages 是"追加式"（新消息接到末尾），
    # 这是 LangGraph 管理多轮对话记录的标准写法。
    messages: Annotated[list, add_messages]
