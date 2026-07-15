"""简历解析与分析服务 — 文件解析 + LLM结构化提取 + 匹配度评估"""
import json
import logging
import os
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.llm_client import llm_client
from app.agents.prompts import RESUME_ANALYSIS_SYSTEM, RESUME_ANALYSIS_PROMPT
from app.models.candidate import Candidate
from app.models.resume import Resume

# 创建模块级日志记录器
logger = logging.getLogger(__name__)


class ResumeAnalyzer:
    """简历分析器：负责文件解析和AI分析"""

    UPLOAD_DIR = "uploads/resumes" # 上传目录
    OCR_TEXT_THRESHOLD = 50 # OCR识别文字阈值（先默认使用直接识别，如果文字量超过阈值，再使用OCR识别）

    def __init__(self):
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)# 确保上传目录存在
        self._ocr = None # 初始化OCR引擎为None
        logger.info(f"简历分析器初始化完成，上传目录: {self.UPLOAD_DIR}")

    # ========== OCR识别相关 ==========
    # 惰性获取PaddleOCR引擎
    def _get_ocr(self):
        # 先判断是否已加载OCR模型，如果没有则加载
        if self._ocr is None:
            logger.info("首次使用PaddleOCR，正在加载模型（约15MB）...")
            from paddleocr import PaddleOCR
            # 加载OCR模型
            self._ocr = PaddleOCR(use_angle_cls=True, # 启用角度分类（在识别图片的时候，需要考虑文字的角度，照片可能是歪的）
                                  lang='ch', # 识别中文
                                  use_gpu=False # 不使用GPU加速
                                  )
            logger.info("PaddleOCR模型加载完成")
        return self._ocr


    # ========== 图片OCR识别 ==========读取内容
    # 对图片进行OCR识别，返回纯文本
    def _ocr_image(self, image_bytes: bytes) -> str:
        """对图片进行OCR识别，返回纯文本"""
        # 读取图片将图片转化成PIL Image对象
        from PIL import Image
        from io import BytesIO
        # 打开图片（从字节流中读取），只有这样OCR才能识别到图片中的文字
        img = Image.open(BytesIO(image_bytes))
        logger.debug(f"OCR识别图片: 尺寸={img.size}, 模式={img.mode}")
        # 创建OCR实例，用于识别图片中的文字
        ocr = self._get_ocr()
        # 对图片进行OCR识别，返回识别结果
        result = ocr.ocr(img, cls=True)
        # 检查识别结果是否为空
        if not result or not result[0]:
            logger.warning("OCR未识别到任何文字")
            return ""
        # 从识别结果中提取文字（过滤掉置信度低的）
        lines = []
        for block in result:  # 遍历每个文字块
            for line in block:  # 遍历块内每一行
                if line[1][1] > 0.3:  # 置信度 > 30% 才保留
                    lines.append(line[1][0])  # 取文字部分
        # 合并所有行文字，用换行符分隔
        text = "\n".join(lines)
        logger.info(f"OCR识别完成: 共 {len(lines)} 行文字, 总长度 {len(text)} 字符")
        return text

    # ========== 解析简历文件 ==========解析文件内容
    async def parse_resume_file(self, file_content: bytes,# 文件内容（字节流）
                                filename: str) -> str: # 文件名
        """解析简历文件为纯文本"""
        # 检查文件扩展名是否支持解析
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""# 获取文件扩展名（小写）
        logger.info(f"开始解析简历文件: {filename} (类型: {ext}), 大小: {len(file_content)} 字节")

        # ========== 纯文本 ==========
        if ext == "txt":
            # 直接解码为UTF-8文本
            text = file_content.decode("utf-8", errors="replace")
            logger.info(f"TXT解析完成: {len(text)} 字符")
            return text

        # ========== Word文档 ==========
        elif ext == "docx":
            import docx
            from io import BytesIO
            # 从字节流中读取Word文档
            doc = docx.Document(BytesIO(file_content))
            text = "\n".join(p.text for p in doc.paragraphs)
            logger.info(f"DOCX解析完成: {len(doc.paragraphs)} 段落, {len(text)} 字符")
            return text

        # ========== PDF（支持文本型和扫描件）=========
        elif ext == "pdf":
            import fitz
            # 从字节流中读取PDF文档
            doc = fitz.open(stream=file_content, filetype="pdf")
            # 获取PDF文档的页数
            page_count = len(doc)
            logger.info(f"PDF文档: {page_count} 页, 尝试提取文本...")

            text_parts = []
            # 遍历PDF每一页，提取文本
            for i, page in enumerate(doc):
                page_text = page.get_text()
                text_parts.append(page_text)
                logger.debug(f"  第{i+1}页: 提取到 {len(page_text)} 字符")
            text = "\n".join(text_parts)
            # 关闭PDF文档
            doc.close()

            # 如果提取到的文字太少，说明是扫描件PDF，走OCR
            if len(text.strip()) < self.OCR_TEXT_THRESHOLD: # 如果提取到的文字太少，说明是扫描件PDF，走OCR
                logger.warning(f"PDF文本提取仅 {len(text.strip())} 字符，判定为扫描件，切换OCR...")
                from PIL import Image
                # 从字节流中读取PDF文档
                doc = fitz.open(stream=file_content, filetype="pdf")
                ocr_pages = []
                # 遍历PDF每一页，进行OCR识别
                for i, page in enumerate(doc):
                    logger.info(f"  OCR识别第 {i+1}/{page_count} 页...")
                    # 将PDF页面转换为PNG图片
                    """PaddleOCR 只能识别图片，无法直接读 PDF。所以需要先把 PDF 页面"拍"成照片，再喂给 OCR"""
                    # 把PDF页面转换为PNG图片，DPI为300
                    pix = page.get_pixmap(dpi=300)
                    # 把PDF页面渲染成图片，300DPI保证清晰度
                    img_bytes = pix.tobytes("png")
                    # 对图片进行OCR识别，返回识别结果
                    page_text = self._ocr_image(img_bytes)
                    # 把OCR识别结果添加到列表中
                    ocr_pages.append(page_text)
                # 关闭PDF文档
                doc.close()
                text = "\n".join(ocr_pages)
                logger.info(f"PDF扫描件OCR完成: {len(text)} 字符")
            else:
                logger.info(f"PDF文本提取成功: {len(text)} 字符")

            return text

        # ========== 图片文件（JPG/PNG/BMP/TIFF）=========
        # 如果是图片文件，直接OCR识别
        elif ext in ("jpg", "jpeg", "png", "bmp", "tiff", "tif"):
            logger.info(f"图片文件OCR识别: {filename}")
            return self._ocr_image(file_content)

        # ========== 未知格式 ==========
        # 如果是未知文件类型，尝试作为纯文本处理
        else:
            logger.warning(f"未知文件类型: {ext}, 尝试作为纯文本处理")
            try:
                # 尝试解码为UTF-8文本
                text = file_content.decode("utf-8", errors="replace")
                logger.info(f"作为纯文本解析成功: {len(text)} 字符")
                return text
            except Exception as e:
                logger.error(f"不支持的文件类型: {ext}, 错误: {e}")
                raise ValueError(f"不支持的文件类型: {ext}")

    # ========== 分析简历 ==========
    async def analyze_resume(self, resume_id: int, # 简历ID
                             job_description: str, # 岗位描述
                             db: AsyncSession) -> dict: # 数据库会话
        """分析简历：调用LLM进行结构化提取和匹配度评估"""
        logger.info(f"开始AI分析简历 ID={resume_id}, 岗位描述={job_description[:50]}...")

        # 1. 从数据库获取简历记录
        # 检查简历是否存在
        result = await db.execute(select(Resume).where(Resume.id == resume_id))
        # 检查简历是否存在
        resume = result.scalar_one_or_none()
        if not resume:
            logger.error(f"简历不存在: resume_id={resume_id}")
            raise ValueError(f"简历不存在: {resume_id}")
        if not resume.raw_text:
            logger.error(f"简历文本为空: resume_id={resume_id}")
            raise ValueError("简历文本为空，请先上传并解析")
        logger.debug(f"简历文本长度: {len(resume.raw_text)} 字符")

        # 2. 获取关联的候选人信息
        cand_result = await db.execute(
            select(Candidate).where(Candidate.id == resume.candidate_id)
        )
        candidate = cand_result.scalar_one_or_none()
        logger.info(f"关联候选人: ID={candidate.id if candidate else '无'}, 姓名={candidate.name if candidate else '未知'}")

        # 3. 构造LLM提示词并调用
        truncated_text = resume.raw_text[:15000]
        prompt = RESUME_ANALYSIS_PROMPT.format(
            resume_text=truncated_text,
            job_description=job_description or "通用岗位",
        )
        logger.info(f"调用LLM分析... 输入文本长度: {len(truncated_text)} 字符")

        # 调用LLM分析
        response = await llm_client.chat(
            system=RESUME_ANALYSIS_SYSTEM, # 系统提示词
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=4096,
        )
        logger.debug(f"LLM返回原始响应: {response[:200]}...")

        # 4. 解析LLM返回的JSON结果
        try:
            result_data = json.loads(response)
            logger.info("LLM响应JSON解析成功")
        except json.JSONDecodeError:
            logger.warning("LLM响应JSON解析失败，尝试正则提取...")
            import re
            # 尝试使用正则表达式提取JSON字符串（防止LLM返回的格式异常）
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            # 检查是否成功提取JSON字符串
            if json_match:
                result_data = json.loads(json_match.group())
                logger.info("正则提取JSON成功")
            else:
                logger.error(f"LLM返回格式异常: {response[:200]}...")
                raise ValueError(f"LLM返回格式异常: {response[:200]}...")
        # 提取分析结果
        analysis = result_data.get("analysis", {})
        # 提取匹配分析结果
        match_analysis = result_data.get("match_analysis", {})
        # 提取摘要
        summary = result_data.get("summary", "")

        # 记录评分结果
        if match_analysis:# 返回结果不为空时，记录评分结果
            # 提取总分和维度
            score = match_analysis.get("overall_score", "N/A")
            # 提取维度
            dims = match_analysis.get("dimensions", {})
            # 记录日志
            logger.info(f"AI分析完成: 总分={score}, 维度={dims}")

        # 5. 更新简历记录
        # 更新分析结果
        resume.analysis_result = analysis
        # 更新匹配分析结果
        resume.match_analysis = match_analysis
        # 更新摘要
        resume.summary = summary
        # 记录日志
        logger.debug("简历记录已更新")

        # 6. 同步更新候选人信息
        # 判断候选人是否存在
        if candidate:
            # 判断匹配分析结果是否存在
            if match_analysis:
                # 更新匹配度评分（把总分写入候选人）
                candidate.match_score = match_analysis.get("overall_score")
            # 判断分析结果是否存在
            if analysis:
                # 更新候选人基本信息
                basic_info = analysis.get("basic_info", {})
                # 更新姓名
                if basic_info.get("name") and not candidate.name:
                    # 更新姓名
                    candidate.name = basic_info["name"]
                    # 记录日志
                    logger.info(f"从简历更新候选人姓名: {candidate.name}")
                # 更新电话
                if basic_info.get("phone") and not candidate.phone:
                    # 更新电话
                    candidate.phone = basic_info.get("phone")
                    # 记录日志
                    logger.info(f"从简历更新候选人电话: {candidate.phone}")
                # 更新邮箱
                if basic_info.get("email") and not candidate.email:
                    # 更新邮箱
                    candidate.email = basic_info.get("email")
                    # 记录日志
                    logger.info(f"从简历更新候选人邮箱: {candidate.email}")
                # 更新技能标签
                if analysis.get("skills"):
                    # 更新技能标签（最多10个）
                    old_tags = list(candidate.tags or [])
                    # 合并新技能标签（去重）
                    candidate.tags = list(set(old_tags + analysis["skills"][:10]))
                    # 新增技能标签数
                    new_skills = len(candidate.tags) - len(old_tags)
                    # 记录日志
                    logger.info(f"更新技能标签: 原有{len(old_tags)}个, 新增{new_skills}个")
            # 更新候选人状态为已分析
            if not candidate.status:
                # 更新状态
                candidate.status = "analyzed"
                # 记录日志
                logger.info(f"候选人状态更新为: analyzed")

        # 7. 记录分析完成时间
        resume.analyzed_at = __import__("datetime").datetime.utcnow()
        await db.flush()
        logger.info(f"简历分析全流程完成: resume_id={resume_id}")

        # 返回分析结果
        return {
            "analysis": analysis,  # 分析结果
            "match_analysis": match_analysis,  # 匹配分析结果
            "summary": summary,  # 摘要
                   } # 返回分析结果

    async def get_resume_analysis(self, candidate_id: int,# 候选人ID
                                  db: AsyncSession) -> Optional[dict]:# 数据库会话
        """获取候选人最新的简历分析结果"""
        logger.debug(f"查询候选人最新分析结果: candidate_id={candidate_id}")
        # 查询最新简历记录
        # 按创建时间降序排序，取最新一条
        result = await db.execute(
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        # 创建sql对象（可类比Java中的MyBatis）
        resume = result.scalar_one_or_none()
        if not resume:
            logger.warning(f"未找到简历记录: candidate_id={candidate_id}")
            return None

        logger.debug(f"查询成功: resume_id={resume.id}, 分析时间={resume.analyzed_at}")
        return {
            "id": resume.id, # 简历记录ID
            "candidate_id": resume.candidate_id, # 候选人ID
            "original_filename": resume.original_filename, # 原始文件名
            "analysis": resume.analysis_result, # 分析结果
            "match_analysis": resume.match_analysis, # 匹配分析结果
            "summary": resume.summary, # 摘要
            "analyzed_at": resume.analyzed_at, # 分析时间
        }


# 全局单例
resume_analyzer = ResumeAnalyzer()