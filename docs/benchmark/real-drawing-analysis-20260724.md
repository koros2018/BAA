# P0 Benchmark: 真实图纸实体类型分布分析

> 分析时间: 2026-07-24 | 分析脚本: scripts/real_drawing_audit.py + 手工分析
> 数据来源: data/real_drawing_audit_report.json（16 张真实图纸全量审计）

## 1. 解析成功率

| 状态 | 数量 | 图纸 |
|------|------|------|
| 解析成功 | 12/16 | 含 8 张大图纸（最大 61,834 图元）|
| 解析失败 | 4/16 | 天正 T3 外部参照格式（东莞通-电气/报警/气体/设备）|

## 2. 语义实体类型产出（44 种）

跨所有成功解析图纸，语义分析器共产出 **44 种实体类型**（P70 后）。

### 2.1 "other"（未分类图元）占比

| 图纸 | other 占比 | 状态 |
|------|-----------|------|
| 东莞通-建筑 | **75.0%** | 🔴 严重 |
| A1云计算中心_水消防 | **51.6%** | 🔴 |
| 基础+2#,3#上部 | **45.7%** | 🔴 |
| A1云计算中心平面图 | **43.6%** | 🔴 |
| 20210409-3#泵房 | 33.3% | 🟡 |
| 中原总图 | 29.5% | 🟡 |
| 202109409-配电房 | 29.1% | 🟡 |
| E-00-01-01 室外电气 | 12.7% | 🟢 |
| 其余 5 张 | 0~2.4% | 🟢 |

**全部图纸平均: 32% 图元未分类 → 约 21,267 个图元存在但语义分析器无法归类**

## 3. P70 实体类型覆盖验证

| 指标 | 数值 |
|------|------|
| P70 定义的实体类型 | 47 |
| 真实图纸中实际检出 | **12（25.5%）** |
| 真实图纸中未检出 | **35（74.5%）** |

### 3.1 已检出的 12 种（真实图纸中存在且能被分析器识别）
`antechamber, column, facade, fire_alarm, floor, lobby, pump, pump_room, rescue_window, road, room, speaker`

### 3.2 未检出的 35 种（P70 定义了但真实图纸中无对应实体产出）
`accessible_door, accessible_elevator, accessible_room, alarm_button, alarm_center, control_room, curtain_wall, detector, distribution_box, driveway, duct, electrical, emergency_broadcast, emergency_power, evacuation_door, evacuation_sign, exit_door, fire_control_room, fire_curtain, fire_lane, fire_system, fire_wall, gas_suppression, heat_detector, insulation, outdoor_stair, piping, pump_controller, refuge, rescue_opening, roof, shaft, sprinkler_system, staircase, staircase_door`

**⚠️ 关键问题：P70 的 100% 覆盖率是对代码结构的，真实图纸中只有 25.5% 能被实际检出。**

## 4. FAIL 分析（违规项分布）

| 指标 | 数值 |
|------|------|
| 总函数调用 | 58,293 |
| PASS | 49,634 (85%) |
| FAIL | **8,659 (14.9%)** |

### 4.1 FAIL 集中度分析（Top 3）

| 函数 | FAIL 数 | 总数 | FAIL 率 | 目标实体 | 阈值 |
|------|---------|------|---------|---------|------|
| EXIST-052 防火墙门窗洞口 | 3,590 | 3,590 | **100%** | door/fire_wall/opening/window | ≤0 |
| EXIST-083 消防救援窗 | 2,265 | 2,265 | **100%** | rescue_window | ≥2 |
| EXIST-093 消防窗口设置 | 2,265 | 2,265 | **100%** | rescue_window | ≥2 |

**这三个函数占全部 FAIL 的 97.7%（8,120/8,659）。**

### 4.2 EXIST-052 逻辑分析

```
函数: 防火墙上不应开设门窗洞口
条件: count(door/window/opening on fire_wall) ≤ 0
```

100% FAIL 的可能原因：
1. `fire_wall` 实体识别不足 → 所有门窗被标记为"在防火墙上"
2. 判定逻辑：每张图的每个 door/window/opening 都被判定，而不是按"在防火墙上"的过滤
3. 需要检查 `matches()` 是否真的过滤了 fire_wall 上的门窗

### 4.3 EXIST-083/093 逻辑分析

```
函数: 每个防火分区应设 ≥2 个消防救援窗
条件: count(rescue_window per fire_zone) ≥ 2
```

100% FAIL 的可能原因：
1. `rescue_window` 识别不足（16 张图中仅 3 张检出，共 3 个）
2. 或判定是按"无防火分区的图纸"逐图判定，每张图整体 ≤2

## 5. 黄金标准基线对比

| 状态 | 数值 |
|------|------|
| CONFIRMED（已知违规） | 9 |
| 漏报 | **9（100% 漏报）** |
| 回归 | 0 |

漏报清单：
- 20210409-3#泵房 EVAC-004（楼梯间前室）
- 202109409-配电房 EVAC-004
- A1云计算中心_水消防 DIM-006（疏散门宽度）
- A1云计算中心平面图 DIST-001/EVAC-001/EVAC-004
- ZY数据中心 EVAC-001
- 东莞通建筑 DIST-001/EVAC-001

## 6. 结论与下一步

### 系统性缺口（优先级排序）

| 优先级 | 问题 | 影响 | 修复方向 |
|--------|------|------|---------|
| P0 | "other" 未分类 32% | ~21,000 图元未被语义分析 | LAYER_RULES 覆盖不足 |
| P0 | P70 74.5% 实体类型未检出 | 代码覆盖≠实际检出 | 层名映射 + TEXT 模式不足 |
| P1 | EXIST-052 100% FAIL | 疑似逻辑缺陷（门窗→防火墙过滤） | 检查 fire_wall 拓扑过滤 |
| P1 | EXIST-083/093 100% FAIL | rescue_window 识别不足 + 按图判定 | 分防火分区聚合逻辑 |
| P2 | 9/9 黄金标准漏报 | 核心违规（EVAC/DIM/DIST）漏检 | 疏散连通性 + 宽度判定 |

## 7. EXIST-052/083/093 误报根因分析（已确认）

### 7.1 EXIST-052: 防火墙门窗洞口

| 项目 | 值 |
|------|-----|
| 函数语义 | 防火墙上不应开设门、窗、洞口（GB50016-6.1.5）|
| target_entities | door, fire_wall, opening, window |
| 实际判定 | 匹配图纸中**所有** door/window/opening，不区分是否在防火墙上 |
| fire_wall 检出数 | 全部 0（所有图纸）|

**验证**: 每张图 FAIL 数 = door + window + opening 精确匹配

| 图纸 | door+window+opening | fire_wall | FAIL | 匹配 |
|------|-------------------|-----------|------|------|
| 泵房 | 29 | 0 | 29 | ✓ |
| 配电房 | 80 | 0 | 80 | ✓ |
| 水消防 | 1,634 | 0 | 1,634 | ✓ |
| 平面图 | 806 | 0 | 806 | ✓ |
| ZY数据中心 | 467 | 0 | 467 | ✓ |
| 中原总图 | 10 | 0 | 10 | ✓ |
| 基础+上部 | 148 | 0 | 148 | ✓ |
| 东莞通 | 416 | 0 | 416 | ✓ |

**→ 100% 误报。根因：`matches()` 匹配所有门窗，不检查实体是否在防火墙上。**

### 7.2 EXIST-083/093: 消防救援窗

| 项目 | 值 |
|------|-----|
| 函数语义 | 每个防火分区应设 ≥2 个消防救援窗（GB50016-7.2.1/7.2.3）|
| target_entities | fire_rescue_opening / fire_window / rescue_window / window |
| 实际判定 | 对**每个** window 实体单独检查 count ≥ 2（每个单独 window 的 count=1）|
| 聚合逻辑 | 缺失：未按防火分区聚合后判定 |

**验证**: 每张图 FAIL 数 = window + rescue_window 精确匹配

**→ 100% 误报。根因：缺少按防火分区的聚合判定逻辑。**

### 7.3 整体 FAIL 构成

| 来源 | FAIL 数 | 占比 | 性质 |
|------|---------|------|------|
| EXIST-052 | 3,590 | 41.5% | 100% 误报 |
| EXIST-083 | 2,265 | 26.2% | 100% 误报 |
| EXIST-093 | 2,265 | 26.2% | 100% 误报 |
| 其余 6 函数 | 539 | 6.2% | 待人工标注 |
| **总计** | **8,659** | **100%** | **93.8% 确认为误报** |

## 8. 关键结论

**8,659 项 FAIL 中，至少 8,120 项（93.8%）是系统性误报，根因是 3 个 EXIST 函数缺乏空间上下文约束或聚合逻辑。**

真正的违规率需要从剩余 539 项（DIST-001 432 + 其余 107）中人工标注确认。
