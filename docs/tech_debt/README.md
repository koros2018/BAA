# 技术债登记表（Tech Debt Registry）

> 记录已知但未修复的问题：现象 / 根因 / 影响 / 建议动作 / 优先级 / 状态。新增条目按表追加到「三、开放项」。
> 发现来源集中在各阶段验收证据链目录 `docs/*_acceptance/`。

## 一、本次登记背景

- 来源：**T-B5 协作前端收尾** 全量 E2E 跑测（2026-10-19），共 25 用例 = 18 passed / **7 failed**。
- 性质：7 例失败均**与 T-B5 协作模块改动无关**（T-B5 仅改 collab 前后端 + 新增协作 E2E）；T-B5 验收对象 `test_collab_flow` 10/10 通过。
- 复现方式：见 `docs/tb5_acceptance/README.md` 第七节（**本机须用 Node 20 运行 Playwright runner**）。

## 二、失败清单（登记时 7 例）

| # | 用例 | 失败现象 | 归因条目 |
|---|---|---|---|
| 1 | `test_regression.spec.ts:14`（AI 审查） | `click` 120s 超时，`[data-page="review"]` 元素不可见 | TD-E2E-001 |
| 2 | `test_regression.spec.ts:14`（报告） | `[data-page="reports"]` 定位失败 | TD-E2E-002 |
| 3 | `test_batch_review.spec.ts:6` | `ENOENT ... \mnt\d\OpenClawData3workspace\...\fixtures\test_basic.dxf` | TD-E2E-003 |
| 4 | `test_drawing_upload.spec.ts:8` | 同上 `ENOENT test_basic.dxf` | TD-E2E-003 |
| 5 | `test_drawing_upload.spec.ts:25` | 同上 `ENOENT test_basic.dxf` | TD-E2E-003 |
| 6 | `test_single_review.spec.ts:6` | 同上 `ENOENT test_basic.dxf` | TD-E2E-003 |
| 7 | `test_audit_flow.spec.ts:23` | POST `/api/v1/audit/items` 返回 2xx 但 `created.created = 0` | TD-E2E-004 |

## 三、开放项

| ID | 来源 | 现象 | 根因 | 影响 | 建议动作 | 优先级 | 状态 |
|---|---|---|---|---|---|---|---|
| TD-E2E-001 | T-B5 全量 E2E | `test_regression.spec.ts:14`「加载 AI 审查 页面不报错」`click` 超时 | `[data-page="review"]` 在 `src/frontend/index.html:36` 带 `style="display:none"`，元素永久不可见 | 回归 smoke 误报失败，掩盖真实回归 | 用例改断言可见侧栏项，或改为按路由加载校验；同时确认 review 页是否本应隐藏 | P2 | 开放 |
| TD-E2E-002 | T-B5 全量 E2E | `test_regression.spec.ts:14`「加载 报告 页面不报错」定位失败 | `index.html` 侧栏无 `data-page="reports"`（报告功能未在侧栏注册；现有相近项为 `history`/`analysis`） | 同上 | 确认报告页入口，修正选择器或在侧栏补入口 | P2 | 开放 |
| TD-E2E-005 | TD-E2E-003 修复过程发现 | `#batch-file-input` 选择文件后 `#batch-review-start-btn` 点击无反应 | ① `window.batchFiles` 全仓无赋值点（`sse-batch.ts:54` 只读不写）→ 读 `undefined.length` 抛错；② 按钮 `data-action="runBatchReviewSSE"` 未挂到 window（`sse-batch.ts` 实际暴露名为 `window.runBatchReview`）→ `resolveAction` 返回 undefined 静默不执行 | 「批量审查」Tab（SSE 实时进度）整条 UI 不可用 | 在 `init.ts` 为 `#batch-file-input` 绑定 change 写入 `window.batchFiles`，并把按钮 `data-action` 改为 `runBatchReview`；补 E2E 守护 | P2 | 开放（未修，仅登记） |

## 四、已关闭

| ID | 来源 | 结论 | 关闭日期 | 提交 |
|---|---|---|---|---|
| TD-E2E-003 | T-B5 全量 E2E（4 例：`test_batch_review` ×1 / `test_drawing_upload` ×2 / `test_single_review` ×1） | 根因两层：① fixture 路径硬编码陈旧 WSL 挂载 `/mnt/d/OpenClawData3workspace/...`，且 `__dirname` 在 ESM 作用域不可用 → 改为 `E2E_FIXTURE_DIR` 环境变量优先、回退 `path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures")`；② 用例体仍是迁移前旧流程（假设隐藏的 `page-review` 侧栏页 + batch 多文件输入）→ 重写为当前 Tab 化真实流程（`uploadAndReview` 触发上传解析 → `showDrawingReviewPanel` 开面板 → 单图 `selectOption`+`runReview`；批量走图纸列表多选 + `#batch-review-btn`）。实测 **4/4 passed（0 flaky）**。batch Tab 的 SSE 入口另有独立缺陷，单列 TD-E2E-005 | 2026-10-19 | `e188ef5` |
| TD-E2E-004 | T-B5 全量 E2E（1 例 `test_audit_flow`） | 根因：后端 `create_items_from_review` 仅创建 `result in ("FAIL","CONFIRMED")` 的条目，用例 details 缺 `result` 字段 → 全部被静默跳过 → `created=0`。修法：用例 details 补 `result:"FAIL"`（3 处），与后端权威契约对齐。实测 **1/1 passed** | 2026-10-19 | `e188ef5` |

## 五、修复提交与推送记录（2026-10-19）

- 提交 `e188ef5`（14 文件，+677/−122）：含 T-B5 协作前端收尾交付 + TD-E2E-003（4 例）/ TD-E2E-004（1 例）修复；**TD-E2E-005 未修复，不在此提交内**。
- 提交 `1ac9d9f`：修正 `docs/tb5_acceptance/README.md` 中本机 Node 的事实表述（Node 26 本机未安装，列出实际路径）。
- 推送：`git push origin main` 成功（git 输出 `b74ebc6..e188ef5` 与 `e188ef5..1ac9d9f` → `main`）。
- 远端复核：`git ls-remote origin -h refs/heads/main` 多次因本机到 github.com:443 间歇不可达失败，未取得远端 sha；以推送时 git 自身输出为准，网络恢复后可再复核。
- TD-E2E-005 现状：**开放（未修）**；「批量审查」Tab（`#batch-file-input` + `#batch-review-start-btn`）整条 UI 仍不可用，修法见三。
