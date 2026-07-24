"""
审查任务队列系统

为 BAA API 审查端点提供基于 asyncio 的排队机制，支持：
- FIFO 排队
- 并发限制（替代原始 asyncio.Semaphore 直接竞争）
- 排队位置查询
- 排队取消
- 进度报告
- 排队超时（408 Request Timeout）
"""

import uuid
import time
import json
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReviewTask:
    """单个审查任务的状态"""

    task_id: str
    file_id: str
    status: str = "queued"  # queued | running | completed | failed
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
    """审查任务队列（内存队列，基于 asyncio）

    - max_concurrent: 最大并发数（默认 4）
    - queue_timeout: 排队超时秒数（默认 300s，超时返回 408）
    - 支持 FIFO 顺序
    - 支持查询排队位置
    - 支持取消排队
    """

    def __init__(self, max_concurrent: int = 4, queue_timeout: float = 300.0):
        self._max_concurrent = max_concurrent
        self._queue_timeout = queue_timeout

        # 等待队列：asyncio.Queue 用于 FIFO 排队
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        # 任务存储：task_id -> ReviewTask
        self._tasks: Dict[str, ReviewTask] = {}
        # 当前正在运行的任务计数
        self._running_count: int = 0
        # 条件变量：通知 dequeue 消费者有新槽位
        self._slot_available: asyncio.Event = asyncio.Event()
        self._slot_available.set()  # 初始时有槽位

        # 用于从队列中取消任务的 Event
        self._cancelled: Dict[str, asyncio.Event] = {}

        # 后台消费者任务
        self._consumer_task: Optional[asyncio.Task] = None

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, value: int) -> None:
        self._max_concurrent = value
        # 可能有更多槽位了，通知等待者
        self._slot_available.set()

    @property
    def running_count(self) -> int:
        return self._running_count

    @property
    def queued_count(self) -> int:
        return self._queue.qsize()

    @property
    def total_count(self) -> int:
        return self.queued_count + self.running_count

    def enqueue(self, file_id: str, priority: int = 0, webhook_url: Optional[str] = None, webhook_type: str = "generic") -> Tuple[str, int]:
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
        task = ReviewTask(
            task_id=task_id,
            file_id=file_id,
            status="queued",
            webhook_url=webhook_url,
            webhook_type=webhook_type,
        )
        self._tasks[task_id] = task

        # 计算排队位置（qsize 是加入前的长度）
        position = self._queue.qsize() + self._running_count + 1
        task.queue_position = position

        self._queue.put_nowait(task_id)

        return task_id, position

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

            # 有槽位，尝试从队列取出任务
            try:
                task_id = await asyncio.wait_for(
                    self._queue.get(), timeout=max(0.1, deadline - time.time())
                )
            except asyncio.TimeoutError:
                return None

            # 检查是否已被取消
            if task_id in self._cancelled:
                cancel_event = self._cancelled.pop(task_id)
                cancel_event.set()
                # 从 tasks 中移除
                self._tasks.pop(task_id, None)
                continue  # 跳过这个任务，取下一个

            task = self._tasks.get(task_id)
            if task is None:
                continue  # 任务已被移除，取下一个

            # 标记为运行中
            task.status = "running"
            task.started_at = time.time()
            self._running_count += 1

            return task

        return None

    async def wait_and_dequeue(
        self, file_id: str, priority: int = 0, webhook_url: Optional[str] = None, webhook_type: str = "generic"
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
        task_id, position = self.enqueue(file_id, priority, webhook_url=webhook_url, webhook_type=webhook_type)
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
        if task is None:
            return False
        if task.status != "queued":
            return False  # 已在运行或已完成，无法取消

        # 标记取消
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
        task = self._tasks.get(task_id)
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

    def update_progress(self, task_id: str, value: float) -> None:
        """更新任务进度"""
        task = self._tasks.get(task_id)
        if task is not None:
            task.progress = max(0.0, min(100.0, value))

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        """标记任务完成"""
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.status = "completed"
        task.completed_at = time.time()
        task.progress = 100.0
        task.result = result
        self._release_slot(task_id)
        # P71: 触发 webhook
        if task.webhook_url:
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
        if task is None:
            return
        task.status = "failed"
        task.completed_at = time.time()
        task.error = error
        self._release_slot(task_id)
        # P71: 触发 webhook
        if task.webhook_url:
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
        to_remove = [
            tid
            for tid, t in self._tasks.items()
            if t.status in ("completed", "failed")
            and t.completed_at is not None
            and (now - t.completed_at) > max_age
        ]
        for tid in to_remove:
            self._tasks.pop(tid, None)
        return len(to_remove)

    def list_active(self) -> List[Dict[str, Any]]:
        """列出所有活跃任务（排队中 + 运行中）"""
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
        """获取队列统计信息"""
        return {
            "max_concurrent": self._max_concurrent,
            "running_count": self._running_count,
            "queued_count": self.queued_count,
            "total_count": self.total_count,
            "completed_count": sum(1 for t in self._tasks.values() if t.status == "completed"),
            "failed_count": sum(1 for t in self._tasks.values() if t.status == "failed"),
        }
