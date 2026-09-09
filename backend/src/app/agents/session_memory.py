# 【小白导读】对话记忆：按 session_id 在内存里保存最近几轮对话，
#   让制度问答等场景"记得上一句说了什么"。重启进程即清空（学习用途足够）。
"""Function Calling 会话短期记忆（进程内 TTL 缓存）

作用：让 HR 的连续对话拥有上下文，例如：
    第 1 轮：查一下 90 分以上的候选人
    第 2 轮：给刚才那个人发面试邀请     <- 没有 memory 时"刚才那个人"无法解析

设计：
- 每个 session_id 保留最近 MAX_MESSAGES 条消息，超过 30 分钟未活动自动过期
- 进程内 dict 实现，单 worker 场景够用；多 worker 部署时把这几个函数
  无缝替换为 Redis 实现（get/append/clear 语义一致）即可
"""
import time
import threading

MAX_MESSAGES = 20          # 每个 session 最多保留的消息条数
TTL_SECONDS = 1800         # 会话过期时间（30 分钟无活动即丢弃）

# {session_id: {"messages": [...], "last_active": timestamp}}
_store: dict = {}
_lock = threading.Lock()


def _evict_expired() -> None:
    """惰性清理过期会话（避免后台定时任务的额外复杂度）"""
    now = time.time()
    expired = [sid for sid, v in _store.items() if now - v["last_active"] > TTL_SECONDS]
    for sid in expired:
        _store.pop(sid, None)


def get_history(session_id: str) -> list:
    """读取某个会话的历史消息（role/content 格式，可直接拼进 messages）"""
    with _lock:
        _evict_expired()
        entry = _store.get(session_id)
        if not entry:
            return []
        entry["last_active"] = time.time()
        return list(entry["messages"])


def append_message(session_id: str, role: str, content: str) -> None:
    """追加一条消息到会话（user / assistant），超出上限时淘汰最早的"""
    if not content:
        return
    with _lock:
        entry = _store.setdefault(session_id, {"messages": [], "last_active": time.time()})
        entry["messages"].append({"role": role, "content": content})
        entry["last_active"] = time.time()
        if len(entry["messages"]) > MAX_MESSAGES:
            entry["messages"] = entry["messages"][-MAX_MESSAGES:]


def clear_session(session_id: str) -> None:
    """手动清空某个会话的记忆"""
    with _lock:
        _store.pop(session_id, None)
