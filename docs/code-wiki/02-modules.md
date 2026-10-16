# 02 · 模块职责

本分册按目录树描述各模块职责，并给出关键文件清单。所有路径相对于仓库根目录 `d:\OpenClawData\BAA`。

## 顶层结构

```
BAA/
├── src/
│   ├── api/              # 服务层：FastAPI 路由、全局单例、鉴权、队列
│   ├── baa_engine/       # 引擎层：解析 / 语义 / 原子函数 / 规范 / 报告 / 协作
│   ├── frontend/         # 前端 SPA（TypeScript + Vite，产物 IIFE bundle）
│   ├── sdk/              # Python SDK
│   ├── mcp/              # MCP Server
│   ├── skill/            # TRAE Skill 包
│   ├── tests/            # pytest 测试集
│   └── tools/            # 标注与训练辅助工具（GUI / YOLO）
├── scripts/              # 数据准备 / 标注 / 基准 / 回归 / 真实图纸审计脚本
├── e2e/                  # Playwright 端到端测试
├── k8s/                  # Kubernetes 部署清单
├── docs/                 # 文档（含 code-wiki 本套文档）
├── Dockerfile / docker-compose.yml / wsgi.py / requirements.txt / pyproject.toml
└── ROADMAP.md / VERSION.md / CHANGELOG.md / baa-roadmap.md
```

---

## 1. 引擎层 `src/baa_engine/`

| 文件 / 目录 | 职责 |
| --- | --- |
| `drawing_parser.py` | 图纸解析总入口：格式分发、分页提取、缓存、描叙分类与损坏检测 |
| `parsers/` | 解析实现：DWG 转换、PDF 矢量转换、几何工具、块引用提取 |
| `semantic_analyzer/` | 语义识别：实体分类、房间检测、关系构建、疏散拓扑、户型推断 |
| `atomic_functions.py` | 原子函数框架：定义、注册表、依赖解析、批量执行 |
| `atomic/` | 原子函数定义分片（按规范/主题拆包，共 431 条） |
| `spec_repository.py` | 规范库兼容转发层（指向 `spec_data/`） |
| `spec_data/` | 规范知识库：条款数据分片、版本管理、施工图审查项 |
| `report_generator/` | PDF 审查报告生成（封面 / 评分 / 摘要 / 违规 / 修正） |
| `correction_engine.py` / `llm_correction.py` | 修正建议引擎（规则 / LLM / 混合） |
| `reverse_engine.py` | 反向重构：结构化数据 → DXF / DWG |
| `review_diff.py` | 两份审查结果的差异对比 |
| `attribution_analyzer.py` | 违规归因：条款 + 实体 + 证据链 |
| `dimension_parser.py` | 尺寸标注解析与注入 |
| `drawing_classifier.py` | 图纸类型分类与损坏判定（结构/电气/暖通 = 非建筑图） |
| `task_queue.py` | 审查任务队列（并发控制、进度、超时、webhook 触发） |
| `cache.py` | SQLite 持久化缓存（WAL、TTL/LRU、cache_key 生成） |
| `api_key_manager.py` | API 密钥生命周期管理（生成/哈希/加密/权限/用量） |
| `feedback_engine.py` | 用户反馈闭环与阈值学习（`FeedbackManager` + `LearningEngine`） |
| `yolo_integrator.py` | YOLO 设备检测集成（可选，辅助） |
| `tianzheng_t3.py` | 天正 T3 图纸解析（T3 加密 / T0 明文 / XData） |
| `team_collab/` | 团队协作 ORM 模型与管理器（用户/团队/项目/评审/审批） |
| `collab/audit.py` | 违规审核工作流（确认 / 驳回 / 待定 / PDF 导出） |
| `project_summary.py` | 跨图纸项目级汇总与报告文本格式化 |
| `model_params/exporter.py` | 模型参数导出（函数参数 / 图层规则 / CD 项 / 样本 / SFT / HF） |
| `webhooks.py` | Webhook 回调体构建与触发（generic / feishu / dingtalk） |
| `i18n.py` | 多语言文案（`t()` 翻译 + 语言列表） |

---

## 2. 服务层 `src/api/`

| 文件 / 目录 | 职责 |
| --- | --- |
| `baa_api.py` | FastAPI 应用入口（含核心端点、lifespan、JWT、引擎预热、定期 GC） |
| `api_globals.py` | 全局变量与工具：路径常量、缓存、API Keys、线程池、队列单例、`verify_api_key` |
| `review/` | 审查相关路由集合（见下表） |
| `admin_routes.py` | 密钥管理、任务、webhook、反馈等管理端点 |
| `collab_routes.py` | 协作模块 REST 端点（注册/登录/团队/项目/评审/审批） |
| `collab/audit_routes.py` | 违规审核工作流端点（P119） |
| `model_params_routes.py` | 模型参数导出端点（P93） |
| `render_endpoint.py` | 图纸渲染相关端点 |
| `stats_routes.py` | 统计聚合函数（`get_stats`，供 `/api/v1/stats` 使用） |

### `src/api/review/` 子模块

| 文件 | 职责 |
| --- | --- |
| `__init__.py` | 组装 `router`，惰性 getter（`_get_dp` / `_get_sa` / `_get_fr` …） |
| `review_routes.py` | 审查主链路：`POST /review`、`/review-from-data`、`/thermal/k-value`、`/reconstruct`、`/order/{order_id}`、`/review-multi-sheet` |
| `render_routes.py` | 队列状态、图纸渲染与叠加层、报告 PDF、项目汇总 |
| `compare_routes.py` | `POST /review/compare` 两图对比 |
| `batch_routes.py` | 批量审查（同步 `/batch-review` 与 SSE 流式 `/batch-review-stream`） |
| `history_routes.py` | 审查历史查询 / 删除、队列任务取消 |
| `case_routes.py` | 行业案例库（前缀 `/api/v1`） |
| `_shared.py` | 路由共享工具 |
| `review_history.py` | 审查历史持久化（SQLite） |

---

## 3. 前端 `src/frontend/`

- **构建**：Vite 打包 `ts/main.ts` → `baa-core-bundle.iife.js`，输出到 `src/frontend/` 根，
  由 `index.html` 以 IIFE 方式加载；开发态 dev server 代理 `/api`、`/collab`、`/admin`、`/health`
  到 `127.0.0.1:8000`。
- **页面导航**：`index.html` 定义页签（系统概览 / 图纸管理 / 规范库 / AI 审图 / 对比演示 /
  审查记录 / 统计仪表盘 / 密钥管理 / 连接配置 / 协作 / 反向重构 / 原子函数库 / 案例库 /
  API 文档 / 施工图审查 / 模型参数导出）。

### `ts/core/`（核心逻辑）

| 文件 | 职责 |
| --- | --- |
| `main.ts` | 将 core/ 与 components/ 函数挂载到 `window`（兼容旧 `baa-core.js` 全局调用） |
| `router.ts` | 页签定义与路由切换（hash → `.page`/`.sidebar-item` + 加载函数） |
| `page-nav.ts` | `navigateTo(page)` 分派到各页加载函数 |
| `api-client.ts` | HTTP 客户端封装 |
| `state.ts` / `drawing-state.ts` | 全局状态与图纸状态 |
| `types.ts` | 类型定义 |
| `key-manager.ts` / `admin-keys.ts` / `import-key.ts` | 密钥管理 |
| `spec-data.ts` | 规范数据 |
| `review-panel.ts` / `review-storage.ts` | 审查面板与本地存储 |
| `utils.ts` / `toast.ts` / `skeleton.ts` | 工具、通知、骨架屏 |
| `utils.test.ts` | Vitest 单元测试 |

### `ts/components/`（UI 组件）

`dashboard`、`drawing`、`drawing-canvas`、`zoom`、`specs`、`review`、`review-item`、`review-table`、
`review-storage`、`correction`、`diff-compare`、`feedback`、`history`、`stats`、`collab`、`reverse`、
`model-params`、`cd-items`、`audit`、`export`、`batch-queue`、`sse-batch`、`multi-sheet`、`thermal`、
`structural`、`tools`、`modal`、`filter-bar`、`init` 等。

---

## 4. 接入层

| 目录 | 职责 |
| --- | --- |
| `src/sdk/` | `BAAClient` 轻量 HTTP 客户端（httpx 优先，urllib 兜底），覆盖全部核心端点；`generate_openapi.py` 生成 OpenAPI |
| `src/mcp/baa_mcp_server.py` | MCP Server（`Server("baa-blueprint")`），暴露 `baa_deconstruct` / `baa_review` / `baa_reconstruct` / `baa_health` / `baa_list_functions` / `baa_review_from_data` |
| `src/skill/` | Skill 包：`SKILL.md` + `scripts/baa_client.py`（及 `review.py` / `deconstruct.py` / `reconstruct.py` / `config.py`） |

---

## 5. 测试与脚本

| 目录 | 内容 |
| --- | --- |
| `src/tests/` | 30 个 pytest 测试文件，覆盖引擎 / API / 解析 / 报告 / MCP / SDK / 队列 / webhook |
| `scripts/` | 数据准备、标注、基准、真实图纸审计与 Linux CI 回归脚本（见 [06-run-and-deploy.md](./06-run-and-deploy.md)） |
| `src/tools/` | 标注 GUI（`annotate_ui.py`）、自动标注、YOLO 训练与可视化 |
| `e2e/` | Playwright 烟雾测试（`smoke.spec.ts` / `run_smoke.mjs`） |

### 测试标记（`pyproject.toml`）

- `slow`：慢测试，默认跳过
- `real_drawing`：真实图纸基线，默认跳过，CI 独立阶段运行
- `api`：API 级集成测试

默认执行：`pytest` → 等价于 `-m 'not slow and not real_drawing'`。
