"""审查任务队列模型（T-C2 无状态化）。

原实现为进程内 asyncio.Queue + dict：任务只存在于接收请求的那一个副本，
HPA 扩到多副本后查询/取消/出队会命中错误副本。改为统一库：
- 所有任务状态落表，任意副本可查
- 出队用原子认领（PG: FOR UPDATE SKIP LOCKED；SQLite: 条件 UPDATE）避免重复消费
- namespace 隔离测试与生产队列（生产固定 "default"）

时间戳沿用 Float epoch，与 ReviewTask dataclass 零转换。
"""

from sqlalchemy import Column, Float, Index, Integer, JSON, String, Text

from .base import Base


class ReviewTaskRecord(Base):
    __tablename__ = "review_tasks"

    task_id = Column(String(64), primary_key=True)
    namespace = Column(String(64), nullable=False, default="default")
    file_id = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="queued")
    queue_position = Column(Integer, default=0)
    progress = Column(Float, default=0.0)
    created_at = Column(Float, nullable=False)
    started_at = Column(Float, nullable=True)
    completed_at = Column(Float, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    webhook_url = Column(Text, nullable=True)
    webhook_type = Column(String(20), default="generic")
    priority = Column(Integer, default=0)
    worker_id = Column(String(64), nullable=True)


Index("idx_review_tasks_ns_status", ReviewTaskRecord.namespace, ReviewTaskRecord.status)
Index("idx_review_tasks_created", ReviewTaskRecord.created_at)
