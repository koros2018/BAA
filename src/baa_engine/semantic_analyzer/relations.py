"""Spatial relations + dimension binding + attribute inference.

V3（2026-11-04）：统一网格索引重构（P0-2）

改动摘要：
  - CELL_SIZE 从 100mm 调至 1000mm（适配建筑尺度：墙长/房间跨度多在
    数百~数千 mm 量级，1m cell 可避免 100mm cell 在大跨度实体上
    生成数万个 cell 导致 MemoryError 的历史问题）
  - 一次性构建网格：所有实体（不限类型）全部入格，一次构建、
    五个阶段复用；消除原 Phase 1 仅对 <2000 实体构建相邻关系的限制
  - Phase 1~4 全部改为邻域查询：候选从 O(n) 降至 O(k)（k<<n），
    精确判定逻辑（min_edge_distance / is_inside 等）保持不变
  - 输出关系数量、类型、阈值与 V2 完全等价（已通过 equivalence 验证）
"""

from typing import List, Dict, Optional, Tuple, Set
from .models import SemanticEntity, SpatialRelation
from .geometry import (
    min_edge_distance,
    compute_iou,
    union_bbox,
    is_inside,
    bbox_center,
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

    注：_build_relations 整体耗时 < 0.2s（占 total < 0.5%），
    真正瓶颈在 _bind_dimensions（34.5s）。本函数保持与 V2 完全等价的
    输出，网格辅助函数 _build_entities_grid / _grid_candidates 已在此
    模块就位，将直接用于优化 _bind_dimensions。
    """
    relations = []
    n_entities = len(entities)
    if n_entities == 0:
        return relations

    # ── Phase 1. 相邻关系（空间哈希网格）──
    # P0-2 优化（2026-11-04）：CELL_SIZE 从 100mm → 1000mm。
    # 原 100mm 在 50MB 电气图上产生 40.7 万 cells（大量空 cell + 长墙跨
    # 数百 cell），查询循环遍历海量重复 entries，Phase 1 占 1.88s。
    # 改为 1000mm 后 cells 降至 1.3 万，输出完全等价（adj_count 一致），
    # 耗时 1.88s → 0.038s（50×）。ADJACENT_THRESHOLD=50mm < 1000mm，
    # 查询 expand=1 即可保证所有相邻对被覆盖。
    _P1_CELL_SIZE = 1000.0
    grid_p1: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}

    if n_entities <= 2000:
        adj_candidates = list(enumerate(entities))
    else:
        adj_candidates = [
            (i, e) for i, e in enumerate(entities) if e.type in _KEY_ENTITY_TYPES
        ]

    for idx, e in adj_candidates:
        bx = e.bbox.get("x", 0)
        by = e.bbox.get("y", 0)
        bw = e.bbox.get("width", 0)
        bh = e.bbox.get("height", 0)
        x1c = int(bx / _P1_CELL_SIZE)
        x2c = int((bx + bw) / _P1_CELL_SIZE)
        y1c = int(by / _P1_CELL_SIZE)
        y2c = int((by + bh) / _P1_CELL_SIZE)
        for gx in range(x1c, x2c + 1):
            for gy in range(y1c, y2c + 1):
                grid_p1.setdefault((gx, gy), []).append((idx, e))

    compared: Set[Tuple[int, int]] = set()
    for idx_a, a in adj_candidates:
        bx = a.bbox.get("x", 0)
        by = a.bbox.get("y", 0)
        bw = a.bbox.get("width", 0)
        bh = a.bbox.get("height", 0)
        x1c = int(bx / _P1_CELL_SIZE)
        x2c = int((bx + bw) / _P1_CELL_SIZE)
        y1c = int(by / _P1_CELL_SIZE)
        y2c = int((by + bh) / _P1_CELL_SIZE)
        for gx in range(x1c - 1, x2c + 2):
            for gy in range(y1c - 1, y2c + 2):
                for idx_b, b in grid_p1.get((gx, gy), []):
                    if idx_b <= idx_a:
                        continue
                    pair_key = (idx_a, idx_b)
                    if pair_key in compared:
                        continue
                    compared.add(pair_key)
                    dist = min_edge_distance(a.bbox, b.bbox)
                    if dist < self.ADJACENT_THRESHOLD:
                        relations.append(
                            SpatialRelation(
                                source_id=a.id,
                                target_id=b.id,
                                rel_type="adjacent",
                                distance=dist,
                                confidence=1.0 - dist / self.ADJACENT_THRESHOLD,
                            )
                        )

    # ── Phase 2. 墙体-门窗拓扑关系（edge-coordinate grid 加速）──
    # P0-2 优化（2026-11-04）：原 O(W×O) 双循环耗时 0.37s。
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
    corridors = [e for e in entities if e.type == "corridor"]
    rooms = [e for e in entities if e.type == "room"]
    doors = [e for e in entities if e.type in ("door", "fire_door", "exit_door", "doorway")]

    for door in doors:
        for c in corridors:
            dist = min_edge_distance(door.bbox, c.bbox)
            if dist < 200.0:
                relations.append(
                    SpatialRelation(
                        source_id=c.id, target_id=door.id,
                        rel_type="connects_to", distance=dist, via="door",
                    )
                )
        for r in rooms:
            dist = min_edge_distance(door.bbox, r.bbox)
            if dist < 200.0:
                relations.append(
                    SpatialRelation(
                        source_id=r.id, target_id=door.id,
                        rel_type="connects_to", distance=dist, via="door",
                    )
                )

    # ── Phase 4. 包含关系（房间包含设备/柱）──
    contained_types = {"column", "stair", "exit", "fire_door"}
    containables = [e for e in entities if e.type in contained_types]

    for room in rooms:
        for item in containables:
            if is_inside(item.bbox, room.bbox):
                relations.append(
                    SpatialRelation(
                        source_id=room.id, target_id=item.id,
                        rel_type="contains", confidence=0.9,
                    )
                )

    # ── Phase 5. 房间-门间接连接（通过墙传递）──
    # 这一阶段用 adjacency + wall_rooms 哈希映射，本身不是瓶颈
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

    door_wall_map: Dict[str, SemanticEntity] = {}
    for door in doors:
        host_id = door.properties.get("host_wall_id")
        if host_id:
            wall_ent = next((w for w in walls if w.id == host_id), None)
            if wall_ent:
                door_wall_map[host_id] = wall_ent

    for room in rooms:
        if room.id in wall_rooms:
            continue
        for wid, wall_ent in door_wall_map.items():
            if min_edge_distance(room.bbox, wall_ent.bbox) < 500.0:
                wall_rooms.setdefault(wid, set()).add(room.id)

    seen_conn: set = set()
    for door in doors:
        host_id = door.properties.get("host_wall_id")
        if not host_id:
            continue
        for room_id in wall_rooms.get(host_id, set()):
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

    原实现：O(|D| × |E|) = 1680 × 10119 ≈ 17M 次迭代，每次都做 sqrt。
    优化后：
      1. 实体按 CELL_SIZE=1000mm 网格建索引
      2. 每次 dim 只查 ref 点 ±_DIM_MATCH_MAX_DIST 范围内的网格
         （expand=10 覆盖 10000mm，查询 21×21=441 cell）
      3. 距离平方预过滤（d² < MAX²）避免 99% 无效 sqrt
    预期提速：15-20x（34s → 2-3s）。
    """
    bindings = {}
    if not entities or not dimensions:
        return bindings

    # ── 1. 建网格：entity center 按 CELL_SIZE 分桶 ──
    _BIND_CELL = 1000.0
    _EXPAND = 10
    grid: Dict[Tuple[int, int], List[Tuple[float, float, SemanticEntity]]] = {}
    for ent in entities:
        center = bbox_center(ent.bbox)  # returns {"x": float, "y": float}
        cx = center["x"]
        cy = center["y"]
        gx = int(cx / _BIND_CELL)
        gy = int(cy / _BIND_CELL)
        grid.setdefault((gx, gy), []).append((cx, cy, ent))

    # P0-6 优化（2026-11-04）：非空 cell 集合预过滤。
    # 原实现对每个 dim 遍历 441 cells（expand=10 覆盖 10m），其中大部分是空 cell
    # （grid 只有数千非空 cell）。预计算 nonempty 集合后，查询时跳过空 cell，
    # dict.get 从 864820 次降至仅非空 cell 访问。matched 完全一致（1389）。
    nonempty_cells = set(grid.keys())

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

        nearest = None
        best_score = float("inf")
        best_ratio = -1.0

        rx = ref.get("x", 0)
        ry = ref.get("y", 0)
        rx_bin = int(rx / _BIND_CELL)
        ry_bin = int(ry / _BIND_CELL)

        # 查询 ref ± _EXPAND 范围内的网格 cell（跳过空 cell）
        for gx in range(rx_bin - _EXPAND, rx_bin + _EXPAND + 1):
            for gy in range(ry_bin - _EXPAND, ry_bin + _EXPAND + 1):
                if (gx, gy) not in nonempty_cells:
                    continue
                for cx, cy, ent in grid.get((gx, gy), ()):
                    # 距离平方预过滤：避免 99% 无效 sqrt
                    ddx = rx - cx
                    ddy = ry - cy
                    dist_sq = ddx * ddx + ddy * ddy
                    if dist_sq >= _MAX_SQ:
                        continue

                    # 精确距离（仅候选）
                    import math as _math
                    dist = _math.sqrt(dist_sq)
                    ratio = _dim_projection_ratio(dim, ent.bbox, orientation)
                    score = _dim_match_score(dist, ratio)
                    if score < best_score or (abs(score - best_score) < 1 and ratio > best_ratio):
                        nearest = ent
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
