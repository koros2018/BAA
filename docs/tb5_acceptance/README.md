# T-B5 协作前端收尾证据链（认证 → 团队 → 评论 → 审批 全流程 E2E）

> 关联：Roadmap v4 T-B5（G5 / B5）。验收标准：**全流程 E2E ≥ 8 用例通过**。
> 通用 DoD：真实数据验证 / 未达标诚实上报 / 不留技术债 / 真实变更附证据链。

## 一、交付物（5 改 1 新）

| 模块 | 文件 | 内容 |
|---|---|---|
| 后端死代码修复 | `src/api/collab_routes.py` | 删除 `collab_resolve_comment` 中的裸 `return`（D1），端点恢复返回 `{"status":"success"}` |
| 前端字段错配修复 | `src/frontend/ts/components/collab.ts` | D2 评论 `clause_ref/entity_ref` → `clause_id/entity_id`；D3 审批 `order/reviewer_name/acted_at` → `step_order/assignee_name/decided_at`；D4 `createTeam` 改读 `d.team.id`；D5 `createProject` 改读 `d.project.id`；D6 空态改判 `flow.steps.length` |
| 前端写操作 UI | 同上 | 新增 11 个导出函数：`submitComment`/`resolveComment`/`showApprovalFlowForm`/`createApprovalFlow`/`approveApprovalStep`/`showRejectStepModal`/`rejectApprovalStep`/`updateSessionStatus`/`showAddMemberModal`/`searchUsersForMember`/`addTeamMember`；`showReviewSessionDetail` 内追加评论表单 + 审批发起区，`showTeamDetail` 内追加「+ 添加成员」入口 |
| 入口挂载 | `src/frontend/ts/main.ts` | collab import 块 + window 暴露段各追加 11 处 |
| 构建产物 | `src/frontend/baa-core-bundle.iife.js`（+ `.map`） | `npm run build` 重建（272148 B） |
| E2E 用例 | `tests/e2e/test_collab_flow.spec.ts`（新建） | 10 用例：C1 注册登录 → C2 建团队 → C3 加成员 → C4 建项目 → C5 建审查会话 → C6 会话详情 → C7 发表评论 → C8 标记已解决 → C9 发起审批 → C10 批准步骤 |

## 二、验收结果

| 验收条款 | 结果 | 证据 |
|---|---|---|
| 全流程 E2E ≥ 8 用例通过（认证→团队→评论→审批） | **通过** | `test_collab_flow.spec.ts` **10/10 passed**，实际跑通全链路（注册/登录 → 建团队 → 加成员 → 建项目 → 建审查会话 → 评论 → 解决 → 发起审批 → 批准） |

各套件实测：

| 套件 | 用例数 | 结果 |
|---|---|---|
| `test_collab_flow.spec.ts`（本轮新增，验收对象） | 10 | **10 passed** |
| `test_login_logout.spec.ts`（本轮修复 2 处存量 bug 后） | 1 | **1 passed** |
| 全量 E2E 套件（含存量） | 25 | 18 passed / 7 failed（7 例均为存量环境性/用例缺陷，见三；其中 5 例已于 2026-10-19 关闭） |

## 三、存量 E2E 失败（登记时 7 例，与 T-B5 无关）

| 用例 | 失败原因 | 性质 | 现状 |
|---|---|---|---|
| `test_audit_flow.spec.ts:23` | `created.created = 0`（details 缺 `result` 字段被后端过滤） | 存量用例缺陷 | **已修复**（TD-E2E-004，1/1 passed） |
| `test_batch_review.spec.ts:6` | `ENOENT` fixture（陈旧 WSL 挂载路径 + 旧 UI 流程） | 环境 + 用例 | **已修复**（TD-E2E-003） |
| `test_drawing_upload.spec.ts:8` | 同上 | 环境 + 用例 | **已修复**（TD-E2E-003） |
| `test_drawing_upload.spec.ts:25` | 同上 | 环境 + 用例 | **已修复**（TD-E2E-003） |
| `test_single_review.spec.ts:6` | 同上 | 环境 + 用例 | **已修复**（TD-E2E-003） |
| `test_regression.spec.ts:14`（AI 审查） | `[data-page="review"]` 在 `index.html:36` 为 `display:none`，不可见 → click 超时 | 存量用例缺陷 | 开放（TD-E2E-001） |
| `test_regression.spec.ts:14`（报告） | `[data-page="reports"]` 在 `index.html` 侧栏中不存在（实际无该项）→ 定位失败 | 存量用例缺陷 | 开放（TD-E2E-002） |

以上 7 例均为 T-B5 改动前即失败的环境性/存量缺陷，不涉及 collab 模块。修复进展：**TD-E2E-003（4 例）+ TD-E2E-004（1 例）已修复并回归通过 → 5/7 关闭**；剩余 2 例（TD-E2E-001/002，`test_regression`）仍开放。全部登记见 `docs/tech_debt/README.md`。

## 四、过程真实缺陷修复

1. **后端死代码（D1）**：`collab_resolve_comment` 内 `raise HTTPException(...)` 之后存在裸 `return`，其后 `return {"status":"success"}` 永不执行 → 端点实际返回 `None`。删除裸 `return`。
2. **前后端字段契约错配 5 处（D2–D6）**：前端读字段名与后端 `models.py` 各 `to_dict()` 权威输出不一致，导致评论条款/实体、审批步骤顺序/审批人/时间、团队与项目新建后 ID 全部取空。
3. **存量用例 `test_login_logout` 两处缺陷**：① 邮箱硬编码 `e2e@test.com`，与持久化 `data/collab/baa_collab.db` 中历史用户唯一约束冲突（注册返回 400）→ 改带时间戳邮箱；② `button:has-text("退出")` 在 `index.html` 有 2 处（`#user-status-logged-in` 内与协作主区），触发 Playwright strict mode 冲突 → 改为 `#user-status-logged-in button:has-text("退出")` 作用域限定。
4. **新增用例 3 处断言 bug（本轮内修复）**：注册成功后 `showCollabLogin()` 会隐藏注册表单致 `#collab-reg-msg` 不可见；`#collab-user-display` 与 `#member-results` 显示 `display_name` 而非 `username`，原断言按 username 匹配必失败。
5. **存量 E2E 用例缺陷（TD-E2E-003/004）**：见三/`docs/tech_debt/README.md` 四之已关闭条目。

## 五、未达标 / 环境约束诚实上报

- **Playwright 1.52.0 test runner 与本机 Node 24.14.1 不兼容**：`@playwright/test` runner 启动即挂死——无任何输出、进程 CPU≈0；`--list` 与实跑均挂，而 `--help`/`--version` 正常。已通过差分实验排除浏览器缺失、config 内容、spec 文件、输出目录、stdio 未关闭、IPC 等因素，定位为 Node 版本兼容问题。
  - **绕过方案（已落地）**：以 Node 20.18.0 运行 runner：`& 'D:\tmp\node20\node-v20.18.0-win-x64\node.exe' 'D:\OpenClawData\BAA\node_modules\@playwright\test\cli.js' test -c tests/e2e/playwright.config.ts <spec>` → 正常跑出。
  - 本机唯一系统 Node 为 `D:\hclaw\node` v24.14.1（无 nvm/fnm）。**该约束需写入本地/CI 跑测文档**（见七）。
- **存量 E2E 失败**：登记时 7 例（见三）；截至 2026-10-19 已修复 5 例（TD-E2E-003 的 4 例 + TD-E2E-004 的 1 例），剩余 2 例（TD-E2E-001/002）仍开放，已列技术债。

## 六、回归

| 项目 | 命令 | 结果 |
|---|---|---|
| 后端全量回归 | `python -m pytest src/tests -q` | **2484 passed, 14 skipped, 14 deselected, 0 failed**（27.05s） |
| 协作全流程 E2E | playwright `test_collab_flow` | 10/10 passed |
| 登录登出 E2E | playwright `test_login_logout` | 1/1 passed |
| 存量修复回归 E2E | playwright `test_batch_review test_drawing_upload test_single_review` | 4/4 passed |
| 存量修复回归 E2E | playwright `test_audit_flow` | 1/1 passed |

与 T-B5 前基线一致，无新增 FAIL。服务跑测后已停机（端口 8000 释放）。

## 七、复现

```powershell
# 1. 后端全量回归
python -m pytest src/tests -q

# 2. 启动服务（需手动启动，playwright 配置无 webServer）
python -m uvicorn src.api.baa_api:app --port 8000

# 3. 协作全流程 E2E —— 注意：本机须用 Node 20 运行 Playwright runner
& 'D:\tmp\node20\node-v20.18.0-win-x64\node.exe' 'D:\OpenClawData\BAA\node_modules\@playwright\test\cli.js' test -c tests/e2e/playwright.config.ts test_collab_flow
```

## 八、约束备注

- 协作 DB 持久化（`data/collab/baa_collab.db`），E2E 用户名/邮箱一律带时间戳后缀规避唯一约束冲突。
- 前端为 IIFE bundle（`baa-core-bundle.iife.js`），改动 TS 后须 `npm run build` 重建方可生效。
