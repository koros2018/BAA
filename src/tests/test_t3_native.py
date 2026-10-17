"""P127-T3 天正 T3 原生识别器与分类覆盖测试（合成 DXF，不依赖真实图纸）。"""

import ezdxf

from src.baa_engine.parsers.t3_native import (
    attach_t3_markers,
    detect_t3_signature,
    extract_t3,
    layer_tail,
)
from src.baa_engine.drawing_parser import DrawingParser, RawPrimitive
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer


# ── 合成 T3 图纸 ────────────────────────────────────────────


def _add_layers(doc):
    for name in ("WALL", "WINDOW", "WINDOW_TEXT", "COLUMN", "AXIS", "STAIR"):
        if name not in doc.layers:
            doc.layers.add(name)
    doc.appids.new("_TCH")


def _make_t3_doc():
    """6000x4200 双线墙房间（200 厚），门联窗洞口 + WINLIB 块窗 + _FZH 柱。"""
    doc = ezdxf.new("R2010")
    _add_layers(doc)
    msp = doc.modelspace()

    def wall(x1, y1, x2, y2):
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "WALL"})

    # 底墙 y=0/200（x 0..6000，在 x=3000..4500 留门联窗洞口）
    for y in (0, 200):
        wall(0, y, 3000, y)
        wall(4500, y, 6000, y)
    # 顶墙 y=4000/4200
    for y in (4000, 4200):
        wall(0, y, 6000, y)
    # 左/右墙
    for x in (0, 200, 5800, 6000):
        wall(x, 0, x, 4200)

    # 门：天正门库块挂 WINDOW 层（旧管线按图层错分为 window）
    door_blk = doc.blocks.new(name="$DorLib2D$00000002")
    door_blk.add_line((0, 0), (900, 0))
    door_blk.add_line((0, 0), (0, 900))
    msp.add_blockref("$DorLib2D$00000002", (3750, 100),
                     dxfattribs={"layer": "WINDOW", "rotation": 0})

    # 门联窗侧亮：WINDOW 层两条水平平行线（1500x200）
    for y in (0, 200):
        msp.add_line((3000, y), (4500, y), dxfattribs={"layer": "WINDOW"})

    # 窗：天正窗库块
    win_blk = doc.blocks.new(name="$WINLIB2D$00000001")
    win_blk.add_line((0, 0), (1200, 0))
    win_blk.add_line((0, 200), (1200, 200))
    msp.add_blockref("$WINLIB2D$00000001", (2400, 4100),
                     dxfattribs={"layer": "WINDOW"})

    # 柱：_FZH 块挂 COLUMN 层（旧图层规则 COLUMN→wall）
    col_blk = doc.blocks.new(name="_FZH")
    col_blk.add_lwpolyline([(0, 0), (400, 0), (400, 400), (0, 400)], close=True)
    msp.add_blockref("_FZH", (200, 3800), dxfattribs={"layer": "COLUMN"})

    # 立面/剖面干扰视图（x≈20000）：有墙线+窗线，但无门块/柱块 → 不应选为平面
    for i in range(10):
        wall(20000, i * 1000, 26000, i * 1000)
    for y in (2000, 2200):
        msp.add_line((21000, y), (23000, y), dxfattribs={"layer": "WINDOW"})
    return doc


# ── 识别器 ──────────────────────────────────────────────────


class TestT3NativeRecognizer:
    def test_signature_detection(self):
        doc = _make_t3_doc()
        sig = detect_t3_signature(doc)
        assert sig["is_t3"] is True
        assert sig["appid_tch"] is True
        assert sig["signature_layer_count"] >= 4

    def test_components_in_plan_only(self):
        doc = _make_t3_doc()
        t3 = extract_t3(doc)
        status = t3["status"]
        assert status["storage_form"] == "exploded_native_layers"
        assert status["diagnostic"] is None
        assert status["proxy_count"] == 0
        assert len(t3["regions"]) == 1  # 立面干扰视图被排除

        assert len(t3["doors"]) == 1
        assert (round(t3["doors"][0]["x"]), round(t3["doors"][0]["y"])) == (3750, 100)
        assert t3["doors"][0]["block"].upper().startswith("$DORLIB2D")

        assert len(t3["columns"]) == 1
        assert (round(t3["columns"][0]["x"]), round(t3["columns"][0]["y"])) == (200, 3800)

        # 线簇窗 + 块窗各一
        sources = {w["source"] for w in t3["windows"]}
        assert sources == {"lines", "block"}
        assert len(t3["windows"]) == 2
        line_win = next(w for w in t3["windows"] if w["source"] == "lines")
        assert 1400 <= line_win["width"] <= 1600

        # 墙：四面双线配成中心线（200 厚），无立面污染
        paired = [w for w in t3["walls"] if not w["single"]]
        assert len(paired) >= 4
        assert all(abs(w["thickness"] - 200) < 1 for w in paired)
        assert all(w["pos"] < 10000 for w in t3["walls"])

    def test_zero_components_has_diagnostic(self):
        """T3 特征命中但 0 构件：parse_status 必须给出诊断，不得静默。"""
        doc = ezdxf.new("R2010")
        _add_layers(doc)  # 只有图层/AppID，无实体
        t3 = extract_t3(doc)
        assert t3["status"]["is_t3"] is True
        assert t3["status"]["diagnostic"]
        assert t3["status"]["storage_form"] == "t3_signature_empty"

    def test_plain_drawing_skips(self):
        doc = ezdxf.new("R2010")
        doc.modelspace().add_line((0, 0), (1000, 1000))
        t3 = extract_t3(doc)
        assert t3["status"]["is_t3"] is False
        assert t3["walls"] == [] and t3["doors"] == []


# ── 标记落库与分类覆盖 ─────────────────────────────────────


def _prim(dxf_type, layer, handle, bbox, props=None):
    return RawPrimitive(dxf_type, layer, handle, bbox, props or {})


class TestT3ClassifyOverride:
    def test_attach_markers(self):
        doc = _make_t3_doc()
        t3 = extract_t3(doc)
        door_handle = t3["doors"][0]["handle"]
        col_handle = t3["columns"][0]["handle"]
        prims = [
            _prim("INSERT", "WINDOW", door_handle, {"x": 3750, "y": 100, "width": 0, "height": 0}),
            _prim("INSERT", "COLUMN", col_handle, {"x": 200, "y": 3800, "width": 400, "height": 400}),
        ]
        attach_t3_markers(prims, t3)
        assert prims[0].properties["_t3_native"] == "door"
        assert prims[1].properties["_t3_native"] == "column"

    def test_classify_overrides_layer_rules(self):
        doc = _make_t3_doc()
        t3 = extract_t3(doc)

        # 直接构造与识别结果对齐的图元
        d = t3["doors"][0]
        c = t3["columns"][0]
        line_handles = [h for w in t3["windows"] if w["source"] == "lines" for h in w["handles"]]
        prims = [
            _prim("INSERT", "WINDOW", d["handle"],
                  {"x": d["x"], "y": d["y"], "width": 0, "height": 0}),
            _prim("INSERT", "COLUMN", c["handle"],
                  {"x": c["x"], "y": c["y"], "width": 400, "height": 400}),
        ]
        for i, h in enumerate(line_handles):
            prims.append(_prim("LINE", "WINDOW", h,
                               {"x": 3000, "y": 0 if i == 0 else 200, "width": 1500, "height": 0}))
        attach_t3_markers(prims, t3)

        out = SemanticAnalyzer().analyze(prims, [], max_entities=100000)
        types = [e["type"] for e in out["entities"]]
        assert types.count("door") == 1
        assert types.count("column") == 1
        # 两根窗线按 gid 合并为 1 个窗实例
        assert types.count("window") == 1

    def test_wall_gid_merges_double_lines(self):
        """墙双线按识别器实例合并：两根面线 → 1 个带厚度的墙实体。"""
        doc = _make_t3_doc()
        t3 = extract_t3(doc)
        wall = next(w for w in t3["walls"] if not w["single"] and w["orientation"] == "h")
        prims = [
            _prim("LINE", "WALL", h,
                  {"x": wall["start"], "y": wall["pos"],
                   "width": wall["end"] - wall["start"], "height": 0})
            for h in wall["handles"]
        ]
        assert len(prims) == 2  # 双线：两个面
        attach_t3_markers(prims, t3)

        out = SemanticAnalyzer().analyze(prims, [], max_entities=100000)
        walls = [e for e in out["entities"] if e["type"] == "wall"]
        assert len(walls) == 1
        seg = walls[0]["properties"]["_t3_wall_seg"]
        assert abs(seg["thickness"] - 200) < 1
        assert abs(walls[0]["bbox"]["height"] - 200) < 1

    def test_shared_face_lines_keep_all_wall_instances(self):
        """共线相邻墙段复用同一根长面线（二次配对长面复用）：面线 handle 被多个
        墙实例共享时，每个实例都必须产出独立墙实体。
        修复前 handle→gid 单值覆盖，「面线全部被共享」的中间墙段整段丢失
        （d3 x=7031540 中段 5.4m 漏识别根因）。"""
        t3 = {
            "walls": [
                # 中段墙：两根面线 A/B 分别被下段/上段墙共享，自身无独占面线
                {"orientation": "v", "pos": 100.0, "start": 2000.0, "end": 4000.0,
                 "thickness": 200.0, "single": False, "handles": ["A", "B"]},
                {"orientation": "v", "pos": 100.0, "start": 0.0, "end": 1800.0,
                 "thickness": 200.0, "single": False, "handles": ["C", "A"]},
                {"orientation": "v", "pos": 100.0, "start": 4200.0, "end": 6000.0,
                 "thickness": 200.0, "single": False, "handles": ["D", "B"]},
            ],
            "doors": [], "windows": [], "columns": [],
        }
        prims = [
            _prim("LINE", "WALL", "A", {"x": 0, "y": 0, "width": 0, "height": 5400}),
            _prim("LINE", "WALL", "B", {"x": 200, "y": 0, "width": 0, "height": 6000}),
            _prim("LINE", "WALL", "C", {"x": 200, "y": 0, "width": 0, "height": 1800}),
            _prim("LINE", "WALL", "D", {"x": 200, "y": 4200, "width": 0, "height": 1800}),
        ]
        attach_t3_markers(prims, t3)
        # 共享面线必须携带全部 gid
        assert prims[0].properties["_t3_wall_gids"] == [0, 1]
        assert prims[1].properties["_t3_wall_gids"] == [0, 2]

        out = SemanticAnalyzer().analyze(prims, [], max_entities=100000)
        segs = [e["properties"]["_t3_wall_seg"] for e in out["entities"]
                if e["type"] == "wall" and e.get("properties", {}).get("_t3_wall_seg")]
        spans = sorted((s["start"], s["end"]) for s in segs)
        assert spans == [(0.0, 1800.0), (2000.0, 4000.0), (4200.0, 6000.0)]

    def test_layer_rule_without_t3_markers(self):
        """无 T3 标记时：门块仍按 WINDOW 层错分为 window（块名语义未接入的已知缺陷）；
        COLUMN 层经 T-A3 根因修复后正确归为 column（原误映为 wall）。"""
        doc = _make_t3_doc()
        t3 = extract_t3(doc)
        d = t3["doors"][0]
        c = t3["columns"][0]
        prims = [
            _prim("INSERT", "WINDOW", d["handle"],
                  {"x": d["x"], "y": d["y"], "width": 0, "height": 0}),
            _prim("INSERT", "COLUMN", c["handle"],
                  {"x": c["x"], "y": c["y"], "width": 400, "height": 400}),
        ]
        out = SemanticAnalyzer().analyze(prims, [], max_entities=100000)
        types = [e["type"] for e in out["entities"]]
        assert "door" not in types  # 门被错分为 window（需 T3 标记覆盖）
        assert "column" in types  # COLUMN 图层规则已修复：不再误映为 wall


# ── 解析器集成 ─────────────────────────────────────────────


class TestDrawingParserIntegration:
    def test_parse_attaches_t3(self, tmp_path):
        doc = _make_t3_doc()
        path = tmp_path / "t3_synthetic.dxf"
        doc.saveas(str(path))

        result = DrawingParser().parse(str(path))
        assert result.success
        assert result.parse_status is not None
        assert result.parse_status["storage_form"] == "exploded_native_layers"
        assert result.t3_components is not None
        assert result.parse_status["component_counts"]["doors"] == 1

        marked_doors = [p for p in result.primitives
                        if p.properties.get("_t3_native") == "door"]
        marked_cols = [p for p in result.primitives
                       if p.properties.get("_t3_native") == "column"]
        assert len(marked_doors) == 1
        assert len(marked_cols) == 1

        out = SemanticAnalyzer().analyze(result.primitives, result.dimensions,
                                         block_refs=result.block_refs,
                                         max_entities=100000)
        types = [e["type"] for e in out["entities"]]
        assert "door" in types and "column" in types

        # 墙实例接入分类输出：识别器每面墙（双线/单面）合并为一个实体
        wall_entities = [e for e in out["entities"] if e["type"] == "wall"]
        seg_walls = [e for e in wall_entities
                     if e.get("properties", {}).get("_t3_wall_seg")]
        assert len(seg_walls) == len(result.t3_components["walls"])
        assert len(seg_walls) >= 4
        for e in seg_walls:
            seg = e["properties"]["_t3_wall_seg"]
            if not seg["single"]:
                assert abs(seg["thickness"] - 200) < 1
        # 立面干扰视图的 10 根 WALL 线无实例标记，仍走旧图层路径逐根成墙
        plain_walls = [e for e in wall_entities
                       if not e.get("properties", {}).get("_t3_wall_seg")]
        assert len(plain_walls) == 10

    def test_layer_tail_variants(self):
        assert layer_tail("WALL") == "WALL"
        assert layer_tail("wall") == "WALL"
        assert layer_tail("S$0$WINDOW") == "WINDOW"
        assert layer_tail("") == ""
