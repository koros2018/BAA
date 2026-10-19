"""拓扑显式化（Roadmap v4 T-B1 / 缺口 G10）：空间邻接图的 NetworkX 构建。

从语义分析结果（entities）构建房间拓扑：
- 空间节点：room/corridor/staircase 等可通行空间实体的质心
- 门窗节点：door/window/doorway/exit_door 等洞口实体（连接相邻空间）
- 空间-空间邻接边：bbox 缘距 ≤ _WALL_GAP_MM（两空间隔一堵墙）
- 门窗-空间边：门窗质心落于空间 bbox 外扩缓冲内

设计决策（诚实记录）：采用 ``nx.Graph`` 而非 DiGraph——空间邻接天然无向，
邻接表 summary 已双向列出满足判定层连通/邻接消费；方向性语义（如疏散流）
留待判定层按需叠加，不在此臆造方向。

护栏：只读消费 SemanticEntity，不改动扫线法房间检测路径（room.py）；
面积/质心直接取实体 bbox，不做二次几何推断。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Set

import networkx as nx

from .models import SemanticEntity

# ── 空间/洞口类型（与 classify.py 产出对齐）────────────────
# 注意：stair 是楼梯段构件（非房间级空间），不进房间节点集；
# staircase（楼梯间）才是空间。
_ROOM_TYPES = {"room", "corridor", "staircase", "fire_compartment"}
_OPENING_TYPES = {"door", "doorway", "exit_door", "fire_door", "window", "fire_window"}

# 两空间 bbox 缘距 ≤ 此值视为隔墙邻接（墙厚上限 600mm 两倍缓冲）
_WALL_GAP_MM = 600.0
# 门窗质心落入空间 bbox 外扩缓冲 → 连接
_DOOR_BUFFER_MM = 400.0


def _center(ent: SemanticEntity) -> tuple:
    bbox = ent.bbox or {}
    try:
        return (
            float(bbox.get("x", 0) or 0) + float(bbox.get("width", 0) or 0) / 2,
            float(bbox.get("y", 0) or 0) + float(bbox.get("height", 0) or 0) / 2,
        )
    except (TypeError, ValueError):
        return (0.0, 0.0)


def _bbox_gap_mm(a: SemanticEntity, b: SemanticEntity) -> float:
    """两实体 bbox 之间的缘距（不相交为正，相交为 0）。"""
    ba, bb = a.bbox or {}, b.bbox or {}
    try:
        ax0, ay0 = float(ba.get("x", 0) or 0), float(ba.get("y", 0) or 0)
        ax1, ay1 = ax0 + float(ba.get("width", 0) or 0), ay0 + float(ba.get("height", 0) or 0)
        bx0, by0 = float(bb.get("x", 0) or 0), float(bb.get("y", 0) or 0)
        bx1, by1 = bx0 + float(bb.get("width", 0) or 0), by0 + float(bb.get("height", 0) or 0)
    except (TypeError, ValueError):
        return float("inf")
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return math.hypot(dx, dy)


def _point_in_bbox(cx: float, cy: float, bbox: Dict, buffer: float) -> bool:
    try:
        x0 = float(bbox.get("x", 0) or 0) - buffer
        y0 = float(bbox.get("y", 0) or 0) - buffer
        x1 = x0 + float(bbox.get("width", 0) or 0) + 2 * buffer
        y1 = y0 + float(bbox.get("height", 0) or 0) + 2 * buffer
    except (TypeError, ValueError):
        return False
    return x0 <= cx <= x1 and y0 <= cy <= y1


def build_topology_graph(entities: List[SemanticEntity]) -> nx.Graph:
    """从语义实体构建空间拓扑图。

    节点属性：kind(room/opening)/entity_type/bbox/center。
    边属性：relation(adjacent/contains)。
    """
    g = nx.Graph()
    rooms: List[SemanticEntity] = []
    openings: List[SemanticEntity] = []
    for ent in entities:
        etype = getattr(ent, "type", "")
        if etype in _ROOM_TYPES:
            rooms.append(ent)
            cx, cy = _center(ent)
            g.add_node(
                ent.id,
                kind="room",
                entity_type=etype,
                bbox=ent.bbox,
                center=(round(cx, 1), round(cy, 1)),
            )
        elif etype in _OPENING_TYPES:
            openings.append(ent)
            cx, cy = _center(ent)
            g.add_node(
                ent.id,
                kind="opening",
                entity_type=etype,
                bbox=ent.bbox,
                center=(round(cx, 1), round(cy, 1)),
            )

    # 空间-空间：隔墙邻接（bbox 缘距 ≤ 墙厚缓冲）
    for i, a in enumerate(rooms):
        for b in rooms[i + 1 :]:
            if _bbox_gap_mm(a, b) <= _WALL_GAP_MM:
                g.add_edge(a.id, b.id, relation="adjacent")

    # 门窗-空间：质心落入外扩 bbox
    for op in openings:
        cx, cy = _center(op)
        for r in rooms:
            if _point_in_bbox(cx, cy, r.bbox or {}, _DOOR_BUFFER_MM):
                g.add_edge(op.id, r.id, relation="contains")

    return g


def topology_summary(g: nx.Graph) -> Dict[str, Any]:
    """导出可 JSON 化的结构（判定层消费：节点/边/邻接/连通分量）。"""
    rooms = [
        {
            "id": nid,
            "entity_type": data.get("entity_type"),
            "center": data.get("center"),
            "bbox": data.get("bbox"),
        }
        for nid, data in g.nodes(data=True)
        if data.get("kind") == "room"
    ]
    edges = [
        {"source": u, "target": v, "relation": data.get("relation")}
        for u, v, data in g.edges(data=True)
    ]
    adjacency = {str(nid): sorted(g.neighbors(nid)) for nid in g.nodes}
    components = [sorted(c) for c in nx.connected_components(g)]
    return {
        "node_count": g.number_of_nodes(),
        "edge_count": g.number_of_edges(),
        "room_count": len(rooms),
        "rooms": rooms,
        "edges": edges,
        "adjacency": adjacency,
        "connected_components": components,
        "is_connected": nx.is_connected(g) if g.number_of_nodes() else True,
    }
