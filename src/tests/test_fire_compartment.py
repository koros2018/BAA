"""fire_compartment 分类落地（T-B2 遗留治理①）。

验证链路与真实图纸证据：
- 真实图层 A-FIRE（平面布置底图0712(1).dxf，16 条 LWPOLYLINE，
  实测闭合区域 219~5483m²）的闭合多边形 → fire_compartment 实体；
- 同层分隔线/文字/图例块等退化几何（bbox<25m²）→ other，不产分区实体；
- 产出的分区实体接入 scope_aggregator 后 mode=compartment（替代 50m 网格）。
"""

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.scope_aggregator import aggregate_exist_in_scopes, build_scopes
from src.baa_engine.semantic_analyzer import SemanticAnalyzer


def _prim(dxf_type, layer, bbox, area=0.0, extra=None):
    props = {"area": area}
    if extra:
        props.update(extra)
    return RawPrimitive(
        dxf_type=dxf_type, layer=layer, handle="", bbox=bbox, properties=props
    )


def _analyze(prims):
    return SemanticAnalyzer().analyze(prims, [], block_refs=None).get("entities", [])


# 100m x 50m 闭合分区多边形（bbox 面积 5000m²，props area 4800m²）
COMP_BBOX = {"x": 0.0, "y": 0.0, "width": 100000.0, "height": 50000.0}


class TestCompartmentClassification:
    def test_afire_closed_polyline_yields_fire_compartment(self):
        ents = _analyze([
            _prim("LWPOLYLINE", "A-FIRE", COMP_BBOX, area=4800e6,
                  extra={"closed": True}),
        ])
        comps = [e for e in ents if e["type"] == "fire_compartment"]
        assert len(comps) == 1
        assert comps[0]["bbox"]["width"] == 100000.0

    def test_afire_xref_nested_layer_matches(self):
        """xref 嵌套图层 底图平面图$0$11$0$A-FIRE 含子串 A-FIRE 同样命中。"""
        ents = _analyze([
            _prim("LWPOLYLINE", "底图平面图$0$11$0$A-FIRE", COMP_BBOX,
                  area=4800e6, extra={"closed": True}),
        ])
        assert any(e["type"] == "fire_compartment" for e in ents)

    def test_afire_boundary_line_rejected(self):
        """A-FIRE 层分隔线（LINE，退化 bbox）不产分区实体，也不走几何兜底。"""
        ents = _analyze([
            _prim("LINE", "A-FIRE",
                  {"x": 0.0, "y": 0.0, "width": 30000.0, "height": 0.0}),
        ])
        assert not any(e["type"] in ("fire_compartment", "fire_zone") for e in ents)

    def test_afire_small_hatch_rejected(self):
        """小面积 HATCH（<25m²）视为局部填充/图例，不产分区实体。"""
        ents = _analyze([
            _prim("HATCH", "A-FIRE",
                  {"x": 0.0, "y": 0.0, "width": 3000.0, "height": 3000.0}),
        ])
        assert not any(e["type"] in ("fire_compartment", "fire_zone") for e in ents)

    def test_cn_layer_closed_poly_yields_fire_zone(self):
        """中文「防火分区」图层闭合多边形 → fire_zone（同为合法分区作用域）。"""
        ents = _analyze([
            _prim("LWPOLYLINE", "防火分区", COMP_BBOX, area=4800e6,
                  extra={"closed": True}),
        ])
        assert any(e["type"] == "fire_zone" for e in ents)

    def test_legend_block_with_degenerate_bbox_rejected(self):
        """块名命中防火分区的图例块（bbox 退化）不产分区实体。"""
        ents = _analyze([
            _prim("INSERT", "0",
                  {"x": 0.0, "y": 0.0, "width": 500.0, "height": 300.0},
                  extra={"block_name": "防火分区示意图"}),
        ])
        assert not any(e["type"] in ("fire_compartment", "fire_zone") for e in ents)

    def test_text_on_fire_layer_rejected(self):
        """防火分区层 TEXT 标注不产分区实体。"""
        ents = _analyze([
            _prim("TEXT", "A-FIRE",
                  {"x": 1000.0, "y": 1000.0, "width": 2000.0, "height": 500.0},
                  extra={"text": "防火分区一"}),
        ])
        assert not any(e["type"] in ("fire_compartment", "fire_zone") for e in ents)


class TestCompartmentScopeIntegration:
    def test_produced_compartment_drives_scope_mode(self):
        """分类产出的分区实体使 build_scopes 进入 compartment 模式。"""
        ents = _analyze([
            _prim("LWPOLYLINE", "A-FIRE", COMP_BBOX, area=4800e6,
                  extra={"closed": True}),
            _prim("LWPOLYLINE", "A-FIRE",
                  {"x": 200000.0, "y": 0.0, "width": 80000.0, "height": 40000.0},
                  area=3000e6, extra={"closed": True}),
        ])
        ent_dicts = [
            {"id": e["id"], "type": e["type"], "bbox": e["bbox"]} for e in ents
        ]
        # 目标实体:落在两个分区内各一个喷淋
        ent_dicts += [
            {"id": "sp1", "type": "sprinkler",
             "bbox": {"x": 40000.0, "y": 20000.0, "width": 100.0, "height": 100.0}},
            {"id": "sp2", "type": "sprinkler",
             "bbox": {"x": 230000.0, "y": 15000.0, "width": 100.0, "height": 100.0}},
        ]
        sc = build_scopes(ent_dicts)
        assert sc["mode"] == "compartment"
        assert len(sc["scopes"]) == 2
        agg = aggregate_exist_in_scopes("EXIST-X", ["sprinkler"], ent_dicts, sc)
        assert agg["overall"] == "pass"
        assert agg["total_hits"] == 2

    def test_partial_compartment_coverage(self):
        """一个分区有喷淋、另一个没有 → partial 且指出缺失分区。"""
        ents = _analyze([
            _prim("LWPOLYLINE", "A-FIRE", COMP_BBOX, area=4800e6,
                  extra={"closed": True}),
            _prim("LWPOLYLINE", "A-FIRE",
                  {"x": 200000.0, "y": 0.0, "width": 80000.0, "height": 40000.0},
                  area=3000e6, extra={"closed": True}),
        ])
        ent_dicts = [{"id": e["id"], "type": e["type"], "bbox": e["bbox"]} for e in ents]
        ent_dicts.append(
            {"id": "sp1", "type": "sprinkler",
             "bbox": {"x": 40000.0, "y": 20000.0, "width": 100.0, "height": 100.0}}
        )
        sc = build_scopes(ent_dicts)
        agg = aggregate_exist_in_scopes("EXIST-X", ["sprinkler"], ent_dicts, sc)
        assert agg["overall"] == "partial"
        assert len(agg["missing_scopes"]) == 1

    def test_no_compartment_falls_back_to_grid(self):
        """无分区实体时保持网格回退（现有行为不变）。"""
        ent_dicts = [
            {"id": "w1", "type": "wall",
             "bbox": {"x": 0.0, "y": 0.0, "width": 10000.0, "height": 200.0}},
        ]
        sc = build_scopes(ent_dicts)
        assert sc["mode"] == "grid"
