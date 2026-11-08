# -*- coding: utf-8 -*-
"""解析层单位归一化：源单位推断、几何缩放、DIMENSION/块引用/分区同步。

口径与被测实现一致：复用 drawing_classifier._area_unit_scale（LINE 长度中位数
≥50 → mm，否则 m），归一化只缩放几何字段，文本/角度/块内比例不动。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baa_engine.drawing_parser import (
    DrawingParser,
    DrawingResult,
    RawPrimitive,
    _detect_source_unit,
    _normalize_parsed_geometry,
    _scale_block_ref_to_mm,
    _scale_dimension_to_mm,
    _scale_raw_primitive_to_mm,
)


def _line(length, layer="0"):
    return RawPrimitive(
        "LINE",
        layer,
        "h",
        {"x": 0, "y": 0, "width": length, "height": 0},
        {
            "length": length,
            "angle": 0.0,
            "start_point": {"x": 0.0, "y": 0.0},
            "end_point": {"x": length, "y": 0.0},
        },
    )


class TestDetectSourceUnit:
    def test_mm_drawing(self):
        info = _detect_source_unit([_line(600), _line(800), _line(1000)])
        assert info["source_unit"] == "mm"
        assert info["coordinate_scale"] == 1.0
        assert info["line_median"] == 800

    def test_meter_drawing(self):
        info = _detect_source_unit([_line(0.6), _line(0.8), _line(1.0)])
        assert info["source_unit"] == "m"
        assert info["coordinate_scale"] == 1000.0

    def test_no_line_keeps_coordinates(self):
        info = _detect_source_unit(
            [RawPrimitive("TEXT", "0", "h", {}, {"text": "x"})]
        )
        assert info["source_unit"] == "unknown"
        assert info["coordinate_scale"] == 1.0

    def test_judgement_matches_area_unit_scale(self):
        from src.baa_engine.drawing_classifier import _area_unit_scale

        for lengths in ([10, 20, 30, 40], [60, 70], [0.5, 1.0]):
            info = _detect_source_unit([_line(v) for v in lengths])
            expected = (
                "mm" if _area_unit_scale([float(v) for v in lengths]) == 1e-6 else "m"
            )
            assert info["source_unit"] == expected


class TestScalePrimitive:
    def test_scales_geometry_keeps_text_and_angle(self):
        prim = RawPrimitive(
            "LWPOLYLINE",
            "0",
            "h",
            {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0},
            {
                "length": 1.5,
                "radius": 0.9,
                "diameter": 1.8,
                "height": 0.2,
                "measured_length": 0.7,
                "area": 1.2,
                "angle": 45.0,
                "text": "hello",
                "start_point": {"x": 1.0, "y": 2.0},
                "end_point": {"x": 3.0, "y": 4.0},
                "insert_x": 3.0,
                "insert_y": 4.0,
                "points": [(1.0, 2.0), (3.0, 4.0)],
                "closed": True,
                "point_count": 2,
            },
        )
        _scale_raw_primitive_to_mm(prim, 1000.0)
        assert prim.bbox == {
            "x": 1000.0,
            "y": 2000.0,
            "width": 3000.0,
            "height": 4000.0,
        }
        props = prim.properties
        assert props["length"] == 1500.0
        assert props["radius"] == 900.0
        assert props["diameter"] == 1800.0
        assert props["height"] == 200.0
        assert props["measured_length"] == 700.0
        assert props["area"] == 1200000.0
        assert props["start_point"] == {"x": 1000.0, "y": 2000.0}
        assert props["points"] == [(1000.0, 2000.0), (3000.0, 4000.0)]
        assert props["insert_x"] == 3000.0
        assert props["angle"] == 45.0
        assert props["text"] == "hello"
        assert props["closed"] is True
        assert props["point_count"] == 2

    def test_scale_one_is_noop(self):
        prim = _line(0.8)
        _scale_raw_primitive_to_mm(prim, 1.0)
        assert prim.properties["length"] == 0.8
        assert prim.bbox["width"] == 0.8


class TestScaleDimensionAndBlockRef:
    def test_dimension_measurement_and_points(self):
        dim = {
            "measurement": 0.85,
            "text": "850",
            "position": {"x": 1.0, "y": 2.0},
            "defpoint2": {"x": 3.0, "y": 4.0},
            "defpoint3": {"x": 5.0, "y": 6.0},
            "text_midpoint": {"x": 7.0, "y": 8.0},
        }
        _scale_dimension_to_mm(dim, 1000.0)
        assert dim["measurement"] == 850.0
        assert dim["position"] == {"x": 1000.0, "y": 2000.0}
        assert dim["defpoint2"] == {"x": 3000.0, "y": 4000.0}
        assert dim["text_midpoint"] == {"x": 7000.0, "y": 8000.0}
        assert dim["text"] == "850"

    def test_block_ref_insert_point_only(self):
        ref = {"insert_point": [1.5, 2.5], "x_scale": 2.0, "rotation": 30.0}
        _scale_block_ref_to_mm(ref, 1000.0)
        assert ref["insert_point"] == [1500.0, 2500.0]
        assert ref["x_scale"] == 2.0
        assert ref["rotation"] == 30.0

    def test_normalize_includes_sheets(self):
        prim = _line(0.8)
        dim = {"measurement": 1.2, "position": {"x": 1, "y": 2}}
        sheet_prim = _line(0.9)
        sheet_dim = {"measurement": 3.0, "position": {"x": 0, "y": 0}}
        sheets = [{"primitives": [sheet_prim], "dimensions": [sheet_dim]}]
        _normalize_parsed_geometry([prim], [dim], None, sheets, 1000.0)
        assert prim.properties["length"] == 800.0
        assert dim["measurement"] == 1200.0
        assert sheet_prim.properties["length"] == 900.0
        assert sheet_dim["measurement"] == 3000.0


def _write_rect_dxf(path, size):
    import ezdxf

    doc = ezdxf.new()
    msp = doc.modelspace()
    w, h = size
    pts = [(0, 0), (w, 0), (w, h), (0, h)]
    for i in range(4):
        msp.add_line(pts[i], pts[(i + 1) % 4])
    doc.saveas(str(path))


class TestParseIntegration:
    def test_meter_dxf_normalized_to_mm(self, tmp_path):
        path = tmp_path / "meter_plan.dxf"
        _write_rect_dxf(path, (3, 4))
        result = DrawingParser().parse(str(path), "unit-test-meter")
        assert result.success
        info = result.unit_normalization
        assert info["applied"] is True
        assert info["source_unit"] == "m"
        assert info["coordinate_scale"] == 1000.0
        lengths = [
            p.properties["length"]
            for p in result.primitives
            if p.dxf_type == "LINE"
        ]
        assert lengths and max(lengths) >= 3000.0

    def test_mm_dxf_not_scaled(self, tmp_path):
        path = tmp_path / "mm_plan.dxf"
        _write_rect_dxf(path, (3000, 4000))
        result = DrawingParser().parse(str(path), "unit-test-mm")
        assert result.success
        info = result.unit_normalization
        assert info["applied"] is False
        assert info["source_unit"] == "mm"
        lengths = [
            p.properties["length"]
            for p in result.primitives
            if p.dxf_type == "LINE"
        ]
        assert lengths and max(lengths) == 4000.0

    def test_drawing_result_defaults_to_empty_audit(self):
        assert DrawingResult("a.dxf", "x").unit_normalization == {}
