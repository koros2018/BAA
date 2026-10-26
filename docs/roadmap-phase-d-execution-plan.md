# BAA Roadmap 阶段 D · 详细执行计划

> **来源**：`docs/baa-roadmap-v4-tasks.md` 阶段 D（6 月+）· 规模化与商业化
> **基线**：v2.5.80-stable / 阶段 C 全闭环（T-C1~T-C8 交付、全量回归 2616 passed / 0 failed）
> **写作日期**：2026-10-26
> **节奏**：按 **价值-依赖序** 排列，先让引擎能服务不同地域客户（D1），再扩大渠道（D2），最后商业闭环（D3/D4）。

---

## 0. 总体原则（承接阶段 C 经验）

1. **验收口径先行**：每个子任务先写 DoD（Definition of Done），再动手。DoD 必须可自动化断言（回归测试 / 数据对比 / 接口冒烟）。
2. **依赖显式化**：T-D4（付费）依赖 T-C2 用量计量 + T-D1 标准库切换 + T-D3 交付物，**不得跳过前置**。
3. **不做的事先声明**：`baa-roadmap-v4-tasks.md` 已列"6 个月内明确不做"项（GNN/VLM/数字孪生/YOLOv11 主线/新增原子函数/重构 IFC·STEP 主线），D 阶段坚守边界。
4. **证据链落 `docs/tdN_acceptance/`**：延续 T-C1~T-C8 命名风格。

---

## 1. T-D1 多标准 / 地方尺度库（关联 G4）

**Roadmap 验收**：覆盖主要地方规范尺度差异，可切换标准集。
**现状**：`spec_data/` 有 GB50016 / GB50974 / GB50116 / GB50763 共 4 个国标；无地标；无"标准集"抽象；无运行时切换。

### D1-T1 标准集抽象层 + 运行时切换（技术基座）

**目标**：引入 `StandardSet` 概念（一组标准条文 + 尺度参数 + 版本号），审查管线按请求参数动态加载。
**DoD**：
- [ ] `src/baa_engine/standards.py` 新建：`StandardSet` dataclass（`code`/`name`/`version`/`clause_paths`/`scale_overrides`）+ `list_sets()` + `load_set(code)`。
- [ ] 现有 4 国标打包为 `sets/CN-National-v1.json`（不改 spec_data 原始文件，JSON 仅做清单+版本标记）。
- [ ] API 层 `POST /reviews` 新增 `standard_set_code` 可选参数，缺省 `CN-National-v1`；错误 code 返回 400。
- [ ] `test_standard_set.py`：注册/加载/缺省/未知 code 4 项；`export_knowledge.py --code CN-National-v1` 包内 version 字段对齐。

**依赖**：T-C6（knowledge bundle 架构已交付，版本字段已有）
**风险**：标准集与原子函数阈值耦合度高（同一 `width>=1.2` 条文在不同地标可能不同），切换层必须**只替换 spec 条文 + 注入尺度参数到原子函数 threshold**，不得改函数本体。

### D1-T2 尺度参数注入原子函数（阈值可配置）

**目标**：把现有原子函数硬编码阈值（如 `MIN_CORRIDOR_WIDTH = 1.2`）提取为可注入参数。
**DoD**：
- [ ] `src/baa_engine/atomic/` 下 422 函数盘点：哪些有硬编码尺度阈值（约 30 个），输出清单 `docs/td1_scale_inventory.md`。
- [ ] 引入 `ScaleContext` 上下文对象，审查管线启动时按 `standard_set` 注入，原子函数内通过 `ctx.get_threshold("MIN_CORRIDOR_WIDTH")` 替代常量。
- [ ] **默认值不变**：注入缺省为现有常量值，确保不指定 `standard_set` 时行为完全回归。
- [ ] 单测：`test_scale_injection.py` 覆盖 5 个改造函数（疏散宽度 / 楼梯净宽 / 门洞 / 防火间距 / 净高），对比注入前后结果一致（阈值未变） + 注入地标阈值后结果可变。

### D1-T3 首批地标导入（2 套）

**目标**：选 2 套代表性地标做 MVP，验证标准集切换能改变审查结果。
**DoD**：
- [ ] 选用地标：**上海地标**（DGJ08-2048）和**广东地标**（DBJ15-31）——覆盖疏散/防火间距典型差异。
- [ ] 仅差异条文入 spec_data（复用国标条文不改，地标只存 diff clauses）。
- [ ] `StandardSet` 加载时做 **国标为底 + 地标覆盖** 合并（同一 clause_id 地标优先级高）。
- [ ] 证据链：用同一张图纸跑 `CN-National` vs `CN-Shanghai`，输出 diff JSON（哪些 finding 消失 / 新增 / 阈值变更）。

### D1-T4 标准集管理面板（前端只读）

**目标**：前端审查配置页可选择标准集，审查结果页显示所用标准集信息。
**DoD**：
- [ ] 审查创建表单新增 `标准集` 下拉（API 取 `GET /standards`）。
- [ ] 审查报告页新增"依据标准集：XX v1"栏。
- [ ] 不改工作流闭环（T-B6 已交付），仅加一个字段。

### D1-T5 指标看板更新

**目标**：Roadmap 指标看板把"规范覆盖"从文字描述升级为可量化。
**DoD**：
- [ ] 新增 `prometheus` 指标 `baa_spec_standards_total{code}`（已安装数）与 `baa_spec_scale_overrides_total`（累计尺度参数覆盖数）。
- [ ] 证据链 `/metrics` 端点新增两个指标。

---

## 2. T-D2 多端（关联 G6）

**Roadmap 验收**：至少移动端查看 + 离线导出可用。
**现状**：前端纯 Web（Vite + Vue 3）；PDF 报告已有（report_generator）；SDK 已有（T-C6 交付 wheel）；无移动端。

### D2-T1 前端响应式改造（Web → 平板/手机）

**目标**：现有 Web 页面能在 1024px / 375px 两档断点下正常用。
**DoD**：
- [ ] 审查列表页：表格列可折叠，窄屏卡片布局。
- [ ] 审查详情页：违规清单与图纸并排 → 窄屏上下堆叠 + 抽屉。
- [ ] 工作流闭环（整改/复查）：移动端简化为查看 + 基本操作，完整流程留 PC 端。
- [ ] E2E 用 Playwright 视口参数：375 / 768 / 1280 / 1920 四档，每档核心页面无横向滚动 + 无溢出。

**依赖**：T-B6（工作流已交付，有现成页面）
**风险**：前端单测 38 项（E2E），视口改 DOM 结构可能断断言；必须用 `.toContain` 而非精确 DOM 匹配。

### D2-T2 微信小程序查看端（轻量只读）

**目标**：做一个轻量"报告查看器"小程序，不做审查/整改操作。
**DoD**：
- [ ] 小程序骨架：`app.json` 2 页（报告列表 / 报告详情）。
- [ ] 登录：企业微信 OAuth（后续可扩微信开放平台）。
- [ ] 报告列表：调 `GET /reports?status=completed&user=me`（接口已存在，T-B6）。
- [ ] 报告详情：PDF 直接 web-view 打开（PDF 已由 T-C5 报告生成器产出）。
- [ ] **不做**：上传/审查/整改/复查/图纸可视化（留 Web 端）。

**依赖**：T-C5（PDF 报告稳定）、T-D1（标准集信息在报告里）
**选型**：原生小程序（跨平台+微信生态+企业微信快速接入），不选 uni-app（当前只做微信，没必要加技术栈）。

### D2-T3 离线导出：DXF/PDF/报告包

**目标**：用户可下载完整交付包，断网可查看。
**DoD**：
- [ ] `POST /exports/{review_id}` 产出 zip（含 DXF 源文件副本 + PDF 报告 + IFC/STEP 导出 + 标准集版本标记 manifest.json）。
- [ ] 依赖：T-C4（PDF/IFC/STEP 均已交付导出接口）。
- [ ] manifest.json 字段：`review_id` / `exported_at` / `standard_set` / `ifc_path` / `step_path` / `dxf_sha256` / `report_version`。
- [ ] SDK 新增 `export_bundle(review_id)` 方法（wheel 更新）。

### D2-T4 图纸可视化移动端优化

**目标**：Web 端图纸定位已有（T-B6 交付），移动端优化缩放/点击定位体验。
**DoD**：
- [ ] 移动端图纸页：双指缩放 + 拖拽 pan + 点击违规项自动定位。
- [ ] 违规标记气泡：移动端改小图标 + 触达后浮层。
- [ ] 不做实时编辑（移动端审查留 Web/PC）。

### D2-T5 小程序发布 + 企业微信配置

**目标**：小程序上架企业微信/微信开放平台，企业客户可扫码接入。
**DoD**：
- [ ] 企业微信应用创建 + Secret 配置 + 后端 OAuth 回跳 URL 白名单。
- [ ] 小程序提审通过 → 发布。
- [ ] 内部管理员账号（本地环境 + 线上各一个）验证查看链路。

### D2-T6 多端指标看板更新

**目标**：验收口径"移动端可用 + 离线导出可用"有数据支撑。
**DoD**：
- [ ] Prometheus 指标 `baa_mobile_reports_viewed_total` / `baa_export_bundle_generated_total`。
- [ ] 报告页脚新增"导出 zip"按钮，点击打埋点。

---

## 3. T-D3 客户成功体系与交付物标准（关联 G28）

**Roadmap 验收**：定义交付物标准与客户成功流程并落地。
**现状**：PDF 报告粗糙（无封面/无项目信息/模板单一）；整改通知单无；客户成功流程未定义。

### D3-T1 交付物包模板化

**目标**：审查报告从"纯违规清单"升级为可交付给客户的完整文档。
**DoD**：
- [ ] 新增 `src/baa_engine/report_generator/cover.py`：封面（项目名/甲方/乙方/日期/图纸清单/标准集）。
- [ ] 新增 `summary.py` + 重写 `violations.py`：违规清单 + 严重度聚合 + 按楼层/构件分组。
- [ ] 模板：至少 2 套（国标审查 / 地标审查），企业可上传自定义模板（JSON 配置）。
- [ ] 现有 5 张图纸样本跑出两套报告，视觉回归（封面图元/字号/表格列对齐）。

**依赖**：T-D1（标准集元数据注入封面）
**风险**：reportlab Table 嵌套单元格会崩（T-C5 踩过的坑），新表格必须用 FONTNAME 属性。

### D3-T2 整改通知单 + 复查意见模板

**目标**：从审查报告中一键生成整改通知单与复查意见。
**DoD**：
- [ ] 新增 `src/baa_engine/report_generator/correction_notice.py`：输入 review_id + 需整改 finding 列表 → 输出 Word 模板（python-docx）。
- [ ] 模板字段：项目信息 / 整改内容 / 整改要求 / 整改期限 / 整改人 / 发单日期。
- [ ] 复查意见：整改完成后生成 Word（整改项 vs 复查结果对照表）。
- [ ] SDK 新增 `generate_correction_notice(review_id, finding_ids)` 方法。

**依赖**：T-B6（整改/复查已在 Web 端闭环，有 review ID 可用）

### D3-T3 客户成功流程 SOP（落地文档 + 接口）

**目标**：定义"新客户接入 → 首次审查 → 整改闭环 → 续约"全流程，并把关键节点落库。
**DoD**：
- [ ] `docs/customer-success-sop.md`：流程文档（onboarding 6 步、首轮审查 3 步、整改闭环 4 步、续约触发条件）。
- [ ] DB 新增 `review_projects` 表：`project_id` / `customer_name` / `standard_set_code` / `owner` / `status`（onboarding/first_review/correction/recheck/closed）。
- [ ] `POST /projects` + `PATCH /projects/{id}/status` 接口，配合现有 review 创建接口。
- [ ] 证据链：端到端 `创建项目 → 首轮审查 → 整改 → 复查 → 归档` 跑通。

### D3-T4 交付物版本化 + SDK 兼容矩阵

**目标**：交付物包有版本标记，SDK 对不同交付包版本做兼容。
**DoD**：
- [ ] 交付物 zip 的 manifest.json 新增 `report_schema_version` 字段。
- [ ] SDK `KnowledgeBundle` + 新增 `ReportBundle` 类，schema 版本不匹配抛 `VersionMismatchError`。
- [ ] SDK 文档页维护兼容矩阵（SDK 版本 × 交付物 schema 版本）。

**依赖**：T-C6（SDK 架构已交付，三重校验逻辑可复用）

---

## 4. T-D4 SLA 与付费闭环（关联 G27）

**Roadmap 验收**：有定价/SLA 且产生首个付费信号（收入闭环）。
**现状**：API Key + 用量计量已交付（T-C2）；无计费逻辑；无 License 模块；无 Stripe/微信支付集成。

### D4-T1 定价与 SLA 文档

**目标**：明确三个版本的能力边界 + SLA 承诺 + 试用/付费流程。
**DoD**：
- [ ] `docs/pricing-sla.md`：**免费版 / 专业版 / 企业版**，每版含：标准集范围 / 并发数 / 月审查量 / 离线导出 / 客户成功支持等级 / SLA（可用性/响应时间/数据备份）。
- [ ] 定价草案：免费版无 License；专业版按"账号 + 月审查量 50 张"；企业版按部署形态（SaaS / 私有部署）协商。
- [ ] 法务预检：许可协议框架 + 数据处理协议。

**风险**：法务需要时间，先用 Draft 文档跑通业务流程再法务审核。

### D4-T2 License 模块 + 在线/离线校验

**目标**：系统启动时校验 License 文件，按版本启用/禁用功能。
**DoD**：
- [ ] `src/baa_engine/license.py`：License 文件读取 + RSA 签名校验 + 到期日 + 版本字段 + 离线模式。
- [ ] 启动时 `license_manager.validate()`，校验失败降级为免费版（不阻塞，不丢数据）。
- [ ] 功能开关由 License 驱动：
  - T-D1 标准集切换（专业版 + / 企业版）
  - T-D2 小程序访问（企业版 +）
  - T-D3 模板化交付物（专业版 +）
- [ ] 单测：`test_license.py` 覆盖正常 / 过期 / 签名篡改 / 版本不匹配 / 离线模式 5 场景。

**依赖**：T-D1 / T-D2 / T-D3（各模块预留 `_license_gate()` hook）

### D4-T3 用量计费 + Stripe / 微信支付集成

**目标**：Web 端用量统计 → 结算 → 在线购买 → 自动续期。
**DoD**：
- [ ] 计费核心：T-C2 用量计量（`api_key_usage` 表）已交付，新增 `billing_cycles` 表：`cycle_id` / `api_key` / `start` / `end` / `review_count` / `rate` / `amount_due` / `status`。
- [ ] 结算任务：每日 0 点后台任务，按上一 cycle 统计用量，触发超额告警。
- [ ] 支付集成：Stripe Checkout（海外）+ 微信支付 Native 下单（国内），回调更新 `billing_cycles.status = paid`。
- [ ] 试用：首次创建 api_key 自动激活 14 天试用，到期降级。
- [ ] SDK 查询：`api_key.get_billing_summary()` 返回当前 cycle 用量。

**依赖**：T-C2（用量计量）+ D4-T1（定价）

### D4-T4 首个付费信号验收

**目标**：产生 1 笔真实付费，打通全链路。
**DoD**：
- [ ] 内测：内部 2 个同事各买 1 个专业版，走微信/Stripe 两通道。
- [ ] 验收：License 文件自动发放 + 版本升级生效 + 用量按 cycle 清零 + 续期提醒。
- [ ] 证据链：支付截图 + License 校验日志 + 功能开关生效验证。

---

## 5. 里程碑与依赖关系

```
                    T-D1 标准集 + 尺度注入 ────┬──▶ T-D3 交付物模板化
                    (D1-T1 ~ T-D1-T5)         │
                                                ├──▶ T-D4 License 模块 + 计费
  阶段 C 交付（T-C1~T-C8） ────┐                │    (D4-T1 ~ D4-T4)
                                │                │
                                ├──▶ T-D2 多端 ◀──┘
                                │    (D2-T1 ~ D2-T6)
                                │
                                └──▶ T-D3 交付物标准
                                    (D3-T1 ~ D3-T4)
```

| 里程碑 | 任务组合 | 前置 | 预计 |
|---|---|---|---|
| M1 可切换标准集 | D1-T1 + D1-T2 + D1-T3 | 阶段 C 全量回归 | 1 周 |
| M2 多端可用 + 离线导出 | D2-T1 ~ D2-T6 | M1 | 2 周 |
| M3 交付物模板化 + 客户成功 SOP | D3-T1 ~ D3-T4 | M1 | 1.5 周 |
| M4 License + 付费闭环 | D4-T1 ~ D4-T4 | M1 + M3 | 2 周 |

---

## 6. 资源与风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| 地标条文数据版权问题（抄规范原文侵权） | 🔴 高 | 只存 diff 条款 + 条文号引用原文，原文放客户侧（`scale_overrides` 仅阈值数字） |
| 企业微信审核/微信支付商户号审批时间不确定 | 🟡 中 | 技术先到位，D2-T5 作为最后一步，审核期间小程序可先本地测试 |
| Stripe/微信支付 webhook 签名校验复杂度 | 🟡 中 | 用官方 SDK，自己不实现签名逻辑；webhook 回调必须在公网（ngrok/临时隧道调试） |
| License RSA 密钥丢失 = 全平台瘫痪 | 🔴 高 | 私钥 3 份备份 + HSM / 云 KMS；公钥嵌入二进制永不丢失 |
| 原子函数阈值全量改造可能断存量客户审查结果 | 🔴 高 | 默认值保持不变（注入缺省回退到现有常量），改造完成后 2616 存量回归 **必须零退化** |

---

## 7. 明确不做（阶段 D 坚守）

| 不做项 | 理由 |
|---|---|
| YOLOv11 迁移主线 / GNN 拓扑推理 / VLM 端到端 / 数字孪生 3D Tiles | 商业验证前不投入（Roadmap 明确） |
| 新增原子函数（容量已满，422 个） | 走阈值/规则调优，不扩容量 |
| IFC/STEP 深化（弧形墙/SI 单位/IfcOpeningElement） | 已作为独立支线 T-C8 交付基础版，等付费信号再深化 |
| iOS 原生 App / 钉钉微应用 | 先做微信小程序企业微信接入，渠道已覆盖主要客户 |
| 自研支付网关 / 自研 OAuth | 用 Stripe + 微信支付 SDK，用企业微信 OAuth |
| 重构审查引擎 / 换语言 | 技术债登记表 0 条，无重构压力 |

---

## 8. 指标看板更新

Roadmap 已有指标看板在 T-B6 交付时补齐前端 E2E 用例；D 阶段新增：

| 指标 | 当前 | D 阶段目标 |
|---|---|---|
| 审查标准集切换数 | 0（仅 4 国标） | ≥3（国标+2 地标） |
| 移动端报告查看量 | 0 | ≥10% 总查看量 |
| 离线导出 zip 下载量 | 0 | ≥5% |
| 付费 License 激活数 | 0 | ≥5 |
| 交付物版本化 bundle 数 | 0 | ≥3 |

---

## 9. 任务清单汇总（可追溯 DoD）

| 代码 | 任务 | 核心 DoD | 依赖 | 预计 |
|---|---|---|---|---|
| **D1-T1** | 标准集抽象层 + 运行时切换 | API 新增 `standard_set_code` 参数 + 4 单测 | T-C6 | 2d |
| **D1-T2** | 尺度参数注入原子函数 | 30 函数盘点 + ScaleContext + 默认值不变 + 5 单测 | 阶段 C 引擎 | 3d |
| **D1-T3** | 首批地标导入（上海/广东） | StandardSet 合并机制 + diff JSON 证据链 | D1-T1 | 2d |
| **D1-T4** | 标准集管理面板（前端） | 审查表单下拉 + 报告页标注 | T-B6 前端 | 1d |
| **D1-T5** | Prometheus 指标 | 2 新指标 /metrics 可查 | T-C3 | 0.5d |
| **D2-T1** | 前端响应式改造 | 4 视口断点 E2E 全过 | T-B6 | 2d |
| **D2-T2** | 微信小程序查看端 | 2 页 + 企业微信 OAuth + PDF web-view | D2-T1 + T-B6 | 3d |
| **D2-T3** | 离线导出 zip（DXF+PDF+IFC+STEP） | manifest.json + 4 文件打包 + SDK 方法 | T-C4/C8 | 1d |
| **D2-T4** | 图纸可视化移动端优化 | 双指缩放 + 点击定位 | T-B6 | 1d |
| **D2-T5** | 小程序发布 + 企业微信配置 | 应用创建 + Secret 配置 + 管理员验证 | D2-T2 | 2d |
| **D2-T6** | 多端指标看板 | 2 新指标 + 导出埋点 | T-C3 | 0.5d |
| **D3-T1** | 交付物包模板化（封面/违规聚合） | 2 套模板 + 视觉回归 | D1-T1 | 2d |
| **D3-T2** | 整改通知单 + 复查意见 | Word 模板 + SDK 方法 | T-B6 | 2d |
| **D3-T3** | 客户成功 SOP + review_projects 表 | 流程文档 + DB 表 + 端到端跑通 | T-B6 | 2d |
| **D3-T4** | 交付物版本化 + SDK 兼容矩阵 | manifest schema_version + VersionMismatchError | T-C6 | 1d |
| **D4-T1** | 定价与 SLA 文档 | 免费/专业/企业三档 + 法务预检 | — | 1d |
| **D4-T2** | License 模块 + 在线/离线校验 | RSA 签名 + 5 单测 + 功能开关 | D1/D2/D3 | 3d |
| **D4-T3** | 用量计费 + 支付集成 | billing_cycles 表 + Stripe + 微信支付 + 14 天试用 | T-C2 | 4d |
| **D4-T4** | 首个付费信号验收 | 内测 2 笔 + License 发放 + 证据链 | D4-T2 + D4-T3 | 1d |

**合计 19 个子任务 / 预计 31.5 工作日 / 核心里程碑 4 个**
