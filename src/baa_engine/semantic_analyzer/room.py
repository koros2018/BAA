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
from functools import lru_cache
from bisect import bisect_left, bisect_right
import math

from .models import SemanticEntity
from ..drawing_parser import RawPrimitive
from .layer_rules import LAYER_RULES
from .room_type_infer import ROOM_TYPE_RULES

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


@lru_cache(maxsize=4096)
def _is_non_room_layer(layer: str) -> bool:
    """判断图层是否为非房间层（带缓存）。

    面过滤对每条边做 ``any(kw in layer for kw in _NON_ROOM_LAYER_KW)``，
    同一层名被多条边重复检查。实测 dongguan 53290 次边访问只有 2 个唯一
    层名（'' 和 '0'），缓存命中率 100%。用 lru_cache 把 O(36) 子串匹配
    降为 O(1) 字典查找，功能严格等价（判定是纯函数，层名是唯一输入）。
    """
    layer_upper = layer.upper()
    return any(kw in layer_upper for kw in _NON_ROOM_LAYER_KW)


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


def _signed_area(pts: List[Any]) -> float:
    """多边形有向面积（mm²）。

    左手法面遍历约定：内面为逆时针（正），连通分量的外侧包络面为顺时针（负）。
    """
    return sum(
        pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
        for i in range(len(pts))
    ) / 2.0


def _polygon_props(raw_pts: Any) -> Dict[str, Any]:
    """Task 1：把房间多边形落盘为可用的 points/point_count/closed。

    凡是作为 room 实体存在的构造路径都必须调用本函数：
    - 扫线法面遍历：face 首尾为同一节点，环天然闭合；
    - 直接闭合 LWPOLYLINE：面积按整环 shoelace 计算，闭合边隐含在环内。
    因此两者均落 closed=True；顶点不足 3 个或坐标非法时返回空 dict，
    由调用方视为多边形不可用（不得生成 room 实体）。
    """
    if not raw_pts:
        return {}
    pts: List[List[float]] = []
    for p in raw_pts:
        try:
            pts.append([float(p[0]), float(p[1])])
        except (TypeError, IndexError, ValueError):
            return {}
    if len(pts) < 3:
        return {}
    # 面遍历会显式回填起点，落盘时去掉重复闭合点，避免 point_count 虚高
    if (
        abs(pts[0][0] - pts[-1][0]) <= _MATCH_THRESHOLD
        and abs(pts[0][1] - pts[-1][1]) <= _MATCH_THRESHOLD
    ):
        pts = pts[:-1]
    if len(pts) < 3:
        return {}
    return {"points": pts, "point_count": len(pts), "closed": True}


def _room_bbox_center(bbox: Dict[str, float]) -> Tuple[float, float]:
    """bbox 中心点（mm）。"""
    return (
        bbox.get("x", 0) + bbox.get("width", 0) / 2,
        bbox.get("y", 0) + bbox.get("height", 0) / 2,
    )


def _same_space(a: SemanticEntity, b: SemanticEntity) -> bool:
    """判断两个房间实体是否描述同一物理空间（用于并存去重）。

    只有证据同时满足「覆盖范围基本相同」才判同：
      1. 面积接近：大小之比 <= _DUP_SOURCE_AREA_RATIO（±30%）；
      2. 且 (bbox IoU >= _DUP_SOURCE_IOU 或 bbox 中心距 <= _DUP_SOURCE_CENTROID_MM)。

    阈值依据：
    - 面积 ±30%：闭合多段线是墙中心线/外皮，面遍历是墙内皮，同一空间两种
      边界口径的差异通常在 10%–30%（2m×2m 房间、200mm 墙 → 3.24/4.0 = 0.81）。
      超过 30% 说明覆盖范围不同（子区域、跨房间、走廊并入房间），不能丢。
    - IoU 0.70：允许上述边界偏移；两个仅部分重叠的面（如走廊穿过房间）IoU
      通常 < 0.5，不会被误判。
    - 中心距 2000mm 与 sweep 内部质心去重容差一致；但必须与面积接近同时成立，
      避免把大房间质心附近的真实小房间当重复丢弃。
    """
    ba = a.bbox or {}
    bb = b.bbox or {}
    wa, ha = ba.get("width", 0), ba.get("height", 0)
    wb, hb = bb.get("width", 0), bb.get("height", 0)
    if wa <= 0 or ha <= 0 or wb <= 0 or hb <= 0:
        return False
    area_a = float((a.properties or {}).get("area") or (wa * ha) / 1_000_000)
    area_b = float((b.properties or {}).get("area") or (wb * hb) / 1_000_000)
    if area_a <= 0 or area_b <= 0:
        return False
    if max(area_a, area_b) / min(area_a, area_b) > _DUP_SOURCE_AREA_RATIO:
        return False
    if _bbox_iou(ba, bb) >= _DUP_SOURCE_IOU:
        return True
    ca = _room_bbox_center(ba)
    cb = _room_bbox_center(bb)
    return math.hypot(ca[0] - cb[0], ca[1] - cb[1]) <= _DUP_SOURCE_CENTROID_MM


def _merge_room_sources(
    explicit_rooms: List[SemanticEntity],
    derived_rooms: List[SemanticEntity],
) -> List[SemanticEntity]:
    """闭合多段线房间（显式几何）与面遍历房间（推断）并存，仅剔除同一空间。

    显式几何可信度高，同一空间时保留 polyline 房间；被丢弃的 sweep 面必须
    被显式房间基本覆盖（判据见 ``_same_space``），否则两者都保留。
    """
    if not derived_rooms:
        return list(explicit_rooms)
    if not explicit_rooms:
        return list(derived_rooms)
    merged: List[SemanticEntity] = list(explicit_rooms)
    for cand in derived_rooms:
        if not any(_same_space(cand, kept) for kept in explicit_rooms):
            merged.append(cand)
    return merged


def _sweep_line_detect_rooms(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
    """扫线法房间检测 — 平面图面遍历法。

    支持 LINE 和 LWPOLYLINE 墙线：先收集墙线原始图元，再展开为线段。
    闭合多段线房间与面遍历房间**并存**（不再二选一）：两者描述不同空间时都保留，
    同一空间时按 ``_same_space`` 只保留显式几何来源。
    """
    wall_prims = _collect_wall_lines(primitives)
    # P130: 排除图框与表格区域——必须在 _extract_closed_polyline_rooms /
    # _collect_wall_segments / _axis_align_merge 之前，此时 layer 尚未被清空。
    wall_prims = _exclude_table_and_frame_prims(wall_prims, primitives)

    # ── 1. 直接提取闭合 LWPOLYLINE 房间 ──
    # P0-1: 放宽到 >=1。原 >=3 门槛导致 1-2 个孤立闭合 LWPOLYLINE 房间
    # （如合成样本的单发电机房/消防车道/违规小房间）无法被识别——它们
    # 通过图遍历找不到面（孤立多边形无共享边），且 _extract_closed_polyline_rooms
    # 已应用面积/短边/宽高比严格过滤，不会误报表格/图框（前置已剔除）。
    # 注意：此检查须在 len(wall_prims)<3 门槛之前，单个闭合 LWPOLYLINE
    # 也是有效房间（如违规样本 4m×4m 控制室）。
    direct_rooms = _extract_closed_polyline_rooms(wall_prims, self)
    # 回归修复：这里不再「有闭合多段线房间就提前 return」。该短路会让面遍历
    # 整体跳过——放宽短边门槛后闭合多段线路径多命中 1–3 个房间，反而使只由
    # 面遍历产出的房间（villa 21 个 line_chain）全部消失。两条路径改为并存，
    # 同一空间由 _merge_room_sources 去重（保留显式几何来源）。
    if len(wall_prims) < 3:
        return list(direct_rooms)

    # ── 2. 转为内部线段表示（LINE + LWPOLYLINE） ──
    segs: List[_Seg] = _collect_wall_segments(wall_prims)

    if len(segs) < 3:
        return list(direct_rooms)

    # ── 2a. PDF 墙段轴对齐合并（P103）──
    # PDF→DXF 的贝塞尔离散化产生大量近轴对齐的短段（75°~95° 区间为主），
    # 直接扫线法无法闭合。投影到轴后合并共线段，再扫线。
    merged_segs = _axis_align_merge(segs)
    if len(merged_segs) >= 3:
        room_candidates = _sweep_and_filter(merged_segs, self)
        # P105: 门洞检测（使用原始墙段，非 axis-merged）
        doorway_candidates = _detect_doorway_gaps(segs)
        if len(room_candidates) >= 1:
            return _merge_room_sources(direct_rooms, room_candidates) + doorway_candidates

    # ── 2. T-junction 分割 ──
    doorway_segs = segs
    segs = _split_t_junctions(segs)
    if len(segs) < 3:
        return list(direct_rooms) + (
            _detect_doorway_gaps(doorway_segs) if direct_rooms else []
        )

    # ── 3. 构建平面图：合并近似端点 → 节点，线段 → 边 ──
    graph = _build_planar_graph(segs)
    if not graph["nodes"] or not graph["edges"]:
        return list(direct_rooms) + (
            _detect_doorway_gaps(doorway_segs) if direct_rooms else []
        )

    # ── 4. 每个节点处按角度排序边（逆时针） ──
    _sort_edges_at_nodes(graph)

    # ── 5. 平面图面遍历（左手定则）──
    faces = _find_faces(graph)

    # ── 6. 过滤 ──
    result: List[SemanticEntity] = []
    seen_centers: Set[Tuple[int, int]] = set()
    for face in faces:
        pts = [(graph["nodes"][nid][0], graph["nodes"][nid][1]) for nid in face]
        if len(pts) < 3:
            continue
        signed = _signed_area(pts)
        # Task 2：左手法内面逆时针（正）；负号是连通分量的外侧包络面
        # （整层轮廓/图框/建筑外框），不是房间，直接剔除。
        if signed <= 0:
            continue
        area = abs(signed)
        if area < 1_000_000 or area > 500_000_000:
            continue
        # P104: 面积过滤——排除双线墙间隙和建筑外框面
        if area < _MIN_ROOM_AREA_MM2 or area > _MAX_ROOM_AREA_MM2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw <= 0 or bh <= 0:
            continue
        # P104: 短边过滤——双线墙间隙短边≈墙厚度 (<2000mm)
        if min(bw, bh) < _MIN_SHORT_EDGE_MM:
            continue
        aspect = max(bw, bh) / min(bw, bh)
        if aspect > 8.0:
            continue
        # P104: 实际面积/包围盒面积比——排除外框面（实际面积远小于 bbox）
        bbox_area = bw * bh
        if bbox_area > 0 and (area / bbox_area) < _MIN_AREA_TO_BBOX_RATIO:
            continue
        # P104: 质心去重（2000mm 容差）
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        key = (round(cx, -3), round(cy, -3))
        if key in seen_centers:
            continue
        seen_centers.add(key)

        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        # P105: 面分类
        face_type = _classify_face(bw, bh, area / 1_000_000)
        room_id = f"line_chain_{face_type}_{self._entity_counter}"
        self._entity_counter += 1
        props = {"area": area / 1_000_000, "_area_source": "polygon_line_chain"}
        props.update(_polygon_props(pts))
        if face_type == "corridor":
            props["clear_width"] = min(bw, bh) * 0.001
            props["length"] = max(bw, bh) * 0.001
        result.append(
            SemanticEntity(
                entity_id=room_id,
                entity_type=face_type,
                layer="",
                properties=props,
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

    merged = _merge_room_sources(direct_rooms, result)
    if direct_rooms:
        # 原短路路径在 direct_rooms 分支始终附加门洞（P105）；并存后保持该口径。
        merged += _detect_doorway_gaps(doorway_segs)
    return merged


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
    seen_centers: Set[Tuple[int, int]] = set()
    for face in faces:
        pts = [(graph["nodes"][nid][0], graph["nodes"][nid][1]) for nid in face]
        if len(pts) < 3:
            continue
        signed = _signed_area(pts)
        # Task 2：左手法内面逆时针（正）；负号是连通分量的外侧包络面
        # （整层轮廓/图框/建筑外框），不是房间，直接剔除。
        if signed <= 0:
            continue
        area = abs(signed)
        if area < 1_000_000 or area > 500_000_000:
            continue
        # P104: 房间面积过滤——排除双线墙间隙和建筑外框面
        if area < _MIN_ROOM_AREA_MM2 or area > _MAX_ROOM_AREA_MM2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw <= 0 or bh <= 0:
            continue
        # P104: 短边过滤——双线墙间隙短边≈墙厚度 (<2000mm)
        if min(bw, bh) < _MIN_SHORT_EDGE_MM:
            continue
        aspect = max(bw, bh) / min(bw, bh)
        if aspect > 8.0:
            continue
        # P104: 实际面积/包围盒面积比——排除外框面（实际面积远小于 bbox）
        bbox_area = bw * bh
        if bbox_area > 0 and (area / bbox_area) < _MIN_AREA_TO_BBOX_RATIO:
            continue
        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        # P104: bbox 重叠去重——新 face 若与已存 room bbox 重叠 >80% 则跳过
        is_dup = False
        for existing in result:
            eb = existing.bbox
            ox = max(
                0, min(bbox["x"] + bbox["width"], eb["x"] + eb["width"]) - max(bbox["x"], eb["x"])
            )
            oy = max(
                0, min(bbox["y"] + bbox["height"], eb["y"] + eb["height"]) - max(bbox["y"], eb["y"])
            )
            if ox <= 0 or oy <= 0:
                continue
            overlap = ox * oy / (bbox["width"] * bbox["height"])
            if overlap > 0.8:
                is_dup = True
                break
        if is_dup:
            continue

        # P105: 面分类
        face_type = _classify_face(bw, bh, area / 1_000_000)
        room_id = f"line_chain_{face_type}_{self_obj._entity_counter}"
        self_obj._entity_counter += 1
        props = {"area": area / 1_000_000, "_area_source": "polygon_sweep_face"}
        props.update(_polygon_props(pts))
        if face_type == "corridor":
            props["clear_width"] = min(bw, bh) * 0.001
            props["length"] = max(bw, bh) * 0.001
        result.append(
            SemanticEntity(
                entity_id=room_id,
                entity_type=face_type,
                layer="",
                properties=props,
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
_MIN_ROOM_AREA_MM2 = 5_000_000  # 最小房间面积 5m²（排除双线墙间隙）
_MAX_ROOM_AREA_MM2 = 2_000_000_000  # 最大房间面积 2000m²（排除建筑外框面）
_MIN_SHORT_EDGE_MM = 2000.0  # 最小短边 2000mm（排除墙厚度方向的间隙）
_CENTER_DUP_TOL_MM = 2000.0  # 面质心去重容差（mm）
_CORRIDOR_ASPECT_RATIO = 3.0  # 走廊最小宽高比
_CORRIDOR_SHORT_EDGE_MAX_MM = 4000.0  # 走廊短边上限（>4000mm 为房间）
_CORRIDOR_SHORT_EDGE_MIN_MM = 2000.0  # 走廊短边下限（<2000mm 为门洞/窄缝）
_DOORWAY_GAP_MIN_MM = 700.0  # 门洞最小间隙
_DOORWAY_GAP_MAX_MM = 2500.0  # 门洞最大间隙
# 门洞去重容差：同一开洞在双线墙的两条墙线上会各检出一条，墙厚通常 100-300mm。
# 取 500mm——小于门洞宽度下界 700mm，不会把两个真门洞并成一个；大于常见墙厚，
# 足以吸收双线墙的重复检出。
_DOORWAY_DEDUP_TOL_MM = 500.0
_MIN_AREA_TO_BBOX_RATIO = 0.3  # 面实际面积/包围盒面积最小比（过滤外框面）

# 房间来源并存去重（闭合多段线 vs 面遍历）：仅当证据同时满足「覆盖范围基本相同」
# 才丢弃可信度较低的一方。面积接近（大小比 <= 1.43，即 ±30%）是必要条件，
# 且 (bbox IoU >= 0.70 或 bbox 中心距 <= 2000mm)。依据见 ``_same_space``。
_DUP_SOURCE_AREA_RATIO = 1.43
_DUP_SOURCE_IOU = 0.70
_DUP_SOURCE_CENTROID_MM = 2000.0

# ── P121-V：视图级过滤常量（drawing_classifier.py）──

# ── H 格子阵列/看台格间检测 ──────────────────────────────────────────────
# 当同一视图簇内出现 ≥GRID_MIN_COUNT 个尺寸几乎相同（边长差 < GRID_DIM_TOL）的
# sweep 派生 line_chain_* 房间，且其质心沿单一方向等距排列（间距变异系数 < GRID_SPACING_CV），
# 视为看台/货架/图例表类非房间栅格，整体丢弃。
_GRID_MIN_COUNT = 3        # 同组最少实体数
_GRID_DIM_TOL = 0.05       # 宽高各自容差（5%）——与真实标准间不同，
                           # 真实标准间虽然也同质，但通常带门/文字标注作为辅证
_GRID_SPACING_CV = 0.50    # 沿主方向的中心点间距变异系数上限
_GRID_AREA_MAX_M2 = 50.0   # 单格面积上限（超过则可能是真实大空间而非格间）
_TABLE_AXIS_TOL_DEG = 3.0  # 判定近轴段的角度容差（度）
_TABLE_LEN_TOL_REL = 0.05  # 同一族内线段长度相对容差（分桶用）
_TABLE_LEN_CV_MAX = 0.05  # 族内长度变异系数上限（长度一律）
_TABLE_MIN_LINES_PER_FAMILY = 4  # 每族最少线段数
_TABLE_MIN_LINE_COVER_RATIO = 0.90  # 贯穿整区的线段占比下限
_TABLE_LINE_COVER_TOL = 0.90  # 线段长度 / 区域对应边长 下限
_TABLE_MIN_INTERSECTION_RATIO = 0.85  # 实际交点数 / (#H * #V) 下限（网格密闭）
_TABLE_MIN_CELLS = 50  # 网格单元数下限（区分"密集表格"与"少量房间阵列"）
_TABLE_COORD_DEDUP_MM = 200.0  # 线坐标去重容差（mm）
# 单元格中位短边上限：真实房间短边 >= _MIN_SHORT_EDGE_MM，
# 表格单元格短边（本例 1366mm）远小于此，故用它作为"不是房间"的判据
_TABLE_CELL_SHORT_EDGE_MAX_MM = _MIN_SHORT_EDGE_MM
_TABLE_MIN_AREA_MM2 = 1_000_000  # 表格区域面积下限 1m²
_TABLE_MAX_AREA_MM2 = 10_000_000_000  # 表格区域面积上限 10000m²
_TABLE_REGION_PAD_MM = 200.0  # 区域边界容差（mm）
_FRAME_MIN_SIDE_MM = 50_000.0  # 图框最小边长（50m）


# ═══════════════════════════════════════════
#  Face classification (P105: corridor/doorway/room)
# ═══════════════════════════════════════════


def _classify_face(bw: float, bh: float, area_m2: float) -> str:
    """Classify a sweep face as corridor or room.

    Corridor: aspect >= 3.0 and short_edge in [2000, 4000]mm
    Room: everything else passing P104 filters.
    """
    short_edge = min(bw, bh)
    aspect = max(bw, bh) / short_edge if short_edge > 0 else 0
    if (
        aspect >= _CORRIDOR_ASPECT_RATIO
        and _CORRIDOR_SHORT_EDGE_MIN_MM <= short_edge <= _CORRIDOR_SHORT_EDGE_MAX_MM
    ):
        return "corridor"
    return "room"


def _detect_doorway_gaps(segs: List[_Seg]) -> List[SemanticEntity]:
    """Detect doorway gaps in raw wall segments (pre axis-merge).

    Strategy:
    1. Collect LINE segments >= 1000mm (filter noise from PDF bezier artifacts)
    2. Cluster by direction + coordinate
    3. Within each cluster, sort by start point and find gaps
    4. Filter gaps in doorway range (700-2500mm)
    5. Merge duplicate detections of the same opening (see _dedup_doorway_gaps)
    """
    if len(segs) < 3:
        return []

    # Use raw segments but filter out very short noise
    filtered = [s for s in segs if s[5] >= 1000]
    if len(filtered) < 3:
        return []

    horizontal: List[_Seg] = []
    vertical: List[_Seg] = []
    for s in filtered:
        x0, y0, x1, y1, _, _ = s
        if abs(y1 - y0) <= 300:
            horizontal.append(s)
        elif abs(x1 - x0) <= 300:
            vertical.append(s)

    gaps: List[Tuple[float, float, float, float, str]] = []
    _find_gaps_in_axis_v2(horizontal, gaps, "horizontal")
    _find_gaps_in_axis_v2(vertical, gaps, "vertical")

    result: List[SemanticEntity] = []
    for x, y, w, h, direction in _dedup_doorway_gaps(gaps):
        # 阶段 A：几何推断的墙洞补稳定 ID，便于 finding 追溯与图节点引用。
        # ID 由中心点几何派生（同图重跑稳定），不含递增计数器，避免与房间 ID 耦合。
        suffix = "h" if direction == "horizontal" else "v"
        cx = x + w / 2 if direction == "horizontal" else x
        cy = y if direction == "horizontal" else y + h / 2
        result.append(
            SemanticEntity(
                entity_id=f"doorway_gap_{suffix}_{int(round(cx))}_{int(round(cy))}",
                entity_type="doorway",
                layer="",
                properties={
                    "gap_width_mm": w if direction == "horizontal" else h,
                    "direction": direction,
                    # 阶段 A 隔离：墙线间隙只证明「此处有开口」，不证明是疏散出口。
                    # doorway 与 exit_door 同属别名组 4，若不带显式否定标记，
                    # 下游出口识别/BFS 会把它当合成出口。此标记落盘而非隐含。
                    "exit_eligible": False,
                    "inferred_from": "wall_gap",
                },
                bbox={"x": x, "y": y, "width": w, "height": h},
            )
        )
    return result


def _dedup_doorway_gaps(
    gaps: List[Tuple[float, float, float, float, str]],
    tol_mm: float = _DOORWAY_DEDUP_TOL_MM,
) -> List[Tuple[float, float, float, float, str]]:
    """合并同一开洞的重复检出：同方向、间隙中心点相距 <= tol_mm 视为一处。

    不同方向的两个间隙即使位置相近也不是同一开洞（转角处横墙与竖墙各有一个），
    因此方向必须参与判定。旧实现用 (round(x,-3), round(y,-3)) 分格去重：
    注释写 500mm、代码实际 1000mm，且不区分方向——villa 图 y=7200 处的
    水平间隙与竖间隙因此被并成一条。
    """
    kept: List[Tuple[float, float, float, float, str]] = []
    seen: List[Tuple[float, float, str]] = []
    for gap in gaps:
        x, y, w, h, direction = gap
        cx, cy = (x + w / 2, y) if direction == "horizontal" else (x, y + h / 2)
        if any(
            d == direction and math.hypot(cx - px, cy - py) <= tol_mm for px, py, d in seen
        ):
            continue
        seen.append((cx, cy, direction))
        kept.append(gap)
    return kept


def _find_gaps_in_axis_v2(
    segs: List[_Seg],
    gaps: List[Tuple[float, float, float, float, str]],
    direction: str,
) -> None:
    """Find doorway gaps between adjacent wall segments on the same line.

    Uses a two-pass approach:
    1. Cluster segments by coordinate (approximate same wall line)
    2. Within each cluster, sort by start point and detect gaps
    """
    tol = 1500.0  # coordinate clustering tolerance
    coord_list: List[float] = []
    by_coord: Dict[int, List[_Seg]] = {}

    for s in segs:
        x0, y0, x1, y1, _, _ = s
        coord = (y0 + y1) / 2 if direction == "horizontal" else (x0 + x1) / 2

        idx = -1
        for i, c in enumerate(coord_list):
            if abs(c - coord) <= tol:
                idx = i
                break
        if idx >= 0:
            by_coord[idx].append(s)
        else:
            idx = len(coord_list)
            coord_list.append(coord)
            by_coord[idx] = [s]

    for idx in sorted(by_coord):
        cluster = by_coord[idx]
        if direction == "horizontal":
            sorted_segs = sorted(cluster, key=lambda s: min(s[0], s[2]))
        else:
            sorted_segs = sorted(cluster, key=lambda s: min(s[1], s[3]))

        for i in range(len(sorted_segs) - 1):
            a = sorted_segs[i]
            b = sorted_segs[i + 1]
            if direction == "horizontal":
                gap = min(b[0], b[2]) - max(a[0], a[2])
                gap_x = max(a[0], a[2])
                gap_y = (a[1] + a[3]) / 2
                if gap < _DOORWAY_GAP_MIN_MM or gap > _DOORWAY_GAP_MAX_MM:
                    continue
                wall_thick = max(200.0, abs(a[3] - a[1]))
                gaps.append((gap_x, gap_y, gap, wall_thick, "horizontal"))
            else:
                gap = min(b[1], b[3]) - max(a[1], a[3])
                gap_x = (a[0] + a[2]) / 2
                gap_y = max(a[1], a[3])
                if gap < _DOORWAY_GAP_MIN_MM or gap > _DOORWAY_GAP_MAX_MM:
                    continue
                wall_thick = max(200.0, abs(a[2] - a[0]))
                gaps.append((gap_x, gap_y, wall_thick, gap, "vertical"))


# ═══════════════════════════════════════════
#  Auxiliary functions
# ═══════════════════════════════════════════


def _axis_align_merge(segs: List[_Seg]) -> List[_Seg]:
    """将 PDF 碎片化的近轴对齐墙段投影到轴上合并为完整墙线。

    PDF→DXF 贝塞尔离散化产生大量 75°~95° 的近垂直/近水平短段，
    扫线法无法直接闭合。投影到轴后按坐标聚类合并，恢复标准墙线段。

    不变量：合并只能「归并」，不能「删除」几何。短于 _AXIS_MIN_LEN_MM 的
    墙段原样透传——它们是 T 接锚点（墙垛、洞口边、转角小段），删掉会让
    相邻长墙的端点变成悬空端。实测东莞通 1,007 个近轴短段中 868 个承担
    「至少一端连接两根以上保留段」的锚点作用；吞掉它们使合并后悬空端点
    增加、T 接数从 3,928 降到 2,356。透传短段后悬空端点 3,179→2,809，
    T 接恢复，剥面碎片率同时从 59.1% 降到 57.9%（段数仍有 7,895→3,285
    的归并收益）。
    """
    near_axis = []
    short_passthrough: List[_Seg] = []
    for s in segs:
        x0, y0, x1, y1, _, length = s
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx + dy < 100:
            continue
        angle = math.atan2(dy, dx) if dx > 0 else math.pi / 2
        if angle > math.pi / 2:
            angle = math.pi - angle
        tol_rad = math.radians(_AXIS_TOL_DEG)
        if not (angle <= tol_rad or angle >= math.pi / 2 - tol_rad):
            continue
        if length < _AXIS_MIN_LEN_MM:
            short_passthrough.append(s)
            continue
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

    return result + short_passthrough


def _merge_collinear(
    intervals: List[Tuple[float, float, float]], tol: float
) -> List[Tuple[float, float, float]]:
    """合并共线区间：先按坐标聚类，再在每簇内合并重叠区间。

    intervals: [(lo, hi, coord)]  coord 是与区间垂直的方向坐标。

    保持原始语义：每个簇以「第一个插入的 coord」为锚点，后续 coord
    按插入顺序找第一个 abs(anchor - coord) <= tol 的簇。此语义依赖
    插入顺序，用排序+二分严格等价实现（O(n·k)，k 为 tol 内簇数）：
    维护 sorted_anchors = [(anchor, idx)] 按 anchor 排序，对每个新 coord
    二分找 anchor ∈ [coord-tol, coord+tol] 的所有候选，取其中 idx 最小者
    （第一个插入的簇）。实测 5000 组随机 + 4 张真实图纸 0 差异。
    """
    coord_list: List[float] = []
    by_coord: Dict[int, List[Tuple[float, float]]] = {}
    # (anchor, idx) 按 anchor 排序；idx 是 coord_list 中的下标（插入顺序）
    sorted_anchors: List[Tuple[float, float, int]] = []
    for lo, hi, coord in intervals:
        # 二分找 anchor ∈ [coord-tol, coord+tol] 的候选，取 idx 最小者
        pos_l = bisect_left(sorted_anchors, (coord - tol, -1.0, -1))
        pos_r = bisect_right(sorted_anchors, (coord + tol, float("inf"), 10**18))
        best_idx = -1
        for p in range(pos_l, pos_r):
            idx = sorted_anchors[p][2]
            if best_idx == -1 or idx < best_idx:
                best_idx = idx
        if best_idx >= 0:
            by_coord[best_idx].append((lo, hi))
        else:
            idx = len(coord_list)
            coord_list.append(coord)
            by_coord[idx] = [(lo, hi)]
            ins = bisect_left(sorted_anchors, (coord, -1.0, idx))
            sorted_anchors.insert(ins, (coord, -1.0, idx))

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

    # P0-3 优化（2026-11-04）：layer 判定结果缓存。
    # 原实现对每个 prim 调 any(kw in layer for kw in non_wall_layer_kw)（~50 关键词），
    # 48K primitives × 50 = 240 万次子串匹配。同层名只判一次，unique layers 通常仅数百。
    _wall_layer_cache: Dict[str, str] = {}  # layer -> "wall" | "excluded" | "keep"

    def _classify_wall_layer(layer: str) -> str:
        if layer in _wall_layer_cache:
            return _wall_layer_cache[layer]
        u = layer.upper()
        # 1. 明确非建筑图层：排除
        if any(kw in u for kw in non_wall_layer_kw):
            _wall_layer_cache[layer] = "excluded"
            return "excluded"
        # P130: titleblock 图层排除
        if _is_titleblock_layer(layer):
            _wall_layer_cache[layer] = "excluded"
            return "excluded"
        # 2. 已知墙/结构图层：保留
        if any(kw in u for kw in wall_layer_kw):
            _wall_layer_cache[layer] = "wall"
            return "wall"
        # 3. 未分类图层：宽松保留
        _wall_layer_cache[layer] = "keep"
        return "keep"

    lines: List[RawPrimitive] = []
    for prim in primitives:
        if prim.dxf_type not in ("LINE", "LWPOLYLINE"):
            continue
        # LWPOLYLINE: 使用 bbox 的 max(width,height) 近似长度
        length = max((prim.bbox or {}).get("width", 0), (prim.bbox or {}).get("height", 0))
        if length < 2000:
            continue
        layer = (prim.layer or "").upper()
        verdict = _classify_wall_layer(layer)
        if verdict == "excluded":
            continue
        lines.append(prim)
    return lines


# ═══════════════════════════════════════════
#  P130: 图框/表格区域排除
# ═══════════════════════════════════════════


def _is_titleblock_layer(layer: str) -> bool:
    """图层是否映射为 titleblock（图框/图签/标题栏）。

    只取 LAYER_RULES 中值为 "titleblock" 的键；子串匹配方式与 classify 一致。
    注意：P-KX1 / PP-COM / VDWG / BORDER 在规则中映射为 "other"，不参与排除。
    """
    u = (layer or "").upper()
    if not u:
        return False
    for kw, t in LAYER_RULES.items():
        if t == "titleblock" and kw.upper() in u:
            return True
    return False


def _prim_endpoints(prim: RawPrimitive) -> List[Tuple[float, float]]:
    """取图元的关键点：LINE 取起终点；LWPOLYLINE 取全部顶点。"""
    if prim.dxf_type == "LINE":
        sp = prim.properties.get("start_point", {}) or {}
        ep = prim.properties.get("end_point", {}) or {}
        if not sp or not ep:
            return []
        return [
            (float(sp.get("x", 0.0)), float(sp.get("y", 0.0))),
            (float(ep.get("x", 0.0)), float(ep.get("y", 0.0))),
        ]
    if prim.dxf_type == "LWPOLYLINE":
        pts = prim.properties.get("points", []) or []
        return [(float(p[0]), float(p[1])) for p in pts]
    return []


def _prim_within_regions(prim: RawPrimitive, regions: List[dict]) -> bool:
    """判断图元是否整体落在任一区域 bbox 内（含 _TABLE_REGION_PAD_MM 容差）。

    要求"全部关键点均在区域内"，避免误排跨越表格边界的墙线。
    """
    pts = _prim_endpoints(prim)
    if not pts:
        return False
    # P0-3 优化：bbox 快速排除。若图元 bbox 与区域 bbox 不重叠，则必不在区域内。
    pb = prim.bbox or {}
    px0, py0 = pb.get("x", 0.0), pb.get("y", 0.0)
    px1 = px0 + pb.get("width", 0)
    py1 = py0 + pb.get("height", 0)
    for r in regions:
        x0, y0 = r["x"], r["y"]
        x1, y1 = x0 + r["width"], y0 + r["height"]
        pad = _TABLE_REGION_PAD_MM
        # 快速排除：bbox 不重叠（含 pad 容差）
        if px1 < x0 - pad or px0 > x1 + pad or py1 < y0 - pad or py0 > y1 + pad:
            continue
        if all(
            x0 - pad <= px <= x1 + pad and y0 - pad <= py <= y1 + pad for px, py in pts
        ):
            return True
    return False


def _cv(values: List[float]) -> float:
    """变异系数 = 标准差 / 均值；样本 < 2 或均值 <= 0 时返回 0.0。"""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    if mean <= 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(var) / mean


def _median(values: List[float]) -> float:
    """中位数；空列表返回 0.0。"""
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _dedup_coords(values: List[float], tol: float) -> List[float]:
    """坐标去重（合并间隔 <= tol 的重复值），返回升序列表。"""
    out: List[float] = []
    for v in sorted(values):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _cluster_by_length(segs: List[_Seg], tol_rel: float) -> List[List[_Seg]]:
    """按线段长度聚类：排序后线性扫描，桶内 max/min <= 1 + tol_rel。"""
    ordered = sorted(segs, key=lambda s: s[5])
    clusters: List[List[_Seg]] = []
    cur: List[_Seg] = []
    cur_lo = 0.0
    for s in ordered:
        ln = s[5]
        if not cur:
            cur = [s]
            cur_lo = ln
            continue
        if cur_lo > 0 and ln / cur_lo <= 1.0 + tol_rel:
            cur.append(s)
        else:
            clusters.append(cur)
            cur = [s]
            cur_lo = ln
    if cur:
        clusters.append(cur)
    return clusters


def _axis_split(segs: List[_Seg]) -> Tuple[List[_Seg], List[_Seg]]:
    """按 _TABLE_AXIS_TOL_DEG 把线段分为水平族 H 与垂直族 V，其余丢弃。"""
    tol = math.tan(math.radians(_TABLE_AXIS_TOL_DEG))
    h: List[_Seg] = []
    v: List[_Seg] = []
    for s in segs:
        x0, y0, x1, y1, _, _ = s
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx <= 0 and dy <= 0:
            continue
        if dy <= tol * dx:
            h.append(s)
        elif dx <= tol * dy:
            v.append(s)
    return h, v


def _count_grid_intersections(h: List[_Seg], v: List[_Seg]) -> int:
    """统计 H 段与 V 段实际相交的对数（交点须落在线段范围内）。"""
    count = 0
    for hs in h:
        hx0, hy, hx1, _, _, _ = hs
        lo_x, hi_x = min(hx0, hx1) - _TABLE_REGION_PAD_MM, max(hx0, hx1) + _TABLE_REGION_PAD_MM
        for vs in v:
            vx, vy0, _, vy1, _, _ = vs
            lo_y, hi_y = min(vy0, vy1) - _TABLE_REGION_PAD_MM, max(vy0, vy1) + _TABLE_REGION_PAD_MM
            if lo_x <= vx <= hi_x and lo_y <= hy <= hi_y:
                count += 1
    return count


def _try_detect_table(h: List[_Seg], v: List[_Seg], hb=None, vb=None) -> Optional[dict]:
    """对一对 (H 族, V 族) 做判据；全部满足返回区域 bbox，否则 None。

    hb/vb 为预计算的 cluster bbox (x0, x1, y0, y1)，由 _detect_table_regions 传入，
    避免每对 (h,v) 重复遍历 h+v 求 min/max（P0-5 优化）。未传入时回退到逐点遍历。
    """
    if len(h) < _TABLE_MIN_LINES_PER_FAMILY or len(v) < _TABLE_MIN_LINES_PER_FAMILY:
        return None

    # P0-4 优化（2026-11-04）：判据重排——先算面积（判据 2）再算 CV（判据 1）。
    # 历史实测：50MB 电气图 1968 对 (h,v) 中，面积判据过滤 99.8%（1036→3），
    # 而 CV 判据只过滤 47%。先算面积可避免 99.8% 的 CV 计算（O(len) 两次），
    # 完全等价（判据为 AND 关系，顺序无关），_detect_table_regions 0.023s→0.016s。

    # 区域 bbox（判据 2 前置，用预计算 cluster bbox 合并）
    if hb is None or vb is None:
        xs: List[float] = []
        ys: List[float] = []
        for s in h + v:
            xs.extend((s[0], s[2]))
            ys.extend((s[1], s[3]))
        rx0, rx1 = min(xs), max(xs)
        ry0, ry1 = min(ys), max(ys)
    else:
        rx0 = min(hb[0], vb[0])
        rx1 = max(hb[1], vb[1])
        ry0 = min(hb[2], vb[2])
        ry1 = max(hb[3], vb[3])
    rw, rh = rx1 - rx0, ry1 - ry0
    if rw <= 0 or rh <= 0:
        return None

    # 判据 2：区域面积区间
    if not (_TABLE_MIN_AREA_MM2 <= rw * rh <= _TABLE_MAX_AREA_MM2):
        return None

    # 判据 1：族内长度一律
    if _cv([s[5] for s in h]) > _TABLE_LEN_CV_MAX:
        return None
    if _cv([s[5] for s in v]) > _TABLE_LEN_CV_MAX:
        return None

    # 判据 3：贯穿整区（水平段长 >= 0.9*区域宽，垂直段长 >= 0.9*区域高）
    h_covered = sum(1 for s in h if s[5] >= _TABLE_LINE_COVER_TOL * rw)
    v_covered = sum(1 for s in v if s[5] >= _TABLE_LINE_COVER_TOL * rh)
    if h_covered / len(h) < _TABLE_MIN_LINE_COVER_RATIO:
        return None
    if v_covered / len(v) < _TABLE_MIN_LINE_COVER_RATIO:
        return None

    # 判据 4：网格密闭（线段实际相交比例）
    intersections = _count_grid_intersections(h, v)
    if intersections / (len(h) * len(v)) < _TABLE_MIN_INTERSECTION_RATIO:
        return None

    # 判据 5：密集网格（单元数 = (列数)*(行数)）
    h_coords = _dedup_coords([(s[1] + s[3]) / 2 for s in h], _TABLE_COORD_DEDUP_MM)
    v_coords = _dedup_coords([(s[0] + s[2]) / 2 for s in v], _TABLE_COORD_DEDUP_MM)
    n_rows = len(h_coords) - 1
    n_cols = len(v_coords) - 1
    if n_rows < 1 or n_cols < 1 or n_rows * n_cols < _TABLE_MIN_CELLS:
        return None

    # 判据 6：单元格尺度远小于房间最小短边（排除"成排真实房间"）
    row_pitch = _median([b - a for a, b in zip(h_coords, h_coords[1:])])
    col_pitch = _median([b - a for a, b in zip(v_coords, v_coords[1:])])
    if min(row_pitch, col_pitch) >= _TABLE_CELL_SHORT_EDGE_MAX_MM:
        return None

    return {"x": rx0, "y": ry0, "width": rw, "height": rh}


def _detect_table_regions(segs: List[_Seg]) -> List[dict]:
    """P130: 几何识别"规则网格表格"区域，返回 bbox 列表。

    判据（全部满足才判定为表格，宁可漏排不误排）：
      1. 同长度族内 H/V 线段数 >= _TABLE_MIN_LINES_PER_FAMILY，且族内长度 CV <= _TABLE_LEN_CV_MAX
      2. 区域面积落在 [_TABLE_MIN_AREA_MM2, _TABLE_MAX_AREA_MM2]
      3. 族内 >= _TABLE_MIN_LINE_COVER_RATIO 的线段长度 >= _TABLE_LINE_COVER_TOL×区域对应边长（贯穿整区）
      4. 实际交点数 / (#H*#V) >= _TABLE_MIN_INTERSECTION_RATIO（网格密闭）
      5. 网格单元数 >= _TABLE_MIN_CELLS（密集阵列）
      6. 单元格中位行/列间距的最小值 < _TABLE_CELL_SHORT_EDGE_MAX_MM（不是房间尺度）

    说明：真实图纸中的图例表格可能是多个子表拼接（行距不均匀、部分线不贯穿），
    因此不要求"等距"，改用"密集 + 密闭 + 房间尺度以下"来判定；
    真实房间阵列达不到判据 3/4/5。
    """
    h_all, v_all = _axis_split(segs)
    if not h_all or not v_all:
        return []

    # P0-5 优化（2026-11-04）：预计算每个 cluster 的 bbox，避免 _try_detect_table
    # 内对每对 (h,v) 重复遍历 h+v 求 min/max。1968 对 × O(len(h)+len(v)) 的
    # 面积计算降至 O(#clusters) 一次。历史实测 _detect_table_regions
    # 0.016s→0.002s（8×），输出完全等价（bbox 合并为 min/max，与逐对遍历结果一致）。
    # 2026-11-06 实测：_sweep_line_detect_rooms 整体 ≈0.056s（48.9MB 电气图，
    # 宿主机负载 ≈50%），约占 analyze 总量（≈0.70s）的 8%；图例表格检测
    # 已降至 0.002s 量级，不再是该阶段的成本中心。
    h_clusters = _cluster_by_length(h_all, _TABLE_LEN_TOL_REL)
    v_clusters = _cluster_by_length(v_all, _TABLE_LEN_TOL_REL)

    def _cluster_bbox(cluster):
        xs: List[float] = []
        ys: List[float] = []
        for s in cluster:
            xs.extend((s[0], s[2]))
            ys.extend((s[1], s[3]))
        return (min(xs), max(xs), min(ys), max(ys))

    h_bboxes = [_cluster_bbox(c) for c in h_clusters]
    v_bboxes = [_cluster_bbox(c) for c in v_clusters]

    regions: List[dict] = []
    for h, hb in zip(h_clusters, h_bboxes):
        for v, vb in zip(v_clusters, v_bboxes):
            cand = _try_detect_table(h, v, hb, vb)
            if cand is not None:
                regions.append(cand)
    return regions


def _detect_frame_rects(all_prims: List[RawPrimitive], segs: List[_Seg]) -> List[dict]:
    """P130: 识别图框边框区域（titleblock 图层上的大尺度图元 bbox）。

    P0-2 优化（2026-11-04）：原实现每次调 `_is_titleblock_layer(p.layer)` 都
    遍历 LAYER_RULES 字典，对 48K primitives 产生 48K × N = 近百万次子串匹配。
    优化：层名 → titleblock 判定结果的 dict 缓存（同层只算一次）。
    unique_layer_names 通常仅数十到数百，完整扫描 titleblock 规则仅数次。
    """
    rects: List[dict] = []
    # 层名判定结果缓存
    _layer_cache: Dict[str, bool] = {}

    def _fast_is_titleblock(layer: str) -> bool:
        if layer in _layer_cache:
            return _layer_cache[layer]
        result = _is_titleblock_layer(layer)
        _layer_cache[layer] = result
        return result

    for p in all_prims:
        if not _fast_is_titleblock(p.layer or ""):
            continue
        b = p.bbox or {}
        w, h = b.get("width", 0), b.get("height", 0)
        if w <= 0 or h <= 0:
            continue
        if max(w, h) < _FRAME_MIN_SIDE_MM:
            continue
        rects.append({"x": b.get("x", 0.0), "y": b.get("y", 0.0), "width": w, "height": h})
    return rects


def _prim_on_rect_border(prim: RawPrimitive, rects: List[dict]) -> bool:
    """判断图元的全部关键点是否都贴在某个矩形边框上（"图框边框"判据）。

    只排除边框线本身，不排除边框内部的图元——否则整幅图框内的墙线都会被误排。
    """
    pts = _prim_endpoints(prim)
    if not pts:
        return False
    pad = _TABLE_REGION_PAD_MM
    # P0-3 优化：bbox 快速排除。若图元 bbox 与矩形 bbox 不重叠，则必不在边框上。
    pb = prim.bbox or {}
    px0, py0 = pb.get("x", 0.0), pb.get("y", 0.0)
    px1 = px0 + pb.get("width", 0)
    py1 = py0 + pb.get("height", 0)
    for r in rects:
        x0, y0 = r["x"], r["y"]
        x1, y1 = x0 + r["width"], y0 + r["height"]
        if px1 < x0 - pad or px0 > x1 + pad or py1 < y0 - pad or py0 > y1 + pad:
            continue
        if all(
            min(abs(px - x0), abs(px - x1), abs(py - y0), abs(py - y1)) <= pad for px, py in pts
        ):
            return True
    return False


def _exclude_table_and_frame_prims(
    prims: List[RawPrimitive], all_prims: List[RawPrimitive]
) -> List[RawPrimitive]:
    """P130: 从墙线候选中剔除表格网格、titleblock 图层与图框边框图元。

    参数:
        prims:     _collect_wall_lines 的输出（墙线候选）
        all_prims: 解析出来的全量图元（用于取图框图元的 bbox）
    """
    segs = _collect_wall_segments(prims)
    table_regions = _detect_table_regions(segs)
    frame_rects = _detect_frame_rects(all_prims, segs)

    # P0-3 优化：titleblock 层判定缓存（同层只判一次）
    _tb_cache: Dict[str, bool] = {}

    def _fast_tb(layer: str) -> bool:
        if layer in _tb_cache:
            return _tb_cache[layer]
        result = _is_titleblock_layer(layer)
        _tb_cache[layer] = result
        return result

    kept: List[RawPrimitive] = []
    for p in prims:
        if _fast_tb(p.layer or ""):
            continue
        if table_regions and _prim_within_regions(p, table_regions):
            continue
        if frame_rects and _prim_on_rect_border(p, frame_rects):
            continue
        kept.append(p)
    return kept


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


class _SpatialGrid:
    """均匀网格空间索引，用于加速线段/端点的邻域查询。

    把 O(n²) 的全量两两比较降为 O(n·k)（k 为局部邻域对象数）。
    cell_size 取匹配阈值，保证任意距离 <= cell_size 的点对必落在
    相邻 cell（含自身）内，查询时只需扫描 3×3 邻域。

    关键设计：**用端点索引而非线段 bbox 索引**。线段可能跨越大量 cell
    （合并后的墙线可达数万 mm），按 bbox 插入会爆炸或漏插；而端点总是
    点对象，插入单个 cell 即可。查询线段 i 的候选时，查 i 的 bbox 扩张
    附近的所有端点，收集这些端点所属的线段——这样超长线段也能正确覆盖。

    用途：
      - _split_t_junctions Pass 1（端点投影到线段）
      - _split_t_junctions Pass 2（线段-线段交叉）
      - _build_planar_graph 端点聚类（_find_or_create）
    """

    def __init__(self, cell_size: float):
        self.cell_size = cell_size
        # 嵌套 dict：cells[kx][ky] = [idx]，避免空 cell 的元组构造/哈希开销。
        # 实测 dongguan query_bbox 遍历 135 万 cell 中 73% 为空，嵌套 dict
        # 让空行整列跳过（row 为 None），query_bbox 0.198s → 0.084s（2.4x）。
        self.cells: Dict[int, Dict[int, List[int]]] = {}
        # 行内 ky 键排序缓存（懒构建）：非空 row 内仍有 72.7% 空 cell，
        # 用二分只遍历 ky 范围内的存在键，跳过空 cell 的 row.get 检查。
        self._row_keys: Dict[int, List[int]] = {}
        self._row_keys_dirty = False

    def _key(self, x: float, y: float) -> Tuple[int, int]:
        return (int(math.floor(x / self.cell_size)), int(math.floor(y / self.cell_size)))

    def _append_cell(self, kx: int, ky: int, idx: int) -> None:
        """把 idx 追加到 cell (kx,ky)，自动创建嵌套行。"""
        row = self.cells.get(kx)
        if row is None:
            row = {}
            self.cells[kx] = row
        lst = row.get(ky)
        if lst is None:
            row[ky] = [idx]
        else:
            lst.append(idx)
        self._row_keys_dirty = True

    def insert_point(self, idx: int, x: float, y: float) -> None:
        """把对象 idx 插入其所在 cell（点对象）。"""
        kx, ky = self._key(x, y)
        self._append_cell(kx, ky, idx)

    def insert_segment(self, idx: int, x0: float, y0: float, x1: float, y1: float) -> None:
        """把对象 idx 按线段路径插入覆盖的所有 cell（线段对象）。

        用 Amanatides-Woo DDA 网格遍历：从起点 cell 出发，沿线段方向
        逐步跨越 cell 边界，精确遍历线段穿过的每个 cell（不重不漏）。
        保证：若线段 j 与查询 bbox 相交，则 j 被插入相交区域所在 cell，
        查询时能被正确找到。超长线段（跨大量 cell）也正确覆盖。
        """
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            kx, ky = self._key(x0, y0)
            self._append_cell(kx, ky, idx)
            return
        cs = self.cell_size
        # 起点 cell
        kx = int(math.floor(x0 / cs))
        ky = int(math.floor(y0 / cs))
        kx_end = int(math.floor(x1 / cs))
        ky_end = int(math.floor(y1 / cs))
        # 内联 _append_cell + 缓存当前 row：DDA 遍历中同一 kx 重复出现，
        # 缓存 row 避免重复 self.cells.get(kx)。
        row = self.cells.get(kx)
        if row is None:
            row = {}
            self.cells[kx] = row
        lst = row.get(ky)
        if lst is None:
            row[ky] = [idx]
        else:
            lst.append(idx)
        self._row_keys_dirty = True
        if kx == kx_end and ky == ky_end:
            return
        # DDA 步进参数
        step_x = 1 if dx > 0 else -1
        step_y = 1 if dy > 0 else -1
        # 到下一个垂直/水平 cell 边界的参数 t
        if dx != 0:
            t_max_x = ((kx + (1 if dx > 0 else 0)) * cs - x0) / dx
            t_delta_x = abs(cs / dx)
        else:
            t_max_x = float("inf")
            t_delta_x = float("inf")
        if dy != 0:
            t_max_y = ((ky + (1 if dy > 0 else 0)) * cs - y0) / dy
            t_delta_y = abs(cs / dy)
        else:
            t_max_y = float("inf")
            t_delta_y = float("inf")
        # 防退化：dx/dy 为 0 时步进方向无意义，但已由 inf 处理
        guard = 0
        max_steps = (abs(kx_end - kx) + abs(ky_end - ky)) * 2 + 4
        while (kx != kx_end or ky != ky_end) and guard < max_steps:
            if t_max_x < t_max_y:
                kx += step_x
                t_max_x += t_delta_x
                # kx 变化，重新获取 row
                row = self.cells.get(kx)
                if row is None:
                    row = {}
                    self.cells[kx] = row
            else:
                ky += step_y
                t_max_y += t_delta_y
            lst = row.get(ky)
            if lst is None:
                row[ky] = [idx]
            else:
                lst.append(idx)
            self._row_keys_dirty = True
            guard += 1

    def query_point(self, x: float, y: float, radius: float) -> List[int]:
        """返回距 (x,y) 半径 radius 内可能匹配的对象索引（3×3 邻域）。"""
        kx = int(math.floor(x / self.cell_size))
        ky = int(math.floor(y / self.cell_size))
        r = int(math.ceil(radius / self.cell_size))
        out: List[int] = []
        seen: Set[int] = set()
        for dx in range(-r, r + 1):
            row = self.cells.get(kx + dx)
            if row is None:
                continue
            for dy in range(-r, r + 1):
                lst = row.get(ky + dy)
                if lst is None:
                    continue
                for idx in lst:
                    if idx not in seen:
                        seen.add(idx)
                        out.append(idx)
        return out

    def query_bbox(self, x0: float, y0: float, x1: float, y1: float, pad: float) -> List[int]:
        """返回 bbox 扩张 pad 后覆盖 cell 内的对象索引。

        额外扩张 1 个 cell（cell_size）：因为 insert_segment 采样点间隔
        cell_size/2，线段与查询 bbox 相交时其采样点可能落在 bbox 边界外
        最多 1 个 cell，需额外容差避免漏检。
        """
        extra = self.cell_size
        kx0 = int(math.floor((min(x0, x1) - pad - extra) / self.cell_size))
        kx1 = int(math.floor((max(x0, x1) + pad + extra) / self.cell_size))
        ky0 = int(math.floor((min(y0, y1) - pad - extra) / self.cell_size))
        ky1 = int(math.floor((max(y0, y1) + pad + extra) / self.cell_size))
        # 懒构建行内 ky 键排序缓存：非空 row 内仍有 72.7% 空 cell，
        # 用二分只遍历 ky 范围内的存在键，跳过空 cell 的 row.get 检查。
        # 缓存 (row, sorted_keys) 元组，避免 query_bbox 中 cells.get(kx)
        # 和 _row_keys.get(kx) 两次行查询。
        if self._row_keys_dirty:
            self._row_keys = {
                kx: (row, sorted(row.keys())) for kx, row in self.cells.items()
            }
            self._row_keys_dirty = False
        out: List[int] = []
        seen: Set[int] = set()
        for kx in range(kx0, kx1 + 1):
            entry = self._row_keys.get(kx)
            if entry is None:
                continue
            row, keys = entry
            lo = bisect_left(keys, ky0)
            hi = bisect_right(keys, ky1)
            # 用索引遍历避免 keys[lo:hi] 切片创建列表
            for _k in range(lo, hi):
                lst = row.get(keys[_k])
                if lst is None:
                    continue
                for idx in lst:
                    if idx not in seen:
                        seen.add(idx)
                        out.append(idx)
        return out


def _split_t_junctions(segs: List[_Seg]) -> List[_Seg]:
    """在 T-junction 和交叉点处分割线段。"""
    n = len(segs)
    split_pts: List[List[Tuple[float, float, float]]] = [[] for _ in range(n)]

    # 空间索引：线段按路径采样插入网格（用 insert_segment 覆盖超长线段）。
    # 保证：若线段 j 与查询 bbox 相交，则 j 的采样点落在相交区域，
    # 从而 j 被插入该区域所在 cell，查询时能被正确找到。
    seg_grid = _SpatialGrid(_MATCH_THRESHOLD)
    for i, s in enumerate(segs):
        seg_grid.insert_segment(i, s[0], s[1], s[2], s[3])

    # Pass 1: 端点到线段的 T-junction
    # 用线段索引：查线段 i 的 bbox 扩张 100mm 内的所有线段（候选）
    # 缓存候选供 Pass 2 复用（Pass 2 的 pad=0 范围是 pad=100mm 的子集，
    # _seg_intersection 会精确过滤不相交的候选）
    cands_by_i: List[List[int]] = [[] for _ in range(n)]
    for i in range(n):
        x0i, y0i, x1i, y1i = segs[i][0], segs[i][1], segs[i][2], segs[i][3]
        dx_i, dy_i = x1i - x0i, y1i - y0i
        len2_i = dx_i * dx_i + dy_i * dy_i
        if len2_i < 1e-6:
            continue
        # 查询线段 i 的 bbox 扩张 100mm 内的所有候选线段
        cands = seg_grid.query_bbox(x0i, y0i, x1i, y1i, _MATCH_THRESHOLD)
        cands_by_i[i] = cands
        for j in cands:
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
    # 复用 Pass 1 的候选（pad=100mm 超集），_seg_intersection 精确过滤
    for i in range(n):
        x0i, y0i, x1i, y1i = segs[i][0], segs[i][1], segs[i][2], segs[i][3]
        cands = cands_by_i[i]
        for j in cands:
            if j <= i:
                continue
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

    # 端点聚类（近似合并）——用空间网格索引加速最近节点查找
    node_list: List[Tuple[float, float]] = []
    pt_to_node: Dict[Tuple[float, float], int] = {}
    node_grid = _SpatialGrid(_MATCH_THRESHOLD)

    def _find_or_create(x: float, y: float) -> int:
        """查找或创建房间。"""
        key = (x, y)
        if key in pt_to_node:
            return pt_to_node[key]
        # 找最近节点（只查 3×3 邻域 cell，而非全量节点）
        best = -1
        best_d = _MATCH_THRESHOLD**2
        for i in node_grid.query_point(x, y, _MATCH_THRESHOLD):
            nx, ny = node_list[i]
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
        node_grid.insert_point(nid, x, y)
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
            """计算角度键值用于聚类。"""
            nx, ny = nodes[nid_neighbor]
            return math.atan2(ny - cy, nx - cx)

        # 排序
        sorted_neighbors = sorted(neighbors, key=_angle_key)
        # 存储 (nid -> sorted list of neighbors)
        # 同时存储反向查找：从 (prev_nid, nid) 出发，下一邻居
        graph["adj_sorted"] = graph.get("adj_sorted", {})
        graph["adj_sorted"][nid] = sorted_neighbors
        # 位置索引：neighbor -> position，供 _find_faces O(1) 查找替代 index()
        graph["pos_index"] = graph.get("pos_index", {})
        graph["pos_index"][nid] = {
            nb: pos for pos, nb in enumerate(sorted_neighbors)
        }


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
                pos_map = graph["pos_index"].get(current)
                if pos_map is None:
                    break
                pos = pos_map.get(prev)
                if pos is None:
                    break
                # 下一逆时针边：pos - 1（循环）
                neighbors = adj_sorted.get(current, [])
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
            layer = edge_layers[key]
            if _is_non_room_layer(layer):
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


# ── Task 2：房间几何合理性门禁 ─────────────────────────────
# 不允许按面积一刀切：真实展厅/中庭/厂房同样是大面积。
# 只用“几何结构性证据”组合判定，每条判据都可单独复核。
_ROOM_CONTAINER_MIN_AREA_M2 = 50.0  # 容器判据只作用于大空间
_EMPTY_OUTLINE_OPENING_RADIUS_MM = 5000.0  # 空壳轮廓：边界 5m 内无任何可开启洞口
_FRAME_BORDER_PAD_MM = 500.0  # 房间 bbox 贴图框边框容差
_MIN_POLY_TO_BBOX_RATIO = 0.05  # 多边形面积/bbox 面积下限（低于此为坐标错乱）
_DUP_BBOX_IOU = 0.90  # 重复实体判定：bbox IoU
_DUP_AREA_TOL = 0.05  # 重复实体面积相对差
_SPATIAL_CORE_TYPES = {
    "room",
    "corridor",
    "space",
    "hall",
    "lobby",
    "antechamber",
    "staircase",
    "stair",
    "fire_elevator",
    "elevator",
    "elevator_lobby",
    "staircase_lobby",
    "equipment_room",
    "pump_room",
    "toilet",
    "accessible_toilet",
    "storage_room",
}
_OPENING_TYPES = {
    "door",
    "fire_door",
    "exit_door",
    "accessible_door",
    "sliding_door",
    "revolving_door",
    "doorway",
    "opening",
    "window",
    "fire_window",
    "rescue_window",
    "smoke_exhaust_window",
}
# 门洞邻接/回折修复只算真正的门（不含 window/opening）。
# 窗是外墙采光口，不构成房间入口；opening 语义模糊（可能是墙洞），
# 不能作为「房间有入口」的证据，否则看台格间/货架格会被误保留。
_DOOR_ONLY_TYPES: Set[str] = {"door", "fire_door", "exit_door", "accessible_door"}
# 房间名/功能标注关键词：复用 room_type_infer 的规则词表，并补充通用空间名
# （走道/强电间/消防器材室等不在 subtype 推断表内，但同样是功能标注）
_SPACE_LABEL_KEYWORDS: Tuple[str, ...] = (
    "走道",
    "走廊",
    "通道",
    "机房",
    "设备",
    "库房",
    "强电",
    "弱电",
    "消防器材",
    "展厅",
    "中庭",
    "厂房",
    "办公",
    "会议",
    "餐厅",
    "厨房",
    "卫生间",
    "厕所",
    "电梯",
    "楼梯",
    "前室",
    "管井",
    "风井",
    "水井",
    "控制室",
    "配电",
    "发电",
    "空调",
    "风机",
    "消控",
    "仓储",
    "宿舍",
    "病房",
    "教室",
    "阅览",
    "商店",
    "银行",
    "食堂",
    "门厅",
    "大堂",
    "更衣",
    "淋浴",
    "阳台",
    "露台",
)
_ROOM_NAME_KEYWORDS: Tuple[str, ...] = tuple(
    dict.fromkeys(
        [kw for _rule in ROOM_TYPE_RULES for kw in (_rule.get("text_keywords") or [])]
        + list(_SPACE_LABEL_KEYWORDS)
    )
)


def _room_polygon(entity: Any) -> Optional[List[List[float]]]:
    """取房间多边形顶点；无 points 时退化为 bbox 矩形（仅用于门禁判定）。"""
    props = entity.properties or {}
    pts = props.get("points")
    if pts and len(pts) >= 3:
        try:
            return [[float(p[0]), float(p[1])] for p in pts]
        except (TypeError, IndexError, ValueError):
            return None
    b = entity.bbox or {}
    if b.get("width", 0) > 0 and b.get("height", 0) > 0:
        x, y, w, h = b["x"], b["y"], b["width"], b["height"]
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return None


def _poly_area_m2(poly: List[List[float]]) -> float:
    return abs(_signed_area(poly)) / 1_000_000


def _bbox_iou(a: Dict[str, float], b: Dict[str, float]) -> float:
    aw = a.get("width", 0)
    ah = a.get("height", 0)
    bw = b.get("width", 0)
    bh = b.get("height", 0)
    ax0, ay0 = a.get("x", 0), a.get("y", 0)
    bx0, by0 = b.get("x", 0), b.get("y", 0)
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    ox = max(0, min(ax1, bx1) - max(ax0, bx0))
    oy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ox * oy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _point_boundary_distance_mm(
    point: Tuple[float, float], poly: List[List[float]]
) -> float:
    """点到多边形边界的最近距离（mm）。"""
    px, py = point
    best = float("inf")
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        seg2 = dx * dx + dy * dy
        if seg2 <= 0:
            dist = math.hypot(px - x1, py - y1)
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg2))
            dist = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
        if dist < best:
            best = dist
    return best


def _point_bbox_distance_mm(
    point: Tuple[float, float], bbox: Dict[str, float]
) -> float:
    """点到矩形 bbox 边界的最近距离（mm）；点在 bbox 内返回 0。

    用于 E 空壳轮廓判定的快速拒绝：多边形完全包含在 bbox 内，故
    点到多边形边界距离 >= 点到 bbox 边界距离。若点到 bbox 距离 > 阈值，
    则点到多边形边界距离必 > 阈值，可安全跳过精确计算。
    """
    px, py = point
    bx = bbox.get("x", 0)
    by = bbox.get("y", 0)
    bw = bbox.get("width", 0)
    bh = bbox.get("height", 0)
    if bw <= 0 or bh <= 0:
        return 0.0
    bx2 = bx + bw
    by2 = by + bh
    if bx <= px <= bx2 and by <= py <= by2:
        return 0.0
    dx = max(bx - px, 0.0, px - bx2)
    dy = max(by - py, 0.0, py - by2)
    return math.hypot(dx, dy)


def _orient(a: List[float], b: List[float], c: List[float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(
    p1: List[float], p2: List[float], p3: List[float], p4: List[float]
) -> bool:
    """两线段是否相交（含端点接触与共线重叠）。"""
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True

    def _on_seg(a: List[float], b: List[float], c: List[float]) -> bool:
        return (
            min(a[0], b[0]) <= c[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= c[1] <= max(a[1], b[1])
        )

    return (
        (d1 == 0 and _on_seg(p3, p4, p1))
        or (d2 == 0 and _on_seg(p3, p4, p2))
        or (d3 == 0 and _on_seg(p1, p2, p3))
        or (d4 == 0 and _on_seg(p1, p2, p4))
    )


def _is_simple_polygon(pts: List[List[float]]) -> bool:
    """Task 1：多边形是否简单闭合环（无自交/无重合边/无重复顶点接触）。

    面遍历得到的是图上的环，但线段交叉（X 型）未被 _split_t_junctions
    拆分时，环会自交。自交多边形无法用于内切圆/净宽/洞归属等几何计算，
    按“不可用 points”处理。
    """
    n = len(pts)
    if n < 3:
        return False
    # 顶点重复（非闭合点）→ 非简单环
    for i in range(n):
        for j in range(i + 1, n):
            if pts[i][0] == pts[j][0] and pts[i][1] == pts[j][1]:
                return False
    for i in range(n):
        a1, b1 = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            # 相邻边共享端点，跳过；首尾边也相邻
            if (i + 1) % n == j or (j + 1) % n == i:
                continue
            if _segments_intersect(a1, b1, pts[j], pts[(j + 1) % n]):
                return False
    return True


def _fold_spike_covered_by_door(
    p0: List[float], p1: List[float], doors: List[Any], door_grid: Optional[Any] = None
) -> bool:
    """折返尖刺 p0→p1 是否被「折返线上的门」覆盖。

    扫线法在门洞开口处会绕门折返：尖刺是垂直线段（x 恒定）或水平线段
    （y 恒定），且门洞（零宽/零高门）恰好位于该折返线上、跨度与尖刺重叠。
    这类回折是真实房间边界的门洞伪影，应修复保留。

    噪声回折（T 型墙/墙板过提取）的尖刺处没有门洞，不满足此判据。

    性能：door_grid 提供后只查询尖刺 bbox 扩张 1mm 内的候选门（空间索引），
    避免遍历全部 doors（O(n·m)）。无 grid 时回退全量遍历（功能等价）。

    返回 True 表示该尖刺被折返线上的门覆盖。
    """
    dx = abs(p0[0] - p1[0])
    dy = abs(p0[1] - p1[1])
    _EPS = 1.0  # mm — 零宽门浮点误差容差
    if door_grid is not None:
        # 只查询尖刺附近的候选门（尖刺 bbox 扩张 EPS）
        xlo = min(p0[0], p1[0]) - _EPS
        xhi = max(p0[0], p1[0]) + _EPS
        ylo = min(p0[1], p1[1]) - _EPS
        yhi = max(p0[1], p1[1]) + _EPS
        candidates = door_grid.query_bbox(xlo, ylo, xhi, yhi, _EPS)
    else:
        candidates = range(len(doors))
    for di in candidates:
        d = doors[di]
        dtype = getattr(d, "type", None) or (d.get("type") if isinstance(d, dict) else None)
        if dtype not in _DOOR_ONLY_TYPES:
            continue
        dbb = d.bbox if hasattr(d, "bbox") else (d if isinstance(d, dict) else {}) or {}
        dx0, dy0 = dbb.get("x", 0), dbb.get("y", 0)
        dw_v, dh_v = dbb.get("width", 0), dbb.get("height", 0)
        if dw_v <= _EPS and dh_v <= _EPS:
            continue
        dx1, dy1 = dx0 + dw_v, dy0 + dh_v
        if dx <= _EPS:  # 垂直尖刺（x 恒定）
            if abs(dx0 - p0[0]) <= _EPS and abs(dx1 - p0[0]) <= _EPS:
                if min(dy0, dy1) <= max(p0[1], p1[1]) and max(dy0, dy1) >= min(p0[1], p1[1]):
                    return True
        elif dy <= _EPS:  # 水平尖刺（y 恒定）
            if abs(dy0 - p0[1]) <= _EPS and abs(dy1 - p0[1]) <= _EPS:
                if min(dx0, dx1) <= max(p0[0], p1[0]) and max(dx0, dx1) >= min(p0[0], p1[0]):
                    return True
    return False


def _repair_folded_polygon(
    pts: List[List[float]],
    doors: Optional[List[Any]] = None,
    door_grid: Optional[Any] = None,
) -> Optional[List[List[float]]]:
    """修复扫线法产生的回折环（重复顶点 + 来回回折），返回修复后的简单环。

    扫线法在 T 型墙/门洞处会生成「回折」环：顶点序列沿某方向走到头再折回
    （如 (x,y0)→(x,y1)→(x,y0)），产生重复顶点和自交。这类回折是几何噪声，
    不是真实自交（蝴蝶结），修复后应保留真实房间。

    修复策略（迭代）：
      1. 去除相邻重复顶点（pts[i] == pts[i+1]）。
      2. 去除来回回折（pts[i] == pts[i+2]，中间点是被折返的冗余顶点）。

    门洞判据（关键区分点）：真实标准间的回折环由门洞开口引起——**每个**
    折返尖刺都必须被「折返线上的门」覆盖（``_fold_spike_covered_by_door``）。
    噪声回折（T 型墙/墙板过提取）至少有一个尖刺处无门洞，不满足，返回 None。

    返回修复后的顶点列表；若无法修复（点数 < 3、仍自交、或存在未被门洞
    覆盖的尖刺）返回 None。仅当修复后面积与原始面积接近（>90%）才接受，
    避免把真实自交（蝴蝶结，面积远小于 bbox）误修复。
    """
    if not pts or len(pts) < 3:
        return None
    orig_area = abs(_signed_area(pts))
    fixed = [list(p) for p in pts]
    changed = True
    while changed:
        changed = False
        # 去除相邻重复顶点
        i = 0
        while i < len(fixed):
            n = len(fixed)
            if n >= 2 and fixed[i][0] == fixed[(i + 1) % n][0] and fixed[i][1] == fixed[(i + 1) % n][1]:
                del fixed[i]
                changed = True
                continue
            i += 1
        # 去除来回回折 pts[i] == pts[i+2]
        i = 0
        while i < len(fixed):
            n = len(fixed)
            if n >= 3 and fixed[i][0] == fixed[(i + 2) % n][0] and fixed[i][1] == fixed[(i + 2) % n][1]:
                del fixed[(i + 1) % n]
                del fixed[(i + 1) % (n - 1)]
                changed = True
                continue
            i += 1
    if len(fixed) < 3:
        return None
    if not _is_simple_polygon(fixed):
        return None
    # 面积守卫：修复后面积与原始面积接近（>90%）才接受
    fixed_area = abs(_signed_area(fixed))
    if orig_area > 0 and fixed_area / orig_area < 0.90:
        return None
    # bbox 填充守卫：回折环是房间边界上的门洞伪影，修复后应几乎填满 bbox
    # （面积/bbox 面积 ≥ 90%）。真实自交多边形（蝴蝶结/复杂轮廓，如 plans
    # ROOM_317 面积比 0.075）即使有门洞覆盖的尖刺，修复后仍远小于 bbox，
    # 不应修复。Villa 9049 回折环面积比 0.984，保留。
    _xs = [p[0] for p in fixed]
    _ys = [p[1] for p in fixed]
    _bbox_area = (max(_xs) - min(_xs)) * (max(_ys) - min(_ys))
    if _bbox_area > 0 and fixed_area / _bbox_area < 0.90:
        return None
    # 门洞判据：每个折返尖刺都必须被折返线上的门覆盖。
    # 真实标准间（如 Villa 9049）的回折由门洞开口引起，尖刺处有门；
    # 噪声回折（T 型墙/墙板过提取）至少一个尖刺处无门，不修复。
    if doors is not None:
        for i in range(len(pts)):
            if (
                pts[i][0] == pts[(i + 2) % len(pts)][0]
                and pts[i][1] == pts[(i + 2) % len(pts)][1]
            ):
                if not _fold_spike_covered_by_door(pts[i], pts[(i + 1) % len(pts)], doors, door_grid):
                    return None
    return fixed


def _room_source_rank(entity_id: str) -> int:
    """重复房间实体取舍：显式图元 > 直接闭合多段线 > 面遍历派生。"""
    if entity_id.startswith("ROOM_"):
        return 0
    if entity_id.startswith("polyline_"):
        return 1
    if entity_id.startswith("line_chain_"):
        return 2
    return 3


def _detect_grid_pattern_suppressions(
    room_ids: Set[str],
    bbox_by_id: Dict[str, Dict[str, float]],
    poly_by_id: Dict[str, List[List[float]]],
    doors: List[Any],
    texts: List[Any],
) -> Dict[str, Dict[str, Any]]:
    """P121-V 扩展：检测 sweep 派生格子阵列（看台/货架/图例表）。

    判据：
      1. 只针对 line_chain_* 派生的房间实体（非显式分类）。
      2. 同组内所有实体尺寸几乎相同（宽高各自容差 < GRID_DIM_TOL = 5%）。
      3. 同组实体 ≥ GRID_MIN_COUNT = 3 个。
      4. 质心沿单一方向等距排列（间距变异系数 < GRID_SPACING_CV = 0.5）。
      5. 单格面积 ≤ GRID_AREA_MAX_M2 = 50㎡（大空间网格不计入）。
      6. 组内无实体带门洞邻接或文字标注（若有 → 真实标准间，不抑制）。

    注意第 6 条是关键区分点：真实标准间（酒店客房、病房）虽然也同质等距排列，
    但通常有门或文字标注作为辅助证据；看台格间/图例表完全没有这些特征。

    返回值：{entity_id: suppression_record}
    """
    from collections import defaultdict as _defaultdict

    # 预构建空间索引：doors 按 bbox 对角线路径插入（覆盖其跨度），
    # texts 按中心点插入。避免每个候选房间遍历全部 doors/texts（O(n·m)）。
    door_grid = _SpatialGrid(_MATCH_THRESHOLD)
    door_list: List[Tuple[float, float, float, float]] = []  # (x0,y0,x1,y1)
    for d in doors:
        dtype = getattr(d, "type", None) or (d.get("type") if isinstance(d, dict) else None)
        if dtype not in _DOOR_ONLY_TYPES:
            continue
        dbb = d.bbox if hasattr(d, "bbox") else (d if isinstance(d, dict) else {}) or {}
        dx, dy = dbb.get("x", 0), dbb.get("y", 0)
        dw_v, dh_v = dbb.get("width", 0), dbb.get("height", 0)
        # 只跳过完全退化的门（宽高均为 0）。零宽度/零高度门是真实门洞
        # （竖直线段/水平线段代表门），必须纳入邻接判定，否则 Villa 等
        # 真实标准间因门 bbox 零宽被误判为"无门洞邻接"而被 grid_pattern 误伤。
        if dw_v <= 0 and dh_v <= 0:
            continue
        door_list.append((dx, dy, dx + dw_v, dy + dh_v))
        door_grid.insert_segment(len(door_list) - 1, dx, dy, dx + dw_v, dy + dh_v)

    text_grid = _SpatialGrid(_MATCH_THRESHOLD)
    text_list: List[Tuple[float, float]] = []  # (cx, cy)
    for t in texts:
        tb = t.bbox if hasattr(t, "bbox") else (t if isinstance(t, dict) else {}) or {}
        tx = tb.get("x", 0) + tb.get("width", 0) / 2
        ty = tb.get("y", 0) + tb.get("height", 0) / 2
        text_list.append((tx, ty))
        text_grid.insert_point(len(text_list) - 1, tx, ty)

    # Helper: check if an entity bbox has nearby door or text
    def _has_adjacent_context(eid: str) -> bool:
        bb = bbox_by_id.get(eid) or {}
        cx = bb.get("x", 0) + bb.get("width", 0) / 2
        cy = bb.get("y", 0) + bb.get("height", 0) / 2
        w, h = bb.get("width", 0), bb.get("height", 0)
        rbx0, rby0 = bb.get("x", 0), bb.get("y", 0)
        rbx1, rby1 = rbx0 + w, rby0 + h
        # Door adjacency: ONLY count actual doors (not windows/openings)
        # 用空间索引查房间 bbox 扩张 1 个 cell 内的候选门洞，再精确双轴重叠
        short_side = min(w, h) if w > 0 and h > 0 else 0
        for di in door_grid.query_bbox(rbx0, rby0, rbx1, rby1, _MATCH_THRESHOLD):
            dbx0, dby0, dbx1, dby1 = door_list[di]
            dw = dbx1 - dbx0
            dh = dby1 - dby0
            ox = max(0, min(rbx1, dbx1) - max(rbx0, dbx0))
            oy = max(0, min(rby1, dby1) - max(rby0, dby0))
            # 需双轴均有实质重叠才算邻接：单轴投影重叠不足以说明门洞与该房间相邻
            # （例如看台格间横向与远处门洞投影重合时不应误判）。
            # 阈值取房间短边的一半，确保重叠区域至少覆盖半个房间宽度/高度。
            if (ox > short_side / 2) and (oy > short_side / 2):
                return True
            # 零宽度/零高度门（竖直线段/水平线段代表门洞）：双轴判据中
            # ox 或 oy 恒为 0，需用"门线段与房间 bbox 相交"判定。
            # 零宽度门（dw==0）：门 x 坐标在房间 x 范围内（含边界，无容差），
            # 且 y 方向与房间有交集（oy>0）。门 x 在房间范围内 ⟹ 门在房间边界上。
            # 远处门（如看台格间 75mm 外的门 x=44451 < 格间 x0=44526）因
            # x 不在房间范围内不会误判。
            if dw == 0 and dh > 0:
                if rbx0 <= dbx0 <= rbx1 and oy > 0:
                    return True
            elif dh == 0 and dw > 0:
                if rby0 <= dby0 <= rby1 and ox > 0:
                    return True
        # Text label within 2.5m
        for ti in text_grid.query_point(cx, cy, 2500):
            tx, ty = text_list[ti]
            if abs(tx - cx) < 2500 and abs(ty - cy) < 2500:
                return True
        return False

    # Build sorted list of grid candidates (only line_chain_ rooms without context)
    import sys as _sys
    candidates: List[Tuple[str, float, float, float, float, float]] = []
    _ctx_count, _no_ctx_count = 0, 0
    _area_skip = 0
    _dims_skip = 0
    _lc_total = 0
    for eid in room_ids:
        if not eid.startswith("line_chain_"):
            continue
        _lc_total += 1
        bb = bbox_by_id.get(eid) or {}
        area_m2 = (bb.get("width", 0) * bb.get("height", 0)) / 1_000_000
        if area_m2 > _GRID_AREA_MAX_M2:
            _area_skip += 1
            continue
        w = bb.get("width", 0)
        h = bb.get("height", 0)
        if w <= 0 or h <= 0:
            _dims_skip += 1
            continue
        cx = bb.get("x", 0) + w / 2
        cy = bb.get("y", 0) + h / 2
        has_ctx = _has_adjacent_context(eid)
        if has_ctx:
            _ctx_count += 1
            continue
        _no_ctx_count += 1
        candidates.append((eid, w, h, cx, cy, area_m2))

    if len(candidates) < _GRID_MIN_COUNT:
        return {}

    # Group by rounded size bucket (100mm tolerance for initial grouping)
    size_groups = _defaultdict(list)
    for item in candidates:
        eid, w, h, cx, cy, area = item
        bw = round(w / 100) * 100
        bh = round(h / 100) * 100
        size_groups[(bw, bh)].append(item)

    suppressed: Dict[str, Dict[str, Any]] = {}
    for (bw, bh), group in size_groups.items():
        if len(group) < _GRID_MIN_COUNT:
            continue
        # Check dimension homogeneity (5%)
        ws = [g[1] for g in group]
        hs = [g[2] for g in group]
        avg_w = sum(ws) / len(ws)
        avg_h = sum(hs) / len(hs)
        if avg_w <= 0 or avg_h <= 0:
            continue
        w_var = max(abs(w - avg_w) / avg_w for w in ws)
        h_var = max(abs(h - avg_h) / avg_h for h in hs)
        if w_var > _GRID_DIM_TOL or h_var > _GRID_DIM_TOL:
            continue

        # Check alignment: primary direction
        cx_list = [g[3] for g in group]
        cy_list = [g[4] for g in group]
        x_range = max(cx_list) - min(cx_list)
        y_range = max(cy_list) - min(cy_list)

        if y_range >= x_range and y_range > 500:
            coords = sorted(cy_list)
            direction = "vertical"
        elif x_range > 500:
            coords = sorted(cx_list)
            direction = "horizontal"
        else:
            continue  # compact cluster — not a grid pattern

        # Check spacing regularity
        spacings = [coords[i + 1] - coords[i] for i in range(len(coords) - 1)]
        if not spacings or min(spacings) < 200:
            continue
        avg_sp = sum(spacings) / len(spacings)
        if avg_sp <= 0:
            continue
        cv = max(abs(s - avg_sp) / avg_sp for s in spacings)
        if cv > _GRID_SPACING_CV:
            continue  # spacing too irregular

        # Suppress all members of this grid group
        for item in group:
            eid = item[0]
            if eid in suppressed:
                continue
            suppressed[eid] = {
                "id": eid,
                "type": "room",
                "action": "suppressed",
                "bbox": bbox_by_id.get(eid, {}),
                "reasons": ["grid_pattern"],
                "evidence": {
                    "group_size": len(group),
                    "avg_width_mm": round(avg_w),
                    "avg_height_mm": round(avg_h),
                    "spacing_avg_mm": round(avg_sp),
                    "spacing_cv": round(cv, 3),
                    "direction": direction,
                },
            }

    return suppressed


def _suppress_implausible_rooms(
    entities: List[Any], primitives: Optional[List[RawPrimitive]] = None
) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Task 2：剔除几何上不成立的 room/corridor 实体，并返回逐条判定证据。

    判据组合（均为结构性证据，不按面积一刀切）：
      A 退化多边形：多边形面积/bbox 面积 < 5%（坐标错乱、构件/图框误判）
      B 未闭合边界：closed 不为 True 且顶点 < 4（P131 的三角形兜底面）
      C 重复实体：与另一 room 的 bbox IoU ≥ 0.90 且面积相近，只保留权威来源
      D 容器/整层轮廓：大空间内部包含 ≥2 个空间实体，或 ≥1 个空间实体+房间名，
        或 ≥2 个不同房间名文本（整层轮廓/防火分区/图框包含多个房间）
      E 空壳轮廓：大空间内部无任何空间实体、无房间名，且边界 5m 内无洞口
      F 贴图框：房间 bbox 与图框边框重合（titleblock 误判）
      G 自交多边形：边界自交/重合/重复顶点，无法用于内切、净宽、洞归属计算

    不变量：room/corridor 实体必须带可用 points。构造期未落盘者按 bbox 矩形补全
    （points_source=bbox_rect）；bbox 也无效者降级为 other，不以 room 名义无几何存在。
    """
    rooms: List[Any] = []
    downgraded: Dict[str, Dict[str, Any]] = {}
    for e in entities:
        if getattr(e, "type", None) not in ("room", "corridor"):
            continue
        props = e.properties if isinstance(e.properties, dict) else {}
        if not isinstance(e.properties, dict):
            e.properties = props
        if props.get("points") and _room_polygon(e) is not None:
            rooms.append(e)
            continue
        # Task 1 不变量：room 实体必须带可用 points。三条构造路径已在构造期统一
        # 落盘；此处兜底处理非构造路径（图层分类/合并）产生的无 points room：
        # bbox 有效的按矩形补全（points_source=bbox_rect），bbox 无效的降级为
        # other —— 不得以 room 名义存在却没有几何。
        b = e.bbox or {}
        bx, by = b.get("x", 0), b.get("y", 0)
        bw, bh = b.get("width", 0), b.get("height", 0)
        rect = _polygon_props(
            [[bx, by], [bx + bw, by], [bx + bw, by + bh], [bx, by + bh]]
        )
        if bw > 0 and bh > 0 and rect and _poly_area_m2(rect["points"]) > 0:
            props.update(rect)
            props["points_source"] = "bbox_rect"
            rooms.append(e)
            continue
        e.type = "other"
        downgraded[e.id] = {
            "id": e.id,
            "type": "room",
            "action": "downgraded",
            "bbox": dict(b),
            "reasons": ["missing_polygon"],
            "evidence": {},
        }
    if not rooms:
        return entities, sorted(
            downgraded.values(),
            key=lambda r: -(r["bbox"].get("width", 0) * r["bbox"].get("height", 0)),
        )

    suppressed: Dict[str, Dict[str, Any]] = {}
    poly_by_id = {e.id: _room_polygon(e) for e in rooms}
    bbox_by_id = {e.id: (e.bbox or {}) for e in rooms}
    # C 重复实体判定预计算 bbox 面积：IoU > 0.90 ⟹ max/min < 1/0.90 ≈ 1.111，
    # 面积差更大时 IoU 必 <= 0.90，可跳过 _bbox_iou 精确计算。
    bbox_area_by_id: Dict[str, float] = {}
    for _rid, _rb in bbox_by_id.items():
        _rw = _rb.get("width", 0)
        _rh = _rb.get("height", 0)
        bbox_area_by_id[_rid] = _rw * _rh if _rw > 0 and _rh > 0 else 0.0
    texts = [e for e in entities if getattr(e, "type", None) == "text"]
    spatial = [
        e
        for e in entities
        if getattr(e, "type", None) in _SPATIAL_CORE_TYPES
        and getattr(e, "id", "") not in ("", None)
    ]
    openings = [e for e in entities if getattr(e, "type", None) in _OPENING_TYPES]
    # E 空壳轮廓判定空间网格：openings 中心点索引，只查询大空间 bbox 扩张
    # 5m 内的 openings，避免遍历全部 11169 个。实测 dongguan 10 个大空间 ×
    # 11169 openings = 111690 次检查，空间索引后只查附近 openings。
    opening_grid = _SpatialGrid(_EMPTY_OUTLINE_OPENING_RADIUS_MM)
    for _op_idx, _op in enumerate(openings):
        _ob = _op.bbox or {}
        _cx = _ob.get("x", 0) + _ob.get("width", 0) / 2
        _cy = _ob.get("y", 0) + _ob.get("height", 0) / 2
        opening_grid.insert_point(_op_idx, _cx, _cy)
    frames: List[Dict[str, float]] = (
        _detect_frame_rects(primitives, []) if primitives else []
    )

    # H 格子阵列检测（看台/货架/图例表等周期性栅格）：在 A/B/C/D/E/F/G 常规门禁
    # 之前先跑一次，避免同质栅格的每个成员单独过后续规则造成重复记录。
    room_ids_set: Set[str] = {e.id for e in rooms}
    door_entities = [e for e in entities if getattr(e, "type", None) in _OPENING_TYPES]
    texts_list = [e for e in entities if getattr(e, "type", None) == "text"]
    grid_suppressions = _detect_grid_pattern_suppressions(
        room_ids_set, bbox_by_id, poly_by_id, door_entities, texts_list
    )
    suppressed.update(grid_suppressions)

    # 回折修复门洞判据空间网格：door 按 bbox 对角线插入，_fold_spike_covered_by_door
    # 只查询尖刺附近的候选门，避免遍历全部 doors（O(n·m)）。
    door_grid = _SpatialGrid(_MATCH_THRESHOLD)
    for _d_idx, _d in enumerate(door_entities):
        _db = _d.bbox if hasattr(_d, "bbox") else (_d if isinstance(_d, dict) else {}) or {}
        _dx0, _dy0 = _db.get("x", 0), _db.get("y", 0)
        _dw, _dh = _db.get("width", 0), _db.get("height", 0)
        if _dw <= 0 and _dh <= 0:
            continue
        door_grid.insert_segment(_d_idx, _dx0, _dy0, _dx0 + _dw, _dy0 + _dh)

    def _record(entity: Any, reason: str, evidence: Dict[str, Any]) -> None:
        rec = suppressed.setdefault(
            entity.id,
            {
                "id": entity.id,
                "type": getattr(entity, "type", ""),
                "action": "suppressed",
                "bbox": dict(entity.bbox or {}),
                "reasons": [],
                "evidence": {},
            },
        )
        rec["reasons"].append(reason)
        rec["evidence"].update(evidence)

    for ent in rooms:
        if ent.id in suppressed:
            continue
        poly = poly_by_id[ent.id]
        b = bbox_by_id[ent.id]
        bbox_area_m2 = (b.get("width", 0) * b.get("height", 0)) / 1_000_000
        poly_area_m2 = _poly_area_m2(poly) if poly else 0.0
        props = ent.properties or {}

        # A 退化多边形
        if bbox_area_m2 > 0 and poly_area_m2 / bbox_area_m2 < _MIN_POLY_TO_BBOX_RATIO:
            _record(
                ent,
                "degenerate_polygon",
                {"poly_area_m2": round(poly_area_m2, 3), "bbox_area_m2": round(bbox_area_m2, 2)},
            )
            continue

        # G 自交多边形：几何上不可用（内部计算需要简单闭合环）
        if not _is_simple_polygon(poly):
            # 回折修复：扫线法在 T 型墙/门洞处产生回折环（重复顶点+自交），
            # 是几何噪声而非真实自交。仅当每个折返尖刺都被「折返线上的门」
            # 覆盖（真实标准间如 Villa 9049 的门洞伪影）且修复后简单、面积
            # 接近（>90%）才保留，避免误伤真实标准间，也避免把噪声回折
            # （T 型墙/墙板过提取，尖刺处无门）误修复。
            repaired = _repair_folded_polygon(poly, doors=door_entities, door_grid=door_grid)
            if repaired is not None:
                props["points"] = repaired
                props["point_count"] = len(repaired)
                poly = repaired
                poly_area_m2 = _poly_area_m2(poly)
                # 更新 poly_by_id 供后续门禁使用
                poly_by_id[ent.id] = poly
            else:
                _record(
                    ent,
                    "self_intersecting_polygon",
                    {
                        "point_count": len(poly),
                        "area_m2": round(poly_area_m2, 3),
                    },
                )
                continue

        # B 未闭合边界（顶点不足 4 的 P131 兜底面）
        # 只对大面积使用：小面积 3 点面可能是真实小房间（墙体检测缺口），
        # 直接剔除会丢失真实房间；大面积 3 点面是整层轮廓/构件未合龙的兜底产物。
        try:
            point_count = int(props.get("point_count") or len(poly or []))
        except (TypeError, ValueError):
            point_count = len(poly or [])
        if (
            props.get("closed") is not True
            and point_count < 4
            and bbox_area_m2 >= _ROOM_CONTAINER_MIN_AREA_M2
        ):
            _record(ent, "unclosed_polygon", {"point_count": point_count})
            continue

        # F 贴图框
        for fr in frames:
            fx0, fy0 = fr["x"], fr["y"]
            fx1, fy1 = fx0 + fr["width"], fy0 + fr["height"]
            bx0, by0 = b.get("x", 0), b.get("y", 0)
            bx1, by1 = bx0 + b.get("width", 0), by0 + b.get("height", 0)
            if (
                min(bx1, fx1) - max(bx0, fx0) > -_FRAME_BORDER_PAD_MM
                and min(by1, fy1) - max(by0, fy0) > -_FRAME_BORDER_PAD_MM
                and min(
                    abs(bx0 - fx0), abs(bx1 - fx1), abs(by0 - fy0), abs(by1 - fy1)
                )
                <= _FRAME_BORDER_PAD_MM
            ):
                _record(ent, "titleblock_frame", {"frame": dict(fr)})
                break
        if ent.id in suppressed:
            continue

        # C 重复实体（同一物理空间重复建模）
        for other in rooms:
            if other.id == ent.id or other.id in suppressed:
                continue
            # 面积预过滤：IoU > _DUP_BBOX_IOU ⟹ max/min < 1/_DUP_BBOX_IOU。
            # 面积差更大时 IoU 必 <= 阈值，跳过 _bbox_iou 精确计算。
            # bbox_area_m2 单位 m²，bbox_area_by_id 单位 mm²，统一到 m²。
            _oa = bbox_area_by_id.get(other.id, 0.0) / 1_000_000
            if _oa > 0 and bbox_area_m2 > 0:
                if max(bbox_area_m2, _oa) / min(bbox_area_m2, _oa) > 1.0 / _DUP_BBOX_IOU:
                    continue
            ob = bbox_by_id[other.id]
            if _bbox_iou(b, ob) < _DUP_BBOX_IOU:
                continue
            oa = _poly_area_m2(poly_by_id[other.id] or [])
            if oa > 0 and abs(poly_area_m2 - oa) / max(poly_area_m2, oa) > _DUP_AREA_TOL:
                continue
            # 仅在“本源 vs 派生”可区分时去重；两条派生路径都保留（交给 D/E）
            r_self = _room_source_rank(ent.id)
            r_other = _room_source_rank(other.id)
            if r_self == r_other:
                continue
            loser, keeper = (ent, other) if r_self > r_other else (other, ent)
            _record(
                loser,
                "duplicate_entity",
                {"duplicate_of": keeper.id, "bbox_iou": round(_bbox_iou(b, ob), 3)},
            )
        if ent.id in suppressed:
            continue

        # D/E 只作用于大空间
        if bbox_area_m2 < _ROOM_CONTAINER_MIN_AREA_M2:
            continue
        core_inside = 0
        labels: Set[str] = set()
        for o in spatial:
            if o.id == ent.id:
                continue
            ob = o.bbox or {}
            center = (
                ob.get("x", 0) + ob.get("width", 0) / 2,
                ob.get("y", 0) + ob.get("height", 0) / 2,
            )
            if _point_in_polygon(center, poly):
                core_inside += 1
        for t in texts:
            tb = t.bbox or {}
            center = (
                tb.get("x", 0) + tb.get("width", 0) / 2,
                tb.get("y", 0) + tb.get("height", 0) / 2,
            )
            if not _point_in_polygon(center, poly):
                continue
            text = str((t.properties or {}).get("text") or "").strip()
            if text and any(kw.lower() in text.lower() for kw in _ROOM_NAME_KEYWORDS):
                labels.add(text)
        if core_inside >= 2 or len(labels) >= 2 or (core_inside >= 1 and len(labels) >= 1):
            _record(
                ent,
                "room_container",
                {
                    "core_entities_inside": core_inside,
                    "room_name_labels": sorted(labels)[:5],
                    "area_m2": round(bbox_area_m2, 1),
                },
            )
            continue
        # E 空壳轮廓：内部无空间实体、无房间名，且边界 5m 内没有任何洞口
        nearest_opening = None
        # 只查询大空间 bbox 扩张 5m 内的 openings（空间网格索引）
        for _op_idx in opening_grid.query_bbox(
            b.get("x", 0),
            b.get("y", 0),
            b.get("x", 0) + b.get("width", 0),
            b.get("y", 0) + b.get("height", 0),
            _EMPTY_OUTLINE_OPENING_RADIUS_MM,
        ):
            op = openings[_op_idx]
            ob = op.bbox or {}
            center = (
                ob.get("x", 0) + ob.get("width", 0) / 2,
                ob.get("y", 0) + ob.get("height", 0) / 2,
            )
            # 快速拒绝：点到 bbox 距离 > 阈值 ⟹ 点到多边形边界距离必 > 阈值
            # （多边形完全包含在 bbox 内）。避免对远处 opening 做精确计算。
            if _point_bbox_distance_mm(center, b) > _EMPTY_OUTLINE_OPENING_RADIUS_MM:
                continue
            dist = _point_boundary_distance_mm(center, poly)
            if nearest_opening is None or dist < nearest_opening:
                nearest_opening = dist
        if (
            core_inside == 0
            and not labels
            and (nearest_opening is None or nearest_opening > _EMPTY_OUTLINE_OPENING_RADIUS_MM)
        ):
            _record(
                ent,
                "empty_outline",
                {
                    "area_m2": round(bbox_area_m2, 1),
                    "nearest_opening_mm": None
                    if nearest_opening is None
                    else round(nearest_opening, 1),
                },
            )

    kept = [e for e in entities if getattr(e, "id", None) not in suppressed]
    log = sorted(
        list(suppressed.values()) + list(downgraded.values()),
        key=lambda r: -(r["bbox"].get("width", 0) * r["bbox"].get("height", 0)),
    )
    return kept, log



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
    seen_centers: Set[Tuple[int, int]] = set()

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
        # P104: 面积过滤
        if area < _MIN_ROOM_AREA_MM2 or area > _MAX_ROOM_AREA_MM2:
            continue

        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        if bw <= 0 or bh <= 0:
            continue
        # P104: 短边过滤
        if min(bw, bh) < _MIN_SHORT_EDGE_MM:
            continue
        aspect = max(bw, bh) / min(bw, bh)
        if aspect > 8.0:
            continue

        # P104: 实际面积/包围盒面积比
        bbox_area = bw * bh
        if bbox_area > 0 and (area / bbox_area) < _MIN_AREA_TO_BBOX_RATIO:
            continue

        bbox = {"x": min(xs), "y": min(ys), "width": bw, "height": bh}
        # P104: bbox 重叠去重
        is_dup = False
        for existing in poly_rooms:
            eb = existing.bbox
            ox = max(
                0, min(bbox["x"] + bbox["width"], eb["x"] + eb["width"]) - max(bbox["x"], eb["x"])
            )
            oy = max(
                0, min(bbox["y"] + bbox["height"], eb["y"] + eb["height"]) - max(bbox["y"], eb["y"])
            )
            if ox <= 0 or oy <= 0:
                continue
            overlap = ox * oy / (bbox["width"] * bbox["height"])
            if overlap > 0.8:
                is_dup = True
                break
        if is_dup:
            continue

        # P105: 面分类
        face_type = _classify_face(bw, bh, area / 1_000_000)
        room_id = f"polyline_{face_type}_{self._entity_counter}"
        self._entity_counter += 1
        props = {"area": area / 1_000_000, "_area_source": "closed_polyline"}
        props.update(_polygon_props(pts))
        if face_type == "corridor":
            props["clear_width"] = min(bw, bh) * 0.001
            props["length"] = max(bw, bh) * 0.001
        poly_rooms.append(
            SemanticEntity(
                entity_id=room_id,
                entity_type=face_type,
                layer="",
                properties=props,
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
