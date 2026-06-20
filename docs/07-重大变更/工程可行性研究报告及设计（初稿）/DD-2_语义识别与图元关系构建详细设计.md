# DD-2：语义识别与图元关系构建——详细设计文档

> **所属阶段：** 工程设计（详细设计）
> **对应架构层：** 语义识别层（图纸解析层→核心推理层的桥梁）
> **编制日期：** 2026-06-09
> **批准依据：** Master批准（决策DD-01/DD-04/DD-06）
> **前提约束：** 零成本创业模式，基于规则+轻量模型，不做图神经网络

---

## 1. 设计概述

### 1.1 设计目标

将DD-4图纸解析管线的输出（原始图元+检测结果），转换为DD-1原子函数可理解的**结构化语义信息**。包括：图元分类归并、空间关系构建、语义属性提取。

**核心指标：**
- 图元语义归类准确率：**≥95%**（基于规则，不依赖ML）
- 空间关系提取准确率：**≥90%**（相邻/包含/连通判定）
- 尺寸标注语义化准确率：**≥98%**（标注→属性映射）
- 处理时间：**≤2秒/张**

### 1.2 参考来源

| 参考来源 | 贡献 | 复用程度 |
|---------|------|---------|
| 论文#5 (DoorDet, 93.5% mAP@0.5) | 门类图元语义子分类方法 | 🟢 完全复用 |
| 论文#14 (GLSP, 87% mAP) | GNN线段解析→图元关系构建 | 🟡 规则简化（不做GNN） |
| 参考1论文4.3.3 (注意力机制) | 关键区域聚焦思路→规则化语义提取 | 🟡 规则化适配 |
| 现有TECH_PLAN.md | ezdxf解析+图层规则 | 🟢 已有实现 |
| DD-4 图纸解析管线 | 原始图元+检测结果输入 | 🟢 接口对接 |
| DD-1 原子函数库 | 结构化语义数据输出目标 | 🟢 接口对接 |

---

## 2. 架构定位

### 2.1 在整体管线中的位置

```
DD-4 图纸解析管线
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  DD-2：语义识别与图元关系构建 ★ 本文件                  │
│                                                        │
│  Step 1: 图元分类归并                                    │
│  ├── 图层规则归类（已知图层名→语义类型）                   │
│  └── 几何特征辅助归类（大小/形状→类型细分）                │
│                                                        │
│  Step 2: 空间关系构建                                    │
│  ├── 相邻关系（距离<阈值→相邻）                          │
│  ├── 包含关系（多边形内部判定→包含）                      │
│  └── 连通关系（门洞/走道→连通）                          │
│                                                        │
│  Step 3: 尺寸标注语义化                                  │
│  ├── 标注→属性绑定（哪个标注对应哪个图元）                 │
│  └── 属性提取（宽度/高度/面积/角度）                      │
│                                                        │
│  Step 4: 结构化语义输出                                   │
│  └── 图元清单 + 关系图 + 属性表 → JSON                   │
└──────────────────────────────────────────────────────┘
    │
    ▼
DD-1 原子函数判定
```

### 2.2 输入输出规范

| 维度 | 输入（来自DD-4） | 输出（给DD-1） |
|------|----------------|---------------|
| 图元 | `RawPrimitive[]`（类别ID+边界框+置信度） | `SemanticEntity[]`（语义类型+属性+ID） |
| 关系 | 无（散列图元） | `SpatialGraph`（相邻/包含/连通边） |
| 属性 | `Dimension[]`（原始标注值+位置） | `AttributeMap`（实体→属性键值对） |
| 格式 | Python dict | JSON Schema（详见第6节） |

---

## 3. Step 1：图元分类归并

### 3.1 图层规则表

基于常见设计院图层命名约定，建立规则映射表：

| 图层关键词 | 语义类型 | 对应DD-1图元类别 | 优先级 |
|-----------|---------|-----------------|:-----:|
| `WALL`, `墙体`, `墙`, `W` | `wall` | C01 墙体 | P0 |
| `DOOR`, `门`, `M`, `D` | `door` | C02 门 | P0 |
| `WINDOW`, `窗`, `C`, `WIND` | `window` | C03 窗 | P0 |
| `STAIR`, `楼梯`, `ST`, `STAIRS` | `stair` | C04 楼梯 | P0 |
| `CORRIDOR`, `走道`, `走廊` | `corridor` | C05 疏散走道 | P0 |
| `FIRE_ZONE`, `防火分区`, `FZ` | `fire_zone` | C06 防火分区 | P1 |
| `DIM`, `标注`, `尺寸`, `DIMENSION` | `dimension` | C07 尺寸标注 | P0 |
| `EXIT`, `出口`, `安全出口` | `exit` | C08 安全出口 | P0 |
| `FIRE_DOOR`, `防火门`, `FD` | `fire_door` | C09 防火门 | P1 |
| `FIRE_ELEV`, `消防电梯`, `FE` | `fire_elevator` | C10 消防电梯 | P1 |

### 3.2 图层未匹配时的兜底策略

当图元所在图层名不在规则表内时，按几何特征归类：

```python
def classify_by_geometry(primitive: RawPrimitive) -> SemanticType:
    """基于几何特征进行语义归类"""
    shape = detect_shape(primitive)  # 矩形/圆形/多边形/折线
    
    if shape == 'rectangle':
        area = primitive.bbox.area
        if area > 50000:     # 大矩形 → 墙体
            return 'wall'
        elif area > 5000:    # 中矩形 → 门/窗
            return classify_door_window(primitive)
        else:                 # 小矩形 → 标注
            return 'dimension'
    elif shape == 'line':
        if primitive.length > 1000:  # 长线 → 墙线
            return 'wall'
        else:
            return 'corridor'
    elif shape == 'circle':
        return 'stair'       # 圆形 → 楼梯（螺旋梯）
    elif shape == 'polyline':
        return 'fire_zone'   # 闭合多段线 → 防火分区
    else:
        return 'unknown'
```

### 3.3 门类子分类（论文#5 DoorDet方法）

```python
def classify_door(primitive: RawPrimitive, context: DrawingContext) -> DoorType:
    """基于论文#5的DoorDet方法，多类门检测"""
    # 方法A：图层关键词
    layer_lower = primitive.layer.lower()
    if 'fire' in layer_lower or '防火' in layer_lower:
        return 'fire_door'    # 防火门
    if 'roll' in layer_lower or '卷帘' in layer_lower:
        return 'rolling_door' # 卷帘门
    
    # 方法B：上下文特征
    door_width = primitive.dimensions.get('width', 0)
    adjacent_walls = find_adjacent_walls(primitive, context)
    wall_thickness = get_wall_thickness(adjacent_walls)
    
    if door_width > 2000 and wall_thickness > 200:
        return 'fire_door'    # 宽门+厚墙 → 防火门
    elif door_width > 1500:
        return 'double_door'  # 双开门
    else:
        return 'single_door'  # 单开门
```

### 3.4 图元归并（合并重复识别）

```python
def merge_primitives(primitives: List[RawPrimitive]) -> List[SemanticEntity]:
    """合并重叠/相邻的同类图元为一个语义实体"""
    merged = []
    sorted_prims = sorted(primitives, key=lambda p: p.confidence, reverse=True)
    
    used = set()
    for i, prim in enumerate(sorted_prims):
        if i in used:
            continue
        
        # 找同类型+重叠的图元
        cluster = [i]
        for j in range(i + 1, len(sorted_prims)):
            if j in used:
                continue
            if prim.category == sorted_prims[j].category:
                if compute_iou(prim.bbox, sorted_prims[j].bbox) > 0.5:
                    cluster.append(j)
                    used.add(j)
        
        # 合并为一个语义实体
        merged.append(SemanticEntity(
            id=f"{prim.category}_{len(merged):03d}",
            type=prim.category,
            bbox=union_bbox([sorted_prims[k].bbox for k in cluster]),
            confidence=max(sorted_prims[k].confidence for k in cluster),
            source='merged' if len(cluster) > 1 else 'single'
        ))
        used.add(i)
    
    return merged
```

---

## 4. Step 2：空间关系构建

### 4.1 三种空间关系

| 关系类型 | 定义 | 判定方法 | 示例 |
|---------|------|---------|------|
| **相邻(adjacent)** | 两个图元距离<阈值 | 边界距离计算 | 墙与门相邻 |
| **包含(contains)** | 图元A完全在图元B内部 | 多边形内部判定 | 门在墙内 |
| **连通(connects_to)** | 两个空间通过门洞/走道连通 | 拓扑路径分析 | 楼梯间→走道→出口 |

### 4.2 相邻关系判定

```python
def compute_adjacency(entities: List[SemanticEntity], threshold: float = 50) -> List[Relation]:
    """计算相邻关系（边界距离<阈值）"""
    relations = []
    for i, a in enumerate(entities):
        for j, b in enumerate(entities):
            if i >= j:
                continue
            distance = min_edge_distance(a.bbox, b.bbox)
            if distance < threshold:
                relations.append(Relation(
                    source_id=a.id,
                    target_id=b.id,
                    type='adjacent',
                    distance=distance,
                    confidence=1.0 - distance / threshold
                ))
    return relations
```

### 4.3 包含关系判定

```python
def compute_containment(entities: List[SemanticEntity]) -> List[Relation]:
    """计算包含关系（墙体包含门/窗）"""
    relations = []
    walls = [e for e in entities if e.type == 'wall']
    openings = [e for e in entities if e.type in ('door', 'window', 'fire_door')]
    
    for wall in walls:
        for opening in openings:
            if is_inside(opening.bbox, wall.bbox):
                relations.append(Relation(
                    source_id=wall.id,
                    target_id=opening.id,
                    type='contains',
                    distance=0,
                    confidence=0.95
                ))
    return relations
```

### 4.4 连通关系判定

```python
def compute_connectivity(entities: List[SemanticEntity]) -> List[Relation]:
    """计算连通关系（通过门洞/走道连接的两个空间）"""
    relations = []
    # 方法A：通过门连接（门两侧的空间）
    doors = [e for e in entities if e.type in ('door', 'fire_door')]
    rooms = [e for e in entities if e.type in ('room', 'stair', 'corridor')]
    
    for door in doors:
        adjacent_rooms = find_adjacent_rooms(door, rooms)
        if len(adjacent_rooms) >= 2:
            relations.append(Relation(
                source_id=adjacent_rooms[0].id,
                target_id=adjacent_rooms[1].id,
                type='connects_to',
                via=door.id,
                confidence=0.9
            ))
    
    # 方法B：走道连通（同一走道连接多个空间）
    corridors = [e for e in entities if e.type == 'corridor']
    for corr in corridors:
        connected_rooms = find_rooms_along_corridor(corr, rooms)
        for i, r1 in enumerate(connected_rooms):
            for r2 in connected_rooms[i+1:]:
                relations.append(Relation(
                    source_id=r1.id,
                    target_id=r2.id,
                    type='connects_to',
                    via=corr.id,
                    confidence=0.85
                ))
    
    return relations
```

---

## 5. Step 3：尺寸标注语义化

### 5.1 标注→图元绑定

```python
def bind_dimensions_to_entities(
    dimensions: List[Dimension],
    entities: List[SemanticEntity]
) -> Dict[str, AttributeMap]:
    """将尺寸标注绑定到最近的图元实体"""
    bindings = {}
    
    for dim in dimensions:
        # 找到距离最近的图元
        nearest = None
        nearest_dist = float('inf')
        
        for entity in entities:
            dist = distance(dim.position, entity.bbox.center)
            if dist < nearest_dist and dist < 500:  # 最大绑定距离
                nearest = entity
                nearest_dist = dist
        
        if nearest:
            if nearest.id not in bindings:
                bindings[nearest.id] = {}
            
            # 根据标注方向推断属性名
            attr_name = infer_attribute_name(dim, nearest)
            bindings[nearest.id][attr_name] = dim.measurement
    
    return bindings
```

### 5.2 属性推断规则

| 图元类型 | 标注方向 | 属性名 | 单位 |
|---------|---------|--------|------|
| 墙体 | 水平 | `width` | mm |
| 墙体 | 垂直 | `height` | mm |
| 门 | 水平 | `clear_width` | mm |
| 窗 | 水平 | `width` | mm |
| 窗 | 垂直 | `height` | mm |
| 楼梯 | 水平 | `step_width` | mm |
| 楼梯 | 垂直 | `rise_height` | mm |
| 走道 | 水平 | `clear_width` | mm |
| 防火分区 | 区域标注 | `area` | ㎡ |
| 疏散距离 | 折线标注 | `travel_distance` | m |

### 5.3 属性提取结果示例

```json
{
  "entities": {
    "WALL_001": {
      "width": 200,
      "height": 3600,
      "material": "concrete"
    },
    "DOOR_003": {
      "clear_width": 1050,
      "type": "fire_door",
      "fire_rating": "甲"
    },
    "STAIR_002": {
      "step_width": 1300,
      "rise_height": 150,
      "flight_count": 2
    },
    "FIRE_ZONE_001": {
      "area": 2200.5,
      "fire_resistance": "2h"
    }
  }
}
```

---

## 6. 结构化语义输出（JSON Schema）

### 6.1 输出格式定义

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["drawing_id", "entities", "relations", "attributes", "metadata"],
  "properties": {
    "drawing_id": {
      "type": "string",
      "description": "图纸唯一标识"
    },
    "entities": {
      "type": "array",
      "description": "语义图元列表",
      "items": {
        "type": "object",
        "required": ["id", "type", "bbox"],
        "properties": {
          "id": {"type": "string", "example": "WALL_001"},
          "type": {"type": "string", "enum": ["wall", "door", "window", "stair", 
                   "corridor", "fire_zone", "dimension", "exit", "fire_door", "fire_elevator"]},
          "subtype": {"type": "string", "description": "子类型（如fire_door/single_door）"},
          "bbox": {
            "type": "object",
            "properties": {
              "x": {"type": "number"},
              "y": {"type": "number"},
              "width": {"type": "number"},
              "height": {"type": "number"}
            }
          },
          "layer": {"type": "string"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1},
          "source": {"type": "string", "enum": ["detection", "rule", "merged", "manual"]}
        }
      }
    },
    "relations": {
      "type": "array",
      "description": "空间关系列表",
      "items": {
        "type": "object",
        "required": ["source_id", "target_id", "type"],
        "properties": {
          "source_id": {"type": "string"},
          "target_id": {"type": "string"},
          "type": {"type": "string", "enum": ["adjacent", "contains", "connects_to"]},
          "distance": {"type": "number"},
          "via": {"type": "string", "description": "连通中介（如门ID）"},
          "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        }
      }
    },
    "attributes": {
      "type": "object",
      "description": "图元属性（entity_id→属性键值对）",
      "additionalProperties": {
        "type": "object",
        "additionalProperties": {
          "type": ["number", "string"]
        }
      }
    },
    "metadata": {
      "type": "object",
      "properties": {
        "processing_time_ms": {"type": "number"},
        "entity_count": {"type": "integer"},
        "relation_count": {"type": "integer"},
        "software_version": {"type": "string"}
      }
    }
  }
}
```

### 6.2 输出示例

```json
{
  "drawing_id": "DWG-2026-001",
  "entities": [
    {"id": "WALL_001", "type": "wall", "bbox": {"x": 0, "y": 0, "width": 10000, "height": 200}, "layer": "A-WALL", "confidence": 0.95},
    {"id": "DOOR_001", "type": "door", "subtype": "fire_door", "bbox": {"x": 3000, "y": 0, "width": 1500, "height": 200}, "layer": "A-DOOR-FIRE", "confidence": 0.88},
    {"id": "STAIR_001", "type": "stair", "bbox": {"x": 5000, "y": 500, "width": 2500, "height": 5000}, "layer": "A-STAIR", "confidence": 0.85},
    {"id": "EXIT_001", "type": "exit", "bbox": {"x": 8000, "y": 6000, "width": 500, "height": 500}, "layer": "A-EXIT", "confidence": 0.92}
  ],
  "relations": [
    {"source_id": "WALL_001", "target_id": "DOOR_001", "type": "contains", "distance": 0, "confidence": 0.95},
    {"source_id": "STAIR_001", "target_id": "EXIT_001", "type": "connects_to", "via": "CORR_001", "confidence": 0.85}
  ],
  "attributes": {
    "DOOR_001": {"clear_width": 1050, "fire_rating": "甲"},
    "STAIR_001": {"step_width": 1300, "rise_height": 150}
  },
  "metadata": {
    "processing_time_ms": 1250,
    "entity_count": 4,
    "relation_count": 2,
    "software_version": "BAA-0.1.0"
  }
}
```

---

## 7. 与DD-1的接口规范

| DD-2输出字段 | DD-1输入 | 对应原子函数参数 |
|-------------|---------|----------------|
| `entities[].type` | `entity_type` | 判定目标类型 |
| `entities[].id` | `entity_id` | 判定目标ID |
| `attributes[entity_id][property]` | `extracted_value` | 属性值 |
| `relations[]` | `spatial_context` | 关系判定上下文 |
| `metadata.processing_time_ms` | — | 性能统计 |

---

## 8. 交付物清单

| 交付物 | 格式 | 说明 |
|--------|------|------|
| `semantic_classifier.py` | Python | Step 1 图元分类归并（规则表+几何兜底） |
| `spatial_graph.py` | Python | Step 2 空间关系构建（相邻/包含/连通） |
| `dimension_binder.py` | Python | Step 3 尺寸标注语义化 |
| `semantic_schema.json` | JSON Schema | 结构化语义输出格式 |
| `semantic_pipeline.py` | Python | 管线调度入口 |

---

*编制：司军（AI业务助理）*
*日期：2026-06-09*
*参考论文#5 (DoorDet门分类) + #14 (GLSP关系构建，规则简化版)*
*接口对接DD-4（输入） + DD-1（输出）*