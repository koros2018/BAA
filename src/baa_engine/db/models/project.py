"""D3-T3 项目域模型：review_projects 表。

追踪项目生命周期：onboarding → first_review → correction → recheck → closed
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# 合法状态流转
ALLOWED_TRANSITIONS = {
    "onboarding": {"first_review"},
    "first_review": {"correction", "closed"},
    "correction": {"recheck"},
    "recheck": {"closed", "correction"},
    "closed": set(),
}


class ReviewProject(Base):
    __tablename__ = "review_projects"

    id = Column(String, primary_key=True)
    project_name = Column(String, nullable=False)
    customer_name = Column(String, default="")
    standard_set_code = Column(String, default="CN-National-v1")
    owner = Column(String, default="")
    status = Column(String, default="onboarding")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)


Index("idx_review_projects_status", ReviewProject.status)
Index("idx_review_projects_customer", ReviewProject.customer_name)
