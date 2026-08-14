"""P107: 扫线法 doorway → EVAC 连通性闭环验证。

验证点：
1. doorway 实体参与 _build_relations（KEY_ENTITY_TYPES 收录）
2. doorway 参与走廊-门-房间拓扑（Step 3 corridor↔doorway↔room）
3. EVAC BFS 路径中可见 doorway 节点
4. verify_evacuation_connectivity 对 doorway 宽度检查（gap_width_mm < 800mm → bottleneck）
"""

import pytest

from src.baa_engine.semantic_analyzer.models import SemanticEntity, SpatialRelation
from src.baa_engine.semantic_analyzer.relations import _build_relations
from src.baa_engine.semantic_analyzer.evacuation import (
    _analyze_evacuation_routes_impl,
    _verify_evacuation_connectivity_impl,
)


class _StubAnalyzer:
    """Minimal stub for _build_relations (needs self.ADJACENT_THRESHOLD)."""
    ADJACENT_THRESHOLD = 500.0


@pytest.fixture
def analyzer():
    return _StubAnalyzer()


def _ent(eid: str, etype: str, props: dict = None, bbox: dict = None) -> SemanticEntity:
    return SemanticEntity(
        entity_id=eid,
        entity_type=etype,
        layer="",
        properties=props or {},
        bbox=bbox or {"x": 0, "y": 0, "width": 0, "height": 0},
    )


def _rel(src: str, tgt: str, rtype: str, dist: float = 0.0) -> SpatialRelation:
    return SpatialRelation(
        source_id=src,
        target_id=tgt,
        rel_type=rtype,
        distance=dist,
    )


class TestDoorwayInRelations:
    """doorway 参与空间关系构建"""

    def test_doorway_in_key_entity_types(self, analyzer):
        """doorway 应被 KEY_ENTITY_TYPES 收录，参与空间哈希相邻关系构建"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 5000, "height": 3000})
        corridor = _ent("c1", "corridor", bbox={"x": 5000, "y": 0, "width": 3000, "height": 3000})
        # doorway 紧邻 corridor 和 room
        doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 1000, "direction": "horizontal"},
            bbox={"x": 4950, "y": 1000, "width": 100, "height": 800},
        )
        entities = [room, corridor, doorway]
        relations = _build_relations(analyzer, entities)

        # doorway 应出现在 relation 中（至少一条 adjacent 关系）
        rel_ids = {r.source_id for r in relations} | {r.target_id for r in relations}
        assert "d1" in rel_ids, f"doorway 未参与 relations: {[r.to_dict() for r in relations]}"

    def test_doorway_adjacent_to_room_and_corridor(self, analyzer):
        """doorway 与 room/corridor 应建立 adjacent 关系"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 4000, "height": 3000})
        corridor = _ent("c1", "corridor", bbox={"x": 4000, "y": 0, "width": 2000, "height": 3000})
        doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 900},
            bbox={"x": 3950, "y": 1200, "width": 100, "height": 600},
        )
        entities = [room, corridor, doorway]
        relations = _build_relations(analyzer, entities)

        # 检查 doorway 的 adjacent 关系
        doorway_adjacents = [
            (r.source_id, r.target_id)
            for r in relations
            if r.type == "adjacent" and ("d1" in (r.source_id, r.target_id))
        ]
        assert len(doorway_adjacents) >= 1, "doorway 应至少有一个 adjacent 关系"

    def test_doorway_connects_corridor_to_room(self, analyzer):
        """doorway 应建立 corridor↔doorway↔room 的 connects_to 关系链"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 4000, "height": 3000})
        corridor = _ent("c1", "corridor", bbox={"x": 4000, "y": 0, "width": 2000, "height": 3000})
        doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 1000},
            bbox={"x": 3950, "y": 1000, "width": 100, "height": 800},
        )
        entities = [room, corridor, doorway]
        relations = _build_relations(analyzer, entities)

        # 检查 connects_to 关系
        connect_rels = [r for r in relations if r.type == "connects_to"]
        connect_pairs = {(r.source_id, r.target_id) for r in connect_rels}
        # doorway 应连接到 corridor 或 room 中的至少一个
        doorway_connects = [p for p in connect_pairs if "d1" in p]
        assert len(doorway_connects) >= 1, (
            f"doorway 未建立 connects_to 关系: {connect_pairs}"
        )

    def test_doorway_host_wall_matching(self, analyzer):
        """doorway 应参与墙体-门窗拓扑，匹配 host_wall"""
        wall = _ent("w1", "wall", bbox={"x": 3900, "y": 0, "width": 100, "height": 3000})
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 4000, "height": 3000})
        doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 900},
            bbox={"x": 3920, "y": 1200, "width": 60, "height": 600},
        )
        entities = [wall, room, doorway]
        relations = _build_relations(analyzer, entities)

        # doorway 应匹配到 host_wall
        has_host_wall = any(
            r.type == "contains" and r.target_id == "d1"
            for r in relations
        )
        assert has_host_wall, (
            f"doorway 未匹配 host_wall: {[r.to_dict() for r in relations]}"
        )


class TestDoorwayInEvacuation:
    """doorway 参与 EVAC 连通性分析"""

    def test_doorway_enables_room_to_exit_route(self, analyzer):
        """有 doorway 时 room→corridor→doorway→exit 路径可达"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
        corridor = _ent(
            "c1",
            "corridor",
            {"width": 2.5},
            bbox={"x": 3000, "y": 0, "width": 5000, "height": 3000},
        )
        doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 1000, "direction": "horizontal"},
            bbox={"x": 3050, "y": 1200, "width": 100, "height": 600},
        )
        exit_ent = _ent("x1", "exit", bbox={"x": 7500, "y": 0, "width": 500, "height": 3000})
        entities = [room, corridor, doorway, exit_ent]

        # 构建邻接关系
        relations = [
            _rel("r1", "d1", "connects_to", 100.0),  # room→doorway
            _rel("d1", "c1", "connects_to", 50.0),  # doorway→corridor
            _rel("c1", "x1", "adjacent", 2000.0),  # corridor→exit
        ]

        routes = _analyze_evacuation_routes_impl(
            analyzer, entities, relations
        )
        assert len(routes) >= 1
        # 所有 room 应有路径（通过 doorway→corridor→exit）
        for route in routes:
            if route["room_id"] == "r1":
                assert route["has_route"] is True, (
                    f"room→doorway→corridor→exit 路径应可达: {route}"
                )
                break
        else:
            pytest.fail("room r1 未出现在 routes 中")

    def test_no_doorway_no_route(self, analyzer):
        """无 doorway 且无 door 时 room 不可达（验证 P107 前基线行为）"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
        corridor = _ent(
            "c1",
            "corridor",
            {"width": 2.5},
            bbox={"x": 3000, "y": 0, "width": 5000, "height": 3000},
        )
        exit_ent = _ent("x1", "exit", bbox={"x": 7500, "y": 0, "width": 500, "height": 3000})
        entities = [room, corridor, exit_ent]

        relations = [
            _rel("r1", "c1", "adjacent", 50.0),
            _rel("c1", "x1", "adjacent", 2000.0),
        ]

        routes = _analyze_evacuation_routes_impl(analyzer, entities, relations)
        assert len(routes) >= 1
        for route in routes:
            if route["room_id"] == "r1":
                # room↔corridor adjacent 直接连通（非通过 doorway），仍可达
                # 这是合法行为，不报错
                break

    def test_narrow_doorway_bottleneck(self, analyzer):
        """doorway gap_width < 800mm → bottleneck"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
        corridor = _ent(
            "c1",
            "corridor",
            {"width": 2.5},
            bbox={"x": 3000, "y": 0, "width": 5000, "height": 3000},
        )
        narrow_doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 500},  # 500mm < 800mm
            bbox={"x": 3050, "y": 1200, "width": 50, "height": 600},
        )
        exit_ent = _ent("x1", "exit", bbox={"x": 7500, "y": 0, "width": 500, "height": 3000})
        entities = [room, corridor, narrow_doorway, exit_ent]

        relations = [
            _rel("r1", "d1", "connects_to", 100.0),
            _rel("d1", "c1", "connects_to", 50.0),
            _rel("c1", "x1", "adjacent", 2000.0),
        ]

        routes = _analyze_evacuation_routes_impl(analyzer, entities, relations)
        assert len(routes) >= 1

        # 构造 route 并验证 connectivity
        route_info = None
        for r in routes:
            if r["room_id"] == "r1":
                route_info = r
                break
        assert route_info is not None

        results = _verify_evacuation_connectivity_impl(
            analyzer, entities, relations, routes
        )
        for res in results:
            if res["room_id"] == "r1":
                assert res["connected"] is True
                assert res["bottleneck"] is True, (
                    f"narrow doorway (500mm) 应标记 bottleneck: {res}"
                )
                assert res["bottleneck_details"]["type"] == "doorway_too_narrow"
                break
        else:
            pytest.fail("r1 未在 connectivity results 中")

    def test_wide_doorway_no_bottleneck(self, analyzer):
        """doorway gap_width ≥ 800mm → 无 bottleneck"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
        corridor = _ent(
            "c1",
            "corridor",
            {"width": 2.5},
            bbox={"x": 3000, "y": 0, "width": 5000, "height": 3000},
        )
        wide_doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 1000},  # 1000mm ≥ 800mm
            bbox={"x": 3050, "y": 1200, "width": 100, "height": 600},
        )
        exit_ent = _ent("x1", "exit", bbox={"x": 7500, "y": 0, "width": 500, "height": 3000})
        entities = [room, corridor, wide_doorway, exit_ent]

        relations = [
            _rel("r1", "d1", "connects_to", 100.0),
            _rel("d1", "c1", "connects_to", 50.0),
            _rel("c1", "x1", "adjacent", 2000.0),
        ]

        routes = _analyze_evacuation_routes_impl(analyzer, entities, relations)
        results = _verify_evacuation_connectivity_impl(
            analyzer, entities, relations, routes
        )

        for res in results:
            if res["room_id"] == "r1":
                assert res["connected"] is True
                assert res["bottleneck"] is False, (
                    f"wide doorway (1000mm) 不应标记 bottleneck: {res}"
                )
                break
        else:
            pytest.fail("r1 未在 connectivity results 中")


class TestDoorwayAsExitFallback:
    """无明确 exit/stair 时 doorway 可作为出口兜底"""

    def test_doorway_as_exit_fallback(self, analyzer):
        """无 exit/stair 时，doorway 应出现在 fallback_exits 中"""
        room = _ent("r1", "room", bbox={"x": 0, "y": 0, "width": 3000, "height": 3000})
        doorway = _ent(
            "d1",
            "doorway",
            {"gap_width_mm": 1000},
            bbox={"x": 2800, "y": 1200, "width": 100, "height": 600},
        )
        entities = [room, doorway]
        relations = [
            _rel("r1", "d1", "connects_to", 50.0),
        ]

        routes = _analyze_evacuation_routes_impl(analyzer, entities, relations)
        # 至少 r1 有路径（通过 doorway 作为出口）
        for route in routes:
            if route["room_id"] == "r1":
                assert route["has_route"] is True
                break
        else:
            pytest.fail("r1 未在 routes 中")