"""P132-B5：空 id 的 doorway 不得成为疏散出口节点。"""

from src.baa_engine.semantic_analyzer.evacuation import (
    _analyze_evacuation_routes_impl,
    _verify_evacuation_connectivity_impl,
)
from src.baa_engine.semantic_analyzer.models import SemanticEntity, SpatialRelation


class _StubAnalyzer:
    ADJACENT_THRESHOLD = 500.0


def _ent(eid, etype, props=None, bbox=None):
    return SemanticEntity(
        entity_id=eid,
        entity_type=etype,
        layer="",
        properties=props or {},
        bbox=bbox or {"x": 0, "y": 0, "width": 0, "height": 0},
    )


def _rel(src, tgt, rtype, dist):
    return SpatialRelation(source_id=src, target_id=tgt, rel_type=rtype, distance=dist)


def test_empty_id_doorway_is_not_an_exit():
    """只有空 id doorway 时，不存在任何可追溯出口 → 不产生路由。"""
    room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
    empty_doorway = _ent(
        "", "doorway", {"gap_width_mm": 1000}, {"x": 2800, "y": 0, "width": 100, "height": 800}
    )
    relations = [_rel("r1", "", "connects_to", 50.0)]

    routes = _analyze_evacuation_routes_impl(_StubAnalyzer(), [room, empty_doorway], relations)
    assert routes == [], "空 id doorway 不应成为出口，路由列表应为空"

    conn = _verify_evacuation_connectivity_impl(
        _StubAnalyzer(), [room, empty_doorway], relations, routes
    )
    # 连通性校验的兜底逻辑仍会为每个 room 产出一条 connected=False 的覆盖记录，
    # 这是"无出口"的正确表达；关键是不能把空 id 当成出口（connected 不得为 True），
    # 且不得出现以空 id 为终点的路由。
    assert conn, "每个 room 仍应被连通性结果覆盖"
    assert all(not r.get("connected") for r in conn), conn
    assert all(r.get("room_id") == "r1" for r in conn), conn


def test_real_door_still_serves_as_exit():
    """空 id doorway 存在时，路由应落到有 id 的真实门，而不是空节点。"""
    room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
    empty_doorway = _ent(
        "", "doorway", {"gap_width_mm": 1000}, {"x": 2800, "y": 0, "width": 100, "height": 800}
    )
    door = _ent(
        "DOOR_1",
        "door",
        {"width": 0.9, "clear_width": 0.9},
        {"x": 3000, "y": 0, "width": 100, "height": 900},
    )
    relations = [
        _rel("r1", "", "connects_to", 50.0),
        _rel("r1", "DOOR_1", "connects_to", 800.0),
    ]

    routes = _analyze_evacuation_routes_impl(
        _StubAnalyzer(), [room, empty_doorway, door], relations
    )
    assert len(routes) == 1
    route = routes[0]
    assert route["has_route"] is True
    assert route["exit_id"] == "DOOR_1"
    assert not route["route_key"].startswith(":")


def test_route_key_never_starts_with_colon():
    """回归证据：route_key=":50.0" 由空 id 出口造成，修复后不再出现。"""
    room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
    empty_doorway = _ent(
        "", "doorway", {"gap_width_mm": 1000}, {"x": 2800, "y": 0, "width": 100, "height": 800}
    )
    routes = _analyze_evacuation_routes_impl(
        _StubAnalyzer(), [room, empty_doorway], [_rel("r1", "", "connects_to", 50.0)]
    )
    for route in routes:
        if route.get("has_route"):
            assert not str(route.get("route_key", "")).startswith(":"), route
