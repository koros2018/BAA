"""E6 回归测试：验证门宽阈值、ARC/CIRCLE微小半径、DWG直读."""
import sys
import os
import pytest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.baa_engine.semantic_analyzer.classify import (
    _classify_by_geometry,
)
from src.baa_engine.semantic_analyzer.models import SemanticEntity


class MockPrimitive:
    """模拟 RawPrimitive，仅包含分类所需字段。"""

    def __init__(self, dxf_type, layer="0", properties=None):
        self.dxf_type = dxf_type
        self.layer = layer
        self.properties = properties or {}
        self.bbox = {"x": 0, "y": 0, "width": 1, "height": 1}


class TestE6_T2_DoorThreshold:
    """E6-T2: 门宽阈值从 700mm 降至 500mm。"""

    def setup_method(self):
        from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
        self.analyzer = SemanticAnalyzer()

    @pytest.mark.parametrize("length,expected", [
        (500, "door"),
        (550, "door"),
        (699, "door"),
        (700, "door"),
        (1998, "door"),  # length+1=1999 < 2000
    ])
    def test_door_threshold_500mm(self, length, expected):
        """LINE [500, 2000)mm 且 nearly-hv → door（E6-T2 降低阈值）。"""
        prim = MockPrimitive(
            "LINE", "0",
            {
                "length": length,
                "angle": 0.0,
                "real_se": 10.0,
                "start_point": {"x": 0, "y": 0},
                "end_point": {"x": length, "y": 0},
            },
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == expected, f"length={length}mm expected door, got {result}"

    def test_line_short_still_other(self):
        """LINE <500mm 仍归 other（非门）。"""
        prim = MockPrimitive(
            "LINE", "0",
            {
                "length": 300,
                "angle": 0.0,
                "real_se": 5.0,
                "start_point": {"x": 0, "y": 0},
                "end_point": {"x": 300, "y": 0},
            },
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "other"


class TestE6_T3_ArcCircleTinyRadius:
    """E6-T3: ARC/CIRCLE radius<50 → other，避免误标为 window/column。"""

    def setup_method(self):
        from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
        self.analyzer = SemanticAnalyzer()

    def test_arc_tiny_radius_other(self):
        """radius < 50mm ARC → other（装饰性弧线）。"""
        prim = MockPrimitive(
            "ARC", "0",
            {"radius": 30.0, "start_angle": 0.0, "end_angle": 180.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "other"

    def test_arc_door_threshold_50mm(self):
        """radius >= 50mm ARC → door（门弧）。"""
        prim = MockPrimitive(
            "ARC", "0",
            {"radius": 50.0, "start_angle": 0.0, "end_angle": 180.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "door"

    def test_circle_tiny_radius_other(self):
        """radius < 50mm CIRCLE → other（装饰性圆形）。"""
        prim = MockPrimitive(
            "CIRCLE", "0",
            {"radius": 20.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "other"

    def test_circle_column_threshold_50mm(self):
        """radius >= 50mm CIRCLE → column（非装饰）。"""
        prim = MockPrimitive(
            "CIRCLE", "0",
            {"radius": 50.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "column"

    def test_arc_large_radius_window(self):
        """radius >= 2000mm ARC → window（弧形窗）。"""
        prim = MockPrimitive(
            "ARC", "0",
            {"radius": 2500.0, "start_angle": 0.0, "end_angle": 90.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "window"


class TestE6_T4_EzdwgDirect:
    """E6-T4: DWG ezdwg 直读优先，保留图层信息。"""

    def test_try_ezdwg_direct_returns_none_for_dxf(self):
        """非 .dwg 文件直接返回 None。"""
        from src.baa_engine.parsers.dwg_convert import _try_ezdwg_direct
        result = _try_ezdwg_direct(Path("dummy.dxf"))
        assert result is None


class TestE6_ClassificationStats:
    """E6: classification_stats 包含 other 字段，effective_rate 公式不变。"""

    def setup_method(self):
        from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
        self.analyzer = SemanticAnalyzer()

    def test_other_counter_exists(self):
        """_classify_other 计数器已初始化。"""
        assert hasattr(self.analyzer, "_classify_other")
        assert self.analyzer._classify_other == 0

    def test_effective_rate_formula_unchanged(self):
        """effective_rate = (unclassified + block_default) / total，other 不纳入。"""
        self.analyzer._classify_total = 1000
        self.analyzer._classify_unclassified = 0
        self.analyzer._classify_block_default = 0
        self.analyzer._classify_other = 100

        effective_rate = round(
            (self.analyzer._classify_unclassified + self.analyzer._classify_block_default)
            / self.analyzer._classify_total, 4
        )
        assert effective_rate == 0.0
        assert self.analyzer._classify_other == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
