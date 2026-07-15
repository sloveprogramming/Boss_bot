"""Agent HTTP 客户端 — 工作流节点调用独立 Agent 服务

若某个 Agent 服务未启动，节点会降级使用内联实现（Backend 已有服务）。
"""
import os
import httpx
from typing import Optional


class AgentClient:
    """统一封装对各独立 Agent 的 HTTP 调用"""

    def __init__(self):
        self.resume_parser_url = os.getenv("RESUME_PARSER_URL", "http://localhost:18001")
        self.classifier_url = os.getenv("CLASSIFIER_URL", "http://localhost:18002")
        self.notification_url = os.getenv("NOTIFICATION_URL", "http://localhost:18006")
        self.analyzer_base_url = os.getenv("ANALYZER_BASE_URL", "http://localhost:18008")

    def _analyzer_url(self, category: str) -> str:
        """获取对应岗位的分析 Agent 地址"""
        ports = {
            "python": "18008", "java": "18009", "product": "18010",
            "ai": "18011", "frontend": "18012", "ops": "18013", "test": "18014",
            "erp": "18008", "外贸运营": "18008", "数据分析": "18008",
            "项目管理": "18008", "销售": "18008", "人力资源": "18008",
        }
        port = ports.get(category, "18008")
        return f"http://localhost:{port}"

    async def parse_resume(self, file_content: bytes, filename: str) -> Optional[dict]:
        """调用 Resume Parser Agent 解析简历"""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                files = {"file": (filename, file_content)}
                resp = await client.post(f"{self.resume_parser_url}/api/parse", files=files)
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None  # 降级信号

    async def classify(self, resume_text: str, position: str = "",
                       skills: Optional[list] = None) -> Optional[dict]:
        """调用 Classifier Agent 判断岗位类别"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.classifier_url}/api/classify",
                    json={
                        "resume_text": resume_text[:5000],
                        "position": position,
                        "skills": skills or [],
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def analyze(self, category: str, resume_text: str,
                      job_description: str = "") -> Optional[dict]:
        """调用对应岗位的分析 Agent"""
        try:
            base = self._analyzer_url(category)
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{base}/api/analyze",
                    json={
                        "resume_text": resume_text[:15000],
                        "job_description": job_description,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def send_notification(self, template: str, channel: str,
                                recipient: str, context: dict) -> Optional[dict]:
        """调用 Notification Agent 发送通知"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.notification_url}/api/send",
                    json={
                        "template": template,
                        "channel": channel,
                        "recipient": recipient,
                        "context": context,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None


# 全局单例
agent_client = AgentClient()
