"""E2-T2：系统审计日志模型。

与 review_audit_items（前端违规审核工作流）不同，此表记录引擎级操作审计，
用于合规举证和纠纷处理。
"""

from sqlalchemy import Column, DateTime, Index, String, Text, func

from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True)  # UUID hex
    event_type = Column(String(50), nullable=False, index=True)  # review_started / violation_confirmed / etc.
    actor_id = Column(String(64), nullable=False, server_default="", index=True)  # API key / user id
    actor_role = Column(String(20), nullable=False, server_default="system")  # system / admin / user
    resource_type = Column(String(50), nullable=False, index=True)  # review / violation / project
    resource_id = Column(String(255), nullable=False, server_default="", index=True)
    action = Column(String(50), nullable=False)  # create / update / confirm / dismiss
    detail = Column(Text, nullable=True)  # JSON 摘要
    ip_address = Column(String(45), nullable=False, server_default="")
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)


Index("ix_audit_logs_event_actor", AuditLog.event_type, AuditLog.actor_id)
