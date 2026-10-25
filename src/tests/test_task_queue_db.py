"""T-C2 无状态化单测：审查任务队列跨实例（副本）共享与原子认领。"""

import asyncio

import pytest

from src.baa_engine.db import dispose_engine
from src.baa_engine.task_queue import ReviewQueue


@pytest.fixture()
def queue_env(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'tasks_state.db').as_posix()}"
    monkeypatch.setenv("BAA_DATABASE_URL", url)
    yield url
    dispose_engine(url)


def _queue(**kwargs) -> ReviewQueue:
    kwargs.setdefault("max_concurrent", 4)
    kwargs.setdefault("queue_timeout", 1.0)
    return ReviewQueue(**kwargs)


@pytest.mark.asyncio
async def test_task_enqueued_by_one_replica_claimed_by_other(queue_env):
    """副本 A 入队的任务，副本 B 可认领执行。"""
    a = _queue()
    b = _queue()
    task_id, position = a.enqueue("file-cross")

    task = await b.dequeue(timeout=2.0)
    assert task is not None
    assert task.task_id == task_id
    assert task.file_id == "file-cross"
    assert task.status == "running"
    assert position >= 1

    # 入队副本也能看到运行状态（读库优先于本地陈旧缓存）
    assert a.get_status(task_id)["status"] == "running"


@pytest.mark.asyncio
async def test_single_task_claimed_once_atomically(queue_env):
    """同一任务只能被一个副本认领（条件 UPDATE 原子性）。"""
    a = _queue()
    b = _queue()
    a.enqueue("file-once")

    results = await asyncio.gather(
        a.dequeue(timeout=0.5),
        b.dequeue(timeout=0.5),
    )
    claimed = [t for t in results if t is not None]
    assert len(claimed) == 1


@pytest.mark.asyncio
async def test_progress_and_completion_visible_across_replicas(queue_env):
    """执行副本的进度/完成状态对入队副本可见。"""
    producer = _queue()
    worker = _queue()
    task_id, _ = producer.enqueue("file-progress")

    task = await worker.dequeue(timeout=2.0)
    assert task is not None

    worker.update_progress(task_id, 42.0)
    assert producer.get_status(task_id)["progress"] == 42.0

    worker.complete(task_id, {"ok": True})
    status = producer.get_status(task_id)
    assert status["status"] == "completed"
    assert worker.running_count == 0


@pytest.mark.asyncio
async def test_cancel_visible_and_skipped_across_replicas(queue_env):
    """副本 A 取消排队任务后，副本 B 不会再认领。"""
    a = _queue()
    b = _queue()
    task_id, _ = a.enqueue("file-cancel")

    assert b.cancel(task_id) is True
    assert a.get_status(task_id)["status"] == "cancelled"
    assert await b.dequeue(timeout=0.4) is None


@pytest.mark.asyncio
async def test_queue_stats_are_global(queue_env):
    """queued 计数为命名空间全局视角（非进程内队列长度）。"""
    a = _queue()
    b = _queue()
    a.enqueue("file-s1")
    a.enqueue("file-s2")

    assert b.stats()["queued_count"] == 2
    assert len(b.list_active()) == 2
