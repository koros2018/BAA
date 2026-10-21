"""历史域模型：review_history（原 data/review_history.db）。

变更点（相对旧 sqlite3 直连 DDL）：
- summary/details/corrections 由 TEXT(JSON 串) 改为 SQLAlchemy JSON 列
  （SQLite 上仍存 TEXT，PG 上为 JSON，读写即对象，调用方不再手工 json.loads）
- created_at/updated_at 由 ISO TEXT 改为 DateTime(timezone=True)
  （旧 ISO 字符串由搬迁工具解析转换）
- team_id/project_id 兼容列（P112）直接进 DDL，不再需要 ALTER TABLE 兜底
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReviewHistory(Base):
    __tablename__ = "review_history"

    id = Column(String, primary_key=True)
    drawing_name = Column(String, nullable=False)
    building_type = Column(String, default="civil")
    standard = Column(String, default="GB 50016-2014")
    status = Column(String, default="success")
    summary = Column(JSON, default=dict)
    details = Column(JSON, default=list)
    corrections = Column(JSON, default=list)
    file_id = Column(String, default="")
    team_id = Column(String, default="")
    project_id = Column(String, default="")
    score = Column(Float, default=0)
    violation_count = Column(Integer, default=0)
    entity_count = Column(Integer, default=0)
    processing_time_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


# 索引名与旧库保持一致
Index("idx_review_history_created", ReviewHistory.created_at)
Index("idx_review_history_drawing", ReviewHistory.drawing_name)
Index("idx_review_history_team", ReviewHistory.team_id)
Index("idx_review_history_project", ReviewHistory.project_id)
