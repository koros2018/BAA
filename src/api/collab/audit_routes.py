"""
P119 违规审核工作流 — 后端 API

端点:
    GET    /api/v1/audit/items?review_id=     获取该审查所有审核条目
    POST   /api/v1/audit/items                 从 details 批量初始化审核条目
    POST   /api/v1/audit/items/{item_id}/confirm   确认违规
    POST   /api/v1/audit/items/{item_id}/dismiss   驳回（误报，需 reason）
    POST   /api/v1/audit/items/{item_id}/pending   标记待核实
    PATCH  /api/v1/audit/items/{item_id}/note      更新批注
    GET    /api/v1/audit/stats?review_id=           统计
    GET    /api/v1/audit/confirmed?review_id=       已确认条目（整改通知单用）
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.api_globals import verify_api_key
from src.baa_engine.collab.audit import (
    confirm_item,
    create_items_from_review,
    dismiss_item,
    get_confirmed_items,
    get_items,
    get_stats,
    pending_item,
    update_note,
)

router = APIRouter(prefix="/api/v1/audit", tags=["Audit (P119)"])


@router.get("/stats")
def audit_stats(
    review_id: str = Query(..., description="审查记录 ID"),
    api_key: str = Depends(verify_api_key),
):
    """审核统计"""
    stats = get_stats(review_id)
    if stats["total"] == 0:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "该审查暂无审核条目，请先调用 POST /items 初始化",
                "review_id": review_id,
            },
        )
    return {"review_id": review_id, "stats": stats}


@router.get("/items")
def list_audit_items(
    review_id: str = Query(..., description="审查记录 ID"),
    status: str = Query("", description="按状态筛选: unreviewed|confirmed|dismissed|pending"),
    api_key: str = Depends(verify_api_key),
):
    """获取该审查的所有审核条目"""
    items = get_items(review_id, status=status or "")
    return {"review_id": review_id, "total": len(items), "items": items}


@router.post("/items")
def init_audit_items(
    body: dict,
    api_key: str = Depends(verify_api_key),
):
    """从审查结果批量创建审核条目

    body: {"review_id": "...", "details": [...]}
    """
    review_id = body.get("review_id") or body.get("task_id") or str(uuid.uuid4())
    details = body.get("details", body.get("review_details", []))
    if not isinstance(details, list):
        raise HTTPException(status_code=422, detail="details 必须为数组")
    count = create_items_from_review(review_id, details)
    return {"review_id": review_id, "created": count}


@router.post("/items/{item_id}/confirm")
def confirm(
    item_id: str,
    body: Optional[dict] = None,
    api_key: str = Depends(verify_api_key),
):
    """确认违规"""
    user_id = (body or {}).get("user_id", "")
    note = (body or {}).get("note", "")
    item = confirm_item(item_id, user_id=user_id, note=note)
    if item is None:
        raise HTTPException(
            status_code=404, detail={"message": "审核条目不存在", "item_id": item_id}
        )
    return {"ok": True, "item": item}


@router.post("/items/{item_id}/dismiss")
def dismiss(
    item_id: str,
    body: Optional[dict] = None,
    api_key: str = Depends(verify_api_key),
):
    """驳回（误报），reason 必填"""
    body = body or {}
    reason = body.get("reason", "")
    if not reason:
        raise HTTPException(status_code=422, detail="误报（dismissed）必须提供 reason")
    user_id = body.get("user_id", "")
    note = body.get("note", "")
    item = dismiss_item(item_id, reason=reason, user_id=user_id, note=note)
    if item is None:
        raise HTTPException(
            status_code=404, detail={"message": "审核条目不存在", "item_id": item_id}
        )
    return {"ok": True, "item": item, "feedback_recorded": True}


@router.post("/items/{item_id}/pending")
def pending(
    item_id: str,
    body: Optional[dict] = None,
    api_key: str = Depends(verify_api_key),
):
    """标记待核实"""
    user_id = (body or {}).get("user_id", "")
    note = (body or {}).get("note", "")
    item = pending_item(item_id, user_id=user_id, note=note)
    if item is None:
        raise HTTPException(
            status_code=404, detail={"message": "审核条目不存在", "item_id": item_id}
        )
    return {"ok": True, "item": item}


@router.patch("/items/{item_id}/note")
def note(
    item_id: str,
    body: Optional[dict] = None,
    api_key: str = Depends(verify_api_key),
):
    """更新批注，不改变 status"""
    body = body or {}
    note_text = body.get("note", "")
    if not note_text:
        raise HTTPException(status_code=422, detail="note 字段不能为空")
    user_id = body.get("user_id", "")
    item = update_note(item_id, note=note_text, user_id=user_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail={"message": "审核条目不存在", "item_id": item_id}
        )
    return {"ok": True, "item": item}


@router.get("/confirmed")
def get_confirmed(
    review_id: str = Query(..., description="审查记录 ID"),
    api_key: str = Depends(verify_api_key),
):
    """获取已确认违规条目（整改通知单用）"""
    items = get_confirmed_items(review_id)
    return {"review_id": review_id, "count": len(items), "items": items}
