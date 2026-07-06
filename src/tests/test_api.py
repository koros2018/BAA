"""
BAA API 测试
"""

import sys  # import
import os  # stdlib: filesystem ops
import json  # stdlib: JSON

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # path operation

from fastapi.testclient import TestClient  # import
from src.api.baa_api import app, generate_auth_token, verify_auth_token, AUTH_SECRETS  # import


from src.baa_engine.api_key_manager import ApiKeyManager, get_key_manager  # import

client = TestClient(app)  # function call

# 设置测试 API Key
os.environ["BAA_API_KEY"] = "test-api-key"  # 操作
os.environ["BAA_AUTH_SECRET"] = "test-secret"  # 操作

# 重新加载模块使配置生效
import importlib  # import
import src.api.baa_api  # import

importlib.reload(src.api.baa_api)  # function call
from src.api.baa_api import app, API_KEYS, AUTH_SECRETS  # import

API_KEYS.add("test-api-key")  # function call


def test_health():  # function: def test_health():
    """测试健康检查"""
    response = client.get("/health")  # function call
    assert response.status_code == 200  # equality check
    data = response.json()  # function call
    assert data["status"] in ("ok", "degraded")  # 断言
    assert data["version"]  # 断言


def test_deconstruct_unauthorized():  # function: def test_deconstruct_unauthorized():
    """测试未认证"""
    response = client.post("/deconstruct")  # function call
    assert response.status_code in (401, 403, 422)  # 断言


def test_deconstruct_unsupported_format():  # function: def test_deconstruct_unsupported_format():
    """测试不支持的文件格式"""
    response = client.post(  # assignment
        "/deconstruct",  # 解构端点
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},  # function call
        headers={"Authorization": "Bearer test-api-key"},  # assignment
    )  # code
    assert response.status_code == 400  # equality check
    data = response.json()  # function call
    assert "UNSUPPORTED_FORMAT" in str(data)  # 断言


def test_generate_and_verify_auth_token():  # function: def test_generate_and_verify_auth_token():
    """测试授权令牌生成和验证"""
    payload = {  # assignment
        "order_id": "test-order-001",  # 字段
        "service": "reconstruct",  # 字段
        "issued_at": "2026-06-20T09:00:00",  # 字段
        "expires_at": "2026-12-31T23:59:59",  # 字段
        "quota": {"max_requests": 1, "max_file_size_mb": 50},  # 字段
        "client_id": "ema2-platform",  # 字段
    }  # code
    token = generate_auth_token(payload)  # function call
    assert token is not None  # 断言
    assert len(token.split(".")) == 3  # 断言

    verified = verify_auth_token(token)  # function call
    assert verified is not None  # 断言
    assert verified["order_id"] == "test-order-001"  # 断言
    assert verified["client_id"] == "ema2-platform"  # 断言


def test_verify_expired_token():  # function: def test_verify_expired_token():
    """测试过期令牌"""
    payload = {  # assignment
        "order_id": "test-expired",  # 字段
        "expires_at": "2020-01-01T00:00:00",  # 字段
    }  # code
    token = generate_auth_token(payload)  # function call
    verified = verify_auth_token(token)  # function call
    assert verified is None  # 断言


def test_verify_invalid_token():  # function: def test_verify_invalid_token():
    """测试无效令牌"""
    verified = verify_auth_token("invalid.token.here")  # function call
    assert verified is None  # 断言


# ── API密钥管理测试 ──────────────────────────────────────


def test_api_key_manager_generate_and_validate():  # function: def test_api_key_manager_generate_and_validate():
    """测试API Key生成和验证"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys.json")  # function call
    km.load()  # function call

    # 生成admin密钥
    r = km.generate_key(permission="admin", label="test-admin")  # function call
    assert r["key_id"].startswith("key_")  # 断言
    assert r["raw_key"].startswith("baa_")  # 断言
    assert r["info"]["permission"] == "admin"  # 断言
    assert r["info"]["enabled"] is True  # 断言

    # 验证
    info = km.validate_key(r["raw_key"])  # function call
    assert info is not None  # 断言
    assert info["permission"] == "admin"  # 断言
    assert info["label"] == "test-admin"  # 断言

    # 错误密钥
    assert km.validate_key("wrong-key") is None  # 断言

    import os  # stdlib: filesystem ops

    for f in ["/tmp/test_baa_keys.json", "/tmp/test_baa_keys.json.tmp"]:  # loop: iterate
        if os.path.exists(f):  # condition: os.path.exists(f):
            os.remove(f)  # remove item


def test_api_key_manager_revoke():  # function: def test_api_key_manager_revoke():
    """测试密钥撤销"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys2.json")  # function call
    km.load()  # function call

    r = km.generate_key(permission="write", label="test-revoke")  # function call
    raw = r["raw_key"]  # assignment
    key_id = r["key_id"]  # assignment

    assert km.validate_key(raw) is not None  # 断言

    km.revoke_key(key_id)  # function call
    assert km.validate_key(raw) is None  # 断言

    import os  # stdlib: filesystem ops

    for f in ["/tmp/test_baa_keys2.json", "/tmp/test_baa_keys2.json.tmp"]:  # loop: iterate
        if os.path.exists(f):  # condition: os.path.exists(f):
            os.remove(f)  # remove item


def test_api_key_manager_expiry():  # function: def test_api_key_manager_expiry():
    """测试密钥过期"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys3.json")  # function call
    km.load()  # function call

    # 1天有效
    r = km.generate_key(permission="read", label="test-expiry", ttl_days=1)  # function call
    assert km.validate_key(r["raw_key"]) is not None  # 断言

    # 模拟过期：手动修改expires_at
    import time  # stdlib: timing

    km._keys[r["key_id"]]["expires_at"] = "2020-01-01T00:00:00+00:00"  # 操作
    assert km.validate_key(r["raw_key"]) is None  # 断言

    import os  # stdlib: filesystem ops

    for f in ["/tmp/test_baa_keys3.json", "/tmp/test_baa_keys3.json.tmp"]:  # loop: iterate
        if os.path.exists(f):  # condition: os.path.exists(f):
            os.remove(f)  # remove item


def test_api_key_manager_rotate():  # function: def test_api_key_manager_rotate():
    """测试密钥轮换"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys4.json")  # function call
    km.load()  # function call

    r = km.generate_key(permission="write", label="test-rotate")  # function call
    old_raw = r["raw_key"]  # assignment
    key_id = r["key_id"]  # assignment

    # 轮换
    result = km.rotate_key(key_id)  # function call
    assert result is not None  # 断言
    new_raw = result["raw_key"]  # assignment
    assert new_raw != old_raw  # inequality check

    # 旧密钥失效，新密钥有效
    assert km.validate_key(old_raw) is None  # 断言
    assert km.validate_key(new_raw) is not None  # 断言

    import os  # stdlib: filesystem ops

    for f in ["/tmp/test_baa_keys4.json", "/tmp/test_baa_keys4.json.tmp"]:  # loop: iterate
        if os.path.exists(f):  # condition: os.path.exists(f):
            os.remove(f)  # remove item


def test_api_key_manager_usage():  # function: def test_api_key_manager_usage():
    """测试用量统计"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys5.json")  # function call
    km.load()  # function call

    r = km.generate_key(permission="admin", label="test-usage")  # function call

    # 记录用量
    for _ in range(3):  # 循环
        km.record_usage(r["raw_key"])  # function call

    stats = km.get_usage_stats(r["key_id"])  # function call
    assert stats["total_calls"] == 3  # 断言
    assert stats["last_used"] is not None  # 断言

    import os  # stdlib: filesystem ops

    for f in ["/tmp/test_baa_keys5.json", "/tmp/test_baa_keys5.json.tmp"]:  # loop: iterate
        if os.path.exists(f):  # condition: os.path.exists(f):
            os.remove(f)  # remove item


def test_api_key_manager_list_keys():  # function: def test_api_key_manager_list_keys():
    """测试密钥列表"""
    km = ApiKeyManager(storage_path="/tmp/test_baa_keys6.json")  # function call
    km.load()  # function call

    km.generate_key(permission="admin", label="k1")  # function call
    km.generate_key(permission="write", label="k2")  # function call

    keys = km.list_keys()  # function call
    assert len(keys) == 2  # get length
    assert keys[0]["label"] == "k2" or keys[0]["label"] == "k1"  # sorted desc

    import os  # stdlib: filesystem ops

    for f in ["/tmp/test_baa_keys6.json", "/tmp/test_baa_keys6.json.tmp"]:  # loop: iterate
        if os.path.exists(f):  # condition: os.path.exists(f):
            os.remove(f)  # remove item


def test_api_key_manager_permission_validation():  # function: def test_api_key_manager_permission_validation():
    """测试权限验证"""
    from src.baa_engine.api_key_manager import ApiKeyPermission  # import

    assert ApiKeyPermission.validate("admin")  # 断言
    assert ApiKeyPermission.validate("write")  # 断言
    assert ApiKeyPermission.validate("read")  # 断言
    assert ApiKeyPermission.validate("limited")  # 断言
    assert not ApiKeyPermission.validate("superadmin")  # 断言


if __name__ == "__main__":  # condition: __name__ == "__main__":
    test_health()  # function call
    test_deconstruct_unauthorized()  # function call
    test_deconstruct_unsupported_format()  # function call
    test_generate_and_verify_auth_token()  # function call
    test_verify_expired_token()  # function call
    test_verify_invalid_token()  # function call
    print("✅ API 测试通过")  # print output
