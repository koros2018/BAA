"""审计域模型：review_audit_items（P119 违规审核工作流）。

原复用 data/review_history.db 的第二张表；FK 指向 review_history.id
（SQLite 历史上未强制，PostgreSQL 上将真实约束，搬迁时需保证父行存在）。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, func

from .base import Base


class ReviewAuditItem(Base):
    __tablename__ = "review_audit_items"

    id = Column(String, primary_key=True)  # 形如 "{review_id}:{item_index}"
    review_id = Column(String, ForeignKey("review_history.id"), nullable=False)
    item_index = Column(Integer, nullable=False)
    function_id = Column(String, nullable=False)
    entity_id = Column(String, default="")
    status = Column(String, nullable=False, default="unreviewed")
    user_id = Column(String, default="")
    note = Column(String, default="")
    reason = Column(String, default="")
    created_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime, nullable=True)


# 索引名与旧库保持一致
Index("idx_ri_review", ReviewAuditItem.review_id)
Index("idx_ri_status", ReviewAuditItem.status)
Index("idx_ri_func", ReviewAuditItem.function_id)
