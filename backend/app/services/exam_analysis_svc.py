"""试卷分析服务 — 调用 Dify Workflow API 分析考试结果"""
import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ExamAnalysis

logger = logging.getLogger(__name__)


class ExamAnalysisService:
    """试卷分析服务"""

    async def call_dify_workflow(self, exam_data: dict) -> Optional[dict]:
        """调用 Dify Workflow API 分析考试结果

        Args:
            exam_data: 包含考试信息的字典（考生信息、得分等）

        Returns:
            Dify 返回的结构化分析结果，失败时返回降级结果
        """
        if not settings.DIFY_API_KEY:
            logger.warning("DIFY_API_KEY 未配置，使用模拟分析结果")
            return self._mock_analysis(exam_data)

        import httpx

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                payload = {
                    "inputs": {},
                    "query": json.dumps(exam_data, ensure_ascii=False),
                    "response_mode": "blocking",
                    "user": "system",
                    "conversation_id": "",
                }
                resp = await client.post(
                    f"{settings.DIFY_API_URL}/chat-messages",
                    headers={
                        "Authorization": f"Bearer {settings.DIFY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                result = resp.json()

                # 解析 Dify chat 输出
                answer = result.get("answer", "{}")
                try:
                    parsed = json.loads(answer)
                    if isinstance(parsed, dict) and any(k in parsed for k in ["overall_score", "strengths", "suggestion"]):
                        return parsed
                except (json.JSONDecodeError, TypeError):
                    pass

                # 没有结构化输出，包装为基本格式
                return {
                    "overall_score": exam_data.get("score", 0),
                    "summary": answer[:500],
                    "suggestion": answer[:500],
                }

        except Exception as e:
            logger.error(f"Dify API 调用失败: {e}")
            return self._mock_analysis(exam_data, error=str(e))

    def _mock_analysis(self, exam_data: dict, error: str = "") -> dict:
        """Dify 不可用时的降级分析结果"""
        score = exam_data.get("score", 0)
        total = exam_data.get("total", 100)
        pct = (score / total * 100) if total > 0 else 0

        return {
            "overall_score": round(pct, 1),
            "knowledge_dimensions": {
                "基础知识": round(pct * 0.9, 1),
                "理解应用": round(pct * 0.85, 1),
                "综合分析": round(pct * 0.75, 1),
                "实践能力": round(pct * 0.8, 1),
            },
            "strengths": ["请配置 Dify API Key 以获取完整分析"],
            "weaknesses": [],
            "suggestion": "请配置 Dify API Key 及工作流后重试分析",
            "summary": f"得分率 {pct:.1f}%，请配置 Dify 获取详细评估",
            "_note": error or "Dify 未配置，此为模拟结果",
        }

    async def trigger_analysis(self, db: AsyncSession, analysis_id: int):
        """触发 Dify 分析（后台任务调用）"""
        try:
            # 查询记录
            result = await db.execute(
                select(ExamAnalysis).where(ExamAnalysis.id == analysis_id)
            )
            record = result.scalar_one_or_none()
            if not record:
                logger.error(f"ExamAnalysis {analysis_id} 不存在")
                return

            # 更新状态为分析中
            record.analysis_status = "analyzing"
            await db.flush()

            # 准备 Dify 输入数据
            exam_data = {
                "candidate_name": record.candidate_name,
                "exam_title": record.exam_title,
                "score": record.exam_score,
                "total": record.exam_total,
                "duration": record.exam_duration,
                "raw_data": record.raw_data or {},
            }

            # 调用 Dify
            result_data = await self.call_dify_workflow(exam_data)

            # 保存分析结果
            record.analysis_result = result_data
            record.analysis_status = "completed"
            record.analyzed_at = datetime.utcnow()
            await db.flush()

        except Exception as e:
            logger.error(f"分析失败 (id={analysis_id}): {e}")
            try:
                record = await db.get(ExamAnalysis, analysis_id)
                if record:
                    record.analysis_status = "failed"
                    record.error_message = str(e)
                    await db.flush()
            except Exception:
                pass


# 全局单例
exam_analysis_service = ExamAnalysisService()
