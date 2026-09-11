"""
P127 天正 T3 降级管线 — 单元测试

测试覆盖：
- classify_layer: 图层名精确/模糊/未命中
- infer_by_geometry: 几何推断（墙体/门/窗/柱/文字）
- classify_entity: 三层降级顺序
- build_summary: 汇总统计
- TianzhengT3: scan 单文件 + scan_batch + 缓存
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.baa_engine.tianzheng_t3 import (
    C_AXIS,
    C_COLUMN,
    C_DIMENSION,
    C_DOOR,
    C_TEXT,
    C_UNSPECIFIED,
    C_WALL,
    C_WINDOW,
    Component,
    TianzhengT3,
    build_summary,
    classify_layer,
    infer_by_geometry,
)

# ── classify_layer 测试 ───────────────────────────────────────────────


class TestClassifyLayer:
    def test_exact_wall(self):
        ctype, conf = classify_layer("WALL")
        assert ctype == C_WALL
        assert conf >= 0.90

    def test_exact_a_wall(self):
        ctype, conf = classify_layer("A-WALL")
        assert ctype == C_WALL
        assert conf >= 0.90

    def test_exact_door(self):
        ctype, conf = classify_layer("DOOR")
        assert ctype == C_DOOR

    def test_exact_column(self):
        ctype, conf = classify_layer("COLUMN")
        assert ctype == C_COLUMN

    def test_exact_axis(self):
        ctype, conf = classify_layer("AXIS")
        assert ctype == C_AXIS

    def test_exact_dim(self):
        ctype, conf = classify_layer("DIM")
        assert ctype == C_DIMENSION

    def test_exact_text(self):
        ctype, conf = classify_layer("TEXT")
        assert ctype == C_TEXT

    def test_exact_a_dim(self):
        ctype, conf = classify_layer("A-DIM")
        assert ctype == C_DIMENSION

    def test_keyword_wall_case_insensitive(self):
        ctype, conf = classify_layer("my-wall-layer")
        assert ctype == C_WALL
        assert conf < 0.90  # 模糊匹配置信度较低

    def test_keyword_door_chinese(self):
        ctype, conf = classify_layer("门")
        assert ctype == C_DOOR

    def test_keyword_window_chinese(self):
        ctype, conf = classify_layer("窗")
        assert ctype == C_WINDOW

    def test_keyword_axis_chinese(self):
        ctype, conf = classify_layer("轴")
        assert ctype == C_AXIS

    def test_unmatched(self):
        ctype, conf = classify_layer("random-layer")
        assert ctype is None
        assert conf == 0.0

    def test_empty(self):
        ctype, conf = classify_layer("")
        assert ctype is None
        assert conf == 0.0


# ── infer_by_geometry 测试 ────────────────────────────────────────────


class TestInferByGeometry:
    def test_dimension_type(self):
        ctype, conf = infer_by_geometry("DIMENSION", {"width": 100, "height": 10})
        assert ctype == C_DIMENSION

    def test_wall_long_aspect(self):
        # 长宽比大，宽度合理 → 墙体
        ctype, conf = infer_by_geometry("LWPOLYLINE", {"width": 5000, "height": 240})
        assert ctype == C_WALL

    def test_wall_line(self):
        ctype, conf = infer_by_geometry("LINE", {"width": 3000, "height": 120})
        assert ctype == C_WALL

    def test_wall_too_thin(self):
        # 宽度太小，不像墙体
        ctype, conf = infer_by_geometry("LINE", {"width": 3000, "height": 10})
        # 短轴=10 < 60，不满足墙体条件
        assert ctype is None or ctype == C_UNSPECIFIED

    def test_door_size(self):
        ctype, conf = infer_by_geometry("LWPOLYLINE", {"width": 900, "height": 600})
        assert ctype == C_DOOR

    def test_window_size(self):
        ctype, conf = infer_by_geometry("LWPOLYLINE", {"width": 1500, "height": 1800})
        assert ctype == C_WINDOW

    def test_column_circle(self):
        ctype, conf = infer_by_geometry("CIRCLE", {"width": 400, "height": 400})
        assert ctype == C_COLUMN

    def test_text(self):
        ctype, conf = infer_by_geometry("TEXT", {"width": 50, "height": 10})
        assert ctype == C_TEXT

    def test_mtext(self):
        ctype, conf = infer_by_geometry("MTEXT", {"width": 50, "height": 10})
        assert ctype == C_TEXT

    def test_unknown_empty_bbox(self):
        ctype, conf = infer_by_geometry("ARC", {})
        assert ctype is None


# ── classify_entity 测试 ──────────────────────────────────────────────


class TestClassifyEntity:
    def _tz(self):
        return TianzhengT3(verbose=False)

    def test_layer_exact_wins_over_geometry(self):
        # 图层 WALL 精确匹配，即使几何也像门
        ctype, conf, evidence = self._tz().classify_entity("LWPOLYLINE", "WALL", {"width": 900, "height": 600})
        assert ctype == C_WALL
        assert evidence == "layer_exact"

    def test_layer_keyword(self):
        ctype, conf, evidence = self._tz().classify_entity("LWPOLYLINE", "my-door-layer", {"width": 900, "height": 600})
        assert ctype == C_DOOR
        assert evidence == "layer_keyword"

    def test_geometry_fallback(self):
        ctype, conf, evidence = self._tz().classify_entity("LWPOLYLINE", "unrelated", {"width": 900, "height": 600})
        assert ctype == C_DOOR
        assert evidence == "geometry"

    def test_unspecified_fallback(self):
        ctype, conf, evidence = self._tz().classify_entity("ARC", "unrelated", {"width": 100, "height": 100})
        assert ctype == C_UNSPECIFIED
        assert evidence == "unspecified"

    def test_dimension_by_geometry(self):
        ctype, conf, evidence = self._tz().classify_entity("DIMENSION", "unrelated", {"width": 100, "height": 10})
        assert ctype == C_DIMENSION
        assert evidence == "geometry"


# ── build_summary 测试 ────────────────────────────────────────────────


class TestBuildSummary:
    def _make(self, ctype, conf=0.8, evidence="layer_exact"):
        return Component(
            dxf_type="LWPOLYLINE",
            layer="test",
            handle="h1",
            bbox={"width": 100, "height": 10},
            properties={},
            component_type=ctype,
            confidence=conf,
            evidence=evidence,
        )

    def test_empty(self):
        s = build_summary([])
        assert s["total"] == 0
        assert s["avg_confidence"] == 0.0

    def test_single(self):
        s = build_summary([self._make(C_WALL, 0.9)])
        assert s["total"] == 1
        assert s["by_type"][C_WALL] == 1
        assert s["avg_confidence"] == pytest.approx(0.9)

    def test_mixed(self):
        comps = [
            self._make(C_WALL, 0.95),
            self._make(C_DOOR, 0.85),
            self._make(C_WINDOW, 0.80),
        ]
        s = build_summary(comps)
        assert s["total"] == 3
        assert s["by_type"][C_WALL] == 1
        assert s["by_type"][C_DOOR] == 1
        assert s["by_type"][C_WINDOW] == 1
        # build_summary 已将置信度 round 到 4 位
        assert s["avg_confidence"] == pytest.approx((0.95 + 0.85 + 0.80) / 3, abs=1e-4)

    def test_all_types_present_in_output(self):
        s = build_summary([self._make(C_WALL)])
        # 即使为 0，主要类型也应在输出中
        assert C_DOOR in s["by_type"]
        assert C_AXIS in s["by_type"]
        assert C_DIMENSION in s["by_type"]


# ── TianzhengT3 主类测试 ──────────────────────────────────────────────


class TestTianzhengT3:
    def test_classify_entity_method(self):
        tz = TianzhengT3(verbose=False)
        ctype, conf, evidence = tz.classify_entity("WALL", "WALL", {"width": 100, "height": 10})
        assert ctype == C_WALL
        assert evidence == "layer_exact"

    def test_scan_with_mock_parser(self):
        tz = TianzhengT3(verbose=False)

        # mock DrawingResult
        mock_prim = MagicMock()
        mock_prim.dxf_type = "LWPOLYLINE"
        mock_prim.layer = "WALL"
        mock_prim.handle = "h1"
        mock_prim.bbox = {"width": 5000, "height": 240}
        mock_prim.properties = {}

        mock_result = MagicMock()
        mock_result.error = None
        mock_result.primitives = [mock_prim]
        mock_result.dimensions = []

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        components = tz.scan("dummy.dxf")
        assert len(components) == 1
        assert components[0].component_type == C_WALL
        assert components[0].to_dict()["component_type"] == C_WALL

    def test_scan_with_dimension(self):
        tz = TianzhengT3(verbose=False)

        mock_result = MagicMock()
        mock_result.error = None
        mock_result.primitives = []
        mock_result.dimensions = [
            {"handle": "d1", "layer": "DIM", "bbox": {"width": 100, "height": 10}}
        ]

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        components = tz.scan("dummy.dxf")
        assert len(components) == 1
        assert components[0].component_type == C_DIMENSION

    def test_scan_cache(self):
        tz = TianzhengT3(verbose=False)

        mock_result = MagicMock()
        mock_result.error = None
        mock_result.primitives = []
        mock_result.dimensions = []

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        tz.scan("dummy.dxf")
        first_call_count = tz._parser.parse.call_count
        tz.scan("dummy.dxf")
        # 第二次命中缓存，不再调用 parser
        assert tz._parser.parse.call_count == first_call_count

    def test_scan_no_cache(self):
        tz = TianzhengT3(verbose=False)

        mock_result = MagicMock()
        mock_result.error = None
        mock_result.primitives = []
        mock_result.dimensions = []

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        tz.scan("dummy.dxf", use_cache=False)
        tz.scan("dummy.dxf", use_cache=False)
        assert tz._parser.parse.call_count == 2

    def test_clear_cache(self):
        tz = TianzhengT3(verbose=False)

        mock_result = MagicMock()
        mock_result.error = None
        mock_result.primitives = []
        mock_result.dimensions = []

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        tz.scan("dummy.dxf")
        assert "dummy.dxf" in tz._cache
        tz.clear_cache()
        assert "dummy.dxf" not in tz._cache

    def test_scan_error_result(self):
        tz = TianzhengT3(verbose=False)

        mock_result = MagicMock()
        mock_result.error = "解析失败"
        mock_result.primitives = []
        mock_result.dimensions = []

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        components = tz.scan("bad.dxf")
        assert components == []

    def test_scan_batch(self, tmp_path):
        tz = TianzhengT3(verbose=False)

        # 创建两个 dummy 文件
        f1 = tmp_path / "a_t3.dxf"
        f2 = tmp_path / "b_t3.dxf"
        f1.write_text("dummy")
        f2.write_text("dummy")

        mock_result = MagicMock()
        mock_result.error = None
        mock_result.primitives = []
        mock_result.dimensions = []

        tz._parser = MagicMock()
        tz._parser.parse.return_value = mock_result

        results = tz.scan_batch(str(tmp_path))
        assert len(results) == 2
        assert all("total" in r for r in results)

    def test_scan_batch_no_match(self, tmp_path):
        tz = TianzhengT3(verbose=False)
        results = tz.scan_batch(str(tmp_path), pattern="*_t3.dxf")
        assert results == []
