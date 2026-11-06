# BAA 产品力评估（2026-11-06 · 基于 HEAD 1f6f245 实测）

> 口径：只采信仓库代码可复现的实测输出；推断部分显式标注。
> 本轮为**评估与取证**，不含代码改动。样本为 `data/drawings/real` 真实图纸 + 1 张 `data/files` 大图。
> 旧报告（`docs/baa-product-assessment-20261104.md`）保留不动，本文件不覆盖其结论。

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
- **验收**：restroom window 占比 ≤30%；东莞通 other ≤35%、stair ≥6（人工核对图面）且 corridor 有产出；`pytest` 全绿。
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
