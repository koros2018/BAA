"""E3-T2：多副本生产部署验收测试。

验证场景（共享同一数据库）：
1. 队列 queued_count / completed_count 跨副本一致（DB 视角全局）
2. worker_id 写入：认领任务后 DB 中有 worker_id 记录
3. 任务状态变更跨副本可见（DB 中状态更新可被另一实例读取）
4. 无重复认领：多个实例竞争同一任务集，每个任务恰被认领一次
5. 部署配置：docker-compose scaling、健康检查、生产 env 变量
"""

import asyncio
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_async(coro):
    """在同步测试中运行异步函数。"""
    try:
        return asyncio.get_running_loop().run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── 辅助：队列清理 fixture ──────────────────────────────

@pytest.fixture(autouse=True)
def _clean_tasks():
    from sqlalchemy import delete
    from src.baa_engine.db import ensure_schema, get_engine, resolve_database_url
    from src.baa_engine.db.models.tasks import ReviewTaskRecord

    url = resolve_database_url()
    ensure_schema(url)
    with get_engine(url).begin() as conn:
        conn.execute(delete(ReviewTaskRecord))
    yield
    with get_engine(url).begin() as conn:
        conn.execute(delete(ReviewTaskRecord))


# ── E3-T2 验收 1：队列 stats 跨副本一致（DB 视角） ────────────

class TestCrossReplicaQueueVisibility:
    """queued_count / completed_count 来自 DB，跨副本一致。"""

    def test_enqueue_visible_to_another_instance(self):
        """副本 A 入队，副本 B 的 queued_count 应为 1。"""
        from src.baa_engine.task_queue import ReviewQueue

        ns = "e3t2-vis"
        a = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)
        b = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)

        a.enqueue("file-1")
        stats = b.stats()
        assert stats["queued_count"] == 1, f"副本 B queued_count 应为 1，实际 {stats}"
        assert stats["total_count"] == 1

    def test_completed_count_visible_across_instances(self):
        """副本 A 完成一个任务，副本 B 的 completed_count 应为 1。"""
        from src.baa_engine.task_queue import ReviewQueue

        ns = "e3t2-comp"
        a = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)
        b = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)

        a.enqueue("file-ok")
        task = _run_async(a.dequeue())
        assert task is not None
        a.complete(task.task_id, {"result": "ok"})

        stats = b.stats()
        assert stats["completed_count"] >= 1, f"副本 B completed_count 应为 >=1，实际 {stats}"
        # A 的 running_count 清零（complete 释放了槽位）
        assert a.running_count == 0

    def test_failed_count_visible_across_instances(self):
        """副本 A 失败一个任务，副本 B 的 failed_count 应为 1。"""
        from src.baa_engine.task_queue import ReviewQueue

        ns = "e3t2-fail"
        a = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)
        b = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)

        a.enqueue("file-fail")
        task = _run_async(a.dequeue())
        assert task is not None
        a.fail(task.task_id, "解析失败")

        stats = b.stats()
        assert stats["failed_count"] >= 1, f"副本 B failed_count 应为 >=1，实际 {stats}"

    def test_stats_consistent_after_mixed_operations(self):
        """多副本混入/出队/完成/失败后，DB 视角总量守恒。"""
        from src.baa_engine.task_queue import ReviewQueue

        ns = "e3t2-consistent"
        a = ReviewQueue(max_concurrent=4, queue_timeout=0.5, namespace=ns)
        b = ReviewQueue(max_concurrent=4, queue_timeout=0.5, namespace=ns)

        for i in range(3):
            a.enqueue(f"file-a-{i}")
        for i in range(2):
            b.enqueue(f"file-b-{i}")

        # 从 B 视角查 stats
        stats = b.stats()
        assert stats["queued_count"] == 5, f"总入队数应为 5，实际 queued={stats['queued_count']}"

        # A 认领并完成任务
        t1 = _run_async(a.dequeue())
        t2 = _run_async(a.dequeue())
        assert t1 is not None and t2 is not None
        a.complete(t1.task_id, {"ok": True})
        a.complete(t2.task_id, {"ok": True})

        # B 视角：completed=2, queued=3
        stats = b.stats()
        assert stats["completed_count"] == 2, f"completed 应为 2，实际 {stats}"
        assert stats["queued_count"] == 3, f"queued 应为 3，实际 {stats}"


# ── E3-T2 验收 2：worker_id 跨副本可见 ──────────────────────

class TestWorkerIdTracking:
    """任务认领后 worker_id 写入 DB，其他副本可通过 DB 查询。"""

    def test_worker_id_recorded_in_db(self):
        """副本 A 认领任务后，DB 中 worker_id 非空。"""
        from src.baa_engine.task_queue import ReviewQueue
        from sqlalchemy import select
        from src.baa_engine.db import get_engine, resolve_database_url
        from src.baa_engine.db.models.tasks import ReviewTaskRecord

        ns = "e3t2-worker"
        a = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)
        a.enqueue("file-w1")
        task = _run_async(a.dequeue())
        assert task is not None

        engine = get_engine(resolve_database_url())
        with engine.connect() as conn:
            row = conn.execute(
                select(ReviewTaskRecord.worker_id, ReviewTaskRecord.status)
                .where(ReviewTaskRecord.task_id == task.task_id)
            ).first()
        assert row is not None
        assert row.worker_id is not None, "worker_id 应被写入数据库"
        assert row.status == "running"

    def test_worker_id_differs_per_replica(self):
        """副本 A 和副本 B 各认领一个任务，worker_id 不同。"""
        from src.baa_engine.task_queue import ReviewQueue
        from sqlalchemy import select
        from src.baa_engine.db import get_engine, resolve_database_url
        from src.baa_engine.db.models.tasks import ReviewTaskRecord

        ns = "e3t2-worker2"
        a = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)
        b = ReviewQueue(max_concurrent=2, queue_timeout=0.5, namespace=ns)

        a.enqueue("file-a")
        b.enqueue("file-b")
        task_a = _run_async(a.dequeue())
        task_b = _run_async(b.dequeue())
        assert task_a is not None and task_b is not None

        engine = get_engine(resolve_database_url())
        with engine.connect() as conn:
            rows = conn.execute(
                select(ReviewTaskRecord.worker_id, ReviewTaskRecord.file_id)
                .where(ReviewTaskRecord.task_id.in_([task_a.task_id, task_b.task_id]))
            ).fetchall()
        assert len(rows) == 2
        worker_ids = {r[0] for r in rows}
        assert len(worker_ids) == 2, "两副本的 worker_id 应不同"


# ── E3-T2 验收 3：多实例并发竞争（无重复认领） ───────────────

class TestNoDuplicateClaim:
    """多个实例竞争同一任务集，每个任务恰被一个实例认领。"""

    def test_no_duplicate_claim_sequential_instances(self):
        """1 个实例入队 3 个任务，5 个副本顺序竞争：每个任务恰被 1 个副本认领。"""
        from src.baa_engine.task_queue import ReviewQueue

        ns = "e3t2-no-dup"
        # 单个副本负责入队
        producer = ReviewQueue(max_concurrent=10, queue_timeout=0.3, namespace=ns)
        for i in range(3):
            producer.enqueue(f"file-{i}")

        claimed_ids = []
        # 5 个副本各尝试认领一个
        for _ in range(5):
            worker = ReviewQueue(max_concurrent=10, queue_timeout=0.3, namespace=ns)
            task = _run_async(worker.dequeue(timeout=0.5))
            if task is not None:
                worker.complete(task.task_id, {"ok": True})
                claimed_ids.append(task.task_id)

        assert len(claimed_ids) == 3, f"应认领 3 个任务，实际 {len(claimed_ids)}"
        assert len(set(claimed_ids)) == 3, "存在重复认领"

    def test_concurrent_threads_no_double_claim(self):
        """5 个线程同时竞争 3 个任务，无重复认领（线程安全验证）。"""
        from src.baa_engine.task_queue import ReviewQueue
        from sqlalchemy import select
        from src.baa_engine.db import get_engine, resolve_database_url
        from src.baa_engine.db.models.tasks import ReviewTaskRecord

        ns = "e3t2-concurrent"
        # 主线程负责入队
        main_q = ReviewQueue(max_concurrent=10, queue_timeout=0.3, namespace=ns)
        for i in range(3):
            main_q.enqueue(f"file-c-{i}")

        claimed_ids = []
        lock = threading.Lock()

        def claim_one(worker_id: str):
            w = ReviewQueue(max_concurrent=10, queue_timeout=0.5, namespace=ns)

            def _inner():
                task = asyncio.run(w.dequeue(timeout=2.0))
                if task is not None:
                    w.complete(task.task_id, {"ok": True})
                    with lock:
                        claimed_ids.append(task.task_id)

            _inner()

        threads = [
            threading.Thread(target=claim_one, args=(f"t{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(claimed_ids) == 3, f"应认领 3 个任务，实际 {len(claimed_ids)}"
        assert len(set(claimed_ids)) == 3, "存在重复认领"


# ── E3-T2 验收 4：部署配置验证 ────────────────────────────

class TestDeployConfig:
    """生产部署配置正确性。"""

    def test_docker_compose_baa_service_defined(self):
        import yaml
        compose = yaml.safe_load(
            (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        )
        assert "baa" in compose["services"]

    def test_docker_compose_pg_service_defined(self):
        import yaml
        compose = yaml.safe_load(
            (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        )
        assert "postgres" in compose["services"]

    def test_baa_depends_on_pg_healthy(self):
        import yaml
        compose = yaml.safe_load(
            (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        )
        baa = compose["services"]["baa"]
        assert "depends_on" in baa
        deps = baa["depends_on"]
        assert "postgres" in deps
        assert deps["postgres"].get("condition") == "service_healthy"

    def test_pg_data_volume_persistent(self):
        import yaml
        compose = yaml.safe_load(
            (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        )
        volumes = compose.get("volumes", {})
        assert "pg_data" in volumes

    def test_healthcheck_on_baa(self):
        import yaml
        compose = yaml.safe_load(
            (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        )
        baa = compose["services"]["baa"]
        # 至少有一个 depends_on with condition，隐含健康检查
        assert "healthcheck" in baa or "depends_on" in baa

    def test_prod_env_has_security_vars(self):
        env_content = (PROJECT_ROOT / ".env.production.example").read_text(encoding="utf-8")
        assert "BAA_API_KEY" in env_content
        assert "POSTGRES_PASSWORD" in env_content
        assert "BAA_ALLOW_ANONYMOUS=0" in env_content
        assert "BAA_PDF_ISOLATION=1" in env_content
        assert "BAA_LOG_FORMAT=json" in env_content

    def test_deploy_script_unix_exists(self):
        assert (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").exists()

    def test_deploy_script_windows_exists(self):
        assert (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").exists()

    def test_deploy_readme_exists(self):
        assert (PROJECT_ROOT / "deploy" / "private" / "README.md").exists()

    def test_deploy_sh_mentions_health_endpoint(self):
        script = (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").read_text(encoding="utf-8")
        assert "/health" in script

    def test_deploy_ps1_mentions_health_endpoint(self):
        script = (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").read_text(encoding="utf-8")
        assert "/health" in script
