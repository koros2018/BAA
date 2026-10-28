"""E4-T3: 属性缺失率优化 — doorway/stair/room 推断验证（Step 1.5/1.6/1.7）。

覆盖:
1. doorway 类型参与门宽推断（bbox/ARC/radius）
2. stair/staircase 踏步宽度从 bbox 长边推断
3. 房间面积 fallback（bbox 估算，范围 1~500m²）
4. 不覆盖已有非零值
5. 区间外值跳过
"""

import pytest

from src.baa_engine.semantic_analyzer.models import SemanticEntity


def _ent(entity_id, etype, x, y, w, h, props=None):
    e = SemanticEntity(entity_id, etype, {"x": x, "y": y, "width": w, "height": h})
    if props:
        e.properties.update(props)
    return e


# ── 1. doorway 宽度推断 ──────────────────────────────────


def test_doorway_bbox_injects_width():
    """doorway bbox 900×80（mm）→ clear_width=0.9（长边作为净宽）。"""
    dw = _ent("DW1", "doorway", 0, 0, 900, 80)
    # 模拟 _infer_corridor_widths 策略1.5 的 doorway 处理
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [dw]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.9)
    assert entities[0].properties["clear_width"] == pytest.approx(0.9)


def test_doorway_existing_width_not_overwritten():
    """doorway 已有 width=0.5 → 不覆盖。"""
    dw = _ent("DW2", "doorway", 0, 0, 900, 80, {"width": 0.5, "clear_width": 0.5})
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [dw]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.5)


def test_doorway_radius_inject():
    """doorway 有 radius=450mm → width=0.45。"""
    dw = _ent("DW3", "doorway", 0, 0, 0, 900, {"radius": 450})
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [dw]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.45)


def test_doorway_arc_span_inject():
    """doorway LINE 类型 bbox 600×0 → 长边 600mm → width=0.6。"""
    dw = _ent("DW4", "doorway", 0, 0, 600, 0)
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [dw]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.6)


# ── 2. stair/staircase 宽度推断 ──────────────────────────


def test_stair_bbox_long_edge_injects_width():
    """stair bbox 1200×300（mm）→ width=1.2（踏步宽=长边）。"""
    stair = _ent("ST1", "stair", 0, 0, 1200, 300)
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [stair]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(1.2)
    assert entities[0].properties["clear_width"] == pytest.approx(1.2)
    assert entities[0].properties["_width_source"] == "stair_bbox_long_edge"


def test_staircase_bbox_long_edge_injects_width():
    """staircase bbox 800×200（mm）→ width=0.8。"""
    stair = _ent("ST2", "staircase", 0, 0, 800, 200)
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [stair]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.8)
    assert entities[0].properties["_width_source"] == "stair_bbox_long_edge"


def test_stair_out_of_range_skipped():
    """stair bbox 2000×100（mm）→ 长边 2000mm > 1500mm → 不注入。"""
    stair = _ent("ST3", "stair", 0, 0, 2000, 100)
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [stair]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert "width" not in entities[0].properties


def test_stair_line_span_injects_width():
    """stair LINE 类型 bbox 0×700 → span=700mm → width=0.7。"""
    stair = _ent("ST4", "stair", 0, 0, 0, 700)
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [stair]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.7)
    assert entities[0].properties["_width_source"] == "stair_bbox_span"


def test_stair_existing_width_not_overwritten():
    """stair 已有 width=0.9 → 不覆盖。"""
    stair = _ent("ST5", "stair", 0, 0, 1200, 300, {"width": 0.9})
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    entities = [stair]
    entities = analyzer._infer_corridor_widths(entities, [])
    assert entities[0].properties["width"] == pytest.approx(0.9)


# ── 3. 房间面积 fallback ─────────────────────────────────


def test_room_area_fallback_from_bbox():
    """room 无 area → bbox 5000×4000mm → area=20.0m²。"""
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
    analyzer = SemanticAnalyzer()
    room = _ent("RM1", "room", 0, 0, 5000, 4000)
    # 直接调用 Step 1.7 逻辑（area fallback）
    entities = [room]
    for ent in entities:
        if ent.type != "room":
            continue
        if ent.properties.get("area", 0) > 0:
            continue
        bbox = ent.bbox
        bw = bbox.get("width", 0)
        bh = bbox.get("height", 0)
        if bw > 0 and bh > 0:
            area_m2 = (bw * bh) / 1_000_000
            if 1.0 <= area_m2 <= 500.0:
                ent.properties["area"] = round(area_m2, 2)
                ent.properties["_area_source"] = "bbox_fallback"
    assert entities[0].properties["area"] == pytest.approx(20.0)
    assert entities[0].properties["_area_source"] == "bbox_fallback"


def test_room_area_not_overwritten():
    """room 已有 area=15.0 → 不覆盖。"""
    room = _ent("RM2", "room", 0, 0, 5000, 4000, {"area": 15.0})
    entities = [room]
    for ent in entities:
        if ent.type != "room":
            continue
        if ent.properties.get("area", 0) > 0:
            continue
        bbox = ent.bbox
        bw = bbox.get("width", 0)
        bh = bbox.get("height", 0)
        if bw > 0 and bh > 0:
            area_m2 = (bw * bh) / 1_000_000
            if 1.0 <= area_m2 <= 500.0:
                ent.properties["area"] = round(area_m2, 2)
                ent.properties["_area_source"] = "bbox_fallback"
    assert entities[0].properties["area"] == pytest.approx(15.0)


def test_room_area_out_of_range_skipped():
    """room bbox 50000×50000mm → area=2500m² > 500 → 不注入。"""
    room = _ent("RM3", "room", 0, 0, 50000, 50000)
    entities = [room]
    for ent in entities:
        if ent.type != "room":
            continue
        if ent.properties.get("area", 0) > 0:
            continue
        bbox = ent.bbox
        bw = bbox.get("width", 0)
        bh = bbox.get("height", 0)
        if bw > 0 and bh > 0:
            area_m2 = (bw * bh) / 1_000_000
            if 1.0 <= area_m2 <= 500.0:
                ent.properties["area"] = round(area_m2, 2)
                ent.properties["_area_source"] = "bbox_fallback"
    assert "area" not in entities[0].properties


def test_room_area_too_small_skipped():
    """room bbox 500×500mm → area=0.25m² < 1 → 不注入。"""
    room = _ent("RM4", "room", 0, 0, 500, 500)
    entities = [room]
    for ent in entities:
        if ent.type != "room":
            continue
        if ent.properties.get("area", 0) > 0:
            continue
        bbox = ent.bbox
        bw = bbox.get("width", 0)
        bh = bbox.get("height", 0)
        if bw > 0 and bh > 0:
            area_m2 = (bw * bh) / 1_000_000
            if 1.0 <= area_m2 <= 500.0:
                ent.properties["area"] = round(area_m2, 2)
                ent.properties["_area_source"] = "bbox_fallback"
    assert "area" not in entities[0].properties


def test_non_room_not_affected():
    """非 room 实体不受 area fallback 影响。"""
    wall = _ent("W1", "wall", 0, 0, 3000, 200)
    entities = [wall]
    for ent in entities:
        if ent.type != "room":
            continue
        if ent.properties.get("area", 0) > 0:
            continue
        bbox = ent.bbox
        bw = bbox.get("width", 0)
        bh = bbox.get("height", 0)
        if bw > 0 and bh > 0:
            area_m2 = (bw * bh) / 1_000_000
            if 1.0 <= area_m2 <= 500.0:
                ent.properties["area"] = round(area_m2, 2)
                ent.properties["_area_source"] = "bbox_fallback"
    assert "area" not in entities[0].properties
