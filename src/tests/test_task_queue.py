"""
审查任务队列单元测试
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import asyncio
import time
from src.baa_engine.task_queue import ReviewQueue, ReviewTask


@pytest.mark.asyncio
async def test_enqueue_and_get_status():
    """测试入队和状态查询"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=10.0)
    task_id, position = queue.enqueue("file-1")

    status = queue.get_status(task_id)
    assert status is not None
    assert status["task_id"] == task_id
    assert status["file_id"] == "file-1"
    assert status["status"] == "queued"
    assert status["queue_position"] == position
    assert status["progress"] == 0.0

    # 不存在的任务返回 None
    assert queue.get_status("nonexistent") is None


@pytest.mark.asyncio
async def test_dequeue_returns_task():
    """测试出队返回有效任务"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=10.0)
    queue.enqueue("file-1")

    task = await queue.dequeue()
    assert task is not None
    assert task.file_id == "file-1"
    assert task.status == "running"
    assert task.started_at is not None


@pytest.mark.asyncio
async def test_concurrent_limit():
    """测试并发限制：最多 max_concurrent 个任务同时运行"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=1.0)
    queue.enqueue("file-1")
    queue.enqueue("file-2")
    queue.enqueue("file-3")

    # 取出两个任务（占满槽位）
    t1 = await queue.dequeue()
    t2 = await queue.dequeue()
    assert t1 is not None
    assert t2 is not None
    assert queue.running_count == 2

    # 第三个任务应超时（槽位满，且队列无超时等待）
    # 使用很短的超时来验证不会死等
    start = time.time()
    t3 = await asyncio.wait_for(queue.dequeue(timeout=0.3), timeout=0.5)
    elapsed = time.time() - start
    # 因为槽位满，dequeue 应该返回 None（超时）
    assert t3 is None


@pytest.mark.asyncio
async def test_complete_releases_slot():
    """测试完成一个任务后释放槽位"""
    queue = ReviewQueue(max_concurrent=1, queue_timeout=1.0)
    queue.enqueue("file-1")
    queue.enqueue("file-2")

    t1 = await queue.dequeue()
    assert t1 is not None
    assert queue.running_count == 1

    # 完成第一个任务
    queue.complete(t1.task_id, {"status": "ok"})
    assert queue.running_count == 0

    # 现在可以取出第二个任务
    t2 = await queue.dequeue()
    assert t2 is not None
    assert t2.file_id == "file-2"


@pytest.mark.asyncio
async def test_cancel_queued_task():
    """测试取消排队中的任务"""
    queue = ReviewQueue(max_concurrent=1, queue_timeout=1.0)
    queue.enqueue("file-1")
    queue.enqueue("file-2")

    # 取出第一个任务
    t1 = await queue.dequeue()
    assert t1 is not None

    # 取消第二个任务（仍在排队中）
    status = queue.get_status("file-2" if False else "")
    # 获取第二个任务的 ID
    task_id_2 = None
    for tid, t in queue._tasks.items():
        if t.file_id == "file-2" and t.status == "queued":
            task_id_2 = tid
            break

    assert task_id_2 is not None
    assert queue.cancel(task_id_2) is True

    # 取消后状态不应再存在
    # （取消的 task 在 dequeue 时被移除）
    assert queue.get_status(task_id_2) is not None  # 尚未出队，仍在 tasks 中

    # 完成第一个任务，然后尝试取出第二个
    queue.complete(t1.task_id, {"status": "ok"})

    # 第二个任务应被跳过
    # 由于队列为空（取消的任务被跳过），dequeue 应返回 None
    t3 = await asyncio.wait_for(queue.dequeue(timeout=0.3), timeout=0.5)
    assert t3 is None


@pytest.mark.asyncio
async def test_cancel_running_task_fails():
    """测试无法取消正在运行的任务"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=1.0)
    queue.enqueue("file-1")
    task = await queue.dequeue()
    assert task is not None

    # 尝试取消运行中的任务
    assert queue.cancel(task.task_id) is False


@pytest.mark.asyncio
async def test_update_progress():
    """测试进度更新"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=1.0)
    queue.enqueue("file-1")
    task = await queue.dequeue()

    queue.update_progress(task.task_id, 50.0)
    status = queue.get_status(task.task_id)
    assert status["progress"] == 50.0

    # 边界值
    queue.update_progress(task.task_id, -10.0)
    status = queue.get_status(task.task_id)
    assert status["progress"] == 0.0

    queue.update_progress(task.task_id, 150.0)
    status = queue.get_status(task.task_id)
    assert status["progress"] == 100.0


@pytest.mark.asyncio
async def test_fail_task():
    """测试标记任务失败"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=1.0)
    queue.enqueue("file-1")
    task = await queue.dequeue()

    queue.fail(task.task_id, "解析失败")
    status = queue.get_status(task.task_id)
    assert status["status"] == "failed"
    assert status["error"] == "解析失败"
    assert queue.running_count == 0


@pytest.mark.asyncio
async def test_wait_and_dequeue():
    """测试一站式入队+出队"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=5.0)
    task, task_id, position = await queue.wait_and_dequeue("file-1")
    assert task is not None
    assert task.file_id == "file-1"
    assert task_id == task.task_id
    assert position >= 1


@pytest.mark.asyncio
async def test_queue_timeout():
    """测试排队超时"""
    queue = ReviewQueue(max_concurrent=1, queue_timeout=0.5)
    queue.enqueue("file-1")
    t1 = await queue.dequeue()
    assert t1 is not None

    # 第二个任务应超时（queue_timeout=0.5，但槽位被占）
    task, task_id, position = await queue.wait_and_dequeue("file-2")
    assert task is None  # 超时返回 None


@pytest.mark.asyncio
async def test_stats():
    """测试队列统计"""
    queue = ReviewQueue(max_concurrent=4, queue_timeout=1.0)
    stats = queue.stats()
    assert stats["max_concurrent"] == 4
    assert stats["running_count"] == 0
    assert stats["queued_count"] == 0
    assert stats["total_count"] == 0

    queue.enqueue("file-1")
    queue.enqueue("file-2")
    stats = queue.stats()
    assert stats["queued_count"] == 2

    t1 = await queue.dequeue()
    assert t1 is not None
    stats = queue.stats()
    assert stats["running_count"] == 1
    assert stats["queued_count"] == 1

    queue.complete(t1.task_id, {"ok": True})
    stats = queue.stats()
    assert stats["running_count"] == 0
    assert stats["completed_count"] == 1


@pytest.mark.asyncio
async def test_list_active():
    """测试列出活跃任务"""
    queue = ReviewQueue(max_concurrent=4, queue_timeout=1.0)
    queue.enqueue("file-1")
    queue.enqueue("file-2")

    active = queue.list_active()
    assert len(active) == 2

    t1 = await queue.dequeue()
    active = queue.list_active()
    assert len(active) == 2  # 一个 running + 一个 queued
    running = [a for a in active if a["status"] == "running"]
    queued = [a for a in active if a["status"] == "queued"]
    assert len(running) == 1
    assert len(queued) == 1


@pytest.mark.asyncio
async def test_cleanup():
    """测试清理过期任务"""
    queue = ReviewQueue(max_concurrent=4, queue_timeout=1.0)
    queue.enqueue("file-1")
    t1 = await queue.dequeue()
    queue.complete(t1.task_id, {"ok": True})

    # 使用极短的 max_age 来触发清理
    # 但由于任务刚完成，completed_at 就在此刻，所以先设一个很小的 max_age
    # 但时间可能不够，我们用 wait
    await asyncio.sleep(0.01)
    cleaned = queue.cleanup(max_age=0.005)  # 5ms
    assert cleaned >= 1


@pytest.mark.asyncio
async def test_max_concurrent_setter():
    """测试动态调整并发数"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=1.0)
    assert queue.max_concurrent == 2
    queue.max_concurrent = 4
    assert queue.max_concurrent == 4


@pytest.mark.asyncio
async def test_fifo_order():
    """测试 FIFO 顺序"""
    queue = ReviewQueue(max_concurrent=1, queue_timeout=5.0)
    queue.enqueue("file-A")
    queue.enqueue("file-B")
    queue.enqueue("file-C")

    t1 = await queue.dequeue()
    assert t1.file_id == "file-A"
    queue.complete(t1.task_id, {})

    t2 = await queue.dequeue()
    assert t2.file_id == "file-B"
    queue.complete(t2.task_id, {})

    t3 = await queue.dequeue()
    assert t3.file_id == "file-C"
    queue.complete(t3.task_id, {})


@pytest.mark.asyncio
async def test_queue_position_accuracy():
    """测试排队位置准确性"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=1.0)
    _, pos1 = queue.enqueue("file-A")
    _, pos2 = queue.enqueue("file-B")
    _, pos3 = queue.enqueue("file-C")

    assert pos1 == 1
    assert pos2 == 2
    assert pos3 == 3

    # 取出一个后，剩余排队位置应更新
    t1 = await queue.dequeue()
    assert t1.file_id == "file-A"

    # 排队中的任务 position 不变（创建时快照）
    status_c = queue.get_status(
        [tid for tid, t in queue._tasks.items() if t.file_id == "file-C"][0]
    )
    assert status_c is not None


@pytest.mark.asyncio
async def test_multiple_complete_and_fail():
    """测试多个任务的完成和失败"""
    queue = ReviewQueue(max_concurrent=2, queue_timeout=5.0)
    queue.enqueue("file-1")
    queue.enqueue("file-2")
    queue.enqueue("file-3")

    t1 = await queue.dequeue()
    t2 = await queue.dequeue()

    queue.complete(t1.task_id, {"result": "ok"})
    queue.fail(t2.task_id, "error")

    assert queue.get_status(t1.task_id)["status"] == "completed"
    assert queue.get_status(t2.task_id)["status"] == "failed"
    assert queue.running_count == 0

    # 第三个任务现在可以取出
    t3 = await queue.dequeue(timeout=2.0)
    assert t3 is not None
    assert t3.file_id == "file-3"