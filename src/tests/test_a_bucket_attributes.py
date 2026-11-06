"""A 桶属性补齐回归：AREA-001 闭合区域 bbox 面积。"""

import pytest

from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.models import SemanticEntity


def _floor(entity_id, w, h, props=None):
    e = SemanticEntity(entity_id, "floor", {"x": 0, "y": 0, "width": w, "height": h})
    if props:
        e.properties.update(props)
    return e


def test_floor_closed_region_gets_bbox_area():
    """closed=True 的 floor 区域：10m×8m → 80.00㎡，area_source=bbox。"""
    ent = _floor("F1", 10000, 8000, props={"closed": True})
    SemanticAnalyzer()._inject_floor_bbox_area([ent])
    assert ent.properties.get("area") == pytest.approx(80.0)
    assert ent.properties.get("area_m2") == pytest.approx(80.0)
    assert ent.properties.get("area_source") == "bbox"
    assert ent.properties.get("_area_source") == "bbox_floor_region"


def test_floor_polygon_region_gets_bbox_area():
    """point_count>=3 的多边形区域同样落 bbox 面积。"""
    ent = _floor("F2", 5000, 4000, props={"point_count": 4})
    SemanticAnalyzer()._inject_floor_bbox_area([ent])
    assert ent.properties.get("area") == pytest.approx(20.0)
    assert ent.properties.get("area_source") == "bbox"


def test_floor_text_label_not_area():
    """东莞通 FLOOR_2729：TEXT 标签，即使 bbox 有宽高也不落面积。"""
    ent = _floor(
        "FLOOR_2729", 560.0, 373.333333,
        props={"text": "负一层地下室顶板结构降板", "floor": "F1"},
    )
    SemanticAnalyzer()._inject_floor_bbox_area([ent])
    assert ent.properties.get("area") is None
    assert ent.properties.get("area_source") is None


def test_floor_line_not_area():
    """villa FLOOR_409：LINE（start/end 点）不落面积。"""
    ent = _floor(
        "FLOOR_409", 1772.75, 0.0,
        props={"start_point": {"x": 0, "y": 0}, "end_point": {"x": 1772.75, "y": 0}},
    )
    SemanticAnalyzer()._inject_floor_bbox_area([ent])
    assert ent.properties.get("area") is None


def test_floor_arc_not_area():
    """villa FLOOR_606：ARC（radius）外接 bbox 194㎡，不得当作面积。"""
    ent = _floor(
        "FLOOR_606", 13961.9, 13961.9,
        props={"radius": 6980.95, "start_angle": 157.8, "end_angle": 178.2},
    )
    SemanticAnalyzer()._inject_floor_bbox_area([ent])
    assert ent.properties.get("area") is None
    assert ent.properties.get("area_source") is None


def test_floor_existing_area_not_overwritten():
    """已有 area 的 floor 不被 bbox 覆盖。"""
    ent = _floor("F3", 10000, 8000, props={"closed": True, "area": 50.0})
    SemanticAnalyzer()._inject_floor_bbox_area([ent])
    assert ent.properties.get("area") == pytest.approx(50.0)
    assert ent.properties.get("area_source") is None
