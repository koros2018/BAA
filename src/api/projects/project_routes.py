"""D3-T3 + E4-T2 项目路由：创建/查询/统计/状态流转 + 审计联动。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from src.api.review.review_routes import verify_api_key
from src.baa_engine.db.database import get_session_factory
from src.baa_engine.db.models.project import ReviewProject, ALLOWED_TRANSITIONS

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Projects"])


class ProjectCreate(BaseModel):
    project_name: str
    customer_name: str = ""
    standard_set_code: str = "CN-National-v1"
    owner: str = ""


class ProjectStatusUpdate(BaseModel):
    status: str


def _to_dict(p: ReviewProject) -> dict:
    return {
        "id": p.id,
        "project_name": p.project_name,
        "customer_name": p.customer_name,
        "standard_set_code": p.standard_set_code,
        "owner": p.owner,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _write_project_audit(project_id: str, action: str, detail: str = ""):
    """写入项目操作审计日志。"""
    from src.api.audit_middleware import write_audit_log

    write_audit_log(
        event_type="project_status_change",
        resource_type="project",
        resource_id=project_id,
        action=action,
        detail=detail,
    )


@router.post("/api/v1/projects")
async def create_project(body: ProjectCreate, api_key: str = Depends(verify_api_key)):
    """创建新项目。"""
    sf = get_session_factory()
    p = ReviewProject(
        id=str(uuid.uuid4()),
        project_name=body.project_name,
        customer_name=body.customer_name,
        standard_set_code=body.standard_set_code,
        owner=body.owner,
        status="onboarding",
    )
    sf.add(p)
    sf.commit()
    sf.refresh(p)
    out = _to_dict(p)
    sf.remove()
    return out


@router.get("/api/v1/projects")
async def list_projects(
    status: Optional[str] = Query(None),
    customer_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(verify_api_key),
):
    """列出项目（支持状态筛选 + 客户名模糊搜索）。"""
    sf = get_session_factory()
    q = sf.query(ReviewProject)
    if status:
        q = q.filter(ReviewProject.status == status)
    if customer_name:
        q = q.filter(ReviewProject.customer_name.like(f"%{customer_name}%"))
    total = q.count()
    rows = q.order_by(ReviewProject.created_at.desc()).offset(offset).limit(limit).all()
    out = {
        "total": total,
        "count": len(rows),
        "offset": offset,
        "limit": limit,
        "projects": [_to_dict(r) for r in rows],
    }
    sf.remove()
    return out


@router.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str, api_key: str = Depends(verify_api_key)):
    """项目详情（含审查统计）。"""
    from src.api.review.review_history import list_review_history

    sf = get_session_factory()
    p = sf.get(ReviewProject, project_id)
    if not p:
        sf.remove()
        raise HTTPException(status_code=404, detail="Project not found")

    # 审查统计
    hist = list_review_history(project_id=project_id, limit=10000)
    items = hist.get("items", [])
    review_count = hist.get("total", len(items))
    # list_review_history 返回 camelCase 字段（violationCount），此处按实际键名读取
    total_violations = sum(i.get("violationCount", 0) for i in items)
    avg_score = (
        sum(i.get("score", 0) for i in items) / len(items) if items else 0.0
    )

    out = {
        **_to_dict(p),
        "review_stats": {
            "total_reviews": review_count,
            "total_violations": total_violations,
            "avg_score": round(avg_score, 2),
        },
        "violation_distribution": _build_violation_distribution(sf, project_id),
    }
    sf.remove()
    return out


def _build_violation_distribution(sf, project_id: str) -> dict:
    """E4-T2：按严重度/条款/实体类型聚合项目历史审查的违规分布。"""
    from src.baa_engine.db.models.history import ReviewHistory

    by_severity: dict = {}
    by_clause: dict = {}
    by_entity_type: dict = {}

    rows = (
        sf.query(ReviewHistory.details)
        .filter(ReviewHistory.project_id == project_id)
        .all()
    )
    for (details,) in rows:
        for d in details or []:
            sev = d.get("severity") or "minor"
            by_severity[sev] = by_severity.get(sev, 0) + 1
            clause = d.get("clause_id") or ""
            if clause:
                by_clause[clause] = by_clause.get(clause, 0) + 1
            etype = d.get("entity_type") or ""
            if etype:
                by_entity_type[etype] = by_entity_type.get(etype, 0) + 1

    return {
        "by_severity": by_severity,
        "by_clause": by_clause,
        "by_entity_type": by_entity_type,
    }


@router.patch("/api/v1/projects/{project_id}/status")
async def update_status(
    project_id: str,
    body: ProjectStatusUpdate,
    api_key: str = Depends(verify_api_key),
):
    """更新项目状态（校验合法状态机流转 + 写审计日志）。"""
    allowed = {"onboarding", "first_review", "correction", "recheck", "closed"}
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    sf = get_session_factory()
    p = sf.get(ReviewProject, project_id)
    if not p:
        sf.remove()
        raise HTTPException(status_code=404, detail="Project not found")
    allowed_next = ALLOWED_TRANSITIONS.get(p.status, set())
    if body.status not in allowed_next:
        sf.remove()
        raise HTTPException(
            status_code=400,
            detail=f"Illegal transition {p.status} -> {body.status}",
        )
    old_status = p.status
    p.status = body.status
    p.updated_at = datetime.now(timezone.utc)
    sf.commit()
    sf.refresh(p)

    # E4-T2：先序列化（避免后续 write_audit_log 的 sf.remove() 导致 DetachedInstanceError）
    out = _to_dict(p)

    # E4-T2：审计联动
    _write_project_audit(
        project_id=project_id,
        action="status_change",
        detail=f"{old_status} -> {body.status}",
    )

    sf.remove()
    return out
