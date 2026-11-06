"""空间哈希网格基础设施（公共模块）。

P0-8 后续增强（2026-11-05）：从 relations.py 提取为公共模块，
供 SemanticAnalyzer 各阶段及未来新增分析步骤复用。

设计原则（源自 P0-2 网格索引优化）：
  - CELL_SIZE=1000mm：建筑尺度合适（墙长/房间跨度数百~数千 mm），
    避免 100mm cell 在大跨度实体上生成数万 cells 导致 MemoryError。
  - _MAX_CELLS_PER_ENTITY=500：覆盖 500m 跨度（远超任何墙体/房间实际尺度），
    同时把极端异常（如跨 500 万 mm 的测绘误差 bbox）挡在外面。
  - 按需分桶：grid 只在有实体的 cell 上建条目，查询用 _neighbor_cells 定位。

等价性约束：本模块与 relations.py 原 _bbox_cells/_neighbor_cells/
_build_entities_grid/_grid_candidates 逻辑完全一致（仅去下划线前缀），
任何改动必须保持输出等价（见 test_spatial_grid.py）。
"""

from typing import Dict, List, Optional, Set, Tuple

# ── 网格常量 ─────────────────────────────────
CELL_SIZE = 1000.0  # mm；建筑尺度合适的 cell
MAX_CELLS_PER_ENTITY = 500  # 单实体最大覆盖 cells（防超大实体爆炸）


def bbox_cells(bbox: Dict) -> List[Tuple[int, int]]:
    """返回 bbox 覆盖的所有 grid cell 坐标。

    安全兜底：若跨度导致 cell 数 > MAX_CELLS_PER_ENTITY，
    退化为只用中心点入一格（极端大实体不可能在精确邻接
    判定中命中，不影响正确性）。
    """
    bx = bbox.get("x", 0)
    by = bbox.get("y", 0)
    bw = bbox.get("width", 0)
    bh = bbox.get("height", 0)
    x1c = int(bx / CELL_SIZE)
    x2c = int((bx + bw) / CELL_SIZE)
    y1c = int(by / CELL_SIZE)
    y2c = int((by + bh) / CELL_SIZE)
    nx = x2c - x1c + 1
    ny = y2c - y1c + 1
    if nx * ny > MAX_CELLS_PER_ENTITY:
        cx = int((bx + bw / 2) / CELL_SIZE)
        cy = int((by + bh / 2) / CELL_SIZE)
        return [(cx, cy)]
    return [(gx, gy) for gx in range(x1c, x2c + 1) for gy in range(y1c, y2c + 1)]


def neighbor_cells(bbox: Dict, expand: int = 1) -> List[Tuple[int, int]]:
    """返回 bbox 所覆盖 cell 及其 expand 圈邻域的所有 cell 坐标。"""
    bx = bbox.get("x", 0)
    by = bbox.get("y", 0)
    bw = bbox.get("width", 0)
    bh = bbox.get("height", 0)
    x1c = int(bx / CELL_SIZE) - expand
    x2c = int((bx + bw) / CELL_SIZE) + expand
    y1c = int(by / CELL_SIZE) - expand
    y2c = int((by + bh) / CELL_SIZE) + expand
    return [(gx, gy) for gx in range(x1c, x2c + 1) for gy in range(y1c, y2c + 1)]


def build_entities_grid(
    entities: List,
) -> Dict[Tuple[int, int], List[Tuple[int, object]]]:
    """所有实体一次性入格（按 bbox 覆盖的 cells 分桶）。

    返回 grid[(gx, gy)] = [(idx, entity), ...]。
    """
    grid: Dict[Tuple[int, int], List[Tuple[int, object]]] = {}
    for idx, e in enumerate(entities):
        for gx, gy in bbox_cells(e.bbox):
            grid.setdefault((gx, gy), []).append((idx, e))
    return grid


def grid_candidates(
    grid: Dict[Tuple[int, int], List[Tuple[int, object]]],
    bbox: Dict,
    expand: int = 1,
) -> List[Tuple[int, object]]:
    """从网格中返回 bbox 邻域内所有候选实体（自动去重）。

    去重依据 idx（实体在 entities 列表中的下标），保证同一实体
    只出现一次，即使其覆盖多个邻域 cell。
    """
    seen: Set[int] = set()
    out: List[Tuple[int, object]] = []
    for cell in neighbor_cells(bbox, expand=expand):
        for idx, ent in grid.get(cell, []):
            if idx not in seen:
                seen.add(idx)
                out.append((idx, ent))
    return out


def nonempty_cells(grid: Dict[Tuple[int, int], List]) -> Set[Tuple[int, int]]:
    """返回 grid 中所有非空 cell 坐标集合。

    P0-6 优化：预计算非空 cell 集合，查询时跳过空 cell，
    避免大量无效 dict.get（历史：_bind_dimensions 曾因此 86 万次 get；
    该函数在 T4 后已改为「按 gx 列 + 列内 gy 二分」，不再使用本接口）。
    """
    return set(grid.keys())
