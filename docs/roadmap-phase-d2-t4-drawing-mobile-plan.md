# D2-T4 图纸可视化移动端优化方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 2 节 T-D2
> **Roadmap 验收**：双指缩放 + 点击定位
> **写作日期**：2026-10-26
> **前置**：D2-T1 响应式改造完成（commit `9d0cbe3`）、D1 全阶段完成

## 1. 现状分析
- **drawings page**：`src/frontend/ts/components/drawing-viewer.ts` 提供 SVG 交互式查看器（locateEntity 双向定位）。
- **zoom.ts**：仅支持鼠标滚轮缩放 + 拖拽平移 + 键盘，无 touch 手势。
- **drawing-canvas.ts**：canvas 违规 overlay，支持 mousemove tooltip，无 touch。

## 2. 改造目标
- 双指 pinch 缩放 + 单指拖拽平移（touchstart/touchmove/touchend）
- 点击实体卡片 → 定位到 SVG 元素（locateEntity 已有，需移动端适配：滚动到视口中心 + 高亮）
- 移动端工具栏：缩放按钮加大触控目标（≥44px），双击重置

## 3. 改造范围
### 阶段 A：zoom.ts 触控手势（0.5 天）
- touchstart：记录单指/双指初始位置与距离
- touchmove：单指拖拽平移；双指 pinch 缩放（center-based）
- touchend：重置状态
- 双击重置
### 阶段 B：drawing-viewer.ts 移动端适配（0.5 天）
- locateEntity 滚动到视口中心 + 高亮动画
- 移动端工具栏按钮 ≥44px
### 阶段 C：E2E 验证 + commit（0.5 天）
- Playwright touch 事件模拟

## 4. 验收标准
- 双指 pinch 可缩放图纸
- 单指拖拽可平移
- 点击违规卡片定位到图纸元素
- 移动端按钮触控目标 ≥44px
