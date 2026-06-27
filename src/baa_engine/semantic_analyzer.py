"""
BAA 语义识别引擎 - 图元分类 + 空间关系构建（规则版）
"""
from typing import List, Dict, Any, Optional, Tuple
from .drawing_parser import RawPrimitive


# ── 图层规则表 ────────────────────────────────────────────

# 短关键字（单字母/2字母）使用全词匹配（前后是_或边界），防止误匹配
# 例如 "D" 不匹配 "DIM"、"DIMENSION"、"DWG"、"DOOR"
LAYER_RULES = {
    "WALL": "wall", "墙体": "wall", "墙": "wall",
    "DOOR": "door", "门": "door",
    "WINDOW": "window", "窗": "window", "WIND": "window",
    "STAIR": "stair", "楼梯": "stair", "STAIRS": "stair",
    "CORRIDOR": "corridor", "走道": "corridor", "走廊": "corridor",
    "FIRE_ZONE": "fire_zone", "防火分区": "fire_zone",
    "DIM": "dimension", "标注": "dimension", "尺寸": "dimension",
    "DIMENSION": "dimension",
    "EXIT": "exit", "出口": "exit", "安全出口": "exit",
    "FIRE_DOOR": "fire_door", "防火门": "fire_door",
    "FIRE_ELEV": "fire_elevator", "消防电梯": "fire_elevator",
    "SB": "door",  # 水消防设备层门标记
}

# 短关键字（单字母/2字母）使用全词匹配
SHORT_LAYER_RULES = {
    "W": "wall",
    "D": "door",
    "M": "door",
    "C": "window",
    "ST": "stair",
    "FZ": "fire_zone",
    "FD": "fire_door",
    "FE": "fire_elevator",
}


# ── 语义实体 ──────────────────────────────────────────────

class SemanticEntity:
    """语义化图元"""
    def __init__(self, entity_id: str, entity_type: str,
                 bbox: Dict[str, float], layer: str = "",
                 subtype: str = "", confidence: float = 1.0,
                 properties: Dict[str, Any] = None):
        self.id = entity_id
        self.type = entity_type
        self.bbox = bbox
        self.layer = layer
        self.subtype = subtype
        self.confidence = confidence
        self.properties = properties or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "subtype": self.subtype,
            "bbox": self.bbox,
            "layer": self.layer,
            "confidence": self.confidence,
            "properties": self.properties,
        }


class SpatialRelation:
    """空间关系"""
    def __init__(self, source_id: str, target_id: str,
                 rel_type: str, distance: float = 0,
                 via: str = "", confidence: float = 1.0):
        self.source_id = source_id
        self.target_id = target_id
        self.type = rel_type      # adjacent / contains / connects_to
        self.distance = distance
        self.via = via
        self.confidence = confidence


# ── 语义分析引擎 ──────────────────────────────────────────

class SemanticAnalyzer:
    """语义识别引擎（规则版，不做ML）"""

    ADJACENT_THRESHOLD = 50.0  # 相邻距离阈值(mm)

    def __init__(self):
        self._entity_counter = 0

    def analyze(self, primitives: List[RawPrimitive],
                dimensions: List[Dict] = None,
                max_entities: int = 1000,
                building_type: str = "civil") -> Dict[str, Any]:
        """
        执行语义分析

        参数:
            primitives: 原始图元列表
            dimensions: 尺寸标注列表
            max_entities: 最大处理实体数（超过则采样，防OOM）

        输出: 结构化语义数据（entities + relations + attributes）
        """
        self._entity_counter = 0

        # 采样限制，防止全量关系构建OOM
        if len(primitives) > max_entities:
            import random
            random.seed(42)
            primitives = random.sample(primitives, max_entities)

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)

        # Step 1.5: 走廊宽度推断（平行线聚类 + bbox 短边）
        entities = self._infer_corridor_widths(entities, primitives)

        # Step 1.6: door/fire_door 属性增强（宽度兜底 + 防火等级推断）
        for ent in entities:
            if ent.type in ("door", "fire_door", "exit_door"):
                # 宽度兜底：bbox短边推断
                if ent.properties.get("width", 0) < 0.3 and ent.properties.get("clear_width", 0) < 0.3:
                    bbox = ent.bbox
                    bw = bbox.get("width", 0)
                    bh = bbox.get("height", 0)
                    if bw > 0 and bh > 0:
                        w_mm = min(bw, bh)
                        w_m = w_mm * 0.001
                        if 0.3 < w_m < 3.0:
                            ent.properties["width"] = w_m
                            ent.properties["clear_width"] = w_m
                # 防火等级推断：从图层名和实体名推断
                if ent.type == "fire_door":
                    existing_rating = ent.properties.get("fire_rating", ent.properties.get("rating", 0))
                    if existing_rating < 0.5:
                        # 图层名包含关键字推断
                        layer_upper = (ent.layer or "").upper()
                        combined = layer_upper
                        if "甲" in combined or "A" in combined:
                            ent.properties["fire_rating"] = 3.0  # 甲级=3.0
                        elif "乙" in combined or "B" in combined:
                            ent.properties["fire_rating"] = 2.0  # 乙级=2.0
                        elif "丙" in combined or "C" in combined:
                            ent.properties["fire_rating"] = 1.0  # 丙级=1.0
                        else:
                            # 默认设为甲级（保守安全策略）
                            ent.properties["fire_rating"] = 3.0

        # Step 2: 空间关系构建（V2拓扑关系）
        relations = self._build_relations(entities)

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])

        # Step 4: 走廊拓扑网络（V2新增）
        corridor_topology = self.build_corridor_topology(entities, relations)

        # Step 5: 疏散路径分析（V2新增）
        evacuation_routes = self.analyze_evacuation_routes(entities, relations)

        # Step 5.5: 疏散路径结果注入到实体属性（EVAC原子函数用）
        route_by_room = {}
        for route in evacuation_routes:
            route_by_room[route["room_id"]] = route
        for ent in entities:
            if ent.id in route_by_room:
                r = route_by_room[ent.id]
                ent.properties["has_evacuation_route"] = r.get("has_route", False)
                if r.get("path_length") is not None:
                    ent.properties["evacuation_path_length"] = r["path_length"]
                ent.properties["evacuation_too_far"] = r.get("exceeds_max_distance", False)
            # 对未找到路径的实体（如走廊兜底），标记为无路径
            elif ent.type in ("room", "corridor"):
                if "has_evacuation_route" not in ent.properties:
                    ent.properties["has_evacuation_route"] = False
                    ent.properties["evacuation_too_far"] = True

        return {
            "entities": [e.to_dict() for e in entities],
            "relations": [self._rel_to_dict(r) for r in relations],
            "attributes": attributes,
            "building_type": building_type,
            "corridor_topology": corridor_topology,
            "evacuation_routes": evacuation_routes,
        }

    def _parse_meta_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
        """
        解析 META 图层的结构化实体元数据。
        格式: ENTITY:<type>|x:<x>|y:<y>|w:<w>|h:<h>|key:value|...
        用于合成图纸测试场景，跳过常规几何归并直接构建实体。
        """
        entities = []
        for prim in primitives:
            if prim.layer.upper() != "META":
                continue
            text = prim.properties.get("text", "")
            if not text.startswith("ENTITY:"):
                continue
            parts = text.split("|")
            if len(parts) < 5:
                continue
            # 解析类型
            etype = parts[0].replace("ENTITY:", "").strip()
            # 解析bbox和属性
            props = {}
            bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
            for part in parts[1:]:
                if ":" not in part:
                    continue
                k, v = part.split(":", 1)
                k = k.strip()
                v = v.strip()
                if k == "x":
                    bbox["x"] = float(v)
                elif k == "y":
                    bbox["y"] = float(v)
                elif k == "w":
                    bbox["width"] = float(v)
                elif k == "h":
                    bbox["height"] = float(v)
                else:
                    # 尝试转数字，失败保留字符串
                    try:
                        props[k] = float(v)
                    except ValueError:
                        props[k] = v

            self._entity_counter += 1
            entity = SemanticEntity(
                entity_id=f"{etype.upper()}_{self._entity_counter:03d}",
                entity_type=etype,
                bbox=bbox,
                layer="META",
                confidence=1.0,
                properties=props,
            )
            entities.append(entity)

        return entities

    def _classify_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
        """图元分类归并"""
        # 优先解析 META 图层（合成图纸结构化数据）
        meta_entities = self._parse_meta_entities(primitives)
        if meta_entities:
            return meta_entities

        entities = []

        for prim in primitives:
            # 图层规则匹配
            entity_type = self._classify_by_layer(prim.layer)
            if entity_type == "unknown":
                entity_type = self._classify_by_geometry(prim)

            if entity_type == "unknown":
                continue

            self._entity_counter += 1
            # 过滤 NaN properties
            cleaned_props = {}
            for pk, pv in prim.properties.items():
                if isinstance(pv, float):
                    import math
                    if not math.isnan(pv):
                        cleaned_props[pk] = pv
                else:
                    cleaned_props[pk] = pv
            entity = SemanticEntity(
                entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",
                entity_type=entity_type,
                bbox=prim.bbox,
                layer=prim.layer,
                confidence=0.9 if entity_type != "unknown" else 0.5,
                properties=cleaned_props,
            )
            entities.append(entity)

        # 归并同类重叠图元
        entities = self._merge_overlapping(entities)

        # 过滤过小的走廊实体（LINE 类型容易被误识别为走廊）
        # 走廊宽度 < 500mm 且 bbox 短边 < 500mm 的实体可能是微小图元误标
        filtered = []
        for e in entities:
            if e.type == "corridor":
                bb = e.bbox
                bw = bb.get("width", 0)
                bh = bb.get("height", 0)
                short_edge = min(bw, bh) if bw > 0 and bh > 0 else max(bw, bh)
                if short_edge < 500:  # 短边 < 500mm 不可能是走廊
                    continue
            filtered.append(e)
        entities = filtered

        return entities

    def _classify_by_layer(self, layer: str) -> str:
        """图层规则归类

        长关键字（≥3字符）：子串匹配
        短关键字（1-2字符）：全词匹配（前后是_或边界），防止误匹配
        """
        if not layer:
            return "unknown"
        layer_upper = layer.upper()

        # 长关键字（≥3字符）：子串匹配
        for keyword, entity_type in LAYER_RULES.items():
            if keyword in layer_upper:
                return entity_type

        # 短关键字（1-2字符）：全词匹配
        for keyword, entity_type in SHORT_LAYER_RULES.items():
            if keyword in layer_upper:
                # 检查全词边界
                idx = layer_upper.find(keyword)
                while idx >= 0:
                    pre_ok = (idx == 0 or layer_upper[idx-1] == '_')
                    post_ok = (idx + len(keyword) >= len(layer_upper) or layer_upper[idx+len(keyword)] == '_')
                    if pre_ok and post_ok:
                        return entity_type
                    idx = layer_upper.find(keyword, idx + 1)

        return "unknown"

    def _classify_by_geometry(self, prim: RawPrimitive) -> str:
        """几何特征兜底归类（V2深度升级版）
        
        新增规则：
        - 短 LINE 且靠近 DIMENSION 标注的 defpoint → door
        - 小面积闭合多边形（门打开轨迹）→ door
        - 靠近门的 ARC → door
        - 狭长闭合多边形 → corridor
        - 大尺寸 CIRCLE（>3000mm）→ stair
        """
        dxf_type = prim.dxf_type
        bbox = prim.bbox
        bw = bbox.get("width", 0)
        bh = bbox.get("height", 0)
        area = bw * bh
        props = prim.properties
        length = props.get("length", 0) or max(bw, bh)
        short_edge = min(bw, bh) if bw > 0 and bh > 0 else length

        if dxf_type == "LINE":
            if length > 2000:
                return "wall"
            # 中等长度 LINE（700~2000mm）：典型门宽范围 → door
            if 700 < length < 2000 and short_edge < 50:
                # 细长 LINE，宽度在典型门宽范围内
                return "door"
            # 短 LINE（50~700mm）可能是门的宽度线或小构件
            if 50 < length < 700 and short_edge < 5:
                return "door"
            return "corridor"

        if dxf_type in ("LWPOLYLINE", "POLYLINE"):
            pts_count = props.get("point_count", 0)
            if pts_count == 2:
                # 2 点 LWPOLYLINE：视为 LINE 等价
                if length > 2000:
                    return "wall"
                if 700 < length < 2000 and short_edge < 50:
                    return "door"
                if 50 < length < 700 and short_edge < 5:
                    return "door"
                return "corridor"
            
            # 闭合多边形判断
            is_closed = props.get("area", 0) > 0 or (pts_count >= 3)
            if is_closed:
                aspect_ratio = max(bw, bh) / max(short_edge, 1)
                if area > 50000:  # 大面积
                    if aspect_ratio > 5:
                        # 狭长大面积 → 走廊或墙体
                        if length > 3000:
                            return "wall"
                        return "corridor"
                    return "wall"
                elif area > 5000:
                    if aspect_ratio > 4:
                        # 狭长中等面积 → corridor
                        return "corridor"
                    return "room"
                else:
                    # 小面积闭合多边形（500~5000mm²）→ door 或 window
                    if aspect_ratio > 3:
                        # 狭长小面积 → 门的开合轨迹
                        return "door"
                    elif aspect_ratio < 1.5:
                        # 接近正方形的小面积 → column
                        return "column"
                    return "door"
            return "corridor"

        # ARC：门弧或窗
        if dxf_type == "ARC":
            radius = props.get("radius", 0)
            if 100 < radius < 2000:
                return "door"
            return "window"

        if dxf_type == "CIRCLE":
            radius = props.get("radius", 0)
            if radius > 3000:
                return "stair"
            elif radius > 1000:
                return "stair"
            elif radius > 300:
                return "column"
            return "column"

        if dxf_type == "TEXT":
            text = props.get("text", "")
            if not text:
                return "text"
            text_upper = text.upper()
            if "出口" in text or "EXIT" in text_upper:
                return "exit"
            if "楼梯" in text or "ST" in text_upper or "STAIR" in text_upper:
                return "stair"
            if "防火" in text or "FIRE" in text_upper:
                return "fire_door"
            return "text"

        # INSERT 块：尝试从块名推断
        if dxf_type == "INSERT":
            block_name = props.get("block_name", "").upper()
            if "DOOR" in block_name or "门" in block_name:
                return "door"
            if "WINDOW" in block_name or "窗" in block_name:
                return "window"
            if "STAIR" in block_name or "ST" in block_name:
                return "stair"
            if "COLUMN" in block_name or "柱" in block_name:
                return "column"
            return "wall"

        return "unknown"

    def _infer_corridor_widths(self, entities: List[SemanticEntity],
                              primitives: List[RawPrimitive] = None) -> List[SemanticEntity]:
        """从 bbox 短边和平行线聚类推断走廊/门的宽度（真实图纸适配）

        两层策略：
        1. 平行线聚类（primitives 可用时）：收集走廊图元，按方向分组，
           找平行线间距作为走廊宽度
        2. bbox 短边：对已有非零 bbox 的实体，短边*0.001 为宽度
        """
        import math
        from collections import defaultdict

        # 防御性过滤：修复 NaN bbox
        for ent in entities:
            bbox = ent.bbox
            for k in ('x', 'y', 'width', 'height'):
                v = bbox.get(k, 0)
                if isinstance(v, float) and math.isnan(v):
                    bbox[k] = 0.0

        # ── 策略1：平行线聚类宽度推断 ──
        if primitives:
            # 收集可能的走廊原始图元（LINE + 2点LWPOLYLINE）
            edge_candidates = []
            for p in primitives:
                bbox = p.bbox
                cx = bbox.get("x", 0) + bbox.get("width", 0) / 2
                cy = bbox.get("y", 0) + bbox.get("height", 0) / 2
                # 排除坐标偏移的图元
                if abs(cx) < 100 and abs(cy) < 100:
                    continue
                if abs(cx) > 1e7 or abs(cy) > 1e7:
                    continue
                bw = bbox.get("width", 0)
                bh = bbox.get("height", 0)
                span = max(bw, bh)
                if span < 100 or span > 100000:  # 0.1m~100m 合理范围
                    continue
                if p.dxf_type == "LINE":
                    angle = p.properties.get("angle", 0) % 180
                    if angle > 90: angle = 180 - angle
                    edge_candidates.append({
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,
                        "span": span, "angle": angle,
                    })
                elif p.dxf_type == "LWPOLYLINE" and p.properties.get("point_count", 0) == 2:
                    angle = 0 if bw > bh else 90
                    edge_candidates.append({
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,
                        "span": span, "angle": angle,
                    })

            if edge_candidates:
                # 按方向分组
                h_edges = [e for e in edge_candidates if e["angle"] < 30]
                v_edges = [e for e in edge_candidates if e["angle"] > 60]

                # 水平线：按cy排序，收集所有gap
                h_sorted = sorted(h_edges, key=lambda e: e["cy"])
                h_gaps = []
                for i in range(min(300, len(h_sorted))):
                    for j in range(i + 1, min(i + 100, len(h_sorted))):
                        gap = abs(h_sorted[i]["cy"] - h_sorted[j]["cy"])
                        if 500 < gap < 10000:
                            h_gaps.append({"gap": gap, "y1": h_sorted[i]["cy"], "y2": h_sorted[j]["cy"]})

                # 垂直线：按cx排序，收集所有gap
                v_sorted = sorted(v_edges, key=lambda e: e["cx"])
                v_gaps = []
                for i in range(min(300, len(v_sorted))):
                    for j in range(i + 1, min(i + 100, len(v_sorted))):
                        gap = abs(v_sorted[i]["cx"] - v_sorted[j]["cx"])
                        if 500 < gap < 10000:
                            v_gaps.append({"gap": gap, "x1": v_sorted[i]["cx"], "x2": v_sorted[j]["cx"]})

                # 空间分区聚类：按 y/x 坐标分桶，每个桶独立计算宽度
                all_gaps = h_gaps + v_gaps
                if all_gaps and len(all_gaps) > 10:
                    bucket_size = 100
                    buckets = defaultdict(list)
                    for g in all_gaps:
                        w = g["gap"]
                        bucket = round(w / bucket_size) * bucket_size
                        buckets[bucket].append(w)
                    sorted_buckets = sorted(buckets.items(), key=lambda x: -len(x[1]))
                    reasonable_buckets = [(b, v) for b, v in sorted_buckets if 800 < b < 3000]
                    
                    if not reasonable_buckets:
                        reasonable_buckets = [(b, v) for b, v in sorted_buckets if 600 < b < 3000]
                    
                    if reasonable_buckets:
                        # 取最众数的桶的均值作为走廊宽度（单位 mm → m）
                        most_common_bucket = reasonable_buckets[0]
                        inferred_width_mm = sum(most_common_bucket[1]) / len(most_common_bucket[1])
                        inferred_width_m = inferred_width_mm / 1000.0
                        
                        # 注入到走廊实体的 width 属性
                        for ent in entities:
                            if ent.type == "corridor":
                                current_w = ent.properties.get("width", 0)
                                if current_w < inferred_width_m:
                                    ent.properties["width"] = inferred_width_m
                                    ent.properties["clear_width"] = inferred_width_m
                                    ent.properties["_width_source"] = "parallel_line_clustering"
        
        # ── 策略1.5：door/window 宽度推断（V2增强）──
        for ent in entities:
            if ent.type in ("door", "window", "fire_door", "exit_door"):
                existing = ent.properties.get("width", 0)
                if existing > 0.5:
                    continue
                # 从 ARC 半径推断门宽度（门弧半径 ≈ 门宽度）
                radius = ent.properties.get("radius", 0)
                if radius > 100 and radius < 2000:
                    w_m = radius * 0.001  # mm → m
                    if 0.3 < w_m < 2.0:
                        ent.properties["width"] = w_m
                        ent.properties["clear_width"] = w_m
                # 从 bbox 短边推断
                bbox = ent.bbox
                bw = bbox.get("width", 0)
                bh = bbox.get("height", 0)
                if bw > 0 and bh > 0:
                    w_mm = min(bw, bh)
                    w_m = w_mm * 0.001
                    if 0.3 < w_m < 2.0 and ent.properties.get("width", 0) < w_m:
                        ent.properties["width"] = w_m
                        ent.properties["clear_width"] = w_m
                # LINE 类型（短边≈0）：用长边作为宽度
                if ent.properties.get("width", 0) < 0.3:
                    span_mm = max(bw, bh)
                    if 300 < span_mm < 2000:  # 300mm~2m
                        w_m = span_mm * 0.001
                        ent.properties["width"] = w_m
                        ent.properties["clear_width"] = w_m

        # ── 策略2：bbox 短边推断（覆盖所有类型） ──
        for ent in entities:
            if ent.type not in ("corridor", "door", "window", "room", "wall"):
                continue
            bbox = ent.bbox
            bw = bbox.get("width", 0)
            bh = bbox.get("height", 0)

            if bw == 0 and bh == 0:
                continue

            # bbox 两边非零 → 短边为宽度（mm→m），长边为 length
            if bw > 0 and bh > 0:
                w_mm = min(bw, bh)
                w_m = w_mm * 0.001
                if not math.isnan(w_m) and w_m > 0.01 and w_m < 10:
                    current_w = ent.properties.get("width", 0)
                    if current_w < w_m:
                        ent.properties["width"] = w_m
                        ent.properties["clear_width"] = w_m
                l_mm = max(bw, bh)
                if l_mm > 0:
                    ent.properties["length"] = l_mm * 0.001
                continue

            # bbox 只有一边非零（LINE / 2 点 LWPOLYLINE）
            span_mm = max(bw, bh)
            if span_mm > 0:
                span_m = span_mm * 0.001
                if not math.isnan(span_m) and span_m > 0.05:
                    ent.properties["length"] = span_m
                    # 对 corridor/room：bbox短边≈宽度
                    if ent.type in ("corridor", "room", "door", "fire_door", "exit_door"):
                        short_mm = min(bw, bh) if bw > 0 and bh > 0 else 0
                        if short_mm > 0:
                            short_m = short_mm * 0.001
                            current_w = ent.properties.get("width", 0)
                            if current_w < 0.01 and 0.05 < short_m < 3.0:
                                ent.properties["width"] = short_m
                                ent.properties["clear_width"] = short_m

        return entities

    def _merge_overlapping(self, entities: List[SemanticEntity]) -> List[SemanticEntity]:
        """合并重叠/相邻的同类图元"""
        if len(entities) < 2:
            return entities

        merged = []
        used = set()

        for i, a in enumerate(entities):
            if i in used:
                continue

            cluster = [a]
            used.add(i)

            for j, b in enumerate(entities):
                if j in used:
                    continue
                if a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5:
                    cluster.append(b)
                    used.add(j)

            if len(cluster) > 1:
                # 合并边界框
                merged_bbox = self._union_bbox([e.bbox for e in cluster])
                merged.append(SemanticEntity(
                    entity_id=a.id,
                    entity_type=a.type,
                    bbox=merged_bbox,
                    layer=a.layer,
                    confidence=max(e.confidence for e in cluster),
                    properties=a.properties,
                ))
            else:
                merged.append(a)

        return merged

    def _build_relations(self, entities: List[SemanticEntity]) -> List[SpatialRelation]:
        """构建空间关系（V2深度升级版）
        
        包括：
        - 相邻关系（相邻距离阈值，>500实体用空间哈希加速）
        - 墙体-门窗拓扑关系（精确匹配门在墙上的位置）
        - 走廊连通关系（门连接走廊与房间）
        - 包含关系（房间包含设备）
        """
        relations = []

        # ── 1. 相邻关系（空间哈希加速）──
        CELL_SIZE = 100.0  # mm
        # 空间哈希网格
        grid: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}
        for idx, e in enumerate(entities):
            bx = e.bbox.get("x", 0)
            by = e.bbox.get("y", 0)
            bw = e.bbox.get("width", 0)
            bh = e.bbox.get("height", 0)
            # 实体占据的网格范围
            x1_cell = int(bx / CELL_SIZE)
            x2_cell = int((bx + bw) / CELL_SIZE)
            y1_cell = int(by / CELL_SIZE)
            y2_cell = int((by + bh) / CELL_SIZE)
            for gx in range(x1_cell, x2_cell + 1):
                for gy in range(y1_cell, y2_cell + 1):
                    grid.setdefault((gx, gy), []).append((idx, e))
        
        # 只比较同一或相邻网格的实体
        compared = set()
        for idx_a, a in enumerate(entities):
            bx = a.bbox.get("x", 0)
            by = a.bbox.get("y", 0)
            bw = a.bbox.get("width", 0)
            bh = a.bbox.get("height", 0)
            x1_cell = int(bx / CELL_SIZE)
            x2_cell = int((bx + bw) / CELL_SIZE)
            y1_cell = int(by / CELL_SIZE)
            y2_cell = int((by + bh) / CELL_SIZE)
            for gx in range(x1_cell - 1, x2_cell + 2):
                for gy in range(y1_cell - 1, y2_cell + 2):
                    for idx_b, b in grid.get((gx, gy), []):
                        if idx_b <= idx_a:
                            continue
                        pair_key = (idx_a, idx_b)
                        if pair_key in compared:
                            continue
                        compared.add(pair_key)
                        dist = self._min_edge_distance(a.bbox, b.bbox)
                        if dist < self.ADJACENT_THRESHOLD:
                            relations.append(SpatialRelation(
                                source_id=a.id, target_id=b.id,
                                rel_type="adjacent", distance=dist,
                                confidence=1.0 - dist / self.ADJACENT_THRESHOLD,
                            ))

        # ── 2. 墙体-门窗拓扑关系（V2升级）──
        # 用几何方法精确匹配门/窗在墙上的位置：
        #   门 bbox 必须与墙 bbox 的某条边重叠（门在墙上）
        #   取最近/重叠最大的墙作为门的宿主墙
        walls = [e for e in entities if e.type == "wall"]
        openings = [e for e in entities if e.type in ("door", "window", "fire_door", "exit_door")]
        
        for opening in openings:
            best_wall = None
            best_overlap = 0.0
            best_distance = float('inf')
            
            ob = opening.bbox
            ox1, oy1 = ob.get("x", 0), ob.get("y", 0)
            ox2 = ox1 + ob.get("width", 0)
            oy2 = oy1 + ob.get("height", 0)
            o_cx = (ox1 + ox2) / 2
            o_cy = (oy1 + oy2) / 2
            
            for wall in walls:
                wb = wall.bbox
                wx1, wy1 = wb.get("x", 0), wb.get("y", 0)
                wx2 = wx1 + wb.get("width", 0)
                wy2 = wy1 + wb.get("height", 0)
                
                # 计算门中心到墙边的距离
                # 到左/右垂直边的水平距离
                dx_left = abs(o_cx - wx1)
                dx_right = abs(o_cx - wx2)
                # 到上/下水平边的垂直距离
                dy_bottom = abs(o_cy - wy1)
                dy_top = abs(o_cy - wy2)
                
                min_dx = min(dx_left, dx_right)
                min_dy = min(dy_bottom, dy_top)
                dist_to_edge = min(min_dx, min_dy)
                
                # 检查重叠：门必须接触墙的边界（距离<50mm）
                if dist_to_edge > 50.0:
                    continue
                
                # 计算门在墙边上的投影重叠长度
                overlap = 0.0
                is_horizontal_wall = (wb.get("width", 0) > wb.get("height", 0))
                
                if min_dx <= min_dy:
                    # 门接触垂直边（墙的左或右边）
                    # 投影重叠在 y 方向
                    overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))
                    overlap = overlap_y / max(ob.get("height", 1), 1)
                else:
                    # 门接触水平边（墙的上或下边）
                    overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))
                    overlap = overlap_x / max(ob.get("width", 1), 1)
                
                if overlap > best_overlap or (overlap == best_overlap and dist_to_edge < best_distance):
                    best_overlap = overlap
                    best_distance = dist_to_edge
                    best_wall = wall
            
            if best_wall:
                relations.append(SpatialRelation(
                    source_id=best_wall.id, target_id=opening.id,
                    rel_type="contains",
                    confidence=min(0.95, best_overlap),
                ))
                # 给门注入宿主墙信息
                opening.properties["host_wall_id"] = best_wall.id
                opening.properties["host_wall_overlap"] = round(best_overlap, 2)

        # ── 3. 走廊-门-房间拓扑（V2：基于边缘距离）──
        # 用 _min_edge_distance 判断门是否连接走廊/房间
        corridors = [e for e in entities if e.type == "corridor"]
        rooms = [e for e in entities if e.type == "room"]
        doors = [e for e in entities if e.type in ("door", "fire_door", "exit_door")]
        
        for door in doors:
            for c in corridors:
                dist = self._min_edge_distance(door.bbox, c.bbox)
                if dist < 200.0:  # 门边缘距走廊 < 200mm
                    relations.append(SpatialRelation(
                        source_id=c.id, target_id=door.id,
                        rel_type="connects_to", distance=dist,
                        via="door",
                    ))
            for r in rooms:
                dist = self._min_edge_distance(door.bbox, r.bbox)
                if dist < 200.0:
                    relations.append(SpatialRelation(
                        source_id=r.id, target_id=door.id,
                        rel_type="connects_to", distance=dist,
                        via="door",
                    ))

        # ── 4. 包含关系（房间包含设备/柱）──
        contained_types = {"column", "stair", "exit", "fire_door"}
        containables = [e for e in entities if e.type in contained_types]
        for room in rooms:
            for item in containables:
                if self._is_inside(item.bbox, room.bbox):
                    relations.append(SpatialRelation(
                        source_id=room.id, target_id=item.id,
                        rel_type="contains", confidence=0.9,
                    ))

        return relations

    def _bind_dimensions(self, entities: List[SemanticEntity],
                         dimensions: List[Dict]) -> Dict[str, Dict]:
        """尺寸标注绑定到实体"""
        bindings = {}

        for dim in dimensions:
            dim_pos = dim.get("position", {})
            if not dim_pos:
                continue

            nearest = None
            nearest_dist = float("inf")

            for entity in entities:
                center = self._bbox_center(entity.bbox)
                dist = self._point_distance(dim_pos, center)
                if dist < nearest_dist and dist < 500:
                    nearest = entity
                    nearest_dist = dist

            if nearest:
                if nearest.id not in bindings:
                    bindings[nearest.id] = {}
                attr_name = self._infer_attribute_name(dim, nearest)
                bindings[nearest.id][attr_name] = dim.get("measurement", 0)

        return bindings

    # ── 几何工具函数 ────────────────────────────────────

    @staticmethod
    def _compute_iou(bbox1: Dict, bbox2: Dict) -> float:
        """计算 IoU"""
        x1 = max(bbox1["x"], bbox2["x"])
        y1 = max(bbox1["y"], bbox2["y"])
        x2 = min(bbox1["x"] + bbox1["width"], bbox2["x"] + bbox2["width"])
        y2 = min(bbox1["y"] + bbox1["height"], bbox2["y"] + bbox2["height"])

        if x2 <= x1 or y2 <= y1:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)
        area1 = bbox1["width"] * bbox1["height"]
        area2 = bbox2["width"] * bbox2["height"]
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _union_bbox(bboxes: List[Dict]) -> Dict[str, float]:
        """合并多个边界框"""
        xs = [b["x"] for b in bboxes]
        ys = [b["y"] for b in bboxes]
        x2s = [b["x"] + b["width"] for b in bboxes]
        y2s = [b["y"] + b["height"] for b in bboxes]
        return {
            "x": min(xs), "y": min(ys),
            "width": max(x2s) - min(xs),
            "height": max(y2s) - min(ys),
        }

    @staticmethod
    def _min_edge_distance(bbox1: Dict, bbox2: Dict) -> float:
        """最小边缘距离"""
        x1a, y1a = bbox1["x"], bbox1["y"]
        x2a = x1a + bbox1["width"]
        y2a = y1a + bbox1["height"]
        x1b, y1b = bbox2["x"], bbox2["y"]
        x2b = x1b + bbox2["width"]
        y2b = y1b + bbox2["height"]

        dx = max(x1b - x2a, x1a - x2b, 0)
        dy = max(y1b - y2a, y1a - y2b, 0)
        return (dx**2 + dy**2) ** 0.5

    @staticmethod
    def _is_inside(inner: Dict, outer: Dict) -> bool:
        """判断内部"""
        return (inner["x"] >= outer["x"]
                and inner["y"] >= outer["y"]
                and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
                and inner["y"] + inner["height"] <= outer["y"] + outer["height"])

    @staticmethod
    def _bbox_center(bbox: Dict) -> Dict[str, float]:
        return {"x": bbox["x"] + bbox["width"] / 2,
                "y": bbox["y"] + bbox["height"] / 2}

    @staticmethod
    def _point_distance(p1: Dict, p2: Dict) -> float:
        return ((p1.get("x", 0) - p2.get("x", 0))**2
                + (p1.get("y", 0) - p2.get("y", 0))**2) ** 0.5

    @staticmethod
    def _infer_attribute_name(dim: Dict, entity: SemanticEntity) -> str:
        """推断属性名"""
        entity_type = entity.type
        dim_text = dim.get("text", "")

        if entity_type == "wall":
            return "width"
        elif entity_type in ("door", "fire_door"):
            return "clear_width"
        elif entity_type == "window":
            return "width"
        elif entity_type == "stair":
            return "step_width"
        elif entity_type == "corridor":
            return "clear_width"
        elif entity_type == "fire_zone":
            return "area"
        else:
            return "measurement"

    # ── 走廊拓扑网络 ────────────────────────────────────

    def build_corridor_topology(self, entities: List[SemanticEntity],
                                 relations: List[SpatialRelation]) -> Dict[str, Any]:
        """构建走廊拓扑网络
        
        将走廊实体按空间相邻关系连接为图，识别：
        - 连通分量（哪些走廊连通）
        - 死胡同（只有一条连接的走廊段）
        - 疏散路径（走廊到出口的可达性）
        """
        corridor_map = {e.id: e for e in entities if e.type == "corridor"}
        
        if len(corridor_map) < 2:
            return {
                "corridors": [e.to_dict() for e in corridor_map.values()],
                "components": 1,
                "dead_ends": [],
                "network": {"nodes": list(corridor_map.keys()), "edges": []},
            }

        # 构建走廊-走廊相邻图
        adjacency: Dict[str, List[Tuple[str, float]]] = {eid: [] for eid in corridor_map}
        
        for rel in relations:
            src = rel.source_id
            tgt = rel.target_id
            if src in corridor_map and tgt in corridor_map and rel.type == "adjacent":
                adjacency[src].append((tgt, rel.distance))
                adjacency[tgt].append((src, rel.distance))
        
        # 门连接：门关联的走廊也算连通
        for rel in relations:
            if rel.type != "connects_to":
                continue
            door_id = rel.target_id
            corridor_id = rel.source_id
            if corridor_id not in corridor_map:
                continue
            # 找门连接的另一侧（room或其他走廊）
            for rel2 in relations:
                if rel2.source_id == door_id and rel2.target_id != corridor_id:
                    other_id = rel2.target_id
                    if other_id in corridor_map:
                        adjacency[corridor_id].append((other_id, rel2.distance))
                        adjacency[other_id].append((corridor_id, rel2.distance))

        # 找连通分量（BFS）
        visited = set()
        components = []
        for eid in corridor_map:
            if eid in visited:
                continue
            comp = []
            queue = [eid]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                comp.append(current)
                for neighbor, _ in adjacency.get(current, []):
                    if neighbor not in visited:
                        queue.append(neighbor)
            if comp:
                components.append(comp)

        # 找死胡同（度=1的走廊节点）
        dead_ends = []
        for eid, neighbors in adjacency.items():
            if len(neighbors) == 1:
                ent = corridor_map[eid]
                dead_ends.append({
                    "id": eid,
                    "width": ent.properties.get("width", 0),
                    "length": ent.properties.get("length", 0),
                    "bbox": ent.bbox,
                })

        # 走廊宽度统计
        widths = [e.properties.get("width", 0) for e in corridor_map.values()]
        valid_widths = [w for w in widths if w > 0]

        return {
            "corridors": [e.to_dict() for e in corridor_map.values()],
            "components": len(components),
            "component_sizes": [len(c) for c in components],
            "dead_ends": dead_ends,
            "dead_end_count": len(dead_ends),
            "width_avg": round(sum(valid_widths) / len(valid_widths), 2) if valid_widths else 0,
            "width_min": round(min(valid_widths), 2) if valid_widths else 0,
            "width_max": round(max(valid_widths), 2) if valid_widths else 0,
            "network": {
                "nodes": list(corridor_map.keys()),
                "edges": [
                    {"source": s, "target": t, "distance": d}
                    for s, neighbors in adjacency.items()
                    for t, d in neighbors
                    if s < t  # 去重
                ],
            },
        }

    def analyze_evacuation_routes(self, entities: List[SemanticEntity],
                                    relations: List[SpatialRelation]) -> List[Dict]:
        """疏散路径分析
        
        检查从每个 room 到最近 exit 的路径：
        1. 是否所有房间都有通往出口的路径
        2. 路径长度是否超过疏散距离阈值
        3. 路径上的走廊宽度是否满足要求
        """
        # 构建全量实体邻接表
        adj: Dict[str, List[Tuple[str, str, float]]] = {}
        for e in entities:
            adj[e.id] = []
        
        for rel in relations:
            if rel.type not in ("adjacent", "connects_to", "contains"):
                continue
            adj.setdefault(rel.source_id, []).append((rel.target_id, rel.type, rel.distance))
            adj.setdefault(rel.target_id, []).append((rel.source_id, rel.type, rel.distance))

        exits = [e for e in entities if e.type in ("exit", "exit_door", "door", "fire_door")]
        rooms = [e for e in entities if e.type == "room"]
        
        if not exits:
            return []

        # 如果没有 room 但有 corridor，用 corridor 作为起点分析连通性
        if not rooms:
            corridors = [e for e in entities if e.type == "corridor"]
            if corridors:
                rooms = corridors  # 兜底：用走廊代替房间作为起点
            else:
                return []
        
        # 优先用 type=exit 的，兜底用 door/fire_door
        has_exit_type = any(e.type == "exit" for e in exits)
        if not has_exit_type:
            pass

        routes = []
        for room in rooms:
            # BFS 找最近出口
            visited = {room.id}
            queue = [(room.id, [room.id], 0.0)]
            found_route = None

            while queue:
                current, path, distance = queue.pop(0)
                if current in {e.id for e in exits}:
                    found_route = (path, distance)
                    break
                for neighbor, rel_type, dist in adj.get(current, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor], distance + dist))

            route_info = {
                "room_id": room.id,
                "room_type": room.type,
                "room_bbox": room.bbox,
                "has_route": found_route is not None,
                "path_length": round(found_route[1], 2) if found_route else None,
                "path": found_route[0] if found_route else [],
                "exceeds_max_distance": found_route is not None and found_route[1] > 30.0,
            }
            routes.append(route_info)

        return routes

    @staticmethod
    def _rel_to_dict(rel: SpatialRelation) -> dict:
        return {
            "source_id": rel.source_id,
            "target_id": rel.target_id,
            "type": rel.type,
            "distance": rel.distance,
            "via": rel.via,
            "confidence": rel.confidence,
        }