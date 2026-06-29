"""
BAA 语义识别引擎 - 图元分类 + 空间关系构建（规则版）
"""
from typing import List, Dict, Any, Optional, Tuple
from .drawing_parser import RawPrimitive


# ── 图层规则表 ────────────────────────────────────────────

# 短关键字（单字母/2字母）使用全词匹配（前后是_或边界），防止误匹配
# 例如 "D" 不匹配 "DIM"、"DIMENSION"、"DWG"、"DOOR"
LAYER_RULES = {  # 赋值
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
    "HATCH": "other",  # 填充图案（非建筑实体）
    "BEAM": "other",  # 结构梁（非建筑实体）
    "BAR": "other",  # 钢筋标记
    "REIN": "other",  # 钢筋
    "AXIS": "other",  # 轴线标记
    "BASE": "other",  # 基础结构
    "钢筋": "other",  # 钢筋（中文图层名）
}

# 短关键字（单字母/2字母）使用全词匹配
SHORT_LAYER_RULES = {  # 赋值
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
                 subtype: str = "", confidence: float = 1.0,  # 赋值
                 properties: Dict[str, Any] = None):  # 赋值
        self.id = entity_id  # 赋值
        self.type = entity_type  # 赋值
        self.bbox = bbox  # 赋值
        self.layer = layer  # 赋值
        self.subtype = subtype  # 赋值
        self.confidence = confidence  # 赋值
        self.properties = properties or {}  # 赋值

    def to_dict(self) -> dict:
        return {  # 返回
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
                 via: str = "", confidence: float = 1.0):  # 赋值
        self.source_id = source_id  # 赋值
        self.target_id = target_id  # 赋值
        self.type = rel_type      # adjacent / contains / connects_to
        self.distance = distance  # 赋值
        self.via = via  # 赋值
        self.confidence = confidence  # 赋值


# ── 语义分析引擎 ──────────────────────────────────────────

class SemanticAnalyzer:
    """语义识别引擎（规则版，不做ML）"""

    ADJACENT_THRESHOLD = 50.0  # 相邻距离阈值(mm)

    def __init__(self):
        self._entity_counter = 0  # 赋值

    def analyze(self, primitives: List[RawPrimitive],
                dimensions: List[Dict] = None,
                max_entities: int = 1000,  # 赋值
                building_type: str = "civil") -> Dict[str, Any]:  # 赋值
        """
        执行语义分析

        参数:
            primitives: 原始图元列表
            dimensions: 尺寸标注列表
            max_entities: 最大处理实体数（超过则采样，防OOM）

        输出: 结构化语义数据（entities + relations + attributes）
        """
        self._entity_counter = 0  # 赋值

        # 采样限制，防止全量关系构建OOM
        if len(primitives) > max_entities:  # 条件判断
            import random
            random.seed(42)  # 调用
            primitives = random.sample(primitives, max_entities)  # 赋值

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)  # 赋值

        # Step 1.5: 走廊宽度推断（平行线聚类 + bbox 短边）
        entities = self._infer_corridor_widths(entities, primitives)  # 赋值

        # Step 1.6: door/fire_door 属性增强（宽度兜底 + 防火等级推断）
        for ent in entities:  # 循环
            if ent.type in ("door", "fire_door", "exit_door"):  # 条件判断
                # 宽度兜底：bbox短边推断
                if ent.properties.get("width", 0) < 0.3 and ent.properties.get("clear_width", 0) < 0.3:  # 条件判断
                    bbox = ent.bbox  # 赋值
                    bw = bbox.get("width", 0)  # 赋值
                    bh = bbox.get("height", 0)  # 赋值
                    if bw > 0 and bh > 0:  # 条件判断
                        w_mm = min(bw, bh)  # 赋值
                        w_m = w_mm * 0.001  # 赋值
                        if 0.3 < w_m < 3.0:  # 条件判断
                            ent.properties["width"] = w_m
                            ent.properties["clear_width"] = w_m
                # 防火等级推断：从图层名和实体名推断
                if ent.type == "fire_door":  # 条件判断
                    existing_rating = ent.properties.get("fire_rating", ent.properties.get("rating", 0))  # 赋值
                    if existing_rating < 0.5:  # 条件判断
                        # 图层名包含关键字推断
                        layer_upper = (ent.layer or "").upper()  # 赋值
                        combined = layer_upper  # 赋值
                        if "甲" in combined or "A" in combined:  # 条件判断
                            ent.properties["fire_rating"] = 3.0  # 甲级=3.0
                        elif "乙" in combined or "B" in combined:  # 分支
                            ent.properties["fire_rating"] = 2.0  # 乙级=2.0
                        elif "丙" in combined or "C" in combined:  # 分支
                            ent.properties["fire_rating"] = 1.0  # 丙级=1.0
                        else:  # 否则
                            # 默认设为甲级（保守安全策略）
                            ent.properties["fire_rating"] = 3.0

        # Step 2: 空间关系构建（V2拓扑关系）
        relations = self._build_relations(entities)  # 赋值

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])  # 赋值

        # Step 4: 走廊拓扑网络（V2新增）
        corridor_topology = self.build_corridor_topology(entities, relations)  # 赋值

        # Step 5: 疏散路径分析（V2新增）
        evacuation_routes = self.analyze_evacuation_routes(entities, relations)  # 赋值

        # Step 5.5: 疏散路径结果注入到实体属性（EVAC原子函数用）
        route_by_room = {}  # 赋值
        for route in evacuation_routes:  # 循环
            route_by_room[route["room_id"]] = route
        dead_end_ids = set(d["id"] for d in corridor_topology.get("dead_ends", []))  # 赋值
        for ent in entities:  # 循环
            if ent.id in dead_end_ids:  # 条件判断
                ent.properties["is_dead_end"] = True
            if ent.id in route_by_room:  # 条件判断
                r = route_by_room[ent.id]  # 赋值
                ent.properties["has_evacuation_route"] = r.get("has_route", False)
                if r.get("path_length") is not None:  # 条件判断
                    ent.properties["evacuation_path_length"] = r["path_length"]
                ent.properties["evacuation_too_far"] = r.get("exceeds_max_distance", False)
            # 对未找到路径的实体（如走廊兜底），标记为无路径
            elif ent.type in ("room", "corridor"):  # 分支
                if "has_evacuation_route" not in ent.properties:  # 条件判断
                    ent.properties["has_evacuation_route"] = False
                    ent.properties["evacuation_too_far"] = True

        return {  # 返回
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
        entities = []  # 赋值
        for prim in primitives:  # 循环
            if prim.layer.upper() != "META":  # 条件判断
                continue  # 继续循环
            text = prim.properties.get("text", "")  # 赋值
            if not text.startswith("ENTITY:"):  # 条件判断
                continue  # 继续循环
            parts = text.split("|")  # 赋值
            if len(parts) < 5:  # 条件判断
                continue  # 继续循环
            # 解析类型
            etype = parts[0].replace("ENTITY:", "").strip()  # 赋值
            # 解析bbox和属性
            props = {}  # 赋值
            bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}  # 赋值
            for part in parts[1:]:  # 循环
                if ":" not in part:  # 条件判断
                    continue  # 继续循环
                k, v = part.split(":", 1)
                k = k.strip()  # 赋值
                v = v.strip()  # 赋值
                if k == "x":  # 条件判断
                    bbox["x"] = float(v)
                elif k == "y":  # 分支
                    bbox["y"] = float(v)
                elif k == "w":  # 分支
                    bbox["width"] = float(v)
                elif k == "h":  # 分支
                    bbox["height"] = float(v)
                else:  # 否则
                    # 尝试转数字，失败保留字符串
                    try:  # 尝试
                        props[k] = float(v)  # 赋值
                    except ValueError:  # 捕获异常
                        props[k] = v  # 赋值

            self._entity_counter += 1  # 赋值
            entity = SemanticEntity(  # 赋值
                entity_id=f"{etype.upper()}_{self._entity_counter:03d}",  # 赋值
                entity_type=etype,  # 赋值
                bbox=bbox,  # 赋值
                layer="META",  # 赋值
                confidence=1.0,  # 赋值
                properties=props,  # 赋值
            )
            entities.append(entity)  # 调用

        return entities  # 返回

    def _classify_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
        """图元分类归并"""
        # 优先解析 META 图层（合成图纸结构化数据）
        meta_entities = self._parse_meta_entities(primitives)  # 赋值
        if meta_entities:  # 条件判断
            return meta_entities  # 返回

        entities = []  # 赋值

        for prim in primitives:  # 循环
            # 图层规则匹配
            entity_type = self._classify_by_layer(prim.layer)  # 赋值
            if entity_type == "unknown":  # 条件判断
                entity_type = self._classify_by_geometry(prim)  # 赋值

            if entity_type == "unknown":  # 条件判断
                continue  # 继续循环

            self._entity_counter += 1  # 赋值
            # 过滤 NaN properties
            cleaned_props = {}  # 赋值
            for pk, pv in prim.properties.items():  # 循环
                if isinstance(pv, float):  # 条件判断
                    import math
                    if not math.isnan(pv):  # 条件判断
                        cleaned_props[pk] = pv  # 赋值
                else:  # 否则
                    cleaned_props[pk] = pv  # 赋值
            entity = SemanticEntity(  # 赋值
                entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",  # 赋值
                entity_type=entity_type,  # 赋值
                bbox=prim.bbox,  # 赋值
                layer=prim.layer,  # 赋值
                confidence=0.9 if entity_type != "unknown" else 0.5,  # 赋值
                properties=cleaned_props,  # 赋值
            )
            entities.append(entity)  # 调用

        # 归并同类重叠图元
        entities = self._merge_overlapping(entities)  # 赋值

        # 过滤过小的走廊实体（LINE 类型容易被误识别为走廊）
        # 走廊宽度 < 500mm 且 bbox 短边 < 500mm 的实体可能是微小图元误标
        filtered = []  # 赋值
        for e in entities:  # 循环
            if e.type == "corridor":  # 条件判断
                bb = e.bbox  # 赋值
                bw = bb.get("width", 0)  # 赋值
                bh = bb.get("height", 0)  # 赋值
                short_edge = min(bw, bh) if bw > 0 and bh > 0 else max(bw, bh)  # 赋值
                if short_edge < 500:  # 短边 < 500mm 不可能是走廊
                    continue  # 继续循环
            filtered.append(e)  # 调用
        entities = filtered  # 赋值

        return entities  # 返回

    def _classify_by_layer(self, layer: str) -> str:
        """图层规则归类

        长关键字（≥3字符）：子串匹配
        短关键字（1-2字符）：全词匹配（前后是_或边界），防止误匹配
        """
        if not layer:  # 条件判断
            return "unknown"  # 返回
        layer_upper = layer.upper()  # 赋值

        # 长关键字（≥3字符）：子串匹配
        for keyword, entity_type in LAYER_RULES.items():  # 循环
            if keyword in layer_upper:  # 条件判断
                return entity_type  # 返回

        # 短关键字（1-2字符）：全词匹配
        for keyword, entity_type in SHORT_LAYER_RULES.items():  # 循环
            if keyword in layer_upper:  # 条件判断
                # 检查全词边界
                idx = layer_upper.find(keyword)  # 赋值
                while idx >= 0:  # 循环
                    pre_ok = (idx == 0 or layer_upper[idx-1] == '_')  # 赋值
                    post_ok = (idx + len(keyword) >= len(layer_upper) or layer_upper[idx+len(keyword)] == '_')  # 赋值
                    if pre_ok and post_ok:  # 条件判断
                        return entity_type  # 返回
                    idx = layer_upper.find(keyword, idx + 1)  # 赋值

        return "unknown"  # 返回

    def _classify_by_geometry(self, prim: RawPrimitive) -> str:
        """几何特征兜底归类（V2深度升级版）
        
        新增规则：
        - 短 LINE 且靠近 DIMENSION 标注的 defpoint → door
        - 小面积闭合多边形（门打开轨迹）→ door
        - 靠近门的 ARC → door
        - 狭长闭合多边形 → corridor
        - 大尺寸 CIRCLE（>3000mm）→ stair
        """
        dxf_type = prim.dxf_type  # 赋值
        bbox = prim.bbox  # 赋值
        bw = bbox.get("width", 0)  # 赋值
        bh = bbox.get("height", 0)  # 赋值
        area = bw * bh  # 赋值
        props = prim.properties  # 赋值
        length = props.get("length", 0) or max(bw, bh)  # 赋值
        short_edge = min(bw, bh) if bw > 0 and bh > 0 else length  # 赋值

        if dxf_type == "LINE":  # 条件判断
            if length > 2000:  # 条件判断
                return "wall"  # 返回
            # 中等长度 LINE（700~2000mm）：典型门宽范围 → door
            if 700 < length < 2000 and short_edge < 50:  # 条件判断
                return "door"  # 返回
            # 短 LINE（50~700mm）可能是门的宽度线或小构件
            if 50 < length < 700 and short_edge < 5:  # 条件判断
                return "door"  # 返回
            # LINE 类型 bbox 短边≈0（纯线无宽度），不可能是走廊
            # 只有长度 > 2000mm 的 LINE 才可能归类为 wall（已处理）
            return "other"  # 返回

        if dxf_type in ("LWPOLYLINE", "POLYLINE"):  # 条件判断
            pts_count = props.get("point_count", 0)  # 赋值
            if pts_count == 2:  # 条件判断
                # 2 点 LWPOLYLINE：视为 LINE 等价
                if length > 2000:  # 条件判断
                    return "wall"  # 返回
                if 700 < length < 2000 and short_edge < 50:  # 条件判断
                    return "door"  # 返回
                if 50 < length < 700 and short_edge < 5:  # 条件判断
                    return "door"  # 返回
                return "other"  # 返回
            
            # 闭合多边形判断
            is_closed = props.get("area", 0) > 0 or (pts_count >= 3)  # 赋值
            if is_closed:  # 条件判断
                aspect_ratio = max(bw, bh) / max(short_edge, 1)  # 赋值
                # 图层排除：非建筑图层上的闭合多边形不可能是房间
                non_room_layers = ["COLU", "视口", "洞口", "板边", "梁边", "轴", "BASE", "梁", "吊筋", "板层", "文字", "钢筋", "标注", "DIM", "立面看线", "立面", "看线", "园林", "井", "电-", "系统", "设备", "电缆", "Defpoints"]  # 赋值
                if any(kw in prim.layer.upper() for kw in non_room_layers):  # 条件判断
                    if aspect_ratio > 3:  # 条件判断
                        return "other"  # 返回
                    return "wall"  # 返回
                # room 最小面积 1m²（1,000,000mm²），过滤小框/文字标注
                # room 最大面积 500m²（500,000,000mm²），过滤图纸边界框/标题栏框
                if area > 500000000:  # > 500m² → 图纸边界/标题栏，不是房间
                    return "other"  # 返回
                if area > 1000000:  # > 1m²
                    if aspect_ratio > 5:  # 条件判断
                        # 狭长 → 走廊
                        if length > 3000:  # 条件判断
                            return "wall"  # 返回
                        return "corridor"  # 返回
                    return "room"  # 返回
                elif area > 50000:  # 大面积但 < 1m²
                    if aspect_ratio > 5:  # 条件判断
                        if length > 3000:  # 条件判断
                            return "wall"  # 返回
                        return "corridor"  # 返回
                    return "wall"  # 返回
                elif area > 50000:  # 条件分支
                    # 中等面积（0.05~1m²）：可能是小房间或设备间
                    if aspect_ratio > 4:  # 条件判断
                        return "corridor"  # 返回
                    return "room"  # 返回
                elif area > 5000:  # 条件分支
                    # 小面积（0.005~0.05m²）：通常是文字框/图例框/标注框，不是房间
                    return "other"  # 返回
                else:  # 否则
                    # 小面积闭合多边形（500~5000mm²）→ door 或 window
                    if aspect_ratio > 3:  # 条件判断
                        # 狭长小面积 → 门的开合轨迹
                        return "door"  # 返回
                    elif aspect_ratio < 1.5:  # 条件分支
                        # 接近正方形的小面积 → column
                        return "column"  # 返回
                    return "door"  # 返回
            return "corridor"  # 返回

        # ARC：门弧或窗
        if dxf_type == "ARC":  # 条件判断
            radius = props.get("radius", 0)  # 赋值
            if 100 < radius < 2000:  # 条件判断
                return "door"  # 返回
            return "window"  # 返回

        if dxf_type == "CIRCLE":  # 条件判断
            radius = props.get("radius", 0)  # 赋值
            if radius > 3000:  # 条件判断
                return "stair"  # 返回
            elif radius > 1000:  # 条件分支
                return "stair"  # 返回
            elif radius > 300:  # 条件分支
                return "column"  # 返回
            return "column"  # 返回

        if dxf_type == "TEXT":  # 条件判断
            text = props.get("text", "")  # 赋值
            if not text:  # 条件判断
                return "text"  # 返回
            text_upper = text.upper()  # 赋值
            if "出口" in text or "EXIT" in text_upper:  # 条件判断
                return "exit"  # 返回
            if "楼梯" in text or "STAIR" in text_upper:  # 条件判断
                return "stair"  # 返回
            # "防火" 关键词需配合 "门" 或 "窗" 才能归类，避免文本描述被误标
            if "防火门" in text or ("FIRE" in text_upper and "DOOR" in text_upper):  # 条件判断
                return "fire_door"  # 返回
            if "防火窗" in text or ("FIRE" in text_upper and "WINDOW" in text_upper):  # 条件判断
                return "fire_window"  # 返回
            return "text"  # 返回

        # INSERT 块：尝试从块名推断
        if dxf_type == "INSERT":  # 条件判断
            block_name = props.get("block_name", "").upper()  # 赋值
            if "DOOR" in block_name or "门" in block_name:  # 条件判断
                return "door"  # 返回
            if "WINDOW" in block_name or "窗" in block_name:  # 条件判断
                return "window"  # 返回
            if "STAIR" in block_name or "ST" in block_name:  # 条件判断
                return "stair"  # 返回
            if "COLUMN" in block_name or "柱" in block_name:  # 条件判断
                return "column"  # 返回
            return "wall"  # 返回

        return "unknown"  # 返回

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
        for ent in entities:  # 循环
            bbox = ent.bbox  # 赋值
            for k in ('x', 'y', 'width', 'height'):  # 遍历
                v = bbox.get(k, 0)  # 赋值
                if isinstance(v, float) and math.isnan(v):  # 条件判断
                    bbox[k] = 0.0  # 赋值

        # ── 策略1：平行线聚类宽度推断（按空间分区）──
        if primitives:  # 条件判断
            # 收集可能的走廊原始图元（LINE + 2点LWPOLYLINE）
            edge_candidates = []  # 赋值
            for p in primitives:  # 循环
                bbox = p.bbox  # 赋值
                cx = bbox.get("x", 0) + bbox.get("width", 0) / 2  # 赋值
                cy = bbox.get("y", 0) + bbox.get("height", 0) / 2  # 赋值
                # 排除坐标偏移的图元
                if abs(cx) < 100 and abs(cy) < 100:  # 条件判断
                    continue  # 继续循环
                if abs(cx) > 1e7 or abs(cy) > 1e7:  # 条件判断
                    continue  # 继续循环
                bw = bbox.get("width", 0)  # 赋值
                bh = bbox.get("height", 0)  # 赋值
                span = max(bw, bh)  # 赋值
                if span < 100 or span > 100000:  # 0.1m~100m 合理范围
                    continue  # 继续循环
                if p.dxf_type == "LINE":  # 条件判断
                    angle = p.properties.get("angle", 0) % 180  # 赋值
                    if angle > 90: angle = 180 - angle  # 条件判断
                    edge_candidates.append({  # 调用
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,
                        "span": span, "angle": angle,
                    })
                elif p.dxf_type == "LWPOLYLINE" and p.properties.get("point_count", 0) == 2:  # 分支
                    angle = 0 if bw > bh else 90  # 赋值
                    edge_candidates.append({  # 调用
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,
                        "span": span, "angle": angle,
                    })

            if edge_candidates:  # 条件判断
                # 按方向分组
                h_edges = [e for e in edge_candidates if e["angle"] < 30]  # 赋值
                v_edges = [e for e in edge_candidates if e["angle"] > 60]  # 赋值

                # 水平线：按cy排序，收集所有gap
                h_sorted = sorted(h_edges, key=lambda e: e["cy"])  # 赋值
                h_gaps = []  # 赋值
                for i in range(min(300, len(h_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(h_sorted))):  # 循环
                        gap = abs(h_sorted[i]["cy"] - h_sorted[j]["cy"])  # 赋值
                        if 500 < gap < 10000:  # 条件判断
                            h_gaps.append({"gap": gap, "y1": h_sorted[i]["cy"], "y2": h_sorted[j]["cy"],
                                          "cx1": h_sorted[i]["cx"], "cx2": h_sorted[j]["cx"]})

                # 垂直线：按cx排序，收集所有gap
                v_sorted = sorted(v_edges, key=lambda e: e["cx"])  # 赋值
                v_gaps = []  # 赋值
                for i in range(min(300, len(v_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(v_sorted))):  # 循环
                        gap = abs(v_sorted[i]["cx"] - v_sorted[j]["cx"])  # 赋值
                        if 500 < gap < 10000:  # 条件判断
                            v_gaps.append({"gap": gap, "x1": v_sorted[i]["cx"], "x2": v_sorted[j]["cx"],
                                          "cy1": v_sorted[i]["cy"], "cy2": v_sorted[j]["cy"]})

                all_gaps = h_gaps + v_gaps  # 赋值
                if all_gaps and len(all_gaps) > 10:  # 条件判断
                    # 空间分区聚类：每条走廊取离它最近的 gap 作为宽度
                    # 1) 对每个 gap，按位置分到最近的走廊
                    # 2) 每个走廊取其区域内 gap 众数
                    corridor_entities = [e for e in entities if e.type == "corridor"]  # 赋值
                    if corridor_entities:  # 条件判断
                        for ent in corridor_entities:  # 循环
                            cx = ent.bbox.get("x", 0) + ent.bbox.get("width", 0) / 2  # 赋值
                            cy = ent.bbox.get("y", 0) + ent.bbox.get("height", 0) / 2  # 赋值
                            bw = ent.bbox.get("width", 0)  # 赋值
                            bh = ent.bbox.get("height", 0)  # 赋值
                            # 先用 bbox 短边推断宽度（LINE 类型用长边）
                            if bw > 0 and bh > 0:  # 条件判断
                                w_mm = min(bw, bh)  # 赋值
                                w_m = w_mm * 0.001  # 赋值
                                if 0.3 < w_m < 3.0 and ent.properties.get("width", 0) < w_m:  # 条件判断
                                    ent.properties["width"] = w_m
                                    ent.properties["clear_width"] = w_m
                                    ent.properties["_width_source"] = "bbox_short_edge"
                                    continue  # 继续循环
                            
                            # bbox 短边≈0（LINE类型）：找附近gap
                            if ent.properties.get("width", 0) < 0.3:  # 条件判断
                                # 找附近 gap
                                nearby_gaps = []  # 赋值
                                for g in all_gaps:  # 循环
                                    if "y1" in g:  # 水平gap
                                        mid_y = (g["y1"] + g["y2"]) / 2  # 赋值
                                        mid_x = (g["cx1"] + g["cx2"]) / 2  # 赋值
                                        if abs(cy - mid_y) < 3000 and abs(cx - mid_x) < 3000:  # 条件判断
                                            nearby_gaps.append(g["gap"])
                                    else:  # 垂直gap
                                        mid_x = (g["x1"] + g["x2"]) / 2  # 赋值
                                        mid_y = (g["cy1"] + g["cy2"]) / 2  # 赋值
                                        if abs(cx - mid_x) < 3000 and abs(cy - mid_y) < 3000:  # 条件判断
                                            nearby_gaps.append(g["gap"])
                                
                                if nearby_gaps:  # 条件判断
                                    # 取附近gap的众数作为此走廊宽度
                                    gap_buckets = defaultdict(list)  # 赋值
                                    for g in nearby_gaps:  # 循环
                                        bucket = round(g / 100) * 100  # 赋值
                                        gap_buckets[bucket].append(g)  # 操作
                                    best_bucket = max(gap_buckets.items(), key=lambda x: len(x[1]))  # 赋值
                                    w_m = (sum(best_bucket[1]) / len(best_bucket[1])) / 1000.0  # 赋值
                                    if 0.3 < w_m < 3.0:  # 条件判断
                                        ent.properties["width"] = w_m
                                        ent.properties["clear_width"] = w_m
                                        ent.properties["_width_source"] = "nearby_gap"
                                else:  # 否则
                                    # 无附近gap：用bbox长边
                                    span_mm = max(bw, bh)  # 赋值
                                    w_m = span_mm * 0.001  # 赋值
                                    if 0.3 < w_m < 3.0:  # 条件判断
                                        ent.properties["width"] = w_m
                                        ent.properties["clear_width"] = w_m
                                        ent.properties["_width_source"] = "bbox_long_edge"
        
        # ── 策略1.5：door/window 宽度推断（V2增强）──
        for ent in entities:  # 循环
            if ent.type not in ("door", "window", "fire_door", "exit_door"):  # 条件判断
                continue  # 继续循环
            existing = ent.properties.get("width", 0)  # 赋值
            if existing > 0.5:  # 条件判断
                continue  # 继续循环
            # 从 ARC 半径推断门宽度（门弧半径 ≈ 门宽度）
            radius = ent.properties.get("radius", 0)  # 赋值
            if radius > 100 and radius < 2000:  # 条件判断
                w_m = radius * 0.001  # mm → m
                if 0.3 < w_m < 2.0:  # 条件判断
                    ent.properties["width"] = w_m
                    ent.properties["clear_width"] = w_m
                    continue  # 继续循环
            # bbox 推断
            bbox = ent.bbox  # 赋值
            bw = bbox.get("width", 0)  # 赋值
            bh = bbox.get("height", 0)  # 赋值
            if bw > 0 and bh > 0:  # 条件判断
                w_mm = min(bw, bh)  # 赋值
                w_m = w_mm * 0.001  # 赋值
                if 0.3 < w_m < 2.0 and ent.properties.get("width", 0) < w_m:  # 条件判断
                    ent.properties["width"] = w_m
                    ent.properties["clear_width"] = w_m
            # LINE 类型（短边≈0）：用长边作为宽度
            if ent.properties.get("width", 0) < 0.3:  # 条件判断
                span_mm = max(bw, bh)  # 赋值
                if 300 < span_mm < 2000:  # 300mm~2m
                    w_m = span_mm * 0.001  # 赋值
                    ent.properties["width"] = w_m
                    ent.properties["clear_width"] = w_m
            # Polygon 类 door（闭合多边形）：短边可能是门扇厚度，用长边推断宽度
            if ent.properties.get("width", 0) < 0.3:  # 条件判断
                long_edge_mm = max(bw, bh)  # 赋值
                if 300 < long_edge_mm < 2000:  # 条件判断
                    w_m = long_edge_mm * 0.001  # 赋值
                    ent.properties["width"] = w_m
                    ent.properties["clear_width"] = w_m

        # ── 策略2：bbox 短边推断（覆盖所有类型） ──
        for ent in entities:  # 循环
            if ent.type not in ("corridor", "door", "window", "room", "wall"):  # 条件判断
                continue  # 继续循环
            bbox = ent.bbox  # 赋值
            bw = bbox.get("width", 0)  # 赋值
            bh = bbox.get("height", 0)  # 赋值

            if bw == 0 and bh == 0:  # 条件判断
                continue  # 继续循环

            # bbox 两边非零 → 短边为宽度（mm→m），长边为 length
            if bw > 0 and bh > 0:  # 条件判断
                w_mm = min(bw, bh)  # 赋值
                w_m = w_mm * 0.001  # 赋值
                if not math.isnan(w_m) and w_m > 0.01 and w_m < 10:  # 条件判断
                    current_w = ent.properties.get("width", 0)  # 赋值
                    if current_w < w_m:  # 条件判断
                        ent.properties["width"] = w_m
                        ent.properties["clear_width"] = w_m
                l_mm = max(bw, bh)  # 赋值
                if l_mm > 0:  # 条件判断
                    ent.properties["length"] = l_mm * 0.001
                continue  # 继续循环

            # bbox 只有一边非零（LINE / 2 点 LWPOLYLINE）
            span_mm = max(bw, bh)  # 赋值
            if span_mm > 0:  # 条件判断
                span_m = span_mm * 0.001  # 赋值
                if not math.isnan(span_m) and span_m > 0.05:  # 条件判断
                    ent.properties["length"] = span_m
                    # 对 corridor/room：bbox短边≈宽度
                    if ent.type in ("corridor", "room", "door", "fire_door", "exit_door"):  # 条件判断
                        short_mm = min(bw, bh) if bw > 0 and bh > 0 else 0  # 赋值
                        if short_mm > 0:  # 条件判断
                            short_m = short_mm * 0.001  # 赋值
                            current_w = ent.properties.get("width", 0)  # 赋值
                            if current_w < 0.01 and 0.05 < short_m < 3.0:  # 条件判断
                                ent.properties["width"] = short_m
                                ent.properties["clear_width"] = short_m

        return entities  # 返回

    def _merge_overlapping(self, entities: List[SemanticEntity]) -> List[SemanticEntity]:
        """合并重叠/相邻的同类图元"""
        if len(entities) < 2:  # 条件判断
            return entities  # 返回

        merged = []  # 赋值
        used = set()  # 赋值

        for i, a in enumerate(entities):  # 循环
            if i in used:  # 条件判断
                continue  # 继续循环

            cluster = [a]  # 赋值
            used.add(i)  # 调用

            for j, b in enumerate(entities):  # 循环
                if j in used:  # 条件判断
                    continue  # 继续循环
                if a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5:  # 条件判断
                    cluster.append(b)  # 调用
                    used.add(j)  # 调用

            if len(cluster) > 1:  # 条件判断
                # 合并边界框
                merged_bbox = self._union_bbox([e.bbox for e in cluster])  # 赋值
                merged.append(SemanticEntity(  # 调用
                    entity_id=a.id,  # 赋值
                    entity_type=a.type,  # 赋值
                    bbox=merged_bbox,  # 赋值
                    layer=a.layer,  # 赋值
                    confidence=max(e.confidence for e in cluster),  # 赋值
                    properties=a.properties,  # 赋值
                ))
            else:  # 否则
                merged.append(a)  # 调用

        return merged  # 返回

    def _build_relations(self, entities: List[SemanticEntity]) -> List[SpatialRelation]:
        """构建空间关系（V2深度升级版）
        
        包括：
        - 相邻关系（相邻距离阈值，>500实体用空间哈希加速）
        - 墙体-门窗拓扑关系（精确匹配门在墙上的位置）
        - 走廊连通关系（门连接走廊与房间）
        - 包含关系（房间包含设备）
        """
        relations = []  # 赋值

        # ── 1. 相邻关系（空间哈希加速）──
        CELL_SIZE = 100.0  # mm
        # 空间哈希网格
        grid: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}
        for idx, e in enumerate(entities):  # 循环
            bx = e.bbox.get("x", 0)  # 赋值
            by = e.bbox.get("y", 0)  # 赋值
            bw = e.bbox.get("width", 0)  # 赋值
            bh = e.bbox.get("height", 0)  # 赋值
            # 实体占据的网格范围
            x1_cell = int(bx / CELL_SIZE)  # 赋值
            x2_cell = int((bx + bw) / CELL_SIZE)  # 赋值
            y1_cell = int(by / CELL_SIZE)  # 赋值
            y2_cell = int((by + bh) / CELL_SIZE)  # 赋值
            for gx in range(x1_cell, x2_cell + 1):  # 循环
                for gy in range(y1_cell, y2_cell + 1):  # 循环
                    grid.setdefault((gx, gy), []).append((idx, e))  # 调用
        
        # 只比较同一或相邻网格的实体
        compared = set()  # 赋值
        for idx_a, a in enumerate(entities):  # 循环
            bx = a.bbox.get("x", 0)  # 赋值
            by = a.bbox.get("y", 0)  # 赋值
            bw = a.bbox.get("width", 0)  # 赋值
            bh = a.bbox.get("height", 0)  # 赋值
            x1_cell = int(bx / CELL_SIZE)  # 赋值
            x2_cell = int((bx + bw) / CELL_SIZE)  # 赋值
            y1_cell = int(by / CELL_SIZE)  # 赋值
            y2_cell = int((by + bh) / CELL_SIZE)  # 赋值
            for gx in range(x1_cell - 1, x2_cell + 2):  # 循环
                for gy in range(y1_cell - 1, y2_cell + 2):  # 循环
                    for idx_b, b in grid.get((gx, gy), []):  # 循环
                        if idx_b <= idx_a:  # 条件判断
                            continue  # 继续循环
                        pair_key = (idx_a, idx_b)  # 赋值
                        if pair_key in compared:  # 条件判断
                            continue  # 继续循环
                        compared.add(pair_key)  # 调用
                        dist = self._min_edge_distance(a.bbox, b.bbox)  # 赋值
                        if dist < self.ADJACENT_THRESHOLD:  # 条件判断
                            relations.append(SpatialRelation(  # 调用
                                source_id=a.id, target_id=b.id,  # 赋值
                                rel_type="adjacent", distance=dist,  # 赋值
                                confidence=1.0 - dist / self.ADJACENT_THRESHOLD,  # 赋值
                            ))

        # ── 2. 墙体-门窗拓扑关系（V2升级）──
        # 用几何方法精确匹配门/窗在墙上的位置：
        #   门 bbox 必须与墙 bbox 的某条边重叠（门在墙上）
        #   取最近/重叠最大的墙作为门的宿主墙
        walls = [e for e in entities if e.type == "wall"]  # 赋值
        openings = [e for e in entities if e.type in ("door", "window", "fire_door", "exit_door")]  # 赋值
        
        for opening in openings:  # 循环
            best_wall = None  # 赋值
            best_overlap = 0.0  # 赋值
            best_distance = float('inf')  # 赋值
            
            ob = opening.bbox  # 赋值
            ox1, oy1 = ob.get("x", 0), ob.get("y", 0)
            ox2 = ox1 + ob.get("width", 0)  # 赋值
            oy2 = oy1 + ob.get("height", 0)  # 赋值
            o_cx = (ox1 + ox2) / 2  # 赋值
            o_cy = (oy1 + oy2) / 2  # 赋值
            
            for wall in walls:  # 循环
                wb = wall.bbox  # 赋值
                wx1, wy1 = wb.get("x", 0), wb.get("y", 0)
                wx2 = wx1 + wb.get("width", 0)  # 赋值
                wy2 = wy1 + wb.get("height", 0)  # 赋值
                
                # 计算门中心到墙边的距离
                # 到左/右垂直边的水平距离
                dx_left = abs(o_cx - wx1)  # 赋值
                dx_right = abs(o_cx - wx2)  # 赋值
                # 到上/下水平边的垂直距离
                dy_bottom = abs(o_cy - wy1)  # 赋值
                dy_top = abs(o_cy - wy2)  # 赋值
                
                min_dx = min(dx_left, dx_right)  # 赋值
                min_dy = min(dy_bottom, dy_top)  # 赋值
                dist_to_edge = min(min_dx, min_dy)  # 赋值
                
                # 检查重叠：门必须接触墙的边界（距离<50mm）
                if dist_to_edge > 50.0:  # 条件判断
                    continue  # 继续循环
                
                # 计算门在墙边上的投影重叠长度
                overlap = 0.0  # 赋值
                is_horizontal_wall = (wb.get("width", 0) > wb.get("height", 0))  # 赋值
                
                if min_dx <= min_dy:  # 条件判断
                    # 门接触垂直边（墙的左或右边）
                    # 投影重叠在 y 方向
                    overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))  # 赋值
                    overlap = overlap_y / max(ob.get("height", 1), 1)  # 赋值
                else:  # 否则
                    # 门接触水平边（墙的上或下边）
                    overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))  # 赋值
                    overlap = overlap_x / max(ob.get("width", 1), 1)  # 赋值
                
                if overlap > best_overlap or (overlap == best_overlap and dist_to_edge < best_distance):  # 条件判断
                    best_overlap = overlap  # 赋值
                    best_distance = dist_to_edge  # 赋值
                    best_wall = wall  # 赋值
            
            if best_wall:  # 条件判断
                relations.append(SpatialRelation(  # 调用
                    source_id=best_wall.id, target_id=opening.id,  # 赋值
                    rel_type="contains",  # 赋值
                    confidence=min(0.95, best_overlap),  # 赋值
                ))
                # 给门注入宿主墙信息
                opening.properties["host_wall_id"] = best_wall.id
                opening.properties["host_wall_overlap"] = round(best_overlap, 2)

        # ── 3. 走廊-门-房间拓扑（V2：基于边缘距离）──
        # 用 _min_edge_distance 判断门是否连接走廊/房间
        corridors = [e for e in entities if e.type == "corridor"]  # 赋值
        rooms = [e for e in entities if e.type == "room"]  # 赋值
        doors = [e for e in entities if e.type in ("door", "fire_door", "exit_door")]  # 赋值
        
        for door in doors:  # 循环
            for c in corridors:  # 循环
                dist = self._min_edge_distance(door.bbox, c.bbox)  # 赋值
                if dist < 200.0:  # 门边缘距走廊 < 200mm
                    relations.append(SpatialRelation(  # 调用
                        source_id=c.id, target_id=door.id,  # 赋值
                        rel_type="connects_to", distance=dist,  # 赋值
                        via="door",  # 赋值
                    ))
            for r in rooms:  # 循环
                dist = self._min_edge_distance(door.bbox, r.bbox)  # 赋值
                if dist < 200.0:  # 条件判断
                    relations.append(SpatialRelation(  # 调用
                        source_id=r.id, target_id=door.id,  # 赋值
                        rel_type="connects_to", distance=dist,  # 赋值
                        via="door",  # 赋值
                    ))

        # ── 4. 包含关系（房间包含设备/柱）──
        contained_types = {"column", "stair", "exit", "fire_door"}  # 赋值
        containables = [e for e in entities if e.type in contained_types]  # 赋值
        for room in rooms:  # 循环
            for item in containables:  # 循环
                if self._is_inside(item.bbox, room.bbox):  # 条件判断
                    relations.append(SpatialRelation(  # 调用
                        source_id=room.id, target_id=item.id,  # 赋值
                        rel_type="contains", confidence=0.9,  # 赋值
                    ))

        # ── 5. 房间-门间接连接（通过墙传递）──
        # 如果房间与墙相邻，且门被墙包含，则建立房间-门的连接
        # 这样 BFS 才能从房间走到门再到出口
        room_wall_adj = {}  # 赋值
        wall_door_contains = {}  # 赋值
        for rel in relations:  # 循环
            if rel.type == "adjacent":  # 条件判断
                if rel.source_id in {r.id for r in rooms} and rel.target_id in {w.id for w in walls}:  # 条件判断
                    room_wall_adj.setdefault(rel.source_id, set()).add(rel.target_id)  # 调用
                if rel.target_id in {r.id for r in rooms} and rel.source_id in {w.id for w in walls}:  # 条件判断
                    room_wall_adj.setdefault(rel.target_id, set()).add(rel.source_id)  # 调用
            if rel.type == "contains":  # 条件判断
                if rel.source_id in {w.id for w in walls} and rel.target_id in {d.id for d in doors}:  # 条件判断
                    wall_door_contains.setdefault(rel.source_id, set()).add(rel.target_id)  # 调用
        for room_id, wall_ids in room_wall_adj.items():  # 循环
            for wall_id in wall_ids:  # 循环
                for door_id in wall_door_contains.get(wall_id, set()):  # 循环
                    relations.append(SpatialRelation(  # 调用
                        source_id=room_id, target_id=door_id,  # 赋值
                        rel_type="connects_to", distance=0.0,  # 赋值
                        via="door",  # 赋值
                    ))

        return relations  # 返回

    def _bind_dimensions(self, entities: List[SemanticEntity],
                         dimensions: List[Dict]) -> Dict[str, Dict]:
        """尺寸标注绑定到实体"""
        bindings = {}  # 赋值

        for dim in dimensions:  # 循环
            dim_pos = dim.get("position", {})  # 赋值
            if not dim_pos:  # 条件判断
                continue  # 继续循环

            nearest = None  # 赋值
            nearest_dist = float("inf")  # 赋值

            for entity in entities:  # 循环
                center = self._bbox_center(entity.bbox)  # 赋值
                dist = self._point_distance(dim_pos, center)  # 赋值
                if dist < nearest_dist and dist < 500:  # 条件判断
                    nearest = entity  # 赋值
                    nearest_dist = dist  # 赋值

            if nearest:  # 条件判断
                if nearest.id not in bindings:  # 条件判断
                    bindings[nearest.id] = {}  # 操作
                attr_name = self._infer_attribute_name(dim, nearest)  # 赋值
                bindings[nearest.id][attr_name] = dim.get("measurement", 0)

        return bindings  # 返回

    # ── 几何工具函数 ────────────────────────────────────

    @staticmethod
    def _compute_iou(bbox1: Dict, bbox2: Dict) -> float:
        """计算 IoU"""
        x1 = max(bbox1["x"], bbox2["x"])  # 赋值
        y1 = max(bbox1["y"], bbox2["y"])  # 赋值
        x2 = min(bbox1["x"] + bbox1["width"], bbox2["x"] + bbox2["width"])  # 赋值
        y2 = min(bbox1["y"] + bbox1["height"], bbox2["y"] + bbox2["height"])  # 赋值

        if x2 <= x1 or y2 <= y1:  # 条件判断
            return 0.0  # 返回

        intersection = (x2 - x1) * (y2 - y1)  # 赋值
        area1 = bbox1["width"] * bbox1["height"]  # 赋值
        area2 = bbox2["width"] * bbox2["height"]  # 赋值
        union = area1 + area2 - intersection  # 赋值

        return intersection / union if union > 0 else 0.0  # 返回

    @staticmethod
    def _union_bbox(bboxes: List[Dict]) -> Dict[str, float]:
        """合并多个边界框"""
        xs = [b["x"] for b in bboxes]  # 赋值
        ys = [b["y"] for b in bboxes]  # 赋值
        x2s = [b["x"] + b["width"] for b in bboxes]  # 赋值
        y2s = [b["y"] + b["height"] for b in bboxes]  # 赋值
        return {  # 返回
            "x": min(xs), "y": min(ys),
            "width": max(x2s) - min(xs),
            "height": max(y2s) - min(ys),
        }

    @staticmethod
    def _min_edge_distance(bbox1: Dict, bbox2: Dict) -> float:
        """最小边缘距离"""
        x1a, y1a = bbox1["x"], bbox1["y"]
        x2a = x1a + bbox1["width"]  # 赋值
        y2a = y1a + bbox1["height"]  # 赋值
        x1b, y1b = bbox2["x"], bbox2["y"]
        x2b = x1b + bbox2["width"]  # 赋值
        y2b = y1b + bbox2["height"]  # 赋值

        dx = max(x1b - x2a, x1a - x2b, 0)  # 赋值
        dy = max(y1b - y2a, y1a - y2b, 0)  # 赋值
        return (dx**2 + dy**2) ** 0.5  # 返回

    @staticmethod
    def _is_inside(inner: Dict, outer: Dict) -> bool:
        """判断内部"""
        return (inner["x"] >= outer["x"]  # 返回
                and inner["y"] >= outer["y"]
                and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
                and inner["y"] + inner["height"] <= outer["y"] + outer["height"])

    @staticmethod
    def _bbox_center(bbox: Dict) -> Dict[str, float]:
        return {"x": bbox["x"] + bbox["width"] / 2,  # 返回
                "y": bbox["y"] + bbox["height"] / 2}

    @staticmethod
    def _point_distance(p1: Dict, p2: Dict) -> float:
        return ((p1.get("x", 0) - p2.get("x", 0))**2  # 返回
                + (p1.get("y", 0) - p2.get("y", 0))**2) ** 0.5

    @staticmethod
    def _infer_attribute_name(dim: Dict, entity: SemanticEntity) -> str:
        """推断属性名"""
        entity_type = entity.type  # 赋值
        dim_text = dim.get("text", "")  # 赋值

        if entity_type == "wall":  # 条件判断
            return "width"  # 返回
        elif entity_type in ("door", "fire_door"):  # 分支
            return "clear_width"  # 返回
        elif entity_type == "window":  # 分支
            return "width"  # 返回
        elif entity_type == "stair":  # 分支
            return "step_width"  # 返回
        elif entity_type == "corridor":  # 分支
            return "clear_width"  # 返回
        elif entity_type == "fire_zone":  # 分支
            return "area"  # 返回
        else:  # 否则
            return "measurement"  # 返回

    # ── 走廊拓扑网络 ────────────────────────────────────

    def build_corridor_topology(self, entities: List[SemanticEntity],
                                 relations: List[SpatialRelation]) -> Dict[str, Any]:
        """构建走廊拓扑网络
        
        将走廊实体按空间相邻关系连接为图，识别：
        - 连通分量（哪些走廊连通）
        - 死胡同（只有一条连接的走廊段）
        - 疏散路径（走廊到出口的可达性）
        """
        corridor_map = {e.id: e for e in entities if e.type == "corridor"}  # 赋值
        
        if len(corridor_map) < 2:  # 条件判断
            return {  # 返回
                "corridors": [e.to_dict() for e in corridor_map.values()],
                "components": 1,
                "dead_ends": [],
                "network": {"nodes": list(corridor_map.keys()), "edges": []},
            }

        # 构建走廊-走廊相邻图
        adjacency: Dict[str, List[Tuple[str, float]]] = {eid: [] for eid in corridor_map}
        
        for rel in relations:  # 循环
            src = rel.source_id  # 赋值
            tgt = rel.target_id  # 赋值
            if src in corridor_map and tgt in corridor_map and rel.type == "adjacent":  # 条件判断
                adjacency[src].append((tgt, rel.distance))  # 操作
                adjacency[tgt].append((src, rel.distance))  # 操作
        
        # 门连接：门关联的走廊也算连通
        for rel in relations:  # 循环
            if rel.type != "connects_to":  # 条件判断
                continue  # 继续循环
            door_id = rel.target_id  # 赋值
            corridor_id = rel.source_id  # 赋值
            if corridor_id not in corridor_map:  # 条件判断
                continue  # 继续循环
            # 找门连接的另一侧（room或其他走廊）
            for rel2 in relations:  # 循环
                if rel2.source_id == door_id and rel2.target_id != corridor_id:  # 条件判断
                    other_id = rel2.target_id  # 赋值
                    if other_id in corridor_map:  # 条件判断
                        adjacency[corridor_id].append((other_id, rel2.distance))  # 操作
                        adjacency[other_id].append((corridor_id, rel2.distance))  # 操作

        # 找连通分量（BFS）
        visited = set()  # 赋值
        components = []  # 赋值
        for eid in corridor_map:  # 循环
            if eid in visited:  # 条件判断
                continue  # 继续循环
            comp = []  # 赋值
            queue = [eid]  # 赋值
            while queue:  # 循环
                current = queue.pop(0)  # 赋值
                if current in visited:  # 条件判断
                    continue  # 继续循环
                visited.add(current)  # 调用
                comp.append(current)  # 调用
                for neighbor, _ in adjacency.get(current, []):  # 循环
                    if neighbor not in visited:  # 条件判断
                        queue.append(neighbor)  # 调用
            if comp:  # 条件判断
                components.append(comp)  # 调用

        # 找死胡同（度=1的走廊节点）
        dead_ends = []  # 赋值
        for eid, neighbors in adjacency.items():  # 循环
            if len(neighbors) == 1:  # 条件判断
                ent = corridor_map[eid]  # 赋值
                dead_ends.append({  # 调用
                    "id": eid,
                    "width": ent.properties.get("width", 0),
                    "length": ent.properties.get("length", 0),
                    "bbox": ent.bbox,
                })

        # 走廊宽度统计
        widths = [e.properties.get("width", 0) for e in corridor_map.values()]  # 赋值
        valid_widths = [w for w in widths if w > 0]  # 赋值

        return {  # 返回
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
                    for s, neighbors in adjacency.items()  # 循环
                    for t, d in neighbors  # 循环
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
        for e in entities:  # 循环
            adj[e.id] = []  # 赋值
        
        for rel in relations:  # 循环
            if rel.type not in ("adjacent", "connects_to", "contains"):  # 条件判断
                continue  # 继续循环
            adj.setdefault(rel.source_id, []).append((rel.target_id, rel.type, rel.distance))  # 调用
            adj.setdefault(rel.target_id, []).append((rel.source_id, rel.type, rel.distance))  # 调用

                # 出口识别：优先用明确的 exit/exit_door
        strict_exits = [e for e in entities if e.type in ("exit", "exit_door")]  # 赋值
        fallback_exits = [e for e in entities if e.type in ("door", "fire_door")]  # 赋值
        # 有明确出口就用明确出口，否则用 door/fire_door 兜底
        exits = strict_exits if strict_exits else fallback_exits  # 赋值
        
        rooms = [e for e in entities if e.type == "room"]  # 赋值
        
        if not exits:  # 条件判断
            return []  # 返回

        # 无明确 exit 时，room 面积 < 10m² 跳过 EVAC 判定（非疏散空间）
        skip_small_rooms = not strict_exits and bool(fallback_exits)  # 赋值

        # 如果没有 room 但有 corridor，用 corridor 作为起点分析连通性
        if not rooms:  # 条件判断
            corridors = [e for e in entities if e.type == "corridor"]  # 赋值
            if corridors:  # 条件判断
                rooms = corridors  # 兜底：用走廊代替房间作为起点
            else:  # 否则
                return []  # 返回
        
        # 优先用 type=exit 的，兜底用 door/fire_door
        has_exit_type = any(e.type == "exit" for e in exits)  # 赋值
        if not has_exit_type:  # 条件判断
            pass  # 占位

        routes = []  # 赋值
        for room in rooms:  # 循环
            # 兜底模式（无明确exit）且 room 面积 < 10m²：跳过 EVAC 判定
            if skip_small_rooms:  # 条件判断
                bw = room.bbox.get("width", 0)  # 赋值
                bh = room.bbox.get("height", 0)  # 赋值
                area = bw * bh / 1e6  # 赋值
                if area < 10:  # 条件判断
                    route_info = {  # 赋值
                        "room_id": room.id,
                        "room_type": room.type,
                        "room_bbox": room.bbox,
                        "has_route": True,
                        "path_length": None,
                        "exit_id": None,
                    }
                    routes.append(route_info)  # 调用
                    continue  # 继续循环

            # BFS 找最近出口
            visited = {room.id}  # 赋值
            queue = [(room.id, [room.id], 0.0)]  # 赋值
            found_route = None  # 赋值

            while queue:  # 循环
                current, path, distance = queue.pop(0)  # 解包
                if current in {e.id for e in exits}:  # 条件判断
                    found_route = (path, distance)  # 赋值
                    break  # 跳出循环
                for neighbor, rel_type, dist in adj.get(current, []):  # 循环
                    if neighbor not in visited:  # 条件判断
                        visited.add(neighbor)  # 调用
                        queue.append((neighbor, path + [neighbor], distance + dist))  # 调用

            route_info = {  # 赋值
                "room_id": room.id,
                "room_type": room.type,
                "room_bbox": room.bbox,
                "has_route": found_route is not None,
                "path_length": round(found_route[1], 2) if found_route else None,
                "path": found_route[0] if found_route else [],
                "is_dead_end_room": room.properties.get("is_dead_end", False),
                # 死胡同走廊（袋形走道）：疏散距离 ≤ 20m（GB50016-5.5.17注1）
                # 其他走廊/房间：≤ 30m
                "evac_distance_limit": 20.0 if room.properties.get("is_dead_end", False) else 30.0,
                "exceeds_max_distance": found_route is not None and found_route[1] > (20.0 if room.properties.get("is_dead_end", False) else 30.0),
            }
            routes.append(route_info)  # 调用
