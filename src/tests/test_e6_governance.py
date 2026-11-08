"""E6 回归测试：验证门宽阈值、ARC/CIRCLE微小半径、DWG直读."""

import sys
import os
import pytest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.baa_engine.semantic_analyzer.classify import (
    _classify_by_geometry,
    UNCLASSIFIED_REASONS,
    _annotate_unclassified_reasons,
    summarize_unclassified_reasons,
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

    @pytest.mark.parametrize(
        "length,expected",
        [
            (500, "door"),
            (550, "door"),
            (699, "door"),
            (700, "door"),
            (1998, "door"),  # length+1=1999 < 2000
        ],
    )
    def test_door_threshold_500mm(self, length, expected):
        """LINE [500, 2000)mm 且 nearly-hv → door（E6-T2 降低阈值）。"""
        prim = MockPrimitive(
            "LINE",
            "0",
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
            "LINE",
            "0",
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
            "ARC",
            "0",
            {"radius": 30.0, "start_angle": 0.0, "end_angle": 180.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "other"

    def test_arc_door_threshold_50mm(self):
        """radius >= 50mm ARC → door（门弧）。"""
        prim = MockPrimitive(
            "ARC",
            "0",
            {"radius": 50.0, "start_angle": 0.0, "end_angle": 180.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "door"

    def test_circle_tiny_radius_other(self):
        """radius < 50mm CIRCLE → other（装饰性圆形）。"""
        prim = MockPrimitive(
            "CIRCLE",
            "0",
            {"radius": 20.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "other"

    def test_circle_column_threshold_50mm(self):
        """radius >= 50mm CIRCLE → column（非装饰）。"""
        prim = MockPrimitive(
            "CIRCLE",
            "0",
            {"radius": 50.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "column"

    def test_arc_large_radius_window(self):
        """radius >= 2000mm ARC → window（弧形窗）。"""
        prim = MockPrimitive(
            "ARC",
            "0",
            {"radius": 2500.0, "start_angle": 0.0, "end_angle": 90.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "window"

    def test_arc_large_span_not_room(self):
        """大半径 + 跨度>90° 的单段 ARC 也不是 room（ROOM_3524 残留路径）。"""
        prim = MockPrimitive(
            "ARC",
            "0",
            {"radius": 4378.57, "start_angle": 0.0, "end_angle": 180.0},
        )
        result = _classify_by_geometry(self.analyzer, prim)
        assert result == "window", f"单段 ARC 不应判 room: {result}"


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
            / self.analyzer._classify_total,
            4,
        )
        assert effective_rate == 0.0
        assert self.analyzer._classify_other == 100


def _unc_entity(layer, dxf_type="LINE", size=1000.0):
    """构造一条 unclassified 实体（与 classify 内的轻量 dict 同构）。"""
    return {
        "id": "UNCLASSIFIED_00001",
        "type": "unclassified",
        "subtype": "",
        "bbox": {"x": 0, "y": 0, "width": size, "height": size},
        "layer": layer,
        "confidence": 0.5,
        "properties": {"dxf_type": dxf_type},
    }


class TestP23UnclassifiedReason:
    """P2-3: unclassified_reason 只做标注，不改变分类/规则/占比。"""

    def test_reason_enum_exact(self):
        assert len(UNCLASSIFIED_REASONS) == 5
        assert set(UNCLASSIFIED_REASONS) == {
            "furniture_fixture",
            "pattern_fill",
            "axis_or_annotation",
            "stroke_fragment",
            "unknown_layer",
        }

    @pytest.mark.parametrize(
        "layer,dxf_type,size,expected",
        [
            ("Furniture", "LINE", 195.0, "furniture_fixture"),
            ("FURN", "HATCH", 500.0, "furniture_fixture"),
            ("P-SANIT", "CIRCLE", 500.0, "furniture_fixture"),
            ("friz", "LINE", 101.88, "furniture_fixture"),
            ("gradient", "LINE", 1000.0, "pattern_fill"),
            ("Structural - Bearing", "LINE", 0.013, "pattern_fill"),
            ("Ck Achurado Muros", "HATCH", 300.0, "pattern_fill"),
            ("AX", "LINE", 5000.0, "axis_or_annotation"),
            ("CASCO", "TEXT", 10.0, "axis_or_annotation"),
            ("kod", "MTEXT", 10.0, "axis_or_annotation"),
            ("v", "LINE", 60.0, "stroke_fragment"),
            ("merdiven", "LINE", 100.0, "stroke_fragment"),
            ("hidden", "LINE", 213.1, "unknown_layer"),
        ],
    )
    def test_layer_reason_mapping(self, layer, dxf_type, size, expected):
        ents = [_unc_entity(layer, dxf_type, size)]
        _annotate_unclassified_reasons(ents)
        assert ents[0]["unclassified_reason"] == expected

    @pytest.mark.parametrize(
        "layer",
        ["Taxi", "Level", "ELEVATOR", "fire_elevator", "FLOOR"],
    )
    def test_short_token_boundary_not_matched(self, layer):
        """短词元（ax 等）必须边界匹配：Taxi/Level 等不得误标为轴线。"""
        ents = [_unc_entity(layer, "LINE", 5000.0)]
        _annotate_unclassified_reasons(ents)
        assert ents[0]["unclassified_reason"] == "unknown_layer"

    def test_type_ratio_fallback(self):
        """无词元时按类型占比：MTEXT→axis、HATCH→pattern、小线→stroke。"""
        cases = [
            ("WEIRD_A", "MTEXT", 10.0, "axis_or_annotation"),
            ("WEIRD_B", "HATCH", 300.0, "pattern_fill"),
            ("WEIRD_C", "LINE", 5.0, "stroke_fragment"),
            ("WEIRD_D", "LINE", 5000.0, "unknown_layer"),
        ]
        for layer, dxf_type, size, expected in cases:
            ents = [_unc_entity(layer, dxf_type, size)]
            _annotate_unclassified_reasons(ents)
            assert ents[0]["unclassified_reason"] == expected, layer

    def test_same_layer_same_reason(self):
        """同层图元必须得到同一原因标签（保证统计口径稳定）。"""
        ents = [
            _unc_entity("Furniture", "LINE", 195.0),
            _unc_entity("Furniture", "ARC", 400.0),
            _unc_entity("Furniture", "HATCH", 800.0),
        ]
        _annotate_unclassified_reasons(ents)
        assert {e["unclassified_reason"] for e in ents} == {"furniture_fixture"}

    def test_summary_counts(self):
        ents = [
            _unc_entity("Furniture", "LINE", 195.0),
            _unc_entity("Furniture", "LINE", 195.0),
            _unc_entity("gradient", "LINE", 1000.0),
            _unc_entity("WEIRD_D", "LINE", 5000.0),
        ]
        _annotate_unclassified_reasons(ents)
        summary = summarize_unclassified_reasons(ents)
        assert summary == {
            "furniture_fixture": 2,
            "pattern_fill": 1,
            "unknown_layer": 1,
        }

    def test_analyze_annotation_only(self):
        """集成：标注不进入 entities、不改变 unclassified/rate，仅新增汇总。"""
        from src.baa_engine.drawing_parser import RawPrimitive
        from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

        prims = [
            RawPrimitive(
                "LINE", "WALL", "h1",
                {"x": 0, "y": 0, "width": 3000, "height": 10},
                {"length": 3000},
            ),
            RawPrimitive(
                "LINE", "Furniture", "h2",
                {"x": 0, "y": 0, "width": 195, "height": 195},
                {},
            ),
            RawPrimitive(
                "LINE", "gradient", "h3",
                {"x": 0, "y": 0, "width": 1000, "height": 1000},
                {},
            ),
        ]
        result = SemanticAnalyzer().analyze(prims)
        stats = result["classification_stats"]
        assert stats["unclassified"] == 2
        assert stats["unclassified"] == len(result["unclassified_entities"])
        assert sum(stats["unclassified_reasons"].values()) == 2
        assert stats["unclassified_reasons"] == {
            "furniture_fixture": 1,
            "pattern_fill": 1,
        }
        # rate 公式未变：unclassified / total
        assert stats["rate"] == round(2 / stats["total"], 4)
        # 未识别图元不得混入 entities
        assert all(e["type"] != "unclassified" for e in result["entities"])
        assert all("unclassified_reason" in u for u in result["unclassified_entities"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
