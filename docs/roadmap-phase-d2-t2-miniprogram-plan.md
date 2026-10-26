# D2-T2 微信小程序查看端方案

> **来源**：`docs/roadmap-phase-d-execution-plan.md` 第 2 节 T-D2  
> **Roadmap 验收**：轻量只读报告查看器，企业微信 OAuth 登录  
> **写作日期**：2026-10-26  
> **前置**：D2-T1 响应式改造完成（commit `9d0cbe3`）、D1 全阶段完成  
> **本方案范围**：D2-T2（原生小程序骨架 + 企微 OAuth + PDF web-view），不含 D2-T3/D2-T4/D2-T5  

---

## 1. 现状分析

### 1.1 代码库现状
- **无小程序代码**：工作树与主项目均无 `miniprogram/`、`pages/`、`app.json` 等文件。
- **后端报告接口**：`GET /reports?status=completed&user=me` 已存在（T-B6 交付，`collab_routes.py` / `baa_api.py`）。
- **PDF 报告**：T-C5 报告生成器产出，可通过 `GET /reviews/{id}/report` 获取 PDF。
- **认证体系**：现有 JWT/API Key 体系（`api_globals.py`、`auth` middleware），无企业微信 OAuth 回调。
- **前端技术栈**：Vite + TS + 纯 DOM，小程序与 Web 完全解耦。

### 1.2 参考资料
- 微信开放平台：企业微信 OAuth 2.0（`wwauth2`）。
- 微信小程序 API：`wx.login` / `wx.request` / `web-view`（PDF 需 HTTPS 公网域名，且需备案）。

---

## 2. 改造目标与验收标准

### 2.1 Roadmap DoD（原文）
- [ ] 小程序骨架：`app.json` 2 页（报告列表 / 报告详情）。
- [ ] 登录：企业微信 OAuth（后续可扩微信开放平台）。
- [ ] 报告列表：调 `GET /reports?status=completed&user=me`。
- [ ] 报告详情：PDF 直接 web-view 打开。
- [ ] **不做**：上传/审查/整改/复查/图纸可视化。

### 2.2 本方案验收标准
| 验收项 | 标准 |
|--------|------|
| 小程序编译 | 微信开发者工具无报错，2 个页面可导航 |
| 登录链路 | 企业微信 OAuth → 后端换 token → 小程序存储 token → 自动登录 |
| 报告列表 | 展示 review_id、项目名、标准集、审查日期、状态；下拉刷新 |
| 报告详情 | PDF web-view 全屏打开，支持下载/分享（可选） |
| 异常处理 | 无网络 / token 过期 / 空列表 / PDF 加载失败有友好提示 |
| 安全 | token 存 Storage（非 globalData），HTTPS 域名白名单 |

---

## 3. 改造范围（分阶段）

### 3.1 阶段 A：小程序骨架 + 页面结构（0.5 天）

**目标**：建立最小可运行的小程序工程，2 个页面可导航。

**改动**：
1. 新建 `miniprogram/` 目录（独立于 `src/frontend/`，避免 Vite 构建干扰）。
2. `app.json`：2 个页面 + tabBar（可选）+ 窗口配置。
3. `app.js`：全局 `globalData` + token 管理 + 请求封装。
4. `pages/index/index`（报告列表）：基础布局 + 空状态。
5. `pages/detail/detail`（报告详情）：接收 `review_id` 参数 + web-view 占位。

**产出**：
- `miniprogram/app.json` + `app.js` + `app.wxss`
- `miniprogram/pages/index/*`（4 文件）
- `miniprogram/pages/detail/*`（4 文件）
- `miniprogram/utils/request.js`（封装 `wx.request` + token 注入 + 错误统一处理）

**风险**：低（新建目录，不改现有代码）

### 3.2 阶段 B：企业微信 OAuth 登录（1 天）

**目标**：小程序内完成企业微信 OAuth，后端签发 JWT，小程序存储并自动携带。

**改动**：

#### 后端（`src/api/`）
1. 新增 `GET /api/v1/auth/wechat-work/callback`：接收 `code` + `state`，调企业微信 `getuserinfo` 接口，映射到本地 `users` 表（新建或复用），签发 JWT。
2. 新增 `GET /api/v1/auth/wechat-work/url`：返回企业微信 OAuth 授权 URL（含 `redirect_uri` 白名单校验）。
3. 新增 `users` 表字段 `wechat_work_userid`（或新建 `oauth_bindings` 表），Alembic 迁移。

#### 小程序
1. `pages/login/login`（或 index 页内嵌登录态）：调 `wx.login` 获取 `code`，发送到后端 `/auth/wechat-work/callback`，存储 token。
2. token 过期自动跳转登录页（401 拦截）。

**产出**：
- 后端：`src/api/auth/wechat_work_routes.py` + `src/baa_engine/db/models/oauth.py` + Alembic 迁移
- 小程序：登录流程 + token 管理

**风险**：中（企业微信审核/Secret 配置，D2-T5 再正式发布）

### 3.3 阶段 C：报告列表 + 详情 web-view（1 天）

**目标**：报告列表展示 + PDF web-view 打开。

**改动**：

#### 报告列表页
- 调 `GET /reports?status=completed&user=me`，分页加载（`page`/`page_size`）。
- 卡片展示：项目名、审查日期、标准集、违规数摘要。
- 下拉刷新 + 触底加载更多。
- 点击跳转详情页（传 `review_id`）。

#### 报告详情页
- 接收 `review_id` 参数。
- 调 `GET /reviews/{review_id}/report` 获取 PDF URL（或直接拼接）。
- `<web-view src="{{pdfUrl}}"></web-view>` 全屏展示。
- 异常：PDF 加载失败显示重试按钮。

**产出**：
- 小程序 2 个页面完整实现
- 后端确认 `/reviews/{id}/report` 返回可直接 web-view 的 URL（需 HTTPS 公网域名）

**风险**：中（web-view 要求业务域名备案，本地调试用开发者工具）

### 3.4 阶段 D：异常处理 + 埋点（0.5 天）

**目标**：健壮性 + 多端指标。

**改动**：
1. 空状态、无网络、token 过期、PDF 加载失败的 UI 提示。
2. 后端新增 Prometheus 指标 `baa_mobile_reports_viewed_total`（D2-T6 范畴，可提前埋点）。
3. 小程序 `app.js` 中 `onShow`/`onHide` 生命周期埋点（可选）。

**产出**：
- 异常处理代码
- 指标埋点

---

## 4. 技术选型

| 选型 | 决策 | 理由 |
|------|------|------|
| 框架 | 原生小程序 | 跨平台 + 企业微信快速接入，避免 uni-app 额外技术栈 |
| 登录 | 企业微信 OAuth 2.0 | 企业客户场景，后续可扩微信开放平台 |
| PDF 展示 | web-view | 复用 T-C5 产出，不做原生 PDF 渲染 |
| 请求封装 | `wx.request` + token 注入 | 标准小程序模式 |
| 状态管理 | globalData + Storage | 轻量，无 Redux/MobX 需求 |

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 企业微信审核/Secret 配置周期不确定 | 中 | D2-T5 作为最后一步，技术先到位，审核期间本地调试 |
| web-view 要求 HTTPS 公网域名备案 | 中 | 开发阶段用开发者工具本地预览；生产用已备案域名 |
| 小程序与 Web 后端 API 版本不一致 | 低 | API 版本号 `/api/v1/`，小程序锁定 v1 |
| 用户体系映射复杂（企业微信 userid → 本地 user） | 中 | 新建 `oauth_bindings` 表，保持解耦 |
| 无 E2E 测试覆盖（小程序） | 中 | 微信开发者工具自动化 + 手动验收 checklist |

---

## 6. 执行计划

### 6.1 阶段 A：小程序骨架（0.5 天）
- [ ] 新建 `miniprogram/` 目录
- [ ] `app.json` + `app.js` + `app.wxss`
- [ ] `pages/index/index`（报告列表空壳）
- [ ] `pages/detail/detail`（报告详情空壳）
- [ ] `utils/request.js`（请求封装）
- [ ] 微信开发者工具编译通过

### 6.2 阶段 B：企业微信 OAuth（1 天）
- [ ] 后端 `src/api/auth/wechat_work_routes.py`
- [ ] DB `oauth_bindings` 表 + Alembic 迁移
- [ ] 小程序登录流程 + token 存储
- [ ] 401 拦截 + 自动跳转登录

### 6.3 阶段 C：报告列表 + 详情（1 天）
- [ ] 报告列表页：API 调用 + 卡片渲染 + 分页 + 下拉刷新
- [ ] 报告详情页：web-view PDF 打开
- [ ] 异常处理（空状态、加载失败）

### 6.4 阶段 D：异常 + 埋点（0.5 天）
- [ ] 全局异常处理
- [ ] Prometheus `baa_mobile_reports_viewed_total` 埋点
- [ ] 手动验收 checklist

**总计**：3 天

---

## 7. 依赖与前置

- **T-C5 PDF 报告**：已交付（报告生成器稳定）
- **T-D1 标准集**：已交付（标准集信息在报告里）
- **D2-T1 响应式**：已完成（Web 端基础）
- **D2-T3 离线导出**：可选并行，小程序可后续消费 zip

---

## 8. 后续任务

- **D2-T3 离线导出**：`POST /exports/{review_id}` 产出 zip + manifest.json
- **D2-T4 图纸可视化移动端优化**：双指缩放 + 点击定位
- **D2-T5 小程序发布**：企业微信应用创建 + 提审 + 发布
- **D2-T6 多端指标看板**：移动端可用 + 离线导出可用的数据支撑

---

## 9. 附录

### 9.1 关键文件路径（新建）
- `miniprogram/app.json`
- `miniprogram/app.js`
- `miniprogram/pages/index/index.*`
- `miniprogram/pages/detail/detail.*`
- `miniprogram/utils/request.js`
- `src/api/auth/wechat_work_routes.py`
- `src/baa_engine/db/models/oauth.py`
- `alembic/versions/xxx_add_oauth_bindings.py`

### 9.2 企业微信 OAuth 流程
1. 小程序调 `wx.login` → 获取 `code`
2. 小程序发送 `code` 到后端 `/api/v1/auth/wechat-work/callback`
3. 后端用 `code` 调企业微信 `getuserinfo` → 获取 `userid`
4. 后端映射 `userid` → 本地 `user_id`，签发 JWT
5. 小程序存储 JWT，后续请求自动携带

### 9.3 安全域名配置
- request 合法域名：`https://api.yourdomain.com`
- web-view 业务域名：`https://report.yourdomain.com`（需 ICP 备案）
- socket 合法域名：无（本方案不使用 WebSocket）