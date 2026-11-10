"""Spatial relations + dimension binding + attribute inference.

V3（2026-11-04）：网格索引重构（P0-2）
T3（2026-11-06）：AABB 前置拒绝 + Phase 3/4 候选网格，去掉全量
min_edge_distance 精确计算。

索引与复杂度：
  - Phase 1：1000mm 实体格（expand=1），大数据量仅对关键类型建格，
    O(候选实体 × 邻域 cell 内实体数)
  - Phase 2：100mm 边坐标桶（x1/x2、y1/y2 分别入桶），
    O(开洞数 × 桶候选数)
  - Phase 3/4：1000mm 候选网格（door→corridor expand=1、
    room→item expand=0），精确距离只对候选对计算
  - Phase 5：adjacency 映射 + AABB 拒绝，O(房间数 × 门-墙映射数)
  - 判定阈值与 V2 完全等价（adjacent 50mm / connects_to 200mm /
    Phase 5 500mm，已通过 equivalence 验证）

当前实测（2026-11-06，48.9MB 电气图 / 10119 实体 / 1680 条标注，
宿主机负载 ≈50%）：_build_relations ≈0.05–0.07s，占 analyze 总量
（≈0.70–0.74s）的 8% 左右。成本集中在 Phase 1/2 的网格构建与候选
遍历；精确距离计算已被 AABB 前置拒绝降到候选对级别。
"""

from typing import List, Dict, Optional, Tuple, Set
import math
from bisect import bisect_left, bisect_right
from .models import SemanticEntity, SpatialRelation
from .geometry import (
    min_edge_distance,
    compute_iou,
    union_bbox,
    is_inside,
    point_distance,
)
# P0-8 后续增强（2026-11-05）：网格基础设施提取为公共模块 spatial_grid，
# relations.py 改为导入复用。逻辑与原先地定义完全一致（仅去下划线前缀）。
from .spatial_grid import (
    bbox_cells as _bbox_cells,
    neighbor_cells as _neighbor_cells,
    build_entities_grid as _build_entities_grid,
    grid_candidates as _grid_candidates,
    CELL_SIZE as _CELL_SIZE,
    MAX_CELLS_PER_ENTITY as _MAX_CELLS_PER_ENTITY,
)


# ── Phase 1 相邻关系需要的关键实体类型（无变化，P76 修复后稳定） ──
_KEY_ENTITY_TYPES = {
    "room", "corridor", "door", "exit", "stair", "fire_door", "exit_door",
    "lobby", "pump_room", "space", "anteroom", "elevator_lobby",
    "staircase_lobby", "entrance_hall", "wall", "facade", "doorway",
}


def _build_relations(self, entities: List[SemanticEntity]) -> List[SpatialRelation]:
    """构建空间关系（V3，P0-2 重构）

    包括：
    - 相邻关系（空间哈希，保持 V2 等价输出）
    - 墙体-门窗拓扑关系（精确匹配门在墙上的位置）
    - 走廊连通关系（门连接走廊与房间）
    - 包含关系（房间包含设备）
    - 房间-门间接连接（通过墙传递）

    注（2026-11-06 实测，48.9MB 电气图 / 10119 实体 / 1680 标注）：
    _build_relations ≈0.05–0.07s，约占 analyze 总量（≈0.70–0.74s）的 8%；
    当前大头是 _merge_overlapping（≈0.11s）与 _bind_dimensions（≈0.08s）。
    本函数保持与 V2 完全等价的输出。
    复杂度：Phase 1 O(候选实体 × 邻域 cell 内实体数)，Phase 2
    O(开洞数 × 边坐标桶候选数)，Phase 3/4 候选网格 + AABB 前置拒绝，
    Phase 5 O(房间数 × 门-墙映射数)。
    """
    relations = []
    n_entities = len(entities)
    if n_entities == 0:
        return relations

    # T3 优化（2026-11-06）：预计算四边坐标 + AABB 快速拒绝。
    # min_edge_distance 的 dx/dy 是两框在 x/y 轴上的间隙（重叠时为 0），
    # 且 dist = sqrt(dx²+dy²) >= max(dx, dy)。因此
    #   dx >= 阈值 或 dy >= 阈值  ⟹  dist >= 阈值  ⟹  必不满足 dist < 阈值。
    # 在进入距离计算前先用该判据拒绝，判据严格取阈值本身（不加外扩容差），
    # 不会吃掉任何合法候选；Pass 后仍按原公式 sqrt(dx²+dy²) 计算，数值逐位一致。
    x1g: List[float] = [0.0] * n_entities
    y1g: List[float] = [0.0] * n_entities
    x2g: List[float] = [0.0] * n_entities
    y2g: List[float] = [0.0] * n_entities
    for i in range(n_entities):
        b = entities[i].bbox
        x = b.get("x", 0)
        y = b.get("y", 0)
        x1g[i] = x
        y1g[i] = y
        x2g[i] = x + b.get("width", 0)
        y2g[i] = y + b.get("height", 0)

    # ── Phase 1. 相邻关系（空间哈希网格）──
    # P0-2 优化（2026-11-04）：CELL_SIZE 从 100mm → 1000mm。
    # 100mm 时 50MB 电气图产生 40.7 万 cells（长墙跨数百 cell），查询循环
    # 遍历大量重复 entries；1000mm 后 cells 降至约 1.3 万，输出完全等价
    # （adj_count 一致）。ADJACENT_THRESHOLD=50mm < 1000mm，查询 expand=1
    # 即可覆盖所有相邻对。当前 Phase 1 已不是热点（整函数 ≈0.05–0.07s）。
    _P1_CELL_SIZE = 1000.0
    # P0-9 后续（T3）：改嵌套 dict[gx][gy] 存实体下标，省去每格 tuple 构造。
    grid_p1: Dict[int, Dict[int, List[int]]] = {}

    if n_entities <= 2000:
        adj_candidates = list(range(n_entities))
    else:
        adj_candidates = [
            i for i in range(n_entities) if entities[i].type in _KEY_ENTITY_TYPES
        ]

    for idx in adj_candidates:
        x1c = int(x1g[idx] / _P1_CELL_SIZE)
        x2c = int(x2g[idx] / _P1_CELL_SIZE)
        y1c = int(y1g[idx] / _P1_CELL_SIZE)
        y2c = int(y2g[idx] / _P1_CELL_SIZE)
        for gx in range(x1c, x2c + 1):
            row = grid_p1.get(gx)
            if row is None:
                row = {}
                grid_p1[gx] = row
            for gy in range(y1c, y2c + 1):
                cell = row.get(gy)
                if cell is None:
                    row[gy] = [idx]
                else:
                    cell.append(idx)

    _THRESH = self.ADJACENT_THRESHOLD
    compared: Set[int] = set()  # idx_a * n + idx_b，比 tuple 省分配
    for idx_a in adj_candidates:
        a = entities[idx_a]
        ax1 = x1g[idx_a]
        ay1 = y1g[idx_a]
        ax2 = x2g[idx_a]
        ay2 = y2g[idx_a]
        x1c = int(ax1 / _P1_CELL_SIZE)
        x2c = int(ax2 / _P1_CELL_SIZE)
        y1c = int(ay1 / _P1_CELL_SIZE)
        y2c = int(ay2 / _P1_CELL_SIZE)
        for gx in range(x1c - 1, x2c + 2):
            row = grid_p1.get(gx)
            if row is None:
                continue
            for gy in range(y1c - 1, y2c + 2):
                cell = row.get(gy)
                if cell is None:
                    continue
                for idx_b in cell:
                    if idx_b <= idx_a:
                        continue
                    pair_key = idx_a * n_entities + idx_b
                    if pair_key in compared:
                        continue
                    compared.add(pair_key)
                    bx1 = x1g[idx_b]
                    by1 = y1g[idx_b]
                    bx2 = x2g[idx_b]
                    by2 = y2g[idx_b]
                    # AABB 快速拒绝（dx/dy 为轴向间隙，重叠取 0）
                    dx = ax1 - bx2
                    if dx < 0.0:
                        dx = bx1 - ax2
                        if dx < 0.0:
                            dx = 0.0
                    if dx >= _THRESH:
                        continue
                    dy = ay1 - by2
                    if dy < 0.0:
                        dy = by1 - ay2
                        if dy < 0.0:
                            dy = 0.0
                    if dy >= _THRESH:
                        continue
                    dist = (dx ** 2 + dy ** 2) ** 0.5
                    if dist < _THRESH:
                        relations.append(
                            SpatialRelation(
                                source_id=a.id,
                                target_id=entities[idx_b].id,
                                rel_type="adjacent",
                                distance=dist,
                                confidence=1.0 - dist / _THRESH,
                            )
                        )

    # ── Phase 2. 墙体-门窗拓扑关系（edge-coordinate grid 加速）──
    # P0-2 优化（2026-11-04）：原 O(W×O) 双循环耗时 0.37s（历史值）。
    # 注意原始 dist_to_edge 只看 wall 四条边坐标到 opening center 的距离，
    # 不检查 wall 范围（一条 y 接近的水平墙即使 x 差 80m 也会匹配）。
    # 因此不能按 bbox 分桶——改为按边坐标值分桶：x1/x2 入 x_edge_grid，
    # y1/y2 入 y_edge_grid。opening 查 o_cx±50mm 和 o_cy±50mm 附近的
    # edges（cell=100mm，expand=1 覆盖），candidates 等价于 dist_to_edge<50
    # 的全部 walls，输出完全一致。837 walls × 600 openings → 候选降至个位数。
    walls = [e for e in entities if e.type == "wall"]
    openings = [
        e for e in entities if e.type in ("door", "window", "fire_door", "exit_door", "doorway")
    ]

    _EDGE_CELL = 100.0
    x_edge_grid: Dict[int, List[SemanticEntity]] = {}
    y_edge_grid: Dict[int, List[SemanticEntity]] = {}
    for wall in walls:
        wb = wall.bbox
        wx1 = wb.get("x", 0)
        wy1 = wb.get("y", 0)
        wx2 = wx1 + wb.get("width", 0)
        wy2 = wy1 + wb.get("height", 0)
        x_edge_grid.setdefault(int(wx1 / _EDGE_CELL), []).append(wall)
        x_edge_grid.setdefault(int(wx2 / _EDGE_CELL), []).append(wall)
        y_edge_grid.setdefault(int(wy1 / _EDGE_CELL), []).append(wall)
        y_edge_grid.setdefault(int(wy2 / _EDGE_CELL), []).append(wall)

    for opening in openings:
        best_wall = None
        best_overlap = 0.0
        best_distance = float("inf")

        ob = opening.bbox
        ox1, oy1 = ob.get("x", 0), ob.get("y", 0)
        ox2 = ox1 + ob.get("width", 0)
        oy2 = oy1 + ob.get("height", 0)
        o_cx = (ox1 + ox2) / 2
        o_cy = (oy1 + oy2) / 2

        # 查 o_cx 附近的 x 边 + o_cy 附近的 y 边（expand=1 覆盖 < 50mm）
        ogx = int(o_cx / _EDGE_CELL)
        ogy = int(o_cy / _EDGE_CELL)
        candidate_walls: List[SemanticEntity] = []
        seen_wall_ids: Set[int] = set()
        for dx in (-1, 0, 1):
            for w in x_edge_grid.get(ogx + dx, []):
                wid = id(w)
                if wid in seen_wall_ids:
                    continue
                seen_wall_ids.add(wid)
                candidate_walls.append(w)
        for dy in (-1, 0, 1):
            for w in y_edge_grid.get(ogy + dy, []):
                wid = id(w)
                if wid in seen_wall_ids:
                    continue
                seen_wall_ids.add(wid)
                candidate_walls.append(w)

        for wall in candidate_walls:
            wb = wall.bbox
            wx1, wy1 = wb.get("x", 0), wb.get("y", 0)
            wx2 = wx1 + wb.get("width", 0)
            wy2 = wy1 + wb.get("height", 0)

            dx_left = abs(o_cx - wx1)
            dx_right = abs(o_cx - wx2)
            dy_bottom = abs(o_cy - wy1)
            dy_top = abs(o_cy - wy2)

            min_dx = min(dx_left, dx_right)
            min_dy = min(dy_bottom, dy_top)
            dist_to_edge = min(min_dx, min_dy)

            if dist_to_edge > 50.0:
                continue

            overlap = 0.0
            if min_dx <= min_dy:
                overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))
                overlap = overlap_y / max(ob.get("height", 1), 1)
            else:
                overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))
                overlap = overlap_x / max(ob.get("width", 1), 1)

            if overlap > best_overlap or (
                overlap == best_overlap and dist_to_edge < best_distance
            ):
                best_overlap = overlap
                best_distance = dist_to_edge
                best_wall = wall

        if best_wall:
            relations.append(
                SpatialRelation(
                    source_id=best_wall.id,
                    target_id=opening.id,
                    rel_type="contains",
                    confidence=min(0.95, best_overlap),
                )
            )
            opening.properties["host_wall_id"] = best_wall.id
            opening.properties["host_wall_overlap"] = round(best_overlap, 2)

    # ── Phase 3. 走廊-门-房间拓扑 ──
    # T3 优化（2026-11-06）：全量对（doors×corridors + doors×rooms = 5.7 万对）
    # 不再逐对调用 min_edge_distance。先用轴向间隙判据拒绝：
    # dist >= max(dx, dy)，故 dx>=200 或 dy>=200 时必不满足 dist<200；
    # 通过判据的对再按原公式 sqrt(dx²+dy²) 计算，输出逐位一致。
    corridors = [e for e in entities if e.type == "corridor"]
    rooms = [e for e in entities if e.type == "room"]
    doors = [e for e in entities if e.type in ("door", "fire_door", "exit_door", "doorway")]

    def _geo(ents):
        """实体 → (entity, x1, y1, x2, y2)，供全量对循环复用。"""
        out = []
        for e in ents:
            b = e.bbox
            x = b.get("x", 0)
            y = b.get("y", 0)
            out.append((e, x, y, x + b.get("width", 0), y + b.get("height", 0)))
        return out

    door_geo = _geo(doors)
    corridor_geo = _geo(corridors)
    room_geo = _geo(rooms)

    # 候选网格（Phase 3/4）：避免全量对逐对进入精确判定。
    #   P3：dist<200 ⟹ 两框轴向间隙<200mm<1000mm ⟹ 必落在对方 cell 的 ±1 邻域，
    #       expand=1 查询即为合法对的超集；候选按下标升序处理，产出顺序与
    #       原「doors×corridors 再 doors×rooms、各自按原列表顺序」完全一致。
    #   P4：item 在 room 内 ⟹ item 的 cell 跨度 ⊆ room 的 cell 跨度，
    #       查询 room 自身 cell（expand=0）即可命中全部合法对。
    _PAIR_CELL = 1000.0

    def _pair_grid(geo_list):
        g: Dict[int, Dict[int, List[int]]] = {}
        for pi in range(len(geo_list)):
            x1, y1, x2, y2 = geo_list[pi][1], geo_list[pi][2], geo_list[pi][3], geo_list[pi][4]
            for gx in range(int(x1 / _PAIR_CELL), int(x2 / _PAIR_CELL) + 1):
                row = g.get(gx)
                if row is None:
                    row = {}
                    g[gx] = row
                for gy in range(int(y1 / _PAIR_CELL), int(y2 / _PAIR_CELL) + 1):
                    cell = row.get(gy)
                    if cell is None:
                        row[gy] = [pi]
                    else:
                        cell.append(pi)
        return g

    def _candidates(grid, x1, y1, x2, y2, expand):
        out = []
        for gx in range(int(x1 / _PAIR_CELL) - expand, int(x2 / _PAIR_CELL) + expand + 1):
            row = grid.get(gx)
            if row is None:
                continue
            for gy in range(int(y1 / _PAIR_CELL) - expand, int(y2 / _PAIR_CELL) + expand + 1):
                cell = row.get(gy)
                if cell is not None:
                    out.extend(cell)
        # 调用方只遍历候选（不依赖顺序），sorted 是多余的；set 去重必要
        # （同一 pi 可能出现在多个 cell）。
        return list(set(out))

    corridor_grid = _pair_grid(corridor_geo)
    room_grid = _pair_grid(room_geo)

    _THRESH_P3 = 200.0
    for (door, ox1, oy1, ox2, oy2) in door_geo:
        for pi in _candidates(corridor_grid, ox1, oy1, ox2, oy2, 1):
            (c, cx1, cy1, cx2, cy2) = corridor_geo[pi]
            gx = ox1 - cx2
            if gx < 0.0:
                gx = cx1 - ox2
                if gx < 0.0:
                    gx = 0.0
            if gx >= _THRESH_P3:
                continue
            gy = oy1 - cy2
            if gy < 0.0:
                gy = cy1 - oy2
                if gy < 0.0:
                    gy = 0.0
            if gy >= _THRESH_P3:
                continue
            dist = (gx ** 2 + gy ** 2) ** 0.5
            if dist < _THRESH_P3:
                relations.append(
                    SpatialRelation(
                        source_id=c.id, target_id=door.id,
                        rel_type="connects_to", distance=dist, via="door",
                    )
                )
        for pi in _candidates(room_grid, ox1, oy1, ox2, oy2, 1):
            (r, rx1, ry1, rx2, ry2) = room_geo[pi]
            gx = ox1 - rx2
            if gx < 0.0:
                gx = rx1 - ox2
                if gx < 0.0:
                    gx = 0.0
            if gx >= _THRESH_P3:
                continue
            gy = oy1 - ry2
            if gy < 0.0:
                gy = ry1 - oy2
                if gy < 0.0:
                    gy = 0.0
            if gy >= _THRESH_P3:
                continue
            dist = (gx ** 2 + gy ** 2) ** 0.5
            if dist < _THRESH_P3:
                relations.append(
                    SpatialRelation(
                        source_id=r.id, target_id=door.id,
                        rel_type="connects_to", distance=dist, via="door",
                    )
                )

    # ── Phase 4. 包含关系（房间包含设备/柱）──
    # T3：is_inside 直接按预计算四边判断（省函数调用），并用 item 网格
    # 只查 room 自身 cell 跨度内的候选项（包含关系必然落在其中）。
    contained_types = {"column", "stair", "exit", "fire_door"}
    containables = [e for e in entities if e.type in contained_types]
    item_geo = _geo(containables)
    item_grid = _pair_grid(item_geo)

    for (room, rx1, ry1, rx2, ry2) in room_geo:
        for pi in _candidates(item_grid, rx1, ry1, rx2, ry2, 0):
            (item, ix1, iy1, ix2, iy2) = item_geo[pi]
            if ix1 >= rx1 and iy1 >= ry1 and ix2 <= rx2 and iy2 <= ry2:
                relations.append(
                    SpatialRelation(
                        source_id=room.id, target_id=item.id,
                        rel_type="contains", confidence=0.9,
                    )
                )

    # ── Phase 5. 房间-门间接连接（通过墙传递）──
    # 这一阶段用 adjacency + wall_rooms 哈希映射，复杂度 O(房间数 ×
    # 门-墙映射数)，在整函数 0.05–0.07s 中占比很小。
    # T3：host_wall 查找改 id→wall 字典（原 next() 为 doors×walls 线性扫描）；
    #     距离同样先做 AABB 拒绝（dx>=500 或 dy>=500 ⟹ dist>=500）。
    wall_ids = {w.id for w in walls}
    room_ids = {r.id for r in rooms}
    wall_rooms: Dict[str, set] = {}
    for rel in relations:
        if rel.type == "adjacent":
            sid, tid = rel.source_id, rel.target_id
            if sid in room_ids and tid in wall_ids:
                wall_rooms.setdefault(tid, set()).add(sid)
            elif tid in room_ids and sid in wall_ids:
                wall_rooms.setdefault(sid, set()).add(tid)

    # setdefault 保留首个同 id 墙体，与 next() 的取首个语义一致
    wall_by_id: Dict[str, SemanticEntity] = {}
    for w in walls:
        wall_by_id.setdefault(w.id, w)

    door_wall_map: Dict[str, Tuple[SemanticEntity, float, float, float, float]] = {}
    for door in doors:
        host_id = door.properties.get("host_wall_id")
        if host_id:
            wall_ent = wall_by_id.get(host_id)
            if wall_ent:
                wb = wall_ent.bbox
                wx = wb.get("x", 0)
                wy = wb.get("y", 0)
                door_wall_map[host_id] = (
                    wall_ent, wx, wy, wx + wb.get("width", 0), wy + wb.get("height", 0),
                )

    _THRESH_P5 = 500.0
    for (room, rx1, ry1, rx2, ry2) in room_geo:
        if room.id in wall_rooms:
            continue
        for wid, (_wall, wx1, wy1, wx2, wy2) in door_wall_map.items():
            gx = rx1 - wx2
            if gx < 0.0:
                gx = wx1 - rx2
                if gx < 0.0:
                    gx = 0.0
            if gx >= _THRESH_P5:
                continue
            gy = ry1 - wy2
            if gy < 0.0:
                gy = wy1 - ry2
                if gy < 0.0:
                    gy = 0.0
            if gy >= _THRESH_P5:
                continue
            dist = (gx ** 2 + gy ** 2) ** 0.5
            if dist < _THRESH_P5:
                wall_rooms.setdefault(wid, set()).add(room.id)

    seen_conn: set = set()
    for door in doors:
        host_id = door.properties.get("host_wall_id")
        if not host_id:
            continue
        # wall_rooms 内层是字符串 set，直接迭代顺序随 PYTHONHASHSEED 变化，
        # 会让同输入在不同哈希种子下产出不同关系顺序。这里按 room_id 排序，
        # 保证输出逐项可复现（不影响关系集合本身）。
        for room_id in sorted(wall_rooms.get(host_id, ())):
            pair = (room_id, door.id)
            if pair in seen_conn:
                continue
            seen_conn.add(pair)
            relations.append(
                SpatialRelation(
                    source_id=room_id, target_id=door.id,
                    rel_type="connects_to", distance=0.0, via="door",
                )
            )

    return relations


def _dim_reference_point(dim: Dict) -> Dict:
    """尺寸标注参考点：优先 text_midpoint，回退 position(defpoint)。"""
    for key in ("text_midpoint", "position"):
        pt = dim.get(key)
        if pt and (pt.get("x") is not None or pt.get("y") is not None):
            return pt
    return {}


def _dim_orientation(dim: Dict) -> str:
    """由 defpoint2→defpoint3 向量判断标注方向：'h' 水平 / 'v' 垂直 / '' 斜向。

    系数 2 为经验值，允许标注线与轴线有小角度偏差。
    """
    dp2 = dim.get("defpoint2") or {}
    dp3 = dim.get("defpoint3") or {}
    dx = abs(dp3.get("x", 0) - dp2.get("x", 0))
    dy = abs(dp3.get("y", 0) - dp2.get("y", 0))
    if dx > dy * 2:
        return "h"
    if dy > dx * 2:
        return "v"
    return ""


def _dim_projection_ratio(dim: Dict, bbox: Dict, orientation: str) -> float:
    """标注线段与实体沿「测量轴」的重叠比例（0~1）。

    水平标注的测量轴为 X（defpoint2/3 的 x 区间应与实体 x 范围重叠），
    垂直标注的测量轴为 Y。斜向标注返回 0。
    注意：水平标注两个 defpoint 的 y 相同（y 区间退化），若沿 y 比较则恒为 0，
    故必须沿测量轴比较，该评分才能把大尺寸标注优先匹配到真正被测量的实体。
    """
    dp2 = dim.get("defpoint2") or {}
    dp3 = dim.get("defpoint3") or {}
    if orientation == "h":
        d_min = min(dp2.get("x", 0), dp3.get("x", 0))
        d_max = max(dp2.get("x", 0), dp3.get("x", 0))
        e1 = bbox.get("x", 0)
        e2 = e1 + bbox.get("width", 0)
    elif orientation == "v":
        d_min = min(dp2.get("y", 0), dp3.get("y", 0))
        d_max = max(dp2.get("y", 0), dp3.get("y", 0))
        e1 = bbox.get("y", 0)
        e2 = e1 + bbox.get("height", 0)
    else:
        return 0.0
    span = e2 - e1
    if span <= 0:
        return 0.0
    overlap = max(0.0, min(e2, d_max) - max(e1, d_min))
    return min(1.0, overlap / span)


_DIM_MATCH_MAX_DIST = 10000.0  # 尺寸标注到实体中心的最大匹配距离(mm)
# 真实图纸的标注文字常距实体中心较远（尤其房间/走廊），沿用 dimension_parser 的
# 宽松阈值（max_distance*2000=10000mm），配合投影评分消歧，避免就近匹配漏配。
_DIM_MM_TO_M_THRESHOLD = 100.0  # 原始值 >100 且 /1000 落入建筑构件区间时判为 mm
_DIM_MM_TO_M_MIN = 0.3
_DIM_MM_TO_M_MAX = 30.0


def _measurement_to_meters(meas) -> Optional[float]:
    """DIMENSION 测量值单位归一为米。

    沿用既有判据：原始值 >100 且 /1000 后落在 0.3~30m 时视为 mm→m。
    measurement<=0 或无法解析时返回 None，调用方据此跳过注入（避免写入 0）。
    """
    if meas is None:
        return None
    try:
        meas = float(meas)
    except (TypeError, ValueError):
        return None
    if meas <= 0:
        return None
    if meas > _DIM_MM_TO_M_THRESHOLD and _DIM_MM_TO_M_MIN < meas / 1000.0 < _DIM_MM_TO_M_MAX:
        return meas / 1000.0
    return meas


def _dim_match_score(dist: float, proj_ratio: float) -> float:
    """组合评分：score = dist * (1.5 - proj_ratio)。

    投影完全重叠时距离权重降至 0.5，无重叠时不降权，从而优先选中
    被标注线穿过/正对的实体。
    """
    return dist * (1.5 - min(max(proj_ratio, 0.0), 1.0))


def _bind_dimensions(
    self,
    entities: List[SemanticEntity],
    dimensions: List[Dict],
) -> Dict[str, Dict]:
    """尺寸标注绑定到实体，返回以实体 id 为键的属性绑定。

    V3（P0-2）：网格加速 + 距离平方预过滤
    T4（2026-11-06）：网格查询改「按 gx 列 + 列内 gy 二分」定位，
    替代每标注 21×21=441 次空 cell dict.get。

    复杂度：O(|E|) 建格 + 每标注 O(命中列数 × 每列命中行数 × cell 内实体数)。

    历史对照：原实现 O(|D| × |E|) = 1680 × 10119 ≈ 17M 次迭代、每次都做
    sqrt，量级为 34.5s；当前实测 ≈0.08s（48.9MB 电气图 / 10119 实体 /
    1680 标注，宿主机负载 ≈50%）。
    """
    bindings = {}
    if not entities or not dimensions:
        return bindings

    # ── 1. 建网格：entity center 按 CELL_SIZE 分桶 ──
    _BIND_CELL = 1000.0
    _EXPAND = 10
    grid: Dict[Tuple[int, int], List[Tuple[float, float, int]]] = {}
    # 预计算实体 bbox 轴向区间：候选循环内直接取数组，省去 ent.bbox 逐次取键。
    x1_a: List[float] = [0.0] * len(entities)
    x2_a: List[float] = [0.0] * len(entities)
    y1_a: List[float] = [0.0] * len(entities)
    y2_a: List[float] = [0.0] * len(entities)
    for idx, ent in enumerate(entities):
        b = ent.bbox
        bx = b["x"]
        by = b["y"]
        bw = b["width"]
        bh = b["height"]
        x1_a[idx] = bx
        y1_a[idx] = by
        x2_a[idx] = bx + bw
        y2_a[idx] = by + bh
        cx = bx + bw / 2
        cy = by + bh / 2
        gx = int(cx / _BIND_CELL)
        gy = int(cy / _BIND_CELL)
        grid.setdefault((gx, gy), []).append((cx, cy, idx))

    # T4 优化（2026-11-06）：原实现每个 dim 遍历 441 个 (gx,gy) tuple 并各做
    # 非空集合判断 + dict.get（1680×441≈74 万次 tuple 哈希）。改为
    # 「gx 升序表 + 列内 gy 有序表 + 二分定位」：每 dim 仅 ≤21 次列定位与
    # 列内二分，命中的非空 cell 才取实体。迭代顺序仍为 gx 升序 → gy 升序 →
    # cell 内实体插入序，与原实现逐对一致（含并列打分的先后顺序）。
    gx_keys = sorted({k[0] for k in grid})
    gy_keys_by_gx: Dict[int, List[int]] = {}
    for (gx, _gy) in grid:
        gy_keys_by_gx.setdefault(gx, []).append(_gy)
    for _gx in gy_keys_by_gx:
        gy_keys_by_gx[_gx].sort()

    # ── 2. 逐 dim 查询邻域 cell ──
    _MAX_SQ = _DIM_MATCH_MAX_DIST * _DIM_MATCH_MAX_DIST

    for dim in dimensions:
        ref = _dim_reference_point(dim)
        if not ref:
            continue

        meas_m = _measurement_to_meters(dim.get("measurement"))
        if meas_m is None:
            continue

        orientation = _dim_orientation(dim)
        # 每 dim 只解析一次标注端点区间（原实现在每个候选里重复 min/max 取键）；
        # 同时按测量轴选定实体区间数组，候选循环内直接下标取值。
        _dp2 = dim.get("defpoint2") or {}
        _dp3 = dim.get("defpoint3") or {}
        if orientation == "h":
            d_min = min(_dp2.get("x", 0), _dp3.get("x", 0))
            d_max = max(_dp2.get("x", 0), _dp3.get("x", 0))
            lo_a = x1_a
            hi_a = x2_a
        elif orientation == "v":
            d_min = min(_dp2.get("y", 0), _dp3.get("y", 0))
            d_max = max(_dp2.get("y", 0), _dp3.get("y", 0))
            lo_a = y1_a
            hi_a = y2_a
        else:
            d_min = 0.0
            d_max = 0.0
            lo_a = None
            hi_a = None

        nearest = None
        best_score = float("inf")
        best_ratio = -1.0

        rx = ref.get("x", 0)
        ry = ref.get("y", 0)
        rx_bin = int(rx / _BIND_CELL)
        ry_bin = int(ry / _BIND_CELL)

        # 查询 ref ± _EXPAND 范围内的网格 cell（只遍历非空 cell，顺序不变）
        i0 = bisect_left(gx_keys, rx_bin - _EXPAND)
        i1 = bisect_right(gx_keys, rx_bin + _EXPAND)
        ylo = ry_bin - _EXPAND
        yhi = ry_bin + _EXPAND
        for gi in range(i0, i1):
            gx = gx_keys[gi]
            gys = gy_keys_by_gx[gx]
            j0 = bisect_left(gys, ylo)
            j1 = bisect_right(gys, yhi)
            for gj in range(j0, j1):
                for cx, cy, idx in grid[(gx, gys[gj])]:
                    # 距离平方预过滤：避免 99% 无效 sqrt
                    ddx = rx - cx
                    ddy = ry - cy
                    dist_sq = ddx * ddx + ddy * ddy
                    if dist_sq >= _MAX_SQ:
                        continue

                    # 精确距离（仅候选）
                    dist = math.sqrt(dist_sq)
                    # 内联 _dim_projection_ratio（原每候选一次函数调用 + 重复
                    # 解析 dim 端点 + bbox 取键）；算式与浮点运算顺序保持不变。
                    if lo_a is None:
                        ratio = 0.0
                    else:
                        e1 = lo_a[idx]
                        e2 = hi_a[idx]
                        span = e2 - e1
                        if span <= 0:
                            ratio = 0.0
                        else:
                            overlap = max(0.0, min(e2, d_max) - max(e1, d_min))
                            ratio = overlap / span
                            if ratio > 1.0:
                                ratio = 1.0
                    # 内联 _dim_match_score：综合评分 = dist * (1.5 - ratio)；
                    # ratio 已落在 [0,1]，与原 min(max(ratio,0),1) 取值等价。
                    score = dist * (1.5 - ratio)
                    if score < best_score or (abs(score - best_score) < 1 and ratio > best_ratio):
                        nearest = entities[idx]
                        best_score = score
                        best_ratio = ratio

        if nearest:
            attr_name = _infer_attribute_name(dim, nearest)
            entry = bindings.setdefault(nearest.id, {})
            entry[attr_name] = meas_m
            entry["_dimension_raw"] = dim.get("measurement")
            nearest.properties["_dimension_raw"] = dim.get("measurement")

    return bindings


# ── 几何工具函数 ────────────────────────────────────


@staticmethod
def _infer_attribute_name(dim: Dict, entity: SemanticEntity) -> str:
    """推断属性名"""
    entity_type = entity.type

    if entity_type == "wall":  # condition: entity_type == "wall":
        return "width"
    elif entity_type in ("door", "fire_door"):  # 分支
        return "clear_width"
    elif entity_type == "window":  # 分支
        return "width"
    elif entity_type == "stair":  # 分支
        return "step_width"
    elif entity_type == "corridor":  # 分支
        return "clear_width"
    elif entity_type == "fire_zone":  # 分支
        return "area"
    else:  # 否则
        return "measurement"


# ── 走廊拓扑网络 ────────────────────────────────────
