"""T-C2 无状态化单测：API 密钥/用量在多个管理器实例（模拟多副本）间共享。

显式 storage_path 仍走独立 JSON（旧行为），本文件只覆盖默认路径 → 统一库。
"""

import pytest

from src.baa_engine.api_key_manager import ApiKeyManager
from src.baa_engine.db import dispose_engine


@pytest.fixture()
def db_env(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'keys_state.db').as_posix()}"
    monkeypatch.setenv("BAA_DATABASE_URL", url)
    monkeypatch.setenv("BAA_API_KEYS_PATH", str(tmp_path / "keys.json"))
    monkeypatch.delenv("BAA_API_KEY", raising=False)
    yield url
    dispose_engine(url)


def _manager(ttl: float = 0) -> ApiKeyManager:
    import os

    os.environ["BAA_API_KEY_CACHE_TTL"] = str(ttl)
    return ApiKeyManager()


def test_key_visible_across_instances(db_env):
    """副本 A 创建的密钥，副本 B 立即可验证通过。"""
    created = _manager().generate_key(permission="read", label="replica-a")
    raw = created["raw_key"]

    other = _manager()
    info = other.validate_key(raw)
    assert info is not None
    assert info["key_id"] == created["key_id"]
    assert info["permission"] == "read"


def test_usage_accumulates_across_instances(db_env):
    """用量计数落在共享库：A 调用后在 B 侧可见。"""
    created = _manager().generate_key(permission="read", label="usage")
    raw = created["raw_key"]
    key_id = created["key_id"]

    b = _manager()
    for _ in range(3):
        b.record_usage(raw)

    fresh = _manager()
    assert fresh.get_usage_stats(key_id)["total_calls"] == 3
    assert fresh.get_usage_stats(key_id)["last_used"]


def test_delete_visible_across_instances(db_env):
    """A 删除密钥后，B 不再能验证通过。"""
    created = _manager().generate_key(permission="read", label="to-delete")
    raw = created["raw_key"]

    a = _manager()
    assert a.delete_key(created["key_id"]) is True

    b = _manager()
    assert b.validate_key(raw) is None
    assert b.list_keys() == []


def test_stale_replica_does_not_rollback_usage(db_env):
    """陈旧副本 save() 不得把用量回退（lost update 防护）。"""
    created = _manager().generate_key(permission="read", label="stale")
    raw = created["raw_key"]
    key_id = created["key_id"]

    # A 带 300s 缓存：load 后保持陈旧快照（calls=0）
    a = _manager(ttl=300)
    a.load()

    b = _manager()
    for _ in range(5):
        b.record_usage(raw)

    # A 此时产生一次写入（如新建密钥），不能覆盖 B 已累计的 5 次
    a.generate_key(permission="read", label="stale-save")

    fresh = _manager()
    assert fresh.get_usage_stats(key_id)["total_calls"] == 5


def test_json_backup_still_written(db_env, tmp_path):
    """统一库为准的同时保留 JSON 备份（旧工具/人工排障可用）。"""
    import json

    created = _manager().generate_key(permission="write", label="backup")
    backup = tmp_path / "keys.json"
    assert backup.exists()
    data = json.loads(backup.read_text(encoding="utf-8"))
    assert created["key_id"] in data["keys"]
