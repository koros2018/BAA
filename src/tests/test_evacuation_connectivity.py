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


class TestEvacuationDoorMarking:
    """Step 5.7 疏散门适用性标注（E5 误报治理后续）"""

    def setup_method(self):
        self.analyzer = SemanticAnalyzer()

    def _make_entity(self, eid, etype, props=None, subtype=""):
        return SemanticEntity(
            entity_id=eid,
            entity_type=etype,
            bbox={"x": 0, "y": 0, "width": 10, "height": 10},
            layer="general",
            subtype=subtype,
            properties=props or {},
        )

    def _make_relation(self, source_id, target_id, rel_type="adjacent"):
        return SpatialRelation(source_id=source_id, target_id=target_id, rel_type=rel_type)

    def test_door_adjacent_to_exit_is_marked(self):
        """与严格出口直接相连的普通门 → 标注为疏散门"""
        door = self._make_entity("door1", "door", {"width": 0.8})
        stair = self._make_entity("stair1", "stair")
        count = self.analyzer.mark_evacuation_doors(
            [door, stair], [self._make_relation("door1", "stair1")], []
        )
        assert count == 1
        assert door.properties["is_evacuation_door"] is True
        assert door.properties["_evacuation_evidence"] == "exit_adjacent"

    def test_door_on_room_route_is_marked(self):
        """非辅助房间疏散路径上的门 → 标注为疏散门"""
        door = self._make_entity("door1", "door", {"width": 0.8})
        room = self._make_entity("room1", "room", subtype="")
        room.properties["has_evacuation_route"] = True
        routes = [{"room_id": "room1", "path": ["room1", "door1"], "has_route": True}]
        count = self.analyzer.mark_evacuation_doors([door, room], [], routes)
        assert count == 1
        assert door.properties["is_evacuation_door"] is True
        assert door.properties["_evacuation_evidence"] == "on_evacuation_route"

    def test_door_on_toilet_route_is_not_marked(self):
        """卫生间等辅助房间的门不承担房间疏散功能 → 不标注"""
        door = self._make_entity("door1", "door", {"width": 0.7})
        toilet = self._make_entity("room1", "room", subtype="toilet")
        toilet.properties["has_evacuation_route"] = True
        routes = [{"room_id": "room1", "path": ["room1", "door1"], "has_route": True}]
        count = self.analyzer.mark_evacuation_doors([door, toilet], [], routes)
        assert count == 0
        assert "is_evacuation_door" not in door.properties

    def test_unevidenced_door_stays_unmarked(self):
        """无证据的普通门保持未标注（DIM-113 继续跳过，避免误报）"""
        door = self._make_entity("door1", "door", {"width": 0.8})
        room = self._make_entity("room1", "room", subtype="")
        # 房间无疏散路径 → 不构成证据
        routes = [{"room_id": "room1", "path": [], "has_route": False}]
        count = self.analyzer.mark_evacuation_doors([door, room], [], routes)
        assert count == 0
        assert "is_evacuation_door" not in door.properties

    def test_dim113_judges_marked_door(self):
        """端到端：标注后的普通门进入 DIM-113 判定（不漏报）"""
        from src.baa_engine.atomic_functions import FuncRegistry

        door = self._make_entity("door1", "door", {"width": 0.8})
        stair = self._make_entity("stair1", "stair")
        self.analyzer.mark_evacuation_doors(
            [door, stair], [self._make_relation("door1", "stair1")], []
        )
        func = FuncRegistry()._funcs["DIM-113"]
        # 生产链路中原子函数消费的是 to_dict() 后的实体字典
        result = func.execute(door.to_dict())
        assert result is not None and result.result == "FAIL"


class TestEvacuationRouteDedup:
    """EVAC 房间级去重：同一疏散路径只由代表房间判定一次"""

    def _entity(self, eid, etype, width=1000, area=None):
        props = {} if area is None else {"area": area}
        return SemanticEntity(
            entity_id=eid,
            entity_type=etype,
            bbox={"x": 0, "y": 0, "width": width, "height": width},
            layer="general",
            properties=props,
        )

    def test_rooms_sharing_route_get_single_representative(self):
        analyzer = SemanticAnalyzer()
        room1 = self._entity("room1", "room", area=4500000)
        room2 = self._entity("room2", "room", area=0)
        exit1 = self._entity("exit1", "exit")
        relations = [
            SpatialRelation(source_id="room1", target_id="exit1", rel_type="adjacent", distance=40.0),
            SpatialRelation(source_id="room2", target_id="exit1", rel_type="adjacent", distance=40.0),
        ]
        routes = analyzer.analyze_evacuation_routes([room1, room2, exit1], relations)
        assert len(routes) == 2
        assert routes[0]["route_key"] == routes[1]["route_key"] == "exit1:40.0"
        reps = [r for r in routes if r["is_route_representative"]]
        assert len(reps) == 1
        # 代表房间取面积最小者（大面积房间路径分析不可靠）
        assert reps[0]["room_id"] == "room2"
        assert all(r["route_shared_room_count"] == 2 for r in routes)

    def test_secondary_route_room_skips_evac_rules(self):
        from src.baa_engine.atomic_functions import FuncRegistry

        registry = FuncRegistry()
        secondary = {
            "id": "room9",
            "type": "room",
            "properties": {
                "has_evacuation_route": True,
                "evacuation_path_length": 48.28,
                "evacuation_too_far": True,
                "evacuation_route_secondary": True,
            },
        }
        primary = dict(secondary, id="room8", properties={**secondary["properties"]})
        primary["properties"].pop("evacuation_route_secondary")
        assert registry.get("EVAC-002").execute(secondary) is None
        assert registry.get("EVAC-003").execute(secondary) is None
        assert registry.get("EVAC-002").execute(primary) is not None


class TestAreaUnitNormalization:
    """EVAC 面积口径：area 双来源（mm²/m²）归一为 area_m2"""

    def _room(self, area, width=4600, height=3000):
        return SemanticEntity(
            entity_id="room1",
            entity_type="room",
            bbox={"x": 0, "y": 0, "width": width, "height": height},
            layer="general",
            properties={"area": area},
        )

    def test_mm2_area_converted_and_original_kept(self):
        ent = self._room(4355882.54)
        SemanticAnalyzer()._normalize_area_units([ent])
        assert ent.properties["area_m2"] == 4.36
        # 原 area 保持不变，不影响 AREA 类规则既有口径
        assert ent.properties["area"] == 4355882.54

    def test_m2_area_kept_as_is(self):
        ent = self._room(20.5)
        SemanticAnalyzer()._normalize_area_units([ent])
        assert ent.properties["area_m2"] == 20.5

    def test_evac_002_compares_in_m2(self):
        """mm² 大数不再被“面积>5000 跳过”误吞，EVAC-002 正常判定"""
        from src.baa_engine.atomic_functions import FuncRegistry

        registry = FuncRegistry()
        entity = {
            "id": "room1",
            "type": "room",
            "bbox": {"x": 0, "y": 0, "width": 4600, "height": 3000},
            "properties": {
                "area": 4355882.54,
                "area_m2": 4.36,
                "has_evacuation_route": True,
                "evacuation_path_length": 40.0,
            },
        }
        result = registry.get("EVAC-002").execute(entity)
        assert result is not None and result.result == "FAIL"

    def test_evac_002_still_skips_really_large_room(self):
        from src.baa_engine.atomic_functions import FuncRegistry

        entity = {
            "id": "room2",
            "type": "room",
            "properties": {
                "area_m2": 6000.0,
                "has_evacuation_route": True,
                "evacuation_path_length": 40.0,
            },
        }
        assert FuncRegistry().get("EVAC-002").execute(entity) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
