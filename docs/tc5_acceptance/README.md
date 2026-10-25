# T-C5 云端部署流水线 — 验收证据链

日期：2026-10-25　分支：main

## 1. 目标与范围

Roadmap 阶段 C 的 T-C5「云端部署流水线」：CI/CD + 生产配置管理。

验收标准（roadmap）：

- `docker compose up -d` 后生产就绪（一键起服务）。

## 2. 实现设计

### 2.1 一键就绪链路

```
docker compose up -d
  └─ postgres（健康检查 pg_isready）
  └─ baa（依赖 postgres healthy）
       └─ docker-entrypoint.sh：
            1) python -m alembic upgrade head   ← 建表/迁移幂等（T-C1/T-C2）
            2) gunicorn + UvicornWorker --preload
       └─ 健康检查 /health → 生产就绪
```

### 2.2 变更明细

| 文件 | 变更 |
|---|---|
| `Dockerfile` | 入口改 `docker-entrypoint.sh`（先迁移后服务）；版本标签 2.5.80；删除硬编码 `ENV BAA_API_KEY=***`；新增生产安全基线默认值（匿名关/AGPL 隔离/JSON 日志）；HEALTHCHECK 端口改为读 `BAA_PORT` 环境变量 |
| `docker-entrypoint.sh`（新） | `alembic upgrade head` + exec gunicorn；`.gitattributes` 锁定 `*.sh` LF（防 Windows CRLF 导致容器内无法执行） |
| `docker-compose.yml` | 新增 `BAA_ALLOW_ANONYMOUS`（默认 0）、`BAA_PDF_ISOLATION`（默认 1）、`BAA_LOG_FORMAT`（默认 json）；`BAA_API_KEY` 注明生产必须覆盖 |
| `.env.production.example`（新） | 生产配置模板：密钥 CHANGE_ME 占位 + 全部 T-C2/C3/C4 环境变量 |
| `.dockerignore` | 收紧：本地 `.env`（含密钥）/测试/E2E/node_modules/运行产物不进镜像；保留 `data/specs` 规范库与 `alembic/` 迁移脚本在镜像内 |
| `.github/workflows/docker.yml`（新） | 3 job：`build`（PR/main 构建验证）→ `compose_smoke`（见 §3）→ `push_ghcr`（v* 标签推送 GHCR 镜像，冒烟通过才推） |

### 2.3 CI 冒烟验收（compose_smoke job）

可执行的「一键起服务」验收（本机无 docker，由 CI ubuntu runner 执行）：

1. `docker compose up -d --build` 全栈启动
2. 轮询 `/health` 直到 200（最长 10 分钟，失败时自动 dump 两服务日志）
3. 端点验证：`/health` 200；`/metrics` 含 `baa_http_requests_total`；
   **无密钥访问受保护接口返回 401/403**（T-C4 匿名关闭在容器内生效）；
   合法密钥可访问
4. 迁移落库验证：PG 内 public schema 表数 ≥ 13（alembic upgrade 已执行）
5. `docker compose down -v` 清理（always）

### 2.4 静态防漂移测试（`src/tests/test_deploy_config.py`，6 用例）

compose 健康依赖/环境基线、Dockerfile 先迁移后服务、dockerignore 排除密钥且保留规范库、
生产模板占位符、CI 冒烟覆盖验收口径、构建上下文完整性。

## 3. 验收结果

| 项 | 结果 |
|---|---|
| 静态测试 | 6/6 passed |
| 全量回归 | **2565 passed / 0 failed**（基线 2559+6，见 regression.txt） |
| compose YAML / workflow YAML | 语法校验通过 |
| CI 冒烟 | 由 push 后 `.github/workflows/docker.yml` compose_smoke 执行（结果附 GitHub Actions run） |

## 4. 已知限制

- 本开发机无 docker，「一键起服务」可执行验收依赖 CI；本地如需验收需安装 Docker Desktop。
- GHCR 推送仅在打 v* 标签时触发（`ghcr.io/koros2018/baa:<tag>`）。
- 生产部署时 `.env.production.example` 中的 CHANGE_ME 必须替换（BAA_API_KEY / POSTGRES_PASSWORD）。
