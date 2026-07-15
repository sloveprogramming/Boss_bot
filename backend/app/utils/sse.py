"""SSE (Server-Sent Events) 流式输出工具

提供统一的 SSE 事件生成器和 StreamingResponse 工厂，
供所有需要流式输出的 API 端点使用。

SSE 事件格式:
    event: <event_type>
    data: <json_string>
    \n

事件类型:
    - progress: 进度更新（node: 节点名, status: running/done/error, message: 描述）
    - token: LLM 生成的文本增量
    - tool_call: Function Calling 工具调用信息
    - tool_result: 工具执行结果摘要
    - done: 流式输出完成
    - error: 错误信息
"""
import json
from typing import AsyncGenerator, Optional


def sse_event(event_type: str, data: dict) -> str:
    """构建单条 SSE 事件字符串"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def sse_progress_generator(
    nodes: list[dict],
    done_message: str = "处理完成",
) -> AsyncGenerator[str, None]:
    """生成工作流进度 SSE 事件流

    每个节点依次 yield progress 事件，最后 yield done 事件。

    Args:
        nodes: 节点列表 [{"name": "解析简历", "status": "running/done/error", "message": "..."}]
        done_message: 完成时的消息
    """
    for node in nodes:
        yield sse_event("progress", node)
    yield sse_event("done", {"message": done_message})


# ===== 便捷工厂 =====

def token_event(text: str) -> str:
    """生成 token 增量事件"""
    return sse_event("token", {"text": text})


def progress_event(node: str, status: str, message: str = "", progress_pct: Optional[int] = None) -> str:
    """生成进度事件"""
    data: dict = {"node": node, "status": status, "message": message}
    if progress_pct is not None:
        data["progress_pct"] = progress_pct
    return sse_event("progress", data)


def done_event(message: str, result: Optional[dict] = None) -> str:
    """生成完成事件"""
    return sse_event("done", {"message": message, "result": result or {}})


def error_event(message: str, detail: str = "") -> str:
    """生成错误事件"""
    return sse_event("error", {"message": message, "detail": detail})
