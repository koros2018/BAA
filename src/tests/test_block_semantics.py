"""Roadmap v4 T-A2 块语义分类（关联缺口 G7）— 单元测试

覆盖:
- classify_block_name: 顺序/语义（防火门/窗、门/窗、泵控制柜优先于 PUMP 等）
- 行为保持: classify.py 的 INSERT 分支与 classify_block_name 命中项一致
- lookup_legend: 图例查表
- 图例兜底: 块名未命中时用 ATTRIB 文本分类
- attach_block_refs: handle / 坐标匹配 + ATTRIB 落库 + 非 INSERT 不受影响
- 端到端: DrawingParser().parse() → analyze(..., block_refs=...)
- 未分类率对比: monkeypatch 关闭图例兜底作为基线
"""

import sys
from pathlib import Path
from unittest.mock import patch

import ezdxf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.baa_engine.drawing_parser import DrawingParser, RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.block_semantics import (
    BLOCK_FALLBACK_TYPE,
    BLOCK_NAME_RULES,
    attach_block_refs,
    classify_block_name,
)
from src.baa_engine.semantic_analyzer.legend_rules import lookup_legend


def _make_insert_prim(block_name, handle="", insert_xy=None, extra_props=None):
    props = {"block_name": block_name}
    if insert_xy is not None:
        props["insert_x"] = insert_xy[0]
        props["insert_y"] = insert_xy[1]
    if extra_props:
        props.update(extra_props)
    return RawPrimitive(
        dxf_type="INSERT",
        layer="0",
        handle=handle,
        bbox={"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
        properties=props,
    )


def _geo_type(block_name):
    prim = _make_insert_prim(block_name)
    return SemanticAnalyzer()._classify_by_geometry(prim)


# ── classify_block_name ─────────────────────────────────────────────


class TestClassifyBlockName:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("FIRE_DOOR_900", "fire_door"),
            ("防火窗", "fire_window"),
            ("DOOR_900", "door"),
            ("WINDOW_C1200", "window"),
            ("PUMP_CONTROLLER", "pump_controller"),
            ("PUMP_CTRL", "pump_controller"),
            ("水泵控制柜", "pump_controller"),
            ("FIRE_PUMP", "fire_pump"),
            ("PUMP", "fire_pump"),
            ("ELEVATOR", "elevator"),
            ("疏散指示", "exit_sign"),
            ("SIGN_BOARD", "exit_sign"),
            # 原文顺序：EXIT 先于 EXIT_SIGN，故 EXIT_SIGN 命中 exit
            ("EXIT_SIGN", "exit"),
            ("FIRE_ZONE", "fire_zone"),
            # T-A2 精化：弱电/信息点位归位 telecom_point（原为 equipment）
            ("办公网网络点", "telecom_point"),
            ("网络点", "telecom_point"),
            ("语音点", "telecom_point"),
            ("信息点", "telecom_point"),
            ("电话点", "telecom_point"),
            ("无线AP", "telecom_point"),
            # 物理解备仍为 equipment（本次不新增类型）
            ("摄像机", "equipment"),
            ("变压器", "equipment"),
        ],
    )
    def test_hits(self, name, expected):
        assert classify_block_name(name) == expected

    def test_bare_ap_no_longer_matched(self):
        # 裸 "AP" 子串规则已移除：含 AP 但非「无线AP」的块名不再被误判。
        assert classify_block_name("APPAREL") is None
        assert classify_block_name("APPAREL") != "telecom_point"
        assert classify_block_name("A$C_APP") is None
        # 仅「无线AP」命中 telecom_point
        assert classify_block_name("无线AP") == "telecom_point"

    def test_pump_controller_not_confused_with_fire_pump(self):
        # PUMP_CONTROLLER 必须命中 pump_controller，而非通用 PUMP→fire_pump
        assert classify_block_name("PUMP_CONTROLLER") == "pump_controller"
        assert classify_block_name("PUMP_CONTROLLER") != "fire_pump"

    def test_fire_door_before_door(self):
        assert classify_block_name("FIRE_DOOR") == "fire_door"
        assert classify_block_name("FIRE_WINDOW") == "fire_window"

    def test_unknown_returns_none(self):
        assert classify_block_name("A$C12345") is None

    def test_empty_and_none_return_none(self):
        assert classify_block_name("") is None
        assert classify_block_name(None) is None

    def test_rules_are_ordered_tuples(self):
        assert isinstance(BLOCK_NAME_RULES, tuple)
        # 泵控制柜判据必须排在前面的 index 小于通用 PUMP
        idx_pc = next(i for i, (k, _) in enumerate(BLOCK_NAME_RULES) if k == "PUMP_CONTROLLER")
        idx_pump = next(i for i, (k, _) in enumerate(BLOCK_NAME_RULES) if k == "PUMP")
        assert idx_pc < idx_pump
        idx_fd = next(i for i, (k, _) in enumerate(BLOCK_NAME_RULES) if k == "FIRE_DOOR")
        idx_door = next(i for i, (k, _) in enumerate(BLOCK_NAME_RULES) if k == "DOOR")
        assert idx_fd < idx_door


class TestInsertBranchBehaviorPreserved:
    """不含 block_attribs 的 INSERT，classify.py 分支结果与规则表一致。"""

    @pytest.mark.parametrize(
        "name",
        [
            "FIRE_DOOR_900",
            "防火窗",
            "DOOR_900",
            "WINDOW_C1200",
            "PUMP_CONTROLLER",
            "FIRE_PUMP",
            "ELEVATOR",
            "A$C12345",
            "UNKNOWN_BLOCK_XYZ",
        ],
    )
    def test_insert_branch_matches_rule_table(self, name):
        expected = classify_block_name(name) or BLOCK_FALLBACK_TYPE
        assert _geo_type(name) == expected


# ── lookup_legend ───────────────────────────────────────────────────


class TestLookupLegend:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("消火栓", "fire_hydrant"),
            ("喷淋", "sprinkler"),
            ("洒水喷头", "sprinkler"),
            ("灭火器", "fire_extinguisher"),
            ("烟感", "smoke_detector"),
            ("报警", "fire_alarm"),
            ("防火卷帘", "fire_curtain"),
            ("应急照明", "evacuation_lighting"),
            ("消防泵", "fire_pump"),
            ("楼梯", "stair"),
            ("出口", "exit"),
            # T-A2 精化：图例/标注文本中的弱电点位归位 telecom_point
            ("网络点", "telecom_point"),
            ("语音点", "telecom_point"),
            ("无线AP", "telecom_point"),
        ],
    )
    def test_hits(self, text, expected):
        assert lookup_legend(text) == expected

    def test_miss_returns_none(self):
        assert lookup_legend("随机文字") is None
        assert lookup_legend("") is None
        assert lookup_legend(None) is None


# ── 图例兜底 ─────────────────────────────────────────────────────────


class TestLegendFallback:
    def test_attrib_text_used_when_block_name_misses(self):
        prim = _make_insert_prim(
            "UNKNOWN_BLOCK_XYZ",
            extra_props={"block_attribs": {"TAG": "消火栓"}},
        )
        assert SemanticAnalyzer()._classify_by_geometry(prim) == "fire_hydrant"

    def test_block_name_wins_over_attrib(self):
        # 块名命中时优先，不落到图例；DOOR 块 + "消火栓" ATTRIB → door
        prim = _make_insert_prim(
            "DOOR_900",
            extra_props={"block_attribs": {"TAG": "消火栓"}},
        )
        assert SemanticAnalyzer()._classify_by_geometry(prim) == "door"

    def test_no_attrib_falls_back_to_wall(self):
        prim = _make_insert_prim("UNKNOWN_BLOCK_XYZ")
        assert SemanticAnalyzer()._classify_by_geometry(prim) == BLOCK_FALLBACK_TYPE


# ── attach_block_refs ───────────────────────────────────────────────


class TestAttachBlockRefs:
    def test_handle_match_writes_attribs(self):
        prim = _make_insert_prim("X", handle="ABC", insert_xy=(10.0, 20.0))
        refs = [
            {
                "handle": "ABC",
                "insert_point": [10.0, 20.0],
                "rotation": 90.0,
                "x_scale": 1.2,
                "y_scale": 0.8,
                "attribs": {"TAG": "M-1"},
            }
        ]
        out = attach_block_refs([prim], refs)
        assert out[0] is prim
        assert prim.properties["block_attribs"] == {"TAG": "M-1"}
        assert prim.properties["block_rotation"] == 90.0
        assert prim.properties["block_x_scale"] == 1.2
        assert prim.properties["block_y_scale"] == 0.8

    def test_coord_match_when_handle_missing(self):
        prim = _make_insert_prim("X", handle="", insert_xy=(5.0, 6.0))
        refs = [
            {
                "handle": "",
                "insert_point": [5.0, 6.0],
                "rotation": 0.0,
                "x_scale": 1.0,
                "y_scale": 1.0,
                "attribs": {"TAG": "喷淋"},
            }
        ]
        attach_block_refs([prim], refs)
        assert prim.properties["block_attribs"] == {"TAG": "喷淋"}

    def test_non_insert_untouched(self):
        line = RawPrimitive(
            dxf_type="LINE",
            layer="0",
            handle="L1",
            bbox={"x": 0.0, "y": 0.0, "width": 10.0, "height": 0.0},
            properties={},
        )
        refs = [{"handle": "L1", "insert_point": [0.0, 0.0], "attribs": {"TAG": "x"}}]
        attach_block_refs([line], refs)
        assert "block_attribs" not in line.properties

    def test_existing_props_not_overwritten(self):
        prim = _make_insert_prim(
            "X",
            handle="ABC",
            extra_props={"block_rotation": 45.0},
        )
        refs = [{"handle": "ABC", "rotation": 90.0, "attribs": {}}]
        attach_block_refs([prim], refs)
        assert prim.properties["block_rotation"] == 45.0

    def test_empty_or_missing_fields_tolerated(self):
        prim = _make_insert_prim("X", handle="ABC")
        assert attach_block_refs([prim], None) == [prim]
        assert attach_block_refs([prim], []) == [prim]
        # 缺失/异常字段不抛异常
        attach_block_refs([prim], [{"handle": "ABC"}])
        assert prim.properties.get("block_attribs") is None
        assert attach_block_refs([prim], [None, 123, {}]) == [prim]


# ── 端到端 ───────────────────────────────────────────────────────────


def _build_doc():
    doc = ezdxf.new("R2010")
    legend_blk = doc.blocks.new(name="MY_LEGEND_BLOCK")
    legend_blk.add_line((0, 0), (100, 0))
    legend_blk.add_attdef("TAG", (10, 10), dxfattribs={"height": 5})
    door_blk = doc.blocks.new(name="DOOR_900")
    door_blk.add_line((0, 0), (900, 0))
    return doc


class TestEndToEnd:
    def test_parse_analyze_with_block_refs(self, tmp_path):
        doc = _build_doc()
        msp = doc.modelspace()
        legend_ins = msp.add_blockref("MY_LEGEND_BLOCK", (1000, 1000), dxfattribs={"layer": "0"})
        legend_ins.add_attrib("TAG", "消火栓")
        msp.add_blockref("DOOR_900", (3000, 1000), dxfattribs={"layer": "0"})
        path = tmp_path / "t_a2.dxf"
        doc.saveas(str(path))

        parsed = DrawingParser().parse(str(path))
        assert parsed.success, parsed.error

        result = SemanticAnalyzer().analyze(
            parsed.primitives,
            parsed.dimensions,
            block_refs=parsed.block_refs,
        )

        stats = result.get("classification_stats")
        assert stats is not None
        assert stats["total"] > 0
        assert 0.0 <= stats["rate"] <= 1.0

        types = {e["type"] for e in result["entities"]}
        assert "fire_hydrant" in types  # 图例 ATTRIB 命中
        assert "door" in types  # 块名命中


def _legend_primitives(n=3):
    prims = []
    for i in range(n):
        x = float(i * 1000)
        prims.append(
            RawPrimitive(
                dxf_type="INSERT",
                layer="0",
                handle="",
                bbox={"x": x, "y": 0.0, "width": 100.0, "height": 100.0},
                properties={
                    "block_name": "ZZZ_EQUIP",
                    "insert_x": x,
                    "insert_y": 0.0,
                    "block_attribs": {"TAG": "消火栓"},
                },
            )
        )
    return prims


def _count_wall_with_block_name(entities, block_name):
    return sum(
        1
        for e in entities
        if e["type"] == "wall" and e.get("properties", {}).get("block_name") == block_name
    )


class TestUnclassifiedRateEvidence:
    def test_legend_fallback_not_worse_and_reclassifies(self):
        # 基线：关闭图例兜底（patch classify 内导入的符号）
        prims = _legend_primitives(3)
        with patch(
            "src.baa_engine.semantic_analyzer.classify.lookup_legend",
            return_value=None,
        ):
            base = SemanticAnalyzer().analyze(prims, [], block_refs=None)

        # 现状：图例兜底开启 + block_refs 落库
        prims2 = _legend_primitives(3)
        block_refs = [
            {
                "handle": getattr(p, "handle", ""),
                "insert_point": [p.properties["insert_x"], p.properties["insert_y"]],
                "rotation": 0.0,
                "x_scale": 1.0,
                "y_scale": 1.0,
                "attribs": {"TAG": "消火栓"},
            }
            for p in prims2
        ]
        cur = SemanticAnalyzer().analyze(prims2, [], block_refs=block_refs)

        base_unc = base["classification_stats"]["unclassified"]
        cur_unc = cur["classification_stats"]["unclassified"]
        # 未分类（unknown）数不劣于基线
        assert cur_unc <= base_unc

        # 度量口径：INSERT 块语义未覆盖回退 wall，计入 block_default / effective_rate
        base_bd = base["classification_stats"]["block_default"]
        cur_bd = cur["classification_stats"]["block_default"]
        assert base_bd == 3
        assert cur_bd == 0
        assert (
            cur["classification_stats"]["effective_rate"]
            < base["classification_stats"]["effective_rate"]
        )

        # 更直接的证据：原本回退为 wall 的图例块被重新归类（严格下降）
        base_wall = _count_wall_with_block_name(base["entities"], "ZZZ_EQUIP")
        cur_wall = _count_wall_with_block_name(cur["entities"], "ZZZ_EQUIP")
        assert base_wall == 3
        assert cur_wall < base_wall
        assert any(e["type"] == "fire_hydrant" for e in cur["entities"])
