# 遗留治理项证据链(2026-10-19)

> 来源:用户指示「先清理遗留治理项」。三项均为真实数据验证,全量回归 **2484 passed / 0 failed**。

## 治理① fire_compartment 分类落地(T-B2 遗留)

**现状缺口**:scope_aggregator `build_scopes` 设计为「分区优先、回退 50m 网格」,但分类链路从不产出分区实体,实际全部回退网格(tb2_acceptance README 局限节)。

**真实图纸摸底**(252 张全库扫描):
- `平面布置底图0712(1).dxf`/`_建筑底图参照.dxf`/`装饰图纸0929.dxf` 的 `A-FIRE` 图层含闭合 LWPOLYLINE 分区边界(实测 219~5483m²,同族项目图纸);
- 修复前这些多边形走几何兜底被「>500m² 判图纸边框」规则丢弃,分区信息完全损失;
- 全库无其他误伤面:`暖-防火防烟分区`(图例行,≤47.7m²)、`W-HYDW-FIRE`(总图边界 27万m²+)均不含 `A-FIRE` 子串,不受影响。

**改动**(3 文件):
1. `_layer_rules_fire.py`:`"A-FIRE" → fire_compartment`(xref 嵌套 `底图平面图$0$11$0$A-FIRE` 含子串同命中);
2. `classify.py`:区域守卫 `_is_compartment_region`——分区类型仅接受闭合多边形/HATCH 且 bbox≥25m²(真实分区数百~数千 m²,25m² 下限只滤分隔线/文字/图例块等退化几何);守卫置于几何兜底之后,统一拦截图层/块名两条来源;
3. `scope_aggregator.py`:`_COMPARTMENT_TYPES` 接受 `fire_compartment` + `fire_zone`(中文「防火分区」图层规则产出类型)。

**真实图纸验证**(平面布置底图0712(1).dxf):
- 产出 3 个 fire_compartment 实体(1387m² / 5590m²×2,重复多边形经 IoU 归并);
- `build_scopes` mode: grid(90 格)→ **compartment(3 分区)**,实体归属 364/1009/932;
- 单测 10 个(`test_fire_compartment.py`):闭合多边形/xref 嵌套层命中、分隔线/小 HATCH/TEXT/图例块滤除、scope 集成 pass/partial/网格回退。

## 治理② 语义层 door 转换缺口对齐(组件层 vs 实体层过滤差异)

**根因**(d3 实测):组件层 `t3_native` 识别跑全量文档,实体层 `analyze` 在 `primitives > max_entities=10000` 时 `random.sample` 抽样——d3 23,651 图元中 381 个 T3 标记图元(门 236/窗 137/柱 8)被随机丢弃 227 个。**「组件层已识别、实体层消失」的系统性漏报缺口。**

**改动**(`main.py` 采样段):T3 标记图元(`_t3_native`/`_t3_window_gid`/`_t3_wall_gid`)全量豁免采样(权威识别结果且占比小,d3 仅 1.6%),采样仅从未标记图元池进行,保持 seed=42 口径。

**验证**:单测 4 个(`test_t3_sampling_exemption.py`):标记门/墙全量保留、未标记池按预算采样、低于上限不采样行为不变。

## 治理③ T-B3 唯一真实漏报根因修复

**漏报点**:d3 平面内门 (7044239.2, 1364371.5)——组件层正确识别(`$DorLib2D$00000001`, handle=13A55),被上述采样丢弃(治理②同一根因)。

**修复后复测**(`recall_metrics.py`,3 张 T3 gold):

| 指标 | 修复前 | 修复后 |
|---|---|---|
| opening_micro recall | 0.9796(48/49) | **1.0(49/49)** |
| door / window / column recall | door 0.9167 | 全部 1.0 |
| d3 audit_box 内 door 实体 | 3 | 16 |

- `docs/recall_metrics/history.jsonl` 已追加修复后记录(第 4 条);
- wall F1 三张均 1.0 未回归;T3 native 墙标记同属豁免集,墙覆盖只增不减;
- CI recall_gate(0.75)余量充足。

## 回归

- 全量 `pytest src/tests`:**2484 passed / 0 failed**(基线 2470 + 新增 14 个治理单测)。
- 期间事故:recall_metrics 相对 GOLD_DIR 需在仓库根目录运行,误跑产生的 files=0 历史记录已剔除并恢复 3 条正确记录(无 BOM/LF)。
