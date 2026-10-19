# -*- coding: utf-8 -*-
"""聚合作用域判定引擎测试（Roadmap v4 T-B2 / B2a）。"""


from src.baa_engine.scope_aggregator import (
    aggregate_exist_in_scopes,
    build_scopes,
)


def _e(eid, etype, x, y, w=1000, h=1000):
    return {"id": eid, "type": etype, "bbox": {"x": x, "y": y, "width": w, "height": h}}


class TestBuildScopes:
    def test_compartment_mode_when_present(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("c2", "fire_compartment", 60000, 0, 50000, 40000),
            _e("s1", "sprinkler", 10000, 10000),
            _e("s2", "sprinkler", 70000, 10000),
        ]
        sc = build_scopes(ents)
        assert sc["mode"] == "compartment"
        assert len(sc["scopes"]) == 2
        assert sc["assignment"]["s1"] == "c1"
        assert sc["assignment"]["s2"] == "c2"

    def test_grid_fallback_when_no_compartments(self):
        ents = [_e("s1", "sprinkler", 0, 0), _e("s2", "sprinkler", 60000, 0)]
        sc = build_scopes(ents, grid_size_mm=50000)
        assert sc["mode"] == "grid"
        assert len(sc["scopes"]) == 2  # 两点相距 60m > 50m 网格 → 两格
        assert sc["assignment"]["s1"] != sc["assignment"]["s2"]

    def test_same_grid_cell_grouping(self):
        sc = build_scopes([_e("a", "room", 1000, 1000), _e("b", "room", 3000, 2000)], grid_size_mm=50000)
        assert sc["mode"] == "grid"
        assert len(sc["scopes"]) == 1
        assert sc["assignment"]["a"] == sc["assignment"]["b"]

    def test_unscoped_entities_in_compartment_mode(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("s1", "sprinkler", 10000, 10000),   # 在 c1 内
            _e("s2", "sprinkler", 200000, 200000),  # 在所有分区外
        ]
        sc = build_scopes(ents)
        assert sc["assignment"]["s1"] == "c1"
        assert "s2" in sc["unscoped_entities"]
        assert "s2" not in sc["assignment"]

    def test_entity_count_per_scope(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("s1", "sprinkler", 1000, 1000),
            _e("s2", "sprinkler", 2000, 2000),
        ]
        sc = build_scopes(ents, include_types={"sprinkler"})  # 分区自身不计入
        c1 = next(s for s in sc["scopes"] if s["scope_id"] == "c1")
        assert c1["entity_count"] == 2

    def test_empty_entities(self):
        sc = build_scopes([])
        assert sc["mode"] == "grid"
        assert sc["scopes"] == []
        assert sc["assignment"] == {}


class TestAggregateExist:
    TARGETS = ["sprinkler", "fire_hydrant"]

    def test_all_scopes_satisfied_pass(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("c2", "fire_compartment", 60000, 0, 50000, 40000),
            _e("s1", "sprinkler", 10000, 10000),
            _e("s2", "sprinkler", 70000, 10000),
        ]
        sc = build_scopes(ents)
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        assert r["overall"] == "pass"
        assert r["missing_scopes"] == []
        assert r["total_hits"] == 2

    def test_all_scopes_missing(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("c2", "fire_compartment", 60000, 0, 50000, 40000),
            _e("w1", "wall", 10000, 10000),  # 无目标类型实体
        ]
        sc = build_scopes(ents)
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        assert r["overall"] == "missing"
        assert len(r["missing_scopes"]) == 2
        assert r["total_hits"] == 0

    def test_partial_hits_identify_missing_scopes(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("c2", "fire_compartment", 60000, 0, 50000, 40000),
            _e("c3", "fire_compartment", 120000, 0, 50000, 40000),
            _e("s1", "sprinkler", 10000, 10000),  # 仅 c1 命中
        ]
        sc = build_scopes(ents)
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        assert r["overall"] == "partial"
        assert set(r["missing_scopes"]) == {"c2", "c3"}
        assert r["total_hits"] == 1

    def test_unscoped_hit_counts_as_satisfied(self):
        ents = [
            _e("c1", "fire_compartment", 0, 0, 50000, 40000),
            _e("s1", "sprinkler", 200000, 200000),  # 分区外但有实体
        ]
        sc = build_scopes(ents)
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        # c1 未命中 + unscoped 命中 → partial（精确暴露 c1 缺失而非整图 pass）
        assert r["overall"] == "partial"
        assert r["missing_scopes"] == ["c1"]
        assert r["total_hits"] == 1

    def test_grid_mode_aggregation(self):
        ents = [
            _e("s1", "sprinkler", 0, 0),
            _e("s2", "sprinkler", 120000, 0),
            _e("w1", "wall", 1000, 1000),  # 与 s1 同格（不新增无目标格）
        ]
        sc = build_scopes(ents, grid_size_mm=50000, include_types={"sprinkler"})
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        assert r["mode"] == "grid"
        assert r["overall"] == "pass"  # 两格均命中

    def test_grid_cell_without_target_is_partial(self):
        """wall 独占网格无目标实体 → partial 精确指出（聚合语义正确行为）。"""
        ents = [
            _e("s1", "sprinkler", 0, 0),
            _e("w1", "wall", 120000, 0),  # 独占另一格
        ]
        sc = build_scopes(ents, grid_size_mm=50000, include_types={"sprinkler", "wall"})
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        assert r["overall"] == "partial"
        assert len(r["missing_scopes"]) == 1

    def test_no_target_type_anywhere_missing(self):
        ents = [_e("w1", "wall", 0, 0), _e("d1", "door", 5000, 5000)]
        sc = build_scopes(ents)
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, ents, sc)
        assert r["overall"] == "missing"

    def test_single_fragment_keeps_only_its_scope(self):
        """分类噪声场景：一个碎片 sprinkler 不再保整图 pass（网格模式下只保所在格）。"""
        ents = [
            _e("frag", "sprinkler", 0, 0),       # 噪声碎片
            _e("x1", "exit_sign", 120000, 0),    # 其它区域无 sprinkler
        ]
        sc = build_scopes(ents, grid_size_mm=50000)
        r = aggregate_exist_in_scopes("EXIST-004", ["exit_sign", "sign"], ents, sc)
        # exit_sign 只在 frag 所在格未出现 → frag 格 missing、x1 格… x1 是 exit_sign 命中其格
        assert r["overall"] == "partial"
        assert len(r["missing_scopes"]) == 1

    def test_empty_scopes(self):
        r = aggregate_exist_in_scopes("EXIST-005", self.TARGETS, [], build_scopes([]))
        assert r["overall"] == "no_scopes"
