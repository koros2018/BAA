"""BAA 统一数据层（T-C1）。

全项目唯一的 engine/session 工厂入口 + 三域（历史/审计/缓存/协作）统一模型。
- URL 解析：BAA_DATABASE_URL 环境变量优先，显式参数更优先，默认回退 SQLite
- engine 惰性创建（--preload fork 安全）
- 生产建表以 Alembic 为准；ensure_schema 仅作测试/首启兜底
"""

from .database import (
    DEFAULT_URL_ENV,
    dispose_all,
    dispose_engine,
    ensure_schema,
    get_engine,
    get_session_factory,
    resolve_database_url,
)
from .models.base import Base

__all__ = [
    "DEFAULT_URL_ENV",
    "Base",
    "resolve_database_url",
    "get_engine",
    "get_session_factory",
    "ensure_schema",
    "dispose_engine",
    "dispose_all",
]
