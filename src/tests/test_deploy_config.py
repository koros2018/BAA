"""T-C5 部署配置静态验收：Dockerfile / compose / 生产配置模板 / CI 工作流。

本机无 docker 环境，「docker compose up -d 生产就绪」的可执行验收由
.github/workflows/docker.yml 的 compose_smoke job 在 CI 上完成；
此处做静态一致性校验（防配置漂移）。
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_compose_production_ready():
    doc = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = doc["services"]

    pg = services["postgres"]
    assert pg["healthcheck"], "postgres 缺 healthcheck（baa 依赖其就绪）"

    baa = services["baa"]
    assert baa["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert baa["healthcheck"], "baa 缺 healthcheck"
    env = " ".join(baa["environment"])
    # T-C2 无状态化三件套共享 PG
    assert "BAA_DATABASE_URL=postgresql" in env
    assert "BAA_RATE_LIMIT_ENABLED=1" in env
    # T-C4 生产安全基线
    assert "BAA_ALLOW_ANONYMOUS" in env
    assert "BAA_PDF_ISOLATION" in env
    # T-C3 结构化日志
    assert "BAA_LOG_FORMAT" in env


def test_dockerfile_runs_migrations_before_serving():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["./docker-entrypoint.sh"]' in dockerfile
    # 一键就绪关键：起服务前先 alembic upgrade head
    assert "alembic upgrade head" in entrypoint
    assert "gunicorn src.api.baa_api:app" in entrypoint
    # 镜像内不得硬编码密钥值
    assert "BAA_API_KEY=" not in dockerfile or "ENV BAA_API_KEY" not in dockerfile
    # 生产安全基线默认值
    assert "BAA_ALLOW_ANONYMOUS=0" in dockerfile
    assert "BAA_PDF_ISOLATION=1" in dockerfile


def test_dockerignore_excludes_secrets_and_dev():
    content = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    lines = {ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("#")}
    assert ".env" in lines, "本地 .env（含密钥）必须被 dockerignore 排除"
    assert ".env.production.example" in lines
    assert "node_modules/" in lines
    # 规范库 data/specs 必须保留在镜像内（不得出现排除规则）
    assert "data/specs" not in lines and "data/" not in lines


def test_production_env_template():
    content = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    assert "BAA_API_KEY=CHANGE_ME" in content
    assert "BAA_ALLOW_ANONYMOUS=0" in content
    assert "BAA_PDF_ISOLATION=1" in content
    assert "POSTGRES_PASSWORD=CHANGE_ME" in content


def test_docker_ci_workflow_smoke_covers_acceptance():
    doc = yaml.safe_load((ROOT / ".github/workflows/docker.yml").read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    assert "compose_smoke" in jobs
    smoke_steps = " ".join(
        s.get("run", "") for s in jobs["compose_smoke"]["steps"] if isinstance(s, dict)
    )
    # 验收口径：一键起服务 + 健康 + 指标 + 匿名阻断 + 迁移落库
    assert "docker compose up -d --build" in smoke_steps
    assert "/health" in smoke_steps
    assert "/metrics" in smoke_steps
    assert "alembic" not in smoke_steps  # 迁移由容器入口负责，CI 只验证结果
    assert "information_schema.tables" in smoke_steps


def test_alembic_and_requirements_in_image_context():
    """迁移脚本与依赖清单必须包含在镜像构建上下文（不被 dockerignore 排除）。"""
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for needed in ("alembic", "alembic.ini", "requirements.txt", "docker-entrypoint.sh"):
        assert needed not in {
            ln.strip() for ln in ignored.splitlines() if ln.strip() and not ln.startswith("#")
        }, f"{needed} 被 dockerignore 误排除"
