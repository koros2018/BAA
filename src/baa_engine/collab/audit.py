"""
P119 违规审核工作流 — 数据模型

数据库表 review_audit_items：审查结果逐条审核的覆盖层。
审核状态变更不修改原始 review_results/review_history，只产生审计记录。

工作流状态机：
    unreviewed → confirmed | dismissed | pending
    pending    → confirmed | dismissed | unreviewed
    confirmed  → unreviewed  (仅重新审核)
    dismissed  → unreviewed  (仅重新审核)

误报（dismissed）自动写入 feedback_engine 入库，供 P113 黄金标准扩库。
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_DB_PATH = _DB_DIR / "review_history.db"  # 复用 review_history DB，不新建文件

_VALID_STATUSES = {"unreviewed", "confirmed", "dismissed", "pending"}
_INITIAL_STATUS = "unreviewed"


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接"""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db() -> None:
    """初始化 review_audit_items 表（向后兼容）"""
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_audit_items (
                id            TEXT PRIMARY KEY,
                review_id     TEXT NOT NULL,
                item_index    INTEGER NOT NULL,
                function_id   TEXT NOT NULL,
                entity_id     TEXT DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'unreviewed',
                user_id       TEXT DEFAULT '',
                note          TEXT DEFAULT '',
                reason        TEXT DEFAULT '',
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                reviewed_at   DATETIME,
                FOREIGN KEY(review_id) REFERENCES review_history(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ri_review ON review_audit_items(review_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ri_status ON review_audit_items(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ri_func ON review_audit_items(function_id)")
        conn.commit()
    finally:
        conn.close()


# ── 自动初始化入口 ────────────────────────────────────────
_init_db()


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
    _init_db()
    conn = _get_conn()
    try:
        count = 0
        for idx, d in enumerate(details):
            result = d.get("result", d.get("status", ""))
            if result not in ("FAIL", "CONFIRMED"):
                continue  # 只创建需要审核的条目
            item_id = f"{review_id}:{idx}"
            function_id = d.get("function_id", d.get("func_id", d.get("clause_id", "")))
            entity_id = str(d.get("entity_id", ""))
            conn.execute(
                "INSERT OR REPLACE INTO review_audit_items "
                "(id, review_id, item_index, function_id, entity_id, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, review_id, idx, function_id, entity_id, _INITIAL_STATUS),
            )
            count += 1
        conn.commit()
        logger.info("[P119] 为 review_id=%s 创建了 %d 条审核条目", review_id, count)
        return count
    except Exception as e:
        conn.rollback()
        logger.error("[P119] 批量创建审核条目失败: %s: %s", type(e).__name__, e)
        raise


def get_items(
    review_id: str,
    status: str = "",
) -> List[Dict[str, Any]]:
    """获取该审查的所有审核条目"""
    _init_db()
    conn = _get_conn()
    try:
        query = "SELECT * FROM review_audit_items WHERE review_id = ?"
        params: List[Any] = [review_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY item_index ASC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_item(item_id: str) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM review_audit_items WHERE id = ?", (item_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _update_item(
    item_id: str,
    status: str,
    user_id: str = "",
    note: str = "",
    reason: str = "",
) -> Optional[Dict[str, Any]]:
    if status not in _VALID_STATUSES:
        raise ValueError(f"非法审核状态: {status}（允许: {', '.join(_VALID_STATUSES)}）")

    conn = _get_conn()
    try:
        item = _get_item(item_id)
        if not item:
            return None

        now = datetime.now(timezone.utc).isoformat()
        query = "UPDATE review_audit_items SET status = ?, reviewed_at = ?"
        params: List[Any] = [status, now]

        if user_id:
            query += ", user_id = ?"
            params.append(user_id)
        if note:
            query += ", note = ?"
            params.append(note)
        if reason:
            query += ", reason = ?"
            params.append(reason)
        query += " WHERE id = ?"
        params.append(item_id)

        conn.execute(query, params)
        conn.commit()

        updated = _get_item(item_id)
        logger.info(
            "[P119] 审核条目 %s → %s (user=%s)", item_id, status, user_id or "-"
        )
        return updated
    except Exception as e:
        conn.rollback()
        logger.error("[P119] 更新审核条目失败: %s: %s", type(e).__name__, e)
        raise
    finally:
        conn.close()


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
    conn = _get_conn()
    try:
        item = _get_item(item_id)
        if not item:
            return None
        now = datetime.now(timezone.utc).isoformat()
        query = "UPDATE review_audit_items SET note = ?, reviewed_at = ?"
        params: List[Any] = [note, now]
        if user_id:
            query += ", user_id = ?"
            params.append(user_id)
        query += " WHERE id = ?"
        params.append(item_id)
        conn.execute(query, params)
        conn.commit()
        return _get_item(item_id)
    except Exception as e:
        conn.rollback()
        logger.error("[P119] 更新批注失败: %s: %s", type(e).__name__, e)
        raise
    finally:
        conn.close()


def _submit_feedback(item: Dict[str, Any], reason: str) -> None:
    """误报自动写入 feedback_engine"""
    try:
        from src.baa_engine.feedback_engine import FeedbackManager

        fb = FeedbackManager(_DB_DIR)
        fb.submit(
            task_id=item.get("review_id", ""),
            clause_id=item.get("function_id", ""),
            entity_id=item.get("entity_id", ""),
            entity_type="",
            reason=reason,
            description=f"[P119 audit] 误报驳回: item={item.get('id')}",
            severity="dismissed",
        )
        logger.info("[P119] 误报反馈已入库: item_id=%s func=%s", item["id"], item.get("function_id"))
    except Exception as e:
        logger.warning("[P119] 误报反馈入库失败: %s: %s", type(e).__name__, e)


def get_stats(review_id: str) -> Dict[str, int]:
    """获取该审查的审核统计"""
    _init_db()
    conn = _get_conn()
    try:
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_audit_items WHERE review_id = ?",
            (review_id,),
        ).fetchone()["cnt"]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM review_audit_items "
            "WHERE review_id = ? GROUP BY status",
            (review_id,),
        ).fetchall()
        return {
            "total": total,
            **{row["status"]: row["cnt"] for row in by_status},
        }
    finally:
        conn.close()


def get_confirmed_items(review_id: str) -> List[Dict[str, Any]]:
    """获取已确认的违规条目（用于整改通知单生成）"""
    return get_items(review_id, status="confirmed")