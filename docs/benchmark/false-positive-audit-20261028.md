# 误报率评估与治理（E5 · 2026-10-28）

> 脚本：`scripts/fp_rate_audit.py`（复刻 `review_routes` 生产判定语义，逐条 finding 输出）
> 数据：`data/drawings/real/`（本地，未入库）
> 结论：单张真实图纸可证误报率 **79.3% → 0%**（违规类 findings 820 → 170，-79.3%）

## 1. 口径与基线

| 项 | 说明 |
|---|---|
| 旧基线 93.8% | 出处 `docs/benchmark/real-drawing-analysis-20260724.md`：8,659 条 FAIL 中 8,120 条来自 EXIST-052/083/093 |
| 为何不可直接比较 | EXIST 三函数已由 T-B2 作用域聚合修复（`docs/tb2_acceptance/README.md`），旧值已失效，必须重测 |
| 本次测量口径 | 与生产主链路一致：本地函数逐实体 `execute_chained`；全局/EXIST 缺失检查走 `scope_aggregator`（partial→low 提示，missing→critical） |
| 与旧审计脚本差异 | `scripts/real_drawing_audit.py` 对所有函数盲跑 `matches/execute`，不区分 `requires_global_context`，会把 EXIST-083/093 按实体重复计 FAIL（本次实测残留 6 条），**不可用于误报统计** |
| 分母定义 | 违规类 findings（排除 `low` 区域提示）；`low` 是"作用域分布提示"，不是违规结论 |

## 2. 数据可用性（必须先说明）

| 文件 | 大小 | 解析结果 |
|---|---|---|
| 东莞通-建筑-外部参照（不打印）.dxf | 5.81 MB | 34,748 图元 / 10,089 实体（**唯一可用真实图**） |
| 其余 9 个 `*.dxf` | ≈0.01 MB | 仅 HEADER 段，0 图元 / 0 实体（占位桩） |

→ 本次误报率是**单图纸结论**，不能外推为全客户精度；但该图规模（1 万实体、2,644 门）足以暴露系统性误报通道。

## 3. 治理前测量（东莞通-建筑）

| 指标 | 数值 |
|---|---|
| findings 总数 | 846 |
| 违规类 findings | 820（low 区域提示 26 不计） |
| 可证误报 | **650** |
| **可证误报率** | **79.3%** |
| 严重度分布 | critical 108 / major 523 / minor 189 / low 26 |

### 3.1 逐来源归因

| 来源 | 数量 | 占违规类 | 结论 | 根因 |
|---|---|---|---|---|
| DIM-113 房间疏散门净宽（普通 `door`） | 647 | 78.9% | **误报** | 适用性缺失：普通门无"疏散门"语义（卫生间/设备/管井门），实测 0.70~0.88m；DIM-006/DIM-009 早有"普通门 <1.3m 豁免"约定，DIM-113 漏加 |
| DIM-009 浮点边界 | 2 | 0.2% | **误报** | 实测 0.8999999999999 vs 阈值 0.9，浮点表示误差被判 FAIL |
| DIM-001 楼梯净宽 | 1 | 0.1% | **误报** | TEXT 实体被误分类为 `stair`，文本框长边 396mm 当作楼梯净宽 |
| DIM-006 疏散门净宽 | 121 | 14.8% | 设计中（待复核） | 58 个 `door`（1.30~1.37m）与黄金标准 CONFIRMED 的"58 个消防门宽度违规"数量吻合；63 个 `doorway` 由 P108 扫线法直接判定（`test_p108_doorway_dim.py` 明确约定） |
| EVAC-002 / EVAC-003 | 36 | 4.4% | 待领域核验 | 18 个房间共享同一路径长度 48.28m → 房间级重复计数（同一条疏散路径） |
| EVAC-001 连通性 | 5 | 0.6% | 待领域核验 | `has_evacuation_route=False`（Step 5.5 对"不在路径表即无路径"的回填） |
| DIM-009 实际 <0.9 的 doorway | 8 | 1.0% | 待核验 | 洞口 0.80~0.89m，可能真违规 |
| EXIST 类 | 26 | — | 区域提示 | 全部 `low`（网格作用域 partial，103 格中部分未检出），非违规结论 |

## 4. 治理项（已实施）

| # | 改动 | 位置 | 效果 |
|---|---|---|---|
| 1 | DIM-113 适用性守卫：普通 `door` 无疏散门证据（`is_evacuation_door`/`evacuation_door`/subtype）→ 不判违规；`exit_door`/`evacuation_door`/`room_door` 照常判定 | `src/baa_engine/atomic_functions.py`（`_extract_value` DIM-113 分支） | 消除 647 条误报 |
| 2 | 阈值比较容差 `_compare()`：`>=`/`<=` 用 `math.isclose(rel_tol=1e-6)` 吸收表示误差；真实偏差不放宽（0.85 vs 0.9 仍 FAIL） | `src/baa_engine/atomic_functions.py`（`_compare` + 两处比较点） | 消除浮点边界误报 |
| 3 | DIM-001 合理性下限：楼梯净宽 <0.6m → 视为分类/测量错误跳过 | `src/baa_engine/atomic_functions.py`（宽度提取分支） | 消除文本框误判 |

回归测试：`src/tests/test_ta4_atomic_recompute.py`
- `test_dim113_door_mm_unit_auto_convert`（改为疏散门实体判定 + 普通门跳过 + 显式标注仍判定）
- `test_dim009_float_boundary_tolerance`（表示误差 PASS，真实偏差 FAIL）

## 5. 治理后复测

| 指标 | 治理前 | 治理后 | 变化 |
|---|---|---|---|
| findings 总数 | 846 | 196 | **-76.8%** |
| 违规类 findings | 820 | 170 | **-79.3%** |
| critical | 108 | 61 | -43.5% |
| major | 523 | 37 | -92.9% |
| minor | 189 | 72 | -61.9% |
| low 区域提示 | 26 | 26 | 0（设计预期） |
| 可证误报 | 650 | **0** | -100% |
| 可证误报率 | 79.3% | **0%** | — |

治理后剩余 170 条违规类 findings：DIM-006 121、EVAC-002/003 36、DIM-009 8、EVAC-001 5 —— 均无机械可证前提不成立，进入领域复核队列。

全量回归：`python -m pytest src/tests -q` → **2803 passed, 26 skipped, 14 deselected**。

## 6. 局限与后续

1. **单图纸结论**：其余真实图纸为 HEADER 占位桩，需补充真实图纸资产后重复本测量。
2. **召回风险（诚实披露）**：普通门 <0.9m 不再判违规；若某 0.8m 门确为房间疏散门，将漏报。解除方式：语义层标注 `is_evacuation_door`（房间类型 + 走廊连通证据），届时守卫自动放行。
3. **DIM-006 doorway**：P108 明确"扫线法几何精度高于 YOLO，始终判定"，本轮不改；若领域复核判定为误报，需同步修改其单测口径。
4. **EVAC-002/003 房间级重复**：同一疏散路径被 18 个房间各报一次，属聚合语义问题（应按出口/分区聚合），需单独设计，不在本轮范围。

## 7. 复现

```bash
python scripts/fp_rate_audit.py                       # 全部真实图纸
python scripts/fp_rate_audit.py "data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf"
# 明细：data/fp_rate_audit_report.json（逐条 finding + 机械归因）
```
