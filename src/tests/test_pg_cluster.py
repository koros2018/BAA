"""T-C2 多进程并发验收（pytest -m pg，需 BAA_TEST_PG_URL）。

验收项（用独立进程模拟多副本，共享同一 PostgreSQL）：
1. 限流跨副本一致：4 个进程各自抢同一配额，总放行数恰等于 limit（不超发）
2. 任务跨副本互见 + 原子认领：父进程入队，3 个工作进程认领，每个任务恰被认领一次
3. 密钥/用量跨副本可见：进程 A 建密钥，进程 B 验证并累计用量，进程 C 读到累计值
4. 吞吐随副本数上升：同一任务集，2 副本完成时间显著短于 1 副本

本地环境：D:\\tmp 便携 PG 17.6（端口 5433，库 baa_test）
    BAA_TEST_PG_URL=postgresql+psycopg://baa@localhost:5433/baa_test
"""

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
import sqlalchemy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PG_URL = os.getenv("BAA_TEST_PG_URL", "")

pytestmark = [
    pytest.mark.pg,
    pytest.mark.skipif(not PG_URL, reason="需要 BAA_TEST_PG_URL（便携 PG 验收环境）"),
]


_WORKER_SRC = '''
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, r"__PROJECT_ROOT__")
mode = sys.argv[1]
url = sys.argv[2]
os.environ["BAA_DATABASE_URL"] = url
os.environ["BAA_API_KEY_CACHE_TTL"] = "0"
os.environ["BAA_API_KEYS_PATH"] = sys.argv[-1] + ".json"

from src.baa_engine.db import dispose_all


def _rate():
    subject, limit, tries, window = sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6])
    from src.baa_engine.rate_limit import DistributedRateLimiter

    lim = DistributedRateLimiter(url=url)
    allowed = 0
    for _ in range(tries):
        if lim.check_and_consume(subject, limit, window=window).allowed:
            allowed += 1
    print("ALLOWED", allowed)


def _claim():
    ns, out_path, cost = sys.argv[3], sys.argv[4], float(sys.argv[5])

    async def main():
        from src.baa_engine.task_queue import ReviewQueue

        q = ReviewQueue(max_concurrent=1, queue_timeout=0.3, namespace=ns)
        claimed = []
        idle_since = None
        while True:
            task = await q.dequeue(timeout=0.3)
            if task is not None:
                idle_since = None
                await asyncio.sleep(cost)  # 模拟审查耗时
                claimed.append(task.task_id)
                q.complete(task.task_id, {"ok": True})
                continue
            if q.stats()["queued_count"] == 0:
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since > 0.5:
                    break
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(claimed, f)
        print("CLAIMED", len(claimed))

    asyncio.run(main())


def _throughput():
    ns, ready_path, go_path, cost = sys.argv[3], sys.argv[4], sys.argv[5], float(sys.argv[6])
    Path = __import__("pathlib").Path
    Path(ready_path).write_text("ready", encoding="utf-8")
    while not os.path.exists(go_path):
        time.sleep(0.02)
    t0 = time.time()

    async def main():
        from src.baa_engine.task_queue import ReviewQueue

        q = ReviewQueue(max_concurrent=1, queue_timeout=0.3, namespace=ns)
        idle_since = None
        done = 0
        while True:
            task = await q.dequeue(timeout=0.3)
            if task is not None:
                idle_since = None
                await asyncio.sleep(cost)
                q.complete(task.task_id, {"ok": True})
                done += 1
                continue
            if q.stats()["queued_count"] == 0:
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since > 0.3:
                    break
        print("DONE", done, round(time.time() - t0, 3))

    asyncio.run(main())


def _key_create():
    out_path = sys.argv[3]
    from src.baa_engine.api_key_manager import ApiKeyManager

    km = ApiKeyManager()
    created = km.generate_key(permission="read", label="cross-replica")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"key_id": created["key_id"], "raw_key": created["raw_key"]}, f)
    print("CREATED", created["key_id"])


def _key_use():
    in_path, calls = sys.argv[3], int(sys.argv[4])
    from src.baa_engine.api_key_manager import ApiKeyManager

    data = json.load(open(in_path, encoding="utf-8"))
    km = ApiKeyManager()
    info = km.validate_key(data["raw_key"])
    assert info is not None, "其他副本创建的密钥在本副本不可用"
    assert info["key_id"] == data["key_id"]
    for _ in range(calls):
        km.record_usage(data["raw_key"])
    print("USED", calls, info["permission"])


def _key_stats():
    in_path = sys.argv[3]
    from src.baa_engine.api_key_manager import ApiKeyManager

    data = json.load(open(in_path, encoding="utf-8"))
    stats = ApiKeyManager().get_usage_stats(data["key_id"])
    print("STATS", json.dumps(stats, ensure_ascii=False))


MODES = {
    "rate": _rate,
    "claim": _claim,
    "throughput": _throughput,
    "key-create": _key_create,
    "key-use": _key_use,
    "key-stats": _key_stats,
}
MODES[mode]()
dispose_all()
'''.replace("__PROJECT_ROOT__", str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def _pg_env(monkeypatch):
    """父进程与工作进程共用同一 PG（模拟共享存储），测后释放缓存连接。"""
    monkeypatch.setenv("BAA_DATABASE_URL", PG_URL)
    yield
    from src.baa_engine.db import dispose_engine

    dispose_engine(PG_URL)


@pytest.fixture()
def worker_script(tmp_path):
    path = tmp_path / "tc2_worker.py"
    path.write_text(_WORKER_SRC, encoding="utf-8")
    yield path


def _spawn(script: Path, args, tmp_path: Path):
    scratch = str(tmp_path / f"scratch-{uuid.uuid4().hex[:8]}")
    return subprocess.Popen(  # noqa: S603
        [sys.executable, str(script), *args, scratch],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _collect(procs):
    outs = []
    for i, p in enumerate(procs):
        out, err = p.communicate()
        assert p.returncode == 0, f"worker{i} rc={p.returncode}\n{out}\n{err}"
        outs.append(out)
    return outs


def _raw_engine():
    return sqlalchemy.create_engine(PG_URL)


# ── 验收 1：限流跨副本一致 ────────────────────────────

def test_tc2_01_rate_limit_consistent_across_replicas(worker_script, tmp_path):
    """4 个副本进程共抢 limit=5 的配额：总放行恰 5（存储层原子判定，不超发）。"""
    subject = f"key:pg-test-{uuid.uuid4().hex[:8]}"
    limit, window, replicas, tries = 5, 600.0, 4, 8

    procs = [
        _spawn(worker_script, ["rate", PG_URL, subject, str(limit), str(tries), str(window)], tmp_path)
        for _ in range(replicas)
    ]
    outs = _collect(procs)
    allowed = sum(int(o.split("ALLOWED")[1].split()[0]) for o in outs)

    assert allowed == limit, f"跨副本放行 {allowed} 次，应为 {limit}（超发/漏发）"

    # 收尾清理限流桶
    from src.baa_engine.rate_limit import DistributedRateLimiter

    lim = DistributedRateLimiter(url=PG_URL)
    lim.reset(subject)


# ── 验收 2：任务跨副本互见 + 原子认领 ──────────────────

def test_tc2_02_tasks_claimed_exactly_once(worker_script, tmp_path):
    """父进程入队的 8 个任务被 3 个副本进程各认领一次，无重复、无遗漏。"""
    ns = f"pgq-{uuid.uuid4().hex[:8]}"
    total = 8
    out_files = [str(tmp_path / f"claimed-{i}.json") for i in range(3)]

    from src.baa_engine.task_queue import ReviewQueue

    queue = ReviewQueue(max_concurrent=2, queue_timeout=0.3, namespace=ns)
    enqueued = [queue.enqueue(f"file-{i}")[0] for i in range(total)]
    # 另一副本视角可见（入队进程之外的连接读库统计）
    assert queue.stats()["queued_count"] == total

    procs = [
        _spawn(worker_script, ["claim", PG_URL, ns, out_files[i], "0.05"], tmp_path)
        for i in range(len(out_files))
    ]
    _collect(procs)

    claimed = []
    for f in out_files:
        claimed.extend(json.loads(Path(f).read_text(encoding="utf-8")))

    assert sorted(claimed) == sorted(enqueued), "存在重复认领或遗漏任务"
    assert len(set(claimed)) == total

    engine = _raw_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sqlalchemy.text(
                "SELECT task_id, status, worker_id FROM review_tasks WHERE namespace = :ns"
            ),
            {"ns": ns},
        ).fetchall()
    assert len(rows) == total
    assert all(r[1] == "completed" for r in rows), f"存在未完成任务: {rows}"
    assert len({r[2] for r in rows}) >= 2, "任务未分散到多个副本执行"
    engine.dispose()


# ── 验收 3：密钥/用量跨副本可见 ────────────────────────

def test_tc2_03_api_key_and_usage_visible_across_replicas(worker_script, tmp_path):
    """副本 A 建密钥 → 副本 B 验证并计用量 → 副本 C 读到累计用量。"""
    in_path = str(tmp_path / "key-info.json")

    outs = _collect([_spawn(worker_script, ["key-create", PG_URL, in_path], tmp_path)])
    assert "CREATED" in outs[0]

    outs = _collect(
        [_spawn(worker_script, ["key-use", PG_URL, in_path, "3"], tmp_path)]
    )
    assert "USED 3 read" in outs[0]

    outs = _collect([_spawn(worker_script, ["key-stats", PG_URL, in_path], tmp_path)])
    stats = json.loads(outs[0].split("STATS", 1)[1].strip().splitlines()[0])
    assert stats["total_calls"] == 3, f"跨副本用量应为 3，实际 {stats}"
    assert stats["permission"] == "read"
    assert stats["last_used"]


# ── 验收 4：吞吐随副本数上升 ──────────────────────────

def test_tc2_04_throughput_scales_with_replicas(worker_script, tmp_path):
    """同一任务集（40 个 × 50ms）：2 副本耗时显著短于 1 副本。"""
    total, cost = 40, 0.05

    def run_group(replicas: int) -> float:
        ns = f"tput-{replicas}-{uuid.uuid4().hex[:8]}"
        from src.baa_engine.task_queue import ReviewQueue

        queue = ReviewQueue(max_concurrent=1, queue_timeout=0.3, namespace=ns)
        for i in range(total):
            queue.enqueue(f"tput-file-{i}")

        ready = [str(tmp_path / f"ready-{replicas}-{i}") for i in range(replicas)]
        go = str(tmp_path / f"go-{replicas}")
        procs = [
            _spawn(
                worker_script,
                ["throughput", PG_URL, ns, ready[i], go, str(cost)],
                tmp_path,
            )
            for i in range(replicas)
        ]
        deadline = time.time() + 60
        while not all(os.path.exists(r) for r in ready):
            assert time.time() < deadline, "工作进程未就绪（疑似启动失败）"
            time.sleep(0.05)
        t0 = time.time()
        Path(go).write_text("go", encoding="utf-8")
        outs = _collect(procs)
        elapsed = time.time() - t0

        done = sum(int(o.split("DONE")[1].split()[0]) for o in outs)
        assert done == total, f"{replicas} 副本共处理 {done}/{total} 个任务"
        return elapsed

    one = run_group(1)
    two = run_group(2)

    assert two < one * 0.8, (
        f"吞吐未随副本数上升：1 副本 {one:.2f}s vs 2 副本 {two:.2f}s"
    )
