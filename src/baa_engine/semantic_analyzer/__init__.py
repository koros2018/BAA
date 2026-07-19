"""
BAA 语义识别引擎 — 包入口
兼容导出：保持 `from src.baa_engine.semantic_analyzer import SemanticAnalyzer` 可用
"""

from .main import SemanticAnalyzer, LAYER_RULES, SHORT_LAYER_RULES
from .models import SemanticEntity, SpatialRelation
from .geometry import (
    compute_iou,
    union_bbox,
    min_edge_distance,
    is_inside,
    bbox_center,
    point_distance,
)

__all__ = [
    "SemanticAnalyzer",
    "SemanticEntity",
    "SpatialRelation",
    "LAYER_RULES",
    "SHORT_LAYER_RULES",
    "compute_iou",
    "union_bbox",
    "min_edge_distance",
    "is_inside",
    "bbox_center",
    "point_distance",
]
