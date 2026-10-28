"""E3-T3: RBAC 角色管理 API 测试。

验证场景:
1. 角色 CRUD 操作
2. 角色成员管理
3. 权限边界验证
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _ensure_rbac_schema(tmp_path, monkeypatch):
    """确保 RBAC 相关表已创建。"""
    monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
    # 先导入模型，确保 Base.metadata 包含新表
    import src.baa_engine.db.models.rbac  # noqa: F401
    from src.baa_engine.db import ensure_schema
    ensure_schema()


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    """管理员密钥测试客户端。"""
    import src.api.api_globals as ag
    from src.baa_engine.api_key_manager import reset_key_manager

    monkeypatch.setenv("BAA_API_KEY", "test-admin-key")
    saved = set(ag.API_KEYS)
    ag.API_KEYS.clear()
    reset_key_manager()

    from src.api.baa_api import app

    client = TestClient(app)
    yield client
    ag.API_KEYS.update(saved)


class TestRoleCRUD:
    """测试角色 CRUD 操作。"""

    def test_create_role(self, admin_client):
        """创建新角色。"""
        resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={
                "name": "engineer",
                "permission_level": "write",
                "description": "Engineer role",
            },
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["role"]["name"] == "engineer"
        assert data["role"]["permission_level"] == "write"
        assert data["role"]["member_count"] == 0

    def test_create_duplicate_role_rejected(self, admin_client):
        """创建重复角色应被拒绝。"""
        admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={"name": "engineer", "permission_level": "write"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={"name": "engineer", "permission_level": "write"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
        assert resp.json()["error_code"] == "DUPLICATE_ROLE"

    def test_list_roles(self, admin_client):
        """列出所有角色。"""
        # 创建几个角色
        for name in ["engineer", "auditor", "manager"]:
            admin_client.post(
                "/api/v1/admin/rbac/roles",
                params={"name": name, "permission_level": "read"},
                headers={"Authorization": "Bearer test-admin-key"},
            )

        resp = admin_client.get(
            "/api/v1/admin/rbac/roles",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["count"] >= 3
        names = {r["name"] for r in data["roles"]}
        assert "engineer" in names
        assert "auditor" in names
        assert "manager" in names

    def test_get_role_detail(self, admin_client):
        """查询角色详情。"""
        create_resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={
                "name": "tester",
                "permission_level": "read",
                "description": "Tester role",
            },
            headers={"Authorization": "Bearer test-admin-key"},
        )
        role_id = create_resp.json()["role"]["id"]

        resp = admin_client.get(
            f"/api/v1/admin/rbac/roles/{role_id}",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["role"]["name"] == "tester"
        assert data["role"]["description"] == "Tester role"

    def test_get_nonexistent_role(self, admin_client):
        """查询不存在的角色。"""
        resp = admin_client.get(
            "/api/v1/admin/rbac/roles/nonexistent-id",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_delete_role(self, admin_client):
        """删除角色。"""
        create_resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={"name": "to-delete", "permission_level": "read"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        role_id = create_resp.json()["role"]["id"]

        resp = admin_client.delete(
            f"/api/v1/admin/rbac/roles/{role_id}",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 验证已删除
        resp = admin_client.get(
            f"/api/v1/admin/rbac/roles/{role_id}",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.json()["status"] == "error"

    def test_delete_nonexistent_role(self, admin_client):
        """删除不存在的角色。"""
        resp = admin_client.delete(
            "/api/v1/admin/rbac/roles/nonexistent-id",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_create_role_requires_admin(self, tmp_path, monkeypatch):
        """创建角色需要 admin 权限。"""
        import src.api.api_globals as ag

        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'test_rbac.db'}")
        monkeypatch.setenv("BAA_API_KEY", "test-admin-key")
        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        try:
            # 创建一个 read-only key
            from src.baa_engine.api_key_manager import get_key_manager
            km = get_key_manager()
            key_info = km.generate_key(permission="read", label="read-only")
            ag.API_KEYS.add(key_info["raw_key"])

            from src.api.baa_api import app
            client = TestClient(app)

            resp = client.post(
                "/api/v1/admin/rbac/roles",
                params={"name": "test", "permission_level": "read"},
                headers={"Authorization": f"Bearer {key_info['raw_key']}"},
            )
            assert resp.status_code == 403
        finally:
            ag.API_KEYS.update(saved)


class TestRoleMembers:
    """测试角色成员管理。"""

    def test_add_member(self, admin_client, tmp_path, monkeypatch):
        """添加成员到角色。"""
        import src.api.api_globals as ag

        # 创建角色
        create_resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={"name": "test-role", "permission_level": "read"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        role_id = create_resp.json()["role"]["id"]

        # 创建一个 key 并获取其 key_id
        from src.baa_engine.api_key_manager import get_key_manager
        km = get_key_manager()
        key_info = km.generate_key(permission="read", label="test-member")
        ag.API_KEYS.add(key_info["raw_key"])
        try:
            resp = admin_client.post(
                f"/api/v1/admin/rbac/roles/{role_id}/members",
                params={"key_id": key_info["key_id"]},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # 验证成员已添加
            detail_resp = admin_client.get(
                f"/api/v1/admin/rbac/roles/{role_id}",
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert detail_resp.json()["role"]["member_count"] >= 1
        finally:
            ag.API_KEYS.discard(key_info["raw_key"])

    def test_add_duplicate_member(self, admin_client, tmp_path, monkeypatch):
        """添加重复成员不应报错。"""
        import src.api.api_globals as ag

        create_resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={"name": "test-role", "permission_level": "read"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        role_id = create_resp.json()["role"]["id"]

        from src.baa_engine.api_key_manager import get_key_manager
        km = get_key_manager()
        key_info = km.generate_key(permission="read", label="test-member")
        ag.API_KEYS.add(key_info["raw_key"])
        try:
            # 第一次添加
            resp1 = admin_client.post(
                f"/api/v1/admin/rbac/roles/{role_id}/members",
                params={"key_id": key_info["key_id"]},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp1.json()["status"] == "ok"

            # 第二次添加应提示已存在
            resp2 = admin_client.post(
                f"/api/v1/admin/rbac/roles/{role_id}/members",
                params={"key_id": key_info["key_id"]},
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp2.json()["status"] == "ok"
            assert "已存在" in resp2.json()["message"]
        finally:
            ag.API_KEYS.discard(key_info["raw_key"])

    def test_remove_member(self, admin_client, tmp_path, monkeypatch):
        """移除角色成员。"""
        import src.api.api_globals as ag

        create_resp = admin_client.post(
            "/api/v1/admin/rbac/roles",
            params={"name": "test-role", "permission_level": "read"},
            headers={"Authorization": "Bearer test-admin-key"},
        )
        role_id = create_resp.json()["role"]["id"]

        from src.baa_engine.api_key_manager import get_key_manager
        km = get_key_manager()
        key_info = km.generate_key(permission="read", label="test-member")
        ag.API_KEYS.add(key_info["raw_key"])
        try:
            # 先添加
            admin_client.post(
                f"/api/v1/admin/rbac/roles/{role_id}/members",
                params={"key_id": key_info["key_id"]},
                headers={"Authorization": "Bearer test-admin-key"},
            )

            # 再移除
            resp = admin_client.delete(
                f"/api/v1/admin/rbac/roles/{role_id}/members/{key_info['key_id']}",
                headers={"Authorization": "Bearer test-admin-key"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
        finally:
            ag.API_KEYS.discard(key_info["raw_key"])

    def test_remove_nonexistent_member(self, admin_client):
        """移除不存在的成员。"""
        resp = admin_client.delete(
            "/api/v1/admin/rbac/roles/some-role/members/nonexistent-key",
            headers={"Authorization": "Bearer test-admin-key"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"
