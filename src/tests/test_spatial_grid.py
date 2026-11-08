"""test_spatial_grid.py — 空间哈希网格基础设施单元测试。

P0-8 后续增强（2026-11-05）：为公共模块 spatial_grid 补充单元测试，
覆盖等价性（与 relations 内部逻辑一致）与边界情况（超大 bbox 退化、
空 grid、expand 边界、去重），防止未来回归。
"""

import pytest
from src.baa_engine.semantic_analyzer.spatial_grid import (
    CELL_SIZE,
    MAX_CELLS_PER_ENTITY,
    bbox_cells,
    neighbor_cells,
    build_entities_grid,
    grid_candidates,
    nonempty_cells,
)
from src.baa_engine.semantic_analyzer.models import SemanticEntity


def _ent(eid, x, y, w, h, etype="room"):
    """构造测试实体。"""
    return SemanticEntity(
        entity_id=eid,
        entity_type=etype,
        bbox={"x": x, "y": y, "width": w, "height": h},
        layer="TEST",
        confidence=1.0,
        properties={},
    )


# ── bbox_cells：基本覆盖 ─────────────────────────────────
class TestBboxCells:
    def test_single_cell(self):
        """单 cell 内的 bbox 覆盖 1 个 cell。"""
        cells = bbox_cells({"x": 0, "y": 0, "width": 500, "height": 500})
        assert cells == [(0, 0)]

    def test_span_two_cells(self):
        """跨 2 个 cell（宽度 1500mm > CELL_SIZE）。"""
        cells = bbox_cells({"x": 0, "y": 0, "width": 1500, "height": 500})
        assert (0, 0) in cells and (1, 0) in cells
        assert len(cells) == 2

    def test_span_grid(self):
        """2×2 覆盖。"""
        cells = bbox_cells({"x": 0, "y": 0, "width": 1500, "height": 1500})
        assert len(cells) == 4
        assert set(cells) == {(0, 0), (1, 0), (0, 1), (1, 1)}

    def test_negative_coords(self):
        """负坐标（图纸左下角可为负）。int 向零截断（非向下取整）：
        int(-1500/1000)=-1，int(-1000/1000)=-1，故单 cell (-1,0)。"""
        cells = bbox_cells({"x": -1500, "y": -500, "width": 500, "height": 500})
        assert cells == [(-1, 0)]  # int(-1500/1000)=-1（向零截断，非-2）

    def test_zero_size(self):
        """零尺寸 bbox 退化为单 cell。"""
        cells = bbox_cells({"x": 0, "y": 0, "width": 0, "height": 0})
        assert cells == [(0, 0)]

    def test_missing_keys(self):
        """缺失 key 按 0 处理。"""
        cells = bbox_cells({"x": 100})
        assert cells == [(0, 0)]


# ── bbox_cells：超大 bbox 退化（边界情况） ─────────────────
class TestBboxCellsDegenerate:
    def test_huge_bbox_degrades_to_center(self):
        """超大 bbox（> MAX_CELLS_PER_ENTITY cells）退化为中心点单 cell。"""
        # 10000mm × 10000mm = 11×11 = 121 cells < 500，不退化
        cells = bbox_cells({"x": 0, "y": 0, "width": 10000, "height": 10000})
        assert len(cells) == 121

        # 30000mm × 30000mm = 31×31 = 961 cells > 500，退化为中心
        cells = bbox_cells({"x": 0, "y": 0, "width": 30000, "height": 30000})
        assert len(cells) == 1
        assert cells == [(15, 15)]  # 中心 (15000, 15000) / 1000

    def test_huge_bbox_negative(self):
        """负坐标超大 bbox 退化到中心（int 向零截断）。"""
        cells = bbox_cells({"x": -30000, "y": -30000, "width": 30000, "height": 30000})
        assert len(cells) == 1
        # 中心 (-15000, -15000) / 1000 = -15（int 向零截断）
        assert cells == [(-15, -15)]

    def test_exactly_at_limit(self):
        """恰好等于 MAX_CELLS_PER_ENTITY 不退化。"""
        # 24999mm → int(24999/1000)=24，跨 25 cells（0..24）
        # 19999mm → int(19999/1000)=19，跨 20 cells（0..19）
        # 25×20 = 500 == MAX_CELLS_PER_ENTITY → 不退化
        cells = bbox_cells({"x": 0, "y": 0, "width": 24999, "height": 19999})
        assert len(cells) == 500

        # 25000mm → int(25000/1000)=25，跨 26 cells（0..25）
        # 20000mm → int(20000/1000)=20，跨 21 cells（0..20）
        # 26×21 = 546 > 500 → 退化
        cells = bbox_cells({"x": 0, "y": 0, "width": 25000, "height": 20000})
        assert len(cells) == 1


# ── neighbor_cells：expand 边界 ─────────────────
class TestNeighborCells:
    def test_expand_zero(self):
        """expand=0 只覆盖 bbox 本身 cells。"""
        cells = neighbor_cells({"x": 0, "y": 0, "width": 500, "height": 500}, expand=0)
        assert cells == [(0, 0)]

    def test_expand_one(self):
        """expand=1 覆盖 3×3 邻域。"""
        cells = neighbor_cells({"x": 0, "y": 0, "width": 500, "height": 500}, expand=1)
        assert len(cells) == 9
        assert (0, 0) in cells and (1, 1) in cells and (-1, -1) in cells

    def test_expand_two(self):
        """expand=2 覆盖 5×5 邻域。"""
        cells = neighbor_cells({"x": 0, "y": 0, "width": 500, "height": 500}, expand=2)
        assert len(cells) == 25

    def test_span_with_expand(self):
        """跨 cell 的 bbox + expand 覆盖更大范围。"""
        cells = neighbor_cells({"x": 0, "y": 0, "width": 1500, "height": 500}, expand=1)
        # x: -1..2 (4), y: -1..1 (3) = 12
        assert len(cells) == 12


# ── build_entities_grid：分桶正确性 ─────────────────
class TestBuildEntitiesGrid:
    def test_empty(self):
        """空实体列表 → 空 grid。"""
        assert build_entities_grid([]) == {}

    def test_basic_bucket(self):
        """同 cell 实体入同桶。"""
        ents = [_ent("a", 0, 0, 500, 500), _ent("b", 100, 100, 400, 400)]
        grid = build_entities_grid(ents)
        assert len(grid[(0, 0)]) == 2
        assert grid[(0, 0)][0][0] == 0  # idx
        assert grid[(0, 0)][1][0] == 1

    def test_multi_cell_entity(self):
        """跨 cell 实体入多桶。"""
        ents = [_ent("a", 0, 0, 1500, 500)]
        grid = build_entities_grid(ents)
        assert (0, 0) in grid and (1, 0) in grid
        assert len(grid[(0, 0)]) == 1 and len(grid[(1, 0)]) == 1

    def test_nonempty_cells(self):
        """nonempty_cells 返回非空 cell 集合。"""
        ents = [_ent("a", 0, 0, 500, 500), _ent("b", 5000, 5000, 500, 500)]
        grid = build_entities_grid(ents)
        ne = nonempty_cells(grid)
        assert ne == {(0, 0), (5, 5)}


# ── grid_candidates：查询 + 去重 ─────────────────
class TestGridCandidates:
    def test_empty_grid(self):
        """空 grid 查询返回空。"""
        assert grid_candidates({}, {"x": 0, "y": 0, "width": 500, "height": 500}) == []

    def test_find_adjacent(self):
        """expand=1 能找到相邻 cell 的实体。"""
        ents = [_ent("a", 0, 0, 500, 500), _ent("b", 1200, 0, 500, 500)]
        grid = build_entities_grid(ents)
        # b 在 cell (1,0)，a 在 (0,0)；查询 a 的邻域 expand=1 应找到 b
        cands = grid_candidates(grid, ents[0].bbox, expand=1)
        idxs = [idx for idx, _ in cands]
        assert 1 in idxs  # b 被找到

    def test_not_found_far(self):
        """expand=1 找不到远处实体。"""
        ents = [_ent("a", 0, 0, 500, 500), _ent("b", 50000, 50000, 500, 500)]
        grid = build_entities_grid(ents)
        cands = grid_candidates(grid, ents[0].bbox, expand=1)
        idxs = [idx for idx, _ in cands]
        assert 1 not in idxs

    def test_dedup(self):
        """跨 cell 实体在邻域内只返回一次（去重）。"""
        # a 跨 2 个 cell，b 在 a 覆盖范围内
        ents = [_ent("a", 0, 0, 1500, 500), _ent("b", 100, 100, 400, 400)]
        grid = build_entities_grid(ents)
        cands = grid_candidates(grid, ents[0].bbox, expand=1)
        idxs = [idx for idx, _ in cands]
        # b 覆盖 cell (0,0) 和 (1,0)，但只应出现一次
        assert idxs.count(1) == 1

    def test_expand_controls_range(self):
        """expand 大小控制查询范围。"""
        ents = [_ent("a", 0, 0, 500, 500), _ent("b", 2500, 0, 500, 500)]
        grid = build_entities_grid(ents)
        # b 在 cell (2,0)，a 在 (0,0)
        # expand=1 找不到（距离 2 cells），expand=3 找到
        cands1 = grid_candidates(grid, ents[0].bbox, expand=1)
        cands3 = grid_candidates(grid, ents[0].bbox, expand=3)
        idxs1 = [idx for idx, _ in cands1]
        idxs3 = [idx for idx, _ in cands3]
        assert 1 not in idxs1
        assert 1 in idxs3


# ── 等价性：与 relations 内部逻辑一致 ─────────────────
class TestEquivalenceWithRelations:
    def test_bbox_cells_matches_relations(self):
        """spatial_grid.bbox_cells 与 relations._bbox_cells 输出一致。"""
        from src.baa_engine.semantic_analyzer import relations as rel

        cases = [
            {"x": 0, "y": 0, "width": 500, "height": 500},
            {"x": 0, "y": 0, "width": 1500, "height": 500},
            {"x": -1500, "y": -500, "width": 500, "height": 500},
            {"x": 0, "y": 0, "width": 30000, "height": 30000},  # 退化
            {"x": 100},  # 缺 key
        ]
        for bbox in cases:
            assert bbox_cells(bbox) == rel._bbox_cells(bbox), f"mismatch for {bbox}"

    def test_neighbor_cells_matches_relations(self):
        """spatial_grid.neighbor_cells 与 relations._neighbor_cells 输出一致。"""
        from src.baa_engine.semantic_analyzer import relations as rel

        bbox = {"x": 0, "y": 0, "width": 1500, "height": 500}
        for expand in (0, 1, 2, 3):
            assert neighbor_cells(bbox, expand) == rel._neighbor_cells(bbox, expand)

    def test_grid_candidates_matches_relations(self):
        """spatial_grid.grid_candidates 与 relations._grid_candidates 输出一致。"""
        from src.baa_engine.semantic_analyzer import relations as rel

        ents = [_ent("a", 0, 0, 1500, 500), _ent("b", 1200, 0, 500, 500),
                _ent("c", 50000, 50000, 500, 500)]
        grid = build_entities_grid(ents)
        rel_grid = rel._build_entities_grid(ents)
        for expand in (1, 2):
            cands = grid_candidates(grid, ents[0].bbox, expand)
            rel_cands = rel._grid_candidates(rel_grid, ents[0].bbox, expand)
            assert sorted(cands) == sorted(rel_cands)

# ── merge 网格护栏：超大退化 bbox 不得爆炸 ────────────────
def test_merge_overlapping_oversized_bbox_guard():
    """70km 级杂散 bbox 在 mm 坐标系下会覆盖数十亿格。

    回归场景：baa-file-584/b042 语义分析因 merge 网格枚举卡死。
    护栏应把极端 bbox 退化为中心一格，且不影响正常实体。
    """
    from src.baa_engine.semantic_analyzer import SemanticAnalyzer
    from src.baa_engine.semantic_analyzer.merge import _merge_overlapping

    sa = SemanticAnalyzer()
    normal = [_ent(f"r{i}", i * 2000, 0, 1000, 1000) for i in range(2001)]
    giant = _ent(
        "giant",
        -35_000_000,
        -35_000_000,
        70_000_000,
        70_000_000,
    )
    merged = _merge_overlapping(sa, normal + [giant])
    # 无重叠，全部原样保留（不因护栏丢实体）
    assert len(merged) == len(normal) + 1
