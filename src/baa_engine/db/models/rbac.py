"""E3-T3：RBAC 角色模型。

roles 表：将多个 API key 聚合到角色，便于管理批量权限。
role_members 表：角色与 key 的多对多关系（一个 key 可属于多个角色）。
"""

from sqlalchemy import Column, DateTime, Index, String, Text, func

from .base import Base


class Role(Base):
    __tablename__ = "rbac_roles"

    id = Column(String(64), primary_key=True)  # UUID hex
    name = Column(String(50), nullable=False, unique=True, index=True)  # admin / engineer / auditor / custom
    description = Column(Text, nullable=True)
    permission_level = Column(String(20), nullable=False, default="read")  # admin / write / read / custom
    scopes = Column(Text, nullable=True)  # JSON 数组，custom 角色时有效
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class RoleMembership(Base):
    __tablename__ = "rbac_role_members"

    id = Column(String(64), primary_key=True)
    role_id = Column(String(64), nullable=False, index=True)
    key_id = Column(String(64), nullable=False, index=True)
    granted_by = Column(String(64), nullable=False, server_default="system")
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# 联合唯一索引：一个 key 在一个 role 下只有一条记录
Index("uq_role_member", RoleMembership.role_id, RoleMembership.key_id)
