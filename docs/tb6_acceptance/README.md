# T-B6 工作流闭环 · 验收证据链

日期：2026-10-20 ｜ 分支：main ｜ 基线：2505 passed / 0 failed（2484 存量 + 21 新增）

## 范围

- **B6-A 工作流闭环**：ReviewStatus 扩展 `rectifying`/`rechecking` + `REVIEW_STATUS_TRANSITIONS` 白名单流转校验（非法流转 400）；新表 `rectification_records` + `rectification.py`（登记/列表/更新 3 端点）；复查端点 `POST /collab/review-sessions/{id}/recheck`（服务端复跑审查，新旧 findings 按 `(clause_id, entity_id, func_id)` 集合差集对比，快照落 `result_summary`）；协作前端状态流转按钮 / 整改登记 / 复查对比 UI。
- **B6-B 违规↔图元双向定位**：`GET /render/{file_id}/interactive`（每图元 `data-eid` + `data-bbox`）；`drawing-viewer.ts`（点击图元联动违规卡片 + `locateEntity` 违规→图元）；违规卡片「📍 定位图元」按钮。

## 验收结果

### ① 闭环端到端可演示（一次完整流转）→ **达标**

- **单测**：`src/tests/test_team_collab_workflow.py` 21/21（状态机流转校验 9 + 整改记录 6 + 复查对比 6）。
- **E2E**：`tests/e2e/test_workflow_loop.spec.ts` **12/12 passed**（Node 20 + Playwright 1.52）：
  W1 注册登录 → W2 建团队/项目 + `/deconstruct` 上传图纸 + 带 `file_ids` 建会话 → W3 详情区块可见 → W4 非法流转（draft→approved）返回 400 且状态不变 → W5 draft→pending→in_progress → W6 整改登记并列表展示 → W7 in_progress→rectifying → W8 复查→rechecking + 对比区渲染 → W9 整改项标记 done → W10 rechecking→rejected→rectifying 闭环 → W11 二次复查→rechecking → W12 rechecking→approved→archived 终态。
- **DB 抽查**（`src/data/collab/baa_collab.db`）：会话 `status=archived`；`result_summary` 含 `rechecked_at`/`rechecked_by`/`last_compare`；`rectification_records` 1 条 `status=done`。
- **复查对比计数为 0 的口径说明**：E2E 夹具合规——离线复现 `run_findings_for_file` 全链路（parse→analyze→规则判定→P70 全局 exist→T-B2 scope 聚合）无异常，实体分类真实发生（test_room.dxf：7 图元→8 语义实体 + 关系/走廊拓扑）；三个夹具探针均 0 findings。`resolved/new/persisted` 非零路径由 T3 单测（monkeypatch 合成 findings）覆盖，非管线空转。

### ② 违规项可跳转到对应图元，反之亦然 → **达标**

- **定位契约（已验证并记录）**：`SemanticEntity.id` 为合成计数 ID（`classify.py`），非 DXF handle（handle 在 `RawPrimitive.handle`，未透传）→ 违规→图元以 **bbox IoU≥0.3 回退为主路径**，`data-eid` 直查保留为优先路径（未来 id 源切换为 handle 时零改动生效）。bbox 来源：`/review?full=true` 返回 `[{id,type,bbox}]` 存入 `window._currentReviewEntities`。
- **违规→图元**：违规卡片「📍 定位图元」→ `locateEntity()`：先 `[data-eid]` 直查（handle 命中场景），失败用该实体 bbox 对 SVG 图元 `data-bbox` 做 IoU 匹配 → 高亮 + scrollIntoView。
- **图元→违规**：interactive SVG 图元点击 → `data-bbox` 与 `_currentReviewEntities` 逐一 IoU，最优匹配 >0.3 → entityId → `[data-entity-id]` 违规卡片闪烁高亮。
- **入口**：审查成功后自动载入交互图（review.ts）；审查页提供「🗺️ 加载交互式图纸」手动入口（index.html）。

## 量化

| 项目 | 结果 |
| --- | --- |
| pytest 全量回归 | **2505 passed / 0 failed**（基线 2484 + 新增 21；14 skipped / 14 deselected 不变） |
| tsc --noEmit | 0 错误 |
| vite build | baa-core-bundle.iife.js 285.41 kB（gzip 64.77 kB），44 modules |
| E2E（本任务 spec） | 12/12 passed，7.0s |

## 过程修复缺陷（4 个）

1. **product_pages.py 文件头双 BOM**（T-B4 时代损坏，非本轮引入）：全量回归 9 failed 根因（U+FEFF×2），剥除后 2505 全绿；全仓扫描确认仅 `src/tools/annotate_ui.py` 单头 BOM 为合法 utf-8-sig，保留。
2. **前端 unknown 可选调用 TS2349**：`(window as unknown as Record<string,unknown>).showToast?.()` 共 8 处不可编译（tsc 探针证实：null 排除后 narrow 到 `{}` 仍不可调用），统一改为 `vite-env.d.ts` 已声明的 `window.showToast?.()`。
3. **补丁脚本竞态**：`tb6_t567_patch.py` 的 collab.ts 追加段 guard 断言误用已写入的同名符号，致 main.ts/index.html 补丁未执行；独立脚本按 MARK 截断失真尾部后以正确转义重放追加。
4. **E2E W2 路由错配**：项目创建实际路由为 `POST /collab/projects`（`team_id` 入 body），非 `POST /collab/teams/{id}/projects`；修正后 12/12 通过。

## 环境与说明

- 跑测须用 Node 20（`D:\tmp\node20\node-v20.18.0-win-x64`）；Node 24 下 Playwright runner 启动挂死（T-B5 已记录，沿用）。
- 协作库实际落盘路径：`src/data/collab/baa_collab.db`（`models.py` DEFAULT_DB_PATH 相对 src 包三层 dirname 计算），非仓库根 `data/`。
- E2E 用户名/邮箱/团队/会话均带时间戳，避免唯一约束冲突；批量审查产品级缺陷未触碰（TD-E2E-005 已另行登记，与 T-B6 无关）。
- 未 commit，待用户确认后执行（T-B6 changeset 含 product_pages.py BOM 修复）。
