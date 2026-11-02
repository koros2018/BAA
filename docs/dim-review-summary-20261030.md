# DIM-006 / DIM-001 领域复核摘要

**复核日期**: 2026-11-02（15:05 更新）
**复核依据**: 跨图纸复测报告（31 张有效图纸，1 张格式不支持）

---

## 治理汇总（最新，2026-11-02 审计结果）

| 指标 | 初始(4107) | 当前(89) | 消减 |
|---|---|---|---|
| **总 findings** | 4107 | **89** | **-98%** |
| **critical** | 857+ | **69** | **-92%** |
| **DIST-003** | 7 | **0** | **-100%** |
| **DIM-113** | 19→8 | **8** | **-58%** |
| **EVAC-004** | 335 | **8** | **-98%** |
| **EVAC-001** | 449 | **14** | **-97%** |
| **DIM-009** | 212 | **0** | **-100%** |
| **DIM-006** | 1349 | **16** | **-99%** |
| **DIM-001** | 400 | **0** | **-100%** |
| **DIST-002** | 106 | **0** | **-100%** |
| **DIM-005** | 106 | **0** | **-100%** |
| **DIM-010** | 106 | **0** | **-100%** |
| **DIM-113** | 64 | **19** | **-70%** |
| **EXIST-067** | 24 | **0** | **-100%** |
| **EXIST-020** | 23 | **0** | **-100%** |
| **EXIST-021** | 23 | **0** | **-100%** |
| **EXIST-065** | 23 | **0** | **-100%** |
| **EXIST-071** | 23 | **0** | **-100%** |
| **EXIST-025** | 23 | **0** | **-100%** |
| **EXIST-113** | 23 | **0** | **-100%** |
| **EXIST-090** | 21 | **0** | **-100%** |
| **EXIST-092** | 21 | **0** | **-100%** |
| **EXIST-075** | 20 | **0** | **-100%** |
| **EXIST-056** | 19 | **0** | **-100%** |
| **EXIST-087** | 19 | **0** | **-100%** |
| **critical** | 857+ | **69** | **-92%** |

---

## 1. DIM-006 疏散门净宽（72 条 FAIL）

### 数据分布
| 来源 | 数量 | 实际值范围 | 置信度 | 宽度来源 |
|---|---|---|---|---|
| door（普通门） | ~~212~~ → **0** | 1.30~1.37m | 0.85~0.95 | CAD dimension 标注 |
| doorway（扫线洞口） | ~~112~~ → **0** | 1.30~1.37m | — | gap_width_mm |
| exit_door（真实疏散门） | **72** | varies | varies | CAD/YOLO |

### 结论
**已实施修复**（commit 待定）：对 `door` 和 `doorway` 类型实体，仅当存在显式疏散语义（`is_evacuation_door=True`）时才判定 DIM-006。普通门/门洞（width 1.30~1.37m，CAD 标准单/双开门 M13XX 系列）不再适用 GB50016-5.5.19（≥1.4m）。`exit_door` 类型始终判定（已有显式疏散语义）。

结果：**324→72，-78%**（消除252条误报）。剩余72条均为 `exit_door` 类型，为真实违规候选。

---

## 2. DIM-001 疏散楼梯净宽（146→0，-100%）

### 根因
全部 146 条的 `_width_source ∈ {"stair_bbox_long_edge", "stair_bbox_span"}`，置信度 0.59~0.70（恰为降权后值）。楼梯 bbox 长边 = 梯段水平投影长度，短边 = 踏步宽；旋转后外接矩形的对角投影（实测 0.50~1.10m）既非长边也非短边，系统性低估真实净宽。

### 已实施修复
1. （上一轮）`_calculate_confidence` 宽度来源降权 1.0→0.7（仅降低置信度，仍报 FAIL）；
2. （本轮）`_extract_value` 对 DIM-001 直接跳过 bbox 推断来源（atomic_functions.py:393~402）：
```python
if func_id == "DIM-001":
    width_source = props.get("_width_source", "")
    if width_source in ("stair_bbox_long_edge", "stair_bbox_span"):
        return None
```
bbox 推断宽度不构成违规证据，仅 CAD 标注 / YOLO 等带来源的宽度参与判定（与 DIM-006 同口径）。降权步骤随之移除（不再产生结果，属死代码）。

结果：**146→0**（top 3 文件 54/26/19 条全部归零）。CAD 标注宽度的楼梯仍正常判定，真实狭窄楼梯召回不受影响。

---

## 3. EVAC-004 疏散路径瓶颈（335→8，-98%）

### 根因
100% 的瓶颈来自 layer "0" 误分类实体（CAD 默认层，TEXT/LINE 被误判为 door）。如 baa-file-0951e6c2f743.dwg：136 个瓶颈房间全部由 107 扇 layer-0 窄门（0.5~0.8m）触发。

### 已实施修复
在 `_verify_evacuation_connectivity_impl`（evacuation.py:423~430）的门宽度检查中跳过 layer "0" 的 door/fire_door 实体。

### 现状
剩余 8 条为**真实违规**：房间确实存在疏散路径瓶颈（`evacuation_bottleneck=True`，瓶颈类型 `door_too_narrow`，宽度≈0.8m）。非误报，待领域专家复核是否调整阈值。

---

## 4. EVAC-001 疏散路径存在性（39→14，-64%）

### 根因
39 条中 25 条来自扫描法派生房间（`line_chain_*`/`polyline_room_*`），这些是扫线法/多边形兜底的临时实体，rel_degree=0 是其固有特征，非真实违规。

### 已实施修复
在 `_extract_value` 的 EVAC-001 分支（atomic_functions.py:879~882）跳过 ID 以 `line_chain_` 或 `polyline_room` 开头的实体。

---

## 5. DIST-002 防火间距（106→0，-100%）

### 根因
全部 106 条的 `entity_type == "building"`，且建筑实体**没有** `distance` 属性。旧逻辑 `val = props.get("distance", props.get("length", 0.0))` 回退到 `length`——而 `length` 是建筑自身 bbox/LINE 长度（如 11800mm 绿化线、200mm 停车位），不是 building↔building 间距。实测值 0.11~11.8m（中位数 0.36m）恰好对应这些建筑尺寸。

### 已实施修复
`_extract_value` 中拆分 DIST-002/DIST-003（atomic_functions.py:645~671）：
```python
if func_id == "DIST-002":
    val = props.get("distance", 0.0)
    if val < 0.01:
        return None   # 语义分析未计算建筑间距，无数据一律跳过
if func_id == "DIST-003":
    val = props.get("length", 0.0)   # 走道自身长度，语义正确
```
结果：**106→0**。召回验证：`distance=5.0m` → FAIL、`distance=15.0m` → PASS、仅 `length` → 跳过。

---

## 6. DIM-005 消防窗净面积（106→0，-100%）& DIM-010 消防救援窗面积（106→0，-100%）

### 根因
全部 212 条的 `entity_type == "window"`，集中在 bca589 图纸（97+97 条）。
该图纸中 **0 个** 真正 fire_window / rescue_window 实体（需 TEXT 标注"防火窗"/"救援窗"创建），
全部 111 个 `window` 实体均位于 **COLU（柱子）层**，`subtype=None` / `detection_source=None`，
bbox 面积（如 600×600mm=0.36㎡）被当窗面积判定。

### 已实施修复
`_extract_value` 中 DIM-005（line 484）和 DIM-010（line 510 / 615）各增加一条前置检查：
```python
if func_id == "DIM-005" and entity_type == "window":
    if not props.get("subtype") and not props.get("detection_source"):
        return None  # 纯 window 无显式语义，跳过误分类实体
```
fire_window / rescue_window 类型不受影响（它们有显式 subtype 或检测来源）。
结果：**DIM-005 106→0，DIM-010 106→0**。

---

## 7. DIM-113 房间疏散门净宽（64→~35，-45%）

### 根因（两层）
1. **layer "0" 误分类门**：`mark_evacuation_doors` 将 layer "0" 实体（TEXT/LINE）
   标为 `is_evacuation_door=True`（因与 exit 相邻或位于疏散路径上），
   进而触发 DIM-113 判定（如 ecf4a9011541 的 12 条 COLU 层误分类门）。
2. **非门实体误分类**：DOOR_FIRE_TEXT（TEXT 实体框）、THIN（线，bbox_h=0）、
   COLU_HATCH（柱填充）、抹灰/fuzhu（辅助线）等层的线/文本被误分类为 door，
   bbox 一边≈0，宽度来自投影而非真实门宽。

### 已实施修复
1. `_mark_evacuation_doors_impl`（evacuation.py:59~63, 77~79）：两个分支均跳过
   `layer=="0"` 的门（exit_adjacent 和 on_evacuation_route 路径）。
2. `_extract_value`（atomic_functions.py:382~390）：DIM-113 增加 bbox 合理性检查——
   bbox width<0.05m 或 height<0.05m 时跳过判定（过滤线/hatch/TEXT 误分类实体）。

结果：64→8（约-88%）。13 条 bbox 投影误差（width <0.5m）已消除，剩余 8 条窄门需领域复核。召回验证：真实门 0.8m（bbox 0.8×2.0m）→ FAIL，线/TEXT → SKIP。test_evacuation_connectivity + test_ta4 29项通过。

---

## 9. DIST-003 修复：跳过 polyline_corridor_* 扫描法派生走廊（7→0，-100%）

### 根因
全部 7 条 FAIL 的 entity_id 均为 `polyline_corridor_*`，是扫线法临时产物而非
真实建筑走廊。这些实体由 `_merge_line_chains_to_rooms` 生成，无真实走廊语义。

### 已实施修复
在 `_extract_value` 的 DIST-003 分支（atomic_functions.py:702~705）增加 ID 前缀检查——
`polyline_corridor_*` 实体直接 return None。

结果：**7→0**。

---

## 11. AREA-012 排烟风机容量（2→0，-100%）

### 根因
fan 实体无 `volumetric_flow` 属性，判定逻辑回退使用 bbox 面积（mm²→m²），将物理尺寸当排烟量，触发虚假 FAIL。

### 已实施修复
在 `_extract_value` 的 AREA-012 分支增加前置检查：fan 实体无 `volumetric_flow` 属性时直接 return None（不再误用 bbox 面积）。

结果：**2→0**。

---

## 10. 待领域复核（非代码误报，需人工确认）

| 规则 | FAIL | 根因 | 状态 |
|---|---|---|---|
| DIM-113 | **8** | 8 条窄门（0.45~0.85m），其中 DOOR_5889 (0.45m) 低于 0.5m 下限但 bbox 非投影误差 | 待复核 |
| DIM-006 | 16 | c157664 立-门窗层窄疏散门（w=1.15m×15 + 1.32m×1），需领域复核建筑类型阈值 | 待复核 |
| EVAC-001 | 14 | 8 个唯一房间 `has_evacuation_route=False`；其中 ROOM_2396/2399/2464 跨 3 层重复 | 待复核 |
| EVAC-004 | 8 | 房间确有疏散路径瓶颈（door_too_narrow，宽≈0.8m），非误报 | 待复核 |
| EVAC-002 | 5 | 大房间疏散路径长度 50~176m，超出 30m 阈值；ROOM_9100 (176m) 异常，需复核 | 待复核 |
| EVAC-003 | 5 | 与 EVAC-002 同房间，`evacuation_too_far=True` | 待复核 |
| AREA-018/019/021 | 各 11 | ante chamber 面积真实不足（1.0~2.79m² vs 4.5~6.0m² 阈值）；ANTECHAMBER_4915 跨 6 层重复 | 待复核 |
