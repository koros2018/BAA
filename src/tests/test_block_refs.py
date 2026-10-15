"""P127-S1 块引用提取器 — 单元测试

测试覆盖：
- read_block_ref: 块名/插入点/旋转/缩放/图层/handle/ATTRIB
- extract_attribs: ATTRIB 读取与缺失兜底
- extract_block_refs: 批量收集、max_refs 上限、非 INSERT 过滤
- summarize_block_refs: 汇总统计
- DrawingParser 集成: parse() 输出 block_refs 字段（常规 + 分页分支）
- 非回归: INSERT 仍作为 primitive 输出，block_name 保留在 properties
"""

import sys
from pathlib import Path

import ezdxf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.baa_engine.parsers.block_refs import (
    TZ_BLOCK_PREFIXES,
    extract_attribs,
    extract_block_refs,
    read_block_ref,
    summarize_block_refs,
)
from src.baa_engine.drawing_parser import DrawingParser

# ── 辅助：构造含块定义的 doc ──────────────────────────────────────────


def _make_doc() -> "ezdxf.document.Drawing":
    doc = ezdxf.new("R2010")
    blk = doc.blocks.new(name="DOOR_900")
    blk.add_line((0, 0), (900, 0))
    blk.add_attdef("TAG", (100, 100), dxfattribs={"height": 50})
    blk.add_attdef("SPEC", (100, 200), dxfattribs={"height": 50})
    return doc


# ── read_block_ref 测试 ──────────────────────────────────────────────


class TestReadBlockRef:
    def test_basic_fields(self):
        doc = _make_doc()
        msp = doc.modelspace()
        ins = msp.add_blockref(
            "DOOR_900",
            (1000, 2000),
            dxfattribs={"rotation": 90, "xscale": 1.2, "yscale": 0.8, "layer": "DOOR"},
        )
        ref = read_block_ref(ins)
        assert ref is not None
        assert ref.block_name == "DOOR_900"
        assert ref.insert_point == (1000.0, 2000.0)
        assert ref.rotation == pytest.approx(90.0)
        assert ref.x_scale == pytest.approx(1.2)
        assert ref.y_scale == pytest.approx(0.8)
        assert ref.layer == "DOOR"
        assert ref.handle  # handle 非空

    def test_rotation_and_scale_defaults(self):
        doc = _make_doc()
        msp = doc.modelspace()
        ins = msp.add_blockref("DOOR_900", (0, 0))
        ref = read_block_ref(ins)
        assert ref.rotation == pytest.approx(0.0)
        assert ref.x_scale == pytest.approx(1.0)
        assert ref.y_scale == pytest.approx(1.0)
        assert ref.layer == "0"

    def test_attribs_collected(self):
        doc = _make_doc()
        msp = doc.modelspace()
        ins = msp.add_blockref("DOOR_900", (0, 0))
        ins.add_attrib("TAG", "M-1")
        ins.add_attrib("SPEC", "900x2100")
        ref = read_block_ref(ins)
        assert ref.attribs == {"TAG": "M-1", "SPEC": "900x2100"}

    def test_attribs_empty_when_not_instantiated(self):
        doc = _make_doc()
        msp = doc.modelspace()
        ins = msp.add_blockref("DOOR_900", (0, 0))
        ref = read_block_ref(ins)
        assert ref.attribs == {}

    def test_anonymous_block_name_kept(self):
        doc = ezdxf.new("R2010")
        doc.blocks.new(name="*U1")
        msp = doc.modelspace()
        ins = msp.add_blockref("*U1", (0, 0))
        ref = read_block_ref(ins)
        assert ref.block_name == "*U1"

    def test_non_insert_returns_none(self):
        doc = _make_doc()
        msp = doc.modelspace()
        line = msp.add_line((0, 0), (10, 10))
        assert read_block_ref(line) is None

    def test_to_dict_is_json_safe(self):
        doc = _make_doc()
        msp = doc.modelspace()
        ins = msp.add_blockref("DOOR_900", (10, 20), dxfattribs={"layer": "DOOR"})
        ins.add_attrib("TAG", "M-1")
        d = read_block_ref(ins).to_dict()
        assert d["block_name"] == "DOOR_900"
        assert d["insert_point"] == [10.0, 20.0]  # tuple → list，可 JSON 序列化
        assert d["attribs"] == {"TAG": "M-1"}
        assert set(d) == {
            "block_name",
            "insert_point",
            "rotation",
            "x_scale",
            "y_scale",
            "layer",
            "handle",
            "attribs",
        }


# ── extract_attribs 测试 ─────────────────────────────────────────────


class TestExtractAttribs:
    def test_no_attrib_attr_returns_empty(self):
        class _Bare:
            pass

        assert extract_attribs(_Bare()) == {}

    def test_attribs_none_returns_empty(self):
        class _None:
            attribs = None

        assert extract_attribs(_None()) == {}


# ── extract_block_refs 测试 ──────────────────────────────────────────


class TestExtractBlockRefs:
    def test_collect_multiple_in_order(self):
        doc = _make_doc()
        msp = doc.modelspace()
        msp.add_blockref("DOOR_900", (0, 0), dxfattribs={"layer": "DOOR"})
        msp.add_blockref("DOOR_900", (500, 0), dxfattribs={"layer": "DOOR"})
        msp.add_line((0, 0), (10, 10))  # 非 INSERT，应被忽略
        refs = extract_block_refs(msp)
        assert len(refs) == 2
        assert all(r.block_name == "DOOR_900" for r in refs)
        assert [r.insert_point for r in refs] == [(0.0, 0.0), (500.0, 0.0)]

    def test_max_refs_limit(self):
        doc = _make_doc()
        msp = doc.modelspace()
        for i in range(5):
            msp.add_blockref("DOOR_900", (i * 100, 0))
        refs = extract_block_refs(msp, max_refs=3)
        assert len(refs) == 3

    def test_empty_msp(self):
        doc = ezdxf.new("R2010")
        assert extract_block_refs(doc.modelspace()) == []

    def test_nested_block_not_flattened(self):
        # 块 A 内部又插入了块 B：顶层引用应记录为 "A"，且不因嵌套被展开成 B
        doc = ezdxf.new("R2010")
        doc.blocks.new(name="B").add_line((0, 0), (10, 0))
        inner = doc.blocks.new(name="A")
        inner.add_line((0, 0), (100, 0))
        inner.add_blockref("B", (50, 0))
        msp = doc.modelspace()
        msp.add_blockref("A", (0, 0))
        refs = extract_block_refs(msp)
        assert len(refs) == 1
        assert refs[0].block_name == "A"  # 顶层块名保留，未被展平


# ── summarize_block_refs 测试 ────────────────────────────────────────


class TestSummarizeBlockRefs:
    def _ref(self, name, attribs=None):
        from src.baa_engine.parsers.block_refs import BlockRef

        return BlockRef(
            block_name=name,
            insert_point=(0.0, 0.0),
            rotation=0.0,
            x_scale=1.0,
            y_scale=1.0,
            layer="0",
            handle="",
            attribs=attribs or {},
        )

    def test_empty(self):
        s = summarize_block_refs([])
        assert s["total"] == 0
        assert s["unique_blocks"] == 0
        assert s["by_block"] == {}
        assert s["attrib_coverage"] == 0.0

    def test_by_block_and_coverage(self):
        refs = [
            self._ref("DOOR_900", {"TAG": "M-1"}),
            self._ref("DOOR_900"),
            self._ref("WINDOW_C1200"),
        ]
        s = summarize_block_refs(refs)
        assert s["total"] == 3
        assert s["unique_blocks"] == 2
        assert s["by_block"]["DOOR_900"] == 2
        assert s["by_block"]["WINDOW_C1200"] == 1
        assert s["attrib_coverage"] == pytest.approx(1 / 3, abs=1e-4)


def test_tz_block_prefixes_present():
    for p in ("M_", "C_", "D_", "W_", "TCH", "TZ"):
        assert p in TZ_BLOCK_PREFIXES


# ── DrawingParser 集成测试 ───────────────────────────────────────────


class TestDrawingParserIntegration:
    def _write_dxf(self, tmp_path) -> str:
        doc = _make_doc()
        msp = doc.modelspace()
        msp.add_line((0, 0), (5000, 0))  # 额外图元
        ins1 = msp.add_blockref(
            "DOOR_900",
            (1000, 2000),
            dxfattribs={"rotation": 90, "xscale": 1.2, "layer": "DOOR"},
        )
        ins1.add_attrib("TAG", "M-1")
        msp.add_blockref("DOOR_900", (3000, 2000), dxfattribs={"layer": "DOOR"})
        path = tmp_path / "sample.dxf"
        doc.saveas(str(path))
        return str(path)

    def test_parse_exposes_block_refs(self, tmp_path):
        path = self._write_dxf(tmp_path)
        result = DrawingParser().parse(path)
        assert result.success, result.error
        assert len(result.block_refs) == 2
        first = result.block_refs[0]
        assert first["block_name"] == "DOOR_900"
        assert first["insert_point"] == [1000.0, 2000.0]
        assert first["rotation"] == pytest.approx(90.0)
        assert first["x_scale"] == pytest.approx(1.2)
        assert first["layer"] == "DOOR"
        assert first["attribs"] == {"TAG": "M-1"}

    def test_parse_keeps_insert_as_primitive(self, tmp_path):
        # 非回归：INSERT 仍按原逻辑输出为 primitive，block_name 保留在 properties
        path = self._write_dxf(tmp_path)
        result = DrawingParser().parse(path)
        inserts = [p for p in result.primitives if p.dxf_type == "INSERT"]
        assert len(inserts) == 2
        assert inserts[0].properties.get("block_name") == "DOOR_900"

    def test_parse_block_refs_paged_branch(self, tmp_path):
        # 强制走分页分支：LARGE_FILE_MB=0 → 启用分页；PAGE_SIZE=1 → 触发分页循环
        path = self._write_dxf(tmp_path)
        parser = DrawingParser()
        parser.LARGE_FILE_MB = 0
        parser.PAGE_SIZE = 1
        result = parser.parse(path)
        assert result.success, result.error
        assert len(result.block_refs) == 2
        assert result.block_refs[0]["block_name"] == "DOOR_900"

    def test_parse_dxf_without_insert_has_empty_block_refs(self, tmp_path):
        doc = ezdxf.new("R2010")
        doc.modelspace().add_line((0, 0), (100, 100))
        path = tmp_path / "plain.dxf"
        doc.saveas(str(path))
        result = DrawingParser().parse(str(path))
        assert result.success, result.error
        assert result.block_refs == []
