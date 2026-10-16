# 把图框与表格区域排除在扫线法之外（P130）

## Summary

在 `room.py` 的扫线法入口 `_sweep_line_detect_rooms` 中，于墙线候选收集（`_collect_wall_lines`）之后、任何几何成面步骤之前，插入一个**几何后置过滤器**，识别：

1. **图例/符号表格的网格框线**（本例是 00582518a28e 图中 10×34 的规则单元格阵列）；
2. **`titleblock` 图层的图元**（复用 `LAYER_RULES` 中 `t == "titleblock"` 的 7 条规则）；
3. **图框边框**（titleblock 图层上的 INSERT / 长矩形边）。

把这些图元从墙线候选中剔除。

**预期收益**：00582518a28e 的 room 计数从"靠 `短边<2000mm` 过滤碰巧丢掉 672 个表格单元格"改为"**源头不产生**这 672 个伪影面"，room 仍为 9。这样做的意义是把"正确"从概率性过滤（靠阈值恰好卡住 6060×1366mm 的单元格）变成结构性排除（表格线根本不进扫线图）。

---

## Current State Analysis

### 调用链与接入点

`_sweep_line_detect_rooms`（[room.py:90](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L90-L122)）：

| 行 | 代码 | 说明 |
|---|---|---|
| L95 | `wall_prims = _collect_wall_lines(primitives)` | 图元级筛选，此时 `layer` 可用 |
| L96-97 | `if len(wall_prims) < 3: return []` | 保护 |
| L100 | `_extract_closed_polyline_rooms(wall_prims, self)` | LWPOLYLINE 直成面路径 |
| L101-105 | `if len(direct_rooms) >= 3:` → 提前返回 | 绕过后续所有步骤 |
| L108 | `_collect_wall_segments(wall_prims)` | 转 `_Seg`，**保留 layer** |
| L116 | `_axis_align_merge(segs)` | 投影合并 |
| L118 | `_sweep_and_filter(merged_segs, self)` | 成面 + 过滤链 |

**关键约束**：`_axis_align_merge` 在 [L545/L547](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L543-L549) 把 `_Seg` 的 layer 字段**硬编码为 `""`**：

```python
for lo, hi, y in h_merged:
    result.append((lo, y, hi, y, "", hi - lo))
for lo, hi, x in v_merged:
    result.append((x, lo, x, hi, "", hi - lo))
```

→ **任何基于 layer 的过滤必须发生在 `_collect_wall_lines` 之后、`_axis_align_merge` 之前。**

唯一接入点：**L95 与 L96 之间**（在 L95 之后立即插入过滤，再保留 L96 的长度保护）。这样：

- 图元级 layer 判据（titleblock）在此生效；
- 几何级表格/图框区域判据在此生效；
- L100 的 LWPOLYLINE 直成面路径同受保护（表格若有 LWPOLYLINE 边框也一并排除）；
- 图框区域判据可取 `primitives` 全集（含 INSERT），因此过滤器签名需要同时拿到 `wall_prims` 与 `primitives`。

### 现有黑名单为什么拦不住本例

[_collect_wall_lines](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L590-L677) 已有 `non_wall_layer_kw` 黑名单（L596-652），其中含 `"表"`、`"图框"`、`"TEL"`、`"轴"`、`"网格"` 等：

```python
if any(kw in layer for kw in non_wall_layer_kw):
    continue
```

但本例表格框线落在 **`A` 层（5 垂 + 34 水平）与 `G` 层（6 垂 + 2 水平）** 这类极短通用图层名上。`A` 在其他设计院的图纸中很可能就是墙体层，**不能**把 `A`/`G` 硬编码进黑名单 → 必须靠几何识别。

### 表格几何事实（00582518a28e，实测）

- 11 条垂直线（长 48597mm，间距 ≈ 6060mm）× 36 条水平线（长 61714mm，间距 ≈ 1366.5mm）→ 10 列 × 34 行单元格阵列；
- 单元格尺寸一律 6060×1366mm（宽仅 1.37m，属表格/图案伪影；真实房间不会尺寸一律）；
- 阵列 bbox：`x[1097, 62811]`、`y[138776, 187373]`（约 617×486mm，正好占 A1 图幅一侧）；
- 范围内 262–282 条文字，表头 `图`/`例`/`名`/`称` 各重复 5 次（5 个并列子表），数据行如 `J1 | 低区（市政）生活给水管 | 安全阀 | Y压力污水立管 | 双口消火栓`；
- 全图 7 个 INSERT 均在该表格区域**之外**；**零 HATCH 参与成面**。

### 可复用的既有资产

- **titleblock 规则**（[layer_rules.py:26](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/layer_rules.py#L26-L35) 的合并 dict `LAYER_RULES`，按**子串匹配**）。映射为 `"titleblock"` 的键恰好 7 个（[_layer_rules_p79.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/_layer_rules_p79.py#L49-L53) 与 L61/L122）：

  | 键 | 值 |
  |---|---|
  | `通-图框` | titleblock |
  | `通-图框-图签` | titleblock |
  | `通-图框-文字` | titleblock |
  | `通-图框-标题块` | titleblock |
  | `C-SHET` | titleblock |
  | `建.17.图框` | titleblock |
  | `建.17.图框文字` | titleblock |

  **注意**：`P-KX1` / `PP-COM` / `VDWG` / `BORDER`（同文件 L96-108）映射为 `"other"`，**不得**拿它们做硬排除。

- **几何工具**：[geometry.py](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/geometry.py#L9-L56) 提供 `compute_iou` / `union_bbox` / `min_edge_distance` / `is_inside`。
- **测试先例**：[test_engine.py:1223-1261](file:///d:/OpenClawData/BAA/src/tests/test_engine.py#L1223-L1261) 已用手工构造 `RawPrimitive` 的方式验证"非建筑图层不产生房间"，新测试仿此风格。

### 相关阈值常量（[room.py:340-352](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L340-L352)）

```python
_AXIS_TOL_DEG = 30.0
_AXIS_MERGE_TOL_MM = 200.0
_AXIS_MIN_LEN_MM = 500.0
_MIN_ROOM_AREA_MM2 = 5_000_000
_MAX_ROOM_AREA_MM2 = 2_000_000_000
_MIN_SHORT_EDGE_MM = 2000.0
_CENTER_DUP_TOL_MM = 2000.0
_MIN_AREA_TO_BBOX_RATIO = 0.3
```

---

## Proposed Changes

### 改动 1：`src/baa_engine/semantic_analyzer/room.py` — 顶部新增 import

在 L19（`from ..drawing_parser import RawPrimitive`）之后新增：

```python
from .layer_rules import LAYER_RULES
```

### 改动 2：接入点（L95 之后 / L96 之前）

原文（L95-97）：

```python
    wall_prims = _collect_wall_lines(primitives)
    if len(wall_prims) < 3:
        return []
```

改为：

```python
    wall_prims = _collect_wall_lines(primitives)
    if len(wall_prims) < 3:
        return []
    # P130: 排除图框与表格区域——必须在 _extract_closed_polyline_rooms /
    # _collect_wall_segments / _axis_align_merge 之前，此时 layer 尚未被清空。
    wall_prims = _exclude_table_and_frame_prims(wall_prims, primitives)
    if len(wall_prims) < 3:
        return []
```

**理由**：L96 的原保护保留不动（过滤前先短路，避免对空集合做几何运算），过滤后再补一次长度保护。

### 改动 3：新增 4 个函数（插在 `_collect_wall_lines` 之后，即 [L677](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L677) 之后）

#### 3.1 `_is_titleblock_layer(layer: str) -> bool`

```python
def _is_titleblock_layer(layer: str) -> bool:
    """图层是否映射为 titleblock（图框/图签/标题栏）。

    只取 LAYER_RULES 中值为 "titleblock" 的键；子串匹配与 classify 一致。
    """
    u = (layer or "").upper()
    if not u:
        return False
    for kw, t in LAYER_RULES.items():
        if t == "titleblock" and kw.upper() in u:
            return True
    return False
```

**设计理由**：独立判据、可单独单测；不复用 `_NON_ROOM_LAYER_KW`，也不并入 `non_wall_layer_kw`（后者是"已知非建筑"的宽泛黑名单，混入会削弱两者的可诊断性）。

#### 3.2 `_exclude_table_and_frame_prims(prims, all_prims) -> List[RawPrimitive]`

编排器：

```python
def _exclude_table_and_frame_prims(
    prims: List[RawPrimitive], all_prims: List[RawPrimitive]
) -> List[RawPrimitive]:
    """P130: 从墙线候选中剔除表格网格与图框区域内的图元。

    参数:
        prims:     _collect_wall_lines 的输出（墙线候选）
        all_prims: 解析出来的全量图元（用于取图框 INSERT 的 bbox）
    """
    segs = _collect_wall_segments(prims)
    regions = _detect_table_regions(segs) + _detect_frame_rects(all_prims, segs)
    if not regions:
        # 仍要执行 titleblock 图层级排除
        return [p for p in prims if not _is_titleblock_layer(p.layer or "")]

    kept: List[RawPrimitive] = []
    for p in prims:
        if _is_titleblock_layer(p.layer or ""):
            continue
        if _prim_within_regions(p, regions):
            continue
        kept.append(p)
    return kept
```

其中 `_prim_within_regions(prim, regions)` 为内部小工具：

```python
def _prim_within_regions(prim: RawPrimitive, regions: List[dict]) -> bool:
    """判断图元是否整体落在任一区域 bbox 内（含 _TABLE_REGION_PAD_MM 容差）。

    LINE: 两端点；LWPOLYLINE: 全部顶点。
    要求"全部点均在区域内"，避免误排跨越表格边界的墙线。
    """
    pts = _prim_endpoints(prim)
    if not pts:
        return False
    for r in regions:
        x0, y0 = r["x"], r["y"]
        x1, y1 = x0 + r["width"], y0 + r["height"]
        if all(
            x0 - _TABLE_REGION_PAD_MM <= px <= x1 + _TABLE_REGION_PAD_MM
            and y0 - _TABLE_REGION_PAD_MM <= py <= y1 + _TABLE_REGION_PAD_MM
            for px, py in pts
        ):
            return True
    return False


def _prim_endpoints(prim: RawPrimitive) -> List[Tuple[float, float]]:
    """取图元的关键点：LINE 取起终点；LWPOLYLINE 取全部顶点。"""
    if prim.dxf_type == "LINE":
        sp = prim.properties.get("start_point", {}) or {}
        ep = prim.properties.get("end_point", {}) or {}
        if not sp or not ep:
            return []
        return [(float(sp.get("x", 0.0)), float(sp.get("y", 0.0))),
                (float(ep.get("x", 0.0)), float(ep.get("y", 0.0)))]
    if prim.dxf_type == "LWPOLYLINE":
        pts = prim.properties.get("points", []) or []
        return [(float(p[0]), float(p[1])) for p in pts]
    return []
```

#### 3.3 `_detect_table_regions(segs) -> List[dict]`

表格识别算法（**主安全阀**是判据 6）：

```python
def _detect_table_regions(segs: List[_Seg]) -> List[dict]:
    """P130: 几何识别"规则网格表格"区域，返回 bbox 列表。

    判据（全部满足才判定为表格，宁可漏排不误排）：
      1. 近轴段分出水平族 H 与垂直族 V，各自 size >= _TABLE_MIN_LINES_PER_FAMILY
      2. 族内长度 CV <= _TABLE_LEN_CV_MAX（长度一律）
      3. 相邻线间距 CV <= _TABLE_GAP_CV_MAX（等距）
      4. 族内 >= _TABLE_MIN_LINE_COVER_RATIO 的线段长度 >= 0.9×区域对应边长（贯穿整区）
      5. 实际交点数 / (#H * #V) >= _TABLE_MIN_INTERSECTION_RATIO（网格密闭）
      6. 区域内"非成员长线段"总长占比 <= _TABLE_MAX_OUTSIDER_LEN_RATIO（安全阀：有跨区墙线则放弃）
      7. _TABLE_MIN_AREA_MM2 <= 区域面积 <= _TABLE_MAX_AREA_MM2
    """
```

实现要点：

- **角度分族**：按 `_TABLE_AXIS_TOL_DEG = 3.0°` 把线段判为 H（|dy| >= |dx| 且距水平 <= tol）或 V，其余丢弃；
- **长度聚类**：按相对容差 `_TABLE_LEN_TOL_REL = 0.05` 分桶（排序后线性扫描，桶内 max/min <= 1.05）；
- **组合枚举**：对每个 (H 桶, V 桶) 组合做判据 1–7；
- **间距 CV**：族内线段中心坐标排序后取相邻差，`CV = std/mean`；
- **交点数**：统计 H 段与 V 段实际相交（点落在线段范围内，容差 `_TABLE_REGION_PAD_MM`）的对数；
- **区域 bbox**：`min/max` 所有成员线段端点；
- **判据 6**：区域内不属于该 (H,V) 族、但长度 >= `0.5 × 区域较短边` 的线段，其总长 / 区域周长 <= 上限；
- 返回 `[{"x":, "y":, "width":, "height":}, ...]`。

**与轴网的区分**：轴网图层名已被 `non_wall_layer_kw`（含 `"轴"`/`"网格"`/`"轴网"`）拦掉；几何侧靠"双族贯穿整区 + `len_cv <= 5%`"——轴网虽等距但线数少、常只有单侧标注。

**与"成排相同房间模块"的区分**：房间水平墙会被门洞/T 接打断，达不到"90% 的线长度 >= 0.9×区域边长"；且一旦区域内存在跨区墙线，判据 6 直接放弃判定。

#### 3.4 `_detect_frame_rects(all_prims, segs) -> List[dict]`

```python
def _detect_frame_rects(
    all_prims: List[RawPrimitive], segs: List[_Seg]
) -> List[dict]:
    """P130: 识别图框边框区域（titleblock 图层上的 INSERT / 长矩形边）。

    说明：图框内部整幅面 84100×59400 = 4.998e9 mm² 已超 _MAX_ROOM_AREA_MM2
    (2e9) 被成面后的 gate0 剔除，因此本函数的主要价值是降低扫线开销、
    并为图框内的表格/标题栏子区域提供外层保护。保持简短（<30 行）。
    """
    rects: List[dict] = []
    for p in all_prims:
        if not _is_titleblock_layer(p.layer or ""):
            continue
        b = p.bbox or {}
        w, h = b.get("width", 0), b.get("height", 0)
        if w <= 0 or h <= 0:
            continue
        if max(w, h) < _FRAME_MIN_SIDE_MM:  # 只取足够大的外框
            continue
        rects.append({"x": b.get("x", 0.0), "y": b.get("y", 0.0),
                      "width": w, "height": h})
    return rects
```

`_FRAME_MIN_SIDE_MM = 50_000.0`（50m，图框尺度）。

### 改动 4：`_collect_wall_lines` 增加 titleblock 判据

[L669-670](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L669-L671) 之后、L672 墙层判据之前插入：

```python
        # 1. 明确非建筑图层：排除
        if any(kw in layer for kw in non_wall_layer_kw):
            continue
        # P130: titleblock 图层排除（独立判据，可单独单测）
        if _is_titleblock_layer(prim.layer or ""):
            continue
        # 2. 已知墙/结构图层：保留
        if any(kw in layer for kw in wall_layer_kw):
```

### 改动 5：新增阈值常量（插在 [L352](file:///d:/OpenClawData/BAA/src/baa_engine/semantic_analyzer/room.py#L352) 之后）

```python
# ── P130: 图框/表格区域排除 ──
_TABLE_AXIS_TOL_DEG = 3.0  # 判定近轴段的角度容差
_TABLE_LEN_TOL_REL = 0.05  # 同一族内线段长度相对容差
_TABLE_LEN_CV_MAX = 0.05  # 族内长度变异系数上限（长度一律）
_TABLE_GAP_CV_MAX = 0.15  # 相邻线间距变异系数上限（等距）
_TABLE_MIN_LINES_PER_FAMILY = 4  # 每族最少线段数
_TABLE_MIN_LINE_COVER_RATIO = 0.90  # 贯穿整区的线段占比下限
_TABLE_LINE_COVER_TOL = 0.90  # 线段长度 / 区域边长 下限
_TABLE_MIN_INTERSECTION_RATIO = 0.85  # 实际交点 / (H*V) 下限
_TABLE_MAX_OUTSIDER_LEN_RATIO = 0.05  # 非成员长线段总长 / 区域周长 上限（安全阀）
_TABLE_MIN_AREA_MM2 = 1_000_000  # 表格区域面积下限 1m²
_TABLE_MAX_AREA_MM2 = 10_000_000_000  # 表格区域面积上限 10000m²
_TABLE_REGION_PAD_MM = 200.0  # 区域边界容差（mm）
_FRAME_MIN_SIDE_MM = 50_000.0  # 图框最小边长（50m）
```

阈值取值理由：
- `_TABLE_LEN_CV_MAX = 0.05`、`_TABLE_GAP_CV_MAX = 0.15`：实测表格"长度一律、等距"非常规整（间距 ≈6060 / ≈1366.5，波动 <1%），放 5%/15% 仍有充分余量，同时能挡住手工绘制的成排房间；
- `_TABLE_MIN_INTERSECTION_RATIO = 0.85`：允许少量单元格因文字/引线遮挡而缺失交线；
- `_TABLE_MAX_OUTSIDER_LEN_RATIO = 0.05`：这是**防误排的核心安全阀**——只要区域内存在跨区墙线（总长占比 >5%），就放弃判定，宁可漏排；
- `_TABLE_MIN_AREA_MM2 = 1e6`：小于 1m² 的网格（如图例小图标）即使误判也无害，直接不处理以省开销；
- 区域面积上限 `1e10`：比 `_MAX_ROOM_AREA_MM2` 宽，因为表格区域本身不参与成面，只为划定排除范围。

### 改动 6：新增测试 `src/tests/test_p130_table_exclusion.py`

仿 [test_engine.py:1223-1261](file:///d:/OpenClawData/BAA/src/tests/test_engine.py#L1223-L1261) 风格手工构造 `RawPrimitive`（`RawPrimitive(dxf_type, layer, handle, bbox, properties)`，LINE 需 `properties["start_point"]/["end_point"]`）。

| 用例 | 构造 | 断言 |
|---|---|---|
| `test_detect_table_grid` | 5 垂 × 4 水平，线长贯穿、间距等距 | `_detect_table_regions(segs)` 返回 1 个区域 |
| `test_excludes_table_but_keeps_room` | 上表 + 一个 8000×6000 闭合房间（4 条墙线，另起图层） | `SemanticAnalyzer()._sweep_line_detect_rooms(prims)` 里 room 数 == 1，且表格线被 `_exclude_table_and_frame_prims` 剔除 |
| `test_keeps_rooms_in_a_row` | 3 个成排 3000×4000 房间，公共水平墙被门洞（2000mm 缺口）打断 | 未判为表格；`_exclude_table_and_frame_prims` 原样返回；解析出 room == 3 |
| `test_titleblock_layer_helper` | — | `_is_titleblock_layer("通-图框-图签") is True`；`("A") is False`；`("BORDER") is False`；`("P-KX1") is False` |
| `test_frame_insert_bbox_excluded` | titleblock 图层上一个 90000×60000 bbox 的 INSERT + 落在其内的 LINE | `_detect_frame_rects` 返回该区域；区域内 LINE 被剔除 |
| `test_no_regions_leaves_prims_unchanged` | 纯房间墙线，无表格/图框 | `_exclude_table_and_frame_prims` 返回原列表（长度相等） |

测试需 import：`from src.baa_engine.semantic_analyzer.room import (_detect_table_regions, _exclude_table_and_frame_prims, _is_titleblock_layer, _detect_frame_rects, _collect_wall_segments, _sweep_line_detect_rooms)` 与 `from src.baa_engine.semantic_analyzer import SemanticAnalyzer`、`from src.baa_engine.drawing_parser import RawPrimitive`。

---

## Assumptions & Decisions

用户已在澄清环节拍板三个决策，本计划严格遵循：

1. **识别策略** = 几何网格识别 + 复用 titleblock 规则（不引入新依赖、不改图层黑名单）；
2. **排除范围** = 表格 + titleblock 图层 + 图框边框（三者全部）；
3. **回归处理** = 先抽验、确认无真实房间被误排后再同步刷新基线。

其余决策：

- **不重构 `_collect_wall_lines`**。职责链变为：`_collect_wall_lines`（图元级筛选）→ `_exclude_table_and_frame_prims`（几何级 + layer 级）→ `_collect_wall_segments` → `_axis_align_merge` → `_sweep_and_filter`。这样改动局部化、可单测。
- **不把 `A` / `G` 等通用短图层名加入任何黑名单**（在其他设计院图纸中可能是墙体层，硬编码会导致大面积漏检）。
- **只取 `t == "titleblock"`** 的 7 条规则做硬排除，`P-KX1`/`PP-COM`/`VDWG`/`BORDER`（值为 `"other"`）不参与。
- **宁可漏排、不可误排**：判据 6（`_TABLE_MAX_OUTSIDER_LEN_RATIO`）与"区域面积上限"共同构成安全阀，任何不确定情形一律放弃判定。
- **已知残留风险（记录不修）**：L101 的 `direct_rooms >= 3` 提前返回分支会跳过本过滤。本例表格由 LINE 构成，不受影响；若未来出现由 LWPOLYLINE 构成的表格，需另议。

---

## Verification

按顺序执行（Windows PowerShell，用 `;` 不用 `&&`；本机用 conda python `D:\APPstore\miniconda3\python.exe`）：

1. **新增测试**：
   ```powershell
   D:\APPstore\miniconda3\python.exe -m pytest src/tests/test_p130_table_exclusion.py -q
   ```
   期望：6 个用例全绿。

2. **既有引擎测试（非回归）**：
   ```powershell
   D:\APPstore\miniconda3\python.exe -m pytest src/tests/test_engine.py -q
   ```
   期望：与改动前一致（已知 4 个 async 用例因本机缺 `pytest-asyncio` 失败，属环境性预存问题，需在报告中标注）。

3. **真实图纸基线**：
   ```powershell
   D:\APPstore\miniconda3\python.exe -m pytest -m real_drawing src/tests/test_real_drawings.py -q
   ```
   期望：8 passed。其中 00582518a28e 的 `room` 仍为 9（±30% 容差内），其余 12 类实体与基线逐项相等。

4. **定量核对（改动收益的直接证据）**：临时插桩统计 `_sweep_and_filter` 的原始面数。
   - 改动前：00582518a28e 原始面 **703**，其中 672 个被 `短边<2000mm` 剔除；
   - 改动后期望：原始面降到约 **31**（表格线不再进入扫线），存活仍为 9 room + 2 corridor。
   - 临时脚本用完必须用 `DeleteFile` 删除，并在报告中说明已确认清理。

5. **若有其他图纸 room 计数变化**：先人工/量化抽验（确认被排除的是表格/图框伪影而非真实房间），确认后同步刷新 [test_real_drawings.py](file:///d:/OpenClawData/BAA/src/tests/test_real_drawings.py#L85-L156) 的 `ENTITY_BASELINE` 对应条目，并在文件顶部 docstring 追加一条刷新记录。

---

## 回滚

改动集中在单个文件 `room.py`（新增 import、新增 1 处两行接入、新增 4 个函数、新增 1 处两行判据、新增一组常量）+ 1 个新测试文件。回滚只需删除新增测试文件并 `git checkout src/baa_engine/semantic_analyzer/room.py`。
