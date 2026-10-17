"""T-A4 / 缺口 G9：DIMENSION 尺寸标注 → 实体属性注入链路验证。

覆盖:
1. 单位换算与评分共享工具函数（_measurement_to_meters / _dim_orientation /
   _dim_projection_ratio / _dim_match_score）
2. _bind_dimensions 绑定结果（单位=米、_dimension_raw 追溯、0/缺 position 跳过）
3. analyze() Step 3.5 把绑定结果注入 ent.properties（_dimension_source 标记）
   且不覆盖既有非零 width/clear_width
"""

import pytest

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.baa_engine.semantic_analyzer.relations import (
    _bind_dimensions,
    _dim_orientation,
    _dim_projection_ratio,
    _dim_match_score,
    _measurement_to_meters,
)


def _ent(entity_id, etype, x, y, w, h):
    return SemanticEntity(
        entity_id,
        etype,
        {"x": x, "y": y, "width": w, "height": h},
    )


# ── 1. 共享工具函数 ─────────────────────────────────────


def test_measurement_to_meters_mm():
    """>100 且 /1000 落入 0.3~30m → 判为 mm 并换算。
    900mm→0.9m；3000mm→3.0m。"""
    assert _measurement_to_meters(900) == pytest.approx(0.9)
    assert _measurement_to_meters(3000) == pytest.approx(3.0)


def test_measurement_to_meters_already_m():
    """<=100 的小值视为已是米，原样返回。"""
    assert _measurement_to_meters(1.5) == pytest.approx(1.5)


def test_measurement_to_meters_zero_or_missing():
    """0 / 负值 / None / 非数值 → None（宁可不注入）。"""
    assert _measurement_to_meters(0) is None
    assert _measurement_to_meters(-10) is None
    assert _measurement_to_meters(None) is None
    assert _measurement_to_meters("abc") is None


def test_dim_orientation():
    """由 defpoint2→defpoint3 向量判断水平/垂直/斜向。"""
    dim_h = {"defpoint2": {"x": 0, "y": 0}, "defpoint3": {"x": 3000, "y": 0}}
    dim_v = {"defpoint2": {"x": 0, "y": 0}, "defpoint3": {"x": 0, "y": 3000}}
    dim_d = {"defpoint2": {"x": 0, "y": 0}, "defpoint3": {"x": 100, "y": 100}}
    assert _dim_orientation(dim_h) == "h"
    assert _dim_orientation(dim_v) == "v"
    assert _dim_orientation(dim_d) == ""


def test_dim_projection_ratio_full_overlap():
    """水平标注的 defpoint y 范围完全落在实体 y 范围内 → 重叠比例=1。"""
    dim = {"defpoint2": {"x": 0, "y": 10}, "defpoint3": {"x": 3000, "y": 10}}
    bbox = {"x": 0, "y": 0, "width": 3000, "height": 100}
    assert _dim_projection_ratio(dim, bbox, "h") == pytest.approx(1.0)


def test_dim_projection_ratio_no_overlap():
    """标注与实体在测量轴上无交集 → 0。"""
    dim = {"defpoint2": {"x": 0, "y": 5000}, "defpoint3": {"x": 3000, "y": 5000}}
    bbox = {"x": 5000, "y": 0, "width": 3000, "height": 100}
    assert _dim_projection_ratio(dim, bbox, "h") == pytest.approx(0.0)


def test_dim_match_score_prefers_projection():
    """相同距离下，投影重叠高者评分更低（更优）。"""
    assert _dim_match_score(100, 1.0) < _dim_match_score(100, 0.0)


# ── 2. _bind_dimensions ────────────────────────────────


def test_bind_dimensions_injects_meters_and_raw():
    """墙 + 水平标注 3000mm → 绑定 width=3.0m，附 _dimension_raw=3000。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    dim = {
        "measurement": 3000.0,
        "position": {"x": 1500, "y": 300},
        "text_midpoint": {"x": 1500, "y": 300},
        "defpoint2": {"x": 0, "y": 300},
        "defpoint3": {"x": 3000, "y": 300},
    }
    bindings = _bind_dimensions(None, [wall], [dim])
    assert bindings["W1"]["width"] == pytest.approx(3.0)
    assert bindings["W1"]["_dimension_raw"] == 3000.0
    assert wall.properties["_dimension_raw"] == 3000.0


def test_bind_dimensions_skips_zero_measurement():
    """measurement=0 的标注不绑定（不注入 0）。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    dim = {
        "measurement": 0,
        "text_midpoint": {"x": 1500, "y": 300},
        "defpoint2": {"x": 0, "y": 300},
        "defpoint3": {"x": 3000, "y": 300},
    }
    assert _bind_dimensions(None, [wall], [dim]) == {}


def test_bind_dimensions_skips_missing_position():
    """无 text_midpoint / position 的标注跳过。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    dim = {"measurement": 3000, "defpoint2": {"x": 0, "y": 0}}
    assert _bind_dimensions(None, [wall], [dim]) == {}


# ── 3. analyze() 注入链路 ──────────────────────────────


def test_analyze_injects_dimension_into_wall_properties():
    """墙(无 width) + 水平标注 3000mm → properties.width=3.0 & _dimension_source=relations_bind。"""
    analyzer = SemanticAnalyzer()
    prims = [
        RawPrimitive(
            "LINE", "WALL", "h_wall_t4", {"x": 0, "y": 0, "width": 3000, "height": 0}, {"angle": 0}
        )
    ]
    dims = [
        {
            "measurement": 3000.0,
            "text_midpoint": {"x": 1500, "y": 200},
            "defpoint2": {"x": 0, "y": 200},
            "defpoint3": {"x": 3000, "y": 200},
        }
    ]
    out = analyzer.analyze(prims, dims)
    walls = [e for e in out["entities"] if e["type"] == "wall"]
    assert walls, "未识别出 wall 实体"
    props = walls[0]["properties"]
    assert props.get("width") == pytest.approx(3.0)
    assert props.get("_dimension_source") == "relations_bind"
    assert props.get("_dimension_raw") == 3000.0


def test_analyze_does_not_overwrite_existing_width():
    """门已有 bbox 推断的 clear_width，DIMENSION 不覆盖既有非零值。"""
    analyzer = SemanticAnalyzer()
    prims = [
        RawPrimitive(
            "LINE", "DOOR", "h_door_t4", {"x": 0, "y": 0, "width": 900, "height": 0}, {"angle": 0}
        )
    ]
    dims = [
        {
            "measurement": 1200.0,
            "text_midpoint": {"x": 450, "y": 200},
            "defpoint2": {"x": 0, "y": 200},
            "defpoint3": {"x": 1200, "y": 200},
        }
    ]
    out = analyzer.analyze(prims, dims)
    doors = [e for e in out["entities"] if e["type"] == "door"]
    assert doors, "未识别出 door 实体"
    props = doors[0]["properties"]
    # 既有 clear_width 由 bbox 兜底（0.9m），不应被 1.2m 覆盖
    assert props.get("clear_width") == pytest.approx(0.9)
    assert props.get("_dimension_source") is None
