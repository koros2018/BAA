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
    "COLU",
    "视口",
    "洞口",
    "板边",
    "梁边",
    "轴",
    "BASE",
    "梁",
    "吊筋",
    "板层",
    "文字",
    "钢筋",
    "标注",
    "DIM",
    "立面看线",
    "立面",
    "看线",
    "园林",
    "井",
    "电-",
    "电气",
    "照明",
    "插座",
    "弱电",
    "消防",
    "火灾",
    "报警",
    "设备",
    "电缆",
    "系统",
    "Defpoints",
    "WIRE",
    "线槽",
    "DOTLN",
    "DOT",
)

_MATCH_THRESHOLD = 100.0  # mm — PDF→DXF 精度损失
_MIN_SEGMENT_LEN = 10.0  # mm


_Seg = Tuple[float, float, float, float, str, float]  # (x0,y0,x1,y1,layer,length)
# Node ID → (x, y)
_Node = Tuple[float, float]
# Edge = (node_id_a, node_id_b, layer)
_Edge = Tuple[int, int, str]


def _is_near_closed(self, prim: RawPrimitive, gap_threshold_mm: float = 500.0) -> bool:
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


def _sweep_line_detect_rooms(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
    """扫线法房间检测 — 平面图面遍历法。

    支持 LINE 和 LWPOLYLINE 墙线：先收集墙线原始图元，再展开为线段。
    """
    wall_prims = _collect_wall_lines(primitives)
    if len(wall_prims) < 3:
        return []

    # ── 1. 直接提取闭合 LWPOLYLINE 房间 ──
    direct_rooms = _extract_closed_polyline_rooms(wall_prims, self)
    if len(direct_rooms) >= 3:
        return direct_rooms

    # ── 2. 转为内部线段表示（LINE + LWPOLYLINE） ──
    segs: List[_Seg] = _collect_wall_segments(wall_prims)

    if len(segs) < 3:
        return []

    # ── 2a. PDF 墙段轴对齐合并（P103）──
    # PDF→DXF 的贝塞尔离散化产生大量近轴对齐的短段（75°~95° 区间为主），
    # 直接扫线法无法闭合。投影到轴后合并共线段，再扫线。
    merged_segs = _axis_align_merge(segs)
    if len(merged_segs) >= 3:
        room_candidates = _sweep_and_filter(merged_segs, self)
        if len(room_candidates) >= 3:
            return room_candidates

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
            sum(
                pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))
            )
            / 2.0
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
        key = (
            round(min(xs), -1),
            round(min(ys), -1),
            round(max(xs) - min(xs), -1),
            round(max(ys) - min(ys), -1),
        )
        if key in seen_bbox:
            continue
        seen_bbox.add(key)

        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        room_id = f"line_chain_room_{self._entity_counter}"
        self._entity_counter += 1
        result.append(
            SemanticEntity(
                entity_id=room_id,
                entity_type="room",
                layer="",
                properties={"area": area / 1_000_000},
                bbox=bbox,
            )
        )
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


def _sweep_and_filter(segs: List[_Seg], self_obj: Any) -> List[SemanticEntity]:
    """通用扫线法：T-junction → 平面图 → 左手定则面遍历 → 过滤。"""
    segs = _split_t_junctions(segs)
    if len(segs) < 3:
        return []

    graph = _build_planar_graph(segs)
    if not graph["nodes"] or not graph["edges"]:
        return []

    _sort_edges_at_nodes(graph)
    faces = _find_faces(graph)

    result: List[SemanticEntity] = []
    seen_bbox: Set[Tuple[int, int, int, int]] = set()
    for face in faces:
        pts = [(graph["nodes"][nid][0], graph["nodes"][nid][1]) for nid in face]
        if len(pts) < 3:
            continue
        area = abs(
            sum(
                pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))
            )
            / 2.0
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
        key = (
            round(min(xs), -1),
            round(min(ys), -1),
            round(max(xs) - min(xs), -1),
            round(max(ys) - min(ys), -1),
        )
        if key in seen_bbox:
            continue
        seen_bbox.add(key)

        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        room_id = f"line_chain_room_{self_obj._entity_counter}"
        self_obj._entity_counter += 1
        result.append(
            SemanticEntity(
                entity_id=room_id,
                entity_type="room",
                layer="",
                properties={"area": area / 1_000_000},
                bbox=bbox,
            )
        )
    # 剔除外框面
    if len(result) > 1:
        result.sort(key=lambda r: r.properties["area"], reverse=True)
        outer = result[0]
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
#  轴对齐合并（P103：PDF 墙段碎片化修复）
# ═══════════════════════════════════════════

_AXIS_TOL_DEG = 30.0  # 近轴对齐角度容差（度）
_AXIS_MERGE_TOL_MM = 200.0  # 共线合并距离容差（mm）
_AXIS_MIN_LEN_MM = 500.0  # 最小墙段长度


# ═══════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════


def _axis_align_merge(segs: List[_Seg]) -> List[_Seg]:
    """将 PDF 碎片化的近轴对齐墙段投影到轴上合并为完整墙线。

    PDF→DXF 贝塞尔离散化产生大量 75°~95° 的近垂直/近水平短段，
    扫线法无法直接闭合。投影到轴后按坐标聚类合并，恢复标准墙线段。
    """
    near_axis = []
    for s in segs:
        x0, y0, x1, y1, _, length = s
        if length < _AXIS_MIN_LEN_MM:
            continue
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx + dy < 100:
            continue
        angle = math.atan2(dy, dx) if dx > 0 else math.pi / 2
        if angle > math.pi / 2:
            angle = math.pi - angle
        tol_rad = math.radians(_AXIS_TOL_DEG)
        if angle <= tol_rad or angle >= math.pi / 2 - tol_rad:
            near_axis.append(s)

    if len(near_axis) < 3:
        return []

    # 投影到轴
    snapped: List[Tuple[float, float, float, float]] = []
    for s in near_axis:
        x0, y0, x1, y1, _, length = s
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx >= dy:  # 近水平
            mid_y = (y0 + y1) / 2
            snapped.append((min(x0, x1), mid_y, max(x0, x1), mid_y))
        else:  # 近垂直
            mid_x = (x0 + x1) / 2
            snapped.append((mid_x, min(y0, y1), mid_x, max(y0, y1)))

    tol = _AXIS_MERGE_TOL_MM

    # 分别合并水平段和垂直段
    horizontal: List[Tuple[float, float, float]] = []
    vertical: List[Tuple[float, float, float]] = []
    for x0, y0, x1, y1 in snapped:
        if abs(y1 - y0) < tol:
            horizontal.append((min(x0, x1), max(x0, x1), y0))
        else:
            vertical.append((min(y0, y1), max(y0, y1), x0))

    h_merged = _merge_collinear(horizontal, tol)
    v_merged = _merge_collinear(vertical, tol)

    result: List[_Seg] = []
    for lo, hi, y in h_merged:
        result.append((lo, y, hi, y, "", hi - lo))
    for lo, hi, x in v_merged:
        result.append((x, lo, x, hi, "", hi - lo))

    return result


def _merge_collinear(
    intervals: List[Tuple[float, float, float]], tol: float
) -> List[Tuple[float, float, float]]:
    """合并共线区间：先按坐标聚类，再在每簇内合并重叠区间。

    intervals: [(lo, hi, coord)]  coord 是与区间垂直的方向坐标。
    """
    coord_list: List[float] = []
    by_coord: Dict[int, List[Tuple[float, float]]] = {}
    for lo, hi, coord in intervals:
        idx = -1
        for i, c in enumerate(coord_list):
            if abs(c - coord) <= tol:
                idx = i
                break
        if idx >= 0:
            by_coord[idx].append((lo, hi))
        else:
            idx = len(coord_list)
            coord_list.append(coord)
            by_coord[idx] = [(lo, hi)]

    merged: List[Tuple[float, float, float]] = []
    for idx in sorted(by_coord):
        coord = coord_list[idx]
        sorted_intervals = sorted(by_coord[idx])
        cur_lo, cur_hi = sorted_intervals[0]
        for lo, hi in sorted_intervals[1:]:
            if lo <= cur_hi + tol:
                cur_hi = max(cur_hi, hi)
            else:
                merged.append((cur_lo, cur_hi, coord))
                cur_lo, cur_hi = lo, hi
        merged.append((cur_lo, cur_hi, coord))

    return merged


def _collect_wall_lines(primitives: List[RawPrimitive]) -> List[RawPrimitive]:
    """收集墙线候选（LINE >= 2000mm，且图层属于墙/结构/未分类）。

    排除电气、表格、图框、标注、轴网等非建筑结构图层。
    """
    # 已知非建筑结构的图层关键词（大写子串匹配）
    non_wall_layer_kw = (
        "表",
        "轴",
        "网格",
        "轴网",
        "BASE",
        "梁边",
        "板边",
        "板层",
        "吊筋",
        "钢筋",
        "标注",
        "DIM",
        "立面",
        "看线",
        "园林",
        "井",
        "电",
        "照明",
        "插座",
        "弱电",
        "消防",
        "火灾",
        "报警",
        "设备",
        "电缆",
        "系统",
        "母线",
        "线槽",
        "DOTLN",
        "DOT",
        "WIRE",
        "DEFPOINTS",
        "Defpoints",
        "图框",
        "PUB_HATCH",
        "HATCH",  # P82
        "视口",
        "洞口",
        "文字",
        "立面看线",
        "TSZ",
        "TEL",  # 标题栏/打印标记
        "PDIM",
        "steel",
        "SLAB",
        "STRUCT",
        "Foundation",
        "foundation",
        "footing",
        "Footing",
        "梁",
        "柱",
        "板",
        "钢",
        "钢构",
    )
    # 已知建筑结构相关图层关键词
    wall_layer_kw = ("WALL", "墙", "BEAM", "COLUMN", "column", "梁", "柱")

    lines: List[RawPrimitive] = []
    for prim in primitives:
        if prim.dxf_type not in ("LINE", "LWPOLYLINE"):
            continue
        # LWPOLYLINE: 使用 bbox 的 max(width,height) 近似长度
        if prim.dxf_type == "LWPOLYLINE":
            length = max((prim.bbox or {}).get("width", 0), (prim.bbox or {}).get("height", 0))
        else:
            length = max((prim.bbox or {}).get("width", 0), (prim.bbox or {}).get("height", 0))
        if length < 2000:
            continue
        layer = (prim.layer or "").upper()
        # 1. 明确非建筑图层：排除
        if any(kw in layer for kw in non_wall_layer_kw):
            continue
        # 2. 已知墙/结构图层：保留
        if any(kw in layer for kw in wall_layer_kw):
            lines.append(prim)
            continue
        # 3. 未分类图层（数字、单字母等）：宽松保留
        lines.append(prim)
    return lines


def _collect_wall_segments(
    primitives: List[RawPrimitive],
) -> List[_Seg]:
    """将墙线原始图元（LINE + LWPOLYLINE）转为内部线段列表。

    LINE 直接取起点→终点。
    LWPOLYLINE 展开为相邻点之间的线段；过滤退化段（< 10mm）。
    """
    segs: List[_Seg] = []
    for prim in primitives:
        layer = prim.layer or ""
        if prim.dxf_type == "LINE":
            sp = prim.properties.get("start_point", {})
            ep = prim.properties.get("end_point", {})
            if not sp or not ep:
                continue
            x0, y0 = sp.get("x", 0.0), sp.get("y", 0.0)
            x1, y1 = ep.get("x", 0.0), ep.get("y", 0.0)
            length = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
            if length < _MIN_SEGMENT_LEN:
                continue
            segs.append((x0, y0, x1, y1, layer, length))
        elif prim.dxf_type == "LWPOLYLINE":
            pts = prim.properties.get("points", [])
            if not pts:
                continue
            for i in range(len(pts) - 1):
                x0, y0 = pts[i]
                x1, y1 = pts[i + 1]
                length = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
                if length < _MIN_SEGMENT_LEN:
                    continue
                segs.append((x0, y0, x1, y1, layer, length))
            # 闭合检测：若首末点距离在匹配阈值内，补一条闭合段
            if len(pts) >= 4:
                x0, y0 = pts[-1]
                x1, y1 = pts[0]
                gap = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
                if 0 < gap <= _MATCH_THRESHOLD:
                    segs.append((x0, y0, x1, y1, layer, gap))
    return segs


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
            if any(abs(tx_i - s[0]) < 0.001 for s in split_pts[i]) or any(
                abs(ty_i - s[0]) < 0.001 for s in split_pts[j]
            ):
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
        best_d = _MATCH_THRESHOLD**2
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
    for a, b in edge_layers:
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
                    visited.add(tuple(face[i], face[i + 1]) for i in range(len(face) - 1))
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


def _extract_closed_polyline_rooms(
    wall_prims: List[RawPrimitive],
    self,
) -> List[SemanticEntity]:
    """直接提取闭合 LWPOLYLINE 房间（绕开扫线法图遍历，因为多边形房间互不共享墙线）。

    策略：
    - 取 4+ 顶点的 LWPOLYLINE，计算面积
    - 面积在 1m²~500m²，宽高比 ≤ 8
    - 外框剔除：最大面若包含所有内框中心则丢弃
    """
    poly_rooms: List[SemanticEntity] = []
    seen_bbox: Set[Tuple[int, int, int, int]] = set()

    for prim in wall_prims:
        if prim.dxf_type != "LWPOLYLINE":
            continue
        pts = prim.properties.get("points", [])
        if len(pts) < 4:
            continue

        # Shoelace 面积
        area = abs(
            sum(
                pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts))
            )
            / 2.0
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
        key = (
            round(min(xs), -1),
            round(min(ys), -1),
            round(max(xs) - min(xs), -1),
            round(max(ys) - min(ys), -1),
        )
        if key in seen_bbox:
            continue
        seen_bbox.add(key)

        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        room_id = f"polyline_room_{self._entity_counter}"
        self._entity_counter += 1
        poly_rooms.append(
            SemanticEntity(
                entity_id=room_id,
                entity_type="room",
                layer="",
                properties={"area": area / 1_000_000},
                bbox=bbox,
            )
        )

    # 外框面剔除（同扫线法逻辑）
    if len(poly_rooms) > 1:
        poly_rooms.sort(key=lambda r: r.properties["area"], reverse=True)
        outer = poly_rooms[0]
        ob = outer.bbox
        outer_poly = [
            (ob["x"], ob["y"]),
            (ob["x"] + ob["width"], ob["y"]),
            (ob["x"] + ob["width"], ob["y"] + ob["height"]),
            (ob["x"], ob["y"] + ob["height"]),
        ]
        all_contained = True
        for r in poly_rooms[1:]:
            ib = r.bbox
            cx = ib["x"] + ib["width"] / 2
            cy = ib["y"] + ib["height"] / 2
            if not _point_in_polygon((cx, cy), outer_poly):
                all_contained = False
                break
        if all_contained:
            poly_rooms = poly_rooms[1:]

    return poly_rooms
