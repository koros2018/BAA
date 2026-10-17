"""T-A4 / 缺口 G9：TEXT/MTEXT 标注 → 图元属性注入验证。

覆盖:
1. 文本解析（厚度 _parse_thickness_m / 门窗编号 _parse_opening_code）
2. _inject_text_attributes 就近注入（厚度→wall.width、编号→door width/height）
3. 不覆盖既有非零值、越界值不注入、无 TEXT 时不动作
"""

import pytest

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.baa_engine.semantic_analyzer.text_attributes import (
    _inject_text_attributes,
    _parse_opening_code,
    _parse_thickness_m,
)


def _ent(entity_id, etype, x, y, w, h, props=None):
    e = SemanticEntity(entity_id, etype, {"x": x, "y": y, "width": w, "height": h})
    if props:
        e.properties.update(props)
    return e


def _text(text, x, y, w=200, h=200):
    return RawPrimitive("TEXT", "标注", "t", {"x": x, "y": y, "width": w, "height": h}, {"text": text})


# ── 1. 厚度解析 ─────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expect",
    [
        ("200厚", 0.2),
        ("厚200", 0.2),
        ("墙厚200", 0.2),
        ("200mm厚", 0.2),
        ("200 mm 厚", 0.2),
        ("混凝土墙200", 0.2),
        ("100厚", 0.1),
    ],
)
def test_parse_thickness_patterns(text, expect):
    assert _parse_thickness_m(text) == pytest.approx(expect)


def test_parse_thickness_out_of_range():
    """<50mm 或 >1000mm 的数值不视为构件厚度。"""
    assert _parse_thickness_m("1.5mm厚镀锌铁皮") is None
    assert _parse_thickness_m("4厚1：2水泥砂浆") is None
    assert _parse_thickness_m("没有厚度标注") is None


# ── 2. 门窗编号解析 ──────────────────────────────────────


def test_parse_opening_code_door():
    """M0921 → 门 900×2100（dm 编码，每对 ×100mm）。"""
    assert _parse_opening_code("M0921") == ("door", pytest.approx(0.9), pytest.approx(2.1))


def test_parse_opening_code_window_height_unknown():
    """C1200 → 窗宽 1.2m，高 00 视为未知（None）。"""
    kind, w, h = _parse_opening_code("C1200")
    assert kind == "window"
    assert w == pytest.approx(1.2)
    assert h is None


def test_parse_opening_code_fire_door_with_grade():
    """FM甲1524 → 防火门 1500×2400。"""
    assert _parse_opening_code("FM甲1524") == (
        "fire_door",
        pytest.approx(1.5),
        pytest.approx(2.4),
    )


def test_parse_opening_code_no_match():
    """裸数字 / 非编号文本不解析。"""
    assert _parse_opening_code("1500*2500") is None
    assert _parse_opening_code("M") is None


# ── 3. 注入链路 ─────────────────────────────────────────


def test_inject_thickness_into_wall():
    """「200厚」→ 就近 wall.width=0.2 & _attribute_source=text_thickness。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    prims = [_text("200厚", 1400, 100)]
    out = _inject_text_attributes(None, [wall], prims)
    assert out[0].properties.get("width") == pytest.approx(0.2)
    assert out[0].properties.get("_attribute_source") == "text_thickness"


def test_inject_thickness_into_slab_uses_thickness_attr():
    """「120厚」→ 就近 slab.thickness=0.12（板厚属性名用 thickness）。"""
    slab = _ent("S1", "slab", 0, 0, 4000, 3000)
    prims = [_text("120厚", 100, 100)]
    umts = _inject_text_attributes(None, [slab], prims)
    assert umts[0].properties.get("thickness") == pytest.approx(0.12)


def test_inject_opening_code_into_door():
    """M0921 → 就近 door width=0.9 / clear_width=0.9 / height=2.1。"""
    door = _ent("D1", "door", 0, 0, 900, 0)
    prims = [_text("M0921", 400, 100)]
    out = _inject_text_attributes(None, [door], prims)
    p = out[0].properties
    assert p.get("width") == pytest.approx(0.9)
    assert p.get("clear_width") == pytest.approx(0.9)
    assert p.get("height") == pytest.approx(2.1)
    assert p.get("_attribute_source") == "text_code"


def test_inject_opening_code_into_window():
    """C1200 → 就近 window width=1.2，高未知不注入。"""
    win = _ent("WIN1", "window", 0, 0, 3000, 0)
    prims = [_text("C1200", 1400, 100)]
    out = _inject_text_attributes(None, [win], prims)
    p = out[0].properties
    assert p.get("width") == pytest.approx(1.2)
    assert "height" not in p or not p.get("height")


def test_does_not_overwrite_existing_nonzero():
    """既有非零 width/clear_width 不被 TEXT 覆盖。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200, props={"width": 0.3})
    door = _ent("D1", "door", 4000, 0, 900, 0, props={"width": 0.8})
    prims = [_text("200厚", 1400, 100), _text("M0921", 4200, 100, w=400)]
    out = _inject_text_attributes(None, [wall, door], prims)
    assert out[0].properties.get("width") == pytest.approx(0.3)
    assert out[0].properties.get("_attribute_source") is None
    assert out[1].properties.get("width") == pytest.approx(0.8)


def test_out_of_range_not_injected():
    """越界厚度（4厚→4m、1.5mm→0.0015m）不注入。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    prims = [_text("4厚1：2水泥砂浆", 1400, 100)]
    out = _inject_text_attributes(None, [wall], prims)
    assert out[0].properties.get("width") is None
    assert out[0].properties.get("_attribute_source") is None


def test_thickness_not_bound_to_wrong_type():
    """«200厚» 就近只有 door（非墙/板）时不注入。"""
    door = _ent("D1", "door", 0, 0, 900, 0)
    prims = [_text("200厚", 400, 100)]
    out = _inject_text_attributes(None, [door], prims)
    assert out[0].properties.get("width") is None


def test_no_text_no_action():
    """无 TEXT/MTEXT 时实体属性不变、无来源标记。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    prims = [
        RawPrimitive("LINE", "WALL", "l1", {"x": 0, "y": 0, "width": 3000, "height": 0}, {"angle": 0})
    ]
    out = _inject_text_attributes(None, [wall], prims)
    assert out[0].properties.get("width") is None
    assert out[0].properties.get("_attribute_source") is None


def test_distance_threshold_skips_far_text():
    """标注距构件超过阈值（3m）不注入。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    prims = [_text("200厚", 9000, 9000)]
    out = _inject_text_attributes(None, [wall], prims)
    assert out[0].properties.get("width") is None
