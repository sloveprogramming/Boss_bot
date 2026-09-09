# ═══════════════════════════════════════════════════════════════
# 【小白导读】简历模块：上传 → 解析（PDF/Word/TXT/图片OCR）→ AI 分析。
#   · analyze_resume：同步等待结果；analyze_resume_stream：SSE 流式看进度。
#   · quick_add_candidate："传简历自动建候选人"的快捷入口。
#   · 文件解析细节在 workflow/nodes/parse_resume.py，AI 分析在 services/resume_analyzer.py。
# ═══════════════════════════════════════════════════════════════
"""简历上传与分析API"""
import json
import logging
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Resume, Candidate, CandidateStatus, UserRole, User
from app.dependencies import (
    require_role, get_current_user, ensure_candidate_visible,
)
from app.services import resume_analyzer
from app.services.position_jd_svc import resolve_jd_with_manual
from app.schemas import ResumeUploadResponse, ResumeAnalysisResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/resumes",
    tags=["简历管理"],
    dependencies=[Depends(require_role([UserRole.ADMIN, UserRole.HR]))],
)


def _parse_llm_json(text: str) -> dict:
    """健壮解析 LLM 返回的 JSON（先 json.loads，失败再正则兜底）"""
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise ValueError("识别结果不是合法 JSON")


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    candidate_id: int = Form(...),          # 候选人ID（表单参数）
    file: UploadFile = File(...),            # 上传的简历文件
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传简历文件并解析为纯文本"""
    # 验证候选人存在且当前 HR 可见
    await ensure_candidate_visible(db, current_user, candidate_id)

    # 读取上传文件内容
    content = await file.read()

    # 根据文件类型解析为纯文本
    try:
        raw_text = await resume_analyzer.parse_resume_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 保存简历记录到数据库
    resume = Resume(
        candidate_id=candidate_id,
        original_filename=file.filename,
        file_type=file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "unknown",
        raw_text=raw_text,
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)
    # 在返回前提交，避免前端立即用返回的ID调analyze时因事务未提交而查不到记录（404）
    await db.commit()

    return ResumeUploadResponse(
        id=resume.id,
        candidate_id=candidate_id,
        original_filename=file.filename,
    )


@router.post("/{resume_id}/analyze", response_model=ResumeAnalysisResponse)
async def analyze_resume(
    resume_id: int,
    job_description: str = Form(""),  # 岗位描述（可选，用于匹配度分析）
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """分析简历：调用LLM进行结构化提取和匹配度评分"""
    # 验证简历存在
    result = await db.execute(
        __import__("sqlalchemy").select(Resume).where(Resume.id == resume_id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    # 数据范围校验：候选人须对当前 HR 可见
    candidate = await ensure_candidate_visible(db, current_user, resume.candidate_id)

    # 执行分析（岗位 JD 自动套用：HR 手填优先，留空按应聘岗位取「岗位 JD 库」标准 JD）
    try:
        effective_jd = await resolve_jd_with_manual(db, candidate.position, job_description)
        analysis = await resume_analyzer.analyze_resume(
            resume_id=resume_id,
            job_description=effective_jd,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 获取候选人姓名用于返回
    cand_result = await db.execute(
        __import__("sqlalchemy").select(Candidate).where(Candidate.id == resume.candidate_id)
    )
    candidate = cand_result.scalar_one_or_none()

    return ResumeAnalysisResponse(
        id=resume.id,
        candidate_id=resume.candidate_id,
        candidate_name=candidate.name if candidate else "",
        original_filename=resume.original_filename,
        analysis=analysis.get("analysis"),
        match_analysis=analysis.get("match_analysis"),
        summary=analysis.get("summary"),
        analyzed_at=resume.analyzed_at,
    )


@router.get("/candidate/{candidate_id}", response_model=ResumeAnalysisResponse)
async def get_candidate_resume_analysis(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取候选人最新的简历分析结果"""
    await ensure_candidate_visible(db, current_user, candidate_id)
    result = await resume_analyzer.get_resume_analysis(candidate_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="未找到简历分析结果")

    cand_result = await db.execute(
        __import__("sqlalchemy").select(Candidate).where(Candidate.id == candidate_id)
    )
    candidate = cand_result.scalar_one_or_none()

    return ResumeAnalysisResponse(
        **result,
        candidate_name=candidate.name if candidate else "",
    )


# ====================================================================
# 简历自动识别预填 / 一键建档（新建候选人流程）
# ====================================================================


@router.post("/preview")
async def preview_resume_basic(
    file: UploadFile = File(...),
):
    """解析简历并识别基本信息（姓名/电话/邮箱/所在地/岗位/技能），用于新建候选人时自动回填

    仅识别不落库；文件支持 txt/docx/pdf(含扫描件OCR)/图片。
    """
    from app.agents import (
        llm_client,
        RESUME_BASIC_PREVIEW_SYSTEM,
        RESUME_BASIC_PREVIEW_PROMPT,
    )

    content = await file.read()
    try:
        raw_text = await resume_analyzer.parse_resume_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=400, detail="未能从该文件中提取到文本，请更换清晰文件")

    truncated = raw_text[:8000]
    try:
        resp = await llm_client.chat(
            system=RESUME_BASIC_PREVIEW_SYSTEM,
            messages=[
                {"role": "user", "content": RESUME_BASIC_PREVIEW_PROMPT.format(resume_text=truncated)}
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=1024,
        )
    except Exception as e:
        logger.error("简历基本信息识别失败: %s", e)
        raise HTTPException(status_code=502, detail=f"简历识别失败（模型调用出错）：{str(e)}")

    data = _parse_llm_json(resp)

    out: dict = {}
    for k in ("name", "phone", "email", "location", "suggested_position"):
        v = data.get(k)
        out[k] = v.strip() if isinstance(v, str) else ""
    ey = data.get("experience_years")
    try:
        out["experience_years"] = float(ey) if ey not in (None, "", "null", "None") else None
    except (TypeError, ValueError):
        out["experience_years"] = None
    skills = data.get("skills")
    out["skills"] = [s for s in skills if isinstance(s, str) and s.strip()][:10] if isinstance(skills, list) else []
    return out


@router.post("/quick-add")
async def quick_add_candidate(
    file: UploadFile = File(...),
    name: str = Form(""),
    position: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    source: str = Form("manual"),
    experience_years: str = Form(""),
    job_description: str = Form(""),
    owner_user_id: Optional[int] = Form(None),  # 负责人（仅 admin 指派有效）
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一步建档：解析简历 → 创建候选人+简历 → 立即 AI 分析

    即使 AI 分析失败也会保留候选人与简历（可到详情页重试），仅返回 warning。
    """
    name = (name or "").strip()
    position = (position or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="姓名不能为空")
    if not position:
        raise HTTPException(status_code=400, detail="应聘岗位不能为空")

    content = await file.read()
    try:
        raw_text = await resume_analyzer.parse_resume_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ey = None
    if experience_years not in ("", "null", "None"):
        try:
            ey = float(experience_years)
        except (TypeError, ValueError):
            ey = None

    # 归属规则：HR 建档归属自己（忽略传入 owner_user_id）；admin 可指派给某 HR/admin
    owner_id = current_user.id
    if current_user.role == UserRole.ADMIN.value and owner_user_id is not None:
        target = (await db.execute(
            select(User).where(User.id == owner_user_id)
        )).scalar_one_or_none()
        if (
            not target or not target.is_active
            or target.role not in (UserRole.ADMIN.value, UserRole.HR.value)
        ):
            raise HTTPException(status_code=400, detail="指定的负责人不存在或不是 HR/admin")
        owner_id = target.id

    candidate = Candidate(
        name=name,
        position=position,
        phone=(phone or "").strip() or None,
        email=(email or "").strip() or None,
        source=(source or "manual").strip() or "manual",
        experience_years=ey,
        owner_user_id=owner_id,
    )
    db.add(candidate)
    await db.flush()
    await db.refresh(candidate)

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "unknown"
    resume = Resume(
        candidate_id=candidate.id,
        original_filename=file.filename,
        file_type=ext,
        raw_text=raw_text,
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)

    # 先提交建档，保证后续 AI 分析即使失败，候选人与简历也已保存
    await db.commit()

    warning = None
    try:
        # 岗位 JD 自动套用：手填优先，留空按应聘岗位 position 从库内取标准 JD
        effective_jd = await resolve_jd_with_manual(db, position, job_description)
        await resume_analyzer.analyze_resume(resume.id, effective_jd, db)
        # 建档默认状态为 new；AI 分析成功后推进为 analyzed
        # （analyze_resume 仅在 status 为空时才置位，故这里显式过渡）
        if candidate.status == CandidateStatus.NEW.value:
            candidate.status = CandidateStatus.RESUME_ANALYZED.value
        await db.commit()
    except Exception as e:
        await db.rollback()
        warning = f"AI 分析未完成（{e}），可在候选人详情页重新分析"
        logger.warning("候选人 %s 快速建档 AI 分析失败: %s", candidate.id, e)

    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "resume_id": resume.id,
        "status": "ok",
        "warning": warning,
    }


# ====================================================================
# SSE 流式分析端点
# ====================================================================

from fastapi.responses import StreamingResponse
from app.utils import token_event, progress_event, done_event, error_event


@router.post("/{resume_id}/analyze/stream")
async def analyze_resume_stream(
    resume_id: int,
    job_description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """流式分析简历（SSE）

    逐 token 输出 LLM 分析结果，让用户看到分析过程：
    1. progress: 正在提取结构化信息...
    2. token: 教育背景: 清华大学 计算机硕士...
    3. token: 工作经验: 5年后端开发经验...
    4. progress: 正在计算匹配度...
    5. token: 匹配度分析: 候选人技能与岗位高度匹配...
    6. done: 分析完成
    """
    import sqlalchemy

    result = await db.execute(
        sqlalchemy.select(Resume).where(Resume.id == resume_id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise HTTPException(status_code=404, detail="简历不存在")
    # 数据范围校验：候选人须对当前 HR 可见
    candidate = await ensure_candidate_visible(db, current_user, resume.candidate_id)

    # SSE 响应体在会话关闭后才执行，故在端点体内先把岗位 JD 解析成普通字符串（会话仍可用）
    # （岗位 JD 自动套用：HR 手填优先，留空按应聘岗位取「岗位 JD 库」标准 JD）
    effective_jd = await resolve_jd_with_manual(db, candidate.position, job_description)

    async def generate():
        from app.agents import llm_client, RESUME_ANALYSIS_SYSTEM, RESUME_ANALYSIS_PROMPT

        yield progress_event("init", "running", "准备分析简历...", 5)

        # 阶段 1: 结构化提取（JSON 输出，使用流式 JSON）
        yield progress_event("extraction", "running", "正在提取简历结构化信息...", 20)

        try:
            messages = [
                {"role": "user", "content": RESUME_ANALYSIS_PROMPT.format(
                    resume_text=resume.raw_text or "",
                    job_description=effective_jd or "",
                )}
            ]

            # 结构化信息一次性生成（JSON 不能逐 token 输出）
            json_result = await llm_client.chat(
                system=RESUME_ANALYSIS_SYSTEM,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            yield progress_event("extraction", "done", "简历信息提取完成", 50)

            # 阶段 2: 逐 token 输出分析摘要
            yield progress_event("summary", "running", "正在生成分析摘要...", 60)

            summary_prompt = f"基于以下简历分析结果，生成一份简洁的分析摘要：\n{json_result[:2000]}"

            async for chunk in llm_client.stream_chat(
                system="你是一位专业的招聘顾问，请基于简历分析数据生成一份简洁、专业的分析摘要。",
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
            ):
                yield token_event(chunk)

            yield progress_event("summary", "done", "分析摘要生成完成", 90)

            # 保存分析结果到数据库
            import json
            try:
                parsed = json.loads(json_result)
                resume.analysis_result = parsed.get("analysis", parsed)
                resume.match_analysis = parsed.get("match_analysis", {})
                resume.summary = parsed.get("summary", "")
                resume.analyzed_at = __import__("datetime").datetime.utcnow()
                await db.flush()
            except Exception as e:
                logger.error("简历 %s 分析结果保存失败: %s", resume_id, e)

            yield done_event("简历分析完成", {
                "resume_id": resume_id,
                "candidate_id": resume.candidate_id,
            })

        except Exception as e:
            yield error_event("分析过程出错", str(e))

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
