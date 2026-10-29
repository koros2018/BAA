# E2-T5 前端组件单测 · 验收证据链

日期：2026-10-28 ｜ 分支：main ｜ 状态：✅ 完成

## 范围

v5 Roadmap E2-T5：前端组件单测（Vitest jsdom）

目标：在 jsdom 环境下验证前端核心模块的纯函数与 DOM 操作，覆盖 drawing-state / toast / review-panel / utils 四大模块，达成 ≥15 用例。

## 验收结果

### Vitest 单测 → **达标**

| 测试文件 | 用例数 | 环境 |
|---|---|---|
| `ts/core/utils.test.ts` | 27 | node（纯函数） |
| `ts/core/component.test.ts` | 43 | jsdom（DOM 操作） |
| **合计** | **70** | — |

**运行命令**：`node node_modules/vitest/vitest.mjs run`

### 测试覆盖

#### drawing-state（7 用例）
- `getParsedDrawings` 初始为空数组
- `setParsedDrawings` 设置后返回新值
- `setParsedDrawings` 覆盖而非追加
- `setParsedDrawings` 同步 `window.parsedDrawings`
- `getFileCache` 初始为空对象
- `setFileCache` 按 id 存储文件
- `setFileCache` 同步 `window.fileCache`

#### toast（6 用例）
- `showToast` 创建 `toast-container` 并插入通知
- `showToast` 不同类型有不同 CSS class（error/success/warn）
- `showToast` 限制最多 5 条
- `showToast` 空消息不创建元素
- `showToast` 非字符串消息不创建元素
- `showToast` 挂载到 `window.showToast`

#### review-panel（3 用例）
- `showDrawingReviewPanel` 切换 visibility
- `showDrawingReviewPanel` 找不到 panel 时不抛异常
- `showDrawingReviewPanel` 挂在 window

#### utils（34 用例）
- `formatDate`：4 用例（空值、秒级时间戳、ISO 字符串、非法日期）
- `maskKey`：3 用例（长密钥、短密钥、空值）
- `escHtml`：4 用例（5 个危险字符、安全文本、null/undefined、数字）
- `permissionBadge`：5 用例（admin/write/read/未知/XSS 转义）
- `enabledBadge`：2 用例（启用/禁用）
- `uid`：3 用例（前缀、唯一性、格式正则）
- `mergeDeep`：6 用例（浅层、深层递归、覆盖、数组替换、不修改原对象、空 source）

## 关键修复

1. **vitest.config.ts**：将 `environment: 'node'` 改为 `environment: 'jsdom'`，并开启 `globals: true`（使 `describe`/`it`/`expect`/`beforeEach` 等全局可用）
2. **component.test.ts**：修复原导入路径 `./ts/core/toast` 错误（应为 `./toast`）；用 `vi.resetModules()` 隔离 drawing-state 模块状态
3. **npm install jsdom**：通过 `C:\Users\26988\.trae-cn\binaries\node\versions\24.21.0\npm.cmd` 安装（本机 npm 未加入 PATH）

## 量化

| 项目 | 结果 |
| --- | --- |
| vitest 单测 | **70 passed / 0 failed**（node 27 + jsdom 43） |
| pytest 全量回归 | **2832 passed / 0 failed**（JS 侧改动不影响后端） |
| vite build | 300.56 kB（无 TS 错误） |

## 文件清单

| 文件 | 操作 |
|---|---|
| `src/frontend/vitest.config.ts` | 改 `environment: 'jsdom'` + `globals: true` |
| `src/frontend/ts/core/component.test.ts` | 重写：修复路径、加 jsdom 测试、扩至 43 用例 |
| `src/frontend/package.json` | 新增 `jsdom` devDependency |
| `src/frontend/package-lock.json` | 自动生成 |
