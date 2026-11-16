# 引入 3D 属性图纸实施方案（2026-11-16）

## 1. 目标

打通 6 条 3D 属性类未判定规则（DIM-011/031/085/086/098/108），这些规则判据载体
（净高/转弯半径）在 2D 图纸中当前不可得。DIM-030（无 rescue_area）、DIM-088/107
（消火栓/扶手高度，无标注实体）为样本覆盖限制，不在本方案范围。

## 2. 现状诊断

### 2.1 规则语义与 handler 错配（核心发现）

| 规则 | 语义 | 判据载体 | handler 现状 | 错配 |
|------|------|---------|-------------|------|
| DIM-011 | 消防车道净高 ≥4.0m（GB50016-7.1.8） | height | `_GENERIC_DIM_RULES` 读 **width** | **读错属性** |
| DIM-085 | 消防车道净高 ≥4.0m（GB50016-7.1.2） | height | 读 **width** | **读错属性** |
| DIM-098 | 消防车道净高 ≥4.0m（GB50016-7.1.1） | height | 读 **width** | **读错属性** |
| DIM-108 | 宽度+净高 ≥4.0m（GB50016-7.1.2） | width AND height | 读 **width** | **净高未判** |
| DIM-031 | 转弯半径 ≥9m（GB50016-7.1.3） | radius | 读 **width** | **读错属性** |
| DIM-086 | 转弯半径 ≥12m（GB50016-7.1.4） | radius | 读 **width** | **读错属性** |

**根因**：`_GENERIC_DIM_RULES`（atomic_functions.py 第 1056-1094 行）统一按
`(prop_key, unit, guards)` 读 width。但 DIM-011/085/098 语义是**净高**（height），
DIM-031/086 语义是**转弯半径**（radius）。handler 读错属性，即使图纸有净高/转弯
半径标注也无法正确判定。

### 2.2 判据载体缺失

road/fire_lane 实体无 `height`/`radius` 属性（实测 baa-file-5840029dbcb8.dwg 87 个
road 全部 width=None，bbox 为符号/标注）。净高/转弯半径需 CAD 标注解析注入。

### 2.3 无净高/转弯半径标注解析器

`text_attributes.py` 只有 `_parse_thickness_m`（厚度）和 `_parse_opening_code`（门窗编号），
无净高/转弯半径解析。

## 3. 实施步骤

### 步骤 1：新增净高/转弯半径标注解析器（text_attributes.py）

**文件**：`src/baa_engine/semantic_analyzer/text_attributes.py`

在 `_parse_opening_grade`（第 124 行）后新增两个解析函数：

```python
import re

# 净高标注：净高4.5m / H=4.5m / 净高4500 / 层高4.5m / 净空4.5米
_CLEAR_HEIGHT_PATTERN = re.compile(
    r"(?:净高|净空|层高|H\s*=|高度)\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(m|mm|M|MM|米)?"
)
# 转弯半径标注：转弯半径12m / R=12m / 半径12m / 转弯半径12000
_RADIUS_PATTERN = re.compile(
    r"(?:转弯半径|R\s*=|半径)\s*[=:]?\s*(\d+(?:\.\d+)?)\s*(m|mm|M|MM|米)?"
)

# 合理范围：净高 2.0~6.0m，转弯半径 3.0~30.0m
_CLEAR_HEIGHT_MIN_M, _CLEAR_HEIGHT_MAX_M = 2.0, 6.0
_RADIUS_MIN_M, _RADIUS_MAX_M = 3.0, 30.0

def _parse_clear_height_m(text: str) -> Optional[float]:
    """解析净高标注 → 米。无匹配或越界返回 None。"""
    if not text:
        return None
    m = _CLEAR_HEIGHT_PATTERN.search(text)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit in ("mm",):
        val = val / 1000.0
    if not (_CLEAR_HEIGHT_MIN_M <= val <= _CLEAR_HEIGHT_MAX_M):
        return None
    return val

def _parse_turning_radius_m(text: str) -> Optional[float]:
    """解析转弯半径标注 → 米。无匹配或越界返回 None。"""
    if not text:
        return None
    m = _RADIUS_PATTERN.search(text)
    if not m:
        return None
    val = float(m.group(1))
    unit = (m.group(2) or "").lower()
    if unit in ("mm",):
        val = val / 1000.0
    if not (_RADIUS_MIN_M <= val <= _RADIUS_MAX_M):
        return None
    return val
```

### 步骤 2：注入净高/转弯半径到就近车道实体（text_attributes.py）

在 `_inject_text_attributes`（第 196 行）中：

**2a. 预筛车道候选实体**（第 209-213 行附近新增）：

```python
# 车道候选：净高/转弯半径标注注入目标
lane_types = ("fire_lane", "road", "driveway", "access_road", "fire_access")
lane_ish = [e for e in entities if e.type in lane_types]
```

**2b. 构建车道网格**（第 261-263 行附近新增）：

```python
lane_grid = _build_ent_grid(lane_ish) if lane_ish else None
```

**2c. 注入分支**（第 336 行 `return entities` 前新增）：

```python
# 4) 净高标注 → 就近车道实体注入 height
clear_h = _parse_clear_height_m(text)
if clear_h is not None and lane_grid:
    ent = _grid_nearest(text_bbox, lane_grid, _TEXT_ATTR_MAX_DIST)
    if ent is not None:
        _inject_attr(ent, "height", clear_h, "text_clear_height")

# 5) 转弯半径标注 → 就近车道实体注入 radius
radius_m = _parse_turning_radius_m(text)
if radius_m is not None and lane_grid:
    ent = _grid_nearest(text_bbox, lane_grid, _TEXT_ATTR_MAX_DIST)
    if ent is not None:
        _inject_attr(ent, "radius", radius_m, "text_radius")
```

### 步骤 3：修复 handler 语义错配（atomic_functions.py）

**文件**：`src/baa_engine/atomic_functions.py`

**3a. 在 `_GENERIC_DIM_RULES` 分支（第 1095 行）前拦截净高/转弯半径规则**：

```python
# 净高规则：读 height（非 width）。DIM-011/085/098 语义是消防车道净高。
_CLEAR_HEIGHT_RULES = {"DIM-011", "DIM-085", "DIM-098"}
# 转弯半径规则：读 radius（非 width）。DIM-031/086 语义是消防车道转弯半径。
_RADIUS_RULES = {"DIM-031", "DIM-086"}

if func_id in _CLEAR_HEIGHT_RULES:
    val = props.get("height", 0.0)
    if val < 0.01:
        return None  # 无净高标注，跳过判定（不误判宽度）
    return val * 1000.0  # m → mm（阈值 4000mm 口径）

if func_id in _RADIUS_RULES:
    val = props.get("radius", 0.0)
    if val < 0.01:
        return None  # 无转弯半径标注，跳过判定
    return val * 1000.0  # m → mm（阈值 9000/12000mm 口径）
```

**3b. DIM-108（宽度+净高复合）**：保留 width 判定，净高部分在标注存在时叠加。
DIM-108 语义「宽度 ≥4m AND 净高 ≥4m」。handler 读 width（宽度），若实体有 height
且 height < 4m，返回 FAIL（净高不足）；否则按 width 判定。

```python
if func_id == "DIM-108":
    h = props.get("height", 0.0)
    if h >= 0.01 and h < 4.0:
        return h * 1000.0  # 净高不足 → 返回 <4000mm → FAIL
    # 否则回落到 width 判定（_GENERIC_DIM_RULES 的 DIM-108 分支）
```

### 步骤 4：构造含净高/转弯半径标注的合成图

**脚本**：`scripts/gen_synth_3d_attrs.py`（新建，模板参照 `scripts/gen_e2e_dxf.py`）

生成 `data/drawings/real/synth/synth_3d_clear_height.dxf`：

```python
import ezdxf
from pathlib import Path

def _make_clear_height_dxf(path: Path) -> None:
    """消防车道 + 净高标注合成图（DIM-011/085/098 验证）。"""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # 消防车道：狭长矩形（FIRE_LANE 图层）
    lane = [((0, 0), (20000, 0)), ((20000, 0), (20000, 4000)),
            ((20000, 4000), (0, 4000)), ((0, 4000), (0, 0))]
    for s, e in lane:
        msp.add_line(s, e, dxfattribs={"layer": "FIRE_LANE"})
    # 净高标注：4.5m（TEXT 图层，就近车道）
    t = msp.add_text("净高4.5m", height=300, dxfattribs={"layer": "TEXT"})
    t.dxf.insert = (1000, 2000)
    doc.saveas(str(path))
```

生成 `data/drawings/real/synth/synth_3d_turning_radius.dxf`（转弯半径 12m 标注，
DIM-031/086 验证）。

### 步骤 5：单元测试（test_engine.py）

**文件**：`src/tests/test_engine.py`

```python
# 净高/转弯半径标注解析
def test_parse_clear_height(self):
    from src.baa_engine.semantic_analyzer.text_attributes import _parse_clear_height_m
    assert _parse_clear_height_m("净高4.5m") == 4.5
    assert _parse_clear_height_m("H=4.5m") == 4.5
    assert _parse_clear_height_m("净高4500") == 4.5
    assert _parse_clear_height_m("普通尺寸") is None
    assert _parse_clear_height_m("净高10m") is None  # 越界

def test_parse_turning_radius(self):
    from src.baa_engine.semantic_analyzer.text_attributes import _parse_turning_radius_m
    assert _parse_turning_radius_m("转弯半径12m") == 12.0
    assert _parse_turning_radius_m("R=12m") == 12.0
    assert _parse_turning_radius_m("普通尺寸") is None

# DIM-011/085/098 净高 handler
def test_dim011_clear_height_pass(self, registry):
    r = registry.get("DIM-011").execute(
        {"id": "L1", "type": "fire_lane", "properties": {"height": 4.5}})
    assert r.result == "PASS"  # 4.5m ≥ 4.0m

def test_dim011_clear_height_fail(self, registry):
    r = registry.get("DIM-011").execute(
        {"id": "L2", "type": "fire_lane", "properties": {"height": 3.5}})
    assert r.result == "FAIL"  # 3.5m < 4.0m

def test_dim011_no_height_skip(self, registry):
    # 无净高标注（只有 width）→ 不判定，不误判宽度
    r = registry.get("DIM-011").execute(
        {"id": "L3", "type": "fire_lane", "properties": {"width": 4.5}})
    assert r is None

# DIM-031/086 转弯半径 handler
def test_dim031_radius_pass(self, registry):
    r = registry.get("DIM-031").execute(
        {"id": "L4", "type": "road", "properties": {"radius": 12.0}})
    assert r.result == "PASS"  # 12m ≥ 9m

def test_dim031_radius_fail(self, registry):
    r = registry.get("DIM-031").execute(
        {"id": "L5", "type": "road", "properties": {"radius": 8.0}})
    assert r.result == "FAIL"  # 8m < 9m
```

## 4. 验收标准

1. **单元测试**：`python -m pytest src/tests/test_engine.py -q`，新增测试全部通过。
2. **合成图验证**：`python scripts/fp_rate_audit.py`，确认 synth_3d_clear_height 的
   DIM-011/085/098 判定 PASS；synth_3d_turning_radius 的 DIM-031/086 判定 PASS。
3. **全量回归**：`python -m pytest src/tests -q`，3179+ 测试通过无回归。
4. **可判定口径**：引入 2 张合成图后，DIM-011/031/085/086/098 进入 evaluated，
   +5 规则。

## 5. 收益评估

- 修复 handler 语义错配后，DIM-011/085/098（净高）与 DIM-031/086（转弯半径）
  在含标注图纸上可判定。
- 引入 2 张合成图（净高 4.5m + 转弯半径 12m），预计打通 **5 条**（+5 规则）。
- 真实图纸（baa-file-5840029dbcb8.dwg 等）road 无净高/转弯半径标注，判据载体仍
  不可得；需引入含标注的真实图纸（消防车道剖面图/总平面图）才能提升真实样本覆盖。

## 6. 风险与边界

1. **误报风险**：净高/转弯半径标注解析需严格正则匹配（「净高」「转弯半径」前缀），
   避免把普通尺寸标注误判为净高。合理范围门禁（净高 2-6m、半径 3-30m）兜底。
2. **语义错配修复更安全**：DIM-011/085/098 从读 width 改为读 height，图纸有 width
   但无 height 时判定从「可能误判宽度」变为「跳过（无净高）」。
3. **DIM-108 复合规则**：宽度+净高取更严格（净高不足时优先 FAIL），需明确
   「宽度 ≥4m AND 净高 ≥4m」语义。
4. **`_inject_attr` 不覆盖既有值**：若实体已有 height（如门窗编号注入），净高标注
   不覆盖，避免冲突。
