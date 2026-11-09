"""Task 1/2：房间多边形完整性与几何合理性门禁 —— 单元测试

覆盖：
  - _polygon_props：闭合点剥离、非法顶点拒绝
  - _is_simple_polygon：矩形/L 形通过，蝴蝶形（自交）拒绝
  - _suppress_implausible_rooms：A 退化 / C 重复 / D 容器 / E 空壳 / F 图框 / G 自交
  - 反面用例：真实大房间（带房间名/带洞口/展厅）不得被误杀
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.baa_engine.semantic_analyzer.room import (
    _is_simple_polygon,
    _merge_room_sources,
    _polygon_props,
    _sweep_line_detect_rooms,
    _suppress_implausible_rooms,
)


def _rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _room(eid, bbox, pts, etype="room", **props):
    p = {"points": pts, "point_count": len(pts), "closed": True}
    p.update(props)
    return SemanticEntity(
        entity_id=eid,
        entity_type=etype,
        bbox=bbox,
        properties=p,
    )


def _box_entity(eid, etype, x, y, w, h, **props):
    return SemanticEntity(
        entity_id=eid,
        entity_type=etype,
        bbox={"x": x, "y": y, "width": w, "height": h},
        properties=props,
    )


# ── _polygon_props ──


def test_polygon_props_strips_closing_point():
    pts = [[0, 0], [4000, 0], [4000, 3000], [0, 3000], [0, 0]]
    p = _polygon_props(pts)
    assert p["closed"] is True
    assert p["point_count"] == 4
    assert len(p["points"]) == 4
    assert p["points"][0] == [0.0, 0.0]


def test_polygon_props_rejects_degenerate():
    assert _polygon_props([[0, 0], [1000, 0]]) == {}
    assert _polygon_props([]) == {}
    assert _polygon_props(None) == {}
    assert _polygon_props([[0, 0], ["bad", 0], [1, 1]]) == {}


def test_closed_polyline_room_carries_points():
    """直接闭合 LWPOLYLINE 构造路径必须落盘 points（Task 1 根因回归）。"""
    prim = RawPrimitive(
        "LWPOLYLINE",
        "WALL",
        "pl1",
        {"x": 0, "y": 0, "width": 8000, "height": 6000},
        {"points": [[0, 0], [8000, 0], [8000, 6000], [0, 6000]]},
    )

    rooms = SemanticAnalyzer()._sweep_line_detect_rooms([prim])
    assert len(rooms) == 1
    props = rooms[0].properties
    assert props["points"], "room 缺 points"
    assert props["point_count"] == 4
    assert props["closed"] is True
    assert props["area"] == pytest.approx(48.0)


# ── 房间来源并存（闭合多段线 vs 面遍历） ──


def _line(chandle, x0, y0, x1, y1, layer="WALL"):
    return RawPrimitive(
        "LINE",
        layer,
        chandle,
        {
            "x": min(x0, x1),
            "y": min(y0, y1),
            "width": abs(x1 - x0),
            "height": abs(y1 - y0),
        },
        {"start_point": {"x": x0, "y": y0}, "end_point": {"x": x1, "y": y1}},
    )


def _rect_walls(x0, y0, w, h, prefix):
    return [
        _line(f"{prefix}_b", x0, y0, x0 + w, y0),
        _line(f"{prefix}_r", x0 + w, y0, x0 + w, y0 + h),
        _line(f"{prefix}_t", x0 + w, y0 + h, x0, y0 + h),
        _line(f"{prefix}_l", x0, y0 + h, x0, y0),
    ]


def test_polyline_room_and_sweep_room_coexist():
    """回归：有闭合多段线房间时，独立的面遍历房间不得被提前 return 短路丢弃。"""
    poly = RawPrimitive(
        "LWPOLYLINE",
        "WALL",
        "pl1",
        {"x": 0, "y": 0, "width": 4000, "height": 4000},
        {"points": _rect(0, 0, 4000, 4000), "closed": True},
    )
    lines = _rect_walls(10000, 0, 5000, 5000, "box")

    rooms = SemanticAnalyzer()._sweep_line_detect_rooms([poly] + lines)
    ids = [r.id for r in rooms]
    assert any(i.startswith("polyline_") for i in ids), ids
    assert any(i.startswith("line_chain_") for i in ids), ids
    assert len(rooms) == 2


def test_merge_keeps_only_explicit_for_same_space():
    """同一空间：显式几何（闭合多段线）保留，面遍历副本丢弃。"""
    pts = _rect(0, 0, 4000, 4000)
    bbox = {"x": 0, "y": 0, "width": 4000, "height": 4000}
    explicit = _room("polyline_room_1", bbox, pts, area=16.0)
    derived = _room("line_chain_room_2", bbox, pts, area=16.0)
    merged = _merge_room_sources([explicit], [derived])
    assert [e.id for e in merged] == ["polyline_room_1"]


def test_merge_keeps_both_for_different_space():
    """不同空间（不相交）：两个来源都保留。"""
    explicit = _room(
        "polyline_room_1",
        {"x": 0, "y": 0, "width": 4000, "height": 4000},
        _rect(0, 0, 4000, 4000),
        area=16.0,
    )
    derived = _room(
        "line_chain_room_2",
        {"x": 20000, "y": 0, "width": 4000, "height": 4000},
        _rect(20000, 0, 4000, 4000),
        area=16.0,
    )
    merged = _merge_room_sources([explicit], [derived])
    assert {e.id for e in merged} == {"polyline_room_1", "line_chain_room_2"}


def test_merge_keeps_both_when_area_differs():
    """质心相近但面积差 >30%（子区域/局部面）：不得当作同一空间丢弃。"""
    explicit = _room(
        "polyline_room_1",
        {"x": 0, "y": 0, "width": 8000, "height": 6000},
        _rect(0, 0, 8000, 6000),
        area=48.0,
    )
    derived = _room(
        "line_chain_room_2",
        {"x": 1000, "y": 1000, "width": 2000, "height": 2000},
        _rect(1000, 1000, 2000, 2000),
        area=4.0,
    )
    merged = _merge_room_sources([explicit], [derived])
    assert {e.id for e in merged} == {"polyline_room_1", "line_chain_room_2"}


# ── _is_simple_polygon ──


def test_simple_polygons_pass():
    assert _is_simple_polygon(_rect(0, 0, 4000, 3000)) is True
    # L 形
    assert _is_simple_polygon([[0, 0], [6000, 0], [6000, 3000], [3000, 3000],
                               [3000, 6000], [0, 6000]]) is True
    # 三角形
    assert _is_simple_polygon([[0, 0], [4000, 0], [0, 3000]]) is True


def test_bowtie_polygon_rejected():
    assert _is_simple_polygon([[0, 0], [4000, 3000], [4000, 0], [0, 3000]]) is False


def test_repeated_vertex_rejected():
    assert _is_simple_polygon([[0, 0], [4000, 0], [0, 0], [0, 3000]]) is False


# ── 门禁正例 ──


def test_suppress_degenerate_polygon():
    """bbox 大但多边形极小（坐标错乱）→ A 退化。"""
    ent = _room("ROOM_1", {"x": 0, "y": 0, "width": 10000, "height": 10000},
                [[0, 0], [600, 0], [0, 600]])
    kept, log = _suppress_implausible_rooms([ent])
    assert kept == []
    assert log[0]["reasons"] == ["degenerate_polygon"]


def test_suppress_self_intersecting_polygon():
    """自交房间多边形（面积/bbox 比正常但边界交叉）不可用 → G 自交。"""
    pts = [[0, 0], [6000, 0], [6000, 6000], [3000, -2000], [0, 6000]]
    ent = _room("ROOM_2", {"x": 0, "y": -2000, "width": 6000, "height": 8000}, pts)
    kept, log = _suppress_implausible_rooms([ent])
    assert kept == []
    assert log[0]["reasons"] == ["self_intersecting_polygon"]


def test_suppress_duplicate_keeps_authoritative_source():
    """ROOM_（显式图元分类）优先于 polyline_（派生构造），后者被降级。"""
    pts = _rect(0, 0, 5000, 4000)
    bbox = {"x": 0, "y": 0, "width": 5000, "height": 4000}
    ro = _room("ROOM_10", bbox, pts)
    pl = _room("polyline_room_1", bbox, pts)
    kept, log = _suppress_implausible_rooms([ro, pl])
    assert [e.id for e in kept] == ["ROOM_10"]
    assert log[0]["id"] == "polyline_room_1"
    assert log[0]["evidence"]["duplicate_of"] == "ROOM_10"


def test_suppress_container_room():
    """20×20m 轮廓内部含 2 个房间 → D 容器（整层轮廓）。"""
    outer = _room("polyline_room_1", {"x": 0, "y": 0, "width": 20000, "height": 20000},
                  _rect(0, 0, 20000, 20000))
    r1 = _room("ROOM_1", {"x": 1000, "y": 1000, "width": 4000, "height": 4000},
               _rect(1000, 1000, 4000, 4000))
    r2 = _room("ROOM_2", {"x": 6000, "y": 1000, "width": 4000, "height": 4000},
               _rect(6000, 1000, 4000, 4000))
    kept, log = _suppress_implausible_rooms([outer, r1, r2])
    assert "polyline_room_1" not in {e.id for e in kept}
    rec = next(r for r in log if r["id"] == "polyline_room_1")
    assert rec["reasons"] == ["room_container"]
    assert rec["evidence"]["core_entities_inside"] == 2


def test_suppress_empty_outline():
    """20×20m 大空间内部无房间、无标注、边界 5m 内无洞口 → E 空壳。"""
    outer = _room("polyline_room_1", {"x": 0, "y": 0, "width": 20000, "height": 20000},
                  _rect(0, 0, 20000, 20000))
    kept, log = _suppress_implausible_rooms([outer])
    assert kept == []
    assert log[0]["reasons"] == ["empty_outline"]
    assert log[0]["evidence"]["nearest_opening_mm"] is None


def test_suppress_titleblock_frame():
    """房间 bbox 与 titleblock 图框边框重合 → F 贴图框。"""
    frame = RawPrimitive(
        "INSERT",
        "通-图框-图签",
        "frame1",
        {"x": 0, "y": 0, "width": 60000, "height": 40000},
        {},
    )
    ent = _room("polyline_room_1", {"x": 0, "y": 0, "width": 60000, "height": 40000},
                _rect(0, 0, 60000, 40000))
    kept, log = _suppress_implausible_rooms([ent], [frame])
    assert kept == []
    assert log[0]["reasons"] == ["titleblock_frame"]


# ── 反面用例：真实房间不得被误杀 ──


def test_real_large_hall_with_label_kept():
    """20×20m 展厅：内部只有 1 个房间名标注 → 不满足 D（需 ≥2 实体或 ≥2 标注）。"""
    hall = _room("polyline_room_1", {"x": 0, "y": 0, "width": 20000, "height": 20000},
                 _rect(0, 0, 20000, 20000), subtype="exhibition")
    label = _box_entity("TEXT_1", "text", 9000, 9000, 1000, 500, text="展厅")
    kept, log = _suppress_implausible_rooms([hall, label])
    assert [e.id for e in kept] == ["polyline_room_1", "TEXT_1"]
    assert log == []


def test_real_large_room_with_opening_kept():
    """20×20m 厂房：无内部实体，但边界 5m 内有门 → 不满足 E。"""
    shop = _room("polyline_room_1", {"x": 0, "y": 0, "width": 20000, "height": 20000},
                 _rect(0, 0, 20000, 20000), subtype="factory")
    door = _box_entity("DOOR_1", "door", 9000, -100, 1200, 200)
    kept, log = _suppress_implausible_rooms([shop, door])
    assert [e.id for e in kept] == ["polyline_room_1", "DOOR_1"]
    assert log == []


def test_small_unclosed_room_kept():
    """小面积 3 点房间（<50m²）保留：B 只作用于大空间，避免误杀真实小房间。"""
    ent = _room("ROOM_3", {"x": 0, "y": 0, "width": 4000, "height": 3000},
                [[0, 0], [4000, 0], [4000, 3000]], closed=False, point_count=3)
    ent.properties["closed"] = False
    kept, log = _suppress_implausible_rooms([ent])
    assert [e.id for e in kept] == ["ROOM_3"]
    assert log == []


def test_large_room_with_door_and_single_core_kept():
    """大房间内 1 个附属空间 + 0 标注：D 需 ≥2 实体或 1 实体+1 标注，故保留。"""
    outer = _room("polyline_room_1", {"x": 0, "y": 0, "width": 20000, "height": 20000},
                  _rect(0, 0, 20000, 20000), subtype="factory")
    inner = _room("ROOM_1", {"x": 3000, "y": 3000, "width": 3000, "height": 3000},
                  _rect(3000, 3000, 3000, 3000))
    door = _box_entity("DOOR_1", "door", 9000, 19800, 1200, 200)
    kept, log = _suppress_implausible_rooms([outer, inner, door])
    assert "polyline_room_1" in {e.id for e in kept}
    assert log == []


# ── 不变量：room 必须带可用 points ──


def test_room_without_points_filled_from_bbox():
    """非构造路径产生的无 points room：按 bbox 矩形补全后保留。"""
    ent = _box_entity("ROOM_LAYER_1", "room", 0, 0, 5000, 4000)
    kept, log = _suppress_implausible_rooms([ent])
    assert [e.id for e in kept] == ["ROOM_LAYER_1"]
    props = kept[0].properties
    assert props["points_source"] == "bbox_rect"
    assert props["point_count"] == 4
    assert props["closed"] is True
    assert len(props["points"]) == 4
    assert log == []  # 补全不是抑制，记录为空


def test_room_without_points_and_invalid_bbox_downgraded():
    """bbox 也无效的无 points room：降级为 other，不以 room 名义无几何存在。"""
    ent = _box_entity("ROOM_LAYER_2", "room", 0, 0, 0, 0)
    kept, log = _suppress_implausible_rooms([ent])
    assert [e.id for e in kept] == ["ROOM_LAYER_2"]
    assert kept[0].type == "other"
    assert log[0]["id"] == "ROOM_LAYER_2"
    assert log[0]["action"] == "downgraded"
    assert log[0]["reasons"] == ["missing_polygon"]
