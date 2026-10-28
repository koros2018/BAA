"""T-C1 Alembic 迁移单测：upgrade 幂等 + downgrade/upgrade 回路（SQLite 目标）"""

from pathlib import Path

import alembic.command
import alembic.config
import pytest
from sqlalchemy import create_engine, inspect, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    # T-C2 无状态化
    "rate_limit_buckets",
    "api_keys",
    "api_key_usage",
    "review_tasks",
    # D4-T3 计费
    "billing_cycles",
    "billing_alerts",
    # E2-T2 审计日志
    "audit_logs",
}


@pytest.fixture()
def alembic_cfg(tmp_path, monkeypatch):
    db = tmp_path / "mig_test.db"
    monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{db.as_posix()}")
    cfg = alembic.config.Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    return cfg, db


def _tables(db_path: Path) -> set:
    insp = inspect(create_engine(f"sqlite:///{db_path}"))
    return {t for t in insp.get_table_names() if t != "alembic_version"}


def test_upgrade_head_creates_all_tables(alembic_cfg):
    cfg, db = alembic_cfg
    alembic.command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _tables(db)
    # version 表记录 head（0004 = E2-T2 审计日志）
    with create_engine(f"sqlite:///{db}").connect() as conn:
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert ver == "0004"


def test_upgrade_head_idempotent(alembic_cfg):
    """迁移可重复执行：第二次 upgrade no-op 且 schema 不变。"""
    cfg, db = alembic_cfg
    alembic.command.upgrade(cfg, "head")
    tables_first = _tables(db)
    alembic.command.upgrade(cfg, "head")  # no-op
    assert _tables(db) == tables_first


def test_downgrade_base_then_upgrade_rebuilds(alembic_cfg):
    """回滚路径清晰：downgrade base 清空全部表，upgrade head 重建。"""
    cfg, db = alembic_cfg
    alembic.command.upgrade(cfg, "head")
    alembic.command.downgrade(cfg, "base")
    assert _tables(db) == set()
    alembic.command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= _tables(db)
