"""
BAA 语义识别引擎 — 疏散分析
走道拓扑 / 疏散路径分析 / 疏散连通性验证
"""

from collections import deque
from typing import List, Dict, Any, Optional, Tuple
from .models import SemanticEntity, SpatialRelation


def _build_corridor_topology_impl(
    self,
    entities: List[
        SemanticEntity
    ],  # method: def build_corridor_topology(self, entities: List[SemanticEnt
    relations: List[SpatialRelation],
) -> Dict[str, Any]:  # 操作
    """构建走廊拓扑网络

    将走廊实体按空间相邻关系连接为图，识别：
    - 连通分量（哪些走廊连通）
    - 死胡同（只有一条连接的走廊段）
    - 疏散路径（走廊到出口的可达性）
    """
    corridor_map = {e.id: e for e in entities if e.type == "corridor"}  # compare: equality

    if len(corridor_map) < 2:  # check: numeric comparison
        return {  # return: dict result
            "corridors": [e.to_dict() for e in corridor_map.values()],  # 字段
            "components": 1,  # 字段
            "dead_ends": [],  # 字段
            "network": {"nodes": list(corridor_map.keys()), "edges": []},  # 字段
        }  # code

    # 构建走廊-走廊相邻图
    adjacency: Dict[str, List[Tuple[str, float]]] = {eid: [] for eid in corridor_map}  # 操作

    for rel in relations:  # 循环
        src = rel.source_id  # assign
        tgt = rel.target_id  # assign
        if (
            src in corridor_map and tgt in corridor_map and rel.type == "adjacent"
        ):  # check: membership test
            adjacency[src].append((tgt, rel.distance))  # 操作
            adjacency[tgt].append((src, rel.distance))  # 操作

    # 门连接：门关联的走廊也算连通
    for rel in relations:  # 循环
        if rel.type != "connects_to":  # condition: rel.type != "connects_to":
            continue  # 继续循环
        door_id = rel.target_id  # assign
        corridor_id = rel.source_id  # assign
        if corridor_id not in corridor_map:  # check: membership test
            continue  # 继续循环
        # 找门连接的另一侧（room或其他走廊）
        for rel2 in relations:  # 循环
            if rel2.source_id == door_id and rel2.target_id != corridor_id:  # check: OR condition
                other_id = rel2.target_id  # assign
                if other_id in corridor_map:  # check: membership test
                    adjacency[corridor_id].append((other_id, rel2.distance))  # 操作
                    adjacency[other_id].append((corridor_id, rel2.distance))  # 操作

    # 找连通分量（BFS）
    visited = set()  # init: empty set
    components = []  # init: empty list
    for eid in corridor_map:  # 循环
        if eid in visited:  # check: membership test
            continue  # 继续循环
        comp = []  # init: empty list
        queue = deque([eid])  # assign: O(1) pop from left
        while queue:  # 循环
            current = queue.popleft()  # assign
            if current in visited:  # check: membership test
                continue  # 继续循环
            visited.add(current)  # call
            comp.append(current)  # append: add to list
            for neighbor, _ in adjacency.get(current, []):  # 循环
                if neighbor not in visited:  # check: membership test
                    queue.append(neighbor)  # append: add to list
        if comp:  # condition: comp:
            components.append(comp)  # append: add to list

    # 找死胡同（度=1的走廊节点）
    dead_ends = []  # init: empty list
    for eid, neighbors in adjacency.items():  # 循环
        if len(neighbors) == 1:  # check: length
            ent = corridor_map[eid]  # assign
            dead_ends.append(
                {  # code
                    "id": eid,  # 字段
                    "width": ent.properties.get("width", 0),  # 字段
                    "length": ent.properties.get("length", 0),  # 字段
                    "bbox": ent.bbox,  # 字段
                }
            )  # code

    # 走廊宽度统计
    widths = [
        e.properties.get("width", 0) for e in corridor_map.values()
    ]  # assign: membership check
    valid_widths = [w for w in widths if w > 0]  # assign: membership check

    return {  # return: dict result
        "corridors": [e.to_dict() for e in corridor_map.values()],  # 字段
        "components": len(components),  # 字段
        "component_sizes": [len(c) for c in components],  # 字段
        "dead_ends": dead_ends,  # 字段
        "dead_end_count": len(dead_ends),  # 字段
        "width_avg": (
            round(sum(valid_widths) / len(valid_widths), 2) if valid_widths else 0
        ),  # 字段
        "width_min": round(min(valid_widths), 2) if valid_widths else 0,  # 字段
        "width_max": round(max(valid_widths), 2) if valid_widths else 0,  # 字段
        "network": {  # 字段
            "nodes": list(corridor_map.keys()),  # 字段
            "edges": [  # 字段
                {"source": s, "target": t, "distance": d}  # 字面量
                for s, neighbors in adjacency.items()  # 循环
                for t, d in neighbors  # 循环
                if s < t  # 去重
            ],  # code
        },  # code
    }  # code


def _analyze_evacuation_routes_impl(
    self,
    entities: List[
        SemanticEntity
    ],  # method: def analyze_evacuation_routes(self, entities: List[SemanticE
    relations: List[SpatialRelation],
) -> List[Dict]:  # 操作
    """疏散路径分析

    检查从每个 room 到最近 exit 的路径：
    1. 是否所有房间都有通往出口的路径
    2. 路径长度是否超过疏散距离阈值
    3. 路径上的走廊宽度是否满足要求
    """
    # 构建全量实体邻接表
    adj: Dict[str, List[Tuple[str, str, float]]] = {}  # 操作
    for e in entities:  # 循环
        adj[e.id] = []  # init: empty list

    for rel in relations:  # 循环
        if rel.type not in ("adjacent", "connects_to", "contains"):  # check: membership test
            continue  # 继续循环
        adj.setdefault(rel.source_id, []).append(
            (rel.target_id, rel.type, rel.distance)
        )  # append: add to list
        adj.setdefault(rel.target_id, []).append(
            (rel.source_id, rel.type, rel.distance)
        )  # append: add to list

        # 出口识别：优先用明确的 exit/exit_door/stair
    strict_exits = [
        e for e in entities if e.type in ("exit", "exit_door", "stair", "staircase")
    ]  # assign: membership check
    fallback_exits = [
        e for e in entities if e.type in ("door", "fire_door")
    ]  # assign: membership check
    # 有明确出口就用明确出口，否则用 door/fire_door 兜底
    exits = strict_exits if strict_exits else fallback_exits  # assign

    rooms = [e for e in entities if e.type == "room"]  # compare: equality

    if not exits:  # check: negated condition
        return []  # return: list of items

    # 如果没有 room 但有 corridor/lobby/pump_room 等空间实体，用它们作为起点
    if not rooms:
        # P76 修复：room 实体在真实图纸中识别不足（被识别为 lobby/pump_room/space 等）
        # 扩展为所有封闭空间类型
        fallback_rooms = [e for e in entities
                          if e.type in ("corridor", "lobby", "pump_room",
                                        "space", "anteroom", "elevator_lobby", "staircase_lobby")]
        if fallback_rooms:
            rooms = fallback_rooms
        else:
            return []

    # exit 查找集合（提前构建，避免循环内重复构造）
    exit_id_set = {e.id for e in exits}  # assign: membership check

    routes = []  # init: empty list
    for room in rooms:  # 循环
        # BFS 找最近出口：所有 room 都走 BFS，不再跳过
        visited = {room.id}  # assign
        queue = deque([(room.id, [room.id], 0.0)])  # assign: O(1) BFS queue
        found_route = None  # init: set to None

        while queue:  # 循环
            current, path, distance = queue.popleft()  # 解包: O(1)
            if current in exit_id_set:  # check: membership test
                found_route = (path, distance)  # assign
                break  # 跳出循环
            for neighbor, rel_type, dist in adj.get(current, []):  # 循环
                if neighbor not in visited:  # check: membership test
                    visited.add(neighbor)  # call
                    queue.append(
                        (neighbor, path + [neighbor], distance + dist)
                    )  # append: add to list

        route_info = {  # assign
            "room_id": room.id,  # 字段
            "room_type": room.type,  # 字段
            "room_bbox": room.bbox,  # 字段
            "has_route": found_route is not None,  # 字段
            "path_length": round(found_route[1], 2) if found_route else None,  # 字段
            "path": found_route[0] if found_route else [],  # 字段
            "is_dead_end_room": room.properties.get("is_dead_end", False),  # 字段
            # 死胡同走廊（袋形走道）：疏散距离 ≤ 20m（GB50016-5.5.17注1）
            # 其他走廊/房间：≤ 30m
            "evac_distance_limit": (
                20.0 if room.properties.get("is_dead_end", False) else 30.0
            ),  # 字段
            "exceeds_max_distance": found_route is not None
            and found_route[1]
            > (20.0 if room.properties.get("is_dead_end", False) else 30.0),  # 字段
        }  # code
        routes.append(route_info)  # append: add to list

    return routes  # return


def _verify_evacuation_connectivity_impl(
    self,  # method: def verify_evacuation_connectivity(self,
    entities: List[SemanticEntity],  # code
    relations: List[SpatialRelation],  # code
    evacuation_routes: List[Dict],
) -> List[Dict]:  # code
    """疏散路径连通性验证（P33）

    在 analyze_evacuation_routes 的基础上，验证路径实际可通行性：
    1. 路径上走廊宽度是否满足最小值（≥ 1.2m 疏散走道）
    2. 路径上是否存在瓶颈（宽度骤变）
    3. 路径是否被堵塞（door 宽度过小 < 0.8m）
    4. 路径中的 room 是否有通向走廊的门连接

    参数:
        entities: 语义实体列表
        relations: 空间关系列表
        evacuation_routes: analyze_evacuation_routes 的返回结果

    返回:
        每个房间的连通性验证结果列表
    """
    # 构建实体查找表
    entity_map = {e.id: e for e in entities}  # assign: membership check

    # 构建邻接表（同 analyze_evacuation_routes 逻辑）
    adj: Dict[str, List[Tuple[str, str, float]]] = {}  # init: empty dict
    for e in entities:  # loop: for e in entities:
        adj[e.id] = []  # init: empty list
    for rel in relations:  # loop: for rel in relations:
        if rel.type not in ("adjacent", "connects_to", "contains"):  # check: membership test
            continue  # code
        adj.setdefault(rel.source_id, []).append(
            (rel.target_id, rel.type, rel.distance)
        )  # append: add to list
        adj.setdefault(rel.target_id, []).append(
            (rel.source_id, rel.type, rel.distance)
        )  # append: add to list

    # 出口识别
    strict_exits = [
        e for e in entities if e.type in ("exit", "exit_door", "stair", "staircase")
    ]  # assign: membership check
    fallback_exits = [
        e for e in entities if e.type in ("door", "fire_door")
    ]  # assign: membership check
    exits = strict_exits if strict_exits else fallback_exits  # assign
    exit_ids = {e.id for e in exits}  # assign: membership check

    results = []  # init: empty list

    for route in evacuation_routes:  # loop: for route in evacuation_routes:
        room_id = route["room_id"]  # assign
        path = route.get("path", [])  # assign
        has_route = route.get("has_route", False)  # assign

        if not has_route or not path:  # check: negated condition
            results.append(
                {  # code
                    "room_id": room_id,  # code
                    "room_type": route.get("room_type", ""),  # call
                    "connected": False,  # code
                    "bottleneck": False,  # code
                    "bottleneck_details": None,  # code
                    "path": path,  # code
                }
            )  # code
            continue  # code

        # 分析路径上的瓶颈
        bottleneck = False  # assign
        bottleneck_details = None  # init: set to None
        min_width = float("inf")  # assign

        for node_id in path:  # loop: for node_id in path:
            ent = entity_map.get(node_id)  # assign
            if ent is None:  # check: value is None
                continue  # code

            # 走廊宽度检查
            if ent.type == "corridor":  # check: OR condition
                width = ent.properties.get("width", 0)  # assign
                if width > 0:  # check: numeric comparison
                    min_width = min(min_width, width)  # assign
                    # GB50016-5.5.18：疏散走道净宽不应小于 1.2m
                    if width < 1.2:  # check: numeric comparison
                        bottleneck = True  # assign
                        bottleneck_details = {  # assign
                            "type": "corridor_too_narrow",  # code
                            "entity_id": ent.id,  # code
                            "width": width,  # code
                            "threshold": 1.2,  # code
                        }  # code

            # 门宽度检查
            if ent.type in ("door", "fire_door"):  # check: membership test
                width = ent.properties.get("width", 0)  # assign
                if width > 0 and width < 0.8:  # check: numeric comparison
                    bottleneck = True  # assign
                    bottleneck_details = {  # assign
                        "type": "door_too_narrow",  # code
                        "entity_id": ent.id,  # code
                        "width": width,  # code
                        "threshold": 0.8,  # code
                    }  # code

            # 检查 room 是否有门连接走廊（不是直接通到出口的 room）
            if ent.type == "room" and node_id not in exit_ids:  # check: membership test
                has_door_to_corridor = False  # assign
                for neighbor, rel_type, _ in adj.get(
                    node_id, []
                ):  # loop: for neighbor, rel_type, _ in adj.get(node_id, []):
                    neighbor_ent = entity_map.get(neighbor)  # assign
                    if neighbor_ent and neighbor_ent.type == "corridor":  # check: OR condition
                        has_door_to_corridor = True  # assign
                        break  # code
                if not has_door_to_corridor and len(path) > 1:  # check: numeric comparison
                    # 房间没有直接的门连接走廊（除非房间本身就是出口）
                    pass  # 不标记为 bottleneck，仅记录

        results.append(
            {  # code
                "room_id": room_id,  # code
                "room_type": route.get("room_type", ""),  # call
                "connected": has_route,  # code
                "bottleneck": bottleneck,  # code
                "bottleneck_details": bottleneck_details,  # code
                "path": path,  # code
                "min_corridor_width": (
                    min_width if min_width != float("inf") else None
                ),  # compare: inequality
            }
        )  # code

    # 对有 BFS 路径但无出口在路径中的 room 标记为未连通
    for room in entities:  # loop: for room in entities:
        if room.type != "room":  # condition: room.type != "room":
            continue  # code
        if room.id not in {r["room_id"] for r in results}:  # check: membership test
            # 检查是否有间接路径
            visited = {room.id}  # assign
            queue = deque([room.id])  # assign: O(1) BFS queue
            found_exit = False  # assign
            while queue:  # loop: while queue:
                current = queue.popleft()  # assign
                if current in exit_ids:  # check: membership test
                    found_exit = True  # assign
                    break  # code
                for neighbor, _, _ in adj.get(
                    current, []
                ):  # loop: for neighbor, _, _ in adj.get(current, []):
                    if neighbor not in visited:  # check: membership test
                        visited.add(neighbor)  # call
                        queue.append(neighbor)  # append: add to list

            results.append(
                {  # code
                    "room_id": room.id,  # code
                    "room_type": room.type,  # code
                    "connected": found_exit,  # code
                    "bottleneck": False,  # code
                    "bottleneck_details": None,  # code
                    "path": list(visited),  # call
                    "min_corridor_width": None,  # code
                }
            )  # code

    return results  # return
