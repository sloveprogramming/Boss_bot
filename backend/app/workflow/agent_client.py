"""Agent HTTP 客户端

依赖注入：
  __init__ 可接受 httpx.AsyncClient 和各 Agent URL。
  未传入时回退到 env 变量 / 默认值（兼容旧代码）。
"""
import os
import httpx
from typing import Optional


class AgentClient:
    """统一封装对各独立 Agent 的 HTTP 调用 — 支持依赖注入"""

    # ---- 构造器依赖注入 ----
    def __init__(self,
                 httpx_client=None,
                 resume_parser_url: Optional[str] = None,
                 classifier_url: Optional[str] = None,
                 notification_url: Optional[str] = None,
                 analyzer_base_url: Optional[str] = None,
                 port_map: Optional[dict] = None):
        """构造 Agent 客户端

        Args:
            httpx_client:       httpx.AsyncClient 实例（注入后复用连接池）
            resume_parser_url:  简历解析 Agent URL
            classifier_url:     分类 Agent URL
            notification_url:   通知 Agent URL
            analyzer_base_url:  分析 Agent 基础 URL
            port_map:           岗位 → 端口映射字典
        """
        self._httpx_client = httpx_client
        self.resume_parser_url = resume_parser_url or os.getenv("RESUME_PARSER_URL", "http://localhost:18001")
        self.classifier_url = classifier_url or os.getenv("CLASSIFIER_URL", "http://localhost:18002")
        self.notification_url = notification_url or os.getenv("NOTIFICATION_URL", "http://localhost:18006")
        self.analyzer_base_url = analyzer_base_url or os.getenv("ANALYZER_BASE_URL", "http://localhost:18008")
        self._port_map = port_map

    def _get_client(self, timeout: int = 30):
        """获取 HTTP 客户端 — 注入优先，否则临时创建"""
        if self._httpx_client is not None:
            return self._httpx_client
        return httpx.AsyncClient(timeout=timeout)

    def _analyzer_url(self, category: str) -> str:
        """获取对应岗位的分析 Agent 地址"""
        ports = self._port_map or {
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
            async with self._get_client(timeout=60) as client:
                files = {"file": (filename, file_content)}
                resp = await client.post(f"{self.resume_parser_url}/api/parse", files=files)
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def classify(self, resume_text: str, position: str = "",
                       skills: Optional[list] = None) -> Optional[dict]:
        """调用 Classifier Agent 判断岗位类别"""
        try:
            async with self._get_client(timeout=30) as client:
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
            async with self._get_client(timeout=120) as client:
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
            async with self._get_client(timeout=30) as client:
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


# 全局单例 — 无参数构造，从 env 变量读取（兼容旧代码）
agent_client = AgentClient()
