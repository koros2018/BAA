"""Alembic 迁移环境（T-C1 统一数据层）。

- target_metadata = 统一 Base.metadata（src/baa_engine/db/models 聚合注册）
- URL 解析：-x db_url= > BAA_DATABASE_URL 环境变量 > 默认回退（resolve_database_url）
- render_as_batch=True：SQLite 无 ALTER 的兼容批次模式（PG 上为直通）
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.db import Base, resolve_database_url  # noqa: E402
from src.baa_engine.db import models as _models  # noqa: F401,E402  # 确保全表注册

config = context.config

if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except (KeyError, ValueError):
        pass  # 无日志配置节时降级为默认日志

target_metadata = Base.metadata


def _get_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get("db_url") or resolve_database_url()


def run_migrations_offline() -> None:
    """离线模式：仅生成 SQL 脚本，不连库。"""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：直连目标库执行迁移。"""
    from sqlalchemy import create_engine

    connectable = create_engine(_get_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
