"""
T3: 前室类规则语义修正（互斥条款 / 别名语义 / 小面积证据不足）。

验证点：
1. DIM-018/DIM-019 显式目标不再含 staircase → 不命中 stair 实体；
   别名组本身保留（其它规则仍需要 stair↔staircase 归并）。
2. 前室类条款按实体语义互斥分流（_lobby_entity_kind）：
   stair → DIM-018、shared → DIM-019、elevator/泛化 lobby → AREA-002。
3. AREA-002 优先读取 area_m2（语义层权威面积），TEXT 文字框不再用 bbox
   兜底（1971×1314mm → 2.5913㎡ 假面积曾把 9.2~14.5㎡ 前室判 critical）。
4. 面积 <2㎡ 且来自文字标签 → 证据不足（返回 None），不得判 critical。
5. 面积传播：文字标签优先按包含关系重建房间，重建不出则不传播。
6. 结果级兜底：同一实体最多保留一条前室面积 finding。
"""

import pytest

from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
from src.baa_engine.semantic_analyzer.models import SemanticEntity
from src.api.review._shared import _dedupe_lobby_area_findings


@pytest.fixture
def registry():
    return FuncRegistry()


class TestLobbyTargetSemantics:
    """DIM-018/DIM-019 显式目标不含 staircase"""

    def test_dim019_targets_exclude_staircase(self, registry):
        assert "staircase" not in registry.get("DIM-019").target_entities
        assert "staircase" not in registry.get("DIM-018").target_entities

    def test_dim019_does_not_match_stair(self, registry):
        f = registry.get("DIM-019")
        stair = {"type": "stair", "properties": {"area_m2": 7.99}}
        assert f.matches(stair) is False
        assert f.execute(stair) is None

    def test_dim018_still_matches_antechamber(self, registry):
        f = registry.get("DIM-018")
        assert f.matches({"type": "antechamber", "properties": {}}) is True

    def test_alias_group_preserved_for_other_rules(self, registry):
        """别名组未删除：DIM-020（楼梯净宽）仍能匹配 stair。"""
        assert registry.get("DIM-020").matches({"type": "stair", "properties": {}}) is True


class TestLobbyExclusivity:
    """同一前室实体只落入一条条款归属域"""

    def test_antechamber_only_dim018(self, registry):
        ent = {"type": "antechamber", "properties": {"area_m2": 8.0}}
        assert registry.get("DIM-018").execute(ent).result == "PASS"
        assert registry.get("DIM-019").execute(ent) is None
        assert registry.get("AREA-002").execute(ent) is None

    def test_elevator_lobby_only_area002(self, registry):
        ent = {"type": "elevator_lobby", "properties": {"area_m2": 7.0}}
        r = registry.get("AREA-002").execute(ent)
        assert r is not None and r.result == "PASS"
        assert registry.get("DIM-018").execute(ent) is None
        assert registry.get("DIM-019").execute(ent) is None

    def test_shared_lobby_only_dim019(self, registry):
        ent = {
            "type": "lobby",
            "properties": {"area_m2": 9.0, "is_shared_lobby": True},
        }
        assert registry.get("DIM-018").execute(ent) is None
        assert registry.get("AREA-002").execute(ent) is None
        r = registry.get("DIM-019").execute(ent)
        assert r is not None and r.result == "FAIL"
        assert r.actual == pytest.approx(9.0)

    def test_shared_lobby_10m2_pass(self, registry):
        ent = {
            "type": "lobby",
            "properties": {"area_m2": 12.0, "is_shared_lobby": True},
        }
        assert registry.get("DIM-019").execute(ent).result == "PASS"

    def test_generic_lobby_owned_by_area002(self, registry):
        """泛化 lobby 归 AREA-002，DIM-018 不再重复判（旧口径两条同时报）。"""
        ent = {"type": "lobby", "properties": {"area_m2": 5.0}}
        assert registry.get("AREA-002").execute(ent).result == "FAIL"
        assert registry.get("DIM-018").execute(ent) is None

    def test_text_label_shared_lobby_owned_by_dim019(self, registry):
        """文字标注「合用前室」是显式合用证据 → 归 DIM-019（10㎡）。"""
        ent = {"type": "antechamber", "properties": {"text": "合用前室", "area_m2": 12.0}}
        assert registry.get("DIM-019").execute(ent).result == "PASS"
        assert registry.get("DIM-018").execute(ent) is None
        assert registry.get("AREA-002").execute(ent) is None


class TestArea002ValueSource:
    """AREA-002 面积口径：area_m2 优先，文字框不做 bbox 兜底"""

    def test_prefers_area_m2_over_bbox(self, registry):
        ent = {
            "type": "lobby",
            "bbox": {"x": 0, "y": 0, "width": 1971.5, "height": 1314.3},
            "properties": {"area_m2": 9.2},
        }
        r = registry.get("AREA-002").execute(ent)
        assert r is not None
        assert r.actual == pytest.approx(9.2)
        assert r.result == "PASS"

    def test_text_label_without_area_is_insufficient(self, registry):
        ent = {
            "type": "lobby",
            "bbox": {"x": 0, "y": 0, "width": 1971.5, "height": 1314.3},
            "properties": {"text": "前室"},
        }
        assert registry.get("AREA-002").execute(ent) is None

    def test_tiny_label_area_is_insufficient(self, registry):
        """1.0~1.54㎡ 的标签前室不得判 critical（无可靠面积证据）。"""
        for area in (1.0, 1.36, 1.54):
            ent = {
                "type": "antechamber",
                "properties": {"area_m2": area, "text": "前室"},
            }
            assert registry.get("DIM-018").execute(ent) is None
            assert registry.get("DIM-019").execute(ent) is None
            assert registry.get("AREA-002").execute(ent) is None


class TestLobbyAreaPropagation:
    """文字标签按包含关系重建房间；重建不出则不传播"""

    def _room(self, rid, area, x, y, w, h):
        return SemanticEntity(
            rid,
            "room",
            {"x": x, "y": y, "width": w, "height": h},
            properties={"area_m2": area},
        )

    def test_label_reconstructed_from_containing_room(self):
        label = SemanticEntity(
            "ANTECHAMBER_T",
            "antechamber",
            {"x": 900, "y": 900, "width": 525, "height": 350},
            properties={"text": "前室"},
        )
        room = self._room("ROOM_A", 20.0, 0, 0, 5000, 4000)
        SemanticAnalyzer()._propagate_room_area([label, room])
        assert label.properties["area_m2"] == pytest.approx(20.0)
        assert label.properties["area_source"] == "reconstructed_from_ROOM_A"

    def test_label_without_containing_room_not_propagated(self):
        label = SemanticEntity(
            "ANTECHAMBER_FAR",
            "antechamber",
            {"x": 90000, "y": 90000, "width": 525, "height": 350},
            properties={"text": "前室"},
        )
        room = self._room("ROOM_A", 20.0, 0, 0, 5000, 4000)
        SemanticAnalyzer()._propagate_room_area([label, room])
        assert "area_m2" not in label.properties

    def test_non_label_keeps_nearest_center_propagation(self):
        ent = SemanticEntity(
            "LOBBY_X",
            "lobby",
            {"x": 6000, "y": 0, "width": 500, "height": 500},
            properties={},
        )
        room = self._room("ROOM_A", 20.0, 0, 0, 5000, 4000)
        SemanticAnalyzer()._propagate_room_area([ent, room])
        assert ent.properties["area_m2"] == pytest.approx(20.0)
        assert ent.properties["area_source"] == "propagated_from_ROOM_A"


class TestDedupeLobbyFindings:
    """结果级兜底：同一实体 ≤1 条前室面积 finding"""

    def test_keep_highest_priority_per_entity(self):
        details = [
            {"func_id": "DIM-018", "entity_id": "E1"},
            {"func_id": "DIM-019", "entity_id": "E1"},
            {"func_id": "AREA-002", "entity_id": "E2"},
            {"func_id": "DIM-021", "entity_id": "E1"},
        ]
        out = _dedupe_lobby_area_findings(details)
        by_entity = [d for d in out if d["entity_id"] == "E1"]
        lobby = [d for d in by_entity if d["func_id"] in {"DIM-018", "DIM-019"}]
        assert len(lobby) == 1
        assert lobby[0]["func_id"] == "DIM-019"
        # 非前室规则不受影响
        assert any(d["func_id"] == "DIM-021" for d in out)
        assert any(d["entity_id"] == "E2" for d in out)

    def test_missing_entity_id_not_deduped(self):
        details = [
            {"func_id": "DIM-018", "entity_id": ""},
            {"func_id": "DIM-019", "entity_id": ""},
        ]
        assert len(_dedupe_lobby_area_findings(details)) == 2
