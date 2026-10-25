# T-C4 安全合规隔离 — 验收证据链

日期：2026-10-25　分支：main

## 1. 目标与范围

Roadmap 阶段 C 的 T-C4「安全合规隔离」：AGPL/GPL 依赖独立进程/微服务；细粒度 RBAC；关闭匿名默认放行。

验收标准（roadmap）：

- 法务可出具合规说明（许可隔离清晰）。
- RBAC 支持细粒度权限；`API_KEYS` 为空不再放行匿名。

## 2. 实现设计

### 2.1 AGPL 许可隔离（PyMuPDF）

- 许可扫描（pip-licenses）：GPL 家族共 4 组——PyMuPDF（**AGPL-3.0**/商业双许可）、
  psycopg/psycopg-binary（LGPL-3.0）、psycopg2-binary（LGPL）、frozendict（LGPLv3）。
- **PyMuPDF 独立进程隔离**：
  - `parsers/pdf_service.py`：CLI worker（`python -m ... pdf_service <pdf> [--page N] [--scale N]`），
    唯一 PyMuPDF 加载进程，stdout 最后一行输出 JSON 结果。
  - `parsers/pdf_isolation.py`：主进程侧封装（**零 PyMuPDF 导入**），subprocess + JSON 通信；
    `BAA_PDF_ISOLATION` 默认 "1"（隔离开），`=0` 仅本地开发回退。
  - `drawing_parser.py` `.pdf` 分支改走 `pdf_to_dxf_isolated`。
  - 进程边界 = 许可边界：两进程仅 CLI 参数 + stdout JSON 通信，无共享内存/动态链接，
    符合 FSF "aggregate" 界定（业界通行的 AGPL 命令行隔离模式，如 Ghostscript）。
- **LGPL 组件**：动态导入 + 未修改源码，符合 LGPL（文档 §3 说明义务）。
- 法务合规说明文档：`docs/compliance/license-isolation.md`（含组件表、隔离架构图、
  持续合规机制、商业许可替换预案）。

### 2.2 细粒度 RBAC（scope 模型）

- `api_key_manager.py`：新增 `PERMISSION_SCOPES` 映射（admin→`*`；write→9 个 scope；
  read→4 个；limited→review:read）+ `has_scope()`；`generate_key(scopes=...)` 支持显式
  scope 子集收窄（如 write 等级仅授予 review:read）；存量密钥无 scopes 字段时按
  permission 映射（向后兼容）。
- `admin_routes.py` `/admin/keys` 支持 body `scopes` 字段。
- `api_globals.py` 新增 `require_scope(scope)` 依赖工厂：DB 密钥校验 scope
  （不足 → 403 INSUFFICIENT_SCOPE）+ 分布式限流；静态配置密钥视为全权限（向后兼容）。
- 已挂载：`/review` → `review:write`；`/deconstruct` → `deconstruct:write`。
  其余读端点保持 `verify_api_key`（认证即可），admin 端点保持 `require_admin`。

### 2.3 关闭匿名默认放行

- `BAA_ALLOW_ANONYMOUS` 默认 "0"：`API_KEYS` 为空时 `verify_api_key` 不再放行匿名（401），
  `require_admin` 直接 403；仅显式 `BAA_ALLOW_ANONYMOUS=1`（本地开发/E2E）恢复旧行为。
- `.env.example` 生产模板默认 0；本机 `.env` 显式设 1（开发/E2E 用，有注释警示）。
- 依赖匿名路径的两处测试夹具（test_webhook / test_p119_correction_notice）已改为显式开启。

## 3. 验收结果

### 3.1 单测（`src/tests/test_security_tc4.py`，13 用例全过）

| 用例 | 验证点 |
|---|---|
| test_permission_scope_mapping | 四级权限 → scope 映射正确，未知权限零授权 |
| test_explicit_scopes_override_permission | 显式 scopes 收窄优先于等级映射 |
| test_generate_key_with_scopes | 建钥持久化 scopes，validate 回读一致 |
| test_env_admin_key_full_scope | 环境变量 admin 通道 `["*"]` |
| test_static_key_passes_scope_check | 静态密钥全权限（向后兼容） |
| test_invalid_key_401 | 无效密钥 401 |
| test_anonymous_denied_by_default | **API_KEYS 为空默认 401（验收硬指标）** |
| test_anonymous_allowed_when_opted_in | BAA_ALLOW_ANONYMOUS=1 恢复匿名 |
| test_require_admin_denied_when_no_keys | 无密钥 admin 通道 403 |
| test_main_process_never_imports_pymupdf | 主链路导入后 sys.modules 无 pymupdf/fitz |
| test_agpl_component_whitelist | GPL 家族组件白名单（新增组件会失败告警） |
| test_pdf_worker_cli_failure_path | 坏 PDF → 子进程 JSON 错误 → 主进程 None |
| test_pdf_isolation_default_on | 隔离默认开启 |

### 3.2 端到端实测

- 生成含线段/矩形/比例尺文字（1:100）的测试 PDF → 隔离子进程解析成功
  （5 lines、scale=100、DXF 落盘）→ 主进程 `sys.modules` 确认无 pymupdf/fitz。
- 临时产物已清理。

### 3.3 回归

- 全量：`2559 passed / 0 failed / 22 skipped`（基线 2546 + 新增 13，见 `regression.txt`）

## 4. 已知限制

- scope 目前挂载在 /review、/deconstruct 两个写端点作代表；其余读端点为认证级
  （verify_api_key）。如需更细颗粒（如 collab:write 独立授权），按同模式逐个挂载即可。
- E2E/前端本地联调依赖 `.env` 的 `BAA_ALLOW_ANONYMOUS=1`；生产部署模板 `.env.example`
  默认为 0，部署 checklist 需确认该值。
