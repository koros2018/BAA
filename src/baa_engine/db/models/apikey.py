"""API 密钥域模型（T-C2 无状态化）。

原实现把密钥与用量存本地 JSON 文件，多副本各持一份互不可见。改为统一库：
- api_keys：整条密钥记录以 JSON 列保存（字段与旧 JSON 完全一致，零语义漂移），
  key_hash 独立成列用于检索/唯一性
- api_key_usage：跨副本累计调用次数与最后使用时间（单行原子自增）
"""

from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, JSON, String

from .base import Base


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"

    key_id = Column(String(64), primary_key=True)
    key_hash = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    # 旧 JSON 中的完整 key_info（含 hash/encrypted_raw/created_at/expires_at/...）
    record = Column(JSON, nullable=False)


Index("idx_api_keys_hash", ApiKeyRecord.key_hash)
Index("idx_api_keys_enabled", ApiKeyRecord.enabled)


class ApiKeyUsage(Base):
    __tablename__ = "api_key_usage"

    key_id = Column(
        String(64),
        ForeignKey("api_keys.key_id", ondelete="CASCADE"),
        primary_key=True,
    )
    calls = Column(Integer, nullable=False, default=0)
    last_used = Column(String(40), nullable=True)
