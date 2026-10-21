"""T-C1 统一数据层：URL 解析与 engine 工厂单测"""

import pytest

from src.baa_engine.db import (
    dispose_engine,
    get_engine,
    get_session_factory,
    resolve_database_url,
)
from src.baa_engine.db.database import DEFAULT_SQLITE_PATH, DEFAULT_URL_ENV


def test_default_fallback_sqlite(monkeypatch):
    monkeypatch.delenv(DEFAULT_URL_ENV, raising=False)
    url = resolve_database_url()
    assert url == f"sqlite:///{DEFAULT_SQLITE_PATH}"


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv(DEFAULT_URL_ENV, "postgresql+psycopg://u:p@localhost:5433/baa")
    assert resolve_database_url() == "postgresql+psycopg://u:p@localhost:5433/baa"


def test_explicit_wins_over_env(monkeypatch):
    monkeypatch.setenv(DEFAULT_URL_ENV, "postgresql+psycopg://u@localhost/db")
    url = resolve_database_url("sqlite:///D:/tmp/isolated.db")
    assert url == "sqlite:///D:/tmp/isolated.db"


def test_blank_env_falls_back(monkeypatch):
    monkeypatch.setenv(DEFAULT_URL_ENV, "   ")
    monkeypatch.setattr(
        "src.baa_engine.db.database.DEFAULT_SQLITE_PATH", DEFAULT_SQLITE_PATH
    )
    assert resolve_database_url().startswith("sqlite:///")


def test_sqlite_engine_cross_thread():
    """SQLite 回退保留旧行为：check_same_thread=False（连接可跨线程使用）。"""
    import threading

    from sqlalchemy import text

    engine = get_engine("sqlite:///D:/tmp/tc1_thread_probe.db")
    errs = []

    def worker():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:  # pragma: no cover — 断言用
            errs.append(e)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert not errs, errs
    dispose_engine("sqlite:///D:/tmp/tc1_thread_probe.db")


def test_pg_engine_pool_pre_ping(monkeypatch):
    """PG 引擎启用 pool_pre_ping（多副本长连接存活探测）。"""
    engine = get_engine("postgresql+psycopg://u@localhost:5433/tc1_test")
    assert engine.pool._pre_ping is True  # noqa: SLF001 — 仅探测配置
    dispose_engine("postgresql+psycopg://u@localhost:5433/tc1_test")


def test_engine_cached_by_url():
    e1 = get_engine("sqlite:///D:/tmp/tc1_cache_probe.db")
    e2 = get_engine("sqlite:///D:/tmp/tc1_cache_probe.db")
    assert e1 is e2
    sf1 = get_session_factory("sqlite:///D:/tmp/tc1_cache_probe.db")
    sf2 = get_session_factory("sqlite:///D:/tmp/tc1_cache_probe.db")
    assert sf1 is sf2
    dispose_engine("sqlite:///D:/tmp/tc1_cache_probe.db")
    e3 = get_engine("sqlite:///D:/tmp/tc1_cache_probe.db")
    assert e3 is not e1  # dispose 后重建
    dispose_engine("sqlite:///D:/tmp/tc1_cache_probe.db")
