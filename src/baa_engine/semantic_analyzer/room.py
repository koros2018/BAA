"""Room recognition — planar face traversal (left-hand rule).

Algorithm:
1. Collect wall-candidate LINEs (>=2000mm)
2. Split segments at T-junctions: if wall endpoint lies on another wall's
   segment, split that segment into two.
3. Build a planar graph: nodes = unique endpoints, edges = segments between them.
4. At each node, sort outgoing edges by angle (counterclockwise).
5. Traverse faces using the left-hand rule: from edge (u→v), at node v,
   take the next edge counterclockwise. This traces each face exactly once.
6. Filter faces by area, aspect ratio, and non-room layer.
"""

from typing import List, Dict, Tuple, Set, Any, Optional
from collections import defaultdict
import math

from .models import SemanticEntity
from ..drawing_parser import RawPrimitive


_NON_ROOM_LAYER_KW: Tuple[str, ...] = (
    "COLU", "视口", "洞口", "板边", "梁边", "轴", "BASE", "梁",
    "吊筋", "板层", "文字", "钢筋", "标注", "DIM", "立面看线",
    "立面", "看线", "园林", "井", "电-", "电气", "照明", "插座",
    "弱电", "消防", "火灾", "报警", "设备", "电缆", "系统",
    "Defpoints", "WIRE", "线槽", "DOTLN", "DOT",
)

_MATCH_THRESHOLD = 100.0  # mm — PDF→DXF 精度损失
_MIN_SEGMENT_LEN = 10.0  # mm


_Seg = Tuple[float, float, float, float, str, float]  # (x0,y0,x1,y1,layer,length)
# Node ID → (x, y)
_Node = Tuple[float, float]
# Edge = (node_id_a, node_id_b, layer)
_Edge = Tuple[int, int, str]


def _is_near_closed(
    self, prim: RawPrimitive, gap_threshold_mm: float = 500.0
) -> bool:
    """接近闭合检测（向后兼容）。"""
    pts = prim.properties.get("points")
    if not pts or len(pts) < 3:
        return False
    try:
        first = pts[0]
        last = pts[-1]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            start = (float(first[0]), float(first[1]))
            end = (float(last[0]), float(last[1]))
        else:
            return False
    except (TypeError, IndexError, ValueError):
        return False
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    return math.sqrt(dx * dx + dy * dy) < gap_threshold_mm


def _sweep_line_detect_rooms(
    self, primitives: List[RawPrimitive]
) -> List[SemanticEntity]:
    """扫线法房间检测 — 平面图面遍历法。"""
    wall_lines = _collect_wall_lines(primitives)
    if len(wall_lines) < 3:
        return []

    # ── 1. 转为内部线段表示 ──
    segs: List[_Seg] = []
    for prim in wall_lines:
        sp = prim.properties.get("start_point", {})
        ep = prim.properties.get("end_point", {})
        x0, y0 = sp.get("x", 0.0), sp.get("y", 0.0)
        x1, y1 = ep.get("x", 0.0), ep.get("y", 0.0)
        length = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
        segs.append((x0, y0, x1, y1, prim.layer or "", length))

    if len(segs) < 3:
        return []

    # ── 2. T-junction 分割 ──
    segs = _split_t_junctions(segs)
    if len(segs) < 3:
        return []

    # ── 3. 构建平面图：合并近似端点 → 节点，线段 → 边 ──
    graph = _build_planar_graph(segs)
    if not graph["nodes"] or not graph["edges"]:
        return []

    # ── 4. 每个节点处按角度排序边（逆时针） ──
    _sort_edges_at_nodes(graph)

    # ── 5. 平面图面遍历（左手定则）──
    faces = _find_faces(graph)

    # ── 6. 过滤 ──
    result: List[SemanticEntity] = []
    seen_bbox: Set[Tuple[int, int, int, int]] = set()
    for face in faces:
        pts = [(graph["nodes"][nid][0], graph["nodes"][nid][1]) for nid in face]
        if len(pts) < 3:
            continue
        area = abs(
            sum(pts[i][0] * pts[(i + 1) % len(pts)][1]
                - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))) / 2.0
        )
        if area < 1_000_000 or area > 500_000_000:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw <= 0 or bh <= 0:
            continue
        aspect = max(bw, bh) / min(bw, bh)
        if aspect > 8.0:
            continue
        # bbox 去重
        key = (round(min(xs), -1), round(min(ys), -1),
               round(max(xs) - min(xs), -1), round(max(ys) - min(ys), -1))
        if key in seen_bbox:
            continue
        seen_bbox.add(key)

        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        room_id = f"line_chain_room_{self._entity_counter}"
        self._entity_counter += 1
        result.append(SemanticEntity(
            entity_id=room_id, entity_type="room", layer="",
            properties={"area": area / 1_000_000}, bbox=bbox,
        ))
    # ── 7. 剔除外框面（外框面应包含所有其他面的中心点） ──
    if len(result) > 1:
        result.sort(key=lambda r: r.properties["area"], reverse=True)
        outer = result[0]
        # 构建外框多边形的顶点（用 bbox 近似为矩形）
        ob = outer.bbox
        outer_poly = [
            (ob["x"], ob["y"]),
            (ob["x"] + ob["width"], ob["y"]),
            (ob["x"] + ob["width"], ob["y"] + ob["height"]),
            (ob["x"], ob["y"] + ob["height"]),
        ]
        all_contained = True
        for r in result[1:]:
            ib = r.bbox
            cx = ib["x"] + ib["width"] / 2
            cy = ib["y"] + ib["height"] / 2
            if not _point_in_polygon((cx, cy), outer_poly):
                all_contained = False
                break
        if all_contained and len(result) > 1:
            result = result[1:]

    return result


# ═══════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════


def _collect_wall_lines(primitives: List[RawPrimitive]) -> List[RawPrimitive]:
    lines: List[RawPrimitive] = []
    for prim in primitives:
        if prim.dxf_type == "LINE":
            length = max((prim.bbox or {}).get("width", 0),
                         (prim.bbox or {}).get("height", 0))
            if length >= 2000:
                lines.append(prim)
    return lines


def _split_t_junctions(segs: List[_Seg]) -> List[_Seg]:
    """在 T-junction 和交叉点处分割线段。"""
    n = len(segs)
    split_pts: List[List[Tuple[float, float, float]]] = [[] for _ in range(n)]

    # Pass 1: 端点到线段的 T-junction
    for i in range(n):
        x0i, y0i, x1i, y1i = segs[i][0], segs[i][1], segs[i][2], segs[i][3]
        dx_i, dy_i = x1i - x0i, y1i - y0i
        len2_i = dx_i * dx_i + dy_i * dy_i
        if len2_i < 1e-6:
            continue
        for j in range(n):
            if i == j:
                continue
            x0j, y0j, x1j, y1j = segs[j][0], segs[j][1], segs[j][2], segs[j][3]
            for px, py in [(x0j, y0j), (x1j, y1j)]:
                t = ((px - x0i) * dx_i + (py - y0i) * dy_i) / len2_i
                if t < 0.001 or t > 0.999:
                    continue
                proj_x = x0i + t * dx_i
                proj_y = y0i + t * dy_i
                dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
                if dist > _MATCH_THRESHOLD:
                    continue
                if any(abs(t - s[0]) < 0.001 for s in split_pts[i]):
                    continue
                split_pts[i].append((t, proj_x, proj_y))

    # Pass 2: 线段-线段交叉检测（非共线的真交叉）
    for i in range(n):
        for j in range(i + 1, n):
            ix = _seg_intersection(segs[i], segs[j])
            if ix is None:
                continue
            tx_i = ix[0]
            ty_i = ix[1]
            # 确保不重复添加端点附近的交叉点
            if any(abs(tx_i - s[0]) < 0.001 for s in split_pts[i]) or any(abs(ty_i - s[0]) < 0.001 for s in split_pts[j]):
                continue
            # 避免在端点处添加交叉点（端点处已有端点处理）
            if tx_i < 0.001 or tx_i > 0.999 or ty_i < 0.001 or ty_i > 0.999:
                continue
            split_pts[i].append((tx_i, ix[2], ix[3]))
            split_pts[j].append((ty_i, ix[2], ix[3]))

    new_segs: List[_Seg] = []
    for i in range(n):
        x0, y0, x1, y1, layer, _ = segs[i]
        pts = split_pts[i]
        if not pts:
            new_segs.append(segs[i])
            continue
        all_pts = [(0.0, x0, y0)] + sorted(pts, key=lambda p: p[0]) + [(1.0, x1, y1)]
        for k in range(len(all_pts) - 1):
            _, px0, py0 = all_pts[k]
            _, px1, py1 = all_pts[k + 1]
            seg_len = math.sqrt((px1 - px0) ** 2 + (py1 - py0) ** 2)
            if seg_len < _MIN_SEGMENT_LEN:
                continue
            new_segs.append((px0, py0, px1, py1, layer, seg_len))
    return new_segs


def _seg_intersection(a: _Seg, b: _Seg) -> Optional[Tuple[float, float, float, float]]:
    """检测两条线段是否真交叉（不共线），返回交点在各自线段上的参数及坐标。

    返回 (t_a, t_b, x, y) 或 None。
    """
    x0a, y0a, x1a, y1a, _, _ = a
    x0b, y0b, x1b, y1b, _, _ = b
    dx_a, dy_a = x1a - x0a, y1a - y0a
    dx_b, dy_b = x1b - x0b, y1b - y0b
    denom = dx_a * dy_b - dy_a * dx_b
    if abs(denom) < 1e-10:
        return None  # 平行或共线，不处理
    t_a = ((x0b - x0a) * dy_b - (y0b - y0a) * dx_b) / denom
    t_b = ((x0b - x0a) * dy_a - (y0b - y0a) * dx_a) / denom
    if 0.001 < t_a < 0.999 and 0.001 < t_b < 0.999:
        x = x0a + t_a * dx_a
        y = y0a + t_a * dy_a
        return (t_a, t_b, x, y)
    return None


def _build_planar_graph(segs: List[_Seg]) -> Dict[str, Any]:
    """构建平面图：合并近似端点为节点，线段为边。

    返回:
        {
            "nodes": List[(x, y)],
            "edges": List[(node_a, node_b, layer)],
            "adj": Dict[int, List[int]],  # node_id -> [neighbor_node_ids]
            "edge_layers": Dict[(int, int), str],
        }
    """
    # 收集所有端点，合并近似的
    raw_pts: List[Tuple[float, float]] = []
    for x0, y0, x1, y1, _, _ in segs:
        raw_pts.append((x0, y0))
        raw_pts.append((x1, y1))

    # 端点聚类（近似合并）
    node_list: List[Tuple[float, float]] = []
    pt_to_node: Dict[Tuple[float, float], int] = {}

    def _find_or_create(x: float, y: float) -> int:
        key = (x, y)
        if key in pt_to_node:
            return pt_to_node[key]
        # 找最近节点
        best = -1
        best_d = _MATCH_THRESHOLD ** 2
        for i, (nx, ny) in enumerate(node_list):
            d = (nx - x) ** 2 + (ny - y) ** 2
            if d < best_d:
                best_d = d
                best = i
        if best >= 0:
            pt_to_node[key] = best
            return best
        nid = len(node_list)
        node_list.append((x, y))
        pt_to_node[key] = nid
        return nid

    for x, y in raw_pts:
        _find_or_create(x, y)

    # 构建边
    edges: Set[Tuple[int, int]] = set()
    edge_layers: Dict[Tuple[int, int], str] = {}
    for x0, y0, x1, y1, layer, _ in segs:
        na = _find_or_create(x0, y0)
        nb = _find_or_create(x1, y1)
        if na == nb:
            continue
        edge = tuple(sorted((na, nb)))
        edges.add(edge)
        edge_layers[edge] = layer

    # 邻接表
    adj: Dict[int, List[int]] = defaultdict(list)
    for (a, b) in edge_layers:
        adj[a].append(b)
        adj[b].append(a)

    return {
        "nodes": node_list,
        "edges": list(edge_layers.keys()),
        "adj": dict(adj),
        "edge_layers": edge_layers,
    }


def _sort_edges_at_nodes(graph: Dict[str, Any]) -> None:
    """在每个节点处按角度排序邻接边（逆时针）。

    排序后，从边 (u→v) 出发，在节点 v 处 "下一逆时针边" 是排序列表中的
    (v→u) 的前一条边（mod 循环）。这是左手定则遍历的关键。
    """
    nodes = graph["nodes"]
    adj = graph["adj"]

    for nid, neighbors in adj.items():
        if not neighbors:
            continue
        cx, cy = nodes[nid]
        # 按 (neighbor) 相对于 (cx,cy) 的极角排序
        def _angle_key(nid_neighbor: int) -> float:
            nx, ny = nodes[nid_neighbor]
            return math.atan2(ny - cy, nx - cx)

        # 排序
        sorted_neighbors = sorted(neighbors, key=_angle_key)
        # 存储 (nid -> sorted list of neighbors)
        # 同时存储反向查找：从 (prev_nid, nid) 出发，下一邻居
        graph["adj_sorted"] = graph.get("adj_sorted", {})
        graph["adj_sorted"][nid] = sorted_neighbors


def _find_faces(graph: Dict[str, Any]) -> List[List[int]]:
    """用左手定则（left-hand rule）遍历平面图的所有面。

    从每条有向边 (u→v) 出发：
    1. 到达 v 后，找到 (v→u) 在 adj_sorted[v] 中的位置
    2. "下一逆时针边" = adj_sorted[v][pos-1]（循环取前一条）
    3. 以此类推，直到回到起点

    每条有向边属于恰好一个面。用 visited 标记已访问的有向边。
    """
    adj_sorted: Dict[int, List[int]] = graph["adj_sorted"]
    nodes = graph["nodes"]
    all_edges: Set[Tuple[int, int]] = set(graph["edges"])

    visited: Set[Tuple[int, int]] = set()
    faces: List[List[int]] = []

    # 枚举所有有向边
    for edge in graph["edges"]:
        for u, v in [(edge[0], edge[1]), (edge[1], edge[0])]:
            if (u, v) in visited:
                continue
            # 从 (u→v) 开始遍历
            face: List[int] = [u]
            current = v
            prev = u
            # 标记这条边已访问
            visited.add((u, v))

            while True:
                if current == u and len(face) >= 3:
                    face.append(u)  # 闭合
                    faces.append(face)
                    break
                if current == u:
                    # 只有 1-2 条边的退化环
                    visited.add(tuple(face[i], face[i+1]) for i in range(len(face)-1))
                    break
                # 在 current 处，找到 (prev→current) 在 adj_sorted[current] 中的位置
                neighbors = adj_sorted.get(current, [])
                if prev not in neighbors:
                    break
                pos = neighbors.index(prev)
                # 下一逆时针边：pos - 1（循环）
                next_nid = neighbors[(pos - 1) % len(neighbors)]
                face.append(current)
                visited.add((prev, current))
                prev = current
                current = next_nid

    # 过滤含非房间图层的环
    result: List[List[int]] = []
    edge_layers = graph["edge_layers"]
    for face in faces:
        has_non_room = False
        for i in range(len(face) - 1):
            a, b = face[i], face[i + 1]
            key = tuple(sorted((a, b)))
            if key not in edge_layers:
                has_non_room = True
                break
            layer = edge_layers[key].upper()
            if any(kw in layer for kw in _NON_ROOM_LAYER_KW):
                has_non_room = True
                break
        if not has_non_room and len(face) >= 4:  # face[0] == face[-1]
            result.append(face)

    return result


def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """射线法判断点是否在多边形内。"""
    px, py = point
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 <= py < y2) or (y2 <= py < y1):
            t = (py - y1) / (y2 - y1)
            x = x1 + t * (x2 - x1)
            if px < x:
                inside = not inside
    return inside
