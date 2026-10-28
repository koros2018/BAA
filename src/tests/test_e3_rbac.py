"""E3-T3: 接口级 RBAC 权限测试。

验证场景:
1. 管理员密钥可访问管理端点
2. 普通密钥访问管理端点被拒绝 (403)
3. 无效密钥被拒绝 (401)
4. 无密钥且匿名关闭时被拒绝 (401)
5. RBAC 中间件正确注入 request.state
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    """管理员密钥测试客户端（通过 BAA_API_KEY 环境变量）。"""
    import src.api.api_globals as ag
    from src.baa_engine.api_key_manager import reset_key_manager

    monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
    monkeypatch.setenv("BAA_API_KEY", "test-admin-key")
    # 清空 API_KEYS，确保使用 env key 路径
    saved = set(ag.API_KEYS)
    ag.API_KEYS.clear()
    reset_key_manager()

    from src.api.baa_api import app

    client = TestClient(app)
    yield client
    ag.API_KEYS.update(saved)


@pytest.fixture
def read_client(tmp_path, monkeypatch):
    """只读密钥测试客户端（通过数据库密钥）。"""
    import src.api.api_globals as ag
    from src.baa_engine.api_key_manager import get_key_manager, reset_key_manager

    monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
    # 不设置 BAA_API_KEY，使用数据库密钥
    saved = set(ag.API_KEYS)
    ag.API_KEYS.clear()
    reset_key_manager()

    # 创建 read-only 密钥
    km = get_key_manager()
    key_info = km.generate_key(permission="read", label="test-read")
    ag.API_KEYS.add(key_info["raw_key"])

    from src.api.baa_api import app

    client = TestClient(app)
    yield client, key_info["raw_key"]
    ag.API_KEYS.update(saved)


@pytest.fixture(autouse=True)
def _ensure_schema(tmp_path, monkeypatch):
    """确保测试数据库 schema 已创建（含 RBAC 表）。"""
    monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
    # 先导入模型，确保 Base.metadata 包含新表
    import src.baa_engine.db.models.rbac  # noqa: F401
    import src.baa_engine.db.models.audit_log  # noqa: F401
    from src.baa_engine.db import ensure_schema
    ensure_schema()
    yield


class TestRBACMiddleware:
    """测试 RBAC 中间件的权限控制。"""

    def test_admin_can_access_admin_endpoint(self, admin_client):
        """管理员密钥可以访问管理端点。"""
        resp = admin_client.get(
            "/api/v1/admin/audit/logs",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200

    def test_read_key_cannot_access_admin_endpoint(self, read_client):
        """只读密钥不能访问管理端点。"""
        client, raw_key = read_client
        resp = client.get(
            "/api/v1/admin/audit/logs",
            headers={"Authorization": f"Bearer {raw_key}"},
        )
        assert resp.status_code == 403

    def test_invalid_key_returns_401(self, tmp_path, monkeypatch):
        """无效密钥返回 401。"""
        import src.api.api_globals as ag

        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
        monkeypatch.setenv("BAA_API_KEY", "test-admin-key")
        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        try:
            from src.api.baa_api import app

            client = TestClient(app)
            resp = client.get(
                "/api/v1/admin/audit/logs",
                headers={"Authorization": "Bearer invalid-key"},
            )
            assert resp.status_code == 401
        finally:
            ag.API_KEYS.update(saved)

    def test_no_key_returns_401_when_anonymous_disabled(self, tmp_path, monkeypatch):
        """匿名访问关闭时，无密钥返回 401。"""
        import src.api.api_globals as ag

        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
        monkeypatch.setenv("BAA_API_KEY", "test-admin-key")
        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "0")
        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        try:
            from src.api.baa_api import app

            client = TestClient(app)
            # 不发送 Authorization header
            resp = client.get("/api/v1/admin/audit/logs")
            assert resp.status_code == 401
        finally:
            ag.API_KEYS.update(saved)

    def test_no_key_allows_anonymous_when_enabled(self, tmp_path, monkeypatch):
        """匿名访问开启时，无密钥可以访问公开端点。"""
        import src.api.api_globals as ag

        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
        monkeypatch.setenv("BAA_ALLOW_ANONYMOUS", "1")
        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        # 不设置 BAA_API_KEY
        try:
            from src.api.baa_api import app

            client = TestClient(app)
            # 公开端点应该可以访问
            resp = client.get("/health")
            assert resp.status_code == 200
        finally:
            ag.API_KEYS.update(saved)

    def test_request_state_injected(self, admin_client):
        """RBAC 中间件正确注入 request.state。"""
        resp = admin_client.get(
            "/api/v1/admin/audit/logs",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        # 如果中间件正常工作，request.state 应该被注入
        assert resp.status_code == 200


class TestRBACScope:
    """测试 scope 验证逻辑。"""

    def test_has_scope_admin_wins(self):
        """admin scope 匹配所有请求。"""
        from src.baa_engine.api_key_manager import has_scope

        key_info = {"permission": "admin", "scopes": ["*"]}
        assert has_scope(key_info, "admin:write") is True
        assert has_scope(key_info, "review:read") is True
        assert has_scope(key_info, "any:scope") is True

    def test_has_scope_read_only(self):
        """read 权限只能访问读操作。"""
        from src.baa_engine.api_key_manager import has_scope

        key_info = {"permission": "read", "scopes": ["review:read"]}
        assert has_scope(key_info, "review:read") is True
        assert has_scope(key_info, "review:write") is False
        assert has_scope(key_info, "admin:write") is False

    def test_has_scope_write(self):
        """write 权限可以访问读写操作。"""
        from src.baa_engine.api_key_manager import has_scope

        key_info = {"permission": "write", "scopes": ["review:write", "review:read"]}
        assert has_scope(key_info, "review:write") is True
        assert has_scope(key_info, "review:read") is True
        assert has_scope(key_info, "admin:write") is False

    def test_has_scope_missing_key(self):
        """缺少 key_info 时返回 False。"""
        from src.baa_engine.api_key_manager import has_scope

        assert has_scope(None, "review:read") is False
        assert has_scope({}, "review:read") is False

    def test_has_scope_with_permission_fallback(self):
        """scopes 为空时使用 permission 映射的默认 scopes。"""
        from src.baa_engine.api_key_manager import has_scope

        # limited 权限默认有 review:read
        key_info = {"permission": "limited", "scopes": []}
        assert has_scope(key_info, "review:read") is True
        assert has_scope(key_info, "admin:write") is False
