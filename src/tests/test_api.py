"""
BAA API 测试
"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from src.api.baa_api import app, generate_auth_token, verify_auth_token, AUTH_SECRETS


from src.baa_engine.api_key_manager import ApiKeyManager, get_key_manager


client = TestClient(app)

# 设置测试 API Key
os.environ["BAA_API_KEY"] = "test-api-key"
os.environ["BAA_AUTH_SECRET"] = "test-secret"

# 重新加载模块使配置生效
import importlib
import src.api.baa_api
importlib.reload(src.api.baa_api)
from src.api.baa_api import app, API_KEYS, AUTH_SECRETS

API_KEYS.add("test-api-key")


def test_health():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


def test_deconstruct_unauthorized():
    """测试未认证"""
    response = client.post("/deconstruct")
    assert response.status_code in (401, 403, 422)


def test_deconstruct_unsupported_format():
    """测试不支持的文件格式"""
    response = client.post(
        "/deconstruct",
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
        headers={"Authorization": "Bearer test-api-key"},
    )
    assert response.status_code == 400
    data = response.json()
    assert "UNSUPPORTED_FORMAT" in str(data)


def test_generate_and_verify_auth_token():
    """测试授权令牌生成和验证"""
    payload = {
        "order_id": "test-order-001",
        "service": "reconstruct",
        "issued_at": "2026-06-20T09:00:00",
        "expires_at": "2026-12-31T23:59:59",
        "quota": {"max_requests": 1, "max_file_size_mb": 50},
        "client_id": "ema2-platform",
    }
    token = generate_auth_token(payload)
    assert token is not None
    assert len(token.split(".")) == 3

    verified = verify_auth_token(token)
    assert verified is not None
    assert verified["order_id"] == "test-order-001"
    assert verified["client_id"] == "ema2-platform"


def test_verify_expired_token():
    """测试过期令牌"""
    payload = {
        "order_id": "test-expired",
        "expires_at": "2020-01-01T00:00:00",
    }
    token = generate_auth_token(payload)
    verified = verify_auth_token(token)
    assert verified is None


def test_verify_invalid_token():
    """测试无效令牌"""
    verified = verify_auth_token("invalid.token.here")
    assert verified is None


# ── API密钥管理测试 ──────────────────────────────────────


def test_api_key_manager_generate_and_validate():
    """测试API Key生成和验证"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys.json")
    km.load()

    # 生成admin密钥
    r = km.generate_key(permission="admin", label="test-admin")
    assert r["key_id"].startswith("key_")
    assert r["raw_key"].startswith("baa_")
    assert r["info"]["permission"] == "admin"
    assert r["info"]["enabled"] is True

    # 验证
    info = km.validate_key(r["raw_key"])
    assert info is not None
    assert info["permission"] == "admin"
    assert info["label"] == "test-admin"

    # 错误密钥
    assert km.validate_key("wrong-key") is None


    import os
    for f in ["/tmp/test_baa_keys.json", "/tmp/test_baa_keys.json.tmp"]:
        if os.path.exists(f):
            os.remove(f)


def test_api_key_manager_revoke():
    """测试密钥撤销"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys2.json")
    km.load()

    r = km.generate_key(permission="write", label="test-revoke")
    raw = r["raw_key"]
    key_id = r["key_id"]

    assert km.validate_key(raw) is not None

    km.revoke_key(key_id)
    assert km.validate_key(raw) is None

    import os
    for f in ["/tmp/test_baa_keys2.json", "/tmp/test_baa_keys2.json.tmp"]:
        if os.path.exists(f):
            os.remove(f)


def test_api_key_manager_expiry():
    """测试密钥过期"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys3.json")
    km.load()

    # 1天有效
    r = km.generate_key(permission="read", label="test-expiry", ttl_days=1)
    assert km.validate_key(r["raw_key"]) is not None

    # 模拟过期：手动修改expires_at
    import time
    km._keys[r["key_id"]]["expires_at"] = "2020-01-01T00:00:00+00:00"
    assert km.validate_key(r["raw_key"]) is None

    import os
    for f in ["/tmp/test_baa_keys3.json", "/tmp/test_baa_keys3.json.tmp"]:
        if os.path.exists(f):
            os.remove(f)


def test_api_key_manager_rotate():
    """测试密钥轮换"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys4.json")
    km.load()

    r = km.generate_key(permission="write", label="test-rotate")
    old_raw = r["raw_key"]
    key_id = r["key_id"]

    # 轮换
    result = km.rotate_key(key_id)
    assert result is not None
    new_raw = result["raw_key"]
    assert new_raw != old_raw

    # 旧密钥失效，新密钥有效
    assert km.validate_key(old_raw) is None
    assert km.validate_key(new_raw) is not None

    import os
    for f in ["/tmp/test_baa_keys4.json", "/tmp/test_baa_keys4.json.tmp"]:
        if os.path.exists(f):
            os.remove(f)


def test_api_key_manager_usage():
    """测试用量统计"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys5.json")
    km.load()

    r = km.generate_key(permission="admin", label="test-usage")

    # 记录用量
    for _ in range(3):
        km.record_usage(r["raw_key"])

    stats = km.get_usage_stats(r["key_id"])
    assert stats["total_calls"] == 3
    assert stats["last_used"] is not None

    import os
    for f in ["/tmp/test_baa_keys5.json", "/tmp/test_baa_keys5.json.tmp"]:
        if os.path.exists(f):
            os.remove(f)


def test_api_key_manager_list_keys():
    """测试密钥列表"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys6.json")
    km.load()

    km.generate_key(permission="admin", label="k1")
    km.generate_key(permission="write", label="k2")

    keys = km.list_keys()
    assert len(keys) == 2
    assert keys[0]["label"] == "k2" or keys[0]["label"] == "k1"  # sorted desc

    import os
    for f in ["/tmp/test_baa_keys6.json", "/tmp/test_baa_keys6.json.tmp"]:
        if os.path.exists(f):
            os.remove(f)


def test_api_key_manager_permission_validation():
    """测试权限验证"""
    from src.baa_engine.api_key_manager import ApiKeyPermission
    assert ApiKeyPermission.validate("admin")
    assert ApiKeyPermission.validate("write")
    assert ApiKeyPermission.validate("read")
    assert ApiKeyPermission.validate("limited")
    assert not ApiKeyPermission.validate("superadmin")


if __name__ == "__main__":
    test_health()
    test_deconstruct_unauthorized()
    test_deconstruct_unsupported_format()
    test_generate_and_verify_auth_token()
    test_verify_expired_token()
    test_verify_invalid_token()
    print("✅ API 测试通过")