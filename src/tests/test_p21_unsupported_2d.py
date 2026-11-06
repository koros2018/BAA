"""P2-1: 2D 图纸不可判定规则标记（unsupported_2d）的元数据测试。

标记只用于覆盖率双口径报告，不改变 matches()/execute() 行为。
"""

from collections import Counter

from src.baa_engine.atomic import ATOMIC_FUNCTIONS, UNSUPPORTED_2D_REASONS
from src.baa_engine.atomic_functions import FuncRegistry


class TestUnsupported2dFlag:
    def test_mapping_size_and_unique(self):
        # 82 条：C 桶 67 + 语义 12 + 依赖 2 + 路径 1
        assert len(UNSUPPORTED_2D_REASONS) == 82
        assert len(set(UNSUPPORTED_2D_REASONS)) == 82

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
        assert counts["path_topology"] == 1
        assert counts["implementation_gate"] == 6
        assert counts["illuminance"] == 9
        assert counts["thermal"] == 8
        assert counts["structural"] == 6
        assert counts["product_spec"] == 11

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
