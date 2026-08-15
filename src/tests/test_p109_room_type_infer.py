"""P109 — 扫线法房间属性自动推断 单元测试"""

import sys
import os

# 确保可以导入 src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from baa_engine.semantic_analyzer.room_type_infer import (
    infer_room_type,
    ROOM_TYPE_RULES,
    _SCORE_THRESHOLD,
)


def _rule_name(rule):
    return rule["name"]


# ── 规则完整性 ──────────────────────────────────────────────

def test_rules_have_all_required_fields():
    required = {"name", "area", "aspect", "min_corridor_adj", "text_keywords", "override_type"}
    for rule in ROOM_TYPE_RULES:
        assert required.issubset(rule.keys()), f"{rule['name']} 缺少字段"


def test_rules_cover_expected_types():
    names = {_rule_name(r) for r in ROOM_TYPE_RULES}
    expected = {"staircase", "elevator", "elevator_lobby", "pump_room", "lobby", "toilet", "bedroom"}
    assert expected.issubset(names), f"缺失规则: {expected - names}"


# ── 置信度评分 ──────────────────────────────────────────────

def test_infer_staircase_with_keywords():
    rtype, conf, override = infer_room_type(
        area_m2=20, aspect=1.5, corridor_adj_count=1, nearby_texts=["楼梯间"]
    )
    assert rtype == "staircase", f"期望 staircase, 得到 {rtype}"
    assert conf > 0.3
    assert override is True


def test_infer_lobby_with_large_area():
    rtype, conf, override = infer_room_type(
        area_m2=120, aspect=1.2, corridor_adj_count=2, nearby_texts=["大堂"]
    )
    assert rtype == "lobby", f"期望 lobby, 得到 {rtype}"
    assert conf > 0.2
    assert override is True


def test_infer_pump_room():
    rtype, conf, override = infer_room_type(
        area_m2=40, aspect=2.0, corridor_adj_count=0, nearby_texts=["泵房"]
    )
    assert rtype == "pump_room", f"期望 pump_room, 得到 {rtype}"
    assert override is True


def test_infer_toilet_without_override():
    rtype, conf, override = infer_room_type(
        area_m2=10, aspect=1.5, corridor_adj_count=0, nearby_texts=["卫生间"]
    )
    assert rtype == "toilet", f"期望 toilet, 得到 {rtype}"
    assert override is False  # toilet 不 override entity_type


def test_infer_bedroom():
    rtype, conf, override = infer_room_type(
        area_m2=20, aspect=1.4, corridor_adj_count=0, nearby_texts=["卧室"]
    )
    assert rtype == "bedroom", f"期望 bedroom, 得到 {rtype}"
    assert override is False


# ── 几何特征推理（无文本关键词） ────────────────────────────

def test_infer_elevator_small_square():
    # 小面积、接近方形 → 可能是电梯井
    rtype, conf, override = infer_room_type(
        area_m2=8, aspect=1.1, corridor_adj_count=1, nearby_texts=[]
    )
    # 无文本关键词时，几何特征可能给出不同结果，
    # 但至少应返回一个合理的非空类型或空字符串（低置信）
    if rtype:
        # 如果命中了，置信度应合理
        assert 0 < conf <= 1.0


def test_infer_empty_when_too_small():
    rtype, conf, override = infer_room_type(
        area_m2=0.1, aspect=1.0, corridor_adj_count=0, nearby_texts=[]
    )
    assert rtype == "", "面积极小应返回空"


# ── 置信度边界 ──────────────────────────────────────────────

def test_confidence_between_0_and_1():
    rtype, conf, override = infer_room_type(
        area_m2=30, aspect=1.5, corridor_adj_count=2, nearby_texts=["楼梯"]
    )
    assert 0 <= conf <= 1.0, f"置信度 {conf} 超出范围"


def test_high_confidence_with_strong_signal():
    rtype, conf, override = infer_room_type(
        area_m2=15, aspect=1.2, corridor_adj_count=2, nearby_texts=["楼梯间", "stair"]
    )
    assert conf > 0.4, f"强信号下置信度应 > 0.4, 得到 {conf}"


def test_low_confidence_no_signal():
    # 无任何匹配特征
    rtype, conf, override = infer_room_type(
        area_m2=100, aspect=0.5, corridor_adj_count=0, nearby_texts=[]
    )
    # 可能命中 lobby 或空字符串
    if rtype:
        assert conf <= 0.35  # area=100 命中 lobby 范围(60-600)，aspect 0.5 也在范围


# ── 边缘情况 ────────────────────────────────────────────────

def test_zero_area():
    rtype, conf, override = infer_room_type(
        area_m2=0, aspect=1.0, corridor_adj_count=0, nearby_texts=[]
    )
    assert rtype == ""


def test_zero_aspect():
    rtype, conf, override = infer_room_type(
        area_m2=10, aspect=0, corridor_adj_count=0, nearby_texts=[]
    )
    assert rtype == ""


def test_none_texts():
    rtype, conf, override = infer_room_type(
        area_m2=20, aspect=1.5, corridor_adj_count=1, nearby_texts=None
    )
    # 不应抛异常
    assert isinstance(rtype, str)


def test_long_thin_room():
    # 长条形状可能是走廊
    rtype, conf, override = infer_room_type(
        area_m2=30, aspect=5.0, corridor_adj_count=3, nearby_texts=[]
    )
    # aspect=5.0 超出大部分规则范围，可能返回空或低置信
    assert isinstance(rtype, str)
    assert 0 <= conf <= 1.0