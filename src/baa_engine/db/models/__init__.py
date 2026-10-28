"""统一模型聚合：import 即把全部表注册进 Base.metadata（Alembic autogenerate 依赖）。

新增模型文件后必须在此 import，否则迁移脚本看不到该表。
"""

from .base import Base  # noqa: F401
from . import apikey, audit, audit_log, billing, cache, collab, history, project, ratelimit, rbac, tasks  # noqa: F401,E402

__all__ = [
    "Base",
    "apikey",
    "audit",
    "billing",
    "cache",
    "collab",
    "history",
    "project",
    "ratelimit",
    "tasks",
]
