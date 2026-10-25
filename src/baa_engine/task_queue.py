"""
审查任务队列系统

为 BAA API 审查端点提供基于 asyncio 的排队机制，支持：
- FIFO 排队
- 并发限制（替代原始 asyncio.Semaphore 直接竞争）
- 排队位置查询
- 排队取消
- 进度报告
- 排队超时（408 Request Timeout）

T-C2 无状态化：任务状态落统一库（默认 SQLite 单库，生产为 PostgreSQL），
多副本共享同一队列——任一副本入队的任务可被任一工作副本原子认领，
任务状态/进度/结果跨副本可查。进程内仅保留：
- `_running_count`：本 Pod 的并发闸门（max_concurrent 按副本计）
- `_tasks`：本进程已知任务的缓存（兼容测试与本地快速读取）
"""

import uuid
import time
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# 无 DB 时 dequeue 的本地轮询间隔（秒）：兼作跨副本新任务的发现周期
_POLL_INTERVAL = 0.2


@dataclass
class ReviewTask:
    """单个审查任务的状态"""

    task_id: str
    file_id: str
    status: str = "queued"  # queued | running | completed | failed | cancelled
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    queue_position: int = 0
    progress: float = 0.0  # 0-100
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    webhook_url: Optional[str] = None  # P71: 任务完成后 POST 到此 URL
    webhook_type: str = "generic"  # generic | feishu | dingtalk


class ReviewQueue:
    """审查任务队列（统一库共享状态 + 进程内槽位）

    - max_concurrent: 单个副本的最大并发数（默认 4），跨副本不叠加
    - queue_timeout: 排队超时秒数（默认 300s，超时返回 408）
    - namespace: 任务命名空间（生产固定 default，测试可隔离）
    """

    def __init__(
        self,
        max_concurrent: int = 4,
        queue_timeout: float = 300.0,
        namespace: str = "default",
    ):
        """初始化实例。"""
        self._max_concurrent = max_concurrent
        self._queue_timeout = queue_timeout
        self._namespace = namespace
        self._worker_id = f"worker-{uuid.uuid4().hex[:8]}"

        # 本地唤醒信号（task_id）：避免跨副本发现依赖固定轮询
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        # 本进程已知任务缓存：task_id -> ReviewTask（兼容旧访问）
        self._tasks: Dict[str, ReviewTask] = {}
        # 本副本当前运行任务数（并发闸门是每副本的）
        self._running_count: int = 0
        # 条件变量：通知 dequeue 消费者有新槽位
        self._slot_available: asyncio.Event = asyncio.Event()
        self._slot_available.set()  # 初始时有槽位

        # 用于从队列中取消任务的 Event（本地信号删除，实际以库状态为准）
        self._cancelled: Dict[str, asyncio.Event] = {}

        # 后台消费者任务
        self._consumer_task: Optional[asyncio.Task] = None

        # 统一库可用性（首次失败后退化为纯内存队列，保证服务可用）
        self._db_ok = True
        self._schema_ready = False

    @property
    def max_concurrent(self) -> int:
        """待补充。"""
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, value: int) -> None:
        """待补充。"""
        self._max_concurrent = value
        # 可能有更多槽位了，通知等待者
        self._slot_available.set()

    @property
    def running_count(self) -> int:
        """待补充。"""
        return self._running_count

    @property
    def queued_count(self) -> int:
        """待补充。"""
        count = self._count_db("queued")
        if count is not None:
            return count
        return self._queue.qsize()

    @property
    def total_count(self) -> int:
        """待补充。"""
        return self.queued_count + self.running_count

    # ── 统一库访问 ────────────────────────────────────────

    def _session(self):
        """打开统一库会话（惰性建表）；调用方负责 remove。"""
        from src.baa_engine.db import (
            ensure_schema,
            get_session_factory,
            resolve_database_url,
        )

        url = resolve_database_url()
        if not self._schema_ready:
            ensure_schema(url)
            self._schema_ready = True
        return get_session_factory(url)()

    def _drop_session(self):
        from src.baa_engine.db import get_session_factory

        get_session_factory().remove()

    def _to_task(self, rec) -> ReviewTask:
        return ReviewTask(
            task_id=rec.task_id,
            file_id=rec.file_id,
            status=rec.status,
            created_at=rec.created_at,
            started_at=rec.started_at,
            completed_at=rec.completed_at,
            queue_position=rec.queue_position or 0,
            progress=rec.progress or 0.0,
            result=rec.result,
            error=rec.error,
            webhook_url=rec.webhook_url,
            webhook_type=rec.webhook_type or "generic",
        )

    def _count_db(self, status: str) -> Optional[int]:
        """按状态统计本命名空间任务数；库不可用返回 None。"""
        if not self._db_ok:
            return None
        from sqlalchemy import func, select

        from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

        try:
            session = self._session()
            try:
                return int(
                    session.execute(
                        select(func.count())
                        .select_from(Rec)
                        .where(Rec.namespace == self._namespace, Rec.status == status)
                    ).scalar()
                    or 0
                )
            finally:
                self._drop_session()
        except Exception as e:
            logger.warning("[P71] 任务队列统一库不可用，退化内存队列: %s", e)
            self._db_ok = False
            return None

    def enqueue(
        self,
        file_id: str,
        priority: int = 0,
        webhook_url: Optional[str] = None,
        webhook_type: str = "generic",
    ) -> Tuple[str, int]:
        """将任务加入队列

        Args:
            file_id: 文件标识符
            priority: 优先级（暂未使用，预留）
            webhook_url: 完成后通知的 Webhook URL
            webhook_type: generic | feishu | dingtalk

        Returns:
            (task_id, queue_position) 元组
        """
        task_id = f"review-{uuid.uuid4().hex[:12]}"
        # 排队位置：库中 queued 数 + 本副本运行数（跨副本语义）
        db_queued = self._count_db("queued")
        if db_queued is not None:
            position = db_queued + self._running_count + 1
        else:
            position = self._queue.qsize() + self._running_count + 1

        task = ReviewTask(
            task_id=task_id,
            file_id=file_id,
            status="queued",
            webhook_url=webhook_url,
            webhook_type=webhook_type,
            queue_position=position,
        )
        self._tasks[task_id] = task

        if self._db_ok:
            from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

            try:
                session = self._session()
                try:
                    session.add(
                        Rec(
                            task_id=task_id,
                            namespace=self._namespace,
                            file_id=file_id,
                            status="queued",
                            queue_position=position,
                            progress=0.0,
                            created_at=task.created_at,
                            webhook_url=webhook_url,
                            webhook_type=webhook_type,
                            priority=priority,
                        )
                    )
                    session.commit()
                finally:
                    self._drop_session()
            except Exception as e:
                logger.warning("[P71] 任务入队写库失败，退化内存队列: %s", e)
                self._db_ok = False

        # 本地唤醒信号（同副本可立即消费；跨副本由轮询发现）
        self._queue.put_nowait(task_id)
        return task_id, position

    def _claim_next(self) -> Optional[ReviewTask]:
        """认领库中最早的一个 queued 任务（条件 UPDATE 原子防重复消费）。

        库不可用时退化为本地内存队列取任务。
        """
        if not self._db_ok:
            return self._claim_local()

        from sqlalchemy import select, update

        from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

        try:
            session = self._session()
            try:
                # PG：FOR UPDATE SKIP LOCKED 让并发工作副本错开同一行
                cand = session.execute(
                    select(Rec.task_id)
                    .where(Rec.namespace == self._namespace, Rec.status == "queued")
                    .order_by(Rec.created_at.asc(), Rec.task_id.asc())
                    .limit(1)
                    .with_for_update(skip_locked=True)
                ).scalar()
                if cand is None:
                    return None
                now = time.time()
                res = session.execute(
                    update(Rec)
                    .where(Rec.task_id == cand, Rec.status == "queued")
                    .values(status="running", started_at=now, worker_id=self._worker_id)
                )
                session.commit()
                if res.rowcount != 1:
                    # 被其他副本抢先认领 → 下一轮重试
                    return None
                rec = session.get(Rec, cand)
                return self._to_task(rec)
            finally:
                self._drop_session()
        except Exception as e:
            logger.warning("[P71] 任务认领写库失败，退化内存队列: %s", e)
            self._db_ok = False
            return self._claim_local()

    def _claim_local(self) -> Optional[ReviewTask]:
        """纯内存认领（库不可用时的降级路径）。"""
        while True:
            try:
                task_id = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return None
            if task_id in self._cancelled:
                cancel_event = self._cancelled.pop(task_id)
                cancel_event.set()
                self._tasks.pop(task_id, None)
                continue
            task = self._tasks.get(task_id)
            if task is None or task.status != "queued":
                continue
            task.status = "running"
            task.started_at = time.time()
            return task

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[ReviewTask]:
        """从队列取出一个任务（等待直到有槽位且队列非空）

        Args:
            timeout: 等待超时秒数，默认使用 queue_timeout

        Returns:
            就绪的 ReviewTask，超时返回 None
        """
        effective_timeout = timeout if timeout is not None else self._queue_timeout
        deadline = time.time() + effective_timeout

        while time.time() < deadline:
            # 先检查是否有可用槽位
            if self._running_count >= self._max_concurrent:
                # 等待槽位释放
                try:
                    await asyncio.wait_for(
                        self._slot_available.wait(),
                        timeout=max(0.1, deadline - time.time()),
                    )
                except asyncio.TimeoutError:
                    return None
                self._slot_available.clear()
                continue

            # 等本地信号（同副本入队即时唤醒），同时作为跨副本发现周期
            try:
                await asyncio.wait_for(
                    self._queue.get(), timeout=min(_POLL_INTERVAL, max(0.1, deadline - time.time()))
                )
            except asyncio.TimeoutError:
                pass

            task = self._claim_next()
            if task is None:
                continue

            self._tasks[task.task_id] = task
            self._running_count += 1
            return task

        return None

    async def wait_and_dequeue(
        self,
        file_id: str,
        priority: int = 0,
        webhook_url: Optional[str] = None,
        webhook_type: str = "generic",
    ) -> Tuple[Optional[ReviewTask], str, int]:
        """入队并等待出队（一站式方法）

        Args:
            file_id: 文件标识符
            priority: 优先级
            webhook_url: 完成后通知的 Webhook URL
            webhook_type: generic | feishu | dingtalk

        Returns:
            (task, task_id, position) — task 为 None 表示超时
        """
        task_id, position = self.enqueue(
            file_id, priority, webhook_url=webhook_url, webhook_type=webhook_type
        )
        task = await self.dequeue()
        return task, task_id, position

    def cancel(self, task_id: str) -> bool:
        """取消排队中的任务

        Args:
            task_id: 任务ID

        Returns:
            是否成功取消（仅对排队中的任务有效）
        """
        task = self._tasks.get(task_id)
        if task is not None and task.status != "queued":
            return False  # 已在运行或已完成，无法取消

        if self._db_ok:
            from sqlalchemy import update

            from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

            try:
                session = self._session()
                try:
                    res = session.execute(
                        update(Rec)
                        .where(Rec.task_id == task_id, Rec.status == "queued")
                        .values(status="cancelled")
                    )
                    session.commit()
                    if res.rowcount == 1:
                        if task is not None:
                            task.status = "cancelled"
                        return True
                    return False
                finally:
                    self._drop_session()
            except Exception as e:
                logger.warning("[P71] 任务取消写库失败，退化为本地标记: %s", e)
                self._db_ok = False

        if task is None:
            return False
        # 本地标记取消
        event = asyncio.Event()
        self._cancelled[task_id] = event
        return True

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """查询任务状态

        Args:
            task_id: 任务ID

        Returns:
            {status, queue_position, progress, ...} 或 None
        """
        task = self._read_task(task_id)
        if task is None:
            return None

        return {
            "task_id": task.task_id,
            "file_id": task.file_id,
            "status": task.status,
            "queue_position": task.queue_position,
            "progress": task.progress,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
        }

    def _read_task(self, task_id: str) -> Optional[ReviewTask]:
        """读任务：优先统一库（跨副本最新），失败/缺失时回退本地缓存。"""
        if self._db_ok:
            from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

            try:
                session = self._session()
                try:
                    rec = session.get(Rec, task_id)
                    if rec is not None and rec.namespace == self._namespace:
                        task = self._to_task(rec)
                        self._tasks[task_id] = task
                        return task
                finally:
                    self._drop_session()
            except Exception as e:
                logger.warning("[P71] 任务状态读库失败，回退本地缓存: %s", e)
                self._db_ok = False
        return self._tasks.get(task_id)

    def update_progress(self, task_id: str, value: float) -> None:
        """更新任务进度"""
        progress = max(0.0, min(100.0, value))
        task = self._tasks.get(task_id)
        if task is not None:
            task.progress = progress
        self._write_fields(task_id, progress=progress)

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        """标记任务完成"""
        task = self._tasks.get(task_id)
        now = time.time()
        if task is not None:
            task.status = "completed"
            task.completed_at = now
            task.progress = 100.0
            task.result = result
            self._release_slot(task_id)
        else:
            task = self._read_task(task_id)
            if task is not None:
                task.status = "completed"
                task.completed_at = now
                self._release_slot(task_id)
        self._write_fields(
            task_id,
            status="completed",
            completed_at=now,
            progress=100.0,
            result=result,
            error=None,
        )
        if task is None or not task.webhook_url:
            return
        # P71: 触发 webhook
        from .webhooks import build_webhook_payload, trigger_webhook

        payload = build_webhook_payload(
            task_id=task_id,
            file_id=task.file_id,
            status="completed",
            result=result,
            error=None,
            webhook_type=task.webhook_type,
        )
        trigger_webhook(task.webhook_url, payload)

    def fail(self, task_id: str, error: str) -> None:
        """标记任务失败"""
        task = self._tasks.get(task_id)
        now = time.time()
        if task is not None:
            task.status = "failed"
            task.completed_at = now
            task.error = error
            self._release_slot(task_id)
        else:
            task = self._read_task(task_id)
            if task is not None:
                task.status = "failed"
                task.completed_at = now
                self._release_slot(task_id)
        self._write_fields(
            task_id, status="failed", completed_at=now, error=error
        )
        if task is None or not task.webhook_url:
            return
        # P71: 触发 webhook
        from .webhooks import build_webhook_payload, trigger_webhook

        payload = build_webhook_payload(
            task_id=task_id,
            file_id=task.file_id,
            status="failed",
            result=None,
            error=error,
            webhook_type=task.webhook_type,
        )
        trigger_webhook(task.webhook_url, payload)

    def _write_fields(self, task_id: str, **values) -> None:
        """按字段更新统一库（仅本命名空间内的任务）。"""
        if not self._db_ok:
            return
        from sqlalchemy import update

        from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

        try:
            session = self._session()
            try:
                session.execute(
                    update(Rec)
                    .where(Rec.task_id == task_id, Rec.namespace == self._namespace)
                    .values(**values)
                )
                session.commit()
            finally:
                self._drop_session()
        except Exception as e:
            logger.warning("[P71] 任务状态写库失败: %s", e)
            self._db_ok = False

    def _release_slot(self, task_id: str) -> None:
        """释放一个并发槽位"""
        task = self._tasks.get(task_id)
        if task is not None and task.status in ("completed", "failed"):
            self._running_count = max(0, self._running_count - 1)
            # 通知等待者可能有新槽位
            self._slot_available.set()

    async def run_consumer(self) -> None:
        """后台消费者循环（可选，供外部调用）"""
        while True:
            task = await self.dequeue()
            if task is None:
                # 超时，继续循环
                await asyncio.sleep(0.1)
                continue
            # 返回任务，由外部处理
            yield task  # type: ignore

    def cleanup(self, max_age: float = 3600.0) -> int:
        """清理过期任务

        Args:
            max_age: 最大存活秒数

        Returns:
            清理的任务数
        """
        now = time.time()
        cleaned = 0

        if self._db_ok:
            from sqlalchemy import delete

            from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

            try:
                session = self._session()
                try:
                    res = session.execute(
                        delete(Rec).where(
                            Rec.namespace == self._namespace,
                            Rec.status.in_(("completed", "failed", "cancelled")),
                            Rec.completed_at.isnot(None),
                            Rec.completed_at < now - max_age,
                        )
                    )
                    session.commit()
                    cleaned = max(0, int(res.rowcount or 0))
                finally:
                    self._drop_session()
            except Exception as e:
                logger.warning("[P71] 任务清理写库失败，退化为本地清理: %s", e)
                self._db_ok = False

        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status in ("completed", "failed", "cancelled")
            and t.completed_at is not None
            and (now - t.completed_at) > max_age
        ]
        for tid in to_remove:
            self._tasks.pop(tid, None)
        return max(cleaned, len(to_remove))

    def list_active(self) -> List[Dict[str, Any]]:
        """列出所有活跃任务（排队中 + 运行中，跨副本）"""
        if self._db_ok:
            from sqlalchemy import select

            from src.baa_engine.db.models.tasks import ReviewTaskRecord as Rec

            try:
                session = self._session()
                try:
                    recs = (
                        session.execute(
                            select(Rec)
                            .where(
                                Rec.namespace == self._namespace,
                                Rec.status.in_(("queued", "running")),
                            )
                            .order_by(Rec.created_at.asc(), Rec.task_id.asc())
                        )
                        .scalars()
                        .all()
                    )
                    return [
                        {
                            "task_id": r.task_id,
                            "file_id": r.file_id,
                            "status": r.status,
                            "queue_position": r.queue_position,
                            "progress": r.progress,
                            "created_at": r.created_at,
                        }
                        for r in recs
                    ]
                finally:
                    self._drop_session()
            except Exception as e:
                logger.warning("[P71] 活跃任务读库失败，回退本地缓存: %s", e)
                self._db_ok = False

        return [
            {
                "task_id": t.task_id,
                "file_id": t.file_id,
                "status": t.status,
                "queue_position": t.queue_position,
                "progress": t.progress,
                "created_at": t.created_at,
            }
            for t in self._tasks.values()
            if t.status in ("queued", "running")
        ]

    def stats(self) -> Dict[str, Any]:
        """获取队列统计信息

        running_count 为本副本视角；queued/completed/failed 为命名空间全局。
        """
        completed = self._count_db("completed")
        failed = self._count_db("failed")
        return {
            "max_concurrent": self._max_concurrent,
            "running_count": self._running_count,
            "queued_count": self.queued_count,
            "total_count": self.total_count,
            "completed_count": completed
            if completed is not None
            else sum(1 for t in self._tasks.values() if t.status == "completed"),
            "failed_count": failed
            if failed is not None
            else sum(1 for t in self._tasks.values() if t.status == "failed"),
        }
