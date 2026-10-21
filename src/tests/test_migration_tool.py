"""T-C1 搬迁工具单测：程序化构造迷你 legacy 三库 → 搬迁 → 幂等与字段断言"""

import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.baa_engine.db import dispose_engine
from src.baa_engine.db.migration_tool import migrate
from src.baa_engine.db.models.history import ReviewHistory

# ── legacy 建表 DDL（与旧模块手写 DDL 一致的最小集） ─────────
HISTORY_DDL = [
    """CREATE TABLE review_history (
        id TEXT PRIMARY KEY, drawing_name TEXT NOT NULL,
        building_type TEXT DEFAULT 'civil', standard TEXT DEFAULT 'GB 50016-2014',
        status TEXT DEFAULT 'success', summary TEXT DEFAULT '{}',
        details TEXT DEFAULT '[]', corrections TEXT DEFAULT '[]',
        file_id TEXT DEFAULT '', team_id TEXT DEFAULT '', project_id TEXT DEFAULT '',
        score REAL DEFAULT 0, violation_count INTEGER DEFAULT 0,
        entity_count INTEGER DEFAULT 0, processing_time_ms INTEGER DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE review_audit_items (
        id TEXT PRIMARY KEY, review_id TEXT NOT NULL, item_index INTEGER NOT NULL,
        function_id TEXT NOT NULL, entity_id TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'unreviewed', user_id TEXT DEFAULT '',
        note TEXT DEFAULT '', reason TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, reviewed_at DATETIME)""",
]
CACHE_DDL = [
    """CREATE TABLE cache_entries (
        cache_key TEXT PRIMARY KEY, cache_type TEXT NOT NULL, value TEXT NOT NULL,
        created_at REAL NOT NULL, expires_at REAL NOT NULL,
        access_count INTEGER DEFAULT 0, last_access_at REAL DEFAULT 0)"""
]
COLLAB_DDL = [
    """CREATE TABLE users (
        id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, email TEXT,
        display_name TEXT, password_hash TEXT NOT NULL, role TEXT,
        avatar_url TEXT, is_active BOOLEAN, created_at REAL, updated_at REAL,
        last_login_at REAL, token TEXT)""",
    """CREATE TABLE teams (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        owner_id TEXT NOT NULL, max_members INTEGER, is_public BOOLEAN,
        created_at REAL, updated_at REAL)""",
    """CREATE TABLE team_members (
        id TEXT PRIMARY KEY, team_id TEXT NOT NULL, user_id TEXT NOT NULL,
        role TEXT, joined_at REAL, invited_by TEXT)""",
]


def _seed(path: Path, ddl: list, rows: list):
    con = sqlite3.connect(str(path))
    for stmt in ddl:
        con.execute(stmt)
    for stmt, params in rows:
        con.execute(stmt, params)
    con.commit()
    con.close()


@pytest.fixture()
def legacy_and_target(tmp_path):
    """构造迷你 legacy 三库 + 干净目标库 URL。"""
    hist = tmp_path / "review_history.db"
    cache_db = tmp_path / "baa_cache.db"
    collab = tmp_path / "baa_collab.db"

    _seed(
        hist,
        HISTORY_DDL,
        [
            (
                "INSERT INTO review_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "rev-1",
                    "plan.dxf",
                    "civil",
                    "GB 50016-2014",
                    "success",
                    json.dumps({"score": 88}, ensure_ascii=False),
                    json.dumps([{"result": "FAIL"}], ensure_ascii=False),
                    json.dumps([{"c": 1}], ensure_ascii=False),
                    "f1",
                    "team-1",
                    "proj-1",
                    88.0,
                    1,
                    10,
                    120,
                    "2026-10-20T10:00:00+00:00",
                    "2026-10-20T10:00:00+00:00",
                ),
            ),
        ],
    )
    _seed(
        hist,
        [],
        [
            (
                "INSERT INTO review_audit_items (id, review_id, item_index, function_id, status)"
                " VALUES (?,?,?,?,?)",
                ("rev-1:0", "rev-1", 0, "DIM-001", "confirmed"),
            ),
        ],
    )
    _seed(
        cache_db,
        CACHE_DDL,
        [
            (
                "INSERT INTO cache_entries VALUES (?,?,?,?,?,?,?)",
                ("k1", "review_result", json.dumps({"v": 1}), 1000.0, 9999.0, 2, 1000.0),
            ),
        ],
    )
    _seed(
        collab,
        COLLAB_DDL,
        [
            (
                "INSERT INTO users (id, username, password_hash, role, is_active, created_at,"
                " updated_at, last_login_at, token) VALUES (?,?,?,?,?,?,?,?,?)",
                ("u1", "alice", "s$h", "user", 1, 1.0, 1.0, 0.0, ""),
            ),
            (
                "INSERT INTO teams (id, name, owner_id, created_at, updated_at)"
                " VALUES (?,?,?,?,?)",
                ("t1", "team-a", "u1", 1.0, 1.0),
            ),
            (
                "INSERT INTO team_members (id, team_id, user_id, role, joined_at)"
                " VALUES (?,?,?,?,?)",
                ("m1", "t1", "u1", "member", 1.0),
            ),
        ],
    )

    target = tmp_path / "target.db"
    url = f"sqlite:///{target.as_posix()}"
    sources = {"history": hist, "cache": cache_db, "collab": collab}
    yield url, sources
    dispose_engine(url)


def test_migrate_copies_all_and_converts(legacy_and_target):
    url, sources = legacy_and_target
    report = migrate(target_url=url, sources=sources)

    assert report["review_history"]["inserted"] == 1
    assert report["review_audit_items"]["inserted"] == 1
    assert report["cache_entries"]["inserted"] == 1
    assert report["users"]["inserted"] == 1
    assert report["teams"]["inserted"] == 1
    assert report["team_members"]["inserted"] == 1

    engine = create_engine(url)
    # JSON 列读出即对象（历史域）——必须经 ORM 模型读（text() 裸查绕过列类型只会得到 TEXT）
    with Session(engine) as sess:
        rh = sess.get(ReviewHistory, "rev-1")
        assert rh.summary == {"score": 88}
        assert rh.details == [{"result": "FAIL"}]
        assert str(rh.created_at).startswith("2026-10-20 10:00:00")
    with engine.connect() as conn:
        # 审计域时间戳转换
        aud = conn.execute(
            text("SELECT created_at IS NOT NULL FROM review_audit_items")
        ).scalar()
        assert aud == 1
        # 缓存 Float epoch 直拷
        ce = conn.execute(
            text("SELECT created_at, expires_at FROM cache_entries WHERE cache_key='k1'")
        ).one()
        assert ce == (1000.0, 9999.0)
    engine.dispose()


def test_migrate_idempotent(legacy_and_target):
    """重复执行：目标行数不变，inserted=0（全部被幂等忽略）。"""
    url, sources = legacy_and_target
    first = migrate(target_url=url, sources=sources)
    second = migrate(target_url=url, sources=sources)
    for table in ("review_history", "review_audit_items", "cache_entries", "users"):
        assert second[table]["inserted"] == 0
        assert second[table]["target_total"] == first[table]["target_total"]


def test_migrate_dry_run_touches_nothing(legacy_and_target):
    url, sources = legacy_and_target
    report = migrate(dry_run=True, target_url=url, sources=sources)
    assert report["review_history"]["source"] == 1
    assert report["review_history"]["inserted"] == 0
    assert report["review_history"]["target_total"] == 0  # 未写入


def test_migrate_missing_source_reported(tmp_path):
    """源缺失不崩溃：报告中标记 error，其余表照常。"""
    url = f"sqlite:///{(tmp_path / 't2.db').as_posix()}"
    report = migrate(
        target_url=url,
        sources={"history": tmp_path / "nope.db", "cache": tmp_path / "nope2.db", "collab": tmp_path / "nope3.db"},
    )
    assert report["review_history"]["error"] == 1
    dispose_engine(url)


def test_migrate_skips_orphan_audit_rows(legacy_and_target):
    """FK 守卫：audit 孤儿行（review_id 不存在）跳过并计数，正常行照搬。"""
    url, sources = legacy_and_target
    con = sqlite3.connect(str(sources["history"]))
    con.execute(
        "INSERT INTO review_audit_items (id, review_id, item_index, function_id, status)"
        " VALUES (?,?,?,?,?)",
        ("orphan:0", "no-such-review", 0, "DIM-001", "unreviewed"),
    )
    con.commit()
    con.close()

    report = migrate(target_url=url, sources=sources)
    audit = report["review_audit_items"]
    assert audit["source"] == 2
    assert audit["skipped"] == 1
    assert audit["inserted"] == 1
    assert audit["target_total"] == 1
    dispose_engine(url)
