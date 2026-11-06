# BAA 产品力评估（2026-11-06 · 基于 HEAD 1f6f245 实测）

> 口径：只采信仓库代码可复现的实测输出；推断部分显式标注。
> 本轮为**评估与取证**，不含代码改动。样本为 `data/drawings/real` 真实图纸 + 1 张 `data/files` 大图。
> 旧报告（`docs/baa-product-assessment-20261104.md`）保留不动，本文件不覆盖其结论。
>
> **状态（2026-11-06 复测）**：§2–§5 的实测数据基于 HEAD `1f6f245`，保留为原始基线，
> **已被 §8 的 11/06 复测（HEAD `6f85763`）取代**；最新数字与结论以 §8 为准。

---

## 1. 结论

### 1.1 旧评分在当前 HEAD 上不成立

| 指标 | 旧值（2026-11-04） | 当前 HEAD 实测 | 结论 |
|---|---|---|---|
| 规则可达性（并集/适用） | 62.6%（产品力口径）/ 40.8%（172/422） | **25 / 186 = 13.4%** | 不成立 |
| 规则可达性（占总规则） | 40.8% | **25 / 422 = 5.9%** | 不成立 |
| 综合评分 | 2.7 / 5 | **约 2.5 / 5（推断）** | 判定/Semantic 两维下调后的重算，其余八维未复测 |

不可复现的原因：全样本中"目标类型至少出现过一次"的规则只有 **173 条**，其中真正产出过 PASS/FAIL 的只有 **25 条**。旧值 172 条在结构上不可能由当前代码产出（除非把"规则命中过类型"计为"已判定"）。

### 1.2 三条真实短板

1. **128 条 EXIST 规则在真实图纸上结构性沉默（30.3%）。**
   目标类型存在的 28 条 EXIST 规则，作用域聚合结果全部为 `partial`、直接执行全部 `FAIL`；判定分支在 `partial` 且实体全局存在时直接 `continue`，既不产 finding 也不计入 `evaluated`。7 张图纸合计 EXIST findings = 0。
   代码：`src/api/review/review_routes.py` 第 682–689 行。

2. **判据层面：别名组造成跨类型误判。**
   `doorway` 与 `exit_door` 同属别名组 5，导致 DIM-113 把 277 个门洞当疏散门判，产生 21 条 finding（东莞通全部 37 条中的 57%）；`door` 有 `is_evacuation_door` 守卫，`doorway` 没有。
   代码：`src/baa_engine/atomic_functions.py` 第 442–466 行（提取守卫）、第 100–137 行（别名组）。

3. **识别层面：实体分类不稳定。**
   restroom.dxf 的 9,979 个实体中 **9,978 个被判为 window**（源：122,965 LINE + 10,892 ARC，全部同一图层）；东莞通 41.3% 实体是 `other`，34,748 图元的建筑图只识别出 window 10 / stair 3 / corridor 3。

---

## 2. 样本构成

> 本节表格为旧版基线（HEAD `1f6f245`），**已被 §8 的 11/06 复测取代**；保留用于新旧对比。

| 图纸 | 大小 | 图元 | 实体 | evaluated/applicable | 比例 | findings | 耗时 |
|---|---|---|---|---|---|---|---|
| 东莞通-建筑-外部参照（不打印） | 5.81 MB | 34,748 | 10,086 | 18 / 185 | 9.7% | 37 | 8.6 s |
| restroom | 38.08 MB | 142,854 | 9,979 | 2 / 24 | 8.3% | 1 | 64.1 s |
| villa-details | 3.00 MB | 10,190 | 8,615 | 15 / 145 | 10.3% | 35 | 10.9 s |
| multiple-stadion | 1.86 MB | 2,759 | 2,482 | 4 / 86 | 4.7% | 0 | 8.1 s |
| mosque-detail | 1.61 MB | 6,263 | 1,467 | 2 / 51 | 3.9% | 0 | 10.0 s |
| plans-of-a-two-family-house | 1.31 MB | 1,568 | 1,365 | 2 / 58 | 3.4% | 0 | 6.9 s |
| Demo - Multi-family block (Template F-1) | 0.21 MB | 68 | 68 | 0 / 33 | 0% | 0 | 0.2 s |
| 4.通风BS170826（暖通，跳过） | 0.04 MB | — | 9 | — | — | 0 | 0.0 s |
| baa-file-2319613b52cb（电气，跳过） | 48.87 MB | — | 48,844 | — | — | 0 | 18.8 s |
| **并集（7 张参与判定）** | | | | **25 / 186** | **13.4%** | **73** | |

规则总量 422（dim 124 / dist 34 / area 26 / count 30 / exist 128 / attr 23 / light 5 / evac 4 / access 16 / thermal 16 / structural 16），其中 `requires_global_context=True` 3 条。

---

## 3. 缺口构成

### 3.1 逐文件覆盖率

- 东莞通 18/185 = 9.7%；restroom 2/24 = 8.3%；villa 15/145 = 10.3%；stadion 4/86 = 4.7%；mosque 2/51 = 3.9%；plans 2/58 = 3.4%；Demo 0/33 = 0%。

### 3.2 全样本规则缺口

| 类别 | 条数 | 说明 |
|---|---|---|
| 目标类型全样本从未出现 | 249 / 422 | water_tank 13、detector 12、fire_pump 11、fire_detector 10、road/driveway 各 9、fire_lane 7、insulation 7… |
| EXIST 被作用域聚合吞掉 | 28（目标类型存在的全部） | `partial` + 全局存在 → `continue`，0 findings、0 evaluated |
| 本地适用但取不到判据值 | 132（东莞通 152 条本地适用） | DIM-001 对 stair 无 `width`；COUNT 类无 floor/fire_zone 语义 |
| 依赖门禁未通过 | 2 | DIM-073/074/075、COUNT-005、EVAC-002/003/004 的前置未 PASS |

### 3.3 实体识别缺口（东莞通）

| 类型 | 数量 | 占比 | 问题 |
|---|---|---|---|
| other | 4,164 | 41.3% | 几何兜底未归类 |
| door | 3,248 | 32.2% | 0 个标注 `is_evacuation_door` |
| wall | 1,482 | 14.7% | — |
| text | 620 | 6.1% | 规则未引用 |
| doorway | 277 | 2.7% | 被别名组当出口 |
| room | 127 | 1.3% | — |
| window / stair / corridor | 10 / 3 / 3 | <0.1% | 识别严重不足 |

---

## 4. findings 质量（73 条）

> 本节为旧版基线（HEAD `1f6f245`），**已被 §8.2 / §8.4 的 11/06 复测取代**（本轮 35 条）。

| 结构性问题 | 条数 | 证据 |
|---|---|---|
| DIM-113 判门洞 | 21 | 全部 `entity_type=doorway`，宽度 0.70–0.88 m；277 个门洞中 35 个 <0.9 m |
| 前室三条互斥条款重复/错目标 | 16 | 6 个实体：ANTECHAMBER_2083 被 AREA-002 + DIM-018 + DIM-019 同时判；DIM-019 还判 STAIR_988(7.99㎡)/3176(9.0)/7839(9.0) |
| DIM-021/022 无前置证据 | 25 | villa 13 扇门，12 扇同时被"首层外门≥1.1m"和"人员密集门≥1.4m"判；`floor=None`，全图仅 20/2772 门被标疏散门 |
| **合计结构性可疑** | **49 / 73 = 67%** | 另 6 条 EVAC-004（actual=0.0 判瓶颈）需人工复核（推断） |

**漏判侧**：东莞通 3,248 扇门中 0 扇被标疏散门 → DIM-113/021/022 对 `door` 判定 0/3248；EVAC 仅 15 次执行 / 127 个房间；multiple-stadion（325 楼梯、217 门）与 mosque（1,209 窗）各只判 4 条、2 条规则且 0 findings。

---

## 5. 下一批开发目标（按影响排序）

### T1 · EXIST 作用域口径修复（128 条规则失效）

- **问题**：`partial` 聚合被"实体全局存在就 continue"吞掉，EXIST 规则永不产出、永不计数。
- **证据**：28 条目标存在的 EXIST 全部 `agg=partial`、`exec=FAIL`；7 张图 EXIST findings 恒为 0。
- **验收**：7 张真实图上 EXIST `evaluated` ≥ 28/28；新增 finding 逐条列出且不得出现 critical；`pytest` ≥ 2902 passed。
- **工作量**：0.5–1 人日（已定口径：partial → low 区域提示）。

### T2 · doorway 退出疏散门判定（21 条高置信误报）

- **问题**：`door` 有 `is_evacuation_door` 守卫，`doorway` 没有，且经别名组 5 与 `exit_door` 混同。
- **证据**：DIM-113 的 21 条全部落在 `doorway`；277 个门洞中 35 个 <0.9 m。
- **验收**：东莞通 DIM-113 findings 21→0；显式疏散门在合成样本上仍命中 ≥3 条；其余图纸无新增高置信误报。
- **工作量**：0.5 人日。

### T3 · 前室类规则语义修正（16 条重复/错目标）

- **问题**：同一 `antechamber` 同时被 6㎡ / 10㎡ 互斥条款判；DIM-019 目标含 `staircase`，经别名组命中 `stair` 面积。
- **证据**：ANTECHAMBER_3274/6314/7087/9457 各 2 条；STAIR_988/3176/7839 各有 1 条。
- **验收**：每实体 findings ≤1 条（16→≤6）；DIM-019 不再命中 `stair`；面积 1.0–1.54㎡ 的前室先由房间重建，重建不出则标 `insufficient_evidence`。
- **工作量**：1–1.5 人日。

### T4 · DIM-021/022 前置条件（25 条无证据误报）

- **问题**："首层疏散外门"与"人员密集场所疏散门"两条互斥条款对同一批门无条件成对判定。
- **证据**：villa 13 扇门 25 条，`floor` 全为 None；20/2772 门被标疏散门。
- **验收**：无 `floor=F1` / `occupancy` 证据时 25→0；首层外门合成样本（1.0 m）仍报 1 条。
- **工作量**：1 人日。

### T5 · 分类坍缩复核（restroom 99.9% 判窗）

- **问题**：单图层图纸几何分类坍缩；`other` 占比过高。
- **证据**：restroom 9,978/9,979 实体为 window（122,965 LINE 单图层）；东莞通 other 41.3%。
- **验收**：restroom window 占比 ≤30%（**已撤回，见 §7**）；东莞通 other ≤35%、stair ≥6（人工核对图面）且 corridor 有产出；`pytest` 全绿。
- **工作量**：1.5–2 人日，风险最高（动 classify 主路径）。

---

## 6. 复现方式

```powershell
# 单张图纸（生产等价判定：逐实体本地函数 + EXIST 作用域聚合）
python scripts/fp_rate_audit.py "data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf"

# 全量 real 目录（DXF + data/files 下 DWG）
python scripts/fp_rate_audit.py
```

本轮测量使用的临时脚本（**未入库**，位于 `C:\Users\26988\AppData\Local\Temp\`）：
`baa_eval_measure.py`（9 张图逐文件 coverage/findings）、`baa_diag.py`（未判定原因分类）、
`baa_diag2.py`（finding 明细）、`baa_diag3/4/5.py`（实体属性面、别名越类、EXIST 聚合诊断）、
原始输出 `baa_eval_out.json`。

关键判定口径（与 `scripts/fp_rate_audit.py` 一致）：
`applicable` = `matches()`（含别名归并）命中任一实体；`evaluated` = 实际产出 PASS/FAIL（PASS 也计入）。

---

## 7. T5 收尾：restroom 样本适配性缺陷（2026-11-06）

**结论：restroom 不是可审查 CAD，`window ≤30%` + `other ≤35%` 这对指标撤回，不参与验收。**

- **头信息缺失**：DXF 头部无 `$INSUNITS`、无 `$MEASUREMENT`、无 `$EXTMIN/$EXTMAX`，无法通过标准字段确定单位。
- **尺度不符 mm 制**：按 mm 解释时图形范围约 x −736~866、y −60~509；122,965 条 LINE 的长度值集中在
  0.013（21,062 条）、0.065（16,592）、0.056（8,287）、0.016（7,550）等，Top20 长度值合计 91,974 条
  （74.8%）全部 ≤1.376；ARC 半径中位数 0.036、p90 0.205、最大 45.6。全部阈值按 mm 设计
  （`<500mm → other`、`500–2000 → door`、`≥2000 → wall`），在该尺度下没有任何一段能过门/墙门槛。
- **来源判定**：图层名 `01 - DWGFREE.com`、142,853/142,854 图元集中在单一图层，叠加 3,005 ELLIPSE、
  218 SOLID、111 MTEXT 等页面转换特征，判断为 DWGFREE 从 PDF/位图转换出的**描线矢量化产物**，
  微线段是描线噪声而非建筑构件。
- **直接误判链路（已修）**：长表子串规则 `"C": "window"` 命中图层名里的 `COM`，导致 9,978 个
  实体全部判窗；已将其移入短表全词匹配（commit `0cc84a8`）。修复后 window 归零，但 99.9% 图元
  成为 `unknown` 未成实体——这是数据不可用的真实结果，不是可通过调阈值改善的分类问题。
- **验收处理**：撤回 restroom 的 `window ≤30%` 与 `other ≤35%` 双指标；9 图统计中仍需报告其
  实体数坍缩（9,979 → 86），但不再以此图判定分类质量。

**待办（下一轮，不在本轮实现）**：解析阶段应识别"无单位信息 + 尺度异常"的图纸（如
无 `$INSUNITS/$MEASUREMENT` 且长度/范围分布明显偏离 mm 制），输出"非可审查 CAD"提示并
停止语义分类，而不是照常分类后输出误导性结论。

---

## 8. 11/06 复测（HEAD `6f85763`）：unknown 保留 + window 误判修复后的整份重算

> 本节为重算结果，**取代 §2–§5 的旧实测**；旧数据保留在原文并已标注。样本、脚本、
> coverage 字段算法与旧版一致，仅分类实现与规则修复进度不同。

### 8.0 口径与改动说明

**判定口径不变**：同 9 张样本、同 `scripts/fp_rate_audit.py`、同 coverage 字段算法——
`applicable` = `matches()`（含别名归并）命中任一实体；`evaluated` = 实际产出 PASS/FAIL
（PASS 亦计入）；规则总量 422。

**三档对照**：

| 档位 | HEAD | 说明 |
|---|---|---|
| 旧版 | `1f6f245` | §2–§5 原始基线 |
| 上轮基线 | `f4305ed` | T1–T4 完成、T5 未修；本轮用等价分类配置（长表含短词 + 旧短表）复算 |
| 本轮 | `6f85763` | window 误判修复 + unknown 保留 |

**本轮代码改动（commit `6f85763`）**：

- `classify.py`：`unknown` 分支不再 `continue` 丢弃，改为收集为 `unclassified` 实体
  （`UNCLASSIFIED_00001…`，轻量 dict：id/type/bbox/layer/confidence/dxf_type），
  只写独立集合，**不进入** `entities`。
- `main.py`：每次分析重置并输出 `semantic["unclassified_entities"]`；在
  `classification_stats` 增加 `unclassified_layer_top`（Top 20 图层及计数）。
- `fp_rate_audit.py`：报告新增 `unclassified_count`、`accounted_entity_count`、
  `unclassified_layer_top`；`entity_count` 仍为分类实体数（`len(entities)`），判定逻辑 0 改动。

**隔离设计**：`unclassified` 与 `entities` 是物理分离的两个集合。规则侧所有入口
（`AtomicFunction.matches`、`FuncRegistry.execute_chained`、`build_scopes`、
`aggregate_exist_in_scopes`、`WidthContext`）只消费 `entities`，因此不需要任何过滤守卫，
也不可能进入规则匹配、适用面分母或 findings。

### 8.1 覆盖率新旧对比（两种口径）

| 口径 | 旧版 `1f6f245` | 上轮基线 `f4305ed` | 本轮 `6f85763` | 本轮 vs 上轮 |
|---|---|---|---|---|
| 适用面可达（并集 evaluated/applicable） | 25 / 186 = 13.4% | 40 / 178 = 22.5% | **43 / 181 = 23.8%** | 分子 +3 / 分母 +3（+1.3pp） |
| 全规则：适用覆盖（applicable / 422） | 186 / 422 = 44.1% | 178 / 422 = 42.2% | **181 / 422 = 42.9%** | +3（+0.7pp） |
| 全规则：判定覆盖（evaluated / 422） | 25 / 422 = 5.9% | 40 / 422 = 9.5% | **43 / 422 = 10.2%** | +3（+0.7pp） |

### 8.2 逐图新旧对比

| 图纸 | entities 旧→上轮→本轮 | unclassified（本轮） | evaluated 旧→上轮→本轮 | applicable 旧→上轮→本轮 | findings 旧→上轮→本轮 | severity（本轮） |
|---|---|---|---|---|---|---|
| 东莞通-建筑-外部参照 | 10,086 → 10,086 → 10,086 | 0 | 18 → 37 → 37 | 185 → 177 → 177 | 37 → 20 → 20 | low 20 |
| restroom | 9,979 → 9,979 → **86** | **9,914** | 2 → 2 → **0** | 24 → 23 → **32** | 1 → 1 → **0** | — |
| villa-details | 8,615 → 8,615 → 8,608 | 966 | 15 → 12 → 15 | 145 → 132 → 137 | 35 → 11 → 14 | critical 10 / low 4 |
| multiple-stadion | 2,482 → 2,482 → 2,208 | 366 | 4 → 4 → 2 | 86 → 80 → 58 | 0 → 0 → 0 | — |
| mosque-detail | 1,467 → 1,467 → **86** | **6,119** | 2 → 2 → 2 | 51 → 47 → 47 | 0 → 0 → **1** | low 1 |
| plans-of-a-two-family-house | 1,365 → 1,365 → 997 | 512 | 2 → 2 → 1 | 58 → 54 → 32 | 0 → 0 → 0 | — |
| Demo - Multi-family block | 68 → 68 → 68 | 0 | 0 → 0 → 0 | 33 → 29 → 29 | 0 → 0 → 0 | — |
| 4.通风BS170826（暖通，跳过） | 9 → 9 → 9 | 0 | 0 → 0 → 0 | 0 → 0 → 0 | 0 | — |
| baa-file-2319613b52cb（电气，跳过） | 48,844（图元） | 0（审计跳过） | 0 | 0 | 0 | — |
| **并集（7 张参与判定）** | | | **25 → 40 → 43** | **186 → 178 → 181** | **73 → 32 → 35** | critical 10 / low 25 |

说明：

- 旧版未逐图记录 severity，故旧版 severity 记为“—”；本轮 35 条 = critical 10 + low 25。
- 旧版 findings 73 = 东莞通 37 + restroom 1 + villa 35；本轮 35 = 东莞通 20 + villa 14 + mosque 1。
- `baa-file` 为电气图，审计按既有规则跳过语义判定，`48,844` 是图元数而非实体数。

**逐图比例（evaluated/applicable）**：东莞通 9.7% → 20.9%；restroom 8.3% → 0.0%；
villa 10.3% → 10.9%；stadion 4.7% → 3.4%；mosque 3.9% → 4.3%；plans 3.4% → 3.1%；
Demo 0%。

### 8.3 unknown 保留：9 图 unclassified 占比与图层 Top N

| 图纸 | 分类实体 | unclassified | 已计账合计 | unclassified 占比 | Top 图层（计数） |
|---|---|---|---|---|---|
| 东莞通 | 10,086 | 0 | 10,086 | 0.0% | — |
| restroom | 86 | 9,914 | 10,000 | **99.1%** | `01 - DWGFREE.com` 9,914 |
| villa-details | 8,608 | 966 | 9,574 | 10.1% | `Furniture` 758 / `v` 96 / `friz` 72 / `merdiven` 15 / `balustrade` 7 |
| multiple-stadion | 2,208 | 366 | 2,574 | 14.2% | `gradient` 195 / `ax` 89 / `fur` 68 / `section` 8 / `FURN` 4 |
| mosque-detail | 86 | 6,119 | 6,205 | **98.6%** | `A-ELEV-FNSH` 2,429 / `A-ELEV` 2,186 / `A-SECT-MCUT` 712 / `A-SECT-MBND` 518 / `A-GLAZ-PRHT` 183 |
| plans-of-a-two-family-house | 997 | 512 | 1,509 | 33.9% | `Structural - Bearing` 244 / `P-SANIT` 123 / `LINEAS01` 50 / `CASCO` 34 / `Ck Achurado Muros` 28 |
| Demo - Multi-family block | 68 | 0 | 68 | 0.0% | — |
| 4.通风BS170826 | 9 | 0 | 9 | 0.0% | — |
| baa-file（电气，审计跳过） | — | 95 / 10,000（直接 analyze） | — | 0.95% | `EQUIP` 29 / `WIRE` 18 / `0TITLE` 12 / `DQ1` 12 / `CAB` 6 |

说明：

- “已计账合计 = 分类实体 + unclassified”；小于原始图元数是因为分类阶段仍有退化图元过滤与
  10,000 采样上限（restroom 原始 142,854 图元、villa 10,190、mosque 6,263、stadion 2,759、
  plans 1,568）。
- 改前（T5 未修）的 unknown 静默丢弃量（等价配置复算）：villa 959、stadion 74、
  mosque 4,683、plans 133、restroom 0。本轮保留后分别为 966 / 366 / 6,119 / 512 / 9,914。
  **差值不是“新产生的未识别”，而是 window 误判修复后原本被错误归为 window 的图元按几何
  兜底落到 unknown**（restroom、mosque、stadion、plans 的主要来源）。
- `baa-file` 因审计跳过未纳入对照；其分类不受 window 修复影响，直接 analyze 的 unclassified
  为 95 个（0.95%）。
- `restroom` / `mosque` 的 unclassified 占比接近 100%，与其“单一图层/立面详图”样本属性一致，
  属于数据侧信号，不是分类质量回升。

### 8.4 规则侧不变性证明（unclassified 保留单独一项）

在“仅加入 unclassified 保留、其余代码完全相同”的前后快照上逐条比对，9 张图结果：

- `entity_types`：逐图完全相等（`entities` 列表本身未变）。
- `applicable_func_ids` / `evaluated_func_ids`：逐图集合完全相等。
- `findings`：逐条（`func_id` + `entity_id` + `severity` + `actual` + `threshold` + `source`）
  完全相等；并集 `evaluated/applicable = 43/181` 前后一致，findings 35 条前后一致。
- 并集 applicable 178→181、evaluated 40→43 的变化**不属于本项改动**，而是 T5 分类修复
  （见 8.5 的等价配置对照）。

结论：unknown 保留对任何既有规则的 evaluated/applicable/findings **零影响**；它只增加可计数的
`unclassified` 集合与图层质量信号。

### 8.5 关键问题：实体基数变化对覆盖率的影响——真实提升 vs 分母缩水

**实体基数变化（上轮基线 → 本轮，仅 T5 分类修复）**：

| 图纸 | 分类实体变化 | 说明 |
|---|---|---|
| restroom | 9,979 → 86（−9,893） | 9,978 个误判 window 归零 |
| mosque-detail | 1,467 → 86（−1,381） | window 1,209 → 3，other 183 → 0 |
| plans | 1,365 → 997（−368） | window 507 → 0 |
| multiple-stadion | 2,482 → 2,208（−274） | window 16 → 0 |
| villa-details | 8,615 → 8,608（−7） | window 148 → 130，wall +6，accessible_toilet +5 |

**分母侧（逐图）**：restroom、stadion、plans **各退出 22 条**窗类规则，且退出集合完全相同：

```
AREA-011 AREA-013 AREA-017 ATTR-003 ATTR-013 ATTR-017 DIM-005 DIM-008 DIM-010
DIM-032 DIM-087 DIM-099 DIM-110 DIM-114 DIST-004 EXIST-081 THERM-004 THERM-006
THERM-010 THERM-012 THERM-013 THERM-016
```

这 22 条规则此前只在“假窗实体”上适用；误判修复后从逐图适用面退出，是应然结果。
restroom 同时新进入 31 条（对真实保留的 `other` 实体适用，如 ATTR/DIM/COUNT/STR/THERM 子集），
净 `applicable` 23→32；stadion / plans 无新进入，净 −22。

**并集侧**：这 22 条规则**没有从并集分母消失**——villa 仍有 130 个真实窗、东莞通仍有 10 个窗，
它们继续在这些图纸上适用。因此并集 `applicable` 没有缩水，反而 178→181。

**分子侧（逐图）**：窗类修复同时带走对应的 evaluated：

| 图纸 | evaluated 退出 | evaluated 进入 | 净 |
|---|---|---|---|
| restroom | DIM-008、EXIST-081 | — | −2 |
| multiple-stadion | DIM-008、EXIST-081 | — | −2 |
| plans | DIM-008、EXIST-081 | DIM-009 | −1 |

这三张图自身覆盖率因此下降（restroom 8.7%→0.0%、stadion 5.0%→3.4%、plans 3.7%→3.1%），
是“误判产生的覆盖率被清除”的诚实代价，**不能算作提升**。由于 DIM-008 / EXIST-081 仍在
villa / 东莞通 上 evaluated，并集 evaluated 没有因此减少。

**真实提升（并集）**：并集 applicable 新进入 3 条、evaluated 新进入 3 条，全部来自 villa 新增的
5 个 `accessible_toilet`（短表 `WC` 规则）：

- applicable 进入：`ACCESS-008`、`ACCESS-020`、`EXIST-036`；
- evaluated 进入：`ACCESS-008`、`EXIST-036`、`EXIST-066`（`ACCESS-020` 判据不足，未产出 PASS/FAIL）；
- findings 变化均为 low：新增 ACCESS-008 3/17、EXIST-036 3/17、EXIST-066 3/17；
  EXIST-081 由 8/17 降为 7/17（未消失）。本轮 villa 的 low 共 4 条，critical 仍为 10 条
  （EVAC-002/003/004 的判定值与上轮一致，仅实体 ID 随重编号平移）。

**结论（直接回答）**：

1. **不是分母缩水造成的覆盖率提升**。并集分母 178→181 是 **+3**（新增可识别类型
   `accessible_toilet`），不是变小；22 条窗类规则的退出只发生在逐图，并集仍由真实窗实体覆盖。
2. **分子 +3 是真实增长**：三条规则真正产出 PASS/FAIL，且新增 findings 全为 low，无 critical。
3. **覆盖率 22.5%→23.8%（+1.3pp）的增量可全部归因于上述真实增长**；窗类误判清除在并集
   层面没有带来任何“假提升”，反而在 restroom/stadion/plans 逐图上表现为下降。
4. **与旧版 25/186=13.4% 相比的 +10.4pp 不能全部记在 T5 账上**：其中 +9.1pp
   （13.4%→22.5%）来自 T1–T4——主要增项是 T1 把 28 条被作用域聚合吞掉的 EXIST 变为
   可判定，T2/T3/T4 的误报清理同时移除了少量 evaluated；T5 只贡献 +1.3pp。

### 8.6 4 个 1.0–1.54㎡ 前室复测

| 实体 | 文本 | 实体 bbox 面积 | 旧区域面积来源 | 房间重建 | 面积规则是否判定 |
|---|---|---|---|---|---|
| ANTECHAMBER_3274 | 合用前室 | 0.105㎡ | 1.36㎡（最近 ROOM_7026，距 8.29m，未包含） | **失败**（中心不在任何 2–100㎡ room 内） | 否（`area_m2` 缺失） |
| ANTECHAMBER_6314 | 前室 | 0.184㎡ | 1.0㎡（最近有效 room ROOM_2182，距 5.84m，未包含） | **失败**（中心落在 ROOM_784 448㎡、polyline_room_10029 448㎡、10011 288㎡ 整层轮廓，均 >100㎡ 被 `valid_rooms` 排除） | 否 |
| ANTECHAMBER_7087 | 前室 | 0.184㎡ | 1.54㎡（最近 ROOM_634，距 4.42m，未包含） | **失败** | 否 |
| ANTECHAMBER_9457 | 前室 | 0.105㎡ | 1.36㎡（最近 ROOM_1240，距 1.30m，未包含） | **失败** | 否 |

结果：**4/4 房间重建失败，4/4 面积规则未恢复判定**（均无 findings，`area_m2=None`）。
图纸级 `AREA-002/018/019/021`、`DIM-018/019` 仍 applicable + evaluated（判定的是其他有面积
证据的前室），但这 4 个 ID 不再被判——符合“不能重建则维持静默”的预期，且旧版的
1.0–1.54㎡ 结论确认为“最近房间面积错配”，不是真实前室面积。

### 8.7 验证（测试与性能）

- **全量 pytest**：`2943 passed, 28 skipped, 14 deselected`（两次运行：148.09s / 150.68s），
  与基线完全一致。
- **语义分析性能**（`scripts/benchmark_semantic_analyze.py`，48.9MB / 48,844 图元，5 轮中位数）：
  - 改动前（暂存本轮 3 文件后复测）：**0.963s**
  - 本轮：**0.972s**
  - 两者均 `< 1.0s`；+0.9% 属主机噪声（两者都在 run 5 出现 ~1.55s 离群）。首轮 5 次曾出现
    中位数 1.011s（单次 1.593s 离群），复跑回到 0.972s，未复现。
- **复现脚本**（临时，未入库）：`baa_t5_snapshot.py`（9 图快照 + 等价旧配置复算）、
  `baa_t5_diff.py`（规则侧逐条 diff）、`baa_t5_covdiff.py`（coverage 集合差分）、
  `baa_t5_ante.py`（4 前室），输出 `baa_t5_before/after2/pret5.json`，均位于
  `C:\Users\26988\AppData\Local\Temp\`。

## 9. 11/06 覆盖率口径修正：unsupported_2d 标记 + 双口径（HEAD `c30bfa0` 之后）

> 本节只加**元数据标记**与**报告口径**，不改任何判据：标记后 9 张图的
> `evaluated` / `applicable` / `findings` 逐条完全一致（见 §9.4 证明）。

### 9.1 分子分母必须同集合：`evaluated ⊄ applicable`

历史口径 `43 / 181 = 23.8%` 的分子里混入了两条**全局上下文规则**
`EXIST-083`、`EXIST-093`：它们产出判定结果，但 `requires_global_context=True`
使它们不进入 `applicable` 集合。分子含分母外元素 → 覆盖率被虚增。

严格口径要求 `evaluated ∩ applicable`：

| 口径 | 分子 | 分母 | 比例 |
|---|---|---|---|
| 历史（虚增，含集合外 2 条） | 44 | 183 | 24.0% |
| **严格（分子分母同集合）** | **42** | **183** | **23.0%** |

> 与 1.6 诊断表 `41 / 181 = 22.7%` 的差额来自 **② villa 块语义修复**：
> 该次提交新增 `ACCESS-005`（evaluated）与 `DIM-107`（applicable），
> 因此当前 HEAD 的并集基线是 `183 / 44`，不是诊断所用的 `181 / 43`
> （诊断数据源 `baa_sheet_accept.json` 生成于 ① 验收时，早于 ②）。

### 9.2 82 条 `unsupported_2d` 标记（按真实归因）

标记字段：`AtomicFunction.unsupported_2d: bool`、`unsupported_reason: str`，
映射表 `src/baa_engine/atomic/__init__.py::UNSUPPORTED_2D_REASONS`。
**规则照常执行、照常计入分子**；标记只用于报告侧给出「可判定口径」分母。

| 归因标签 | 条数 | 规则 |
|---|---|---|
| semantic_gap（实体在但语义不足以判定） | 12 | AREA-004/005/006/011/013/016/017/022、DIM-005/010/021/022 |
| non_geometric（体积/时间/温度/人流率/风速） | 11 | AREA-020、COUNT-004、DIM-028/029/047/057/061/062/079/109/111 |
| product_spec（防火等级/耐火极限/设备参数） | 11 | ATTR-004/005/006/007/010/013/014/016/017/018/019 |
| illuminance（照度 lx） | 9 | LIGHT-002/003/004/005/007/008/009/010/011 |
| semantic_unmapped（2D 无图层/块约定） | 8 | ACCESS-012/019/020、DIM-032/102/110/114/115 |
| thermal（传热/保温/遮阳/气密） | 8 | THERM-001/003/004/006/007/010/012/016 |
| implementation_gate（执行门禁不一致，本轮不动） | 6 | EXIST-033/034/035/054/062/095 |
| site_or_path（场地/室外设施/无障碍路线） | 6 | DIST-014/015/017/018/019/020 |
| structural（荷载/配筋/强度） | 6 | STR-001/002/003/006/007/014 |
| mep_data（探测器/消防电气设备） | 2 | COUNT-027/028 |
| prereq_unsupported（前置规则不可判定） | 2 | DIM-073/075 |
| path_topology（需疏散路径网络） | 1 | DIST-001 |
| **合计** | **82** | C 桶 67 + 语义 12 + 依赖 2 + 路径 1 |

> 与 1.6 表的差异：**族内条数完全一致**（DIM 14 / ATTR 11 / ACCESS 3 / THERM 8 /
> LIGHT 9 / COUNT 3 / DIST 6 / EXIST 6 / STR 6 / AREA 1）。C 桶的具体成员按
> 统一判据重选：规则所需判据量在 2D 图纸中**无载体**（非几何量、产品参数、
> 场地信息），或所需语义在 2D 中**无图层/块约定**（救援窗、自然排烟口、前室形式）。
> 因此 `DIM-032/102/110/114/115` 归入 `semantic_unmapped`——它们不是补提取分支
> 能解决，需要图纸侧语义约定；`STR-010/011/015`（墙厚/板厚）、`DIM-013/015`
> 等可在剖面/标注中取证，留在 B 桶待提取；`THERM-013`（「有/无」）可由文本
> 判存在性，留在 A 桶。若对某个成员归属有异议，改一行映射即可重新归组。

### 9.3 双口径结果（并集，5 张参与判定图纸）

| 口径 | 分母构成 | 分子 | 比例 | 含义 / 适用 |
|---|---|---|---|---|
| 全规则口径 | 183（含全部 unsupported） | 42 | **23.0%** | 对外披露、跨版本可比：分母不因规则能力变化而缩放 |
| 可判定口径 | 101（183 − 82） | 42 | **41.6%** | 内部研发看板：衡量「本可判定的规则实际判了多少」 |

> 按 1.6 表述「分母 114」换算：那对应 `181 − 67`（只剔除 C 桶）。
> 当前基线下为 `183 − 67 = 116`，比例 `42 / 116 = 36.2%`。
> 该口径与「打 82 条标记」不自洽（12+2+1 仍留在分母），故**仅作参考**，
> 正式「可判定口径」采用 101。建议产品看板展示全规则口径（23.0%），
> 研发周报展示可判定口径（41.6%），两者并列注明分母。

逐图（`ev/app` 与 `ev/judgeable`）：

| 图纸 | evaluated | applicable | 其中 unsupported | 可判定分母 | 全规则 | 可判定 |
|---|---|---|---|---|---|---|
| 东莞通-建筑 | 37 | 177 | 80 | 97 | 20.9% | 38.1% |
| villa-details | 17 | 140 | 69 | 71 | 12.1% | 23.9% |
| multiple-stadion | 2 | 58 | 20 | 38 | 3.4% | 5.3% |
| plans（two-family-house） | 1 | 32 | 14 | 18 | 3.1% | 5.6% |
| Demo Multi-family F-1 | 0 | 29 | 11 | 18 | 0.0% | 0.0% |
| restroom / mosque | — | — | — | — | 非平面，不进分母 | — |
| 4.通风 / baa-file-c157664de336 | — | — | — | — | 跳过，不进分母 | — |

### 9.4 标记后规则侧不变性证明

同一脚本、同一 HEAD、标记前后各跑一次 9 张图（`fp_rate_audit.run_review`），
逐图对比 `evaluated_rules` / `applicable_rules` / `evaluated_func_ids` /
`applicable_func_ids` / `findings`（func_id + entity_id + actual + severity）：

```
东莞通 37/177/20 · restroom 0/0/0 · villa 17/140/16 · stadion 2/58/0
mosque 0/0/0 · plans 1/32/0 · demo 0/29/0 · 4.通风 跳过 · baa-file 跳过
→ ALL IDENTICAL（无任何集合或 finding 差异）
```

### 9.5 复现

```powershell
python scripts/fp_rate_audit.py            # 打印全规则/严格/可判定三行覆盖率
python -m pytest src/tests/test_p21_unsupported_2d.py -q
```
