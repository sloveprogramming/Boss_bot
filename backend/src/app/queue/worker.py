"""简历分析 Worker（独立进程）— 消费 RabbitMQ 任务并运行 LangGraph

启动方式：
    python -m app.queue.worker
或在 docker-compose 中作为 backend-worker 服务运行。

高并发防护组合拳：
  - broker 侧：prefetch_count（broker.py 中设置）→ 源头节流，worker 最多同时持 N 条
  - 进程侧：asyncio.Semaphore → 限制实际 LLM/DB 并发，保护下游
  - 重试：指数退避（retry 交换机 TTL）→ 瞬时故障自动恢复，不丢任务
  - 死信：重试耗尽 → 进 DLQ，可审计、可人工重放

每个任务把进度写进 task_progress 表，前端轮询 GET /api/workflow/task/{task_id} 即可。
"""
import asyncio
import json
import logging
import traceback

from app.config import settings
from app.database import async_session_factory, init_db
from app.models import Candidate, TaskProgress, TaskStatus
from app.workflow import RecruitmentState, recruitment_graph
from app.queue.broker import (
    BrokerUnavailable,
    consume_analysis_tasks,
    republish_with_delay,
    close_connection,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("queue.worker")

# 进程内并发信号量：保护 LLM API 与数据库连接，避免单 worker 打爆下游。
# 取值与 broker 的 prefetch 一致，作为第二道防线。
_semaphore = asyncio.Semaphore(settings.TASK_PREFETCH_COUNT)


def _build_initial_state(candidate, resume_text: str, job_description: str) -> RecruitmentState:
    """构造 LangGraph 初始 State（与 API 路由保持一致）。"""
    return {
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "position": candidate.position,
        "email": candidate.email or "",
        "phone": candidate.phone or "",
        "status": candidate.status,
        "pipeline_stage": "resume",
        "resume_text": resume_text or "",
        "job_description": job_description or candidate.position,
        "match_score": candidate.match_score or 0,
        "errors": [],
        "retry_count": 0,
        "notifications_sent": [],
        "messages": [],
    }


async def _update_task(task_id: str, candidate_id: int, **fields):
    """upsert 一条任务进度记录（不存在则创建）。"""
    async with async_session_factory() as db:
        from sqlalchemy import select
        res = await db.execute(select(TaskProgress).where(TaskProgress.task_id == task_id))
        tp = res.scalar_one_or_none()
        if tp is None:
            tp = TaskProgress(task_id=task_id, candidate_id=candidate_id)
            db.add(tp)
        for k, v in fields.items():
            setattr(tp, k, v)
        await db.commit()


async def _handle_message(message):
    """处理单条消息。手动管理 ack/nack/reject 以实现精确重试语义。"""
    import aio_pika
    try:
        body = json.loads(message.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.error("消息格式错误，直接拒绝: %r", message.body[:200])
        await message.reject(requeue=False)   # → 死信队列
        return

    task_id = body.get("task_id")
    candidate_id = body.get("candidate_id")
    resume_text = body.get("resume_text", "")
    job_description = body.get("job_description", "")
    retry_count = int((message.headers or {}).get("x-retry-count", 0) or 0)

    # 标记「已领取」
    await _update_task(
        task_id, candidate_id,
        status=TaskStatus.RECEIVED.value, progress=5,
        current_stage="dequeue", stage_message="Worker 已领取任务",
    )

    # 查候选人（不存在属于致命错误，直接归档失败，不重试）
    async with async_session_factory() as db:
        from sqlalchemy import select
        candidate = (await db.execute(
            select(Candidate).where(Candidate.id == candidate_id)
        )).scalar_one_or_none()

    if candidate is None:
        await _update_task(task_id, candidate_id, status=TaskStatus.FAILURE.value,
                           progress=100, error="候选人不存在")
        await message.ack()
        return

    initial_state = _build_initial_state(candidate, resume_text, job_description)
    await _update_task(task_id, candidate_id, status=TaskStatus.RUNNING.value,
                       progress=10, current_stage="parse_resume",
                       stage_message="开始解析简历")

    try:
        async with _semaphore:
            result_state = await recruitment_graph.ainvoke(initial_state)
    except Exception as e:
        # 可重试的瞬时故障（LLM 限流 / DB 抖动等）
        if retry_count < settings.TASK_MAX_RETRIES:
            backoff = min(
                settings.TASK_RETRY_BACKOFF ** (retry_count + 1),
                settings.TASK_RETRY_BACKOFF_MAX,
            )
            logger.warning(
                "任务 %s 执行失败，%.1fs 后重试 (%d/%d): %s",
                task_id, backoff, retry_count + 1, settings.TASK_MAX_RETRIES, e,
            )
            await _update_task(
                task_id, candidate_id, retries=retry_count + 1,
                status=TaskStatus.RUNNING.value,
                error=f"第{retry_count + 1}次执行失败，准备重试: {e}",
            )
            try:
                await republish_with_delay(body, retry_count + 1, backoff)
            except BrokerUnavailable:
                # retry 队列不可用 → 原消息进死信，避免静默丢失
                await message.reject(requeue=False)
                return
            await message.ack()   # 原始消息完成，重试副本已在 retry 队列排期
            return

        # 重试耗尽 → 标记失败并 reject 进死信队列，便于审计/重放
        tb = traceback.format_exc()
        logger.error("任务 %s 重试耗尽，进入死信队列:\n%s", task_id, tb)
        await _update_task(
            task_id, candidate_id, status=TaskStatus.FAILURE.value, progress=100,
            error=f"重试 {settings.TASK_MAX_RETRIES} 次仍失败:\n{tb}",
        )
        await message.reject(requeue=False)
        return

    # 成功完成
    await _update_task(
        task_id, candidate_id,
        status=TaskStatus.SUCCESS.value, progress=100,
        current_stage="done", stage_message="分析完成",
        result_payload={
            "final_status": result_state.get("status"),
            "match_score": result_state.get("match_score"),
            "job_category": result_state.get("job_category"),
        },
    )
    logger.info(
        "任务 %s 完成 candidate_id=%s status=%s score=%s",
        task_id, candidate_id, result_state.get("status"), result_state.get("match_score"),
    )
    await message.ack()


async def main():
    # 确保数据库表（含 task_progress）存在（worker 是独立进程，不会触发 backend 的 lifespan）
    await init_db()
    logger.info("数据库初始化完成，启动 RabbitMQ 消费者...")

    if not settings.TASK_ENABLED:
        logger.warning("TASK_ENABLED=false，worker 不启动消费（队列功能已禁用）")
        return

    # 连接失败则不断重试，便于 RabbitMQ 晚于 worker 启动的场景
    while True:
        try:
            await consume_analysis_tasks(_handle_message)
            break
        except BrokerUnavailable as e:
            logger.warning("RabbitMQ 暂不可用（%s），5s 后重试...", e)
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("worker 收到取消信号")
            break
        finally:
            await close_connection()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker 被手动中断")
