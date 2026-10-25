"""T-C4 安全合规隔离单测：细粒度 RBAC（scope）、匿名默认关闭、AGPL 进程隔离。"""

import os
import sys

import pytest


# ── 细粒度 RBAC ────────────────────────────────────────────


class TestScopeModel:
    def test_permission_scope_mapping(self):
        from src.baa_engine.api_key_manager import PERMISSION_SCOPES, has_scope

        assert has_scope({"permission": "admin"}, "review:write")
        assert has_scope({"permission": "write"}, "review:write")
        assert has_scope({"permission": "write"}, "deconstruct:write")
        assert not has_scope({"permission": "read"}, "review:write")
        assert has_scope({"permission": "read"}, "review:read")
        assert not has_scope({"permission": "limited"}, "deconstruct:write")
        assert has_scope({"permission": "limited"}, "review:read")
        # 未知权限不授予任何 scope
        assert not has_scope({"permission": "bogus"}, "review:read")
        assert PERMISSION_SCOPES["admin"] == ["*"]

    def test_explicit_scopes_override_permission(self):
        from src.baa_engine.api_key_manager import has_scope

        # 显式 scopes 优先于 permission 映射（write 等级收窄为只读 review）
        info = {"permission": "write", "scopes": ["review:read"]}
        assert has_scope(info, "review:read")
        assert not has_scope(info, "review:write")
        assert not has_scope(info, "deconstruct:write")

    def test_generate_key_with_scopes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'k.db'}")
        from src.baa_engine.api_key_manager import ApiKeyManager

        km = ApiKeyManager()  # _use_db → 共享测试库
        r = km.generate_key(permission="write", scopes=["review:read"], label="narrow")
        info = km.validate_key(r["raw_key"])
        assert info["scopes"] == ["review:read"]

        r2 = km.generate_key(permission="read", label="default")
        info2 = km.validate_key(r2["raw_key"])
        assert "review:read" in info2["scopes"]
        assert "review:write" not in info2["scopes"]

    def test_env_admin_key_full_scope(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BAA_DATABASE_URL", f"sqlite:///{tmp_path / 'k2.db'}")
        from src.baa_engine.api_key_manager import ApiKeyManager, has_scope

        km = ApiKeyManager(env_key="env-admin-key")
        info = km.validate_key("env-admin-key")
        assert info["scopes"] == ["*"]
        assert has_scope(info, "review:write")


class TestRequireScopeEndpoint:
    """HTTP 层 scope 强制（/deconstruct 已挂 require_scope("deconstruct:write")）。"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient

        from src.api.baa_api import app

        return TestClient(app)

    def test_static_key_passes_scope_check(self, client):
        # 静态配置密钥（test-api-key 在 API_KEYS 中）视为全权限（向后兼容）
        resp = client.post(
            "/deconstruct", headers={"Authorization": "Bearer test-api-key"}
        )
        assert resp.status_code in (400, 422)  # 缺文件参数 → 业务校验，非 401/403

    def test_invalid_key_401(self, client):
        resp = client.post(
            "/deconstruct", headers={"Authorization": "Bearer nope-nope-nope"}
        )
        assert resp.status_code == 401


# ── 匿名默认关闭 ───────────────────────────────────────────


class TestAnonymousGate:
    @pytest.fixture
    def no_keys(self, monkeypatch):
        import src.api.api_globals as ag

        saved = set(ag.API_KEYS)
        ag.API_KEYS.clear()
        yield monkeypatch
        ag.API_KEYS.update(saved)

    def test_anonymous_denied_by_default(self, no_keys):
        from fastapi.testclient import TestClient

        from src.api.baa_api import app

        no_keys.delenv("BAA_ALLOW_ANONYMOUS", raising=False)
        resp = TestClient(app).get("/api/v1/functions")
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "UNAUTHORIZED"

    def test_anonymous_allowed_when_opted_in(self, no_keys):
        from fastapi.testclient import TestClient

        from src.api.baa_api import app

        no_keys.setenv("BAA_ALLOW_ANONYMOUS", "1")
        resp = TestClient(app).get("/api/v1/functions")
        assert resp.status_code == 200

    def test_require_admin_denied_when_no_keys(self, no_keys):
        from src.api import api_globals as ag

        no_keys.delenv("BAA_ALLOW_ANONYMOUS", raising=False)
        with pytest.raises(Exception) as exc_info:
            ag.require_admin(request=None, api_key="")
        assert getattr(exc_info.value, "status_code", None) == 403


# ── AGPL 许可隔离 ──────────────────────────────────────────


class TestLicenseIsolation:
    def test_main_process_never_imports_pymupdf(self):
        """导入主链路模块后，sys.modules 不得出现 pymupdf/fitz。"""
        import importlib

        for mod in ("pymupdf", "fitz"):
            sys.modules.pop(mod, None)
        importlib.import_module("src.baa_engine.drawing_parser")
        importlib.import_module("src.baa_engine.parsers.pdf_isolation")
        importlib.import_module("src.baa_engine.parsers.pdf_service")
        assert "pymupdf" not in sys.modules
        assert "fitz" not in sys.modules

    def test_agpl_component_whitelist(self):
        """GPL 家族组件清单白名单：新增 AGPL/GPL 组件必须显式更新本文档与隔离方案。"""
        import json
        import subprocess

        out = subprocess.run(
            [sys.executable, "-m", "piplicenses", "--format=json"],
            capture_output=True,
            text=True,
        )
        pkgs = json.loads(out.stdout)
        gpl_family = [
            p["Name"]
            for p in pkgs
            if any(
                t in (p.get("License") or "")
                for t in ("AGPL", "GPL", "LGPL", "Affero")
            )
        ]
        # 白名单：AGPL 仅 PyMuPDF（已进程隔离）；LGPL 动态链接合规
        allowed = {
            "PyMuPDF",
            "psycopg",
            "psycopg-binary",
            "psycopg2-binary",
            "frozendict",
        }
        assert set(gpl_family) <= allowed, f"新增未评审 GPL 家族组件: {set(gpl_family) - allowed}"

    def test_pdf_worker_cli_failure_path(self, tmp_path):
        """隔离子进程对坏输入返回 JSON 错误（非零退出码），主进程得到 None。"""
        from src.baa_engine.parsers.pdf_isolation import pdf_to_dxf_isolated

        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        assert pdf_to_dxf_isolated(str(bad)) is None

    def test_pdf_isolation_default_on(self, monkeypatch):
        from src.baa_engine.parsers.pdf_isolation import pdf_isolation_enabled

        monkeypatch.delenv("BAA_PDF_ISOLATION", raising=False)
        assert pdf_isolation_enabled() is True
        monkeypatch.setenv("BAA_PDF_ISOLATION", "0")
        assert pdf_isolation_enabled() is False
