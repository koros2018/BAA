"""缓存域模型：cache_entries（原 src/data/cache/baa_cache.db）。

时间戳保持 Float epoch（与旧库零转换）；value 保持 TEXT 存 JSON 串
（序列化/反序列化仍由 PersistentCache 负责，行为不变）。
"""

from sqlalchemy import Column, Float, Index, Integer, String, Text

from .base import Base


class CacheEntry(Base):
    __tablename__ = "cache_entries"

    cache_key = Column(String, primary_key=True)
    cache_type = Column(String, nullable=False)
    value = Column(Text, nullable=False)
    created_at = Column(Float, nullable=False)
    expires_at = Column(Float, nullable=False)
    access_count = Column(Integer, default=0)
    last_access_at = Column(Float, default=0)


# 索引名与旧库保持一致（create_all 对已存在索引幂等）
Index("idx_cache_type", CacheEntry.cache_type)
Index("idx_expires_at", CacheEntry.expires_at)
