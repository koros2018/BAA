"""D3-T3 项目路由：创建/查询/更新项目状态。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

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
    limit: int = Query(50, ge=1, le=200),
    api_key: str = Depends(verify_api_key),
):
    """列出项目。"""
    sf = get_session_factory()
    q = sf.query(ReviewProject)
    if status:
        q = q.filter(ReviewProject.status == status)
    rows = q.order_by(ReviewProject.created_at.desc()).limit(limit).all()
    out = {"count": len(rows), "projects": [_to_dict(r) for r in rows]}
    sf.remove()
    return out


@router.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str, api_key: str = Depends(verify_api_key)):
    """项目详情。"""
    sf = get_session_factory()
    p = sf.get(ReviewProject, project_id)
    if not p:
        sf.remove()
        raise HTTPException(status_code=404, detail="Project not found")
    out = _to_dict(p)
    sf.remove()
    return out


@router.patch("/api/v1/projects/{project_id}/status")
async def update_status(project_id: str, body: ProjectStatusUpdate, api_key: str = Depends(verify_api_key)):
    """更新项目状态（校验合法状态机流转）。"""
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
    p.status = body.status
    p.updated_at = datetime.now(timezone.utc)
    sf.commit()
    sf.refresh(p)
    out = _to_dict(p)
    sf.remove()
    return out
