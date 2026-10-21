"""
P119 违规审核工作流 — 审计域（T-C1 统一数据层）

数据库表 review_audit_items（统一模型 src/baa_engine/db/models/audit.py）：
审查结果逐条审核的覆盖层。审核状态变更不修改原始 review_results/review_history，
只产生审计记录。

工作流状态机：
    unreviewed → confirmed | dismissed | pending
    pending    → confirmed | dismissed | unreviewed
    confirmed  → unreviewed  (仅重新审核)
    dismissed  → unreviewed  (仅重新审核)

误报（dismissed）自动写入 feedback_engine 入库，供 P113 黄金标准扩库。

T-C1 变更：原模块级 `_init_db()` import 副作用已移除，改为惰性 ensure_schema；
连接经统一 engine（BAA_DATABASE_URL / 回退 SQLite），多副本共享存储可用。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select, update

from src.baa_engine.db import ensure_schema, get_session_factory
from src.baa_engine.db.models.audit import ReviewAuditItem

logger = logging.getLogger(__name__)

_VALID_STATUSES = {"unreviewed", "confirmed", "dismissed", "pending"}
_INITIAL_STATUS = "unreviewed"


def _session_factory():
    """获取会话工厂（ensure_schema 幂等兜底；生产以 Alembic 为准）。"""
    ensure_schema()
    return get_session_factory()


def _to_dict(item: ReviewAuditItem) -> Dict[str, Any]:
    """ORM → 旧契约 dict（键名与 sqlite3.Row 版完全一致）。"""
    return {
        "id": item.id,
        "review_id": item.review_id,
        "item_index": item.item_index,
        "function_id": item.function_id,
        "entity_id": item.entity_id or "",
        "status": item.status,
        "user_id": item.user_id or "",
        "note": item.note or "",
        "reason": item.reason or "",
        "created_at": item.created_at,
        "reviewed_at": item.reviewed_at,
    }


# ── 核心 API ──────────────────────────────────────────────


def create_items_from_review(
    review_id: str,
    details: List[Dict[str, Any]],
) -> int:
    """从审查结果的 details 数组批量创建审核条目

    每个 FAIL/CONFIRMED 条目创建一个 unreviewed 记录。
    PASS 条目不创建（无需审核）。

    Args:
        review_id: 关联的审查记录 ID
        details: /review 返回的 details 数组

    Returns:
        创建的条目数量
    """
    sf = _session_factory()
    session = sf()
    try:
        count = 0
        for idx, d in enumerate(details):
            result = d.get("result", d.get("status", ""))
            if result not in ("FAIL", "CONFIRMED"):
                continue  # 只创建需要审核的条目
            item_id = f"{review_id}:{idx}"
            function_id = d.get("function_id", d.get("func_id", d.get("clause_id", "")))
            entity_id = str(d.get("entity_id", ""))
            # 与旧 INSERT OR REPLACE 语义一致：同 PK 覆盖
            session.merge(
                ReviewAuditItem(
                    id=item_id,
                    review_id=review_id,
                    item_index=idx,
                    function_id=function_id,
                    entity_id=entity_id,
                    status=_INITIAL_STATUS,
                )
            )
            count += 1
        session.commit()
        logger.info("[P119] 为 review_id=%s 创建了 %d 条审核条目", review_id, count)
        return count
    except Exception:
        session.rollback()
        logger.exception("[P119] 批量创建审核条目失败")
        raise
    finally:
        sf.remove()


def get_items(
    review_id: str,
    status: str = "",
) -> List[Dict[str, Any]]:
    """获取该审查的所有审核条目"""
    sf = _session_factory()
    session = sf()
    try:
        stmt = select(ReviewAuditItem).where(ReviewAuditItem.review_id == review_id)
        if status:
            stmt = stmt.where(ReviewAuditItem.status == status)
        stmt = stmt.order_by(ReviewAuditItem.item_index.asc())
        return [_to_dict(item) for item in session.scalars(stmt).all()]
    finally:
        sf.remove()


def _get_item(item_id: str) -> Optional[Dict[str, Any]]:
    """按 key 获取审计记录。"""
    sf = _session_factory()
    session = sf()
    try:
        item = session.get(ReviewAuditItem, item_id)
        return _to_dict(item) if item else None
    finally:
        sf.remove()


def _update_item(
    item_id: str,
    status: str,
    user_id: str = "",
    note: str = "",
    reason: str = "",
) -> Optional[Dict[str, Any]]:
    """更新审计记录。"""
    if status not in _VALID_STATUSES:
        raise ValueError(f"非法审核状态: {status}（允许: {', '.join(_VALID_STATUSES)}）")

    sf = _session_factory()
    session = sf()
    try:
        item = session.get(ReviewAuditItem, item_id)
        if item is None:
            return None

        item.status = status
        item.reviewed_at = datetime.now(timezone.utc)
        if user_id:
            item.user_id = user_id
        if note:
            item.note = note
        if reason:
            item.reason = reason

        session.commit()
        updated = _to_dict(item)
        logger.info("[P119] 审核条目 %s → %s (user=%s)", item_id, status, user_id or "-")
        return updated
    except Exception:
        session.rollback()
        logger.exception("[P119] 更新审核条目失败")
        raise
    finally:
        sf.remove()


def confirm_item(item_id: str, user_id: str = "", note: str = "") -> Optional[Dict[str, Any]]:
    """确认违规：status=confirmed"""
    return _update_item(item_id, "confirmed", user_id=user_id, note=note)


def dismiss_item(
    item_id: str,
    reason: str,
    user_id: str = "",
    note: str = "",
) -> Optional[Dict[str, Any]]:
    """驳回（误报）：status=dismissed，reason 必填

    误报自动写入 feedback_engine 入库。
    """
    if not reason:
        raise ValueError("误报（dismissed）必须提供 reason")
    item = _get_item(item_id)
    result = _update_item(item_id, "dismissed", user_id=user_id, note=note, reason=reason)
    if item:
        _submit_feedback(item, reason)
    return result


def pending_item(item_id: str, user_id: str = "", note: str = "") -> Optional[Dict[str, Any]]:
    """标记待核实：status=pending"""
    return _update_item(item_id, "pending", user_id=user_id, note=note)


def update_note(item_id: str, note: str, user_id: str = "") -> Optional[Dict[str, Any]]:
    """更新批注，不改变 status"""
    sf = _session_factory()
    session = sf()
    try:
        item = session.get(ReviewAuditItem, item_id)
        if item is None:
            return None
        item.note = note
        item.reviewed_at = datetime.now(timezone.utc)
        if user_id:
            item.user_id = user_id
        session.commit()
        return _to_dict(item)
    except Exception:
        session.rollback()
        logger.exception("[P119] 更新批注失败")
        raise
    finally:
        sf.remove()


def _submit_feedback(item: Dict[str, Any], reason: str) -> None:
    """误报自动写入 feedback_engine"""
    try:
        from src.baa_engine.feedback_engine import FeedbackManager
        from pathlib import Path

        fb = FeedbackManager(Path(__file__).resolve().parent.parent.parent.parent / "data")
        fb.submit(
            task_id=item.get("review_id", ""),
            clause_id=item.get("function_id", ""),
            entity_id=item.get("entity_id", ""),
            entity_type="",
            reason=reason,
            description=f"[P119 audit] 误报驳回: item={item.get('id')}",
            severity="dismissed",
        )
        logger.info(
            "[P119] 误报反馈已入库: item_id=%s func=%s", item["id"], item.get("function_id")
        )
    except Exception as e:
        logger.warning("[P119] 误报反馈入库失败: %s: %s", type(e).__name__, e)


def get_stats(review_id: str) -> Dict[str, int]:
    """获取该审查的审核统计"""
    sf = _session_factory()
    session = sf()
    try:
        total = session.scalar(
            select(func.count()).select_from(ReviewAuditItem).where(
                ReviewAuditItem.review_id == review_id
            )
        )
        rows = session.execute(
            select(ReviewAuditItem.status, func.count())
            .where(ReviewAuditItem.review_id == review_id)
            .group_by(ReviewAuditItem.status)
        ).all()
        return {
            "total": total or 0,
            **{status: cnt for status, cnt in rows},
        }
    finally:
        sf.remove()


def get_confirmed_items(review_id: str) -> List[Dict[str, Any]]:
    """获取已确认的违规条目（用于整改通知单生成）"""
    return get_items(review_id, status="confirmed")
