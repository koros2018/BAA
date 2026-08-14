"""Spatial relations + dimension binding + attribute inference.
"""
from typing import List, Dict, Tuple, Set
from .models import SemanticEntity, SpatialRelation
from .geometry import (
    min_edge_distance,
    compute_iou,
    union_bbox,
    is_inside,
    bbox_center,
    point_distance,
)

def _build_relations(
    self, entities: List[SemanticEntity]
) -> List[
    SpatialRelation
]:
    """构建空间关系（V2深度升级版）

    包括：
    - 相邻关系（相邻距离阈值，>500实体用空间哈希加速）
    - 墙体-门窗拓扑关系（精确匹配门在墙上的位置）
    - 走廊连通关系（门连接走廊与房间）
    - 包含关系（房间包含设备）

    性能优化：实体数 > 2000 时跳过全量相邻关系构建，
    仅保留墙体-门窗拓扑和包含关系。相邻关系主要用于
    疏散路径分析，大图纸 room 数量少，影响可控。
    """
    relations = []
    n_entities = len(entities)

    # ── 1. 相邻关系（空间哈希加速，>2000 实体只构建关键实体对）──
    # 关键实体类型：room/corridor/door/exit/stair/fire_door/exit_door + wall
    # P76 修复：真实图纸 room 识别不足，fallback 到 lobby/pump_room/space 等空间类型，
    # 必须也参与相邻关系构建，否则 BFS 拓扑为空（has_route=False）
    # wall 必须包含：room↔wall adjacent 是 step 5 (room-wall-door 传递) 的基础
    KEY_ENTITY_TYPES = {
        "room",
        "corridor",
        "door",
        "exit",
        "stair",
        "fire_door",
        "exit_door",
        "lobby",
        "pump_room",
        "space",
        "anteroom",
        "elevator_lobby",
        "staircase_lobby",
        "entrance_hall",
        # P82: 大图纸相邻关系需包含 wall——room↔wall↔door↔stair 链是
        # 疏散 BFS 的核心路径，缺 wall 导致所有 room has_route=False
        "wall",
        "facade",  # 外墙参与 room↔facade↔exit 路径
        "doorway",  # P107: 扫线法产出的 doorway 参与相邻关系构建
    }

    CELL_SIZE = 100.0  # mm
    grid: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}

    # 选择需要构建相邻关系的实体
    if n_entities <= 2000:
        adj_candidates = list(enumerate(entities))
    else:
        # 大图纸：只对关键实体构建相邻关系
        adj_candidates = [(i, e) for i, e in enumerate(entities) if e.type in KEY_ENTITY_TYPES]

    for idx, e in adj_candidates:
        bx = e.bbox.get("x", 0)
        by = e.bbox.get("y", 0)
        bw = e.bbox.get("width", 0)
        bh = e.bbox.get("height", 0)
        x1_cell = int(bx / CELL_SIZE)
        x2_cell = int((bx + bw) / CELL_SIZE)
        y1_cell = int(by / CELL_SIZE)
        y2_cell = int((by + bh) / CELL_SIZE)
        for gx in range(x1_cell, x2_cell + 1):
            for gy in range(y1_cell, y2_cell + 1):
                grid.setdefault((gx, gy), []).append((idx, e))

    compared = set()
    for idx_a, a in adj_candidates:
        bx = a.bbox.get("x", 0)
        by = a.bbox.get("y", 0)
        bw = a.bbox.get("width", 0)
        bh = a.bbox.get("height", 0)
        x1_cell = int(bx / CELL_SIZE)
        x2_cell = int((bx + bw) / CELL_SIZE)
        y1_cell = int(by / CELL_SIZE)
        y2_cell = int((by + bh) / CELL_SIZE)
        for gx in range(x1_cell - 1, x2_cell + 2):
            for gy in range(y1_cell - 1, y2_cell + 2):
                for idx_b, b in grid.get((gx, gy), []):
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

    # ── 2. 墙体-门窗拓扑关系（V2升级）──
    # 用几何方法精确匹配门/窗在墙上的位置：
    #   门 bbox 必须与墙 bbox 的某条边重叠（门在墙上）
    #   取最近/重叠最大的墙作为门的宿主墙
    walls = [e for e in entities if e.type == "wall"]  # compare: equality
    # P107: doorway 与 door 同为墙体开口，参与 host_wall 匹配
    openings = [
        e
        for e in entities
        if e.type in ("door", "window", "fire_door", "exit_door", "doorway")
    ]

    for opening in openings:  # 循环
        best_wall = None
        best_overlap = 0.0
        best_distance = float("inf")

        ob = opening.bbox
        ox1, oy1 = ob.get("x", 0), ob.get("y", 0)  # 操作
        ox2 = ox1 + ob.get("width", 0)
        oy2 = oy1 + ob.get("height", 0)
        o_cx = (ox1 + ox2) / 2
        o_cy = (oy1 + oy2) / 2

        for wall in walls:  # 循环
            wb = wall.bbox
            wx1, wy1 = wb.get("x", 0), wb.get("y", 0)  # 操作
            wx2 = wx1 + wb.get("width", 0)
            wy2 = wy1 + wb.get("height", 0)

            # 计算门中心到墙边的距离
            # 到左/右垂直边的水平距离
            dx_left = abs(o_cx - wx1)
            dx_right = abs(o_cx - wx2)
            # 到上/下水平边的垂直距离
            dy_bottom = abs(o_cy - wy1)
            dy_top = abs(o_cy - wy2)

            min_dx = min(dx_left, dx_right)
            min_dy = min(dy_bottom, dy_top)
            dist_to_edge = min(min_dx, min_dy)

            # 检查重叠：门必须接触墙的边界（距离<50mm）
            if dist_to_edge > 50.0:  # check: numeric comparison
                continue  # 继续循环

            # 计算门在墙边上的投影重叠长度
            overlap = 0.0

            if min_dx <= min_dy:  # check: numeric comparison
                # 门接触垂直边（墙的左或右边）
                # 投影重叠在 y 方向
                overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))
                overlap = overlap_y / max(ob.get("height", 1), 1)
            else:  # 否则
                # 门接触水平边（墙的上或下边）
                overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))
                overlap = overlap_x / max(ob.get("width", 1), 1)

            if overlap > best_overlap or (
                overlap == best_overlap and dist_to_edge < best_distance
            ):  # check: numeric comparison
                best_overlap = overlap
                best_distance = dist_to_edge
                best_wall = wall

        if best_wall:  # condition: best_wall:
            relations.append(
                SpatialRelation(  # code
                    source_id=best_wall.id,
                    target_id=opening.id,
                    rel_type="contains",
                    confidence=min(0.95, best_overlap),
                )
            )  # code
            # 给门注入宿主墙信息
            opening.properties["host_wall_id"] = best_wall.id  # 操作
            opening.properties["host_wall_overlap"] = round(best_overlap, 2)  # 操作

    # ── 3. 走廊-门-房间拓扑（V2：基于边缘距离）──
    # 用 _min_edge_distance 判断门是否连接走廊/房间
    corridors = [e for e in entities if e.type == "corridor"]  # compare: equality
    rooms = [e for e in entities if e.type == "room"]  # compare: equality
    # P107: 扫线法产出的 doorway 与 door 等价，参与走廊-门-房间拓扑
    doors = [
        e
        for e in entities
        if e.type in ("door", "fire_door", "exit_door", "doorway")
    ]

    for door in doors:  # 循环
        for c in corridors:  # 循环
            dist = min_edge_distance(door.bbox, c.bbox)
            if dist < 200.0:  # 门边缘距走廊 < 200mm
                relations.append(
                    SpatialRelation(  # code
                        source_id=c.id,
                        target_id=door.id,
                        rel_type="connects_to",
                        distance=dist,
                        via="door",
                    )
                )  # code
        for r in rooms:  # 循环
            dist = min_edge_distance(door.bbox, r.bbox)
            if dist < 200.0:  # check: numeric comparison
                relations.append(
                    SpatialRelation(  # code
                        source_id=r.id,
                        target_id=door.id,
                        rel_type="connects_to",
                        distance=dist,
                        via="door",
                    )
                )  # code

    # ── 4. 包含关系（房间包含设备/柱）──
    contained_types = {"column", "stair", "exit", "fire_door"}
    containables = [
        e for e in entities if e.type in contained_types
    ]
    for room in rooms:  # 循环
        for item in containables:  # 循环
            if is_inside(item.bbox, room.bbox):  # condition: self._is_inside(item.bbox, room.bbox):
                relations.append(
                    SpatialRelation(  # code
                        source_id=room.id,
                        target_id=item.id,
                        rel_type="contains",
                        confidence=0.9,
                    )
                )  # code

    # ── 5. 房间-门间接连接（通过墙传递）──
    # 使用 door.properties["host_wall_id"] 直接定位门所在的墙
    # 然后遍历该墙相邻的 room，建立 room↔door 连接
    # wall 不在 KEY_ENTITY_TYPES 中，避免大图纸 wall×wall adjacency 超时
    # 先构建 wall_id -> set(room_id) 映射：只有 room↔wall 相邻关系中的墙才收录
    wall_rooms: Dict[str, set] = {}
    for rel in relations:  # 循环
        if rel.type == "adjacent":  # condition: rel.type == "adjacent":
            sid, tid = rel.source_id, rel.target_id
            if sid in {r.id for r in rooms} and tid in {w.id for w in walls}:  # room→wall
                wall_rooms.setdefault(tid, set()).add(sid)  # call
            elif tid in {r.id for r in rooms} and sid in {w.id for w in walls}:  # wall→room
                wall_rooms.setdefault(sid, set()).add(tid)  # call
    # 大图纸 room 数量少但 wall 极多，相邻关系不足时用 bbox 检测补全
    # 只检测 room 与门所在墙的 bbox 距离，不走全量 wall adjacency
    door_wall_map: Dict[str, SemanticEntity] = {}
    for door in doors:  # 循环
        host_id = door.properties.get("host_wall_id")  # function call
        if host_id:  # check: truthy
            wall_ent = next((w for w in walls if w.id == host_id), None)
            if wall_ent:  # check: truthy
                door_wall_map[host_id] = wall_ent  # call
    # 对每个 room，找所有与门所在墙 bbox 接近的墙
    for room in rooms:  # 循环
        if room.id in wall_rooms:  # 已有相邻墙
            continue  # 跳过已覆盖的 room
        for wid, wall_ent in door_wall_map.items():  # 循环
            if min_edge_distance(room.bbox, wall_ent.bbox) < 500.0:  # function call
                wall_rooms.setdefault(wid, set()).add(room.id)  # call
    # 建立 room↔door connects_to：遍历每个门，找相邻的 room
    seen_conn: set = set()
    for door in doors:  # 循环
        host_id = door.properties.get("host_wall_id")  # function call
        if not host_id:  # check: negated condition
            continue  # 无宿主墙，跳过
        for room_id in wall_rooms.get(host_id, set()):  # 循环
            pair = (room_id, door.id)
            if pair in seen_conn:  # check: membership test
                continue  # 避免重复
            seen_conn.add(pair)  # call
            relations.append(
                SpatialRelation(  # code
                    source_id=room_id,
                    target_id=door.id,
                    rel_type="connects_to",
                    distance=0.0,
                    via="door",
                )
            )  # code

    return relations




def _bind_dimensions(
    self,
    entities: List[
        SemanticEntity
    ],
    dimensions: List[Dict],
) -> Dict[str, Dict]:  # 操作
    """尺寸标注绑定到实体"""
    bindings = {}

    for dim in dimensions:  # 循环
        dim_pos = dim.get("position", {})
        if not dim_pos:  # check: negated condition
            continue  # 继续循环

        nearest = None
        nearest_dist = float("inf")

        for entity in entities:  # 循环
            center = bbox_center(entity.bbox)
            dist = point_distance(dim_pos, center)
            if dist < nearest_dist and dist < 500:  # check: numeric comparison
                nearest = entity
                nearest_dist = dist

        if nearest:  # condition: nearest:
            if nearest.id not in bindings:  # check: membership test
                bindings[nearest.id] = {}  # 操作
            attr_name = _infer_attribute_name(dim, nearest)
            bindings[nearest.id][attr_name] = dim.get("measurement", 0)  # 操作

    return bindings

# ── 几何工具函数 ────────────────────────────────────

@staticmethod



def _infer_attribute_name(
    dim: Dict, entity: SemanticEntity
) -> str:
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
