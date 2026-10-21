"""
BAA 统一数据层 — 引擎与会话工厂（T-C1）

全项目唯一的 create_engine 位置：
- URL 解析：显式参数 > BAA_DATABASE_URL 环境变量 > 默认回退 SQLite 单库（data/baa.db）
- SQLite 回退经 event listener 保留 WAL / synchronous=NORMAL；PG 启用 pool_pre_ping
- engine 一律惰性创建并按 URL 缓存（--preload fork 安全：import 时不建任何连接）
"""

import os
import threading
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import scoped_session, sessionmaker

# src/baa_engine/db/database.py → parents[3] = 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "baa.db"

DEFAULT_URL_ENV = "BAA_DATABASE_URL"

_engine_lock = threading.RLock()
_engines: dict = {}
_session_factories: dict = {}


def resolve_database_url(explicit_url=None) -> str:
    """解析数据库 URL：显式参数 > BAA_DATABASE_URL > 默认 SQLite 单库回退。

    显式参数优先于环境变量：测试隔离（tmp_path 传路径）不受环境变量影响。
    """
    if explicit_url:
        return explicit_url
    env_url = os.getenv(DEFAULT_URL_ENV, "").strip()
    if env_url:
        return env_url
    path = DEFAULT_SQLITE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def _is_sqlite(url: str) -> bool:
    return url.strip().lower().startswith("sqlite")


def _apply_sqlite_pragmas(dbapi_conn, _record):
    """SQLite 连接级 PRAGMA：与旧实现（WAL + NORMAL synchronous）保持一致。"""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def get_engine(explicit_url=None, **engine_kwargs) -> Engine:
    """获取（惰性创建的）统一 engine，按 URL 单例。"""
    url = resolve_database_url(explicit_url)
    with _engine_lock:
        eng = _engines.get(url)
        if eng is None:
            kwargs = dict(engine_kwargs)
            if _is_sqlite(url):
                connect_args = dict(kwargs.get("connect_args") or {})
                connect_args.setdefault("check_same_thread", False)
                kwargs["connect_args"] = connect_args
            else:
                kwargs.setdefault("pool_pre_ping", True)
            eng = create_engine(url, **kwargs)
            if _is_sqlite(url):
                event.listen(eng, "connect", _apply_sqlite_pragmas)
            _engines[url] = eng
        return eng


def get_session_factory(explicit_url=None) -> scoped_session:
    """获取（惰性创建的）scoped_session 工厂，按 URL 单例。"""
    url = resolve_database_url(explicit_url)
    with _engine_lock:
        sf = _session_factories.get(url)
        if sf is None:
            sf = scoped_session(sessionmaker(bind=get_engine(explicit_url)))
            _session_factories[url] = sf
        return sf


def ensure_schema(explicit_url=None) -> None:
    """建表兜底（幂等）。

    生产以 Alembic 迁移为准；此处服务于：测试零配置建库、首启无迁移环境。
    """
    from .models.base import Base

    Base.metadata.create_all(get_engine(explicit_url))


def dispose_engine(explicit_url=None) -> None:
    """释放指定 URL 的 engine 与 session 工厂（测试清理用）。"""
    url = resolve_database_url(explicit_url)
    with _engine_lock:
        eng = _engines.pop(url, None)
        _session_factories.pop(url, None)
    if eng is not None:
        eng.dispose()


def dispose_all() -> None:
    """释放全部缓存的 engine 与 session 工厂（pytest 进程退出前调用，
    确保 SQLite 测试库文件不被池化连接锁定，atexit 才能删除）。"""
    with _engine_lock:
        engines = list(_engines.values())
        _engines.clear()
        _session_factories.clear()
    for eng in engines:
        eng.dispose()
