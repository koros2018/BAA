"""E4-T4：生产配置管理 — 环境变量校验 + /api/v1/admin/config 端点。

覆盖:
1. validate_env() 必填项缺失 → errors
2. validate_env() 合法配置 → valid=True，无 errors
3. 敏感字段脱敏（BAA_API_KEY / BAA_AUTH_SECRET / BAA_DATABASE_URL）
4. 非敏感字段原值展示
5. 生产安全警告（匿名放行开启、视觉层开启、key 过短、日志非 json）
6. /api/v1/admin/config 端点：需 admin scope，返回脱敏摘要
7. /api/v1/admin/config 端点：无 auth 返回 401
8. /api/v1/admin/config 端点：非法 key 返回 401
9. 响应结构完整性（schema_keys / env_count / health 字段）
"""

import os
import pytest
from fastapi.testclient import TestClient


# ── 纯函数测试（不依赖 FastAPI 应用） ───────────────────────────


class TestValidateEnv:
    """环境变量校验逻辑测试。"""

    def _clear_baa_env(self, monkeypatch):
        """清除所有 BAA_ 环境变量。"""
        for k in list(os.environ.keys()):
            if k.startswith("BAA_"):
                monkeypatch.delenv(k, raising=False)

    def test_missing_required_keys_produce_errors(self, monkeypatch):
        """必填项缺失 → errors。"""
        from src.api.config_middleware import validate_env

        self._clear_baa_env(monkeypatch)
        report = validate_env()
        assert not report["valid"]
        error_keys = {e["key"] for e in report["errors"]}
        assert "BAA_ALLOW_ANONYMOUS" in error_keys
        assert "BAA_DATABASE_URL" in error_keys

    def test_valid_production_config_no_errors(self, monkeypatch):
        """完整生产配置 → valid=True，无 errors。"""
        from src.api.config_middleware import validate_env

        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
        monkeypatch.setenv("BAA_DATABASE_URL", "postgresql+psycopg://u:p@host/db")
        monkeypatch.setenv("BAA_PDF_ISOLATION", "1")
        monkeypatch.setenv("BAA_LOG_FORMAT", "json")
        monkeypatch.setenv("BAA_API_KEY", "a" * 40)
        monkeypatch.setenv("BAA_AUTH_SECRET", "b" * 20)
        monkeypatch.setenv("BAA_PORT", "8000")
        monkeypatch.setenv("BAA_WORKERS", "4")
        monkeypatch.setenv("BAA_QUEUE_NAMESPACE", "prod")
        monkeypatch.setenv("BAA_DATA_DIR", "/app/data")
        monkeypatch.setenv("BAA_CORRECTION_MODE", "rule")
        monkeypatch.setenv("BAA_VISION_ENABLED", "false")

        report = validate_env()
        assert report["valid"]
        assert report["errors"] == []

    def test_sensitive_fields_masked(self, monkeypatch):
        """敏感字段在 summary 中应脱敏显示。"""
        from src.api.config_middleware import validate_env

        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
        monkeypatch.setenv(
            "BAA_DATABASE_URL",
            "postgresql+psycopg://admin:supersecret123@pg:5432/baa",
        )
        monkeypatch.setenv("BAA_API_KEY", "my-admin-key-12345678")
        monkeypatch.setenv("BAA_AUTH_SECRET", "auth-secret-abcdefgh")

        report = validate_env()
        summary = report["summary"]

        key_val = summary["BAA_API_KEY"]
        assert key_val != "my-admin-key-12345678"
        if len(key_val) >= 8:
            assert key_val.startswith("my-a") and key_val.endswith("5678")

        db_val = summary["BAA_DATABASE_URL"]
        assert "supersecret123" not in db_val

        assert summary["BAA_ALLOW_ANONYMOUS"] == "0"
        assert summary["BAA_LOG_FORMAT"] == "text"

    def test_anonymous_enabled_warning(self, monkeypatch):
        """BAA_ALLOW_ANONYMOUS=1 → 安全警告。"""
        from src.api.config_middleware import validate_env

        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "1")
        monkeypatch.setenv("BAA_DATABASE_URL", "sqlite:///test.db")

        report = validate_env()
        warn_keys = {w["key"] for w in report["warnings"]}
        assert "BAA_ALLOW_ANONYMOUS" in warn_keys

    def test_vision_enabled_warning(self, monkeypatch):
        """BAA_VISION_ENABLED=true → 安全警告。"""
        from src.api.config_middleware import validate_env

        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
        monkeypatch.setenv("BAA_DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("BAA_VISION_ENABLED", "true")

        report = validate_env()
        warn_keys = {w["key"] for w in report["warnings"]}
        assert "BAA_VISION_ENABLED" in warn_keys

    def test_short_api_key_warning(self, monkeypatch):
        """BAA_API_KEY 长度 < 32 → 警告。"""
        from src.api.config_middleware import validate_env

        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
        monkeypatch.setenv("BAA_DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("BAA_API_KEY", "short")

        report = validate_env()
        warn_keys = {w["key"] for w in report["warnings"]}
        assert "BAA_API_KEY" in warn_keys

    def test_text_log_format_no_error(self, monkeypatch):
        """BAA_LOG_FORMAT=text（合法值）→ 不报 error。"""
        from src.api.config_middleware import validate_env

        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
        monkeypatch.setenv("BAA_DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("BAA_LOG_FORMAT", "text")

        report = validate_env()
        assert all(e["key"] != "BAA_LOG_FORMAT" for e in report["errors"])


# ── FastAPI 端点集成测试 ───────────────────────────────────────


@pytest.fixture
def cfg_admin_client(tmp_path, monkeypatch):
    """带 admin 权限的测试客户端。

    使用 BAA_API_KEY 环境变量方式（而非 DB 生成密钥），
    与 test_e3_rbac.py 的 admin_client fixture 保持一致的模式。
    """
    import src.api.api_globals as ag
    from src.baa_engine.api_key_manager import reset_key_manager

    monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'cfg_test.db'}")
    monkeypatch.setenv("BAA_API_KEY", "e4t4-test-admin-key-1234567890abcdef")
    monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
    monkeypatch.setenv("BAA_LOG_FORMAT", "json")
    monkeypatch.setenv("BAA_PDF_ISOLATION", "1")
    monkeypatch.setenv("BAA_VISION_ENABLED", "false")

    saved = set(ag.API_KEYS)
    ag.API_KEYS.clear()
    reset_key_manager()

    from src.api.baa_api import app

    client = TestClient(app)
    yield client
    ag.API_KEYS.update(saved)


def test_config_endpoint_returns_200_with_admin(cfg_admin_client):
    """admin key 访问 → 200 + 脱敏摘要。"""
    resp = cfg_admin_client.get(
        "/api/v1/admin/config",
        headers={"Authorization": "Bearer e4t4-test-admin-key-1234567890abcdef"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "health" in data
    assert "config" in data
    summary = data["config"]["summary"]
    assert "BAA_API_KEY" in summary
    assert "BAA_DATABASE_URL" in summary


def test_config_endpoint_rejects_no_auth(cfg_admin_client):
    """无认证 → 401。"""
    resp = cfg_admin_client.get("/api/v1/admin/config")
    assert resp.status_code == 401


def test_config_endpoint_rejects_invalid_key(cfg_admin_client):
    """非法 key → 401。"""
    resp = cfg_admin_client.get(
        "/api/v1/admin/config",
        headers={"Authorization": "Bearer invalid-key-xxxx"},
    )
    assert resp.status_code == 401


def test_config_endpoint_schema_keys_listed(cfg_admin_client):
    """响应包含 schema_keys 列表。"""
    resp = cfg_admin_client.get(
        "/api/v1/admin/config",
        headers={"Authorization": "Bearer e4t4-test-admin-key-1234567890abcdef"},
    )
    data = resp.json()
    schema_keys = data["config"]["schema_keys"]
    assert "BAA_ALLOW_ANONYMOUS" in schema_keys
    assert "BAA_DATABASE_URL" in schema_keys
    assert "BAA_LOG_FORMAT" in schema_keys


def test_config_endpoint_health_reports_structure(cfg_admin_client):
    """健康报告结构正确。"""
    resp = cfg_admin_client.get(
        "/api/v1/admin/config",
        headers={"Authorization": "Bearer e4t4-test-admin-key-1234567890abcdef"},
    )
    data = resp.json()
    health = data["health"]
    assert "errors" in health
    assert "warnings" in health
    assert "summary" in health
    assert "valid" in health
    assert isinstance(health["errors"], list)
    assert isinstance(health["warnings"], list)


def test_config_endpoint_env_count(cfg_admin_client):
    """响应包含已设置环境变量数量。"""
    resp = cfg_admin_client.get(
        "/api/v1/admin/config",
        headers={"Authorization": "Bearer e4t4-test-admin-key-1234567890abcdef"},
    )
    data = resp.json()
    assert "env_count" in data["config"]
    assert isinstance(data["config"]["env_count"], int)
    assert data["config"]["env_count"] >= 3
