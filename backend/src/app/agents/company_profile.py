"""公司档案 —— 【人工维护常量】⚠️⚠️

⚠️⚠️ 本文件是唯一"公司事实"来源，必须由招聘方/HR 人工维护。
    严禁从候选人、岗位、简历等动态数据自动推断后写死（会随数据漂移失真）。
    公司名留空 = LLM 不写公司名。
    标注 [待核实] 的行仅为占位示例，上线前请逐条人工确认。

    消费方：JD 生成器（routers/jd_generator.py）、JD 全网参考服务
    （services/jd_reference_service.py）、MCP 工具（mcp/tools/jd_reference.py）。
    agents/ 不反向依赖 routers/mcp/services，可被任一端安全 import，无循环风险。
"""
from __future__ import annotations


# 公司名称 —— 留空则提示 LLM 不写公司名
COMPANY_NAME: str = ""          # 例："XX食品科技有限公司"

# 3-5 句第一人称简介，用于 JD 开篇"我们是谁"
COMPANY_BRIEF: str = ""

# [待核实] 依据在招岗位类型反推的行业/业务线草稿 —— 仅占位，务必人工核对后再启用
INDUSTRY_TAG: str = ""          # 例："烘焙/食品原料"

# [待核实] 主要业务线 —— 默认全注释，人工确认后取消注释
BUSINESS_LINES: list[str] = [
    # "坚果等烘焙/食品原料的大宗贸易与供应链",
    # "烘焙酱料/馅料/风味糖浆的研发与生产",
    # "自有品牌坚果/休闲食品的电商零售（天猫/京东/视频号等）",
    # "华东区域烘焙饼店/商超/便利店渠道分销",
    # "俄语区等海外市场外贸出口",
]

# JD 通用适配偏好（人工维护）
JD_STYLE_PREFERENCES: dict = {
    "lang": "zh-CN",
    "tone": "简洁专业、突出结果导向、少空洞套话",
    "sections": ["## 岗位职责", "## 任职要求", "## 加分项", "## 薪资福利"],
    "duties_range": '岗位职责5-8条，任职要求4-7条，加分项2-4条，每条以"- "开头',
}

# 合规红线（《就业促进法》反歧视）—— 普通 JD 与"参考全网"JD 共用同一份。
# 文本与 jd_generator 原 JD_SYSTEM_PROMPT 中红线部分保持一致。
JD_COMPLIANCE_REDLINES = """合规红线（最高优先级，违反即输出无效）：
- 不得出现性别、年龄、婚育状况、户籍/地域、民族、宗教、身材外貌等歧视性或限定性表述；
- 学历要求只能按用户输入原样呈现，不得自行提高或附加"全日制"等限定；
- 薪资必须写明具体范围或"面议"，不得使用"高薪""薪资上不封顶"等模糊承诺作为唯一描述。"""


def format_company_profile_block() -> str:
    """渲染成塞给 LLM 的文本块（内容为空自动返回空串，避免污染 prompt）"""
    parts = []
    if COMPANY_NAME:
        parts.append(f"- 公司名称：{COMPANY_NAME}")
    if COMPANY_BRIEF:
        parts.append(f"- 公司简介：{COMPANY_BRIEF}")
    if INDUSTRY_TAG:
        parts.append(f"- 所属行业：{INDUSTRY_TAG}")
    if BUSINESS_LINES:
        parts.append("- 主要业务线：\n" + "\n".join(f"  · {b}" for b in BUSINESS_LINES))
    if JD_STYLE_PREFERENCES.get("tone"):
        parts.append(f"- JD 风格偏好：{JD_STYLE_PREFERENCES.get('tone', '')}")
    if not parts:
        return ""
    return "\n\n【我司公司档案（写作时据此适配，禁止编造我司不存在的事实）】\n" + "\n".join(parts)
