"""E3-T1：私有部署包验收测试。

验证 deploy/private/ 目录结构、脚本命令、README 内容，以及 Dockerfile/compose 完整性。
集成测试（需运行容器）标记 @pytest.mark.skip。
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestDeployStructure:
    """deploy/private/ 目录与文件结构。"""

    def test_readme_exists(self):
        assert (PROJECT_ROOT / "deploy" / "private" / "README.md").exists()

    def test_deploy_script_unix_exists(self):
        assert (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").exists()

    def test_deploy_script_windows_exists(self):
        assert (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").exists()

    def test_readme_covers_quickstart(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "README.md").read_text(encoding="utf-8")
        assert "快速开始" in content or "quickstart" in content.lower()

    def test_readme_covers_security_section(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "README.md").read_text(encoding="utf-8")
        assert "安全" in content or "生产" in content

    def test_deploy_sh_has_init_command(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").read_text(encoding="utf-8")
        assert "cmd_init" in content or "init)" in content

    def test_deploy_sh_has_up_command(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").read_text(encoding="utf-8")
        assert "cmd_up" in content or "up)" in content

    def test_deploy_ps1_has_init_command(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").read_text(encoding="utf-8")
        assert "Cmd-Init" in content or '"init"' in content

    def test_deploy_ps1_has_up_command(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").read_text(encoding="utf-8")
        assert "Cmd-Up" in content or '"up"' in content


class TestDeployScriptsFunctionality:
    """部署脚本基础功能验证（静态检查，不运行容器）。"""

    def test_deploy_sh_generates_random_key(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").read_text(encoding="utf-8")
        assert "secrets.token_urlsafe" in content or "gen_key" in content

    def test_deploy_sh_checks_prereqs(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").read_text(encoding="utf-8")
        assert "docker" in content.lower()

    def test_deploy_sh_waits_for_health(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.sh").read_text(encoding="utf-8")
        assert "/health" in content

    def test_deploy_ps1_generates_random_key(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").read_text(encoding="utf-8")
        assert "RNGCryptoServiceProvider" in content or "New-RandomKey" in content

    def test_deploy_ps1_waits_for_health(self):
        content = (PROJECT_ROOT / "deploy" / "private" / "deploy.ps1").read_text(encoding="utf-8")
        assert "/health" in content


class TestHealthCheckEndpoints:
    """集成测试：需运行中的 BAA 容器（默认跳过）。"""

    import pytest

    @pytest.mark.skip(reason="需要 docker compose up -d 运行环境")
    def test_health_endpoint_returns_200(self):
        import urllib.request

        resp = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)
        assert resp.status == 200
        data = resp.read().decode()
        assert "subsystems" in data

    @pytest.mark.skip(reason="需要 docker compose up -d 运行环境")
    def test_metrics_endpoint_returns_prometheus(self):
        import urllib.request

        resp = urllib.request.urlopen("http://127.0.0.1:8000/metrics", timeout=5)
        assert resp.status == 200
        body = resp.read().decode()
        assert "baa_http_requests_total" in body

    @pytest.mark.skip(reason="需要 docker compose up -d 运行环境")
    def test_anonymous_request_blocked(self):
        import urllib.request, urllib.error

        try:
            urllib.request.urlopen("http://127.0.0.1:8000/api/v1/functions", timeout=5)
            assert False, "应返回 401"
        except urllib.error.HTTPError as e:
            assert e.code == 401
