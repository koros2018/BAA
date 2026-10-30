# DIM-006 / DIM-001 领域复核摘要

**复核日期**: 2026-10-30
**复核依据**: 跨图纸复测报告（32 图，2206 findings）

---

## 1. DIM-006 疏散门净宽（324 条 FAIL）

### 数据分布
| 来源 | 数量 | 实际值范围 | 置信度 | 宽度来源 |
|---|---|---|---|---|
| door（普通门） | 212 | 1.30~1.37m | 0.85~0.95 | CAD dimension 标注（`_dimension_source=dimension`）|
| doorway（扫线洞口） | 112 | 1.30~1.37m | — | gap_width_mm（≥1.3m 保留判定）|

### 根因分析
- **door 212 条**：宽度来自 CAD 尺寸标注（dimension_parser 匹配到门实体），非 bbox 推断。E5 基线已 CONFIRMED 58 条为真实消防门宽度违规（< 1.4m）。置信度已由「偏差幅度」逻辑衰减至 0.85~0.95，反映阈值接近的不确定性。
- **doorway 112 条**：≥1.3m 的门洞，保留判定以不遗漏大尺寸疏散通道。

### 结论
**无需置信度降权**。CAD dimension 标注是可靠数据源，现有置信度衰减机制已覆盖阈值接近场景。212 条 door FAIL 进入领域复核队列，区分真实违规 vs 标注偏差。

---

## 2. DIM-001 疏散楼梯净宽（146 条 FAIL）

### 数据分布
| 来源 | 数量 | 实际值范围 | 置信度 | 宽度来源 |
|---|---|---|---|---|
| stair/staircase | 146 | 0.60~1.06m | **1.0**（过高）| `stair_bbox_long_edge` / `stair_bbox_span` |

### 根因分析
- 全部 146 条的 `_width_source ∈ {"stair_bbox_long_edge", "stair_bbox_span"}`
- STAIR 实体在 CAD 中以 LINE/POLYLINE 形式存在，bbox 长边 = 楼梯段水平投影长度（≈1.5~3m），短边 ≈ 踏步宽度（150~300mm）
- 实测值 0.60~1.06m **既不是长边也不是短边**——是楼梯旋转后外接矩形的对角/斜边投影，**系统性低估真实净宽**
- E5 基线曾定位 1 例 TEXT 误分类（396mm 文本框当楼梯），此次 146 条全部来自 bbox 长边，是系统性测量缺陷
- 原置信度 = 1.0（最高），严重高估测量可靠性

### 已实施修复
在 `_calculate_confidence`（atomic_functions.py:338~344）新增第 5 步宽度来源降权：
```python
# 5. 宽度来源降权：bbox 推断的楼梯宽度系统性低估
width_source = props.get("_width_source", "")
if width_source in ("stair_bbox_long_edge", "stair_bbox_span"):
    confidence *= 0.7  # bbox 推断的楼梯宽度不可靠
```

**效果**：146 条 DIM-001 stair FAIL 置信度从 1.0 → 0.7，审计界面可见低置信度警示，避免高置信度 critical 误导判断。

---

## 3. 治理汇总

| 规则 | 改前 FAIL | 改后 FAIL | 置信度变化 | 状态 |
|---|---|---|---|---|
| DIM-006 door | 212 | 212（不变）| 0.85~0.95（已有）| 进入领域复核队列 |
| DIM-001 stair | 146 | 146（不变）| **1.0→0.7** | 已降权，审计可见 |

### 后续行动
- DIM-006 door 212 条：提交领域复核，人工甄别真实违规 vs 标注偏差
- DIM-001 stair：考虑方案 B（合理性检查跳过 >2m 值）需等 bbox 测量根因修复（识别楼梯旋转角度）后再评估
