"""P2-1: 2D 图纸不可判定规则标记（unsupported_2d）的元数据测试。

标记只用于覆盖率双口径报告，不改变 matches()/execute() 行为。
"""

from collections import Counter

from src.baa_engine.atomic import (
    ATOMIC_FUNCTIONS,
    IMPLEMENTATION_GATE_DEFECTS,
    IMPLEMENTATION_GATES,
    UNSUPPORTED_2D_REASONS,
)
from src.baa_engine.atomic_functions import FuncRegistry


class TestUnsupported2dFlag:
    def test_mapping_size_and_unique(self):
        # 99 条：C 桶 61 + 语义 12 + 依赖 2 + 路径 4（DIST-001/DIM-056/DIM-094/DIM-015）
        # + 净高 4（DIM-013/016/087/099）+ 产品选型 5（ATTR-001/003/008/009/012）
        # + 结构 5（STR-010/011/012/013/015）+ 设备流体 6（DIM-038/041/042/043/044/045，2026-11-16）
        # （原 82 剔除 6 条 implementation_gate_defect）
        assert len(UNSUPPORTED_2D_REASONS) == 99
        assert len(set(UNSUPPORTED_2D_REASONS)) == 99

    def test_every_id_exists_in_registry(self):
        known = {f.func_id for f in ATOMIC_FUNCTIONS}
        missing = sorted(set(UNSUPPORTED_2D_REASONS) - known)
        assert missing == []

    def test_flag_applied_to_module_functions(self):
        flagged = {f.func_id for f in ATOMIC_FUNCTIONS if f.unsupported_2d}
        assert flagged == set(UNSUPPORTED_2D_REASONS)
        for func in ATOMIC_FUNCTIONS:
            if func.unsupported_2d:
                assert func.unsupported_reason == UNSUPPORTED_2D_REASONS[func.func_id]

    def test_registry_clone_keeps_flag(self):
        registry = FuncRegistry()
        for fid, reason in UNSUPPORTED_2D_REASONS.items():
            func = registry.get(fid)
            assert func is not None
            assert func.unsupported_2d is True
            assert func.unsupported_reason == reason

    def test_unflagged_rules_default_false(self):
        registry = FuncRegistry()
        unflagged = [
            f for f in registry.list_all() if f.func_id not in UNSUPPORTED_2D_REASONS
        ]
        assert unflagged
        assert all(f.unsupported_2d is False for f in unflagged)
        assert all(f.unsupported_reason == "" for f in unflagged)

    def test_reason_bucket_totals(self):
        counts = Counter(UNSUPPORTED_2D_REASONS.values())
        assert counts["semantic_gap"] == 12
        assert counts["prereq_unsupported"] == 2
        assert counts["path_topology"] == 4  # DIST-001/DIM-056/DIM-094/DIM-015（2026-11-16）
        assert "implementation_gate" not in counts
        assert counts["illuminance"] == 9
        assert counts["thermal"] == 8
        assert counts["structural"] == 11
        assert counts["product_spec"] == 22

    def test_flag_does_not_change_matching(self):
        """标记前后 matches() 结果一致：标记不是判据门禁。"""
        registry = FuncRegistry()
        entity = {"id": "E-1", "type": "wall", "properties": {}}
        for fid in ("ATTR-004", "THERM-001", "LIGHT-002"):
            func = registry.get(fid)
            before = func.matches(entity)
            func.unsupported_2d = False
            after = func.matches(entity)
            func.unsupported_2d = True
            assert before == after


class TestImplementationGateDefect:
    def test_defect_list(self):
        assert len(IMPLEMENTATION_GATE_DEFECTS) == 6
        assert set(IMPLEMENTATION_GATE_DEFECTS) == {
            "EXIST-033",
            "EXIST-034",
            "EXIST-035",
            "EXIST-054",
            "EXIST-062",
            "EXIST-095",
        }

    def test_defect_not_marked_unsupported(self):
        """门禁缺陷留在可判定分母：不能用 unsupported_2d 排除。"""
        registry = FuncRegistry()
        for fid, note in IMPLEMENTATION_GATE_DEFECTS.items():
            func = registry.get(fid)
            assert func.implementation_gate_defect is True
            assert func.defect_note == note
            assert func.unsupported_2d is False
            assert func.unsupported_reason == ""
            assert fid not in UNSUPPORTED_2D_REASONS

    def test_defect_flag_does_not_change_matching(self):
        registry = FuncRegistry()
        entity = {"id": "E-1", "type": "room", "subtype": "pump_room",
                  "properties": {"subtype": "pump_room"}}
        func = registry.get("EXIST-033")
        before = func.matches(entity)
        func.implementation_gate_defect = False
        after = func.matches(entity)
        func.implementation_gate_defect = True
        assert before == after


class TestImplementationGate:
    """P133: 能力缺失门禁——剔除可判定分母、执行链不产出 PASS/FAIL。"""

    def test_gate_list(self):
        assert set(IMPLEMENTATION_GATES) == {"EVAC-002", "EVAC-003"}

    def test_gate_flags_applied(self):
        registry = FuncRegistry()
        for fid, reason in IMPLEMENTATION_GATES.items():
            func = registry.get(fid)
            assert func.implementation_gate is True
            assert func.implementation_gate_reason == reason
            # 与 unsupported_2d / 执行缺陷是三种独立标记
            assert func.unsupported_2d is False
            assert func.implementation_gate_defect is False
            assert fid not in UNSUPPORTED_2D_REASONS
            assert fid not in IMPLEMENTATION_GATE_DEFECTS

    def test_gate_not_executed_in_chain(self):
        registry = FuncRegistry()
        entity = {
            "id": "R1",
            "type": "room",
            "properties": {
                "has_evacuation_route": True,
                "evacuation_path_length": 40.0,
                "evacuation_too_far": True,
                "area_m2": 4.0,
            },
        }
        results = registry.execute_chained(["EVAC-001", "EVAC-002", "EVAC-003"], entity)
        assert results.get("EVAC-001") is not None
        assert "EVAC-002" not in results
        assert "EVAC-003" not in results

    def test_direct_execute_keeps_math(self):
        """门禁只作用于执行链；直接 execute 保留数值计算，供单测与诊断使用。"""
        result = FuncRegistry().get("EVAC-002").execute(
            {
                "id": "R2",
                "type": "room",
                "properties": {"evacuation_path_length": 40.0, "area_m2": 4.0},
            }
        )
        assert result is not None and result.actual == 40.0
