# 05 · 依赖关系

## 1. 运行时依赖（`requirements.txt`）

| 依赖 | 版本约束 | 用途 |
| --- | --- | --- |
| `ezdxf` | `>=1.3.0` | DXF 读写与实体遍历（解析与反向重构核心） |
| `ezdwg` | `>=0.16.0` | DWG 原生解析（纯 Python，第五级兜底），**必须显式声明**以防 CI 环境缺失 |
| `pydantic` | `>=2` | FastAPI 请求/响应模型与校验 |
| `numpy` | — | 几何计算、置信度与矩阵运算 |
| `fastapi` | — | REST API 框架 |
| `uvicorn` | — | ASGI 服务器 |
| `python-multipart` | — | 多段文件上传 |
| `httpx` | — | SDK / webhook 出站 HTTP（SDK 中可选，缺失降级 urllib） |
| `cryptography` | — | AES-GCM 加密（API Key 元数据） |
| `psutil` | — | `/health` 内存与资源上报 |
| `sqlalchemy` | — | 协作模块 ORM（`team_collab`） |
| `reportlab` | — | PDF 审查报告（**运行时必需**，曾在 CI 中漏声明导致 test_p119 失败） |
| `PyMuPDF` (`fitz`) | — | PDF 矢量解析 |
| `pytesseract` | — | OCR（扫描件方向，当前为阻塞项） |
| `pytest` / `pytest-asyncio` / `pytest-cov` / `pytest-xdist` | — | 测试框架与并行/覆盖率 |
| `black` | — | 代码格式化（line-length 100） |

> **可选依赖说明**：`ultralytics`（YOLO）与 LibreOffice（`soffice`）为可选运行依赖。
> 缺失时相关能力优雅降级：YOLO 增强跳过、DWG 导出走其他兜底路径。

## 2. 前端依赖（`src/frontend/package.json`）

- 构建：`vite`（TypeScript），入口 `ts/main.ts`，产物 `baa-core-bundle.iife.js`
- 测试：`vitest`
- 脚本：`dev` / `build` / `build:check` / `preview` / `test` / `test:run` / `typecheck`

根 `package.json`（`baa-e2e`）用于 Playwright E2E：`@playwright/test` + `typescript`。

---

## 3. 模块间依赖关系

```
src/api/baa_api.py
  ├── src/api/api_globals.py            （全局单例、鉴权、线程池、队列）
  ├── src/api/review/                   （审查链路路由）
  ├── src/api/admin_routes.py
  ├── src/api/collab_routes.py
  ├── src/api/collab/audit_routes.py
  ├── src/api/model_params_routes.py
  └── src/api/render_endpoint.py
        │  惰性获取引擎单例
        ▼
src/baa_engine/
  ├── drawing_parser.py ──► parsers/ (dwg_convert / pdf_parser / block_refs / geometry)
  │                     ──► drawing_classifier.py
  ├── semantic_analyzer/ (main + layer_rules + room + relations + evacuation + room_type_infer …)
  ├── atomic_functions.py ──► atomic/ (fire_general / fire_sprinkler / fire_alarm /
  │                                   accessibility / thermal / structural)
  ├── spec_data/ ──► _repo.py + 各标准分片 + versioning + construction_review
  │   (spec_repository.py 为兼容转发层)
  ├── report_generator/ (main + components + cover + score + summary + violations + diff)
  ├── correction_engine.py / llm_correction.py ◄── atomic_functions + spec_data
  ├── attribution_analyzer.py ◄── atomic_functions + spec_data
  ├── reverse_engine.py / review_diff.py / dimension_parser.py
  ├── task_queue.py / cache.py / api_key_manager.py / feedback_engine.py
  ├── webhooks.py / i18n.py / project_summary.py / model_params/exporter.py
  ├── yolo_integrator.py
  └── team_collab/ + collab/audit.py
```

### 关键依赖方向

- **单向**：API 层依赖引擎层；引擎层不反向依赖 API（引擎通过构造参数接收依赖，避免循环导入）。
- **引擎引用注入**：`baa_api._load_engine_sync` 通过 `sys.modules[__name__]` 把引擎实例写回全局，
  `api_globals` 的惰性 getter 再对外暴露。
- **兼容转发**：`src/baa_engine/spec_repository.py` 从 `spec_data._repo` 转发，
  保留旧 import 路径 `from src.baa_engine.spec_repository import SpecRepository, Clause, Threshold`。
- **规范库与判定逻辑解耦**：`Clause` 描述条款，`AtomicFunction` 通过 `clause_id` 关联条款并执行判定；
  阈值可由 `FeedbackManager` / `LearningEngine` 回写 `SpecRepository.set_threshold`。
- **引擎 → 外部命令**：`reverse_engine` 调用 LibreOffice（`BAA_SOFFICE_PATH` 可覆盖默认路径探测）。

---

## 4. 外部依赖与集成

| 外部项 | 用途 | 缺失时行为 |
| --- | --- | --- |
| LibreOffice `soffice` | DWG 导出 / 转换兜底 | 走 `ezdwg` 等其它兜底或跳过导出 |
| `ultralytics` + `yolov8n.pt` / `yolov8m.pt` | 消防设备符号检测（辅助） | 跳过 YOLO 增强 |
| LLM 端点（`BAA_LLM_ENDPOINT` / `BAA_LLM_API_KEY` / `BAA_LLM_MODEL`） | LLM 修正建议 | 退回 `rule` 模式 |
| 字体（TrueType / CJK） | PDF 报告渲染 | `ensure_font` 逐候选 try/except，跨平台容错 |

---

## 5. 数据存储

| 存储 | 位置 | 用途 |
| --- | --- | --- |
| SQLite 缓存 | `src/data/cache/baa_cache.db`（WAL） | `PersistentCache` 审查结果缓存 |
| SQLite 协作 | `src/data/collab/baa_collab.db` | `team_collab` ORM 数据 |
| SQLite 主库 | `src/data/baa_data.db` | 审查历史 / 任务等 |
| JSON | `feedbacks.json`、spec 导出 JSON | 反馈记录、规范库快照 |
