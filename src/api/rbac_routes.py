"""E3-T3：RBAC 角色管理 API。

POST /api/v1/admin/rbac/roles        — 创建角色
GET  /api/v1/admin/rbac/roles        — 列出角色
GET  /api/v1/admin/rbac/roles/{id}   — 查询角色详情
DELETE /api/v1/admin/rbac/roles/{id} — 删除角色（需 admin）
POST /api/v1/admin/rbac/roles/{id}/members — 添加成员
DELETE /api/v1/admin/rbac/roles/{id}/members/{key_id} — 移除成员
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.api_globals import require_scope
from src.baa_engine.db.database import get_session_factory
from src.baa_engine.db.models.rbac import Role, RoleMembership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/rbac", tags=["RBAC (E3-T3)"])


def _get_db():
    sf = get_session_factory()
    try:
        yield sf()
    finally:
        sf.remove()


def _parse_scopes(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [s.strip() for s in raw.split(",")]


@router.post("/roles")
async def create_role(
    name: str = Query(..., description="角色名称（唯一）"),
    permission_level: str = Query("read", description="admin | write | read | custom"),
    description: Optional[str] = None,
    scopes_json: Optional[str] = Query(default=None, description="custom 角色的 scope 列表（JSON 字符串）"),
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:write")),
):
    """创建角色。"""
    existing = db.execute(select(Role).where(Role.name == name)).scalar_one_or_none()
    if existing:
        return {"status": "error", "error_code": "DUPLICATE_ROLE", "message": f"角色 '{name}' 已存在"}

    import uuid
    role = Role(
        id=uuid.uuid4().hex,
        name=name,
        description=description,
        permission_level=permission_level,
        scopes=scopes_json,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return {
        "status": "ok",
        "role": {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "permission_level": role.permission_level,
            "scopes": _parse_scopes(role.scopes) if role.scopes else [],
            "member_count": 0,
            "created_at": role.created_at.isoformat() if role.created_at else None,
        },
    }


@router.get("/roles")
async def list_roles(
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:read")),
):
    """列出所有角色。"""
    rows = db.execute(
        select(Role, RoleMembership.role_id)
        .outerjoin(RoleMembership, Role.id == RoleMembership.role_id)
        .order_by(Role.created_at.desc())
    ).all()

    # 聚合成员数
    role_map = {}
    for role, _ in rows:
        rid = role.id
        if rid not in role_map:
            role_map[rid] = {
                "id": rid,
                "name": role.name,
                "description": role.description,
                "permission_level": role.permission_level,
                "scopes": _parse_scopes(role.scopes) if role.scopes else [],
                "member_count": 0,
                "created_at": role.created_at.isoformat() if role.created_at else None,
                "updated_at": role.updated_at.isoformat() if role.updated_at else None,
            }
        role_map[rid]["member_count"] += 1

    return {"status": "ok", "roles": list(role_map.values()), "count": len(role_map)}


@router.get("/roles/{role_id}")
async def get_role(
    role_id: str,
    include_members: bool = Query(default=True),
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:read")),
):
    """查询角色详情。"""
    role = db.execute(select(Role).where(Role.id == role_id)).scalar_one_or_none()
    if role is None:
        return {"status": "error", "error_code": "NOT_FOUND", "message": "角色不存在"}

    members = []
    if include_members:
        rows = db.execute(
            select(RoleMembership, Role.id.label("r_id"))
            .where(RoleMembership.role_id == role_id)
        ).all()
        members = [{"key_id": r[0].key_id, "granted_by": r[0].granted_by} for r in rows]

    return {
        "status": "ok",
        "role": {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "permission_level": role.permission_level,
            "scopes": _parse_scopes(role.scopes) if role.scopes else [],
            "member_count": len(members),
            "members": members,
            "created_at": role.created_at.isoformat() if role.created_at else None,
        },
    }


@router.delete("/roles/{role_id}")
async def delete_role(
    role_id: str,
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:write")),
):
    """删除角色（同时清除成员关系）。"""
    role = db.execute(select(Role).where(Role.id == role_id)).scalar_one_or_none()
    if role is None:
        return {"status": "error", "error_code": "NOT_FOUND", "message": "角色不存在"}

    db.execute(RoleMembership.__table__.delete().where(RoleMembership.role_id == role_id))
    db.delete(role)
    db.commit()
    return {"status": "ok", "message": f"角色 '{role.name}' 已删除"}


@router.post("/roles/{role_id}/members")
async def add_member(
    role_id: str,
    key_id: str = Query(..., description="API key ID"),
    granted_by: str = Query(default="system"),
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:write")),
):
    """将 API key 加入角色。"""
    role = db.execute(select(Role).where(Role.id == role_id)).scalar_one_or_none()
    if role is None:
        return {"status": "error", "error_code": "NOT_FOUND", "message": "角色不存在"}

    import uuid

    existing = db.execute(
        select(RoleMembership).where(
            RoleMembership.role_id == role_id, RoleMembership.key_id == key_id
        )
    ).scalar_one_or_none()
    if existing:
        return {"status": "ok", "message": "成员已存在"}

    membership = RoleMembership(
        id=uuid.uuid4().hex,
        role_id=role_id,
        key_id=key_id,
        granted_by=granted_by,
    )
    db.add(membership)
    db.commit()
    return {"status": "ok", "message": f"key={key_id} 已加入角色 '{role.name}'"}


@router.delete("/roles/{role_id}/members/{key_id}")
async def remove_member(
    role_id: str,
    key_id: str,
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:write")),
):
    """从角色中移除 API key。"""
    row = db.execute(
        select(RoleMembership).where(
            RoleMembership.role_id == role_id, RoleMembership.key_id == key_id
        )
    ).scalar_one_or_none()
    if row is None:
        return {"status": "error", "error_code": "NOT_FOUND", "message": "成员关系不存在"}

    db.delete(row)
    db.commit()
    return {"status": "ok", "message": f"key={key_id} 已从角色中移除"}
