"""BAA 协作模块 — 整改记录管理（T-B6 工作流闭环）

驳回后登记整改任务（RectificationRecord），整改方更新进度，复查阶段核销。
复用 CollaborationManager 的会话工厂与项目权限检查，数据落在 baa_collab.db。

端点映射（src/api/collab_routes.py）：
- POST /collab/review-sessions/{sid}/rectifications  批量登记（EDIT）
- GET  /collab/review-sessions/{sid}/rectifications  列表（VIEW）
- PUT  /collab/rectifications/{rid}                  更新状态/备注（COMMENT）
"""

from typing import List, Optional, Tuple

from .manager import CollaborationManager, _check_permission
from .models import ProjectPermission, RectificationRecord, ReviewSession

VALID_RECT_STATUSES = {"pending", "done"}


def create_rectifications(
    mgr: CollaborationManager, session_id: str, user_id: str, items: List[dict]
) -> Tuple[Optional[List[dict]], str]:
    """批量登记整改记录，需项目 EDIT 权限。返回 (records, msg)。"""
    if not items:
        return None, "整改项不能为空"

    db = mgr._get_session()

    try:

        rs = db.query(ReviewSession).filter(ReviewSession.id == session_id).first()

        if not rs:

            return None, "会话不存在"

        perm = mgr._get_project_permission(db, rs.project_id, user_id)

        if not _check_permission(perm, ProjectPermission.EDIT.value):

            return None, "无权限"

        records = []

        for item in items:

            rec = RectificationRecord(
                session_id=session_id,
                clause_id=str(item.get("clause_id", "")),
                entity_id=str(item.get("entity_id", "")),
                action=str(item.get("action", "")),
                owner=str(item.get("owner", "")),
                note=str(item.get("note", "")),
            )

            db.add(rec)

            records.append(rec)

        db.commit()

        return [r.to_dict() for r in records], "success"

    except Exception as e:

        db.rollback()

        return None, str(e)

    finally:

        mgr._close_session(db)


def list_rectifications(
    mgr: CollaborationManager, session_id: str, user_id: str
) -> Tuple[Optional[List[dict]], str]:
    """整改记录列表，需项目 VIEW 权限。返回 (records, msg)。"""
    db = mgr._get_session()

    try:

        rs = db.query(ReviewSession).filter(ReviewSession.id == session_id).first()

        if not rs:

            return None, "会话不存在"

        perm = mgr._get_project_permission(db, rs.project_id, user_id)

        if not _check_permission(perm, ProjectPermission.VIEW.value):

            return None, "无权限"

        rows = (
            db.query(RectificationRecord)
            .filter(RectificationRecord.session_id == session_id)
            .order_by(RectificationRecord.created_at.asc())
            .all()
        )

        return [r.to_dict() for r in rows], "success"

    except Exception as e:

        return None, str(e)

    finally:

        mgr._close_session(db)


def update_rectification(
    mgr: CollaborationManager, rid: str, user_id: str, updates: dict
) -> Tuple[Optional[dict], str]:
    """更新整改记录（status/note/action/owner），需项目 COMMENT 权限。返回 (record, msg)。"""
    db = mgr._get_session()

    try:

        rec = db.query(RectificationRecord).filter(RectificationRecord.id == rid).first()

        if not rec:

            return None, "整改记录不存在"

        rs = db.query(ReviewSession).filter(ReviewSession.id == rec.session_id).first()

        if not rs:

            return None, "会话不存在"

        perm = mgr._get_project_permission(db, rs.project_id, user_id)

        if not _check_permission(perm, ProjectPermission.COMMENT.value):

            return None, "无权限"

        new_status = updates.get("status")

        if new_status is not None and new_status not in VALID_RECT_STATUSES:

            return None, f"不支持的整改状态: {new_status}"

        for key in ("status", "note", "action", "owner"):

            if key in updates:

                setattr(rec, key, updates[key])

        db.commit()

        return rec.to_dict(), "success"

    except Exception as e:

        db.rollback()

        return None, str(e)

    finally:

        mgr._close_session(db)
