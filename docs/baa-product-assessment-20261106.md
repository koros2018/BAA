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

## 12. 扫线 doorway 补 ID（阶段 A）与 `closed` 真值核查（2026-11-08）

### 12.1 阶段 A：补稳定 ID + 显式 `exit_eligible=False` 隔离

**问题**：`room.py::_detect_doorway_gaps` 产出的扫线墙洞长期 `entity_id=""`。

1. **不可追溯**：finding / 路由 / 关系图里的空 ID 无法定位到具体墙洞；
2. **依赖隐式约束**：`evacuation.py` 此前用「空 ID」这一巧合挡住 doorway 成为合成出口
   （P132-B5 已记录该风险），一旦补 ID 就会立刻放行；
3. **空 ID 还是共享伪节点**：所有墙洞的邻接边都挂在同一个 `""` 节点上，等于把所有有墙洞
   的空间连成一张全连通网——这不是拓扑证据，是 ID 缺失造成的假连通。

**改动**（`room.py` + `evacuation.py`）：

- ID 由间隙中心点几何派生：`doorway_gap_{h|v}_{cx}_{cy}`（整数毫米）。同图重跑稳定，
  不占用房间的递增计数器，不会让 `line_chain_room_*` 编号漂移；
- 属性落盘 `exit_eligible=False`、`inferred_from="wall_gap"`：墙线间隙只证明「此处有开口」，
  不证明「是疏散出口」。`doorway` 与 `exit_door` 同属原子函数别名组 4，必须显式否定，
  不能继续靠空 ID 巧合；
- `evacuation.py` 新增 `_exit_eligible()`，三处出口候选（`strict_exits` / `fallback_exits` /
  `fallback_exits_sweep`）统一加过滤；
- 墙洞仍保留为关系图节点（不额外屏蔽），用于后续阶段 B 做「洞口作边」的正确连通建模。

**测试**：

- `test_pdf_pipeline.py::test_detect_doorway_gaps` 增加断言：ID 前缀/唯一性/同输入重跑稳定、
  `exit_eligible is False`、`inferred_from == "wall_gap"`；
- `test_p132_b5_empty_exit.py` 新增 3 条：带 ID 但 `exit_eligible=False` 的墙洞不得成为出口；
  有真实门时路由必须落到真实门；显式缺省（`exit_eligible` 未设）的 doorway 仍可作出口
  （P107 口径不变）。

**逐图改前 → 改后（`scripts/fp_rate_audit.py` 复现）**：

| 图 | doorway | entity_count | evaluated | applicable | judgeable | findings |
|---|---|---|---|---|---|---|
| 东莞通-建筑 | 277 → 277 | 10086 → 10086 | 35 → 35 | 177 → 177 | 101 → 101 | **20 → 26** |
| villa-details | 27 → 27 | 8608 → 8608 | 10 → 10 | 114 → 114 | 53 → 53 | 6 → 6 |
| multiple-stadion | 0 → 0 | 2208 | 3 → 3 | 58 → 58 | 38 → 38 | 0 → 0 |
| two-family-house | 0 → 0 | 997 | 1 → 1 | 32 → 32 | 18 → 18 | 0 → 0 |
| Demo F-1 | 0 → 0 | 68 | 0 → 0 | 29 → 29 | 18 → 18 | 0 → 0 |

覆盖率三口径**全部不变**（并集 41/183 = 22.4%、可判定 38/105 = 36.2% 的当前值）。

**新增 6 条 critical（全部在东莞通，逐条列出）**：

| func_id | entity_id | actual | threshold | severity |
|---|---|---|---|---|
| EVAC-001 | ROOM_1803 | 0.0 | 1.0 | critical |
| EVAC-001 | ROOM_3377 | 0.0 | 1.0 | critical |
| EVAC-001 | ROOM_349 | 0.0 | 1.0 | critical |
| EVAC-001 | ROOM_5066 | 0.0 | 1.0 | critical |
| EVAC-001 | ROOM_7881 | 0.0 | 1.0 | critical |
| EVAC-001 | ROOM_911 | 0.0 | 1.0 | critical |

**这 6 条是不是新假阳性？逐条用「补 ID 前的旧邻接复演」核验**：

| room | 旧口径路径（空 ID 回填） |
|---|---|
| ROOM_1803 | `ROOM_1803 → polyline_room_10024 → polyline_corridor_10023 → "" → EXIT_2903` |
| ROOM_3377 | `ROOM_3377 → "" → EXIT_2903` |
| ROOM_349 | `ROOM_349 → DOOR_5719 → ROOM_4283 → "" → EXIT_2903` |
| ROOM_5066 | `ROOM_5066 → "" → EXIT_2903` |
| ROOM_7881 | `ROOM_7881 → "" → EXIT_2903` |
| ROOM_911 | `ROOM_911 → "" → EXIT_2903` |

6 条旧路径**全部经过空字符串节点**。该节点把 277 个互不相同的墙洞合并成一个点：
「房间挨着某个墙洞」+「EXIT_2903 挨着另一个墙洞」就足以宣布连通。这不是真实拓扑，
是 ID 缺失制造的**假阴性（掩盖了无路径）**。补 ID 后该伪节点消失，这 6 间房改为
如实报告「模型内无疏散路径」。

**结论与边界**：这 6 条**不是新假阳性**，是移除伪拓扑后的真实判定；但也不能据此断言
建筑违规——当前模型还没有「洞口作为两个空间之间的边」的拓扑（阶段 B 才做）。因此：

- 不调 EVAC-001 判据、不加白名单掩盖这 6 条；
- 阶段 B 需要让墙洞以**边**而非**节点**参与关系图，届时才能给出「经洞口到达出口」的
  合格路径；在此之前这 6 条如实输出。

### 12.2 `closed="False"` 字符串真值核查：无真实来源，不改代码

结论：**当前代码链路不存在把布尔值写成字符串的路径，不提交推测性防御改动。**

证据：

1. `properties["closed"]` 的唯一写入点是 `parsers/geometry.py:177` 的
   `props["closed"] = geo_closed`，`geo_closed` 是 `bool`（`is_closed` 的结果）；
2. T3 原生解析只把 `closed` 用作局部变量，未写入 `properties`；
3. 全仓无 API/MCP 入参把 `properties` 反序列化为字符串的路径；持久化缓存与 DB 走 JSON，
   `true/false` 反序列化回来仍是 `bool`，不会变成 `"False"`；
4. 规则判定处 `semantic_analyzer/main.py::_is_closed_region` 已用 `is True` 严格判断，
   即便真的出现字符串也不会被误判为闭合；
5. `drawing_classifier.py:568/572` 的两处 truthiness 只参与图幅统计
   （`closed_count` / `closed_polygon_count` 与闭合面积均值），不进入任何规则判定，
   影响面限于图幅画像指标。

处置：**记录观察，不改代码**。按纪律不为「看起来有进展」提交无实际收益的改动。若未来
出现外部 JSON 注入 `properties` 的入口，需在该入口做类型归一化（`"True"/"true"` → `True`），
届时再补判据与测试。

## 13. EVAC-001 证据分级：区分「建筑无出口」与「建模缺口」（2026-11-08）

### 13.1 问题

§12.1 补 ID 后出现的 6 条 EVAC-001 critical，其旧路径全部经过空字符串伪节点。它们的
共同成因是**连通图缺边**，不是图纸证明该房间没有出口。但旧实现把两者用同一个
`actual=0.0 / threshold=1.0` 的 critical 表达，读者无法区分「模型没算出来」与「建筑真违规」——
与前面几轮反复纠正的「无证据 ≠ 违规」是同一类问题。

### 13.2 判据（新增 `evacuation_evidence` 实体属性）

| 级别 | 条件（全部满足） | 处置 |
|---|---|---|
| `sealed_no_opening` | `closed is True`、`point_count >= 4`、邻接实体中没有门/窗/洞口类、也不与其他空间相邻 | 出 EVAC-001 判定；FAIL 为 critical |
| `model_gap` | 其余全部情形：有门窗/墙洞邻接、有空间邻接、未闭合、顶点不足 | insufficient_evidence，返回 None，不产出 PASS/FAIL |

实现位置：

- [main.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/main.py) `_evacuation_evidence_level()`，
  在 Step 5.5 两处「注入 `has_evacuation_route=False`」的路径上同时写 `evacuation_evidence`；
- [atomic_functions.py](file:///d:/OpenClawData/BAA/src/baa_engine/atomic_functions.py) EVAC-001 `_extract_value`，
  仅 `sealed_no_opening` 放行；缺失证据级别（旧缓存/旧数据）也不判。

### 13.3 6 条 critical 的逐条降级依据（可核对）

| room | closed | point_count | area_m2 | 邻接证据 | 级别 |
|---|---|---|---|---|---|
| ROOM_1803 | False | 4 | 27.11 | room×1 + corridor×1（仅空间相邻） | model_gap |
| ROOM_3377 | False | 3 | 17.85 | doorway×2 + door×5 | model_gap |
| ROOM_349 | False | 3 | 13.8 | door×2 | model_gap |
| ROOM_5066 | False | 4 | 15.86 | door×6 + doorway×4 + room×1 | model_gap |
| ROOM_7881 | False | 3 | 38.71 | door×2 + doorway×3 + room×1 | model_gap |
| ROOM_911 | False | 4 | 21.25 | door×2 + doorway×2 + room×2 | model_gap |

6 间房 `closed` 全为 False（扫线/T 字接头派生，边界未显式闭合）；其中 5 间直接邻接
门或墙洞，ROOM_1803 直接邻接走廊。两条独立理由都指向「建模缺口」，不是「建筑无出口」。

### 13.4 逐图改前 → 改后

| 图 | evaluated | applicable | judgeable | EVAC-001 findings | findings 总数 |
|---|---|---|---|---|---|
| 东莞通-建筑 | 35 → 35 | 177 → 177 | 101 → 101 | 6 → 0 | 26 → 20 |
| villa-details | 10 → 10 | 114 → 114 | 53 → 53 | 0 → 0 | 6 → 6 |
| multiple-stadion | 3 → 3 | 58 → 58 | 38 → 38 | 0 → 0 | 0 → 0 |
| two-family-house | 1 → 1 | 32 → 32 | 18 → 18 | 0 → 0 | 0 → 0 |
| Demo F-1 | 0 → 0 | 29 → 29 | 18 → 18 | 0 → 0 | 0 → 0 |

覆盖率三口径不变；新增 critical 为 0。

### 13.5 「真实违规仍会报」的反例

5 张样本中没有 `sealed_no_opening` 房间（因此这 6 条之外没有真实无出口案例）。用单元测试
固定反例：`has_evacuation_route=False + evacuation_evidence="sealed_no_opening"` →
EVAC-001 FAIL / critical；`model_gap` → None。见
[test_evacuation_connectivity.py](file:///d:/OpenClawData/BAA/src/tests/test_evacuation_connectivity.py)
`TestEvac001EvidenceGrading`。该判据不会让「闭合房间 + 周边无任何洞口」的真实违规静默。

## 14. 阶段 B 可行性预研：墙洞改为「空间间的边」（2026-11-08）

> **已被 §17 重跑取代**：本节为 2026-11-08 早间快照（房间缺 points、假 room 未抑制），
> 保留以对照；最新结论、成功率与失败模式见 §17。

### 14.1 方法

对每个扫线墙洞，取间隙中心点沿法向（horizontal 墙洞 → y 方向；vertical → x 方向）两侧
偏移 300/600/1000/1500/2500/4000mm 探测，用射线法判断落点属于哪个 room 多边形。
统计「两侧各命中一个不同 room」的比例；只在「墙洞 500mm 内存在已识别 room」的子集上评估
配对算法本身，避免把上游房间提取缺口算到配对头上。

### 14.2 结果

| 图 | doorway | room | 近邻房间(<500mm) | 两侧配对成功 | 单侧命中 | 两侧都无 |
|---|---|---|---|---|---|---|
| 东莞通 | 277 | 126 | 27（9.7%） | **0（0%）** | 13（48.1%） | 14（51.9%） |
| villa | 27 | 8 | 26（96.3%）* | **0（0%）** | 0 | 26（100%） |

\* villa 的 26 个「近邻」主要由一个覆盖全图的假房间 `line_chain_room_9032`（26×15m）造成，
该房间没有多边形 points，无法做点包含判定，因此 0 命中。

### 14.3 失败模式分布（按影响从大到小）

1. **上游房间覆盖不足**：东莞通 175/277（63.2%）墙洞距最近 room bbox ≥5m，中位 8.0m——
   这些墙洞位于未被识别为 room 的区域（走廊/外部/其它构件），配对无从谈起。
2. **房间几何缺失**：东莞通 32/126 个 room 没有 `properties.points`（只有 bbox），
   无法做真实多边形包含判定。
3. **全图级假 room**：东莞通 11 个 room 的 bbox >50m²（最大 45×10m、7×37m）；villa 8 个
   room 中 5 个是 25×24m 级别的全图假房间。它们会让「近邻」统计虚高，并可能把任意墙洞
   配对到同一个错误空间。
4. **单侧命中**：东莞通 13 个近邻墙洞只有一侧落进 room，另一侧多为外墙/未识别空间。

### 14.4 结论

**阶段 B 当前不可行**，不是因为配对算法，而是因为前置条件不满足：房间提取覆盖率、
房间多边形完整性、假 room 抑制三项都未达到可用水平。继续实现「墙洞作边」只会把
错误的房间配对固化成疏散拓扑，风险高于收益。

后续解锁条件（按顺序）：

1. 房间几何补全：所有 room 必须带多边形 points（bbox-only 房间需回填或标记不可用）；
2. 假 room 抑制：全图级 bbox（例如 >50m² 且无 points）不得参与空间拓扑；
3. 再在「两侧都有可靠多边形」的子集上重跑本预研，两侧配对成功率需先达到可用阈值
   （建议 ≥80% 且失败样本可逐条解释）才进入实现。

### 14.5 第三优先：1500mm 聚类 phantom

阶段 B 预研没有产出足以裁决 `_find_gaps_in_axis_v2` 1500mm 跨墙线聚类的证据（房间侧
不可靠，无法判断 phantom 是否影响配对）。按纪律**不调容差、不改代码**，缺陷继续挂在
§9.7.4；待阶段 B 前置条件满足后一并裁决。

## 15. 房间多边形完整性（Task 1，2026-11-08）

### 15.1 诊断：32/32 来自「直接闭合多段线」构造路径

东莞通原 126 个 room 中 32 个没有 `properties.points`。逐条回溯后的结论：

| 项 | 结论 |
|---|---|
| 来源 | **32/32 全部是 `polyline_room_*`**，由 `_extract_closed_polyline_rooms`（直接闭合 LWPOLYLINE）构造 |
| 其它路径 | 扫线主面 0、`_sweep_and_filter` 0、文字标签 0、块 0 |
| 同源但不在 room 口径 | 另有 3 个 `polyline_corridor_*`，同样缺 points |
| 根因 | **构造期就没写**。该分支已算出 `pts` 并据此算 `area`，但 properties 只写 `{"area": ...}`，未写 `points` / `point_count` / `closed` |
| 是否写入后丢失 | **不是**。该分支在 `_sweep_line_detect_rooms` 中早返回；Step 1.8 只修正面积，不写 points；全链路无删除 points 的代码 |
| 非 polyline 房间 | 94 个，`no_points = 0`，说明缺口只在这一条构造路径 |

### 15.2 方案选择：补齐 points，不降级

选择「凡是 room 必须带可用 points」并**补齐**，而不是把 32 个降级为未识别。理由：

1. 几何在构造时已存在：闭合 LWPOLYLINE 的顶点序列直接可得，降级会删掉 17 个真实闭合
   多边形房间（东莞通 10012 的 124.2m²、10024 的 96.3m² 都在其中），违反「不丢真实房间」。
2. 「构造不出 points」与「几何不可信」是两类问题。32 个都有几何；其中 15 个的问题在
   Task 2 的几何合理性（重复/容器/空壳），应由门禁单独降级，不能混同为「无几何」。
3. 补齐后可立即用于下游点包含/内切/净宽；降级则会让这 32 个空间永久退出几何能力。

实现（[room.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py)）：

- 新增 `_polygon_props()`：统一写 `points` / `point_count` / `closed=True`；剥离与首点重合的
  闭合点；顶点 <3 或坐标非法返回 `{}`。
- 三处房间构造（扫线主循环、`_sweep_and_filter`、`_extract_closed_polyline_rooms`）在写入
  `area` 后统一 `props.update(_polygon_props(pts))`。
- DXF/T3 的 LWPOLYLINE 不写 closed 标志且首尾可能相距整条边长，因此不能靠首尾距离判断
  闭合；面积本就按整环 shoelace 计算，统一记 `closed=True`。

### 15.3 32 个逐条处理结果

**补全保留 17 / 补全后被 Task 2 门禁降级 15 / 仍缺 0。**

| 结果 | 实体 | 顶点 | 面积 m² | 备注 |
|---|---|---|---|---|
| 补全保留 | polyline_room_10012 | 8 | 124.2 | 设备房，见 §16.5 |
| 补全保留 | polyline_room_10024 | 8 | 96.3 | 设备房，见 §16.5 |
| 补全保留 | polyline_room_10002 | 4 | 27.0 | |
| 补全保留 | polyline_room_10021 | 4 | 18.1 | |
| 补全保留 | polyline_room_10019 | 4 | 17.0 | |
| 补全保留 | polyline_room_10030 | 4 | 15.0 | |
| 补全保留 | polyline_room_10004 | 4 | 14.5 | |
| 补全保留 | polyline_room_10007 | 4 | 14.4 | |
| 补全保留 | polyline_room_10015 | 4 | 13.8 | |
| 补全保留 | polyline_room_10014 | 4 | 13.5 | |
| 补全保留 | polyline_room_10001 | 4 | 13.0 | |
| 补全保留 | polyline_room_10016 | 8 | 12.0 | |
| 补全保留 | polyline_room_10006 | 4 | 11.0 | |
| 补全保留 | polyline_room_10028 | 4 | 9.7 | |
| 补全保留 | polyline_room_10010 | 4 | 9.2 | |
| 补全保留 | polyline_room_10020 | 4 | 8.0 | |
| 补全保留 | polyline_room_10017 | 8 | 6.1 | |
| 降级 | polyline_room_10029 | 4 | 448.0 | duplicate_entity（ROOM_784，IoU 1.0） |
| 降级 | polyline_room_10011 | 4 | 288.0 | room_container（内 10 个空间实体 + 走道） |
| 降级 | polyline_room_10027 | 4 | 270.1 | room_container（卫生间二 / 强电间 2 个标注） |
| 降级 | polyline_room_10032 | 4 | 270.1 | room_container（1 空间实体 + 消防器材室） |
| 降级 | polyline_room_10034 | 4 | 246.6 | empty_outline（最近洞口 35.98m） |
| 降级 | polyline_room_10013 | 4 | 121.0 | room_container（内 5 个空间实体） |
| 降级 | polyline_room_10003 | 4 | 46.5 | duplicate_entity（ROOM_6717，IoU 1.0） |
| 降级 | polyline_room_10009 | 4 | 37.2 | duplicate_entity（ROOM_1993，IoU 1.0） |
| 降级 | polyline_room_10033 | 4 | 36.0 | duplicate_entity（ROOM_7353，IoU 0.937） |
| 降级 | polyline_room_10031 | 4 | 24.5 | duplicate_entity（ROOM_3402，IoU 1.0） |
| 降级 | polyline_room_10018 | 4 | 21.2 | duplicate_entity（ROOM_9929，IoU 0.99） |
| 降级 | polyline_room_10000 | 4 | 13.0 | duplicate_entity（ROOM_7506，IoU 1.0） |
| 降级 | polyline_room_10008 | 4 | 12.8 | duplicate_entity（ROOM_1956，IoU 1.0） |
| 降级 | polyline_room_10005 | 4 | 6.0 | duplicate_entity（ROOM_9814，IoU 1.0） |
| 降级 | polyline_room_10026 | 4 | 5.9 | duplicate_entity（ROOM_3966，IoU 1.0） |

> 15 个降级全部有几何（顶点 4），降级原因是几何不可信，不是「无法构造 points」；
> 若按「无 points 才降级」规则，这 15 个会全部保留，与 §16 的假 room 抑制目标冲突。

### 15.4 补全后的几何质量

| 指标 | 东莞通（107 room/corridor） | villa（24 room） |
|---|---|---|
| 顶点数分布 | 3:13、4:88、5:2、8:4 | 4:15、5:8、7:1 |
| **最小顶点数** | **3**（13 个 3 点房间均为 `ROOM_*`，非 32 个补全对象） | 4 |
| 补全的 32 个 | 顶点 4–8，最小 4 | — |
| 自交（shapely `is_valid=False`） | **0 / 107** | **0 / 24** |
| 被 G 抑制的自交实体 | 1（ROOM_8555，9 点，1.78m²） | 29（§16.4） |
| 多边形面积 / bbox 面积 | min 0.300（ROOM_3593）、median 1.000 | min 0.704（ROOM_4551）、median ≈1.000 |
| 补全的 32 个 poly/bbox | min 0.375（10024）、其余多为 1.000 | — |
| `area` 属性 vs 多边形 shoelace | 补全的 32 个误差 <0.01% | 0 处 >2% |
| `area_m2` vs 多边形 | 13 个 `ROOM_*` 3 点未闭合房间不一致（见下） | 0 处 >2% |

**面积与 bbox 一致性的残留偏差（如实登记）**：东莞通有 13 个 `ROOM_*` 为 3 点、`closed=False`，
Step 1.8 的 `_correct_unclosed_room_area` 仍按 bbox 估算 `area_m2`（P131 既有口径），
与多边形 shoelace 面积不一致，例：ROOM_349 `area_m2=13.8` / 多边形 4.36m²、
ROOM_634 1.54 / 0.77、ROOM_3377 17.85 / 6.06。最大偏差约 3.2×。
这 13 个不在 32 个补全对象内，也不是本轮引入；本轮**未改**该口径（改它会牵动 P131 与
多张图的 EVAC/AREA 判定），在此登记供产品口径裁决。

### 15.5 与 32 个无 points 的关系

- 32 个补全后全部可用：顶点 ≥4、无自交、`area` 与多边形一致。
- 32 个中 17 个保留、15 个由 Task 2 门禁降级（逐条见 §15.3）；**没有「仍缺 points」**。
- 加上 3 个同源 corridor：`polyline_corridor_10022` duplicate 降级，10023（27.1m²）、
  10025（21.8m²）补全保留。东莞通最终 room/corridor = 107。

### 15.6 引擎级不变量（防回归）：room 必须带可用 points

32 个的根因是三条构造路径漏写；已在构造期统一落盘。为避免未来新增路径（如图层规则
`PLAN→room`、合并产生的 room）再次产出「无 points 的 room」，门禁函数另加兜底：

| 情形 | 处理 | 记录 |
|---|---|---|
| `properties.points` 缺失或坐标非法，bbox 有效 | 按 bbox 矩形补全（`points_source=bbox_rect`，`closed=True`，4 点） | 不进抑制日志（属补全） |
| `properties.points` 缺失且 bbox 无效（宽或高 ≤0） | `entity_type` 降级为 `other` | `room_suppressions` 中 `action=downgraded`、`reasons=[missing_polygon]` |

实测影响：5 张主样本中无此类实体（东莞通 107 / villa 24 的 room 均已在构造期带 points），
因此本轮数字不变；新增 2 条单元测试固定该不变量（补全保留、无效 bbox 降级）。

## 16. 假 room 抑制（Task 2，2026-11-08）

### 16.1 判据组合：7 条结构/上下文证据，不做面积单判

新增 `_suppress_implausible_rooms(entities, primitives)`，在 Step 1.4 之后、Step 1.8 之前执行
（[main.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/main.py) Step 1.4b），
逐条记录到 `room_suppressions`（id / bbox / reasons / evidence），供报告与审计。

| 代号 | 判据 | 参数 | 实测依据（为什么不是拍脑袋） |
|---|---|---|---|
| A | 退化多边形 | 多边形面积 / bbox 面积 **<5%** | 真实房间最低 0.300（ROOM_3593）、10024 0.375、10012 0.45；命中者 0.000–0.001（ROOM_4594/6562），相差 2 个数量级 |
| B | 未闭合大边界 | `closed != True` 且顶点 **<4** 且 bbox **≥50m²** | 命中 ROOM_4283（45.3×10.3m，3 点）、ROOM_7691（24.4×15.3m，3 点）；13 个 <50m² 的 3 点房间全部保留，避免误杀真实小房间 |
| C | 重复实体 | bbox IoU **≥0.90** 且面积相对差 **≤5%**，按来源权威度保留 | 11 条命中全部与 `ROOM_*` 同 bbox（IoU 1.0/0.99/0.937）；来源序：ROOM_（显式图元）> polyline_（直接闭合线）> line_chain_（面遍历派生） |
| D | 容器 / 整层轮廓 | 仅 **≥50m²**；内部空间实体 **≥2**，或不同房间名 **≥2**，或「空间实体 ≥1 且房间名 ≥1」 | 5 条命中：ROOM_784（10 实体 + 走道）、10011（10 实体 + 走道）、10027（卫生间二/强电间）、10032（1 实体 + 消防器材室）、10013（5 实体） |
| E | 空壳轮廓 | 仅 **≥50m²**；内部空间实体 **0** 且房间名 **0** 且边界 **5m** 内无洞口 | 1 条命中 10034（246.6m²，最近洞口 35.98m）；10012/10024 边界 1m 内有 14/2 个门窗，保留 |
| F | 贴图框 | bbox 与 titleblock 图框矩形重合 **≤500mm** | 5 张样本 **0 命中**；保留为后续图纸的防线，本轮不产生误杀 |
| G | 自交多边形 | 边界自交 / 重合边 / 重复顶点（`_is_simple_polygon`） | 东莞通 1 条（ROOM_8555）；villa 29 条，全部 shapely `is_valid=False`；保留房间 0 条无效 |

**为什么不是面积一刀切**：东莞通保留了 2 个 bbox ≥50m² 的真实空间（10012 276.3m² bbox、
10024 256.6m² bbox），villa 保留 24 个 4–7 顶点简单房间；抑制只发生在 A–G 至少一条成立时。

### 16.2 构造期剔除：有向面积 <0 的外侧包络面

左手法面遍历的定向约定：连通分量的**内面逆时针（signed >0）**，
**外侧包络面顺时针（signed <0）**。这是精确几何判据，不是面积阈值。
`_sweep_line_detect_rooms` 两处面循环已改为 `signed <= 0: continue`。

villa 的 5 个 25×24m 级假 room 正是这一类，构造期即被剔除（不会进入 entity 层）：

| 面积 m² | bbox | 顶点 | 内部包含的正向面数 |
|---|---|---|---|
| 392.8 | 25.4×23.5m | 105 | 158 |
| 354.3 | 24.4×21.1m | 95 | 125 |
| 161.5 | 26.0×15.2m | 96 | 192 |
| 129.6 | 34.5×12.1m | 92 | 63 |
| 116.8 | 25.0×11.9m | 93 | 56 |

「内部包含几十到上百个正向面」证明它们是连通分量的外侧包络，不是房间。villa 面遍历
共 50 个正向面 + 14 个非正面积面（含上表 5 个大面），剔除负向后保留 50 个正向面候选。

东莞通在同一路径的子调用中：43 个正向面、90 个非正面积面；非正面积面最大也落在
448m²（32×14m）、288m²（32×9m）、270m²（7×37m）量级，与 §14 的大 bbox 假 room 同尺度。
这些面未进入 entity 层；最终 11 个 bbox ≥50m² 的 room 由 A–G 逐条处置（§16.3）。

### 16.3 东莞通 22 条抑制明细

room/corridor 129 → 107（−22）。逐条：

| # | 实体 | bbox | bbox 面积 | 命中判据 | 证据 |
|---|---|---|---|---|---|
| 1 | ROOM_4283 | 45.3×10.3m | 466.6 | unclosed_polygon (B) | 3 点，closed=False |
| 2 | polyline_room_10029 | 32.0×14.0m | 448.0 | duplicate_entity (C) | duplicate_of=ROOM_784，IoU 1.0 |
| 3 | ROOM_784 | 32.0×14.0m | 448.0 | room_container (D) | 内 10 个空间实体 + 走道 |
| 4 | ROOM_7691 | 24.4×15.3m | 375.3 | unclosed_polygon (B) | 3 点，closed=False |
| 5 | polyline_room_10011 | 32.0×9.0m | 288.0 | room_container (D) | 内 10 个空间实体 + 走道 |
| 6 | polyline_room_10027 | 7.3×37.0m | 270.1 | room_container (D) | 标注 卫生间二 / 强电间 |
| 7 | polyline_room_10032 | 7.3×37.0m | 270.1 | room_container (D) | 1 空间实体 + 消防器材室 |
| 8 | polyline_room_10034 | 9.5×26.1m | 246.6 | empty_outline (E) | 最近洞口 35,982.8mm |
| 9 | polyline_room_10013 | 13.3×9.1m | 121.0 | room_container (D) | 内 5 个空间实体 |
| 10 | polyline_room_10003 | 5.0×9.3m | 46.5 | duplicate_entity (C) | ROOM_6717，IoU 1.0 |
| 11 | polyline_room_10009 | 4.0×9.3m | 37.2 | duplicate_entity (C) | ROOM_1993，IoU 1.0 |
| 12 | polyline_room_10033 | 6.0×6.0m | 36.0 | duplicate_entity (C) | ROOM_7353，IoU 0.937 |
| 13 | polyline_corridor_10022 | 10.4×2.6m | 27.1 | duplicate_entity (C) | ROOM_1803，IoU 1.0 |
| 14 | polyline_room_10031 | 3.5×7.0m | 24.5 | duplicate_entity (C) | ROOM_3402，IoU 1.0 |
| 15 | polyline_room_10018 | 5.1×4.2m | 21.2 | duplicate_entity (C) | ROOM_9929，IoU 0.99 |
| 16 | ROOM_4594 | 6.9×2.3m | 15.8 | degenerate_polygon (A) | 多边形 0.000m² |
| 17 | polyline_room_10000 | 5.2×2.5m | 13.0 | duplicate_entity (C) | ROOM_7506，IoU 1.0 |
| 18 | polyline_room_10008 | 4.0×3.2m | 12.8 | duplicate_entity (C) | ROOM_1956，IoU 1.0 |
| 19 | polyline_room_10005 | 2.5×2.4m | 6.0 | duplicate_entity (C) | ROOM_9814，IoU 1.0 |
| 20 | polyline_room_10026 | 2.7×2.2m | 5.9 | duplicate_entity (C) | ROOM_3966，IoU 1.0 |
| 21 | ROOM_8555 | 2.8×0.7m | 2.1 | self_intersecting (G) | 9 点，1.778m² |
| 22 | ROOM_6562 | 1.7×1.0m | 1.8 | degenerate_polygon (A) | 多边形 0.001m² |

判据分布：C 11、D 5、B 2、A 2、E 1、G 1。**D/C 全部有实体证据；A 的比值差 2 个数量级；
B 只作用于 ≥50m²；E 只作用于 ≥50m² 且 5m 内无洞口。**

### 16.4 villa 29 条抑制明细（全部 G 自交）

| 实体 | bbox | 面积 m² / 顶点 |
|---|---|---|
| line_chain_room_9067 | 10.2×7.2m | 61.1 / 52 |
| line_chain_room_9066 | 10.2×3.9m | 39.5 / 13 |
| line_chain_room_9039 | 3.8×8.2m | 27.4 / 26 |
| line_chain_room_9060 | 3.7×7.2m | 27.0 / 17 |
| line_chain_room_9034 | 7.8×3.0m | 23.5 / 13 |
| line_chain_corridor_9064 | 2.1×11.3m | 23.4 / 12 |
| line_chain_corridor_9063 | 2.2×8.2m | 18.0 / 8 |
| line_chain_corridor_9061 | 2.1×8.2m | 17.5 / 7 |
| line_chain_room_9058 | 4.0×4.2m | 17.1 / 13 |
| line_chain_room_9056 | 3.9×4.2m | 16.6 / 24 |
| line_chain_room_9075 | 3.9×4.1m | 15.9 / 17 |
| line_chain_room_9055 | 3.9×3.9m | 15.2 / 7 |
| line_chain_room_9059 | 3.7×3.9m | 14.6 / 7 |
| line_chain_room_9045 | 3.9×3.4m | 13.3 / 7 |
| line_chain_room_9074 | 3.9×4.1m | 12.2 / 18 |
| line_chain_room_9081 | 4.0×3.0m | 11.9 / 10 |
| line_chain_room_9033 | 3.6×3.2m | 11.6 / 19 |
| line_chain_room_9038 | 3.9×3.4m | 9.2 / 13 |
| line_chain_room_9054 | 2.2×4.2m | 9.1 / 14 |
| line_chain_room_9053 | 2.1×3.9m | 8.3 / 13 |
| line_chain_room_9065 | 2.1×3.9m | 7.7 / 12 |
| line_chain_room_9070 | 2.4×3.0m | 7.2 / 14 |
| line_chain_room_9078 | 2.5×3.0m | 7.2 / 7 |
| line_chain_room_9049 | 2.1×3.4m | 7.2 / 8 |
| line_chain_room_9080 | 2.4×3.0m | 7.1 / 9 |
| line_chain_room_9042 | 3.2×2.1m | 6.7 / 7 |
| line_chain_room_9036 | 4.0×3.8m | 6.2 / 27 |
| line_chain_room_9041 | 2.1×2.8m | 5.7 / 7 |
| line_chain_room_9035 | 3.9×3.2m | 5.2 / 16 |

villa 总量：**53（门禁关）→ 24（门禁开）**；相对 §14 的基线 8 个，实际是
「5 个 25×24m 假 room 构造期剔除 + 29 个自交面抑制 + 21 个正向简单面转正」。
29 条自交均无房间名标注（villa 全图没有任何 room-name 文本落在这些多边形内），
且 shapely 全部 `is_valid=False`，属于 X 型线交叉产生的不可用环，不是可修复的真实房间边界。

### 16.5 未误杀证明：保留的大面积房间逐条核对

东莞通门禁后 bbox ≥50m² 的 room 仅 2 个，全部保留：

| 实体 | bbox | bbox 面积 | 多边形面积 | 顶点 | 类型推断 | 边界 1m 内门窗 |
|---|---|---|---|---|---|---|
| polyline_room_10012 | 7.55×36.6m | 276.3 | 124.23 | 8 | equipment_room（0.762） | 14 |
| polyline_room_10024 | 23.5×10.9m | 256.6 | 96.28 | 8 | equipment_room（0.762） | 2 |

两条均为 L/U 形（poly/bbox 0.45 / 0.375），不是整层矩形；`equipment_room` 推断走
`room_type_infer` 的「需文本证据」分支，说明附近有设备类房间名；且边界 1m 内有 14/2 个
门/窗。A（≥0.05）、B（closed）、C（无同 bbox 重复）、D（内部无容器证据）、E（5m 内有洞口）、
G（简单环）全部不命中，故保留。**没有「大面积 ⇒ 抑制」这条规则。**

villa 门禁后无 bbox ≥50m² 的房间；24 个保留房间全部是 4/5/7 顶点简单多边形，
`area_m2` 与多边形面积 0 偏差，poly/bbox min 0.704。唯一 ≥50m² 的 9067 是 52 顶点自交
复合环，按 G 抑制并列入 §16.4。

### 16.6 下游变化（逐图，门禁前 → 门禁后）

同一 `fp_rate_audit.run_review`、同一 HEAD，只切换门禁函数：

| 图 | room/corridor 总数 | evaluated | applicable | findings |
|---|---|---|---|---|
| 东莞通-建筑 | 129 → **107** | 35 → **34** | 177 → **171** | 20 → **20** |
| villa-details | 53 → **24** | 17 → **9** | 159 → **108** | 6 → **6** |
| multiple-stadion | 0 → 0 | 3 → 3 | 58 → 58 | 0 → 0 |
| plans（two-family） | 0 → 0 | 1 → 1 | 32 → 32 | 0 → 0 |
| Demo F-1 | 0 → 0 | 0 → 0 | 29 → 29 | 0 → 0 |

- findings **零变化**：东莞通 20、villa 6，均无 critical；抑制只作用于假 room，未删除
  任何真实违规，也未新增 critical。
- evaluated 下降来自「被抑制房间原本承载的可判定规则」：东莞通 −1、villa −8；
  applicable 对应 −6 / −51。这是分母的诚实收缩，不是判定退化。
- 5 张样本合计 findings 26（全 low），与门禁前一致。

### 16.7 全量 79 图回归：门禁未引入新的 critical

用 `scripts/fp_rate_audit.py` 无参全量（`data/drawings/real` 79 个文件）复跑，口径与 §8 一致：

| 指标 | 门禁后 |
|---|---|
| 审计文件数 | 79 |
| 有效图纸 | 48（无效 8 + 跳过 22，均剔除出基线） |
| 规则可达（有效图纸并集） | 79 / 243 = 32.5%；可判定口径 72 / 165 = 43.6% |
| room 实体总数（含合成样本） | 240 |
| findings 原始条数 | 76（low 63 / critical 7 / major 4 / minor 2），分布在 9 个文件 |
| findings 去重后（func_id + entity_id） | 56（low 48 / critical 4 / major 3 / minor 1） |

去重是为了剔除两份同图副本（`baa-file-5840029dbcb8.dwg` 与 `baa-file-b042e240337a.dwg`）
产生的重复行。4 条唯一 critical 逐条如下：

| severity | 图 | 规则 | 实体 | actual / threshold | 性质 |
|---|---|---|---|---|---|
| critical | synth_control_room_violation.dxf | AREA-004 | polyline_room_3 | 16.0 / 30.0 | 人工构造的违规样本，预期 critical |
| critical | baa-file-5840029dbcb8.dwg | DIM-003 | ROAD_2527 | 0.8 / 4.0 | 道路宽度，与房间门禁无关 |
| critical | baa-file-5840029dbcb8.dwg | DIM-003 | ROAD_2841 | 0.5 / 4.0 | 同上 |
| critical | baa-file-5840029dbcb8.dwg | DIM-003 | ROAD_3290 | 2.0578 / 4.0 | 同上 |

结论：**门禁新增 critical = 0**。4 条 critical 中 1 条出自人工违规样本（设计上就该报），
3 条全部落在 `ROAD_*` 道路实体；没有任何一条挂在被抑制或被补全的 room 实体上。
对照 5 张主样本 findings 门禁前后 26 → 26（东莞通 20 / villa 6），可判定基数
（evaluated/applicable）只随假 room 分母收缩，未牵动任何既有 finding。

## 17. 阶段 B 重跑复核（Task 3，2026-11-08）

### 17.1 方法（与 §14.1 完全一致）

墙洞取间隙中心，沿法向（horizontal→y、vertical→x）两侧偏移 300/600/1000/1500/2500/4000mm，
射线法（shapely 点包含）判断落点属于哪个 room 多边形；只在「墙洞中心距最近 room 多边形
≤500mm」的近邻子集上评估配对算法本身；paired = 两侧各命中一个不同 room。

### 17.2 结果

| 图 | room | doorway | ≤500mm | 500–1000 | 1000–5000 | >5000 | 近邻子集 | paired | 近邻成功率 |
|---|---|---|---|---|---|---|---|---|---|
| 东莞通 | 107 | 277 | 15 | 16 | 59 | 187 | 15 | 4 | **26.7%** |
| villa | 24 | 27 | 7 | 5 | 11 | 4 | 7 | 1 | **14.3%** |
| stadion / two-family / Demo F-1 | 0 | 0 | — | — | — | — | 0 | 0 | — |
| **合计** | 131 | **304** | 22 | 21 | 70 | 191 | **22** | **5** | **22.7%** |

全量口径：5/304 = **1.6%**。

### 17.3 失败模式分布

| 失败模式 | 数量 | 占比（全量 doorway / 近邻子集） | 说明 |
|---|---|---|---|
| 上游房间覆盖不足（>500mm 无房间） | 282 | 92.8% / — | 其中 >5m 191 条（62.8%）；东莞通 187、villa 4 |
| 近邻但两侧零命中 | 14 | 4.6% / 63.6% | 墙洞中心落在房间边界的延长线上，最近房间是**侧向相邻**而非法向对侧；偏移 300–4000mm 均不进入 |
| 两侧命中同一房间 | 2 | 0.7% / 9.1% | 墙洞位于房间自身边界上，对侧无另一房间（未分割/未识别） |
| 单侧命中 | 1 | 0.3% / 4.5% | 一侧是已识别房间，另一侧是外墙/未识别空间 |
| **配对成功** | **5** | **1.6% / 22.7%** | 两侧各命中不同房间 |

典型近邻零命中（东莞通）：`doorway_gap_h_-13300_-36400` 距最近 room 边界 375mm，
该 room 在墙洞左侧（x 方向），而法向偏移沿 y 方向，任何偏移都不进入；说明墙洞不在
两个已识别空间之间。villa 同类 5 条的最近距离仅 15–30mm，但偏移仍全部落空，原因相同。

### 17.4 结论：22.7% < 80%，仍不具备可用水平

- 相比 §14 的 **0%**，近邻配对成功率提升到 **22.7%**（东莞通 0→26.7%，villa 0→14.3%）：
  points 补全与假 room 抑制确实解除了「无多边形可判」和「全图假 room 污染近邻」两个前置障碍。
- 但离 ≥80% 仍差一大截。瓶颈已从「房间没有 points」转移到**「房间集合不铺满平面图」**：
  304 个墙洞中 282 个（92.8%）在 500mm 内没有任何 room 多边形；近邻子集里 63.6% 的墙洞
  也不在两个空间之间。配对算法本身在 5 个成功样本上可复现，问题在前置的房间拓扑。
- 还差的一环（按顺序）：
  1. **房间覆盖**：当前东莞通的 room 主要来自「直接闭合 LWPOLYLINE」+ 少量 `ROOM_*`，
     走廊/管井/楼梯/由墙线围合的房间没有进入 room 集合；需要「墙线闭合环 + 门洞补边」
     的面提取，而不是只认闭合多段线。
  2. **面遍历的可信度**：villa 的 50 个正向面中 29 个自交不可用，说明图存在 X 型线交叉
     且未拆分；需先做边交叉拆分或面修复，才能让 villa 的可用房间数接近平面覆盖率。
  3. **墙洞有效性**：近邻零命中的 14 条说明 1500mm 聚类产生的部分间隙不是「两个空间
     之间的洞」，应先按两侧空间存在性过滤，再进入配对。
- 按 §14.4 的解锁条件，三项前置中「房间多边形完整性」已达成，「假 room 抑制」已达成，
  **「房间覆盖率」仍未达成**；因此阶段 B 不进入实现，缺陷与阈值均不改动。
- **后续**：针对「房间集合不铺满平面图」这条根，§18 对「墙线网络直接剥面」做了可行性验证；
  结论是当前墙线网络与噪声水平不达标，面提取不接入生产线。

### 17.5 本轮变更清单（供复核）

| 文件 | 变更 |
|---|---|
| [room.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py) | `_polygon_props` / `_is_simple_polygon` / `_suppress_implausible_rooms`；两处面循环 `signed<=0 continue`；三处构造写 points；无 points room 的 bbox 补全/降级兜底 |
| [main.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/main.py) | Step 1.4b 接入门禁；返回 `room_suppressions` |
| [test_room_geometry_integrity.py](file:///d:/OpenClawData/BAA/src/tests/test_room_geometry_integrity.py) | 18 条：`_polygon_props`、简单环、A–G 正例、真实大房间/小房间不误杀反例、points 不变量 |
| 文档 | §14 取代标注；§15/§16/§17 新增 |

## 18. 面提取可行性验证（阶段一，2026-11-08）

> 本轮为**只读原型**：临时探针直接调用 `drawing_parser` 与 `room.py` 内部函数，
> 不修改生产代码、不接入生产线。样本为东莞通（单层平面、34,748 图元）与
> villa-details（立面/大样，`sheet_type=unknown`）。
> **前置说明**：东莞通当前走「直接闭合 LWPOLYLINE」分支（35 个闭合多段线 ≥1 即返回），
> 图遍历面提取在生产中根本没有执行过；本节测的是「若改用面提取」的真实输入质量。

### 18.1 方法

1. 墙线候选：`_collect_wall_lines` → `_exclude_table_and_frame_prims` → `_collect_wall_segments`，
   与生产完全同一入口。
2. 闭合性统计：端点按 100mm 聚类得节点；悬空端点 = 仅一个线段端点且 100mm 内无其它线段经过；
   X 型交叉 = 两段参数均在内部的真交叉；同线断开 = 轴对齐（容差 300mm）线段按长度排序后的间隙，
   按 100–700 / 700–2500 / >2500mm 分档。
3. 面遍历：`_axis_align_merge` → `_split_t_junctions` → `_build_planar_graph` →
   `_sort_edges_at_nodes` → 左手法遍历（探针自带实现，**不做**图层/面积/长宽比过滤），
   正向面（逆时针）计入，外侧包络面剔除。
4. doorway 补边：`_detect_doorway_gaps` 的间隙中心线作为新边；两版对照——裸端点 /
   端点吸附到最近墙线（≤600mm 投影）。吸附后再 `_split_t_junctions` 并入网络。
5. 判定门槛：碎片（<0.5㎡）占比 > 40% 即判定「墙线噪声未解决」，不得用后置过滤改善数字。

### 18.2 东莞通：闭合性（补齐前后）

| 阶段 | 线段 | 焊接节点 | 悬空端点 | X 型交叉 | 同线断开 100–700 | 700–2500 | >2500 |
|---|---|---|---|---|---|---|---|
| 原始墙线 | 7,895 | 8,491 | **2,798（35.4%）** | **25,826** | 256 | 264 | 916 |
| 轴对齐合并后 | 2,423 | 4,635 | **3,176（65.5%）** | 5,756 | 78 | 231 | 786 |
| 基线 T/X 分割后 | 14,509 | 10,022 | 3,176 | 23 | 91 | 242 | 814 |
| +doorway 分割后 | 15,303 | 10,325 | 2,880 | 33 | 100 | 114 | 822 |

- 原始 35.4% 端点悬空；**轴对齐合并把悬空率推到 65.5%**（合并共线短段反而切断端点对齐），
  这是必须先修的闭合性缺陷。
- X 型交叉从 25,826 降到 23，说明 `_split_t_junctions` 确实拆开了交叉；但拆开不等于闭合，
  悬空端点没有减少（3,176 不变）。
- 墙线候选 **5,457 个图元全部在图层 `0`**（LINE 4,238 + LWPOLYLINE 1,219），
  无法靠图层名区分墙/轴网/图例/家具；同线间隙总长 38,992m（原始）/ 43,802m（合并后）。

### 18.3 东莞通：剥面结果与噪声

| 指标 | 基线（无 doorway） | +doorway（吸附后） |
|---|---|---|
| 正向面数 | 10,018 | 10,372 |
| 唯一面 / 重复面 | 5,270 / **4,748（47.4%）** | 5,462 / **4,910（47.3%）** |
| <0.5㎡ 碎片占比 | **61.8%（唯一后 59.8%）** | **61.9%（唯一后 59.8%）** |
| 狭长条（短边<0.5m 或长宽比>8） | 7,168（71.6%） | 7,398（71.3%） |
| 面积分布 | <0.5:6,191 / 0.5–5:3,258 / 5–20:406 / 20–50:102 / 50–100:43 / >100:18 | <0.5:6,420 / 0.5–5:3,365 / 5–20:419 / 20–50:110 / 50–100:42 / >100:16 |
| 面积合计 / 并集 | 26,355㎡ / **14,334㎡** | — / **14,331㎡** |

- **碎片 61.8% 远超 40% 门槛**；按唯一面去重后仍有 59.8%，不因重复面而改善。
- 面积合计 26,355㎡ > 并集 14,334㎡（约 1.84 倍），说明除重复面外还存在重叠几何；
  重复面 47.4% 是图内重复/共线几何在左手法遍历上的直接症状。
- 有文字标注的面仅 **323 / 10,372（3.1%）**，绝大多数面没有房间名可对齐。
- doorway 补边基本无效：277 个门洞中，仅 **32 个（11.6%）真正分隔两个面**；
  8 个两侧同面；**237 个未闭合/未接上**，其中 **214 个是桥边**（端点接进了图，但周边墙线不闭合，
  这条边无法围成新面）。端点吸附只把「两段都接上」从 86 提到 223，不能解决成环问题。

### 18.4 东莞通：覆盖率

覆盖率的分母无法可靠建立，三种口径都有硬伤：

| 分母口径 | 面积 | 覆盖率 | 问题 |
|---|---|---|---|
| 墙线节点凸包 | 20,655,423㎡ | 0.07% | 图内含轴网/图例外内容，节点最远到约 8km |
| 墙线节点 bbox | 48,653,949㎡ | 0.03% | 同上 |
| 节点坐标 5–95 分位核心框 | 302,428㎡ | 4.7% | 仍被长轴线的 p95 拉到 1,168m |
| 主连通分量凸包 | 59,511㎡ | 19.9% | 分量内仍挂长轴网/场地线 |

- 原始墙段中点 5–95 分位为 1,232m × 265m = 326,676㎡，最大中点在 x≈7,962m：
  **图内存在大量非建筑平面内容**（轴网、场地、图例、外部参照）。
- 因此「面覆盖了多少平面图面积」在本轮**不可计算**：面并集 14,334㎡ 中，仅抽样即可看到
  4 个大面（约 3,851㎡）属于空白区/设备大样。真实平面区域只能靠人工圈定，不能作为自动指标。
- 能给出的替代指标：现有 107 个 room 并集仅 **815.6㎡**（中位 2.1㎡、最大 124.2㎡），
  面并集是它的 **17.6 倍**；现有 room 仅覆盖面并集的 3.2%，面并集覆盖现有 room 的 56.9%。
  两者基本不对齐，既不能证明面更全，也不能证明 room 更准。

### 18.5 东莞通：面 vs 现有 107 个 room

| 指标 | 结果 |
|---|---|
| IoU ≥ 0.5（可认为同一空间） | 8 / 107 |
| IoU 0.1–0.5（部分重合） | 56 / 107 |
| IoU < 0.1（对不上） | 43 / 107 |
| ≥5㎡ 面中没有任何 room 覆盖 | **562 个** |
| 现有 room 并集被面覆盖 | 56.9% |
| 面并集落在现有 room 内 | 3.2% |

结论：面集合与现有 room 集合是两套互不对齐的划分——现有路径漏掉大量围合区，
面集合又把非房间区域混进来；不能用「重合度」单方面判定谁对。

### 18.6 人工抽查 10 个面（大小各半）

| # | 面积 | bbox | 顶点 | 位置/文字 | 判读 |
|---|---|---|---|---|---|
| 1 | 2,345.8㎡ | 110.1×21.3m | 4 | (-55,213)，无文字 | 图面左上空白区长矩形，由轴网/场地线围合 → **拓扑假面，非房间** |
| 2 | 2,345.8㎡ | 同上 | 4 | 同上 | #1 的**重复面**（遍历重复），非房间 |
| 3 | 698.7㎡ | 110.1×6.3m | 6 | (-55,196)，无文字 | 空白区相邻条带 → **非房间** |
| 4 | 409.4㎡ | 32.8×12.5m | 7 | (373,204)，"−7.400"/"3600m" | 设备/表格大样区 → **非房间（图纸本身含大样）** |
| 5 | 397.9㎡ | 32.8×12.2m | 6 | (373,217)，"总有效容积"/"−8.400" | 设备参数大样 → **非房间** |
| 6 | 1.73㎡ | 0.62×2.79m | 7 | (15.7,-12.6) | 墙缝窄条 → **线型噪声** |
| 7 | 3.60㎡ | 4.0×0.9m | 4 | (106.7,3.8) | 墙缝条 → **线型噪声** |
| 8 | 1.44㎡ | 1.2×1.2m | 4 | (-4.4,-37.2) | 柱/管井小盒 → **构件，非房间** |
| 9 | 8.00㎡ | 4.0×2.0m | 4 | (106.7,-39.1) | 平面密集区内小矩形，**疑似楼梯/小房间，无标注无法确认** |
| 10 | 6.27㎡ | 3.39×1.85m | 4 | (-16.0,10.5)，邻近"甲"/"FM"/"1020" | 防火门旁小间，**疑似楼梯/前室，无房间名** |

- 10 个面中 **8 个可确定为非房间**（4 个来自轴网/空白/设备大样，4 个来自墙缝/柱盒）；
  2 个面积与形态像小房间，但无文字标注，不能确认。
- 图面渲染复核（临时 PNG，不入库）显示：真正的平面密集区集中在 x≈−50~90m、y≈−50~15m；
  4 个大面全部在空白区或设备大样区，**大面≠房间** 在本图是稳定现象。

### 18.7 villa：不适用（预期结果）

| 指标 | villa-details |
|---|---|
| 墙线候选 / 原始段 | 847 / 883（layer 0 497、wall 88、friz 87、axis 74、doors 35、Furniture 33…） |
| 悬空端点 / X 交叉 | 273（30.9%）/ 817 |
| 基线面 / 唯一面 | 480 / 268（重复 212，44.2%） |
| <0.5㎡ 碎片 | 21.7%（唯一后 19.4%） |
| 覆盖率（面积加权 / 最大分量） | 39.7% / 50.7% |
| 与现有 24 个 room：IoU≥0.5 / 不符 | 20 / 4 |
| room 被面覆盖 / 面落在 room 内 | 80.0% / 25.4% |
| 文字实体 | **0** |

- villa 是立面/大样图（已判 `unknown`），没有平面房间语义，也没有任何文字标注。
  面提取剥出的是详图/立面围合区，与「房间」无关；20/24 的 IoU 匹配只说明详图区域被稳定围合，
  **不能作为房间识别能力**。
- 按约定不为了让 villa 过关而调参；本轮结论如实记为**不适用**。

### 18.8 判定：阶段一不达标，不接线

1. **碎片门槛未过**：61.8%（唯一后 59.8%）> 40% → 墙线噪声尚未解决。
2. **覆盖率不可计算**：墙线网络含轴网/场地/图例/外部参照，跨度到 8km，任何自动分母都被拉爆；
   真实平面区域需人工圈定，不能作为验收指标。
3. **doorway 作为边无效**：仅 11.6% 分隔两面，214/277 是桥边；在墙线不闭合的前提下，
   补门洞边不能生成房间。
4. **重复面 47.4%**：遍历在重复/共线几何上重复成面，必须先做几何去重与重合边处理。
5. 与现有 107 room 的 8/56/43 分布说明两套划分互不对齐，不能直接替换。

**继续面提取前必须先完成的前置（按顺序，均可量化）**：

1. **墙线候选清洗**：东莞通 100% 墙线候选在图层 `0`，需几何规则剔除轴网/图例/场地/外部参照；
   当前 7,895 段中约 36% 的中点落在平面密集区之外。
2. **闭合性修复**：原始悬空 2,798（35.4%），轴合并后 3,176（65.5%）；先修合并导致的端点错位，
   再做 ≤700mm 的缺口桥接，最后才谈门洞。
3. **几何去重**：消除 47.4% 重复面与 1.84 倍面积重叠，保证一次遍历一面对应一块区域。
4. **门洞补边改为强制成环**：从「补一条边」改为「在两侧墙上成对落点并把所在墙段切开」，
   目标是把 11.6% 的分隔率提升到可验收水平。
5. 以上四项完成并复测碎片 <40%、覆盖率有可解释分母后，才进入阶段二（并行输出、独立对比、
   不替换现有 room；下游规则切换逐条提交）。

### 18.9 复现与临时脚本

```powershell
# 只读探针（不入库，用完即删）
python "$env:TEMP\baa_probe_face_extract.py"
# 输出：$env:TEMP\baa_probe_face_extract.json + 控制台摘要；渲染复核图 baa_face_overlay_dg.png
```

临时脚本与本轮证据图均位于 `%TEMP%`，验证完成后已删除；本轮未修改任何生产代码，
未新增/删除测试，未做 git 破坏性操作。本轮仅新增本节文档并独立提交。


