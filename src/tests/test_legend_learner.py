# -*- coding: utf-8 -*-
"""图例学习器测试（阶段 B M4）。"""

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.legend_learner import (
    _learn_legend_blocks,
    _legend_type_of_text,
)


def _insert(block_name, x, y, layer="0"):
    return RawPrimitive(
        dxf_type="INSERT",
        layer=layer,
        handle=f"I_{block_name}_{x}",
        bbox={"x": x, "y": y, "width": 0.0, "height": 0.0},
        properties={"block_name": block_name, "insert_x": x, "insert_y": y},
    )


def _text(text, x, y):
    return RawPrimitive(
        dxf_type="TEXT",
        layer="0",
        handle=f"T_{text}_{x}",
        bbox={"x": x, "y": y, "width": 400.0, "height": 300.0},
        properties={"text": text},
    )


class TestLegendTypeOfText:
    def test_keyword_hits(self):
        assert _legend_type_of_text("消火栓系统") == "fire_hydrant"
        assert _legend_type_of_text("SPRINKLER-UP") == "sprinkler"

    def test_no_hit_returns_none(self):
        assert _legend_type_of_text("随机文字ABC") is None
        assert _legend_type_of_text("") is None


class TestLearnLegendBlocks:
    def test_row_aligned_pair_learned(self):
        prims = [_insert("k300", 0, 0), _text("消火栓", 800, 100)]
        learned = _learn_legend_blocks(prims)
        assert learned == {"k300": "fire_hydrant"}

    def test_row_alignment_dy_window(self):
        # TEXT 中心 y=300（bbox y=150+height/2）与 INSERT 同行带共现；
        # 中心 y=950 超出 500mm 行带不共现
        near = _learn_legend_blocks([_insert("kA", 0, 0), _text("喷淋", 500, 150)])
        assert near == {"kA": "sprinkler"}
        far = _learn_legend_blocks([_insert("kB", 0, 0), _text("喷淋", 500, 800)])
        assert far == {}

    def test_row_alignment_dx_window(self):
        # dx>8000 视为另一图例区，不共现
        far = _learn_legend_blocks([_insert("kC", 0, 0), _text("喷淋", 9000, 0)])
        assert far == {}

    def test_low_confidence_not_learned(self):
        # 同块名与两个不同类型竞争（各 2 次，50% < 60%）→ 不学习
        prims = [
            _insert("kD", 0, 0),
            _text("消火栓", 800, 0),
            _insert("kD", 100, 2000),
            _text("灭火器", 900, 2000),
            _insert("kD", 200, 4000),
            _text("消火栓", 1000, 4000),
            _insert("kD", 300, 6000),
            _text("灭火器", 1100, 6000),
        ]
        assert _learn_legend_blocks(prims) == {}

    def test_single_sample_uncontested_learned(self):
        # 单一类型无竞争：图例行结构即强证据，共现 1 次即学习
        assert _learn_legend_blocks([_insert("kE", 0, 0), _text("喷淋", 500, 0)]) == {
            "kE": "sprinkler"
        }

    def test_majority_wins_when_confident(self):
        # 3 次共现中 2 次喷淋 1 次烟感 → 67% ≥ 60%，取最高频 sprinkler
        prims = [
            _insert("kF", 0, 0),
            _text("喷淋", 500, 0),
            _insert("kF", 0, 1000),
            _text("洒水", 500, 1000),
            _insert("kF", 0, 2000),
            _text("烟感", 500, 2000),
        ]
        assert _learn_legend_blocks(prims) == {"kF": "sprinkler"}

    def test_empty_primitives(self):
        assert _learn_legend_blocks([]) == {}


class TestClassifyIntegration:
    def test_learned_map_used_in_insert_classification(self):
        analyzer = SemanticAnalyzer()
        analyzer._legend_learned = {"GHJKBVV": "fire_hydrant"}
        prim = _insert("GHJKBVV", 0, 0)
        assert analyzer._classify_by_geometry(prim) == "fire_hydrant"

    def test_learned_map_wins_over_landscape_guard(self):
        # 学习优先级高于图层守卫（LA- 层块学习命中仍按学习类型）
        analyzer = SemanticAnalyzer()
        analyzer._legend_learned = {"k300": "fire_hydrant"}
        prim = _insert("k300", 0, 0, layer="LA-小铺装")
        assert analyzer._classify_by_geometry(prim) == "fire_hydrant"

    def test_no_learned_map_falls_through(self):
        # 无学习表时走原链路：0 层未识别块 → wall 兜底
        analyzer = SemanticAnalyzer()
        prim = _insert("UNKNOWN_XYZ", 0, 0)
        assert analyzer._classify_by_geometry(prim) == "wall"

    def test_block_name_rule_beats_learned_map(self):
        # 静态块名规则优先于学习表（学习表只兜底未识别块名）
        analyzer = SemanticAnalyzer()
        analyzer._legend_learned = {"DOOR_900": "fire_hydrant"}
        prim = _insert("DOOR_900", 0, 0)
        assert analyzer._classify_by_geometry(prim) == "door"
