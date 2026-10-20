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
（无——2026-10-20 阶段 A/B 收口全部关闭）

## 四、已关闭

| ID | 来源 | 结论 | 关闭日期 | 提交 |
|---|---|---|---|---|
| TD-E2E-003 | T-B5 全量 E2E（4 例：`test_batch_review` ×1 / `test_drawing_upload` ×2 / `test_single_review` ×1） | 根因两层：① fixture 路径硬编码陈旧 WSL 挂载 `/mnt/d/OpenClawData3workspace/...`，且 `__dirname` 在 ESM 作用域不可用 → 改为 `E2E_FIXTURE_DIR` 环境变量优先、回退 `path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures")`；② 用例体仍是迁移前旧流程（假设隐藏的 `page-review` 侧栏页 + batch 多文件输入）→ 重写为当前 Tab 化真实流程（`uploadAndReview` 触发上传解析 → `showDrawingReviewPanel` 开面板 → 单图 `selectOption`+`runReview`；批量走图纸列表多选 + `#batch-review-btn`）。实测 **4/4 passed（0 flaky）**。batch Tab 的 SSE 入口另有独立缺陷，单列 TD-E2E-005 | 2026-10-19 | `e188ef5` |
| TD-E2E-004 | T-B5 全量 E2E（1 例 `test_audit_flow`） | 根因：后端 `create_items_from_review` 仅创建 `result in ("FAIL","CONFIRMED")` 的条目，用例 details 缺 `result` 字段 → 全部被静默跳过 → `created=0`。修法：用例 details 补 `result:"FAIL"`（3 处），与后端权威契约对齐。实测 **1/1 passed** | 2026-10-19 | `e188ef5` |
| TD-E2E-001 | T-B5 全量 E2E | 用例对齐侧栏现实：review 入口按设计隐藏（P112 审图并入图纸管理），新增断言 `toBeHidden()`；实测通过 | 2026-10-20 | 待提交（阶段 A/B 收口 changeset） |
| TD-E2E-002 | T-B5 全量 E2E | 报告无独立侧栏页（由审查记录 history 承载），用例改指 `[data-page="history"]`；实测通过 | 2026-10-20 | 待提交（阶段 A/B 收口 changeset） |
| TD-E2E-005 | TD-E2E-003 修复过程发现 | 三层根因全修：① `init.ts` 绑定 `#batch-file-input` change → `window.batchFiles`（原全仓无赋值点）+ `getBatchFiles()` 加固（undefined→[] 免 TypeError）；② 按钮 `data-action` 改为实际挂载名 `runBatchReview`；③ 深层根因：sse-batch 模块自 P125 起被 vite tree-shake 整体摇掉（main.ts 仅 import 不使用，模块内隐式挂载不存活）——`main.ts` 显式 `w.runBatchReview = runBatchReviewSSE` 修复；新增守护用例（change 赋值断言 + `/batch-review-stream` 请求断言）；全量 E2E 38/38 | 2026-10-20 | 待提交（阶段 A/B 收口 changeset） |

## 五、修复提交与推送记录（2026-10-19）

- 提交 `e188ef5`（14 文件，+677/−122）：含 T-B5 协作前端收尾交付 + TD-E2E-003（4 例）/ TD-E2E-004（1 例）修复；**TD-E2E-005 未修复，不在此提交内**。
- 提交 `1ac9d9f`：修正 `docs/tb5_acceptance/README.md` 中本机 Node 的事实表述（Node 26 本机未安装，列出实际路径）。
- 推送：`git push origin main` 成功（git 输出 `b74ebc6..e188ef5` 与 `e188ef5..1ac9d9f` → `main`）。
- 远端复核：`git ls-remote origin -h refs/heads/main` 多次因本机到 github.com:443 间歇不可达失败，未取得远端 sha；以推送时 git 自身输出为准，网络恢复后可再复核。
- TD-E2E-005 现状：**已关闭（2026-10-20）**；「批量审查」Tab（SSE 实时进度）修复并带守护用例，详见「四、已关闭」。
