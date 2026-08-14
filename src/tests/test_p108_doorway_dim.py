"""P108: 扫线法 doorway gap_width_mm → DIM-006/DIM-009 自动触发验证。

验证点：
1. DIM-006 接受 doorway（target_entities 含 "doorway"）
2. DIM-009 接受 doorway（target_entities 含 "doorway"）
3. doorway gap_width_mm 单位转换正确（mm → m）
4. 宽度阈值判定正确（PASS/FAIL/None）
5. 过滤逻辑正确（<100mm→None, <0.8m→None, <1.3m 普通门→None for DIM-006）
"""

import pytest

from src.baa_engine.atomic_functions import FuncRegistry


@pytest.fixture
def registry():
    return FuncRegistry()


class TestDIM006Doorway:
    """DIM-006 疏散门净宽（>=1.4m）对 doorway 的判定"""

    def test_target_entities_contains_doorway(self, registry):
        f = registry.get("DIM-006")
        assert "doorway" in f.target_entities

    def test_doorway_1500mm_pass(self, registry):
        """doorway 1500mm → 1.5m >= 1.4m → PASS"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 1500}})
        assert result is not None
        assert result.result == "PASS"
        assert result.actual == pytest.approx(1.5)

    def test_doorway_1000mm_fail(self, registry):
        """doorway 1000mm → 1.0m < 1.4m → FAIL"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 1000}})
        assert result is not None
        assert result.result == "FAIL"
        assert result.actual == pytest.approx(1.0)

    def test_doorway_1200mm_fail(self, registry):
        """doorway 1200mm → 1.2m < 1.4m → FAIL（不受 1.3m 普通门过滤影响）"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 1200}})
        assert result is not None
        assert result.result == "FAIL"

    def test_doorway_narrow_too_small_skip(self, registry):
        """doorway 50mm < 100mm → 跳过（None）"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 50}})
        assert result is None

    def test_doorway_sub800mm_skip(self, registry):
        """doorway 700mm → 0.7m < 0.8m → 跳过（None，小门不适用疏散判定）"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 700}})
        assert result is None

    def test_doorway_entity_type_in_result(self, registry):
        """结果 entity_type 正确标注为 doorway"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 1500}})
        assert result is not None
        assert result.entity_type == "doorway"


class TestDIM009Doorway:
    """DIM-009 疏散出口宽度（>=0.9m）对 doorway 的判定"""

    def test_target_entities_contains_doorway(self, registry):
        f = registry.get("DIM-009")
        assert "doorway" in f.target_entities

    def test_doorway_1000mm_pass(self, registry):
        """doorway 1000mm → 1.0m >= 0.9m → PASS"""
        f = registry.get("DIM-009")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 1000}})
        assert result is not None
        assert result.result == "PASS"
        assert result.actual == pytest.approx(1.0)

    def test_doorway_800mm_fail(self, registry):
        """doorway 800mm → 0.8m < 0.9m → FAIL"""
        f = registry.get("DIM-009")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 800}})
        assert result is not None
        assert result.result == "FAIL"

    def test_doorway_narrow_too_small_skip(self, registry):
        """doorway 50mm < 100mm → 跳过（None）"""
        f = registry.get("DIM-009")
        result = f.execute({"type": "doorway", "properties": {"gap_width_mm": 50}})
        assert result is None

    def test_doorway_entity_type_in_result(self, registry):
        result = registry.get("DIM-009").execute(
            {"type": "doorway", "properties": {"gap_width_mm": 1000}}
        )
        assert result is not None
        assert result.entity_type == "doorway"


class TestBackwardCompatibility:
    """确保原有 door/exit_door 判定不受影响"""

    def test_door_1000mm_dim006_skip(self, registry):
        """普通 door 1.0m < 1.3m → 不适用 DIM-006（None）"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "door", "properties": {"width": 1.0}})
        assert result is None

    def test_exit_door_1000mm_dim006_fail(self, registry):
        """exit_door 1.0m < 1.4m → FAIL"""
        f = registry.get("DIM-006")
        result = f.execute({"type": "exit_door", "properties": {"width": 1.0}})
        assert result is not None
        assert result.result == "FAIL"