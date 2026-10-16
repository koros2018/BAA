# 06 · 运行方式

## 1. 环境要求

- Python **3.12**
- 依赖见 [05-dependencies.md](./05-dependencies.md)；安装：`pip install -r requirements.txt`
- 可选：Node.js（前端构建 / E2E）、LibreOffice（DWG 导出兜底）、`ultralytics`（YOLO 辅助）

## 2. 本地运行

### 2.1 开发模式

```bash
# 启动开发服务（自动重载）
uvicorn src.api.baa_api:app --reload --port 8000
```

- 交互式 API 文档：`http://localhost:8000/docs`（Swagger）/ `/redoc`
- 健康检查：`GET /health`

### 2.2 生产模式

`wsgi.py` 提供生产入口：

```bash
gunicorn src.api.baa_api:app -k uvicorn.workers.UvicornWorker
```

环境变量：
- `BAA_PORT`（默认 8000）
- `BAA_WORKERS`（worker 数）
- `BAA_TIMEOUT`（超时）

### 2.3 前端

```bash
cd src/frontend
npm install
npm run dev        # 开发（代理 /api、/collab、/admin、/health → 127.0.0.1:8000）
npm run build      # 产出 baa-core-bundle.iife.js 到 src/frontend/
npm run typecheck  # 类型检查
npm test           # Vitest 单元测试
```

前端为 Vite + TypeScript，打包为 IIFE bundle，由 `index.html` 直接加载（非 SPA 框架路由，
通过 `ts/core/router.ts` 做页签切换）。

## 3. 测试

测试配置在 `pyproject.toml`：`testpaths=["src/tests"]`，
默认 `addopts = "-m 'not slow and not real_drawing' --tb=short"`。

```bash
# 默认测试集（排除 slow 与真实图纸基线）
pytest

# 全量（含慢测试）
pytest -m ""

# 真实图纸基线
pytest -m real_drawing

# API 级集成测试
pytest -m api

# 覆盖率
pytest --cov=src --cov-report=term-missing

# 并行
pytest -n auto
```

测试标记：`slow`（默认跳过）、`real_drawing`（CI 独立阶段）、`api`。

`src/tests/conftest.py` 负责设置测试 API key/secret、`TestClient`，并注册上述 markers。

### 代表性测试文件

`test_engine.py`、`test_pdf_pipeline.py`、`test_tianzheng_t3.py`、`test_block_refs.py`、
`test_real_drawings.py`、`test_p121_drawing_classifier.py`、`test_p130_table_exclusion.py`、
`test_atomic_functions_full.py`、`test_api.py`、`test_review_routes.py`、`test_multi_sheet.py`、
`test_pdf_report.py`、`test_mcp_server.py`、`test_sdk_model_params.py`、`test_task_queue.py`、
`test_webhook.py`、`test_llm_correction.py`、`test_construction_review.py`、
`test_reverse_roundtrip.py`、`test_evacuation_connectivity.py`。

### E2E

```bash
npm run e2e          # Playwright 烟雾测试
npm run e2e:gen-dxf  # 生成测试用 DXF
```

---

## 4. 部署

### 4.1 Docker

`Dockerfile` 为两阶段构建（`python:3.12-slim`）：

- **builder**：安装编译依赖（gcc/g++/libc6-dev），`pip install -r requirements.txt`，
  预下载 YOLOv8n 权重
- **runtime**：复制已安装包，清理开发/测试文件，创建数据目录
  `/app/data/files`、`/app/data/models`、`/app/data/logs`、`/app/data/specs`

运行时环境变量：`BAA_PORT`、`BAA_WORKERS`、`BAA_DATA_DIR`、`BAA_API_KEY`、`PYTHONUNBUFFERED=1`。
健康检查 `HEALTHCHECK` 请求 `/health`。入口为 Gunicorn：

```
gunicorn src.api.baa_api:app -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:${BAA_PORT:-8000} --timeout 120 --max-requests 10000 \
  --workers ${BAA_WORKERS:-2} --access-logfile - --error-logfile - --preload
```

### 4.2 docker-compose

```bash
docker compose up -d
```

- 服务 `baa`，端口 `${BAA_PORT:-8000}:8000`
- 卷 `baa_data:/app/data`
- 健康检查 `/health`
- `BAA_API_KEY=${BAA_API_KEY:-baa_dev_2026}`

### 4.3 Kubernetes

清单：`k8s/baa-deployment.yaml`。

---

## 5. CI / CD

GitHub Actions（`.github/workflows/`）：

| Workflow | 触发 | 内容 |
| --- | --- | --- |
| `test.yml` | push/PR → main/develop | `pytest -m "not slow and not real_drawing"` + 覆盖率；另跑 `pytest -m real_drawing` 阶段 |
| `real_drawing_audit.yml` | 每周 / 手动 | `scripts/real_drawing_audit.py`，检查真实图纸基线是否回归 |
| `frontend.yml` | 前端变更 | 前端构建 / 单测 |
| `lint.yml` | push/PR | 代码风格（black） |
| `audit.yml` | — | 依赖/安全审计 |

### 关键脚本

| 脚本 | 用途 |
| --- | --- |
| `scripts/real_drawing_audit.py` | 真实图纸人工标注基线（`GOLD_STANDARD`）：解析 → 语义 → 原子函数 → 对比 |
| `scripts/validate_real_drawings.py` | 真实图纸验证（`--output report.json`） |
| `scripts/linux_ci_regression.py` | Linux CI 全量回归（环境自检 / 字体漂移 / PDF 测试组 / 语义检查 / 真实图纸基线） |
| `scripts/train_pipeline.py` | 训练流水线（inventory / annotate / review / merge / train，支持断点续跑） |
| `scripts/gen_e2e_dxf.py` | 生成 E2E 测试 DXF |
| `src/tools/annotate_ui.py` | 标注 GUI |

---

## 6. 跨平台注意事项

代码需覆盖 Windows / Linux / macOS 差异，重点：

- **字体**：reportlab 渲染需同时探测 TrueType 与 CJK 字体；
  macOS 的 CFF 轮廓字体与 `TTFont` 不兼容，采用 TrueType 优先 + 逐候选 try/except。
- **外部命令**：LibreOffice `soffice` 路径探测需覆盖三类系统的默认安装位置（`BAA_SOFFICE_PATH` 可覆盖）。
- **可选依赖**：`ezdwg` 必须写入 `requirements.txt`，避免 CI 环境缺失掩盖缺陷。
- **验证清单**：见 [docs/cross-platform-checklist-20261015.md](../cross-platform-checklist-20261015.md)。

更多设计与运行细节可参考仓库既有文档：[DEPLOY.md](../DEPLOY.md)、[ci-cd-guide.md](../ci-cd-guide.md)、
[USER_GUIDE.md](../USER_GUIDE.md)、[API.md](../API.md)。
