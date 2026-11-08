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


# ── COUNT-001：仅 fire_zone/fire_compartment 作用域聚合 ──────


def _zone(entity_id, x, y, w, h):
    return SemanticEntity(entity_id, "fire_zone", {"x": x, "y": y, "width": w, "height": h})


def _exit(entity_id, x, y):
    return SemanticEntity(entity_id, "exit", {"x": x, "y": y, "width": 100, "height": 100})


def test_zone_exit_count_inside():
    """分区 100×100m 内含 1 个出口 → exit_count=1。"""
    zone = _zone("Z1", 0, 0, 100000, 100000)
    exits = [_exit("E1", 50000, 50000)]
    SemanticAnalyzer()._inject_zone_exit_counts([zone] + exits)
    assert zone.properties.get("exit_count") == 1
    assert zone.properties.get("_exit_count_source") == "zone_bbox"


def test_zone_exit_count_only_counts_inside():
    """分区外出口不计入；分区内 2 个 → exit_count=2。"""
    zone = _zone("Z1", 0, 0, 100000, 100000)
    exits = [_exit("E1", 30000, 30000), _exit("E2", 70000, 70000), _exit("E3", 200000, 200000)]
    SemanticAnalyzer()._inject_zone_exit_counts([zone] + exits)
    assert zone.properties.get("exit_count") == 2


def test_zone_without_exit_keeps_none():
    """分区内没有出口实体 → 不写 0（缺符号不等于出口不足）。"""
    zone = _zone("Z1", 0, 0, 100000, 100000)
    far = _exit("E9", 300000, 300000)
    SemanticAnalyzer()._inject_zone_exit_counts([zone, far])
    assert zone.properties.get("exit_count") is None


def test_floor_never_gets_exit_count():
    """没有 fire_zone 时，floor 标签不得摊派全图出口数。"""
    floor = _floor("FLOOR_2729", 560, 373, props={"text": "负一层地下室顶板结构降板"})
    exits = [_exit("E1", 50000, 50000)]
    SemanticAnalyzer()._inject_zone_exit_counts([floor] + exits)
    assert floor.properties.get("exit_count") is None


def test_small_zone_not_a_scope():
    """bbox 小于 25㎡ 的分区（文字/图例块退化几何）不作为作用域。"""
    zone = _zone("Z1", 0, 0, 2000, 2000)  # 4㎡
    exits = [_exit("E1", 1000, 1000)]
    SemanticAnalyzer()._inject_zone_exit_counts([zone] + exits)
    assert zone.properties.get("exit_count") is None


def _room(entity_id, w, h, props=None):
    e = SemanticEntity(entity_id, "room", {"x": 0, "y": 0, "width": w, "height": h})
    if props:
        e.properties.update(props)
    return e


def test_room_area_correction_skips_closed_region():
    """closed=True 的三角/L 形房间：bbox 不得越权覆盖 polygon 面积。"""
    ent = _room("R1", 4000, 4000, props={"area_m2": 8.0, "point_count": 3, "closed": True})
    SemanticAnalyzer()._correct_unclosed_room_area([ent])
    assert ent.properties["area_m2"] == pytest.approx(8.0)
    assert "_area_correction" not in ent.properties


def test_room_area_correction_skips_sweep_faces():
    """point_count=0（扫线面遍历房间）不按未合龙处理：东莞通 L 形 96.28 ㎡ 不得放大到 256.63。"""
    ent = _room("R2", 23460, 10939, props={"area_m2": 96.28})
    SemanticAnalyzer()._correct_unclosed_room_area([ent])
    assert ent.properties["area_m2"] == pytest.approx(96.28)
    assert "_area_correction" not in ent.properties


def test_room_area_correction_still_fixes_unclosed_triangle():
    """未闭合 3 点指纹（closed=False）仍按 bbox 修正，保留原面积供审计。"""
    ent = _room("R3", 4000, 4000, props={"area_m2": 8.0, "point_count": 3, "closed": False})
    SemanticAnalyzer()._correct_unclosed_room_area([ent])
    assert ent.properties["area_m2"] == pytest.approx(16.0)
    assert ent.properties["_polygon_area"] == pytest.approx(8.0)
    assert ent.properties["_area_correction"] == "bbox_unclosed"


def test_room_area_correction_still_fixes_low_ratio_polygon():
    """ratio<0.5 且有多边形顶点证据（point_count=4）→ 仍按 bbox 修正。"""
    ent = _room("R4", 7000, 2550, props={"area_m2": 6.06, "point_count": 4})
    SemanticAnalyzer()._correct_unclosed_room_area([ent])
    assert ent.properties["area_m2"] == pytest.approx(17.85)
    assert ent.properties["_area_correction"] == "bbox_unclosed"
