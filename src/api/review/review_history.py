"""
审查历史记录持久化模块（T-C1 统一数据层）

审查结果经统一 SQLAlchemy 模型（src/baa_engine/db/models/history.py）落库：
- 默认库由 BAA_DATABASE_URL / 回退 SQLite 决定，PostgreSQL 共享存储多副本可用
- summary/details/corrections 为 JSON 列，读写即对象（不再手工 json.dumps/loads）
前端审查记录页面从此加载，而非仅依赖浏览器 localStorage。

P112: 增加 team_id/project_id 字段，打通协作系统与审查历史。
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from src.baa_engine.db import ensure_schema, get_session_factory
from src.baa_engine.db.models.history import ReviewHistory


def _session_factory():
    """获取会话工厂（ensure_schema 幂等兜底；生产以 Alembic 为准）。"""
    ensure_schema()
    return get_session_factory()


def save_review_result(
    review_id: str,
    drawing_name: str,
    response_data: dict,
    team_id: str = "",
    project_id: str = "",
) -> bool:
    """保存审查结果到数据库

    Args:
        review_id: 审查记录唯一 ID
        drawing_name: 图纸文件名
        response_data: 审查 API 返回的完整响应数据
        team_id: P112 所属团队 ID（可选，来自 X-Team-Id header）
        project_id: P112 所属项目 ID（可选，来自 X-Project-Id header）

    Returns:
        True 保存成功，False 失败（如重复 ID）
    """
    sf = _session_factory()
    session = sf()
    try:
        now = datetime.now(timezone.utc)
        details = response_data.get("details", [])
        summary = response_data.get("summary", {})
        building_type = response_data.get("building_type", "civil")
        standard = response_data.get("standard", "GB 50016-2014")
        status = response_data.get("status", "success")
        score = summary.get("score", 0)
        violation_count = len(details)
        entity_count = summary.get("total_entities", 0)
        processing_time = response_data.get("processing_time_ms", 0)
        corrections = response_data.get("corrections", [])
        file_id = response_data.get("file_id", "")

        # P112: 从 response_data 兜底读取 team_id/project_id（review_multi_sheet 等会写入）
        if not team_id:
            team_id = response_data.get("team_id", "")
        if not project_id:
            project_id = response_data.get("project_id", "")

        session.add(
            ReviewHistory(
                id=review_id,
                drawing_name=drawing_name,
                building_type=building_type,
                standard=standard,
                status=status,
                summary=summary,
                details=details,
                corrections=corrections,
                file_id=file_id,
                team_id=team_id,
                project_id=project_id,
                score=score,
                violation_count=violation_count,
                entity_count=entity_count,
                processing_time_ms=processing_time,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return False
    finally:
        sf.remove()


def list_review_history(
    limit: int = 50,
    offset: int = 0,
    drawing_name: Optional[str] = None,
    building_type: Optional[str] = None,
    status: Optional[str] = None,
    team_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> Dict:
    """查询审查历史记录

    Returns:
        {"total": int, "items": [dict, ...]}
    """
    sf = _session_factory()
    session = sf()
    try:
        conditions = []
        if drawing_name:
            conditions.append(ReviewHistory.drawing_name.like(f"%{drawing_name}%"))
        if building_type:
            conditions.append(ReviewHistory.building_type == building_type)
        if status:
            conditions.append(ReviewHistory.status == status)
        if team_id:
            conditions.append(ReviewHistory.team_id == team_id)
        if project_id:
            conditions.append(ReviewHistory.project_id == project_id)

        total = session.scalar(
            select(func.count()).select_from(ReviewHistory).where(*conditions)
        )

        rows = session.execute(
            select(
                ReviewHistory.id,
                ReviewHistory.drawing_name,
                ReviewHistory.building_type,
                ReviewHistory.standard,
                ReviewHistory.status,
                ReviewHistory.score,
                ReviewHistory.violation_count,
                ReviewHistory.entity_count,
                ReviewHistory.processing_time_ms,
                ReviewHistory.corrections,
                ReviewHistory.team_id,
                ReviewHistory.project_id,
                ReviewHistory.created_at,
            )
            .where(*conditions)
            .order_by(ReviewHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()

        items = [
            {
                "id": r.id,
                "drawingName": r.drawing_name,
                "buildingType": r.building_type,
                "standard": r.standard,
                "status": r.status,
                "score": r.score,
                "violationCount": r.violation_count,
                "entityCount": r.entity_count,
                "processingTimeMs": r.processing_time_ms,
                "correctionCount": len(r.corrections or []),
                "teamId": r.team_id,
                "projectId": r.project_id,
                "reviewedAt": r.created_at,
            }
            for r in rows
        ]
        return {"total": total or 0, "items": items}
    finally:
        sf.remove()


def get_review_detail(review_id: str) -> Optional[Dict]:
    """获取单条审查记录详情"""
    sf = _session_factory()
    session = sf()
    try:
        r = session.get(ReviewHistory, review_id)
        if r is None:
            return None
        return {
            "id": r.id,
            "drawingName": r.drawing_name,
            "buildingType": r.building_type,
            "standard": r.standard,
            "status": r.status,
            "summary": r.summary or {},
            "details": r.details or [],
            "corrections": r.corrections or [],
            "fileId": r.file_id,
            "score": r.score,
            "violationCount": r.violation_count,
            "entityCount": r.entity_count,
            "processingTimeMs": r.processing_time_ms,
            "teamId": r.team_id,
            "projectId": r.project_id,
            "reviewedAt": r.created_at,
        }
    finally:
        sf.remove()


def delete_review_history(review_id: str) -> bool:
    """删除单条审查记录"""
    sf = _session_factory()
    session = sf()
    try:
        result = session.execute(
            delete(ReviewHistory).where(ReviewHistory.id == review_id)
        )
        session.commit()
        return (result.rowcount or 0) > 0
    finally:
        sf.remove()


def clear_review_history() -> int:
    """清空所有审查记录，返回删除条数"""
    sf = _session_factory()
    session = sf()
    try:
        result = session.execute(delete(ReviewHistory))
        session.commit()
        return result.rowcount or 0
    finally:
        sf.remove()
