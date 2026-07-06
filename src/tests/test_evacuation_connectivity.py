"""
疏散路径连通性验证测试 - P33
"""

import pytest
from src.baa_engine.semantic_analyzer import SemanticAnalyzer, SemanticEntity, SpatialRelation


class TestEvacuationConnectivity:
    """疏散路径连通性验证测试"""

    def setup_method(self):
        self.analyzer = SemanticAnalyzer()

    def _make_entity(self, eid, etype, bbox=None, props=None):
        """辅助方法：创建SemanticEntity"""
        return SemanticEntity(
            entity_id=eid,
            entity_type=etype,
            bbox=bbox or {"x1": 0, "y1": 0, "x2": 10, "y2": 10},
            layer="general",
            confidence=1.0,
            properties=props or {},
        )

    def _make_relation(self, source_id, target_id, rel_type="adjacent", distance=0.0):
        """辅助方法：创建SpatialRelation"""
        return SpatialRelation(
            source_id=source_id, target_id=target_id, rel_type=rel_type, distance=distance
        )

    def test_single_room_connected_to_exit(self):
        """测试单个房间通过走廊连接到出口"""
        room = self._make_entity("room1", "room", {"x1": 0, "y1": 0, "x2": 10, "y2": 10})
        exit_ent = self._make_entity("exit1", "exit", {"x1": 10, "y1": 0, "x2": 20, "y2": 10})
        corridor = self._make_entity(
            "corr1", "corridor", {"x1": 5, "y1": 5, "x2": 15, "y2": 10}, {"width": 1.5}
        )

        # 构建空间关系
        relations = [
            self._make_relation("room1", "corr1"),
            self._make_relation("corr1", "exit1"),
        ]

        # 模拟evacuation_routes
        evacuation_routes = [
            {"room_id": "room1", "path": ["room1", "corr1", "exit1"], "has_route": True}
        ]

        results = self.analyzer.verify_evacuation_connectivity(
            entities=[room, exit_ent, corridor],
            relations=relations,
            evacuation_routes=evacuation_routes,
        )

        assert len(results) >= 1
        room_result = next((r for r in results if r.get("room_id") == "room1"), None)
        assert room_result is not None
        assert room_result["connected"] is True

    def test_room_not_connected_to_exit(self):
        """测试房间无路径到出口"""
        room = self._make_entity("room1", "room", {"x1": 0, "y1": 0, "x2": 10, "y2": 10})
        exit_ent = self._make_entity("exit1", "exit", {"x1": 100, "y1": 100, "x2": 110, "y2": 110})

        relations = []
        evacuation_routes = [{"room_id": "room1", "path": [], "has_route": False}]

        results = self.analyzer.verify_evacuation_connectivity(
            entities=[room, exit_ent], relations=relations, evacuation_routes=evacuation_routes
        )

        room_result = next((r for r in results if r.get("room_id") == "room1"), None)
        assert room_result is not None
        assert room_result["connected"] is False

    def test_corridor_bottleneck_detected(self):
        """测试走廊瓶颈检测（宽度<1.2m）"""
        room = self._make_entity("room1", "room", {"x1": 0, "y1": 0, "x2": 10, "y2": 10})
        exit_ent = self._make_entity("exit1", "exit", {"x1": 10, "y1": 0, "x2": 20, "y2": 10})
        narrow_corridor = self._make_entity(
            "corr1", "corridor", {"x1": 5, "y1": 5, "x2": 15, "y2": 10}, {"width": 0.8}
        )

        relations = [
            self._make_relation("room1", "corr1"),
            self._make_relation("corr1", "exit1"),
        ]

        evacuation_routes = [
            {"room_id": "room1", "path": ["room1", "corr1", "exit1"], "has_route": True}
        ]

        results = self.analyzer.verify_evacuation_connectivity(
            entities=[room, exit_ent, narrow_corridor],
            relations=relations,
            evacuation_routes=evacuation_routes,
        )

        room_result = next((r for r in results if r.get("room_id") == "room1"), None)
        assert room_result is not None
        assert room_result["connected"] is True
        assert room_result["bottleneck"] is True

    def test_multiple_exits_improves_connectivity(self):
        """测试多个出口时路径选择"""
        room = self._make_entity("room1", "room", {"x1": 5, "y1": 5, "x2": 15, "y2": 15})
        exit1 = self._make_entity("exit1", "exit", {"x1": 0, "y1": 0, "x2": 5, "y2": 10})
        exit2 = self._make_entity("exit2", "exit", {"x1": 15, "y1": 0, "x2": 20, "y2": 10})

        relations = [
            self._make_relation("room1", "exit1"),
            self._make_relation("room1", "exit2"),
        ]

        evacuation_routes = [{"room_id": "room1", "path": ["room1", "exit1"], "has_route": True}]

        results = self.analyzer.verify_evacuation_connectivity(
            entities=[room, exit1, exit2], relations=relations, evacuation_routes=evacuation_routes
        )

        room_result = next((r for r in results if r.get("room_id") == "room1"), None)
        assert room_result is not None
        assert room_result["connected"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
