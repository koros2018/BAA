"""
BAA 语义识别引擎 — 数据模型
SemanticEntity + SpatialRelation 数据类定义
"""

from typing import Dict, Any


class SemanticEntity:
    """语义化图元"""

    def __init__(
        self,
        entity_id: str,
        entity_type: str,
        bbox: Dict[str, float],
        layer: str = "",
        subtype: str = "",
        confidence: float = 1.0,
        properties: Dict[str, Any] = None,
    ):
        """初始化实例。"""
        self.id = entity_id
        self.type = entity_type
        self.bbox = bbox
        self.layer = layer
        self.subtype = subtype
        self.confidence = confidence
        self.properties = properties or {}

    def to_dict(self) -> dict:
        """序列化为字典。"""
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
    """空间关系（相邻/包含/连接）"""

    def __init__(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        distance: float = 0,
        via: str = "",
        confidence: float = 1.0,
    ):
        """初始化实例。"""
        self.source_id = source_id
        self.target_id = target_id
        self.type = rel_type  # adjacent / contains / connects_to
        self.distance = distance
        self.via = via
        self.confidence = confidence
