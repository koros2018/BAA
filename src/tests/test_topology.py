# -*- coding: utf-8 -*-
"""拓扑显式化测试（Roadmap v4 T-B1 / B1a）。"""

import json

from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.baa_engine.semantic_analyzer.topology import (
    build_topology_graph,
    topology_summary,
)


def _room(eid, x, y, w, h, etype="room"):
    return SemanticEntity(
        entity_id=eid, entity_type=etype,
        bbox={"x": x, "y": y, "width": w, "height": h},
        properties={},
    )


class TestBuildTopologyGraph:
    def test_adjacent_rooms_connected(self):
        # 两房间 bbox 间隙 200mm（隔一堵墙）→ adjacent 边
        g = build_topology_graph([_room("r1", 0, 0, 5000, 4000), _room("r2", 5200, 0, 5000, 4000)])
        assert g.has_edge("r1", "r2")
        assert g.edges["r1", "r2"]["relation"] == "adjacent"

    def test_distant_rooms_not_connected(self):
        # 间隙 2000mm > 600mm 缓冲 → 无边
        g = build_topology_graph([_room("r1", 0, 0, 5000, 4000), _room("r2", 7000, 0, 5000, 4000)])
        assert not g.has_edge("r1", "r2")

    def test_door_inside_room_connected(self):
        # 门质心落入房间 bbox → contains 边
        door = _room("d1", 4800, 1500, 900, 200, etype="door")
        g = build_topology_graph([_room("r1", 0, 0, 5000, 4000), door])
        assert g.has_edge("d1", "r1")
        assert g.edges["d1", "r1"]["relation"] == "contains"

    def test_node_kinds_and_attrs(self):
        g = build_topology_graph([_room("r1", 0, 0, 5000, 4000), _room("d1", 1000, 1000, 900, 200, etype="door")])
        assert g.nodes["r1"]["kind"] == "room"
        assert g.nodes["d1"]["kind"] == "opening"
        assert g.nodes["r1"]["entity_type"] == "room"
        assert g.nodes["r1"]["center"] == (2500.0, 2000.0)

    def test_non_space_entities_ignored(self):
        g = build_topology_graph([_room("w1", 0, 0, 300, 300, etype="wall"), _room("o1", 0, 0, 100, 100, etype="other")])
        assert g.number_of_nodes() == 0

    def test_empty_entities(self):
        g = build_topology_graph([])
        assert g.number_of_nodes() == 0
        assert g.number_of_edges() == 0


class TestTopologySummary:
    def test_summary_json_serializable_and_complete(self):
        ents = [
            _room("r1", 0, 0, 5000, 4000),
            _room("r2", 5200, 0, 5000, 4000),
            _room("r3", -2200, 4200, 5000, 4000),  # 仅与 r1 垂直间隙 200mm 相邻（与 r2 对角距 >600）
            _room("d1", 4000, 1500, 900, 200, etype="door"),  # 质心 4450，仅落 r1 外扩缓冲
        ]
        s = topology_summary(build_topology_graph(ents))
        # 可 JSON 化（判定层消费前提）
        json.dumps(s, ensure_ascii=False)
        assert s["node_count"] == 4
        assert s["room_count"] == 3
        assert s["edge_count"] == 3  # r1-r2 adjacent + r1-r3 adjacent + d1-r1 contains
        assert sorted(s["adjacency"]["r1"]) == ["d1", "r2", "r3"]
        assert len(s["connected_components"]) == 1
        assert s["is_connected"] is True

    def test_disconnected_components(self):
        s = topology_summary(build_topology_graph([
            _room("r1", 0, 0, 5000, 4000),
            _room("r2", 50000, 0, 5000, 4000),
        ]))
        assert len(s["connected_components"]) == 2
        assert s["is_connected"] is False

    def test_empty_summary(self):
        s = topology_summary(build_topology_graph([]))
        assert s["node_count"] == 0
        assert s["room_count"] == 0
        assert s["is_connected"] is True
