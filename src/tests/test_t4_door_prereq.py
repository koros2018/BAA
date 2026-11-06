"""
T4: DIM-021/022 前置条件（首层楼层证据 / 人员密集场所证据）。

验证点：
1. 无 floor=F1 证据 → DIM-021 不判定（返回 None，静默，不产出 finding）。
2. 无 occupancy=人员密集场所证据 → DIM-022 不判定。
3. 两条条款按建筑业态互斥：人员密集 → 只判 DIM-022；否则只判 DIM-021。
4. 首层外门合成样本（1.0m）仍报 1 条（DIM-021 FAIL）。
5. 非疏散门（无 is_evacuation_door）仍被既有门类防误报守卫拦截。
"""

import pytest

from src.baa_engine.atomic_functions import FuncRegistry, _is_ground_floor, _is_assembly_occupancy


@pytest.fixture
def registry():
    return FuncRegistry()


def _door(**props):
    base = {"is_evacuation_door": True, "clear_width": 0.516}
    base.update(props)
    return {"type": "door", "properties": base}


class TestGroundFloorLabel:
    def test_accepts_ground_floor_labels(self):
        for value in ("F1", "1F", "一层", "首层", "地上一层", 1, 1.0, "F1-消防"):
            assert _is_ground_floor(value) is True, value

    def test_rejects_other_floors_and_missing(self):
        for value in (None, "", "F2", "F11", "11F", "2", 2, "二层", "B1"):
            assert _is_ground_floor(value) is False, value

    def test_assembly_occupancy_evidence(self):
        assert _is_assembly_occupancy({"occupancy": "人员密集场所"}) is True
        assert _is_assembly_occupancy({"occupancy_type": "assembly"}) is True
        assert _is_assembly_occupancy({"is_assembly_occupancy": True}) is True
        assert _is_assembly_occupancy({"occupancy": "office"}) is False
        assert _is_assembly_occupancy({}) is False


class TestDIM021GroundFloorPrereq:
    def test_no_floor_evidence_is_silent(self, registry):
        """villa 13 扇门（floor=None）→ 25 条无证据误报归零。"""
        ent = _door()
        assert registry.get("DIM-021").execute(ent) is None
        assert registry.get("DIM-022").execute(ent) is None

    def test_synthetic_ground_floor_door_1000mm_fails(self, registry):
        """首层外门合成样本 1.0m → DIM-021 仍报 1 条。"""
        ent = {
            "type": "exit_door",
            "properties": {
                "is_evacuation_door": True,
                "floor": "F1",
                "clear_width": 1.0,
            },
        }
        r = registry.get("DIM-021").execute(ent)
        assert r is not None and r.result == "FAIL"
        assert r.actual == pytest.approx(1000.0)
        assert r.delta == pytest.approx(-100.0)
        # 互斥：人员密集场所条款不得同时报出
        assert registry.get("DIM-022").execute(ent) is None

    def test_ground_floor_door_1200mm_passes(self, registry):
        ent = {"type": "door", "properties": {"is_evacuation_door": True, "floor": "F1", "clear_width": 1.2}}
        r = registry.get("DIM-021").execute(ent)
        assert r is not None and r.result == "PASS"

    def test_non_evac_door_still_skipped(self, registry):
        ent = {"type": "door", "properties": {"floor": "F1", "clear_width": 1.0}}
        assert registry.get("DIM-021").execute(ent) is None


class TestDIM022AssemblyPrereq:
    def test_no_occupancy_evidence_is_silent(self, registry):
        ent = _door(floor="F1")
        assert registry.get("DIM-022").execute(ent) is None

    def test_assembly_door_1000mm_fails_only_dim022(self, registry):
        ent = {
            "type": "exit_door",
            "properties": {
                "is_evacuation_door": True,
                "floor": "F1",
                "occupancy": "人员密集场所",
                "clear_width": 1.0,
            },
        }
        r = registry.get("DIM-022").execute(ent)
        assert r is not None and r.result == "FAIL"
        assert r.actual == pytest.approx(1000.0)
        # 互斥：首层外门条款（1.1m）不再对同一实体报出
        assert registry.get("DIM-021").execute(ent) is None

    def test_assembly_door_1500mm_passes(self, registry):
        ent = {
            "type": "door",
            "properties": {
                "is_evacuation_door": True,
                "floor": "F1",
                "occupancy_type": "assembly",
                "clear_width": 1.5,
            },
        }
        r = registry.get("DIM-022").execute(ent)
        assert r is not None and r.result == "PASS"

    def test_assembly_door_without_floor_still_judged(self, registry):
        """人员密集场所条款只依赖 occupancy，不要求楼层证据。"""
        ent = {
            "type": "door",
            "properties": {
                "is_evacuation_door": True,
                "occupancy": "人员密集场所",
                "clear_width": 1.0,
            },
        }
        r = registry.get("DIM-022").execute(ent)
        assert r is not None and r.result == "FAIL"
        assert registry.get("DIM-021").execute(ent) is None
