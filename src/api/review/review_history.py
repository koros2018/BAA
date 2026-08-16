"""
审查历史记录持久化模块

将审查结果保存到 SQLite，支持查询、分页、删除。
前端审查记录页面从此加载，而非仅依赖浏览器 localStorage。

P112: 增加 team_id/project_id 字段，打通协作系统与审查历史。
"""

import json
import sqlite3
import os
import time
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timezone

# 数据库文件路径
_DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_DB_PATH = _DB_DIR / "review_history.db"


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（线程安全，每个调用创建新连接）"""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db():
    """初始化表结构，向后兼容：已存在的旧表自动增加 team_id/project_id"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS review_history (
                id TEXT PRIMARY KEY,
                drawing_name TEXT NOT NULL,
                building_type TEXT DEFAULT 'civil',
                standard TEXT DEFAULT 'GB 50016-2014',
                status TEXT DEFAULT 'success',
                summary TEXT DEFAULT '{}',
                details TEXT DEFAULT '[]',
                corrections TEXT DEFAULT '[]',
                file_id TEXT DEFAULT '',
                team_id TEXT DEFAULT '',
                project_id TEXT DEFAULT '',
                score REAL DEFAULT 0,
                violation_count INTEGER DEFAULT 0,
                entity_count INTEGER DEFAULT 0,
                processing_time_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        # 向后兼容：旧表先补列，再建索引（列不存在时 CREATE INDEX 会失败）
        cols = [c[1] for c in conn.execute("PRAGMA table_info(review_history)")]
        if "team_id" not in cols:
            conn.execute("ALTER TABLE review_history ADD COLUMN team_id TEXT DEFAULT ''")
        if "project_id" not in cols:
            conn.execute("ALTER TABLE review_history ADD COLUMN project_id TEXT DEFAULT ''")
        # 建索引（此时列已确保存在）
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_history_created ON review_history(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_history_drawing ON review_history(drawing_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_history_team ON review_history(team_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_review_history_project ON review_history(project_id)")
        conn.commit()
    finally:
        conn.close()


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
    _init_db()
    conn = _get_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
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

        conn.execute(
            """INSERT INTO review_history
            (id, drawing_name, building_type, standard, status,
             summary, details, corrections, file_id,
             team_id, project_id,
             score, violation_count, entity_count, processing_time_ms,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                review_id,
                drawing_name,
                building_type,
                standard,
                status,
                json.dumps(summary, ensure_ascii=False),
                json.dumps(details, ensure_ascii=False),
                json.dumps(corrections, ensure_ascii=False),
                file_id,
                team_id,
                project_id,
                score,
                violation_count,
                entity_count,
                processing_time,
                now,
                now,
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


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
    _init_db()
    conn = _get_conn()
    try:
        conditions = []
        params = []
        if drawing_name:
            conditions.append("drawing_name LIKE ?")
            params.append(f"%{drawing_name}%")
        if building_type:
            conditions.append("building_type = ?")
            params.append(building_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if team_id:
            conditions.append("team_id = ?")
            params.append(team_id)
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        # 总数
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM review_history {where}", params
        ).fetchone()
        total = count_row["cnt"] if count_row else 0

        # 分页查询
        rows = conn.execute(
            f"""SELECT id, drawing_name, building_type, standard, status,
                       score, violation_count, entity_count, processing_time_ms,
                       corrections, team_id, project_id, created_at
                FROM review_history {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

        items = []
        for row in rows:
            corrections = json.loads(row["corrections"]) if row["corrections"] else []
            items.append(
                {
                    "id": row["id"],
                    "drawingName": row["drawing_name"],
                    "buildingType": row["building_type"],
                    "standard": row["standard"],
                    "status": row["status"],
                    "score": row["score"],
                    "violationCount": row["violation_count"],
                    "entityCount": row["entity_count"],
                    "processingTimeMs": row["processing_time_ms"],
                    "correctionCount": len(corrections),
                    "teamId": row["team_id"],
                    "projectId": row["project_id"],
                    "reviewedAt": row["created_at"],
                }
            )

        return {"total": total, "items": items}
    finally:
        conn.close()


def get_review_detail(review_id: str) -> Optional[Dict]:
    """获取单条审查记录详情"""
    _init_db()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM review_history WHERE id = ?", (review_id,)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "drawingName": row["drawing_name"],
            "buildingType": row["building_type"],
            "standard": row["standard"],
            "status": row["status"],
            "summary": json.loads(row["summary"]),
            "details": json.loads(row["details"]),
            "corrections": json.loads(row["corrections"]),
            "fileId": row["file_id"],
            "score": row["score"],
            "violationCount": row["violation_count"],
            "entityCount": row["entity_count"],
            "processingTimeMs": row["processing_time_ms"],
            "teamId": row["team_id"],
            "projectId": row["project_id"],
            "reviewedAt": row["created_at"],
        }
    finally:
        conn.close()


def delete_review_history(review_id: str) -> bool:
    """删除单条审查记录"""
    _init_db()
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM review_history WHERE id = ?", (review_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def clear_review_history() -> int:
    """清空所有审查记录，返回删除条数"""
    _init_db()
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM review_history")
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()