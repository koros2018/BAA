"""统一 declarative Base + 命名约定。

naming_convention 是 Alembic/PG 迁移的硬前提：无固定命名时 PG 上约束/索引
随机命名，downgrade 会断链。
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))
