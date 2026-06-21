"""
BAA API 测试
"""
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi.testclient import TestClient
from src.api.baa_api import app, generate_auth_token, verify_auth_token, AUTH_SECRETS


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
    assert response.status_code in (401, 403)


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


if __name__ == "__main__":
    test_health()
    test_deconstruct_unauthorized()
    test_deconstruct_unsupported_format()
    test_generate_and_verify_auth_token()
    test_verify_expired_token()
    test_verify_invalid_token()
    print("✅ API 测试通过")