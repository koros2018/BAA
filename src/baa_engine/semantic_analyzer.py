"""
BAA 语义识别引擎 - 图元分类 + 空间关系构建（规则版）
"""
from typing import List, Dict, Any, Optional, Tuple
from .drawing_parser import RawPrimitive


# ── 图层规则表 ────────────────────────────────────────────

LAYER_RULES = {
    "WALL": "wall", "墙体": "wall", "墙": "wall", "W": "wall",
    "DOOR": "door", "门": "door", "M": "door", "D": "door",
    "WINDOW": "window", "窗": "window", "C": "window", "WIND": "window",
    "STAIR": "stair", "楼梯": "stair", "ST": "stair", "STAIRS": "stair",
    "CORRIDOR": "corridor", "走道": "corridor", "走廊": "corridor",
    "FIRE_ZONE": "fire_zone", "防火分区": "fire_zone", "FZ": "fire_zone",
    "DIM": "dimension", "标注": "dimension", "尺寸": "dimension",
    "DIMENSION": "dimension",
    "EXIT": "exit", "出口": "exit", "安全出口": "exit",
    "FIRE_DOOR": "fire_door", "防火门": "fire_door", "FD": "fire_door",
    "FIRE_ELEV": "fire_elevator", "消防电梯": "fire_elevator", "FE": "fire_elevator",
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
                dimensions: List[Dict] = None) -> Dict[str, Any]:
        """
        执行语义分析

        输入: 原始图元列表（来自 drawing_parser）
        输出: 结构化语义数据（entities + relations + attributes）
        """
        self._entity_counter = 0

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)

        # Step 2: 空间关系构建
        relations = self._build_relations(entities)

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])

        return {
            "entities": [e.to_dict() for e in entities],
            "relations": [self._rel_to_dict(r) for r in relations],
            "attributes": attributes,
        }

    def _classify_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
        """图元分类归并"""
        entities = []

        for prim in primitives:
            # 图层规则匹配
            entity_type = self._classify_by_layer(prim.layer)
            if entity_type == "unknown":
                entity_type = self._classify_by_geometry(prim)

            if entity_type == "unknown":
                continue

            self._entity_counter += 1
            entity = SemanticEntity(
                entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",
                entity_type=entity_type,
                bbox=prim.bbox,
                layer=prim.layer,
                confidence=0.9 if entity_type != "unknown" else 0.5,
                properties=prim.properties,
            )
            entities.append(entity)

        # 归并同类重叠图元
        entities = self._merge_overlapping(entities)

        return entities

    def _classify_by_layer(self, layer: str) -> str:
        """图层规则归类"""
        if not layer:
            return "unknown"
        layer_upper = layer.upper()
        for keyword, entity_type in LAYER_RULES.items():
            if keyword in layer_upper:
                return entity_type
        return "unknown"

    def _classify_by_geometry(self, prim: RawPrimitive) -> str:
        """几何特征兜底归类"""
        dxf_type = prim.dxf_type
        bbox = prim.bbox
        area = bbox.get("width", 0) * bbox.get("height", 0)
        props = prim.properties

        if dxf_type == "LINE":
            length = props.get("length", 0)
            if length > 1000:
                return "wall"
            return "corridor"

        if dxf_type in ("LWPOLYLINE", "POLYLINE"):
            if area > 50000:
                return "wall"
            elif area > 5000:
                return "room"
            return "corridor"

        if dxf_type == "CIRCLE":
            radius = props.get("radius", 0)
            if radius > 1000:
                return "stair"
            return "column"

        if dxf_type == "TEXT":
            text = props.get("text", "")
            if "出口" in text or "EXIT" in text.upper():
                return "exit"
            return "text"

        return "unknown"

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
        """构建空间关系"""
        relations = []

        # 相邻关系
        for i, a in enumerate(entities):
            for b in entities[i+1:]:
                dist = self._min_edge_distance(a.bbox, b.bbox)
                if dist < self.ADJACENT_THRESHOLD:
                    relations.append(SpatialRelation(
                        source_id=a.id, target_id=b.id,
                        rel_type="adjacent", distance=dist,
                        confidence=1.0 - dist / self.ADJACENT_THRESHOLD,
                    ))

        # 包含关系（墙体包含门/窗）
        walls = [e for e in entities if e.type == "wall"]
        openings = [e for e in entities if e.type in ("door", "window", "fire_door")]
        for wall in walls:
            for opening in openings:
                if self._is_inside(opening.bbox, wall.bbox):
                    relations.append(SpatialRelation(
                        source_id=wall.id, target_id=opening.id,
                        rel_type="contains", confidence=0.95,
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