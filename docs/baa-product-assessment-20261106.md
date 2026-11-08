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

### 9.2 76 条 `unsupported_2d` 标记（按真实归因）

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
| site_or_path（场地/室外设施/无障碍路线） | 6 | DIST-014/015/017/018/019/020 |
| structural（荷载/配筋/强度） | 6 | STR-001/002/003/006/007/014 |
| mep_data（探测器/消防电气设备） | 2 | COUNT-027/028 |
| prereq_unsupported（前置规则不可判定） | 2 | DIM-073/075 |
| path_topology（需疏散路径网络） | 1 | DIST-001 |
| **合计** | **76** | C 桶 61 + 语义 12 + 依赖 2 + 路径 1 |

### 9.2.1 单列缺陷清单：6 条 `implementation_gate_defect`（不计入 unsupported）

这 6 条**判据本身可从 2D 图纸取得**，缺口在实现侧：`matches()` 因
subtype / 别名组命中而返回 `True`，进入作用域聚合后 `execute(None)` 拿到
空目标集合，被执行侧 `targets ∩ entity_types` 硬交集跳过。

| func_id | 缺陷说明 |
|---|---|
| EXIST-033 | 适用面命中但执行侧目标集合为空；缺 `drain` 实体，直接修会产假 FAIL |
| EXIST-034 | 适用面命中但执行侧目标集合为空；缺备用电源实体 |
| EXIST-035 | 适用面命中但执行侧目标集合为空；缺无障碍电梯语义 |
| EXIST-054 | 适用面命中但执行侧目标集合为空；疏散门/防火门门禁不一致 |
| EXIST-062 | 适用面命中但执行侧目标集合为空；缺 `fire_pump` 实体 |
| EXIST-095 | 适用面命中但执行侧目标集合为空；缺 `sump` 实体 |

**为什么不修**：直接补齐会走 `build_scopes → execute(None)`，而这些样本图
缺 `drain` / `sump` / `fire_pump` 实体，大概率产出假 FAIL（把「图纸没画」
误报成「违规」）。待语义（这些设施应在哪类图/哪个作用域取证）确定后再修。
本轮只登记缺陷、不动执行路径；**6 条仍留在可判定分母**。

> 与 1.6 表的差异：C 桶由 67 降为 61（`EXIST-*` 6 条移入 §9.2.1 缺陷清单），
> 其余族内条数不变（DIM 14 / ATTR 11 / ACCESS 3 / THERM 8 / LIGHT 9 /
> COUNT 3 / DIST 6 / STR 6 / AREA 1）。C 桶的具体成员按
> 统一判据重选：规则所需判据量在 2D 图纸中**无载体**（非几何量、产品参数、
> 场地信息），或所需语义在 2D 中**无图层/块约定**（救援窗、自然排烟口、前室形式）。
> 因此 `DIM-032/102/110/114/115` 归入 `semantic_unmapped`——它们不是补提取分支
> 能解决，需要图纸侧语义约定；`STR-010/011/015`（墙厚/板厚）、`DIM-013/015`
> 等可在剖面/标注中取证，留在 B 桶待提取；`THERM-013`（「有/无」）可由文本
> 判存在性，留在 A 桶。若对某个成员归属有异议，改一行映射即可重新归组。

### 9.3 双口径结果（并集，5 张参与判定图纸）

> **2026-11-06 快照，已被 §9.6（2026-11-08 P133 复测）取代**；保留以对照变化。

| 口径 | 分母构成 | 分子 | 比例 | 含义 / 适用 |
|---|---|---|---|---|
| 全规则口径 | 183（含全部 unsupported） | 42 | **23.0%** | 对外披露、跨版本可比：分母不因规则能力变化而缩放 |
| **可判定口径（正式）** | **107（183 − 76）** | **42** | **39.3%** | 内部研发看板：衡量「本可判定的规则实际判了多少」；6 条门禁缺陷仍计在分母 |
| ~~历史对照~~ | ~~101（183 − 82）~~ | 42 | ~~41.6%~~ | **已废止**：把 6 条实现缺陷误作 2D 无解剔除，虚增 2 个百分点 |

> 39.3% 与已废止的 41.6% 差 2.3 个百分点，全来自把 6 条门禁缺陷放回分母：
> 它们是实现缺陷、不是 2D 图纸缺判据，若剔除会让可判定率虚高。
> 建议产品看板展示全规则口径（23.0%），研发周报展示可判定口径（39.3%），
> 两者并列注明分母。

逐图（`ev/app` 与 `ev/judgeable`）：

| 图纸 | evaluated | applicable | 其中 unsupported | 门禁缺陷 | 可判定分母 | 全规则 | 可判定 |
|---|---|---|---|---|---|---|---|
| 东莞通-建筑 | 37 | 177 | 74 | 6 | 103 | 20.9% | 35.9% |
| villa-details | 17 | 140 | 65 | 4 | 75 | 12.1% | 22.7% |
| multiple-stadion | 2 | 58 | 20 | 0 | 38 | 3.4% | 5.3% |
| plans（two-family-house） | 1 | 32 | 14 | 0 | 18 | 3.1% | 5.6% |
| Demo Multi-family F-1 | 0 | 29 | 11 | 0 | 18 | 0.0% | 0.0% |
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

### 9.6 P133 实现门禁：EVAC-002 / EVAC-003（2026-11-08 复测）

**性质：承认能力缺失，不是修复缺陷。** 这两条规则在真实路径几何就绪前
不具备判定能力，处理为「实现门禁」而非「判定失败」。

#### 9.6.1 诊断结论（只读实测，东莞通 + villa）

- `relations.py` 产出的 `distance` 是 **bbox 轴向间隙**，单位 mm：
  相邻 `dist=sqrt(dx²+dy²)`（[relations.py:177](../src/baa_engine/semantic_analyzer/relations.py) 计算、184 赋值），
  Phase3 `connects_to`（374/398 计算、379/403 赋值），Phase5 host_wall 恒 `0.0`。
- `evacuation.py` 把各边距离直接累加（[evacuation.py:274](../src/baa_engine/semantic_analyzer/evacuation.py)），
  `path_length=round(sum,2)`（282），**全程无 /1000**；唯一 mm→m 换算是 442 行的
  doorway 净宽，与路径长度无关。
- 因此 `path_length` 是「最短路径各边 bbox 间隙之和」，不是行走距离：
  东莞通 109 条 has_route 中位 **48.28mm**、最大 **148.28mm**；villa 的 `ROOM_3524`
  报 `40.64` 实为 `40.63902641154709`mm（room→door 单跳），`50.0` 实为
  `~50mm`（room→doorway 单跳）。
- 方向：比较层系统性高估 1000×（mm 数值 vs m 阈值），原 `>80` 守卫又把所有
  ≥8cm 的路径静默吞掉 → 双重错误：`(30,80]mm` 全是假阳性，`>80mm` 全是假阴性。
  东莞通「当前判为超距」61/109 → 按真实毫米换算后 **0/109**。

#### 9.6.2 处理方式

- 新增 `src/baa_engine/atomic/__init__.py::IMPLEMENTATION_GATES`，标记
  `EVAC-002`（path_length 非行走距离）/ `EVAC-003`（`exceeds_max_distance`
  由同一间隙和与米阈值比较得出）。标记字段 `AtomicFunction.implementation_gate`
  / `implementation_gate_reason`，与 `unsupported_2d`、`implementation_gate_defect`
  三者独立。
- `execute_chained` 跳过被标记规则：**不产出 PASS/FAIL**；但直接 `execute()`
  保留数值计算，供单测与诊断复算。
- 删除 `atomic_functions.py` 原 `if val > 80: return None` 守卫。该守卫以
  「路径计算 bug」掩盖了真正的单位/几何错配，删除后由门禁统一拦截。
- `path_length` **保留毫米原值、不做 /1000**（换算会让它看起来"像米"，造成
  二次误用）；改为显式标注语义：路由字段 `path_length_basis="bbox_gap_sum_mm"`，
  实体属性 `evacuation_path_length_basis` 同步透传。

#### 9.6.3 覆盖率三口径（并集，5 张参与判定图纸）

| 口径 | 分子 | 分母 | 比例 | 与 9.3 快照的差异 |
|---|---|---|---|---|
| 全规则口径 | **39** | **183** | **21.3%** | 分母不变（门禁仍计入全规则口径）；分子 −3（DIM-006 早于本提交，EVAC-002/003 本提交） |
| **可判定口径（正式）** | **39** | **105（183 − 76 − 2）** | **37.1%** | 分母 −2（门禁剔除）；分子 −2 |
| ~~历史对照~~ | — | — | — | 仍废止，见 9.3 |

> 2026-11-06 快照 `42/183 = 23.0%` 与 `42/107 = 39.3%` 已被本表取代。

#### 9.6.4 逐图标记前后对比（`evaluated / applicable / findings`）

| 图纸 | evaluated（前 → 后） | applicable | findings |
|---|---|---|---|
| 东莞通-建筑 | **37 → 35**（严格 35 → 33） | 177 → 177 | 20 → 20 |
| villa-details | 12 → 12 | 137 → 137 | 6 → 6 |
| multiple-stadion | 3 → 3 | 58 → 58 | 0 → 0 |
| plans（two-family-house） | 1 → 1 | 32 → 32 | 0 → 0 |
| Demo Multi-family F-1 | 1 → 1 | 51 → 51 | 0 → 0 |

- 唯一集合变化：东莞通 `evaluated_func_ids` 去掉 `EVAC-002`、`EVAC-003`；
  `applicable_func_ids` 逐图零变化。
- **findings 零新增、零消失**（20/6/0/0/0 前后一致）：这两条规则在东莞通本就
  被 EVAC-001 依赖门控挡住，标记只是去掉分子里的"伪可达"，不触碰任何结果。

> 修正（2026-11-08，P134 复测）：§9.6.4 的 Demo 行 `1 → 1 / 51 → 51` 与本文
> §8（§9 同口径）的 `0 / 29` 以及今日 `scripts/fp_rate_audit.py` 实测 `0 / 29`
> 不一致，**以 `0 / 29` 为准**；旧值保留不删，仅标注不一致。

### 9.7 P134 门洞去重口径定案：500mm + 区分方向（2026-11-08）

#### 9.7.1 口径判定：500mm 是设计意图，1000mm 是实现偏差

- 分歧来源：注释 [room.py](../src/baa_engine/semantic_analyzer/room.py) 写 "500mm grid"，
  实现 `key = (round(x, -3), round(y, -3))` 是 **1000mm** 分格；两者由同一提交
  `06a0b24`（2026-08-13，P105）引入，`test_pdf_pipeline.py` 原有 3 例门洞测试
  只断言数量/宽度，**从未断言去重口径**。
- 判定为 **500mm** 的硬约束：门洞宽度域 **700–2500mm**（`_DOORWAY_GAP_MIN_MM`）。
  去重容差必须小于 700mm，才在结构上不可能把两个同向真门洞并成一个；1000mm 越界。
- 实测差异（5 图全量 gap 复算）：500 与 1000 两种口径**仅 villa 一处不同**——
  水平间隙 `(12481,7200,w=1620)` 与竖间隙 `(12106,7200,h=1240)` 因 bbox 角点
  四舍五入同落 `(12000,7000)` 而被并成 1 条。二者方向不同，不可能是同一开洞，
  旧实现**错并**。东莞通（277 gap）及其余 3 图（0 gap）两口径完全一致。

#### 9.7.2 实现：同方向 + 中心距 500mm

- 新增 `_DOORWAY_DEDUP_TOL_MM = 500.0`；去重抽为 `_dedup_doorway_gaps`：
  同方向且间隙中心点欧氏距离 `<=500mm` 才合并，**不同方向永不合并**。
- 不用分格 key 的原因：分格是坐标量化，不是距离判据，跨格边界的同一开洞会漏合并
  （假阴性）；中心距直接对应「同一开洞在双线墙两面重复检出」，墙厚通常 100–300mm。

#### 9.7.3 测试（真正可裁决）

| 测试 | 断言 | 旧实现是否通过 |
|---|---|---|
| `test_doorway_dedup_same_direction_tolerance` | 双线墙 200mm → 1；平行墙 600mm → 2；中心距 500 合并 / 501 保留 | **否**（600mm 平行墙被旧 1000mm 分格并成 1） |
| `test_doorway_dedup_keeps_perpendicular_openings` | villa 实战坐标横竖两条 → 2 | **否**（旧实现并成 1） |

#### 9.7.4 逐图改前/改后（同脚本 `fp_rate_audit.py`，5 图）

| 图纸 | 实体数 | doorway | evaluated | applicable | findings（critical） |
|---|---|---|---|---|---|
| 东莞通-建筑 | 10086 → 10086 | 277 → 277 | 35 → 35 | 177 → 177 | 20 → 20（0） |
| villa-details | 8609 → **8610** | 26 → **27** | 12 → 12 | 137 → 137 | 6 → 6（0） |
| multiple-stadion | 2208 → 2208 | 0 → 0 | 3 → 3 | 58 → 58 | 0 → 0 |
| plans（two-family-house） | 997 → 997 | 0 → 0 | 1 → 1 | 32 → 32 | 0 → 0 |
| Demo Multi-family F-1 | 68 → 68 | 0 → 0 | 0 → 0 | 29 → 29 | 0 → 0 |

- **findings 零新增、零消失、零 critical**；覆盖率不变：
  全规则 **41/183 = 22.4%**，可判定 **39/105 = 37.1%**。
- villa 新增的那一条 doorway 逐条列出：`vertical bbox=(12106,7200,200,1240)`。
  它和保留下来的 `horizontal bbox=(12481,7200,1620,200)` 都是
  `_find_gaps_in_axis_v2` 的 **1500mm 聚类容差**把相邻但不同墙线上的墙段配对成
  「间隙」产生的。该聚类口径是独立缺陷（本轮不动），因此这条新增实体属于
  已知上游噪声，不是本次去重引入的新判定；它未触发任何 finding。

#### 9.7.5 验证

- pytest：**3046 passed / 28 skipped / 14 deselected**（基线 3044 + 新增 2）。

### 9.8 P135 room 面积被 bbox 越权覆盖的修复（2026-11-08）

#### 9.8.1 根因

`_correct_unclosed_room_area`（[main.py](../src/baa_engine/semantic_analyzer/main.py)）
的触发条件是 `point_count <= 3 or ratio < 0.5`。扫线法面遍历产出的 room
**从不写 `point_count`**（缺省 0），所以 `point_count <= 3` 恒真：所有扫线
room 一律被 bbox 面积覆盖，既不看 `closed`，也不看 ratio。L 形房间的 bbox
天然大于 polygon，面积因此被系统性放大。

#### 9.8.2 实测放大（改前 → 改后）

东莞通：48 间被校正，其中 **24 间 bbox 面积 == polygon 面积（无实质变化）**，
9 间实质放大：

| bbox (x, y, w, h) | 改前 bbox 面积 | 改后 polygon 面积 | ratio |
|---|---|---|---|
| (1299645, 197151, 7300, 37000) | 270.10 | 267.10 | 0.99 |
| (-66500, -36600, 7550, 36600) | 276.33 | 124.23 | 0.45 |
| (468145, 198862, 23460, 10939) | 256.63 | 96.28 | 0.38 |
| (526145, 215351, 2600, 7700) | 20.02 | 18.14 | 0.91 |
| (526145, 201151, 2900, 6400) | 18.56 | 16.96 | 0.91 |
| (11721, -12800, 2700, 5500) | 14.85 | 13.47 | 0.91 |
| (-4550, -36800, 5050, 4200) | 21.21 | 12.11 | 0.57 |
| (-2500, -35595, 5991, 5295) | 31.72 | 11.99 | 0.38 |
| (-1888, -1044, 4020, 2010) | 8.08 | 6.06 | 0.75 |

villa：11 间被校正，5 间实质放大（最大 3.2×）：

| bbox (x, y, w, h) | 改前 bbox 面积 | 改后 polygon 面积 | ratio |
|---|---|---|---|
| (6380, 52306, 25385, 23547) | 597.73 | 392.82 | 0.66 |
| (44533, 52082, 24408, 21101) | 515.03 | 354.34 | 0.69 |
| (3, 755, 26044, 15240) | 396.91 | 161.50 | 0.41 |
| (36641, 428, 34546, 12103) | 418.12 | 129.65 | 0.31 |
| (19305, 24474, 25033, 11929) | 298.61 | 116.76 | 0.39 |

#### 9.8.3 修复口径

- `closed=True`：跳过。已确认闭合，polygon 面积可信，bbox 只会高估。
- `point_count=0`：跳过。面遍历房间没有顶点计数，不能当作"未合龙"。
- 仍保留 `point_count` 为 1–3 或 `ratio < 0.5` 的 bbox 修正：东莞通改后
  仍有 **15 间** 未合龙矩形被校正（P131 能力不回退）。

#### 9.8.4 逐图改前/改后与验证

| 图纸 | evaluated | applicable | findings | 面积校正数 |
|---|---|---|---|---|
| 东莞通-建筑 | 35 → 35 | 177 → 177 | 20 → 20 | 48 → 15 |
| villa-details | 12 → 12 | 137 → 137 | 6 → 6 | 11 → 0 |
| multiple-stadion | 3 → 3 | 58 → 58 | 0 → 0 | 0 → 0 |
| plans（two-family-house） | 1 → 1 | 32 → 32 | 0 → 0 | 0 → 0 |
| Demo Multi-family F-1 | 0 → 0 | 29 → 29 | 0 → 0 | 0 → 0 |

- **findings 零新增、零消失、零 critical**；覆盖率口径不变：
  全规则 **41/183 = 22.4%**，可判定 **39/105 = 37.1%**。
- pytest：**3050 passed / 28 skipped / 14 deselected**（上一提交 3046 + 新增 4）。

### 9.9 P136 单段 ARC 不再判 room（ROOM_3524 残留路径，2026-11-08）

#### 9.9.1 根因

[classify.py](../src/baa_engine/semantic_analyzer/classify.py) 的 ARC 分支曾有
「`radius > 3000` 且跨度 > 90° → room」。**单段 ARC 不是闭合区域**，不构成房间；
5 图实测产生 7 个假房间：

| 图纸 | 假 room | radius (mm) | area_m2 |
|---|---|---|---|
| 东莞通 | ROOM_6412 | 4378.57 | 76.69 |
| villa | ROOM_226 | 3905.33 | 61.01 |
| villa | ROOM_2832 | 3905.33 | 94.89 |
| villa | ROOM_3214 | 6735.79 | 189.58 |
| villa | ROOM_3524 | 4059.96 | 65.93 |
| villa | ROOM_3759 | 3425.02 | 46.92 |
| villa | ROOM_1439 | 3905.33 | — |

这 7 个假 room 随后被赋予**楼梯/前室类子类型**（stair/staircase 等），成为 villa
唯一的「楼梯」实体来源，连带 23 条 stair/antechamber 规则产生**伪适用面**
（ACCESS-014/015、ATTR-010/018、COUNT-003/015/021/022、DIM-001/020/025/026/071/079/101、
EXIST-001/003/050/051/064/068/080、LIGHT-007）。

#### 9.9.2 修复

删除该分支：大半径 ARC 统一按弧形窗处理（与既有 `test_arc_large_radius_window`
口径一致）。新增 `test_arc_large_span_not_room`：radius 4378.57 + 跨度 180° → window。

#### 9.9.3 逐图改前/改后

| 图纸 | room | window | applicable | evaluated | findings |
|---|---|---|---|---|---|
| 东莞通-建筑 | 127 → **126** | 10 → **11** | 177 → 177 | 35 → 35 | 20 → 20 |
| villa-details | 14 → **8** | 136 → **140** | 137 → **114** | 12 → **10** | 6 → 6 |
| multiple-stadion | 0 → 0 | — | 58 → 58 | 3 → 3 | 0 → 0 |
| plans（two-family-house） | 0 → 0 | — | 32 → 32 | 1 → 1 | 0 → 0 |
| Demo Multi-family F-1 | 0 → 0 | — | 29 → 29 | 0 → 0 | 0 → 0 |

- villa 实体数 8610 → 8608：6 个假 room 改判 window，其中 2 条并入相邻窗
  （window 只 +4），故净 −2。
- villa `evaluated` 少 2 条：DIM-001、EVAC-001——两者此前都是在假 stair 房间上
  判定，属于**伪覆盖**的移除，不是能力退化。
- 并集：evaluated **41 → 40**（40/183 = **21.9%**），可判定 **39/105 → 38/105
  （36.2%）**；applicable 并集 183 不变（那 23 条在其它图纸仍适用）。
- **findings 零新增、零消失、零 critical**。
- pytest：**3051 passed / 28 skipped / 14 deselected**。

> 更正：§9.7.4 / §9.8.4 原写「全规则 39/183」，系转写错误；两次实测均为
> **41/183 = 22.4%**，已就地更正。

## 10. A 桶属性补齐结论（2026-11-06）

**结论：ATTR-001 / ATTR-003 / AREA-001 / COUNT-001 四条在 9 张样本图上
全部无合规取值**（补前 None、补后 None），净收益 **0**；覆盖率保持
**42/107 = 39.3%**（全规则 42/183 = 23.0%）。四条不产生任何新 finding。

### 10.1 ATTR-001 / ATTR-003：只有“防火门类型”证据，没有等级证据

| 图纸 | 门窗实体 | 等级证据 | 补前 → 补后 |
|---|---|---|---|
| 东莞通-建筑 | door 3248、doorway 277、window 10、rescue_window 3 | 256 条 `FM` 逐门 TEXT（距最近门 0~144mm）；8 条门编号 `HFM1220(6)`/`HFM0716(5)`/`HFM0820(6)`/`HHFM1520(6)`/`HHFM1020(6)`/`HM1020`/`HM1220`/`HHM1220`；`甲级证书号：A144018965` 为证书说明（距最近门 1389mm）；`（耐火极限≥` 文本截断、无值 | None → **None** |
| villa-details | door 2772、window 136 | 关键词文本 0；块名仅 `A$C57C31BFC`（wc/sanitary 洁具块）与 `okna-150`（窗，无等级）；ATTRIB 0 | None → **None** |
| multiple-stadion / plans / Demo | door 217 / 84 / 14 | 关键词文本、块名、ATTRIB 均为 0 | None → **None** |

判定：
- `FM` / `HFM` 只证明“是防火门”，不证明等级；把 `FM` 写成 1.0（丙级）就是
  按类型猜等级，已禁止。
- `甲级证书号` 是整份门窗表的证书说明，不是逐门等级标注；其最近实体是
  `WINDOW_143`（误分类窗），跨实体写 3.0 会制造假 PASS。
- `HFM/HHM` 编号不含甲/乙/丙，无法落等级。

例外与捕获：仅当编号**显式带等级字符**（`FM甲1220` / `FC乙1212`）时写
`fire_rating`——门按甲/乙/丙 = 3/2/1 级，窗按 = 1.5/1.0/0.5h；裸 `FM1220`
不写（[text_attributes.py](../src/baa_engine/semantic_analyzer/text_attributes.py)）。
图层名推断仅保留中文甲/乙/丙，删除裸 `A`/`B`/`C` 单字母
（[main.py](../src/baa_engine/semantic_analyzer/main.py)），避免 `A-WALL`/`B-DOOR`/
`C-COLUMN` 被误判为等级。

### 10.2 AREA-001：只对真实闭合区域落 bbox

- 条件：`closed=True` 或 `point_count>=3` 的空间区域；文字标签（TEXT/MTEXT）、
  LINE（start/end 点）、ARC（radius）一律 None。
- 落值：`area = width*height/1e6`（图纸单位 mm → ㎡），并写
  `area_source="bbox"`、`_area_source="bbox_floor_region"`。
- 为什么用 bbox 而非闭合轮廓：2D 解析对未合龙多边形只能给 bbox；bbox 对
  L 形/弧形区域会偏大，只适用于近似矩形的闭合区域。本图集没有该类实体。

样本验证（全部保持 None，无新增 finding）：

| 实体 | 实际几何 | bbox 面积 | 若落 bbox 的后果 |
|---|---|---|---|
| 东莞通 `FLOOR_2729` | TEXT「负一层地下室顶板结构降板」560×373.33mm | 0.209067㎡ | 新增 critical FAIL（<5） |
| 东莞通 `FLOOR_6405` | TEXT「上负一层」401.07×267.38mm | 0.107240㎡ | 新增 critical FAIL（<5） |
| villa `FLOOR_606` | ARC，半径 6980.95mm、弧角 157.8°~178.2° | 194.934693㎡ | 假 PASS（外接矩形） |
| villa 其余 10 个 floor | LINE，短边≈0 | 0.000000㎡ | 仍 None |

### 10.3 COUNT-001：无分区保持 None，禁止向 floor 摊派

- 作用域：仅 `fire_zone` / `fire_compartment`，且 bbox 面积 ≥25㎡（过滤文字/图例块）。
- 分区内找到 ≥1 个出口实体才写 `exit_count`；0 个不写 0（缺符号 ≠ 出口不足）。
- `floor` 标签/楼层线不是空间范围，任何情况下都不摊派全图出口数。

样本：5 张参与判定的图纸 `fire_zone` / `fire_compartment` 均为 **0**；
东莞通有 2 个 floor 标签与 1 个 `exit`，villa 有 11 个 floor 线元与
0 个 `exit`/`exit_door`（仅 20 个 `is_evacuation_door`，非分区出口）。
→ 全部 None；villa 11 个 floor 不产生任何 finding。

### 10.4 验收

- 9 张图 findings 对比：**ALL IDENTICAL**（东莞通 37/177/20、villa 17/140/16、
  stadion 2/58/0、plans 1/32/0、demo 0/29/0；restroom/mosque 0/0/0；其余跳过）。
- 全量 pytest：**3017 passed**（新增 text_attributes 6 例 + A 桶 AREA/COUNT 11 例）。
- 覆盖率：全规则 42/183 = 23.0%，可判定 **42/107 = 39.3%**，均不变。
- 提交：`fix(semantic)` 等级捕获与图层收口；`feat(area)` 闭合区域 bbox；
  `feat(count)` 分区出口聚合。

## 11. B 桶 · DIM 几何提取（2026-11-06）

### 11.1 净宽算法选型：空间用最小内切，门窗用符号自尺寸

在 villa 与东莞通各取 20 个门（15 LINE + 5 ARC）与 12 个闭合房间廓线实测：

| 场景 | (a) 墙线配对/开口间隙 | (b) 闭合轮廓栅格 EDT 最小内切 |
|---|---|---|
| 门洞 40 例 | **0/40 有值**（36 例「墙面在洞口未断开」=90%，4 例「窗口内无墙段」=10%） | 33/40 无闭合空间；7 例有值的误差 +184~+1586mm，仅 1 例 ≤100mm |
| 房间 24 廓线 | 20 可算，18 例 ≤30mm；2 例高估 +1350/+1915mm | 24/24 可算，21 例 ≤30mm，0 高估（3 例偏保守 −110/−127/−300mm） |

结论：
- **门窗洞口**：用符号自尺寸（LINE 扇线长 / ARC 弧半径），误差来自未扣门框（±50mm），
  不是几何算法误差。bbox 对 LINE 门 30/30 零误差，对 ARC 门 10/10 恰好 2×（直径）。
- **闭合空间**：用 (b) 栅格 EDT 最小内切宽；20mm 栅格，必须补零边框，否则数组边界
  不被当作背景、直径虚高一倍。(a) 只作交叉校验，不作为取值来源。
- **走道 / 楼梯**：无多边形/梯段几何，判「无法可靠提取」，见 §11.5。

### 11.2 第一批：ARC 门宽 2× 错值修复

- 根因：ARC 实体 bbox = 圆弧外接正方形（边长 = 2r），Step 1.6 取 bbox 长边当门宽；
  Step 1.5 半径分支虽先写 r，但策略 2 以 min(bbox) 覆盖回 2r。
- 修复：门宽权威取半径（`width = radius`，>3 视为 mm、≤3 视为米），写
  `width_basis="arc_radius"` / `_width_source="arc_radius"`；LINE 门扇线写 `width_basis="leaf"`。
- 改前/改后逐实体全量：`docs/benchmark/arc-door-width-fix-20261106.csv`（440 条）。

| 图纸 | ARC 门 | 改前 → 改后 | 其中恰为 2× |
|---|---|---|---|
| 东莞通 | 88 | 2× 或模数吸附值 → 半径 | 部分 |
| villa-details | 342 | 2× 或模数吸附值 → 半径 | 部分 |
| multiple-stadion | 10 | None → 0.5m | 0 |
| 合计 | **440** | **430 有值改动 + 10 由 None 落值** | **212** |

- findings：9 图**逐条完全一致**（东莞通 20、villa 16，其余 0），无新增 FAIL。
- evaluated：仅 stadion +1（`DIM-113` 由不可判定变为 PASS）；其余不变。
- 覆盖率：**42/107 = 39.3%** 不变。全量 pytest：**3020 passed**。

### 11.3 第二批：门窗符号尺寸标 approximate + ±50mm 不确定带

- LINE 门 `width = 扇线长`，ARC 门 `width = 半径`；`width_basis` ∈ `leaf` / `arc_radius`，
  置 `approximate=True`、`_width_uncertainty_m=0.05`。
- finding 新增 `approximate` / `width_basis` 字段（生产 `review_routes` 与审计脚本同口径）。
- 判定纪律：
  - 符号宽 <300mm 或 >3000mm → `_width_plausible=False`，不判定；
  - `|actual - threshold| <= 50mm` → **insufficient_evidence**，返回 None，不产 PASS/FAIL；
  - 带外才正常 PASS/FAIL，并在 finding 标 `approximate=true`。
- 9 图实测：东莞通 leaf 2353 / arc 92，villa leaf 464 / arc 381，stadion arc 10；
  窗类 ARC 2× 同步纠正（东莞通 4 个、villa 39 个）。
- findings 与 evaluated **零变化**（本图集无门窗宽度类 finding，故无 approximate 可见样本）；
  覆盖率 **42/107 = 39.3%** 不变。全量 pytest：**3024 passed**。
- 未能落地的 None 条件（如实记录）：
  - 「扇线与弧差 >60mm 或 >10%」需要同一门的扇线+弧配对；当前实体与图元 1:1，
    一个门实体只携带扇线或弧，二者不共存，无法交叉校验，未凭空构造配对。
  - 「双扇无逐扇线」需要双扇识别与逐扇线，当前无该结构，未实现。

### 11.4 房间净宽：目标类型不匹配，本批不实现

核查全部 DIMENSION 规则：target 含 `room` 的仅 `DIM-013`（unit=mm，实为净高/2.0m 口径，
`_extract_value` 无提取分支，恒为 None）与 `DIM-015`（DISTANCE，疏散距离，非净宽）；
`DIM-012`（走道净宽）target 仅 `corridor`；门窗净宽 target 为 `door/exit_door/exit/doorway`。
**没有任何原子函数消费 `room.clear_width`**。

现有 room 廓线口径：东莞通 `room` 127 个、villa 34 个（闭合廓线），`room.py` 已写
`clear_width = min(bbox_w, bbox_h)/1000`（bbox 短边）。若改用 (b) 最小内切，产物无规则消费，
findings/evaluated 均为 0 变化。按「不匹配就说明」处理：**本批不实现**，避免为无效规则
引入新几何路径与回归面。待未来新增房间净宽条款时，再以 (b) 接入。

### 11.5 阻塞项（写入依赖台账）

| 项目 | 阻塞原因 | 依赖 |
|---|---|---|
| 走道净宽（DIM-012） | 3 条 corridor 全部 `points=0`（无多边形），仅 bbox 短边 2.6m/2.4m | 走廊路径化/中线提取 |
| 楼梯净宽 / 踏步 | 仅有 CIRCLE（东莞通 3 个，φ2826.9 / 3000 / 3000mm），无梯段与踏步线；villa 0 个 | 楼梯构件识别（梯段/踏步/扶手） |
| 袋形走道长度 | 走廊无路径几何，无法算纵深远端长度 | 同「走廊路径化」 |
| 前室形式（开敞/封闭/防烟） | 4 个小面积前室房间重建全部失败 | 房间重建能力 |
| COUNT 15 条 | 无 `fire_zone` / `fire_compartment` 作用域可用 | 房间/分区识别 |

### 11.6 验收汇总

- 9 图 findings：第一批、第二批均为**逐条一致**（无新增 FAIL，无新增 critical）。
- 覆盖率：两批后仍为 **42/107 = 39.3%**（全规则 42/183 = 23.0%），分子增量 **0**。
- pytest：第一批 3020 passed；第二批 3024 passed（新增 3 例 ARC 语义 + 4 例不确定带）。
- 提交：`fix(semantic)` ARC 门宽；（第二批）`feat(rule)` 符号尺寸 approximate 与不确定带。

### 11.7 第三路：门扇端点法定位洞口——已否决（2026-11-06）

**假设**：门扇两端必然各贴洞口一侧（铰点端 + 洞口另一端），把两端投影到最近的**同向**
墙线即可定位洞口区间并求净宽，从而绕开「墙线必须在洞口断开」这一前提。

**样本**：东莞通 / villa 各 15 LINE 扇线 + 5 ARC 弧线，按 §11.1 同一选型规则等距取样
（原选型探针已删，实体 ID 与原批不完全相同）。真值 = 扇线长 / 弧半径。

| 图纸 | 墙线段 | LINE 成功（≤30mm） | ARC 成功 | 小计 |
|---|---|---|---|---|
| 东莞通-建筑-外部参照 | 4,337 | 1/15 | 0/5 | 1/20 |
| villa-details | 1,226 | 3/15 | 0/5 | 3/20 |
| **合计** | | **4/20** | **0/10** | **4/40 = 10%** |

误差分布（40 样本）：**≤30mm 4 条（10%）、30–100mm 0 条、>100mm 1 条**
（villa ARC DOOR_1753：定位 596.6mm vs 真值 940.5mm，−343.9mm）、未定位（None）35 条（87.5%）。
故 ≤100mm 口径同为 4/40。

扩展样本（每图 80 LINE + 20 ARC）：东莞通 19/89、villa 18/100，合计 **37/189 ≈ 19.6%**。

**失败模式（40 样本，35 个 None）**：

| 失败模式 | 条数 | 占比 |
|---|---|---|
| `endpoint_far_from_wall`（端点不贴墙） | 18 | 45% |
| `wall_direction_mismatch`（扇线与墙方向不一致） | 15 | 37.5% |
| `missing_endpoints`（实体无扇线端点） | 1 | 2.5% |
| `no_wall_segment_in_range`（投影脚附近无墙段） | 1 | 2.5% |
| `ambiguous_wall`（多候选洞口歧义） | 0 | 0% |
| 已定位但误差 >100mm | 1 | 2.5% |

**结构性结论（两条，无法靠调参绕开）**：

1. **90° 开启符号的自由端离墙恰约一个扇长**。东莞通型门扇一端为铰点、另一端为开启状态自由端，
   「另一端贴洞口另一侧」在这类符号上不成立；其表现就是 `wall_direction_mismatch(angle=90)`
   与 `endpoint_far_from_wall`（实测 514–48,100mm）。只有 villa 型关闭状态符号（扇线横跨洞口）
   命中时为零误差，但仅占 villa LINE 样本的 3/15。
2. **ARC 实体缺 `center`，由 bbox 反推圆心在部分实体上失效**。东莞通 DOOR_4493 的端点距最近墙线
   183,729mm（约 183m），即为 bbox ≠ 圆心±半径 时的反推失败，与容差无关。

**敏感性诊断（仅诊断，不作为过关依据）**：贴墙容差 500mm → 1500mm，40 样本 4/40 → **8/40 = 20%**，
扩展样本 37/189 → **67/189 ≈ 35.4%**，仍远低于 60% 门槛；剩余失败以方向不一致与无墙段为主。

**与另两路对照**：

| 方法 | 有值数 / 40 | 备注 |
|---|---|---|
| (a) 墙线配对 | **0** | 墙面在洞口未断开 |
| (b) 最小内切 | **7** | 门洞处无闭合空间，有值者误差 +184~+1586mm |
| (c) 门扇端点法（本路） | **4**（≤100mm 亦 4） | 见上表 |

**判定：不可行，不实现生产代码。** 依据是 10%（最宽松 35.4%）远低于 60% 门槛，
且两项失败原因是符号语义与上游实体缺字段，不是算法参数问题。

### 11.8 疏散门语义推断的离线精度验证——已否决（2026-11-06）

**背景**：门宽已可量（§11.2/11.3，符号尺寸零误差），但宽度类条款只对
`is_evacuation_door` 生效；东莞通 3248 门 **0 标注**、villa 2772 门仅 **20 标注**，
这是覆盖率卡住的直接原因。本轮验证“能否用图上证据自动推断疏散门”。

#### 11.8.0 前置发现：villa-details 是立面/大样图，不是平面图

这一点必须单列，因为它不是“语义推断方法不好”，而是**输入不成立**：

- 原始 112 条文字（58 TEXT + 54 MTEXT）内容为 `Facade 1-9`、`Facade E-A`、`Level 2` 与轴号
  （`1`–`9`、`А`/`Б`/`В`/`Г`），**没有一条平面标注**（无房间名、无门窗编号、无尺寸链）。
- 语义分析后 text 实体数 = **0**（文字未被分类实体化），exit / corridor / stair 实体均为 **0**。
- 34 个“房间”中仅 23 个有多边形，其轮廓来自立面图元；117 扇门落在这些多边形内。
- 2772 个“门”里 254 扇宽度 ≤0.2m，出现 w=0.05m 的檐口/线条误判，门/窗实为立面构件。

结论：**villa-details 被 R3 判为平面图是图幅误判**，其真实图幅为立面/大样，
后续由 R3 判据复核修正（见 §11.9）。

#### 11.8.1 证据清单与可获取性（实测）

| 证据 | 东莞通 | villa-details | 判定 |
|---|---|---|---|
| 门→走廊连通 | corridor 实体 3（`npts=0`），≤3m 命中 4 门 | 0 | 不足 |
| 门→楼梯间连通 | stair 类 4（3 CIRCLE+1 staircase），≤200mm 13 门、≤8m 362 门 | 0 | 覆盖与歧义均不可接受 |
| 紧邻出口符号 | `exit` 实体 1（“安全出口”），≤200mm 3、≤1m 6、≤5m **66** | 0 | 一个符号 5m 半径圈住 66 门 |
| 门窗表编号 FM/HFM | text 620，FM 89、HFM 3；≤3m **229 门**；另有 11 门靠近一段“室外…标志”说明文字（讲救援窗，非门标注） | text 实体 0 | 东莞通 FM 语义是防火门≠疏散门；villa 无 |
| 所在房间类型 | 房间类 181 / 多边形 92 / 门在多边形内 205 | 34 / 23 / 117 | 计算可行，但 villa 轮廓非平面房间 |
| 门宽分布 | 3248 全有，中位 1.0m，≥0.9m 1958 | 2523 有值，中位 0.79m，≤0.2m 254 | 无区分力 |
| 墙面朝向 / 外侧连通 | 墙实体 **1482** vs LINE 图元 **27749**；外侧判“室外”**1882/3248 = 58%** | 1681 墙实体；外侧 297（10.7%，但为立面） | 东莞通严重失真 |
| 现有标注 | `is_evacuation_door` 0/3248 | 20/2772 | 东莞通无正例 |

#### 11.8.2 人工核对 27 例与精度/召回

核对方式：按红叉门渲染 8–40m 视窗（东莞通 40m 看外轮廓，villa 8m 看构件类型）。

**东莞通 · 候选 9 例**：DOOR_3761/8949/9122（evac_text≤3m）、DOOR_1891/4286/8711/1872
（exit≤5m）、DOOR_091/293（fire_label）——图上**全部是室内门**（前 7 例为房间内墙门，
DOOR_091 为局部大样、不是平面门），正确 **0/9**。
**东莞通 · 未标注对照 6 例**：DOOR_040/051/059/092/107/149，全部室内（059 旁有楼梯阴影，
判不明），样本内无确认疏散门。

**villa · 候选 8 例**：DOOR_006（屋面/烟囱区）、063/073/082/099/195（立面门窗）、
228（檐口，w=0.05m）、231（楼梯详图片段）——**0 例**可计为平面疏散门，正确 **0/8**。
**villa · 未标注对照 4 例**：DOOR_001/004/013/018，均为立面门窗符号。

- **精度**：东莞通 0/9、villa 0/8，合计 **0/17 = 0%**（门槛 ≥90%，未达成）。
- **召回**：27 例人工核对中确认的疏散门为 **0 例**，召回分母为 0，**不可测**；
  villa 因图幅为立面，结构上不存在可判读的疏散门语义，召回按 **0** 计。
- **并集上限**：若把全部证据取并集，东莞通将标注 **2366/3248 = 73%** 的门；
  一个标 73% 门的规则不可能达到 90% 精度，因此不允许“放宽证据凑精度”。

#### 11.8.3 替代方案：以“门与室外/楼梯间直接连通”作几何启用判据——不可行

实测三处结构性失效：

1. **外侧连通判定失真**：东莞通按“图纸边框 flood fill = 室外”计算，58%（1882/3248）的门被判外侧连通；
   其中 **1197 门（37%）两侧同时为“室外”**，在几何上不可能（门两侧不可能都在室外）。
   根因是障碍集不闭合：墙实体只有 1482 个，而 LINE 图元有 27,749 个。
2. **楼梯不可识别**：东莞通仅 4 个 stair 类实体（3 CIRCLE + 1 staircase），villa 为 0；
   “与楼梯间直接连通”在无梯段实体的图上无从计算。
3. **图幅不匹配**：villa-details 为立面/大样（见 11.8.0），“通向室外”在该图上不存在可判定拓扑。

**判定：语义推断与几何替代判据均不可行，不实现生产代码。** 阻塞在上游：①图幅筛选
（立面/大样不得进入平面审查域）；②墙体网络完整化；③出口/楼梯构件识别。三者缺一，
只能产出大面积错标。

### 11.9 villa 图幅误判修正与覆盖率重算（2026-11-06，commit `787c0c6`）

#### 11.9.1 villa 的完整平面证据画像（原始图元口径）

villa-details 共 10,190 图元、25 个用到图层。原始文字 112 条（58 TEXT + 54 MTEXT），
分类如下——**没有一条平面标注**：

| 文字类别 | 条数 | 内容 |
|---|---|---|
| 立面编号 | 3 | `Facade 1-9`、`Facade 9-1`、`Facade E-A` |
| 标高 | 3 | `Level 2`、`Level1`、`Level 2` |
| 轴号 | 81 | 1–2 位数字（`1`–`9`）与西里尔字母轴号（`А`/`Б`/`В`/`Г`） |
| 房间名 | 0 | — |
| 门窗编号 | 0 | — |
| 尺寸标注数字 | 0 | — |
| 未转义轴号/其它 | 25 | `\U+0415`、`\U+0410` 等（西里尔字母的 unicode 转义残留） |
| DIMENSION 图元 | 0 | — |
| 纯中文文字 | 0 | — |

闭合多边形：显式闭合多段线 **335 个**（若计入 ≥4 顶点未闭合面为 436 个）。
按 LINE 长度中位数（292）与文字高度中位数（262）判定图纸单位为 **mm**，面积换算后：

| 面积分位 | p10 | p50 | p90 | max |
|---|---|---|---|---|
| m² | 0.002 | **0.062** | 0.405 | 10.74 |

≥0.5㎡ 仅 **9.6%（32/335）**，≥2㎡ 仅 **2.4%（8/335）**。面积集中在构件倒角/线脚量级，
**不构成房间平面轮廓**。

轴线与尺寸链：存在轴网（图层 `axis`，83 条 LINE；轴号文字 81 条），但**没有尺寸链**
（DIMENSION 0、尺寸数字 0）——只有“轴网 + 立面视图名 + 标高”，这是立面/大样图的标准组合。

门窗编号格式：0 条，**无任何平面式编号**（无 M/C/FM/HFM 等）。

语义侧交叉验证（详见 §11.8.0）：34 个“房间”中仅 23 个有多边形，轮廓来自立面图元；
2,772 个“门”里 254 扇宽度 ≤0.2m，含 w=0.05m 的檐口——门窗实为立面构件。

#### 11.9.2 判据：R3 平面图必须有平面证据

旧 R3 只看图层词元（`plan/wall/door/window/axis/...`），而立面/大样图的图层名同样含
这些词（villa 命中 7 个），因此**单靠图层词元不能判平面**。新判据要求 R3 在原有触发条件
（平面词元图层 ≥2 或（闭合面 ≥3% 且标注 ≥1%））之上，再满足以下**任一平面证据**：

- **A. 平面型标注**：2–8 字纯中文房间名、门窗编号（`HM1220`/`FM1020` 等）、
  尺寸数字（≥3 位整数或带小数，如 `2400`/`2.650`）、DIMENSION 图元；
- **B. 房间状闭合多边形**：闭合多段线 ≥10 个，且面积 ≥0.5㎡ 的占比 ≥15%
  （面积单位按 LINE 长度中位数自适应：≥50 判 mm，否则 m）；
- **C. 完全无文字标注**：无从用标注否定平面，保留原图层词元判据。

三条均不满足 → 判**未知/低置信（R4）**，不再进入平面审查域。
代码落点：`src/baa_engine/drawing_classifier.py` 的 `classify_sheet_type`，阈值常量
`_SHEET_ROOM_MIN_AREA_M2=0.5`、`_SHEET_ROOM_MIN_POLYGONS=10`、`_SHEET_ROOM_MIN_RATIO=0.15`。

#### 11.9.3 逐张判定结果与证据（9 图重跑）

| 图纸 | 平面词元图层 | 闭合面 | 标注 | 文字 | 平面型标注 | 闭合多边形 | ≥0.5㎡占比 | 单位 | 新判定 | 命中的平面证据 |
|---|---|---|---|---|---|---|---|---|---|---|
| 东莞通 | 0 | 4.23% | 6.68% | 2320 | **1106** | 13 | 100% | mm | **plan** | A（尺寸数字 415 + 门窗编号 11 + 中文 760） |
| villa | 7 | 6.02% | 1.10% | 112 | **0** | 335 | **9.6%** | mm | **unknown** | 无（A/B/C 均不满足） |
| stadion | 4 | 8.95% | 5.65% | 156 | 0 | 245 | **49.4%** | m | **plan** | B |
| plans | 0 | 18.18% | 16.20% | 245 | 0 | 220 | **21.8%** | m | **plan** | B |
| demo | 4 | 0% | 0% | **0** | 0 | 0 | — | m | **plan** | C（无文字） |
| restroom | 0 | 0.69% | 0.14% | 197 | 0 | 274 | 22.6% | m | unreviewable（R2） | 判据前置于 R3，不变 |
| mosque | 0 | 0.05% | 0.78% | 47 | 0 | 1 | 100% | m | elevation_section（R1） | 判据前置于 R3，不变 |
| 通风（暖通） | 0 | 22.22% | 66.67% | 6 | 0 | 2 | 100%（仅 2 个） | m | **unknown** | 无；已按专业跳过 |
| 电气（大图） | — | — | — | — | — | — | — | — | plan（专业跳过） | 原判据不变 |

**未误伤已确认平面图**：东莞通、stadion、plans、demo 全部仍判 `plan`；两个合成平面样本
（`test_r3_plan_by_layer_tokens`、`test_fire_elevator_plan_not_non_plan`）仍判 `plan`。
**挡住 villa**：唯一不满足任何平面证据的被审图纸，`plan → unknown`。

#### 11.9.4 9 图改前/改后逐张对比

| 图纸 | evaluated 改前→改后 | applicable 改前→改后 | findings 改前→改后 | sheet_type 改前→改后 |
|---|---|---|---|---|
| 东莞通 | 37 → 37 | 177 → 177 | 20 → 20（low 20） | plan → plan |
| villa | 17 → 17 | 140 → 140 | 16 → 16（critical 10 / low 6） | **plan → unknown** |
| stadion | 3 → 3 | 58 → 58 | 0 → 0 | plan → plan |
| plans | 1 → 1 | 32 → 32 | 0 → 0 | plan → plan |
| demo | 0 → 0 | 29 → 29 | 0 → 0 | plan → plan |
| restroom | 0 → 0 | 0 → 0 | 0 → 0 | unreviewable（不变） |
| mosque | 0 → 0 | 0 → 0 | 0 → 0 | elevation_section（不变） |
| 通风（暖通） | 0 → 0 | 0 → 0 | 0 → 0 | plan → unknown（专业已跳过） |
| 电气（大图） | 0 → 0 | 0 → 0 | 0 → 0 | plan → plan（专业已跳过） |

**逐张 evaluated/applicable/findings 与改前完全一致**：只改图幅标签，不改判定逻辑。
`unknown` 与 `plan` 都正常审查，因此 villa 的 17/140/16 原样保留。

#### 11.9.5 覆盖率三口径重算：分母缩水 vs 真实变化

| 口径 | 含 villa（5 图，旧） | 剔除 villa（4 图，新） | 变化 |
|---|---|---|---|
| 全规则（并集） | 42 / 183 = **23.0%** | 36 / 177 = **20.3%** | −2.7pp |
| 可判定（并集，剔 76→74 条 unsupported_2d） | 42 / 107 = **39.3%** | 36 / 103 = **35.0%** | −4.3pp |
| 逐图累加（比例） | 58 / 436 = **13.3%** | 41 / 296 = **13.9%** | +0.6pp |
| 逐图累加（可判定） | 58 / 252 = **23.0%** | 41 / 177 = **23.2%** | +0.2pp |

**拆解：哪部分是分母缩水、哪部分是真实变化**

1. **分母缩水（全部来自 villa 移出）**
   - 并集分母 183 → 177（−6）：仅在 villa 适用的 6 条规则
     `ACCESS-005`、`ACCESS-008`、`ACCESS-020`、`DIM-107`、`DIM-111`、`EXIST-036`；
   - 可判定分母 107 → 103（−4）：上述 6 条中 `ACCESS-020`、`DIM-111` 属 `unsupported_2d`，
     因此只缩 4 条；
   - 逐图累加分母 436 → 296（−140）：villa 自身的适用规则数。
2. **分子变化**
   - 并集分子 42 → 36（−6）：`ACCESS-005`、`ACCESS-008`、`DIM-001`、`DIM-006`、
     `EXIST-036`、`EXIST-066`；
   - 逐图累加分子 58 → 41（−17）：villa 自身的判定规则数。
   - 其中 `DIM-001`/`DIM-006`/`EXIST-066` 在 4 图口径下**仍然适用**（留在分母），
     只是从未在其余 4 图产出判定——这是剔图后**真实的分子损失**；另外 3 条随分母一起移出。
3. **真实变化（代码层面）= 0**：4 张平面图逐张 evaluated/applicable/findings 与改前一致，
   判定逻辑未改，覆盖率变化**全部由统计口径剔除 villa 造成**。

**结论（不粉饰）**：并集口径覆盖率**下降**（23.0% → 20.3%、39.3% → 35.0%），因为 villa
是唯一“分母新增 6 条、分子同时新增 6 条”（该切片 100% 被判定）的图纸，剔除后整体被拉低。
若只缩分母不缩分子，会得到 42/177 = 23.7%——**这个数不能采用**，实际分子同步降到 36。
逐图累加口径反而 +0.6pp，原因是 villa 自身 17/140 = 12.1% 低于其余四图的加权均值；
两个口径方向相反，如实并列。

#### 11.9.6 findings 与 critical

| 口径 | findings | critical |
|---|---|---|
| 新平面审查域（4 图） | **20** | **0** |
| 旧平面审查域（5 图，含 villa） | 36 | 10 |
| 生产全样本（villa 以 unknown 正常审查） | **36** | **10** |

**验收纪律回应**：本轮**新增 critical = 0**（<20，无需停下）。
但必须写明：critical 从 10 降到 0 是**“移出统计口径”而非“修复误报”**——villa 仍以
`unknown` 正常审查（低置信），那 10 条 critical 在生产侧仍会输出。它们很可能与 §11.8.0
的立面构件误判同源，需另做判据约束，不在本次图幅修正范围内。
