"""
BAA 语义识别引擎 — 几何工具函数
IoU / 边界框合并 / 边缘距离 / 包含判断 / 中心点 / 点距离
"""

from typing import List, Dict


def compute_iou(bbox1: Dict, bbox2: Dict) -> float:
    """计算两个边界框的 IoU"""
    x1 = max(bbox1["x"], bbox2["x"])
    y1 = max(bbox1["y"], bbox2["y"])
    x2 = min(bbox1["x"] + bbox1["width"], bbox2["x"] + bbox2["width"])
    y2 = min(bbox1["y"] + bbox1["height"], bbox2["y"] + bbox2["height"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = bbox1["width"] * bbox1["height"]
    area2 = bbox2["width"] * bbox2["height"]
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def union_bbox(bboxes: List[Dict]) -> Dict[str, float]:
    """合并多个边界框"""
    xs = [b["x"] for b in bboxes]
    ys = [b["y"] for b in bboxes]
    x2s = [b["x"] + b["width"] for b in bboxes]
    y2s = [b["y"] + b["height"] for b in bboxes]
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(x2s) - min(xs),
        "height": max(y2s) - min(ys),
    }


def min_edge_distance(bbox1: Dict, bbox2: Dict) -> float:
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


def is_inside(inner: Dict, outer: Dict) -> bool:
    """判断 inner 是否在 outer 内部"""
    return (
        inner["x"] >= outer["x"]
        and inner["y"] >= outer["y"]
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"]
    )


def bbox_center(bbox: Dict) -> Dict[str, float]:
    """边界框中心点"""
    return {
        "x": bbox["x"] + bbox["width"] / 2,
        "y": bbox["y"] + bbox["height"] / 2,
    }


def point_distance(p1: Dict, p2: Dict) -> float:
    """两点欧氏距离"""
    return ((p1.get("x", 0) - p2.get("x", 0)) ** 2 + (p1.get("y", 0) - p2.get("y", 0)) ** 2) ** 0.5
