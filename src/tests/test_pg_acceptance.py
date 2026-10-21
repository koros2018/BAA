"""T-C1 T8：PostgreSQL 验收（pytest -m pg，需环境变量 BAA_TEST_PG_URL）。

四项验收（按定义顺序执行，pytest -m pg 整模块运行）：
1. Alembic upgrade ×2 幂等：13 表 + alembic_version=0001，二次升级无操作
2. 双进程并发三域读写：两个独立进程同时写历史/缓存/协作并回读，互相可见
   （PG 多副本共享存储核心场景，SQLite 文件锁做不到）
3. downgrade base → upgrade head 重建
4. 真实 legacy 三库搬迁行数比对：每表 target_total 增量 == source 行数，二次搬迁幂等

本地环境：D:\\tmp 便携 PG 17.6（initdb -U baa --auth=trust，端口 5433，库 baa_test）
    BAA_TEST_PG_URL=postgresql+psycopg://baa@localhost:5433/baa_test
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PG_URL = os.getenv("BAA_TEST_PG_URL", "")

# 0001_initial 覆盖的 13 张业务表
EXPECTED_TABLES = {
    "review_history",
    "review_audit_items",
    "cache_entries",
    "users",
    "teams",
    "team_members",
    "projects",
    "project_members",
    "review_sessions",
    "rectification_records",
    "review_comments",
    "approval_flows",
    "approval_steps",
}

pytestmark = [
    pytest.mark.pg,
    pytest.mark.skipif(not PG_URL, reason="需要 BAA_TEST_PG_URL（便携 PG 验收环境）"),
]


# ── 辅助 ──────────────────────────────────────────────

def _raw_engine():
    return sqlalchemy.create_engine(PG_URL)


def _table_names(engine):
    return set(sqlalchemy.inspect(engine).get_table_names())


def _table_count(engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(sqlalchemy.text(f"SELECT COUNT(*) FROM {table}")).scalar()  # noqa: S608


def _with_pg_env(fn, *args):
    """临时把 BAA_DATABASE_URL 指向 PG 供 alembic env.py 解析，执行后还原。"""
    old = os.environ.get("BAA_DATABASE_URL")
    os.environ["BAA_DATABASE_URL"] = PG_URL
    try:
        return fn(*args)
    finally:
        if old is None:
            os.environ.pop("BAA_DATABASE_URL", None)
        else:
            os.environ["BAA_DATABASE_URL"] = old


def _alembic(rev: str, down: bool = False):
    from alembic import command
    from alembic.config import Config

    def run(cfg):
        return command.downgrade(cfg, rev) if down else command.upgrade(cfg, rev)

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    _with_pg_env(run, cfg)


def _reset_to_base(engine):
    """脏状态自清理：仅当目标库已有 Alembic 版本记录时降回 base。"""
    if sqlalchemy.inspect(engine).has_table("alembic_version"):
        _alembic("base", down=True)


@pytest.fixture(autouse=True)
def _pg_engine_hygiene():
    """每用例后释放统一数据层对 PG 的缓存 engine，避免跨用例持连。"""
    yield
    from src.baa_engine.db import dispose_engine

    dispose_engine(PG_URL)


# ── 验收 1：upgrade ×2 幂等 ──────────────────────────

def test_pg_01_upgrade_idempotent():
    engine = _raw_engine()
    _reset_to_base(engine)  # 重复验收时先清场
    _alembic("head")
    _alembic("head")  # 二次升级必须为无操作（幂等）
    tables = _table_names(engine)
    assert "alembic_version" in tables
    assert EXPECTED_TABLES <= tables, f"缺表: {EXPECTED_TABLES - tables}"
    with engine.connect() as conn:
        ver = conn.execute(sqlalchemy.text("SELECT version_num FROM alembic_version")).scalar()
    assert ver == "0001"
    engine.dispose()


# ── 验收 2：双进程并发三域读写 ────────────────────────

_WORKER_SRC = '''
import os
import sys

tag = sys.argv[1]
url = sys.argv[2]
sys.path.insert(0, r"__PROJECT_ROOT__")
os.environ["BAA_DATABASE_URL"] = url

from src.baa_engine.db import dispose_all, ensure_schema, get_session_factory
from src.baa_engine.db.models.cache import CacheEntry
from src.baa_engine.db.models.collab import User
from src.baa_engine.db.models.history import ReviewHistory

ensure_schema()  # 已由 Alembic 建表，此处幂等兜底
sf = get_session_factory()
s = sf()
s.add(CacheEntry(cache_key="pgconc-" + tag, cache_type="review_result",
                 value="{\\"v\\":1}", created_at=1000.0, expires_at=9999999999.0))
s.add(ReviewHistory(id="pgconc-" + tag, drawing_name="conc-" + tag + ".dxf", score=88.0))
s.add(User(id="pgconc-u-" + tag, username="pgconc_" + tag, password_hash="s$h"))
s.commit()
assert s.get(CacheEntry, "pgconc-" + tag).cache_type == "review_result"
assert s.get(ReviewHistory, "pgconc-" + tag).drawing_name == "conc-" + tag + ".dxf"
assert s.get(User, "pgconc-u-" + tag).username == "pgconc_" + tag
s.close()
sf.remove()
dispose_all()
print("OK-" + tag)
'''.replace("__PROJECT_ROOT__", str(PROJECT_ROOT))


def test_pg_02_concurrent_three_domains():
    tags = [uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]]
    worker = Path(PROJECT_ROOT) / "_pg_worker_tmp.py"
    worker.write_text(_WORKER_SRC, encoding="utf-8")
    procs = [
        subprocess.Popen(  # noqa: S603
            [sys.executable, str(worker), tag, PG_URL],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for tag in tags
    ]
    try:
        outs = [p.communicate() for p in procs]
        for i, (out, err) in enumerate(outs):
            assert procs[i].returncode == 0, f"worker{i} rc={procs[i].returncode}\n{out}\n{err}"
            assert f"OK-{tags[i]}" in outs[i][0]
    finally:
        worker.unlink(missing_ok=True)

    # 互见性：两进程各自写入的三域行在第三方连接均可见（共享存储生效）
    engine = _raw_engine()
    with engine.connect() as conn:
        for tag in tags:
            assert conn.execute(
                sqlalchemy.text("SELECT 1 FROM cache_entries WHERE cache_key = :k"),
                {"k": "pgconc-" + tag},
            ).fetchone(), f"cache {tag} 不可见"
            assert conn.execute(
                sqlalchemy.text("SELECT 1 FROM review_history WHERE id = :k"),
                {"k": "pgconc-" + tag},
            ).fetchone(), f"history {tag} 不可见"
            assert conn.execute(
                sqlalchemy.text("SELECT 1 FROM users WHERE id = :k"),
                {"k": "pgconc-u-" + tag},
            ).fetchone(), f"user {tag} 不可见"
    engine.dispose()


# ── 验收 3：downgrade 重建 ────────────────────────────

def test_pg_03_downgrade_rebuild():
    engine = _raw_engine()
    assert sqlalchemy.inspect(engine).has_table("review_history")  # 前序用例已建
    _alembic("base", down=True)
    assert not sqlalchemy.inspect(engine).has_table("review_history")
    _alembic("head")
    tables = _table_names(engine)
    assert EXPECTED_TABLES <= tables
    with engine.connect() as conn:
        ver = conn.execute(sqlalchemy.text("SELECT version_num FROM alembic_version")).scalar()
    assert ver == "0001"
    engine.dispose()


# ── 验收 4：真实 legacy 三库搬迁行数比对 ──────────────

@pytest.mark.skipif(
    not (PROJECT_ROOT / "data" / "review_history.db").exists(),
    reason="无真实 legacy 库（data/review_history.db 缺失）",
)
def test_pg_04_real_migration_row_counts():
    from src.baa_engine.db.migration_tool import migrate

    engine = _raw_engine()
    pre = {t: _table_count(engine, t) for t in EXPECTED_TABLES}
    r1 = migrate(target_url=PG_URL)
    r2 = migrate(target_url=PG_URL)  # 二次搬迁：全表 inserted=0（幂等）
    engine.dispose()

    checked = 0
    for table, r in r1.items():
        if r.get("error"):
            continue  # 源库缺表（旧库版本落后），已有 warning，不参与比对
        assert r2[table]["inserted"] == 0, f"{table} 二次搬迁非幂等"
        assert r2[table]["target_total"] == r1[table]["target_total"]
        # 本次净增行数 == 源行数 - 孤儿跳过数（无丢行、无多行）
        expect = r1[table]["source"] - r1[table].get("skipped", 0)
        assert (
            r1[table]["target_total"] - pre[table] == expect
        ), f"{table}: source={r1[table]['source']} skipped={r1[table].get('skipped', 0)} 净增={r1[table]['target_total'] - pre[table]}"
        checked += 1
    assert checked >= 13, f"有效比对表数不足: {checked}"
