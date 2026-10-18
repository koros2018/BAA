"""T-A4 / 缺口 G9：T3 native 实例字段 + 线元几何长度注入验证（Step 3.7）。

覆盖:
1. 墙 _t3_wall_seg → width=厚度 / length=跨度（mm→m）
2. 窗 _t3_window_bbox → width=洞口跨度；柱 bbox → width/height
3. bbox 退化线元 → length=长边（真实跨度），宽度不做几何臆测
4. 区间双保险、不覆盖既有非零值、_attribute_source 追溯
"""

import pytest

from src.baa_engine.semantic_analyzer.geometry_attributes import (
    _inject_geometry_attributes,
    _inject_geometry_lengths,
    _inject_native_instance_fields,
)
from src.baa_engine.semantic_analyzer.models import SemanticEntity


def _ent(entity_id, etype, x, y, w, h, props=None):
    e = SemanticEntity(entity_id, etype, {"x": x, "y": y, "width": w, "height": h})
    if props:
        e.properties.update(props)
    return e


# ── 1. T3 墙 seg 字段提升 ────────────────────────────────


def test_t3_wall_seg_injects_width_and_length():
    """seg 厚度 200mm/跨度 5400mm → wall.width=0.2, length=5.4, source=t3_native。"""
    wall = _ent("W1", "wall", 0, 0, 5400, 200, {
        "_t3_wall_seg": {"orientation": "h", "pos": 100, "start": 0, "end": 5400, "thickness": 200},
    })
    out = _inject_native_instance_fields([wall])
    assert out[0].properties["width"] == pytest.approx(0.2)
    assert out[0].properties["length"] == pytest.approx(5.4)
    assert out[0].properties["_attribute_source"] == "t3_native"


def test_t3_single_wall_thickness_none_only_length():
    """single 未配对面墙 thickness=None → 只注入 length，不臆测厚度。"""
    wall = _ent("W2", "wall", 0, 0, 3000, 1, {
        "_t3_wall_seg": {"orientation": "h", "pos": 50, "start": 0, "end": 3000, "thickness": None},
    })
    out = _inject_native_instance_fields([wall])
    assert "width" not in out[0].properties
    assert out[0].properties["length"] == pytest.approx(3.0)


def test_t3_wall_thickness_out_of_range_skipped():
    """厚度 2000mm 超出 0.05~1.0m 合理区间 → 不注入。"""
    wall = _ent("W3", "wall", 0, 0, 5000, 2000, {
        "_t3_wall_seg": {"orientation": "h", "pos": 1000, "start": 0, "end": 5000, "thickness": 2000},
    })
    out = _inject_native_instance_fields([wall])
    assert "width" not in out[0].properties
    assert out[0].properties["length"] == pytest.approx(5.0)


# ── 2. T3 窗/柱字段提升 ──────────────────────────────────


def test_t3_window_bbox_injects_width():
    """_t3_window_bbox 1200×200（mm）→ window.width=1.2。"""
    win = _ent("WIN1", "window", 0, 0, 1200, 200, {
        "_t3_window_bbox": {"x": 0, "y": 0, "width": 1200, "height": 200},
    })
    out = _inject_native_instance_fields([win])
    assert out[0].properties["width"] == pytest.approx(1.2)
    assert "height" not in out[0].properties


def test_t3_column_bbox_injects_width_height():
    """分解态柱 bbox 378×300（mm）→ column.width=0.3, height=0.378。"""
    col = _ent("C1", "column", 0, 0, 378, 300, {"_t3_native": "column"})
    out = _inject_native_instance_fields([col])
    assert out[0].properties["width"] == pytest.approx(0.3)
    assert out[0].properties["height"] == pytest.approx(0.378)


def test_non_column_with_t3_marker_ignored():
    """_t3_native=column 但实体类型非 column → 不注入（防跨类污染）。"""
    ent = _ent("X1", "wall", 0, 0, 378, 300, {"_t3_native": "column"})
    out = _inject_native_instance_fields([ent])
    assert "width" not in out[0].properties


# ── 3. 退化线元长度注入 ──────────────────────────────────


def test_degenerate_wall_gets_length_not_width():
    """水平墙线 bbox 3000×0 → length=3.0；width 不做几何臆测。"""
    wall = _ent("W4", "wall", 0, 0, 3000, 0)
    out = _inject_geometry_lengths([wall])
    assert out[0].properties["length"] == pytest.approx(3.0)
    assert out[0].properties["_attribute_source"] == "geometry_length"
    assert "width" not in out[0].properties


def test_degenerate_door_gets_length_only():
    """门洞线 bbox 900×0 → length=0.9（净宽留给尺寸/TEXT 链路）。"""
    door = _ent("D1", "door", 0, 0, 0, 900)
    out = _inject_geometry_lengths([door])
    assert out[0].properties["length"] == pytest.approx(0.9)
    assert "width" not in out[0].properties


def test_non_degenerate_entity_skipped():
    """bbox 非退化（2000×1500 楼梯间）→ 不注入（短边非零非线元）。"""
    stair = _ent("S1", "stair", 0, 0, 2000, 1500)
    out = _inject_geometry_lengths([stair])
    assert "length" not in out[0].properties


def test_tiny_fragment_skipped():
    """<300mm 碎片线元不注入。"""
    frag = _ent("F1", "wall", 0, 0, 200, 0)
    out = _inject_geometry_lengths([frag])
    assert "length" not in out[0].properties


def test_existing_length_not_overwritten():
    """已有非零 length 不覆盖。"""
    wall = _ent("W5", "wall", 0, 0, 3000, 0, {"length": 2.5})
    out = _inject_geometry_lengths([wall])
    assert out[0].properties["length"] == pytest.approx(2.5)


def test_geometry_length_after_text_width_no_conflict():
    """TEXT 已注入 width=0.2 的墙 → 几何只补 length，width 保持 0.2。"""
    wall = _ent("W6", "wall", 0, 0, 3000, 0, {"width": 0.2, "_attribute_source": "text_thickness"})
    out = _inject_geometry_attributes(None, [wall], [])
    assert out[0].properties["width"] == pytest.approx(0.2)
    assert out[0].properties["length"] == pytest.approx(3.0)
    assert out[0].properties["_attribute_source"] == "geometry_length"


def test_other_type_skipped():
    """other/设备类不做长度注入（防噪声）。"""
    ent = _ent("O1", "other", 0, 0, 3000, 0)
    out = _inject_geometry_lengths([ent])
    assert "length" not in out[0].properties


def test_empty_entities_noop():
    assert _inject_geometry_attributes(None, [], []) == []
