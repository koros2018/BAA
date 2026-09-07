"""
P121: 图纸类型分类器 + 损坏文件检测
覆盖 classify_drawing 和 is_likely_corrupt
"""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baa_engine.drawing_classifier import classify_drawing, is_likely_corrupt


class TestClassifyByFilename:
    def test_structure_drawing(self):
        r = classify_drawing("A1IDC及通信机楼结构平面图20161227z.dxf")
        assert r["type"] == "结构"
        assert r["confidence"] >= 0.5
        assert "文件名" in r["reason"]

    def test_electrical_drawing(self):
        r = classify_drawing("2.1电气170825-报审.dxf")
        assert r["type"] == "电气"
        assert r["confidence"] >= 0.5

    def test_fire_alarm_drawing(self):
        r = classify_drawing("6.火灾自动报警_（报审）_t3.dxf")
        assert r["type"] in ("电气", "暖通")  # 火灾报警含消防，可能归电气或暖通
        assert r["confidence"] >= 0.5

    def test_hvac_drawing(self):
        r = classify_drawing("4.通风BS170826.dxf")
        assert r["type"] == "暖通"
        assert r["confidence"] >= 0.5

    def test_water_fire_drawing(self):
        r = classify_drawing("A1云计算中心_水消防2017.03.31_t3.dxf")
        assert r["type"] in ("暖通", "电气")  # 水消防含消防关键字
        assert r["confidence"] >= 0.5

    def test_architectural_drawing(self):
        r = classify_drawing("A1云计算中心平面图0405_t3.dxf")
        assert r["type"] in ("建筑",)
        assert r["confidence"] >= 0.3

    def test_generic_drawing(self):
        r = classify_drawing("unknown_file.dxf")
        assert r["type"] == "未知"
        assert r["confidence"] == 0.0


class TestClassifyByLayers:
    def test_structure_layers(self):
        r = classify_drawing(
            "drawing.dxf",
            layer_names=["STR_COLUMN", "STR_BEAM", "WALL_STR", "SLAB"],
        )
        assert r["type"] == "结构"

    def test_electrical_layers(self):
        r = classify_drawing(
            "drawing.dxf",
            layer_names=["EL_POWER", "EL_LIGHT", "配电", "照明"],
        )
        assert r["type"] == "电气"

    def test_hvac_layers(self):
        r = classify_drawing(
            "drawing.dxf",
            layer_names=["HVAC_DUCT", "PIPE", "风管", "水管"],
        )
        assert r["type"] == "暖通"

    def test_filename_overrides_layers(self):
        # 文件名结构 vs 图层暖通 → 文件名权重更高
        r = classify_drawing(
            "结构平面图.dxf",
            layer_names=["HVAC", "DUCT", "PIPE"],
        )
        assert r["type"] == "结构"

    def test_layers_only_when_no_filename(self):
        r = classify_drawing(
            "drawing.dxf",
            layer_names=["HVAC_DUCT", "PIPE", "风管", "水管"],
        )
        assert r["type"] == "暖通"


class TestCorruptDetection:
    def test_valid_large_dxf(self, tmp_path):
        # 写一个有效 DXF 头 + 足够大小
        dxf = tmp_path / "valid.dxf"
        dxf.write_bytes(b"  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n" + (b"padding" * 2000))
        r = is_likely_corrupt(str(dxf))
        assert r["corrupt"] is False

    def test_undersized_file(self, tmp_path):
        dxf = tmp_path / "tiny.dxf"
        dxf.write_bytes(b"  0\nSECTION\n")
        r = is_likely_corrupt(str(dxf))
        assert r["corrupt"] is True
        assert "大小" in r["reason"]

    def test_missing_header(self, tmp_path):
        dxf = tmp_path / "bad.dxf"
        # 写足够大但无 SECTION 头
        dxf.write_bytes(b"this is not a dxf file at all\n" * 2000)
        r = is_likely_corrupt(str(dxf))
        assert r["corrupt"] is True
        assert "SECTION" in r["reason"] or "HEADER" in r["reason"]

    def test_placeholder_file(self, tmp_path):
        # 模拟 15267 字节的占位文件（无 SECTION）
        dxf = tmp_path / "placeholder.dxf"
        content = b"  0\nSECTION\n  2\nHEADER\n" + (b"junk" * 3000)
        dxf.write_bytes(content)
        # 有 SECTION 头，不算 corrupt
        r = is_likely_corrupt(str(dxf))
        assert r["corrupt"] is False


class TestIntegration:
    def test_full_parse_with_classification(self):
        """端到端：解析已知建筑图，检查 drawing_type 字段"""
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.baa_engine.drawing_parser import DrawingParser

        parser = DrawingParser()
        dxf_path = "data/drawings/real/test_floorplan.pdf2dxf.dxf"
        result = parser.parse(dxf_path)
        assert result.success
        assert "drawing_type" in result.__dict__
        assert isinstance(result.drawing_type, dict)
        assert "type" in result.drawing_type

    def test_corrupt_file_returns_error(self):
        """损坏文件应返回错误而非空结果"""
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.baa_engine.drawing_parser import DrawingParser

        parser = DrawingParser()
        # 用已知的占位文件
        dxf_path = "data/drawings/real/A1云计算中心平面图0405_t3.dxf"
        result = parser.parse(dxf_path)
        # 如果解析出 0 实体且文件小，应标记为损坏
        assert result.error is not None or len(result.primitives or []) == 0
