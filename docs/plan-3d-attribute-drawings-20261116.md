# 引入 3D 属性图纸方案（2026-11-16）

## 1. 目标

打通 9 条 3D 属性类未判定规则（DIM-011/031/085/086/088/098/107/108、DIM-030），
这些规则判据载体（净高/转弯半径/扶手高度/消火栓高度/救援场地宽度）在 2D 图纸中
当前不可得。

## 2. 现状诊断

### 2.1 规则语义与 handler 错配

| 规则 | 语义 | 判据载体 | handler 现状 | 错配 |
|------|------|---------|-------------|------|
| DIM-011 | 消防车道净高 ≥4.0m（GB50016-7.1.8） | height | `_GENERIC_DIM_RULES` 读 **width** | **读错属性** |
| DIM-085 | 消防车道净高 ≥4.0m（GB50016-7.1.2） | height | 读 **width** | **读错属性** |
| DIM-098 | 消防车道净高 ≥4.0m（GB50016-7.1.1） | height | 读 **width** | **读错属性** |
| DIM-108 | 宽度+净高 ≥4.0m（GB50016-7.1.2） | width AND height | 读 **width** | **净高未判** |
| DIM-031 | 转弯半径 ≥9m（GB50016-7.1.3） | radius | 读 **width** | **读错属性** |
| DIM-086 | 转弯半径 ≥12m（GB50016-7.1.4） | radius | 读 **width** | **读错属性** |
| DIM-030 | 救援场地宽度 ≥10m（GB50016-7.2.2） | width | 读 width | 无 rescue_area 实体（样本覆盖限制，非 3D 属性） |
| DIM-088 | 消火栓栓口高度 1.1m（GB50974-7.4.10） | height | 无专用 handler | 属性未注入 |
| DIM-107 | 楼梯扶手高度（GB50763-3.6.3） | height | 无专用 handler | 属性未注入 |

### 2.2 根因

1. **handler 语义错配**：DIM-011/085/098 是净高规则，但 `_GENERIC_DIM_RULES` 统一读
   `width`（车道宽度）。净高 ≠ 宽度，语义错配。
2. **判据载体缺失**：road/fire_lane 实体无 `height`/`radius` 属性（bbox 为符号/标注，
   实测 87 个 road 全部 width=None）。净高/转弯半径需 CAD 标注解析注入。
3. **无净高/转弯半径标注解析器**：`text_attributes.py` 只有 `_parse_thickness_m`（厚度）
   和 `_parse_opening_code`（门窗编号），无净高/转弯半径解析。

## 3. 方案设计

### 3.1 新增净高/转弯半径标注解析器（text_attributes.py）

```python
# 净高标注：净高4.5m / H=4.5m / 净高4500 / 层高4.5m
_CLEAR_HEIGHT_PATTERN = re.compile(
    r"(?:净高|净空|层高|H\s*=|高度)\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(m|mm|M|MM)?"
)

# 转弯半径标注：转弯半径12m / R=12m / 转弯半径12000
_RADIUS_PATTERN = re.compile(
    r"(?:转弯半径|R\s*=|半径)\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(m|mm|M|MM)?"
)

def _parse_clear_height_m(text: str) -> Optional[float]:
    """解析净高标注 → 米。无匹配返回 None。"""
    ...

def _parse_turning_radius_m(text: str) -> Optional[float]:
    """解析转弯半径标注 → 米。无匹配返回 None。"""
    ...
```

注入逻辑（在 `_inject_text_attributes` 中新增分支）：
- 净高标注 → 就近 road/fire_lane/driveway 实体注入 `height`（source=`text_clear_height`）
- 转弯半径标注 → 就近 road/fire_lane 实体注入 `radius`（source=`text_radius`）

### 3.2 修复 handler 语义错配（atomic_functions.py）

```python
# 净高规则：读 height（非 width）
_CLEAR_HEIGHT_RULES = {"DIM-011", "DIM-085", "DIM-098"}
# 转弯半径规则：读 radius（非 width）
_RADIUS_RULES = {"DIM-031", "DIM-086"}

# 在 _GENERIC_DIM_RULES 分支前拦截：
if func_id in _CLEAR_HEIGHT_RULES:
    val = props.get("height", 0.0)
    if val < 0.01:
        return None  # 无净高标注，跳过判定
    return val * 1000.0  # m → mm（阈值 4000mm 口径）

if func_id in _RADIUS_RULES:
    val = props.get("radius", 0.0)
    if val < 0.01:
        return None  # 无转弯半径标注，跳过判定
    return val * 1000.0  # m → mm（阈值 9000/12000mm 口径）
```

DIM-108（宽度+净高复合）：保留 width 判定，净高部分在标注存在时叠加判定
（取更严格结果）。

### 3.3 引入 3D 属性图纸

需要含净高/转弯半径标注的图纸。候选来源：
1. **消防车道剖面图**：含「净高4.5m」标注（DIM-011/085/098）
2. **总平面图**：含「转弯半径12m」标注（DIM-031/086）
3. **合成图**：可构造含净高/转弯半径标注的合成图纸（确定性验证）

## 4. 验证方案

1. **单元测试**：
   - `_parse_clear_height_m`：净高4.5m / H=4.5m / 净高4500 / 无匹配
   - `_parse_turning_radius_m`：转弯半径12m / R=12m / 无匹配
   - DIM-011/085/098 handler：height=4.5 → PASS，height=3.5 → FAIL，无 height → None
   - DIM-031/086 handler：radius=12 → PASS，radius=8 → FAIL，无 radius → None

2. **合成图验证**：构造含「净高4.5m」标注的消防车道合成图，确认 DIM-011/085/098
   判定 PASS；构造含「转弯半径12m」标注，确认 DIM-031/086 判定 PASS。

3. **全量回归**：`python -m pytest src/tests -q`，确认无回归。

## 5. 收益评估

- 修复 handler 语义错配后，DIM-011/085/098（净高）与 DIM-031/086（转弯半径）
  在含标注图纸上可判定。
- 当前样本中 road/fire_lane 无 height/radius 标注（bbox 为符号），判据载体仍不可得；
  需引入含净高/转弯半径标注的图纸。
- 预计可判定口径提升：引入 1 张含净高+转弯半径标注的图纸，可打通 5 条
  （DIM-011/031/085/086/098），+5 规则。

## 6. 风险与边界

1. **误报风险**：净高/转弯半径标注解析需严格正则匹配（「净高」「转弯半径」前缀），
   避免把普通尺寸标注误判为净高。
2. **语义错配修复需谨慎**：DIM-011/085/098 从读 width 改为读 height，若图纸有
   width 但无 height，判定从「可能误判宽度」变为「跳过（无净高）」——更安全。
3. **DIM-108 复合规则**：宽度+净高取更严格，需明确「宽度 ≥4m AND 净高 ≥4m」语义。
