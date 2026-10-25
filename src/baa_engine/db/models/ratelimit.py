"""限流域模型：rate_limit_buckets（T-C2 分布式限流）。

固定窗口计数器：多副本共享同一行，靠原子 UPSERT/条件 UPDATE 保证一致。
- bucket_key = "{subject}:{window_start}"，主键即窗口标识
- expires_at 为 Float epoch，惰性清理过期窗口
"""

from sqlalchemy import Column, Float, Index, Integer, String

from .base import Base


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"

    bucket_key = Column(String(200), primary_key=True)
    window_start = Column(Integer, nullable=False)
    count = Column(Integer, nullable=False, default=0)
    expires_at = Column(Float, nullable=False)


Index("idx_rl_expires_at", RateLimitBucket.expires_at)
