"""
P121: 图纸类型分类器 + 损坏文件检测
覆盖 classify_drawing 和 is_likely_corrupt
"""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.baa_engine.drawing_classifier import (
    classify_drawing,
    is_likely_corrupt,
    _kw_match,
)


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


class TestShortTokenBoundaryRegression:
    """T5 回归：短 ASCII 关键词按词元边界匹配，避免 EL ⊂ elev 类误判。

    历史缺陷：`_FILENAME_RULES["电气"]` 含 `"EL"`，用 `in` 匹配时
    `synth_fire_elevator.dxf`（含 `elev`）被判为电气图，下游审计直接
    `scope_mode=skipped`，消防电梯图纸永远进不了原子函数判定。
    """

    def test_fire_elevator_filename_not_electrical(self):
        for name in (
            "synth_fire_elevator.dxf",
            "synth_fire_elev_lobby.dxf",
            "fire_elev.dxf",
            "elevator_plan.dxf",
        ):
            r = classify_drawing(name)
            assert r["type"] != "电气", f"{name} 被误判为电气图: {r}"

    def test_el_substring_victims_not_electrical(self):
        # EL 子串的其他受害者：level / panel / hotel / tunnel / parallel 等
        for name in (
            "hotel_plan.dxf",
            "panel_layout.dxf",
            "level_3.dxf",
            "parallel_walls.dxf",
            "tunnel.dxf",
        ):
            r = classify_drawing(name)
            assert r["type"] != "电气", f"{name} 被误判为电气图: {r}"

    def test_real_electrical_names_still_electrical(self):
        # 真实电气命名仍须命中：EL 词元 / 带数字后缀 / ELEC 前缀 / 中文
        for name in (
            "EL.dxf",
            "EL-1.dxf",
            "EL1.dxf",
            "EL_POWER.dxf",
            "ELEC_plan.dxf",
            "2.1电气170825-报审.dxf",
        ):
            r = classify_drawing(name)
            assert r["type"] == "电气", f"{name} 未识别为电气图: {r}"
        # 图层名路径：裸 EL 层、EL_ 前缀层、ELEC 层
        assert classify_drawing("drawing.dxf", layer_names=["EL"])["type"] == "电气"
        assert classify_drawing("drawing.dxf", layer_names=["EL_1"])["type"] == "电气"
        assert classify_drawing("drawing.dxf", layer_names=["ELEC"])["type"] == "电气"

    def test_str_not_matched_in_instrument(self):
        assert classify_drawing("instrument_layout.dxf")["type"] != "结构"
        assert classify_drawing("drawing.dxf", layer_names=["STR_BEAM"])["type"] == "结构"

    def test_elt_not_matched_in_shelter(self):
        assert classify_drawing("drawing.dxf", layer_names=["SHELTER"])["type"] != "电气"

    def test_long_keyword_keeps_substring_semantics(self):
        # 长词/带分隔符关键词不能改成边界匹配，否则会漏掉词形变化
        assert _kw_match("VENT", "ventilation_layer")
        assert _kw_match("REIN", "reinforced_concrete")
        assert _kw_match("PIPE", "pipework")
        assert _kw_match("EL_", "el_power")
        assert _kw_match("electric", "electrical_layer")

    def test_synth_fire_elevator_parse_not_skipped(self):
        """端到端：两个消防电梯样本解析后不得被类型过滤降级。"""
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.baa_engine.drawing_parser import DrawingParser

        for name in ("synth_fire_elevator.dxf", "synth_fire_elev_lobby.dxf"):
            path = os.path.join(repo_root, "data", "drawings", "real", "synth", name)
            if not os.path.exists(path):
                pytest.skip(f"data/drawings/real/synth/{name} 未入库")
            r = DrawingParser().parse(path)
            assert r.success
            assert r.drawing_type.get("type") not in ("结构", "电气", "暖通"), r.drawing_type


class TestSheetTypeKeywordBoundary:
    """图幅识别复用词元边界：ELEV 不得命中 ELEVATOR / LEVEL / fire_elevator。"""

    def test_elev_boundary(self):
        assert _kw_match("elev", "a-elev-fnsh", force_boundary=True)
        assert _kw_match("elev", "elev", force_boundary=True)
        for victim in ("elevator", "fire_elevator", "level_3", "a-elevator-pit"):
            assert not _kw_match("elev", victim, force_boundary=True), victim

    def test_sect_boundary(self):
        assert _kw_match("sect", "a-sect-mcut", force_boundary=True)
        for victim in ("section_detail", "intersection"):
            assert not _kw_match("sect", victim, force_boundary=True), victim

    def test_old_calls_unchanged(self):
        # 不传 force_boundary 时旧的子串语义保持不变（长词仍按子串）
        assert _kw_match("elevation", "elevations")
        assert _kw_match("section", "cross_section")
        assert _kw_match("VENT", "ventilation_layer")


def _prim(
    dxf_type="LINE",
    layer="0",
    width=5.0,
    height=5.0,
    length=None,
    closed=False,
    props=None,
):
    p = {
        "dxf_type": dxf_type,
        "layer": layer,
        "bbox": {"x": 0.0, "y": 0.0, "width": width, "height": height},
        "properties": dict(props or {}),
    }
    if dxf_type == "LINE":
        p["properties"].setdefault("length", length if length is not None else max(width, height))
    if closed:
        p["properties"]["closed"] = True
    return p


class TestClassifySheetType:
    def test_r1_elevation_section(self):
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = (
            [_prim("LINE", "A-ELEV", width=10, height=0.5, length=10) for _ in range(40)]
            + [_prim("LINE", "A-SECT-MCUT", width=10, height=0.5, length=10) for _ in range(20)]
            + [_prim("LINE", "0", width=10, height=0.5, length=10) for _ in range(40)]
        )
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "elevation_section"
        assert r["rule"] == "R1"
        assert r["scope_mode"] == "non_plan"
        assert r["reviewable"] is False
        assert any("A-ELEV" in e for e in r["evidence"])

    def test_r1_single_layer_not_triggered(self):
        # 只有 1 个立面图层 → 不判 R1（避免单一图层名误伤）
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "A-ELEV", width=10, height=0.5, length=10) for _ in range(60)]
        prims += [_prim("LINE", "0", width=10, height=0.5, length=10) for _ in range(40)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] != "elevation_section"

    def test_r2_unreviewable(self):
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "01 - DWGFREE.com", width=0.5, height=0, length=0.5) for _ in range(
            995
        )]
        prims += [_prim("TEXT", "01 - DWGFREE.com", width=2, height=1) for _ in range(4)]
        prims += [_prim("LINE", "0", width=0.5, height=0, length=0.5)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "unreviewable"
        assert r["rule"] == "R2"
        assert r["scope_mode"] == "non_plan"

    def test_single_layer_low_micro_not_r2(self):
        # 单层占比高但微图元不足 70% → 不得判不可审查
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "0", width=10, height=0, length=10) for _ in range(600)]
        prims += [_prim("LINE", "0", width=0.5, height=0, length=0.5) for _ in range(400)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] != "unreviewable"

    def test_high_micro_multi_layer_plan(self):
        # plans 类特征：微图元占比高但图层多 → 不得判不可审查
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = []
        for i in range(16):
            prims += [
                _prim("LINE", f"A-WALL-{i}", width=0.5, height=0, length=0.5)
                for _ in range(60)
            ]
        prims += [_prim("TEXT", "A-WALL-0", width=2, height=1) for _ in range(30)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan"

    def test_r3_plan_by_layer_tokens(self):
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "A-WALL") for _ in range(10)]
        prims += [_prim("LINE", "A-DOOR") for _ in range(10)]
        prims += [_prim("LINE", "A-WINDOW") for _ in range(10)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan"
        assert r["rule"] == "R3"
        assert r["scope_mode"] == "plan"

    def test_r3_plan_by_closed_and_annotation(self):
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LWPOLYLINE", "0", closed=True) for _ in range(40)]
        prims += [_prim("TEXT", "0", width=2, height=1) for _ in range(20)]
        prims += [_prim("LINE", "0") for _ in range(940)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan"

    def test_r4_unknown_reviewable_low_confidence(self):
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", f"custom-{i}") for i in range(10)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "unknown"
        assert r["scope_mode"] == "unknown"
        assert r["reviewable"] is True
        assert r["low_confidence"] is True

    def test_empty_primitives_unknown(self):
        from src.baa_engine.drawing_classifier import classify_sheet_type

        r = classify_sheet_type([])
        assert r["sheet_type"] == "unknown"
        assert r["reviewable"] is True

    def test_fire_elevator_plan_not_non_plan(self):
        """消防电梯样本含 ELEVATOR 图层名，不得被判成立面/剖面。"""
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "A-ELEVATOR") for _ in range(5)]
        prims += [_prim("LINE", "A-WALL") for _ in range(5)]
        prims += [_prim("LINE", "A-DOOR") for _ in range(5)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan"
        assert r["scope_mode"] == "plan"


def _poly(side, layer="0", closed=True):
    """构造边长为 side（图纸单位）的正方形闭合多段线。"""
    h = side / 2.0
    pts = [
        {"x": -h, "y": -h},
        {"x": h, "y": -h},
        {"x": h, "y": h},
        {"x": -h, "y": h},
    ]
    return _prim(
        "LWPOLYLINE", layer, closed=closed, props={"point_count": 4, "points": pts}
    )


def _text(value, layer="0"):
    return _prim("TEXT", layer, width=2, height=1, props={"text": value})


class TestPlanEvidenceGate:
    """R3 平面图必须另有平面证据，不能只靠平面词元图层（villa 误判回归）。"""

    def test_elevation_detail_with_plan_layer_tokens_is_unknown(self):
        """villa 特征：door/window/axis 图层 + Facade/Level/轴号文字 + 小面 → 未知。"""
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "wall", width=292, height=0, length=292) for _ in range(60)]
        prims += [_prim("LINE", "door", width=292, height=0, length=292) for _ in range(30)]
        prims += [_prim("LINE", "window", width=292, height=0, length=292) for _ in range(30)]
        prims += [_poly(200) for _ in range(40)]  # 200mm 见方 → 0.04㎡，非房间
        prims += [
            _text("Facade 1-9"),
            _text("Facade 9-1"),
            _text("Level 2"),
            _text("9"),
            _text("1"),
            _text("\\U+0415"),
        ]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "unknown", r
        assert r["rule"] == "R4"
        assert r["scope_mode"] == "unknown"
        assert r["reviewable"] is True
        assert r["low_confidence"] is True
        assert r["metrics"]["plan_layer_count"] >= 2
        assert r["metrics"]["plan_annotation_count"] == 0
        assert r["metrics"]["room_like_polygon_ratio"] < 0.15

    def test_stadion_like_room_polygons_keep_plan(self):
        """stadion 特征：轴号文字（无平面标注）但闭合面为房间尺度 → 平面。"""
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "A-WALL", width=1.5, height=0, length=1.5) for _ in range(60)]
        prims += [_prim("LINE", "A-DOOR", width=1.5, height=0, length=1.5) for _ in range(30)]
        prims += [_prim("LINE", "axis", width=1.5, height=0, length=1.5) for _ in range(30)]
        prims += [_poly(1.0) for _ in range(100)]  # 1㎡
        prims += [_text("1"), _text("2"), _text("A-A SECTION")]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan", r
        assert r["metrics"]["plan_annotation_count"] == 0
        assert r["metrics"]["room_like_polygon_ratio"] >= 0.15

    def test_plans_like_closed_and_annotation_keep_plan(self):
        """plans 特征：无平面词元图层，闭合面 + 标注占比高 → 平面。"""
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "0", width=0.25, height=0, length=0.25) for _ in range(80)]
        prims += [_poly(1.0) for _ in range(60)]
        prims += [_text("N.P.T. + 0.15"), _text("DEPOSITO"), _text("01")]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan", r
        assert r["metrics"]["plan_layer_count"] < 2

    def test_dim_numbers_are_plan_evidence(self):
        """东莞通特征：无平面词元图层，但尺寸数字/门窗编号充分 → 平面。"""
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "0", width=1000, height=0, length=1000) for _ in range(200)]
        prims += [_poly(1000) for _ in range(10)]  # 1㎡（mm）
        prims += [_text("2400"), _text("2.650"), _text("HM1220")]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan", r
        assert r["metrics"]["plan_annotation_count"] == 3
        assert r["metrics"]["area_unit"] == "mm"

    def test_no_text_falls_back_to_layer_tokens(self):
        """demo 特征：完全无文字，无从以标注否定平面 → 保留图层词元判据。"""
        from src.baa_engine.drawing_classifier import classify_sheet_type

        prims = [_prim("LINE", "A-WALL", width=1.75, height=0, length=1.75) for _ in range(20)]
        prims += [_prim("LINE", "A-DOOR", width=1.75, height=0, length=1.75) for _ in range(20)]
        r = classify_sheet_type(prims)
        assert r["sheet_type"] == "plan", r
        assert r["metrics"]["text_count"] == 0


class TestSheetTypeGuardsRealSamples:
    """真实样本判定守卫（数据未入库时跳过）：平面图不得被判非平面。"""

    @pytest.mark.parametrize(
        "rel,expected",
        [
            # villa-details 是立面/大样图（Facade/Level/轴号文字，无房间名/门窗编号/
            # 尺寸链，闭合面为立面轮廓小面），无平面证据 → 未知而非平面
            ("data/drawings/real/nasji/villa-details.dxf", "unknown"),
            ("data/drawings/real/nasji/multiple-stadion.dxf", "plan"),
            ("data/drawings/real/nasji/plans-of-a-two-family-house.dxf", "plan"),
            ("data/drawings/real/东莞通-建筑-外部参照（不打印）.dxf", "plan"),
            ("data/drawings/real/nasji/mosque-detail.dxf", "elevation_section"),
            ("data/drawings/real/nasji/restroom.dxf", "unreviewable"),
        ],
    )
    def test_real_sample_sheet_type(self, rel, expected):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(repo_root, rel)
        if not os.path.exists(path):
            pytest.skip(f"{rel} 未入库")
        from src.baa_engine.drawing_parser import DrawingParser

        r = DrawingParser().parse(path)
        assert r.success, r.error
        assert r.sheet_type.get("sheet_type") == expected, r.sheet_type

    def test_synth_fire_elevator_end_to_end_plan(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.baa_engine.drawing_parser import DrawingParser

        for name in ("synth_fire_elevator.dxf", "synth_fire_elev_lobby.dxf"):
            path = os.path.join(repo_root, "data", "drawings", "real", "synth", name)
            if not os.path.exists(path):
                pytest.skip(f"data/drawings/real/synth/{name} 未入库")
            r = DrawingParser().parse(path)
            assert r.success
            assert r.sheet_type.get("scope_mode") != "non_plan", r.sheet_type


class TestViewFrames:
    """P121-V: 混合图集子视框聚类（视图级 scope_mode）。"""

    def _prim(self, dxf_type, layer="0", x=0, y=0, w=1000, h=1000, **props):
        from src.baa_engine.drawing_parser import RawPrimitive

        return RawPrimitive(
            dxf_type,
            layer,
            f"h{hash((x, y, w, h, dxf_type, layer)) & 0xFFFF}",
            {"x": x, "y": y, "width": w, "height": h},
            props,
        )

    def _hline(self, x, y, length):
        """水平长线（有 start/end 端点，供退化 bbox 的 _centroid 回退）。"""
        from src.baa_engine.drawing_parser import RawPrimitive

        return RawPrimitive(
            "LINE",
            "0",
            f"h{hash((x, y, length)) & 0xFFFF}",
            {"x": x, "y": y, "width": length, "height": 0},
            {
                "start_point": {"x": x, "y": y},
                "end_point": {"x": x + length, "y": y},
                "length": length,
            },
        )

    def _text(self, val, x, y):
        return self._prim("TEXT", "0", x, y, 100, 100, text=val)

    def _poly(self, x, y, w, h):
        pts = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
        return self._prim("LWPOLYLINE", "0", x, y, w, h, points=pts, closed=True)

    def test_single_band_returns_empty(self):
        """单视幅（无 Y 断层）→ 无需拆分，返回空列表。"""
        from src.baa_engine.drawing_classifier import classify_view_frames

        prims = [self._prim("LINE", "0", 0, i * 1000, 1000, 0) for i in range(40)]
        assert classify_view_frames(prims) == []

    def test_multi_band_detects_non_plan(self):
        """两簇：上簇为立面（无房间证据），下簇为平面 → 上簇 non_plan。"""
        from src.baa_engine.drawing_classifier import classify_view_frames

        prims = []
        # 下簇（平面证据）：闭合多边形 + 房间文字
        for i in range(20):
            prims.append(self._poly(0, i * 3000, 4000, 3000))
        for i in range(8):
            prims.append(self._text("房间", 500, i * 3000))
        # 上簇（立面证据）：超长横线 + 剖面文字
        for i in range(30):
            prims.append(self._hline(0, 100000 + i * 500, 50000))
        for i in range(5):
            prims.append(self._text("剖面", 500, 100000 + i * 500))

        frames = classify_view_frames(prims)
        assert len(frames) >= 2, frames
        non_plan = [f for f in frames if f["scope_mode"] == "non_plan"]
        assert len(non_plan) >= 1, frames
        assert non_plan[0]["y_min"] > 50000  # 上簇被正确标为 non_plan

    def test_plan_band_stays_plan(self):
        """平面证据充分的簇保持 plan。"""
        from src.baa_engine.drawing_classifier import classify_view_frames

        prims = []
        for i in range(20):
            prims.append(self._poly(0, i * 3000, 4000, 3000))
        for i in range(10):
            prims.append(self._text("房间", 500, i * 3000))
        for i in range(15):
            prims.append(self._text("2400", 500, i * 3000 + 100))
        # 少量立面文字，不足以否定
        for i in range(3):
            prims.append(self._text("立面", 0, 100000 + i * 500))
        for i in range(20):
            prims.append(self._hline(0, 100000 + i * 500, 50000))

        frames = classify_view_frames(prims)
        plan = [f for f in frames if f["scope_mode"] == "plan"]
        assert len(plan) >= 1, frames
        assert plan[0]["y_min"] < 50000  # 下簇保持 plan


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

    def test_small_but_structurally_valid(self, tmp_path):
        """回归：合法的小体积 DXF（单房间 ~754B）不应被判损坏

        引擎反向生成的简易房间 DXF 仅 754 字节，曾因 min_size_bytes=10000
        被判 corrupt，导致自身产物无法回灌 /review 闭环。
        """
        from src.baa_engine.reverse_engine import ReverseEngine, RoomSpec, RoomType

        dxf = tmp_path / "small_room.dxf"
        ReverseEngine().generate_dxf(
            RoomSpec(room_type=RoomType.OFFICE, width_mm=5000, height_mm=4000), str(dxf)
        )
        assert dxf.stat().st_size < 10000
        r = is_likely_corrupt(str(dxf))
        assert r["corrupt"] is False
        assert r["recoverable"] is True


class TestIntegration:
    def test_full_parse_with_classification(self):
        """端到端：解析已知建筑图，检查 drawing_type 字段"""
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.baa_engine.drawing_parser import DrawingParser

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dxf_path = os.path.join(repo_root, "data", "drawings", "real", "test_floorplan.pdf2dxf.dxf")
        # test_floorplan 未入库（.gitignore 排除数据目录），CI 上跳过而非误报
        if not os.path.exists(dxf_path):
            pytest.skip("data/drawings/real/test_floorplan.pdf2dxf.dxf 未入库（需配置图纸数据源）")
        parser = DrawingParser()
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
