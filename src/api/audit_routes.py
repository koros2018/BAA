"""E2-T2：系统审计日志查询 API。

GET /api/v1/admin/audit/logs?event_type=&resource_type=&actor_id=&limit=50&cursor=
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.baa_engine.db.database import get_session_factory
from src.baa_engine.db.models.audit_log import AuditLog
from src.api.api_globals import require_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/audit", tags=["System Audit (E2-T2)"])


def _get_db():
    sf = get_session_factory()
    session = sf()
    try:
        yield session
    finally:
        sf.remove()


@router.get("/logs")
async def list_audit_logs(
    event_type: Optional[str] = Query(default=None, description="事件类型过滤"),
    resource_type: Optional[str] = Query(default=None, description="资源类型过滤"),
    actor_id: Optional[str] = Query(default=None, description="操作者 ID 过滤"),
    limit: int = Query(default=50, ge=1, le=200, description="返回条数（最大 200）"),
    cursor: Optional[str] = Query(default=None, description="游标（created_at ISO 字符串）"),
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:read")),
):
    """查询审计日志（仅 admin scope）。"""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())

    if event_type:
        stmt = stmt.where(AuditLog.event_type == event_type)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if cursor:
        try:
            ct = datetime.fromisoformat(cursor)
            stmt = stmt.where(AuditLog.created_at < ct)
        except ValueError:
            pass

    stmt = stmt.limit(limit + 1)
    rows = db.execute(stmt).scalars().all()

    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]

    items = [
        {
            "id": r.id,
            "event_type": r.event_type,
            "actor_id": r.actor_id,
            "actor_role": r.actor_role,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "action": r.action,
            "detail": r.detail,
            "ip_address": r.ip_address,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    next_cursor = rows[-1].created_at.isoformat() if has_next and rows else None

    return {
        "status": "ok",
        "items": items,
        "next_cursor": next_cursor,
        "count": len(items),
    }


@router.get("/logs/{log_id}")
async def get_audit_log(
    log_id: str,
    db: Session = Depends(_get_db),
    _key: str = Depends(require_scope("admin:read")),
):
    """按 ID 查询单条审计日志。"""
    row = db.execute(select(AuditLog).where(AuditLog.id == log_id)).scalar_one_or_none()
    if row is None:
        return {"status": "error", "error_code": "NOT_FOUND", "message": "审计日志不存在"}
    return {
        "status": "ok",
        "item": {
            "id": row.id,
            "event_type": row.event_type,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "action": row.action,
            "detail": row.detail,
            "ip_address": row.ip_address,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }
