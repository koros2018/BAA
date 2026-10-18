"""阶段 B M1：双线墙厚度配对验证（Step 3.8 pairing_attributes）。

覆盖:
1. 水平/垂直双线墙 → 两侧 width=间距（mm→m），source=paired_wall_thickness
2. 负例：间距越界（<100 / >600mm）、重叠率不足（<50%）、图层黑名单、
   非墙族、非退化 bbox
3. 仲裁：开洞分段多候选同间距仍命中；间距真歧义（并列）放弃；
   非标准厚度唯一候选仍注入（常见墙厚表非硬门槛）
4. 不覆盖既有非零 width
"""

import pytest

from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.baa_engine.semantic_analyzer.pairing_attributes import (
    _inject_paired_attributes,
    _pair_wall_thickness,
)


def _ent(entity_id, etype, x, y, w, h, props=None, layer="WALL"):
    e = SemanticEntity(
        entity_id, etype, {"x": x, "y": y, "width": w, "height": h}, layer=layer
    )
    if props:
        e.properties.update(props)
    return e


# ── 1. 正例：双线墙配对 ──────────────────────────────────


def test_horizontal_double_line_wall_pairs():
    """水平双线墙间距 240mm → 两侧 width=0.24, source=paired_wall_thickness。"""
    a = _ent("W1", "wall", 0, 0, 5000, 0)
    b = _ent("W2", "wall", 0, 240, 5000, 0)
    out = _pair_wall_thickness([a, b])
    assert out[0].properties["width"] == pytest.approx(0.24)
    assert out[1].properties["width"] == pytest.approx(0.24)
    assert out[0].properties["_attribute_source"] == "paired_wall_thickness"
    assert out[1].properties["_attribute_source"] == "paired_wall_thickness"


def test_vertical_double_line_wall_pairs():
    """垂直双线墙间距 200mm → 两侧 width=0.2。"""
    a = _ent("W1", "wall", 0, 0, 0, 4000)
    b = _ent("W2", "wall", 200, 0, 0, 4000)
    out = _pair_wall_thickness([a, b])
    assert out[0].properties["width"] == pytest.approx(0.2)
    assert out[1].properties["width"] == pytest.approx(0.2)


def test_unique_nonstandard_thickness_injects():
    """260mm 间距（不在常见墙厚表）但唯一候选 → 仍注入（表非硬门槛）。"""
    a = _ent("W1", "wall", 0, 0, 3000, 0)
    b = _ent("W2", "wall", 0, 260, 3000, 0)
    out = _pair_wall_thickness([a, b])
    assert out[0].properties["width"] == pytest.approx(0.26)
    assert out[1].properties["width"] == pytest.approx(0.26)


def test_opening_split_segments_agree_on_distance():
    """整墙线 + 开洞分段线：多候选同间距（240）→ 仲裁聚类后全部命中。"""
    full = _ent("W0", "wall", 0, 0, 6000, 0)  # y=0 整线
    seg1 = _ent("W1", "wall", 0, 240, 2500, 0)  # y=240 分段1
    seg2 = _ent("W2", "wall", 3500, 240, 2500, 0)  # y=240 分段2（洞口隔开）
    out = _pair_wall_thickness([full, seg1, seg2])
    assert out[0].properties["width"] == pytest.approx(0.24)
    assert out[1].properties["width"] == pytest.approx(0.24)
    assert out[2].properties["width"] == pytest.approx(0.24)


# ── 2. 负例：不满足配对条件 ──────────────────────────────


def test_distance_below_range_skipped():
    """间距 80mm < 100mm 下限 → 不注入（防双线/细线误判）。"""
    a = _ent("W1", "wall", 0, 0, 3000, 0)
    b = _ent("W2", "wall", 0, 80, 3000, 0)
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


def test_distance_above_range_skipped():
    """间距 700mm > 600mm 上限 → 不注入（可能是房间宽度）。"""
    a = _ent("W1", "wall", 0, 0, 3000, 0)
    b = _ent("W2", "wall", 0, 700, 3000, 0)
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


def test_insufficient_overlap_skipped():
    """重叠率 0.4 < 0.5（错位搭接）→ 不注入。"""
    a = _ent("W1", "wall", 0, 0, 0, 1000)  # y ∈ [0,1000]
    b = _ent("W2", "wall", 240, 600, 0, 1000)  # y ∈ [600,1600]
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


def test_no_overlap_skipped():
    """同 x 带、纵向完全无重叠 → 不注入。"""
    a = _ent("W1", "wall", 0, 0, 0, 1000)
    b = _ent("W2", "wall", 240, 2000, 0, 1000)
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


def test_non_wall_family_skipped():
    """非墙族（other）不做配对注入。"""
    a = _ent("O1", "other", 0, 0, 3000, 0)
    b = _ent("O2", "other", 0, 240, 3000, 0)
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


def test_excluded_layer_skipped():
    """标注类图层（DIM/AXIS/TEXT）不参与配对。"""
    a = _ent("W1", "wall", 0, 0, 3000, 0, layer="DIM-1")
    b = _ent("W2", "wall", 0, 240, 3000, 0, layer="AXIS")
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


def test_non_degenerate_bbox_skipped():
    """非退化 bbox（M1 只处理退化线元）→ 不注入。"""
    a = _ent("W1", "wall", 0, 0, 5000, 200)
    b = _ent("W2", "wall", 0, 240, 5000, 200)
    out = _pair_wall_thickness([a, b])
    assert "width" not in out[0].properties
    assert "width" not in out[1].properties


# ── 3. 仲裁：歧义并列放弃 ────────────────────────────────


def test_ambiguous_three_lines_tie_abandoned():
    """三线 200/300 竞争（均命中常见表、重叠相同）→ 并列放弃全部。"""
    a = _ent("W1", "wall", 0, 0, 5000, 0)  # cross=0
    b = _ent("W2", "wall", 0, 200, 5000, 0)  # 距 a=200, 距 c=100
    c = _ent("W3", "wall", 0, 300, 5000, 0)  # 距 a=300, 距 b=100
    out = _pair_wall_thickness([a, b, c])
    for ent in out:
        assert "width" not in ent.properties


# ── 4. 不覆盖既有值 / 入口 ───────────────────────────────


def test_existing_width_not_overwritten():
    """已有 width=0.2 的墙不覆盖、不盖章；对偶缺失侧正常注入。"""
    a = _ent("W1", "wall", 0, 0, 3000, 0, props={"width": 0.2})
    b = _ent("W2", "wall", 0, 240, 3000, 0)
    out = _pair_wall_thickness([a, b])
    assert out[0].properties["width"] == pytest.approx(0.2)
    assert "_attribute_source" not in out[0].properties
    assert out[1].properties["width"] == pytest.approx(0.24)
    assert out[1].properties["_attribute_source"] == "paired_wall_thickness"


def test_partner_with_width_still_evidence():
    """对偶线已有宽度（如 TEXT 来源）→ 仍作为证据，缺失侧可配对。"""
    a = _ent("W1", "wall", 0, 0, 3000, 0)  # 缺失侧
    b = _ent("W2", "wall", 0, 240, 3000, 0, props={"width": 0.24})
    out = _pair_wall_thickness([a, b])
    assert out[0].properties["width"] == pytest.approx(0.24)


def test_step_entry_smoke():
    """Step 3.8 入口签名兼容（self=None, primitives=[]）。"""
    assert _inject_paired_attributes(None, [], []) == []
    wall = _ent("W1", "wall", 0, 0, 3000, 0)
    other = _ent("W2", "wall", 0, 240, 3000, 0)
    out = _inject_paired_attributes(None, [wall, other], [])
    assert out[0].properties["width"] == pytest.approx(0.24)
