# ═══════════════════════════════════════════════════════════════
# 【小白导读】RabbitMQ 队列的"邮局"封装。
#   为什么要队列？AI 分析一份简历要几十秒，几百份同时来会压垮 API；
#   有了队列：API 只负责"投递任务"立刻返回，worker 慢慢消化。
#   亮点：任务失败按指数退避延迟重试（republish_with_delay），
#   重试超限进死信队列，RabbitMQ 不可用时上层自动降级为同步执行。
# ═══════════════════════════════════════════════════════════════
"""RabbitMQ 消息代理封装（基于 aio-pika，异步原生）

职责：
  - publish_analysis_task()  : 把「分析某候选人」的任务发布到 durable 队列
  - republish_with_delay()   : 重试时发布到带 TTL 的 retry 队列，到期自动回主队列
  - consume_analysis_tasks()  : 供 worker 消费（prefetch 控制背压）

高并发防护点：
  1. durable 队列 + publisher confirms  → 消息不丢（broker 落盘后才算发送成功）
  2. prefetch_count（有界并发）          → 背压，避免瞬间把 LLM/DB 打爆
  3. 死信交换机 DLX                      → 重试耗尽的故障任务可审计、可重放
  4. retry 交换机 + 每消息 TTL           → 指数退避重试，不占用主队列
  5. 连接失败抛 BrokerUnavailable        → 上层（API 路由）降级为内联同步执行

若 aio_pika 未安装或 RabbitMQ 不可达，所有方法抛 BrokerUnavailable，
调用方据此降级，保证系统在无 MQ 环境仍可用。
"""
import asyncio
import json
import logging
import uuid
from typing import Optional

from app.config import settings

logger = logging.getLogger("queue.broker")


class BrokerUnavailable(Exception):
    """RabbitMQ 不可用（未装客户端 / 连接失败 / 功能被禁用）"""
    pass


_connection: Optional[object] = None
_connection_lock = asyncio.Lock()


def _require_aio_pika():
    try:
        import aio_pika
        return aio_pika
    except ImportError:
        raise BrokerUnavailable("未安装 aio_pika，任务队列不可用（pip install aio-pika）")


async def get_connection():
    """获取（或懒创建）长连接。任何失败都转为 BrokerUnavailable。"""
    global _connection
    if _connection is not None and not _connection.is_closed:
        return _connection
    async with _connection_lock:
        # double-check：锁内再确认一次，避免并发重复建连
        if _connection is not None and not _connection.is_closed:
            return _connection
        aio_pika = _require_aio_pika()
        try:
            conn = await asyncio.wait_for(
                aio_pika.connect_robust(settings.RABBITMQ_URL, timeout=3.0),
                timeout=5.0,
            )
        except Exception as e:  # 网络不可达 / 拒绝 / 超时 / 认证失败
            raise BrokerUnavailable(f"无法连接 RabbitMQ ({settings.RABBITMQ_URL}): {e}")
        _connection = conn
        return conn


async def close_connection():
    """关闭缓存的连接（进程退出时调用）。"""
    global _connection
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
    _connection = None


async def _ensure_infrastructure(channel):
    """声明交换机 / 主队列(带死信) / 死信队列 / retry 队列(带 TTL)。幂等。"""
    aio_pika = _require_aio_pika()
    qname = settings.TASK_QUEUE_NAME
    exname = settings.TASK_EXCHANGE

    # 死信：主队列消费失败(reject) → 进 DLX → DLQ 留存
    dlx = await channel.declare_exchange(exname + ".dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(qname + ".dlq", durable=True)
    await dlq.bind(dlx, routing_key=qname)

    # 主交换机 + 主队列（绑定死信参数）
    exchange = await channel.declare_exchange(exname, aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue(
        qname,
        durable=True,
        arguments={
            "x-dead-letter-exchange": exname + ".dlx",
            "x-dead-letter-routing-key": qname,
        },
    )
    await queue.bind(exchange, routing_key=qname)

    # retry 队列：带 TTL，到期后自动死信回主队列（实现延迟重试）
    retry_ex = await channel.declare_exchange(exname + ".retry", aio_pika.ExchangeType.DIRECT, durable=True)
    retry_q = await channel.declare_queue(
        qname + ".retry",
        durable=True,
        arguments={
            "x-dead-letter-exchange": exname,
            "x-dead-letter-routing-key": qname,
        },
    )
    await retry_q.bind(retry_ex, routing_key=qname)

    return exchange, queue, retry_ex


async def publish_analysis_task(
    candidate_id: int,
    resume_text: str = "",
    job_description: str = "",
    task_id: Optional[str] = None,
) -> str:
    """发布一个简历分析任务，返回 task_id。

    失败（未启用 / 未装客户端 / 连接失败）抛 BrokerUnavailable，由调用方降级。
    """
    if not settings.TASK_ENABLED:
        raise BrokerUnavailable("任务队列已禁用（TASK_ENABLED=false）")
    aio_pika = _require_aio_pika()
    task_id = task_id or str(uuid.uuid4())

    conn = await get_connection()
    channel = await conn.channel()
    try:
        exchange, _, _ = await _ensure_infrastructure(channel)
        message = aio_pika.Message(
            body=json.dumps({
                "task_id": task_id,
                "candidate_id": candidate_id,
                "resume_text": resume_text,
                "job_description": job_description,
            }).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,   # 持久化，broker 重启不丢
            message_id=task_id,
            headers={"x-retry-count": 0},
        )
        # publisher confirms：broker 真正落盘后才返回，否则视为发送失败
        await exchange.publish(message, routing_key=settings.TASK_QUEUE_NAME)
        logger.info("已发布分析任务 task_id=%s candidate_id=%s", task_id, candidate_id)
        return task_id
    finally:
        await channel.close()


async def republish_with_delay(body: dict, retry_count: int, delay_seconds: float):
    """把任务重新投递到 retry 队列，delay_seconds 后由 broker 自动回主队列。

    用于指数退避重试：原始消息已在 worker 中被 reject（进 DLX 前先走这里）。
    注意：retry 队列本身也会被消费，所以最终仍回主队列重新执行。
    """
    aio_pika = _require_aio_pika()
    task_id = body.get("task_id") or str(uuid.uuid4())

    conn = await get_connection()
    channel = await conn.channel()
    try:
        _, _, retry_ex = await _ensure_infrastructure(channel)
        message = aio_pika.Message(
            body=json.dumps({**body, "task_id": task_id}).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=task_id,
            headers={"x-retry-count": retry_count},
            expiration=int(delay_seconds * 1000),   # RabbitMQ 按毫秒计
        )
        await retry_ex.publish(message, routing_key=settings.TASK_QUEUE_NAME)
        logger.info("已安排延迟重试 task_id=%s retry=%d delay=%.1fs", task_id, retry_count, delay_seconds)
    finally:
        await channel.close()


async def consume_analysis_tasks(on_message):
    """启动消费循环（worker 进程调用）。

    on_message(message: aio_pika.IncomingMessage) 为异步回调。
    prefetch_count 控制背压：worker 最多同时持有 N 条未 ack 消息，
    超出部分留在 broker，从源头节流。
    """
    _require_aio_pika()
    conn = await get_connection()
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=settings.TASK_PREFETCH_COUNT)
    _, queue, _ = await _ensure_infrastructure(channel)
    await queue.consume(on_message)
    logger.info(
        "RabbitMQ 消费者已启动 queue=%s prefetch=%d",
        settings.TASK_QUEUE_NAME, settings.TASK_PREFETCH_COUNT,
    )
    # 常驻：用永不完成的 Future 阻塞，直到被取消
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("消费者被取消，正在关闭...")
    finally:
        await channel.close()
