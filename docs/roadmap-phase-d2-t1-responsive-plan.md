# D2-T1 前端响应式改造方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 2 节 T-D2 多端
> **Roadmap 验收**：至少移动端查看 + 离线导出可用
> **写作日期**：2026-10-26
> **前置**：D1 阶段全部完成（T1-T6，5 commits）
> **本方案范围**：D2-T1（Web → 平板/手机响应式），不含 D2-T2 小程序、D2-T3 离线导出、D2-T4 图纸可视化移动端优化

---

## 1. 现状分析

### 1.1 前端架构

- **技术栈**：Vite 6 + TypeScript 5.7 + **纯 DOM 操作**（非 Vue/React，无 .vue/.tsx）
- **构建**：`vite build` 产出 `baa-core-bundle.iife.js`（IIFE 格式，297.73 kB）
- **样式**：`baa.css` 手写内联 Tailwind v3 utility classes（无 CDN，无 PostCSS）
- **入口**：`index.html`（1059 行，15 个 page）+ `ts/main.ts`（模块挂载到 `window.*`）

### 1.2 页面清单（15 个 page）

| # | page id | 标题 | 主要布局 | 响应式优先级 |
|---|---------|------|---------|------------|
| 1 | `page-home` | 系统概览 | `grid-cols-4` 统计卡 + `grid-cols-2` 图表 | 中 |
| 2 | `page-drawings` | 图纸管理与审查 | 上传卡 + 表格 + 内嵌审查面板 | **高** |
| 3 | `page-specs` | 规范与图集库 | `grid-cols-1 sm:grid-cols-4` + 表格 | 中 |
| 4 | `page-review` | AI审图（已合并，`display:none`） | 占位 | 低 |
| 5 | `page-compare` | 审查结果对比 | `grid-cols-2` 双上传 + `grid-cols-5` 摘要 | 中 |
| 6 | `page-analysis` | 统计仪表盘 | `grid-cols-2` + 表格 | 中 |
| 7 | `page-history` | 审查历史记录 | 卡片列表（`space-y-2`） | **高** |
| 8 | `page-apikeys` | API 密钥管理 | `grid-cols-4` + 表格 + Modal | 低 |
| 9 | `page-collab` | 团队协作 | 登录 + `grid-cols-4` + 团队列表 | **高** |
| 10 | `page-reverse` | 反向重构 | `flex flex-col` + `grid-cols-2` 表单 | 中 |
| 11 | `page-funcs` | 原子函数库 | 搜索 + 列表 | 低 |
| 12 | `page-cases` | 行业案例库 | `grid-cols-4` + 列表 + 分页 | 低 |
| 13 | `page-settings` | 连接配置 | 卡片堆叠 | 低 |
| 14 | `page-model-params` | 模型参数导出 | 5 Tab + `grid-cols-1 sm:grid-cols-2` | 低 |
| 15 | `page-cd` | 施工图审查深度标准 | `grid-cols-1 sm:grid-cols-4` + 表格 | 中 |

### 1.3 响应式 CSS 现状

**结论：几乎没有响应式规则，需从零开始。**

- `baa.css` 中 **0 处 `@media`**、**0 处 `@container`**、**0 处断点定义**
- `index.html` 中 **0 处 `@media`**
- `<meta name="viewport" content="width=device-width, initial-scale=1.0">` 已声明（第 5 行）
- 唯一"响应式"痕迹是 Tailwind 的 `sm:` 前缀（`sm:grid-cols-2`、`sm:grid-cols-4`），但 `baa.css` 是**手写内联 utility**，**未定义 `sm:` 断点**，所以这些 `sm:` 类实际**不生效**（死代码）
- 大量使用固定 `grid-cols-2` / `grid-cols-4` / `grid-cols-5`，小屏会挤压
- 侧边栏固定 `w-56`（224px），无折叠逻辑
- 主内容区 `p-6` 固定内边距

### 1.4 E2E 测试现状

**结论：无 E2E 测试，需从零开始。**

- 无 `playwright` / `cypress` / `e2e` 目录或配置文件
- `package.json` 的 `devDependencies` 只有 `vite`、`typescript`、`@types/node`、`vitest`
- `scripts` 无 E2E 脚本

### 1.5 前端单测现状

- 唯一测试文件：`ts/core/utils.test.ts`（27 个用例，全部纯函数）
- **组件层零覆盖**（30+ 组件文件，含 history/review/collab/correction 等）
- 无 jsdom 配置，无 DOM 测试

---

## 2. 改造目标与验收标准

### 2.1 Roadmap DoD（原文）

- [ ] 审查列表页：表格列可折叠，窄屏卡片布局
- [ ] 审查详情页：违规清单与图纸并排 → 窄屏上下堆叠 + 抽屉
- [ ] 工作流闭环（整改/复查）：移动端简化为查看 + 基本操作，完整流程留 PC 端
- [ ] E2E 用 Playwright 视口参数：375 / 768 / 1280 / 1920 四档，每档核心页面无横向滚动 + 无溢出

### 2.2 本方案验收标准（细化）

| 断点 | 视口宽度 | 目标 |
|-----|---------|-----|
| **Mobile** | 375px（iPhone SE） | 侧边栏抽屉化，主内容单列，表格卡片化，无横向滚动 |
| **Tablet** | 768px（iPad 竖屏） | 侧边栏可折叠，主内容 2 列，表格保留但列数减少 |
| **Laptop** | 1280px（MacBook） | 侧边栏固定，主内容 3-4 列，完整表格 |
| **Desktop** | 1920px（4K） | 侧边栏固定，主内容 4-5 列，完整表格 |

**核心页面**（必须通过 4 档视口验证）：
1. `page-home`（系统概览）
2. `page-drawings`（图纸管理与审查）
3. `page-history`（审查历史记录）
4. `page-collab`（团队协作 + 工作流闭环）

---

## 3. 改造范围（分阶段）

### 3.1 阶段 A：CSS 基础层（MVP 核心）

**目标**：建立响应式 CSS 基础设施，不改 DOM 结构。

**改动**：
1. `baa.css` 新增 `@media` 断点定义
2. `baa.css` 补齐 `sm:` / `md:` / `lg:` 前缀的 utility class 定义（让现有 `sm:grid-cols-*` 生效）
3. `baa.css` 新增侧边栏折叠样式（`.sidebar-collapsed`、`.sidebar-drawer`）
4. `index.html` 新增汉堡菜单按钮（移动端显示）

**产出**：
- `baa.css` 新增约 200 行响应式规则
- `index.html` 新增约 10 行汉堡菜单 DOM

**风险**：低（纯 CSS，不改 DOM 结构，不影响现有功能）

### 3.2 阶段 B：侧边栏折叠 + 汉堡菜单

**目标**：移动端侧边栏抽屉化，PC 端保持固定。

**改动**：
1. `index.html` 左侧导航 `<div class="w-56 ...">` 加 `id="sidebar"` 和 `data-sidebar-state`
2. `index.html` 主内容区顶部加汉堡菜单按钮（`#mobile-menu-btn`，移动端显示）
3. `ts/main.ts` 新增 `toggleSidebar()` 函数
4. `baa.css` 新增 `.sidebar-drawer`（移动端抽屉）和 `.sidebar-collapsed`（PC 端折叠）样式

**产出**：
- `index.html` 新增约 15 行
- `ts/main.ts` 新增约 20 行
- `baa.css` 新增约 50 行

**风险**：低（新增功能，不改现有逻辑）

### 3.3 阶段 C：核心页面适配（4 个页面）

**目标**：4 个核心页面在 4 档视口下无横向滚动、无溢出。

**改动**：

#### C1. `page-history`（审查历史记录）

- **现状**：卡片列表（`space-y-2`），已较响应式
- **改动**：
  - 过滤条 `flex.items-center.gap-3.flex-wrap` → 窄屏改 `flex-col`
  - 卡片内部 `flex.items-center.justify-between` → 窄屏改 `flex-col`
  - 详情 Modal `max-w-2xl` → 窄屏改 `max-w-full`

#### C2. `page-drawings`（图纸管理与审查）

- **现状**：上传卡 + 表格 + 内嵌审查面板
- **改动**：
  - 上传卡 `grid-cols-2` → 窄屏改 `grid-cols-1`
  - 表格 `table` → 窄屏加 `overflow-x-auto` 容器
  - 审查面板 `#drawing-review-panel` → 窄屏 `p-2` 替代 `p-4`
  - 6 个 Tab 按钮 `flex.gap-2.flex-wrap` → 窄屏 `flex-wrap` 已生效，加 `min-w-0`

#### C3. `page-collab`（团队协作 + 工作流闭环）

- **现状**：登录区 + `grid-cols-4` 统计 + 团队列表 + Modal 内嵌工作流
- **改动**：
  - 登录区 `grid-cols-2` → 窄屏改 `grid-cols-1`
  - 统计卡 `grid-cols-4` → 窄屏改 `grid-cols-2`
  - 团队列表 → 窄屏卡片化
  - 工作流 Modal `max-w-2xl` → 窄屏改 `max-w-full`
  - 整改记录表 `table.collab-table` → 窄屏加 `overflow-x-auto`

#### C4. `page-home`（系统概览）

- **现状**：`grid-cols-4` 统计卡 + `grid-cols-2` 图表
- **改动**：
  - 统计卡 `grid-cols-4` → 窄屏改 `grid-cols-2`
  - 图表 `grid-cols-2` → 窄屏改 `grid-cols-1`

**产出**：
- `index.html` 修改约 30 行（加 `sm:` / `md:` 前缀）
- `baa.css` 新增约 100 行（页面特定响应式规则）

**风险**：中（改 DOM class，可能影响现有布局）

### 3.4 阶段 D：Playwright E2E 测试（可选，完整版）

**目标**：4 档视口下核心页面无横向滚动 + 无溢出。

**改动**：
1. `package.json` 新增 `@playwright/test` 依赖
2. 新增 `playwright.config.ts`
3. 新增 `e2e/` 目录 + 测试用例
4. `package.json` 新增 `test:e2e` 脚本

**测试用例**：
- `e2e/responsive.spec.ts`：
  - 4 档视口 × 4 个核心页面 = 16 个用例
  - 每个用例：加载页面 → 检查 `document.documentElement.scrollWidth <= window.innerWidth`（无横向滚动）
  - 检查关键元素 `getBoundingClientRect().width > 0`（无溢出）

**产出**：
- `package.json` 新增 1 个依赖 + 1 个脚本
- `playwright.config.ts` 新增约 30 行
- `e2e/responsive.spec.ts` 新增约 100 行

**风险**：中（引入新依赖，CI 需配置浏览器）

---

## 4. 断点设计

### 4.1 CSS 断点

```css
/* baa.css 新增 */
:root {
  --breakpoint-sm: 640px;   /* 手机横屏 */
  --breakpoint-md: 768px;   /* iPad 竖屏 */
  --breakpoint-lg: 1024px;  /* iPad 横屏 */
  --breakpoint-xl: 1280px;  /* MacBook */
  --breakpoint-2xl: 1536px; /* 4K */
}

/* 移动端（< 768px） */
@media (max-width: 767px) {
  .sidebar { display: none; }
  .sidebar-drawer { display: flex; }
  .main-content { padding: 0.5rem; }
  .grid-cols-2, .grid-cols-3, .grid-cols-4, .grid-cols-5 {
    grid-template-columns: 1fr;
  }
}

/* 平板（768px - 1023px） */
@media (min-width: 768px) and (max-width: 1023px) {
  .sidebar { width: 4rem; }  /* 折叠态 */
  .grid-cols-4, .grid-cols-5 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

/* 桌面（>= 1024px） */
@media (min-width: 1024px) {
  /* 保持现有布局 */
}
```

### 4.2 Tailwind 前缀补齐

```css
/* baa.css 新增（让现有 sm:grid-cols-* 生效） */
@media (min-width: 640px) {
  .sm\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .sm\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .sm\:grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

@media (min-width: 768px) {
  .md\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .md\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .md\:grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

@media (min-width: 1024px) {
  .lg\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .lg\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .lg\:grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
```

---

## 5. 侧边栏折叠方案

### 5.1 DOM 结构

```html
<!-- 现状 -->
<div class="flex h-screen">
  <div class="w-56 bg-white border-r ...">  <!-- 侧边栏 -->
    ...
  </div>
  <div class="flex-1 overflow-y-auto p-6">  <!-- 主内容 -->
    ...
  </div>
</div>

<!-- 改造后 -->
<div class="flex h-screen">
  <div id="sidebar" class="w-56 bg-white border-r ... sidebar-desktop">
    ...
  </div>
  <div id="sidebar-drawer" class="sidebar-drawer">  <!-- 移动端抽屉 -->
    <div class="w-56 bg-white border-r ...">
      ...
    </div>
  </div>
  <div class="flex-1 overflow-y-auto p-6">
    <button id="mobile-menu-btn" class="mobile-menu-btn">☰</button>
    ...
  </div>
</div>
```

### 5.2 CSS

```css
/* baa.css 新增 */
.sidebar-drawer {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 100;
}

.sidebar-drawer.open {
  display: block;
}

.sidebar-drawer > div {
  height: 100%;
  overflow-y: auto;
}

.mobile-menu-btn {
  display: none;
  position: fixed;
  top: 1rem;
  left: 1rem;
  z-index: 99;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.5rem;
  padding: 0.5rem;
  cursor: pointer;
}

@media (max-width: 767px) {
  .sidebar-desktop { display: none; }
  .mobile-menu-btn { display: block; }
}
```

### 5.3 JS

```typescript
// ts/main.ts 新增
export function toggleSidebar(): void {
  const drawer = document.getElementById('sidebar-drawer');
  if (drawer) {
    drawer.classList.toggle('open');
  }
}

// 注册到 window
w.toggleSidebar = toggleSidebar;
```

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|-----|-----|---------|
| 改 DOM class 影响现有布局 | 中 | 分阶段改，每阶段跑全量回归 |
| 引入 Playwright 增加 CI 时间 | 低 | E2E 可选，MVP 不引入 |
| 侧边栏抽屉遮挡内容 | 低 | 加半透明遮罩，点击关闭 |
| 表格卡片化改动大 | 中 | 优先加 `overflow-x-auto`，卡片化留后续 |
| 前端单测覆盖不足 | 中 | 阶段 C 前补组件渲染测试（jsdom） |

---

## 7. 执行计划

### 7.1 阶段 A：CSS 基础层（1 天）

- [ ] `baa.css` 新增 `@media` 断点定义
- [ ] `baa.css` 补齐 `sm:` / `md:` / `lg:` 前缀 utility class
- [ ] `baa.css` 新增侧边栏折叠样式
- [ ] 跑 `npm run build:check` 验证构建
- [ ] commit

### 7.2 阶段 B：侧边栏折叠 + 汉堡菜单（0.5 天）

- [ ] `index.html` 左侧导航加 `id="sidebar"`
- [ ] `index.html` 新增汉堡菜单按钮
- [ ] `ts/main.ts` 新增 `toggleSidebar()`
- [ ] 跑 `npm run build:check` 验证构建
- [ ] commit

### 7.3 阶段 C：核心页面适配（2 天）

- [ ] C1. `page-history` 适配
- [ ] C2. `page-drawings` 适配
- [ ] C3. `page-collab` 适配
- [ ] C4. `page-home` 适配
- [ ] 跑 `npm run build:check` 验证构建
- [ ] 手动验证 4 档视口（Chrome DevTools）
- [ ] commit

### 7.4 阶段 D：Playwright E2E（1 天，可选）

- [ ] `package.json` 新增 `@playwright/test`
- [ ] 新增 `playwright.config.ts`
- [ ] 新增 `e2e/responsive.spec.ts`
- [ ] 跑 `npm run test:e2e` 验证
- [ ] commit

**总计**：4.5 天（MVP 3 天 + E2E 1.5 天）

---

## 8. 依赖与前置

- **T-B6 工作流闭环**：已交付（D1 前置）
- **T-C5 PDF 报告**：已交付（D2-T2 前置，非 D2-T1 前置）
- **T-D1 标准集**：已交付（D1 阶段完成）

---

## 9. 后续任务

- **D2-T2 微信小程序查看端**：原生小程序骨架 + 企微 OAuth + PDF web-view
- **D2-T3 离线导出**：`POST /exports/{review_id}` 产出 zip + manifest.json + SDK `export_bundle`
- **D2-T4 图纸可视化移动端优化**：双指缩放 + 拖拽 pan + 点击定位
- **D2-T5 小程序发布**：企微应用创建 + 提审 + 发布
- **D2-T6 多端指标看板**：移动端可用 + 离线导出可用的数据支撑

---

## 10. 附录

### 10.1 关键文件路径

- `src/frontend/index.html`（1059 行，15 个 page）
- `src/frontend/baa.css`（手写 Tailwind utility，无 @media）
- `src/frontend/ts/main.ts`（模块挂载）
- `src/frontend/ts/components/history.ts`（审查列表渲染）
- `src/frontend/ts/components/review.ts`（审查详情渲染）
- `src/frontend/ts/components/collab.ts`（工作流闭环，第 400 行起）
- `src/frontend/package.json`（无 E2E 依赖）
- `src/frontend/vitest.config.ts`（Vitest 配置）

### 10.2 现有断点（Tailwind 默认）

| 前缀 | 断点 | 说明 |
|-----|-----|-----|
| `sm:` | 640px | 手机横屏 |
| `md:` | 768px | iPad 竖屏 |
| `lg:` | 1024px | iPad 横屏 |
| `xl:` | 1280px | MacBook |
| `2xl:` | 1536px | 4K |

**当前 `baa.css` 未定义这些前缀，需补齐。**

### 10.3 现有 `sm:` 类使用位置（死代码）

- `index.html` 第 269 行：`sm:grid-cols-2`
- `index.html` 第 949 行：`sm:grid-cols-4`
- `index.html` 第 969 行：`sm:grid-cols-2`

**补齐 `sm:` 前缀后，这些类会自动生效。**
