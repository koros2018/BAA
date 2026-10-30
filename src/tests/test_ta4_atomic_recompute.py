"""T-A4 验收：依赖属性的原子函数（DIM/AREA/COUNT）结果可复算且正确。

验证注入链路（尺寸绑定 Step 3.5 / TEXT Step 3.6 / native+几何 Step 3.7）产出的
属性能被原子函数正确消费：
1. DIM 类：注入 width/clear_width → 判定结果正确（PASS/FAIL/属性缺失跳过）
2. AREA 类：注入 area → 判定正确
3. COUNT 类：注入 count → 判定正确
4. 可复算：同一实体重复执行结果一致（确定性）；注入属性值可从
   _dimension_source/_attribute_source 追溯复算
5. 无属性不误判：退化实体（无宽度数据）→ None 跳过，不产生违规
"""

import pytest

from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer


@pytest.fixture(scope="module")
def registry():
    return FuncRegistry()


def _ent(etype, x, y, w, h, props=None):
    return {
        "id": f"{etype.upper()}_TEST",
        "type": etype,
        "bbox": {"x": x, "y": y, "width": w, "height": h},
        "layer": "TEST",
        "properties": props or {},
    }


# ── 1. DIM 类：宽度属性注入 → 判定正确 ───────────────────


def test_dim006_exit_door_width_injected(registry):
    """疏散门净宽 ≥1.4m：exit_door 注入 clear_width=1.5（米）→ PASS；=1.2 → FAIL。

    注意必须用 exit_door：普通 door 宽度 <1.3m 被有意跳过
    （0.8~1.3m 是标准单开门，不适用 1.4m 疏散门条款）。
    """
    func = registry._funcs["DIM-006"]
    ok = func.execute(_ent("exit_door", 0, 0, 1500, 100, {"clear_width": 1.5}))
    assert ok is not None and ok.result == "PASS"
    assert ok.actual == pytest.approx(1.5)
    bad = func.execute(_ent("exit_door", 0, 0, 1200, 100, {"clear_width": 1.2}))
    assert bad is not None and bad.result == "FAIL"
    # 普通 door 1.2m：守卫生效 → None 跳过（不是误报违规）
    plain = func.execute(_ent("door", 0, 0, 1200, 100, {"clear_width": 1.2}))
    assert plain is None


def test_dim004_corridor_width_dimension_source(registry):
    """走道净宽 ≥1.1m：_dimension_source 注入 width=1.2 → PASS，可追溯。"""
    func = registry._funcs["DIM-004"]
    ent = _ent("corridor", 0, 0, 12000, 1200, {
        "width": 1.2, "_dimension_source": "relations_bind", "_dimension_raw": 1200.0,
    })
    res = func.execute(ent)
    assert res is not None and res.result == "PASS"
    # 可复算：从追溯字段复算注入值（_dimension_raw 1200mm → 1.2m）
    assert res.actual == pytest.approx(ent["properties"]["_dimension_raw"] / 1000.0)


def test_dim001_stair_width_text_source(registry):
    """楼梯净宽 ≥1.1m（GB50016-5.5.18 通用最小值）：TEXT 编码注入 width=1.3 → PASS；1.05 → FAIL。"""
    func = registry._funcs["DIM-001"]
    ok = func.execute(_ent("stair", 0, 0, 2000, 1300, {"width": 1.3}))
    assert ok is not None and ok.result == "PASS"
    bad = func.execute(_ent("stair", 0, 0, 2000, 1100, {"width": 1.05}))
    assert bad is not None and bad.result == "FAIL"
    # 边界容差：1.09m（<2% 偏差，0.991*1.1）→ 测量误差跳过（None）
    assert func.execute(_ent("stair", 0, 0, 2000, 1100, {"width": 1.09})) is None


def test_dim113_door_mm_unit_auto_convert(registry):
    """房间疏散门 ≥0.9m：疏散门实体 mm 属性（>100 启发式）自动换算 → 正确判定。

    误报治理：普通 ``door`` 无疏散门语义（卫生间/设备/管井门），
    与 DIM-006/DIM-009 同口径不判违规；显式标注后仍判定（不漏报）。
    """
    func = registry._funcs["DIM-113"]
    ok = func.execute(_ent("exit_door", 0, 0, 1000, 100, {"width": 1000}))
    assert ok is not None and ok.result == "PASS"
    assert ok.actual == pytest.approx(1.0)
    bad = func.execute(_ent("exit_door", 0, 0, 800, 100, {"width": 800}))
    assert bad is not None and bad.result == "FAIL"
    # 普通 door（无疏散门证据）→ 适用性未知，不判违规
    assert func.execute(_ent("door", 0, 0, 800, 100, {"width": 800})) is None
    # 显式标注为疏散门的 door 仍判定（不漏报）
    explicit = func.execute(
        _ent("door", 0, 0, 800, 100, {"width": 800, "is_evacuation_door": True})
    )
    assert explicit is not None and explicit.result == "FAIL"


def test_dim009_float_boundary_tolerance(registry):
    """DIM-009 边界：实测 0.8999999999999 vs 阈值 0.9 → PASS（表示误差不报违规）。

    真实偏差不放宽：0.85 < 0.9 → 仍 FAIL。
    """
    func = registry._funcs["DIM-009"]
    ok = func.execute(_ent("exit_door", 0, 0, 900, 0, {"clear_width": 0.8999999999999418}))
    assert ok is not None and ok.result == "PASS"
    bad = func.execute(_ent("exit_door", 0, 0, 850, 0, {"clear_width": 0.85}))
    assert bad is not None and bad.result == "FAIL"


# ── 2. AREA 类 ───────────────────────────────────────────


def test_area001_refuge_floor_area(registry):
    """避难层面积 ≥5㎡：注入 area=60 → PASS；area=3 → FAIL。"""
    func = registry._funcs["AREA-001"]
    ok = func.execute(_ent("refuge_floor", 0, 0, 80000, 60000, {"area": 60.0}))
    assert ok is not None and ok.result == "PASS"
    bad = func.execute(_ent("refuge_floor", 0, 0, 20000, 15000, {"area": 3.0}))
    assert bad is not None and bad.result == "FAIL"


# ── 3. COUNT 类 ──────────────────────────────────────────


def test_count001_exit_count(registry):
    """安全出口 ≥2：COUNT-001 按 楼层/防火分区 实体判定
    （target_entities=[floor, fire_zone]），注入 count=2 → PASS；count=1 → FAIL。"""
    func = registry._funcs["COUNT-001"]
    ok = func.execute(_ent("floor", 0, 0, 0, 0, {"count": 2}))
    assert ok is not None and ok.result == "PASS"
    bad = func.execute(_ent("fire_zone", 0, 0, 0, 0, {"count": 1}))
    assert bad is not None and bad.result == "FAIL"
    # exit 类型不是 COUNT-001 的判定对象（是 COUNT-015/019/021 等的）
    assert func.execute(_ent("exit", 0, 0, 0, 0, {"count": 2})) is None


# ── 4. 可复算（确定性） ──────────────────────────────────


def test_recompute_deterministic(registry):
    """同一实体重复执行 N 次 → 结果与 actual 完全一致。"""
    func = registry._funcs["DIM-006"]
    ent = _ent("door", 0, 0, 1500, 100, {"clear_width": 1.5})
    results = [func.execute(ent) for _ in range(5)]
    assert all(r is not None for r in results)
    assert len({(r.result, round(r.actual, 6)) for r in results}) == 1


def test_injected_value_traceable(registry):
    """注入属性可复算：geometry_length 注入的 length 与 bbox 长边/1000 一致。"""
    from src.baa_engine.semantic_analyzer.geometry_attributes import (
        _inject_geometry_lengths,
    )
    from src.baa_engine.semantic_analyzer.models import SemanticEntity

    wall = SemanticEntity("WALL_T", "wall", {"x": 0, "y": 0, "width": 3600, "height": 0})
    out = _inject_geometry_lengths([wall])
    injected = out[0].properties["length"]
    assert injected == pytest.approx(3.6)
    assert out[0].properties["_attribute_source"] == "geometry_length"
    # 复算：bbox 长边 / 1000 == 注入值
    assert max(3600, 0) / 1000.0 == pytest.approx(injected)


# ── 5. 无属性不误判 ──────────────────────────────────────


@pytest.mark.parametrize("func_id,etype", [
    ("DIM-001", "stair"),
    ("DIM-004", "corridor"),
    ("DIM-006", "door"),
    ("DIM-113", "door"),
])
def test_missing_width_skips_judgment(registry, func_id, etype):
    """退化实体无宽度数据 → None 跳过判定，不产生误报违规。"""
    func = registry._funcs[func_id]
    assert func.execute(_ent(etype, 0, 0, 0, 0, {})) is None


def test_t3_native_wall_width_end_to_end():
    """端到端：T3 标记墙实体经 analyze → properties.width=厚度（m）→ DIM 可读。

    用合成 T3 标记图元走完整管线，验证 Step 3.7 注入链路（回归保护）。
    面线 bbox 须真实退化（水平墙面线 height=0）：此时 bbox 策略只写 length，
    width 只能由 Step 3.7 从 _t3_wall_seg.thickness 注入并盖章 t3_native。
    """
    seg = {"orientation": "h", "pos": 100.0, "start": 0.0, "end": 3000.0,
           "thickness": 200.0, "single": False}
    prim = RawPrimitive(
        dxf_type="LINE",
        layer="WALL",
        handle="T3W1",
        bbox={"x": 0.0, "y": 100.0, "width": 3000.0, "height": 0.0},
        properties={
            "_t3_wall_gid": 0,
            "_t3_wall_seg": seg,
            "length": 3000.0,
            "angle": 0.0,
            "start_point": {"x": 0.0, "y": 100.0},
            "end_point": {"x": 3000.0, "y": 100.0},
        },
    )
    out = SemanticAnalyzer().analyze([prim], [], block_refs=None)
    walls = [e for e in out["entities"] if e["type"] == "wall"]
    assert walls, "T3 标记墙实体应产出"
    wall = walls[0]
    assert wall["properties"].get("width") == pytest.approx(0.2)
    assert wall["properties"].get("length") == pytest.approx(3.0)
    assert wall["properties"].get("_attribute_source") == "t3_native"
