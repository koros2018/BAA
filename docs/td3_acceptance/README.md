# D1-T3 验收证据链：首批地标导入（上海 / 广东）

日期：2026-10-26 · 分支：main · D1-T3

---

## 1. Roadmap DoD 回顾

> 选用地标：**上海地标**和**广东地标**——覆盖疏散/防火间距典型差异。
> 仅差异条文入 spec_data（复用国标条文不改，地标只存 diff clauses）。
> StandardSet 加载时做 **国标为底 + 地标覆盖** 合并（同一 clause_id 地标优先级高）。
> 证据链：用同一张图纸跑 `CN-National` vs `CN-Shanghai`，输出 diff JSON（哪些 finding 消失 / 新增 / 阈值变更）。

---

## 2. 改动清单（3 修改 + 2 新增）

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/baa_engine/standards.py` | 修改 | 新增 ScaleContext.create 深拷贝 scale_overrides + 注册 CN-Shanghai-v1 / CN-Guangdong-v1 |
| `src/tests/test_standard_set.py` | 修改 | 内置集数量断言 2 → 4（加上海+广东） |
| `src/tests/test_landmark_scale_overrides.py` | **新增** | 8 单测：地标注册/深拷贝/三级兜底/同图双跑 diff JSON |
| `docs/td3_acceptance/README.md` | **新增** | 本文件 |

**零 SpecRepository 改动**——地标阈值差异全部落在 `StandardSet.scale_overrides`，复用国标 clause 不改。

---

## 3. 已验证地标差异（scale_overrides 数字来源）

| StandardSet | clause_id | 国标值 civil | 地标值 civil | 来源 |
|---|---|---|---|---|
| CN-Shanghai | GB50016-5.5.18-2（走道净宽） | 1.1m | **1.2m** | DGJ08-20-2018 住宅 5.3.1 |
| CN-Shanghai | GB50016-7.1.1（消防车道宽度） | 4.0m | **4.5m** | DG/TJ 08-2408-2022 综合体消防 |
| CN-Shanghai | GB50016-5.5.18（楼梯净宽） | 1.2m | **1.3m** | 上海人员密集场所疏散要点 |
| CN-Guangdong | GB50016-5.5.18-2（走道净宽） | 1.1m | **3.0m** | 广东省公安厅 2014 商业主通道 |
| CN-Guangdong | GB50016-5.5.17（疏散距离） | 30m | **25m** | 广东商业消防审查要点 |
| CN-Guangdong | GB50016-5.5.18-3（疏散门净宽） | 0.9m | **1.0m** | DBJ15 系列地标加严 |

**保守原则**：仅 6 条差异，不确定的不填；只存阈值数字不存地标原文（版权风险）。

---

## 4. 三级兜底完整链路验证

admin_routes.py Step 3 对每个原子函数的阈值判定：

```
┌─ tier 1 ──────────────────────────────────┐
│  ScaleContext.get_override(clause_id, bt)  │  ← D1-T3 地标阈值覆盖
│  (StandardSet.scale_overrides 深拷贝)      │
├─ tier 2 ──────────────────────────────────┤
│  SpecRepository.get_threshold_safe(...)    │  ← D1-T2 国标 clause 阈值
├─ tier 3 ──────────────────────────────────┤
│  保留 AtomicFunction 构造时硬编码           │  ← 兜底（≈128 个无 clause 函数）
└───────────────────────────────────────────┘
```

同 clause_id，三套标准集阈值不同 → 审查结果 diff 可预测：

| clause_id | CN-National | CN-Shanghai | CN-Guangdong | 差异类型 |
|---|---|---|---|---|
| GB50016-5.5.18-2（走道） | 1.1m | **1.2m** | **3.0m** | 阈值变更 |
| GB50016-7.1.1（消防车道） | 4.0m | **4.5m** | 4.0m | 阈值变更 |
| GB50016-5.5.18（楼梯） | 1.2m | **1.3m** | 1.2m | 阈值变更 |
| GB50016-5.5.17（疏散距离） | 30m | 30m | **25m** | 阈值变更 |
| GB50016-5.5.18-3（疏散门） | 0.9m | 0.9m | **1.0m** | 阈值变更 |

**CN-Shanghai** 比国标严：走道+消防车道+楼梯全加严 → 同一张"走道 1.15m 的图纸"，CN-National 过（≥1.1）CN-Shanghai 不过（<1.2）。

**CN-Guangdong** 加严幅度最大：商业主通道 3.0m 是国标 1.1m 的 2.7 倍，会触发大量 finding 消失（不符合广东地标阈值的 finding 在广东地标集下会被判定为 PASS）。

---

## 5. 单测 + 全量回归

### 5.1 D1-T3 新单测（test_landmark_scale_overrides.py）

```
8 passed  (0 skipped)
```

覆盖：
- CN-Shanghai-v1 / CN-Guangdong-v1 注册到位 + scale_overrides 条数 + 值
- ScaleContext.create 深拷贝（实例内修改不污染 StandardSet 全局数据）
- 三级兜底 tier1 地标覆盖优先 / tier2 SpecRepository 兜底 / tier3 硬编码
- 同图双跑 diff JSON（CN-National vs CN-Shanghai → 3 条 clause 全变；CN-Guangdong 更显著）

### 5.2 全量回归

```
python -m pytest src/tests -q
2642 passed, 23 skipped, 14 deselected, 8 warnings in 72.46s
（基线 2634 → +8 / 0 退化）
```

### 5.3 冒烟：三级兜底链路

```
CN-National: clause=GB50016-5.5.18-2 → threshold=1.1m (来源: SpecRepository)
CN-Shanghai: clause=GB50016-5.5.18-2 → threshold=1.2m (来源: scale_overrides)
CN-Guangdong: clause=GB50016-5.5.18-2 → threshold=3.0m (来源: scale_overrides)
```

---

## 6. 设计决策记录

### 6.1 为什么不引入地标自身条款号？
roadmap 原 DoD 说"地标只存 diff clauses"，但实际地标体系碎片化严重（上海 DGJ08-20 是住宅、DG/TJ 08-2408 是综合体；广东 DBJ15 覆盖商业/公共建筑/地下等），每个地标规范覆盖不同场景。MVP 阶段：
- **直接用 GB clause_id 作 scale_overrides key**（"该国标条款在此地标下的覆盖值"）
- 不建立地标条款号体系——未来真正需要时再补映射表

### 6.2 为什么 building_type 只用 "civil"？
当前 `POST /tasks` Query 参数只有 `civil` / `industrial`。广东商业主通道 ≥3m 是"大中型商业建筑"特定要求，需要 `commercial` building_type 才能精准区分。**MVP 阶段暂不扩 Query 参数**，把地标差异值挂在 "civil" 上——表示"地标整体比国标严"，而非精准到商业场景。D1-T3 后续（或 D4-T2 License 驱动的精细化）再扩 building_type 选项。

### 6.3 为什么不引地标 standard 字符串？
`StandardSet.included_standards` 仍是 GB 系列——地标没有自己的 Clause 对象（SpecRepository 里不存地标 clause），只是用 `scale_overrides` 覆盖国标阈值。这样：
- 零 SpecRepository 改动
- 零 clause.standard 改动
- StandardSet.resolve_standard() / SpecRepository.get_threshold() / 原子函数的 func_id→standard 映射全不变

### 6.4 ScaleContext.create 为什么要深拷贝？
admin_routes.py Step 3 里会动态覆盖 `func.threshold`（虽然不修改 `scale_overrides` 自身），但 `ScaleContext.get_override` 返回的是 dict 内部值。如果 StandardSet.scale_overrides 被多个审查任务共享引用，实例内意外修改会污染后续审查。用 `copy.deepcopy` 隔离。

---

## 7. 已知局限（后续 D1-T3x / D4-T2 跟进）

| 局限 | 影响 | 跟进任务 |
|---|---|---|
| 广东 3.0m 主通道覆盖在 civil → 所有民用建筑走道判定都用 3m（含住宅） | 住宅审查结果过严 | 扩 building_type=commercial（或 D4-T2 License 驱动的场景化阈值） |
| 地标差异只有 6 条 clause（保守原则，不确定不填） | 审查 diff 覆盖面有限 | 逐步对标地标原文校准（每扩一批+1~3 条 scale_overrides） |
| 无地标自身条款号体系 | 报告里不能显示"依据上海 DGJ08-20-2018 5.3.1" | 建 clause_id 映射表（GB50016-5.5.18-2 → DGJ08-20-2018-5.3.1） |
| 无同图双跑 API 端点 | diff JSON 只能在单测 / 脚本里手动跑 | D1-T4 前端标准集面板 + 后端批量双跑接口 |

---

## 8. 后续依赖

| 任务 | 复用 |
|---|---|
| **D1-T4 前端标准集管理面板** | `GET /standards` 已暴露 4 个 code，前端下拉直接用 |
| **D1-T5 Prometheus 指标** | `baa_spec_standards_total{code}` 注册数 4；`baa_spec_scale_overrides_total` 累计 6 |
| **D4-T2 License 功能开关** | License 驱动 `ScaleContext.scale_overrides` 是否生效（免费版不可用地标阈值覆盖） |
| **后续地标扩展（北京/深圳/江苏）** | 直接 `StandardSet.register(StandardSet(code="CN-Beijing-v1", scale_overrides={...}))` |
