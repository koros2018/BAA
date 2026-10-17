"""天正 T3 原生识别器（P127-T3）。

实测真实 T3 导出 DXF（AC1032/gbk）形态：
- 天正自定义对象已在导出时分解为标准实体（无 PROXY_ENTITY），AppID 含 ``_TCH``；
- 构件遵循天正约定图层（精确大写名）：``WALL``（墙双线）、``WINDOW``
  （窗线 + 天正门/窗库 INSERT + WINDOW_TEXT）、``COLUMN``（柱 INSERT，块名
  如 ``_FZH/_FZHK``，并非 CIRCLE）、``AXIS``、``STAIR``；
- 门 = ``$DorLib2D$*`` 库块 INSERT（挂 WINDOW 图层，因此旧管线按图层错分为 window）；
- 窗 = ``$WINLIB2D$*`` 库块 INSERT，或 WINDOW 图层的四线符号线簇（门联窗侧亮）；
- 一张 DWG 常含多个视图（平面 + 立面/剖面/大样），F1/分类必须限定平面区域。

本模块不做光栅化、不展平块（INSERT 保留块名/旋转），输出纯 dict 实例：
``{status, regions, walls, doors, windows, columns}``，供：
1. ``DrawingParser`` 挂到 ``DrawingResult.t3_components`` / ``parse_status``；
2. 语义分类按 handle 覆盖图层误判（门/柱）并把窗线合并为单实例；
3. T3 验收工具按坐标计算 F1。

解析状态铁律：T3 特征命中但解出 0 构件时必须给出 ``diagnostic``，不得静默。
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ── 常量（单位：mm）────────────────────────────────────────

TCH_APPID = "_TCH"

# 天正平面约定图层（精确大写名；同时兼容 "$0$" 后缀的非标导出名）
SIGNATURE_LAYERS = ("WALL", "WINDOW", "COLUMN", "AXIS", "STAIR")
LAYER_WALL = "WALL"
LAYER_WINDOW = "WINDOW"
LAYER_COLUMN = "COLUMN"

DOOR_BLOCK_PREFIX = "$DORLIB2D"
WINDOW_BLOCK_PREFIX = "$WINLIB2D"
COLUMN_BLOCK_PREFIXES = ("_FZH", "_FZK")

VIEW_GAP = 2000.0            # 平面视图聚类膨胀间隙（仅 WALL/COLUMN/门窗核心实体）
WALL_MIN_LEN = 300.0         # 最短墙段
WALL_FACE_MIN_GAP = 60.0     # 双墙线最小间距
WALL_FACE_MAX_GAP = 600.0    # 双墙线最大间距
WALL_FACE_MERGE_GAP = 80.0   # 同面墙共线合并间隙
WALL_PAIR_MIN_OVERLAP = 0.5  # 双面墙重叠率阈值
WINDOW_CLUSTER_GAP = 150.0   # 窗线聚类间隙
WINDOW_MIN_LONG = 350.0      # 窗洞最小长边
WINDOW_MAX_LONG = 4000.0     # 窗洞最大长边
WINDOW_MAX_SHORT = 800.0     # 窗符号最大短边
WINDOW_WALL_NEAR = 600.0     # 窗中心到墙面的最大距离
COLUMN_MIN_R = 50.0
COLUMN_MAX_R = 1000.0

REGION_MIN_AREA = 8.0         # m²
REGION_MAX_AREA = 50000.0
REGION_MAX_ASPECT = 10.0
REGION_MIN_WALL_SEGS = 8


# ── 基础工具 ────────────────────────────────────────────────


def layer_tail(layer: Optional[str]) -> str:
    """取天正图层尾段大写名。

    常规导出为精确名 ``WALL``；非标导出可能带 ``$0$`` 分段，取最后一段。
    """
    if not layer:
        return ""
    name = str(layer).upper()
    if "$0$" in name:
        name = name.rsplit("$0$", 1)[-1]
    return name


def _segments_of(entity) -> List[Tuple[float, float, float, float]]:
    """把 LINE/LWPOLYLINE/POLYLINE 拆为轴对齐候选线段（不展开 INSERT）。"""
    t = entity.dxftype()
    out: List[Tuple[float, float, float, float]] = []
    try:
        if t == "LINE":
            s, e = entity.dxf.start, entity.dxf.end
            out.append((float(s.x), float(s.y), float(e.x), float(e.y)))
        elif t == "LWPOLYLINE":
            pts = [(float(x), float(y)) for x, y, *_ in entity.get_points("xy")]
            if entity.closed and len(pts) >= 3:
                pts.append(pts[0])
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                out.append((x1, y1, x2, y2))
        elif t == "POLYLINE":
            pts = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices]
            if entity.is_closed and len(pts) >= 3:
                pts.append(pts[0])
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                out.append((x1, y1, x2, y2))
    except Exception:
        return []
    return out


def _axis_aligned(x1: float, y1: float, x2: float, y2: float, tol: float = 1.0) -> int:
    """返回 0=水平, 1=竖直, -1=非轴对齐（端点容差 1mm）。"""
    if abs(y1 - y2) <= tol and abs(x2 - x1) >= 1.0:
        return 0
    if abs(x1 - x2) <= tol and abs(y2 - y1) >= 1.0:
        return 1
    return -1


def _bbox_items(items: Sequence[dict]) -> Tuple[float, float, float, float]:
    x0 = min(i["bbox"][0] for i in items)
    y0 = min(i["bbox"][1] for i in items)
    x1 = max(i["bbox"][2] for i in items)
    y1 = max(i["bbox"][3] for i in items)
    return x0, y0, x1, y1


class _DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _cluster_bbox(items: Sequence[dict], gap: float) -> List[List[int]]:
    """按膨胀 bbox 碰撞做并查集聚类（网格分桶，避免大图 O(n²)）。"""
    n = len(items)
    dsu = _DSU(n)
    cell = gap
    buckets: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for idx, it in enumerate(items):
        x0, y0, x1, y1 = it["bbox"]
        cx0 = int(math.floor((x0 - gap) / cell))
        cy0 = int(math.floor((y0 - gap) / cell))
        cx1 = int(math.floor((x1 + gap) / cell))
        cy1 = int(math.floor((y1 + gap) / cell))
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                key = (cx, cy)
                for other in buckets[key]:
                    dsu.union(idx, other)
                buckets[key].append(idx)
    groups: Dict[int, List[int]] = defaultdict(list)
    for idx in range(n):
        groups[dsu.find(idx)].append(idx)
    return list(groups.values())


def _point_seg_dist(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    denom = dx * dx + dy * dy
    if denom <= 1e-9:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / denom
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


# ── 实体采集 ────────────────────────────────────────────────


def _collect_items(msp) -> List[dict]:
    """遍历模型空间一次，采集聚类/构件所需的轻量条目。

    item 形态：
      seg:    {"kind":"seg","bbox":(x0,y0,x1,y1),"layer":tail,"handle","p1","p2",
               "axis":0|1|-1}
      insert: {"kind":"insert","bbox":点 bbox,"layer","handle","block","x","y","rot"}
      circle: {"kind":"circle","bbox","layer","handle","x","y","r"}
    """
    items: List[dict] = []
    for e in msp:
        t = e.dxftype()
        handle = e.dxf.handle
        try:
            if t in ("LINE", "LWPOLYLINE", "POLYLINE"):
                tail = layer_tail(e.dxf.layer)
                for x1, y1, x2, y2 in _segments_of(e):
                    items.append(
                        {
                            "kind": "seg",
                            "bbox": (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)),
                            "layer": tail,
                            "handle": handle,
                            "p1": (x1, y1),
                            "p2": (x2, y2),
                            "axis": _axis_aligned(x1, y1, x2, y2),
                        }
                    )
            elif t == "INSERT":
                p = e.dxf.insert
                items.append(
                    {
                        "kind": "insert",
                        "bbox": (float(p.x), float(p.y), float(p.x), float(p.y)),
                        "layer": layer_tail(e.dxf.layer),
                        "handle": handle,
                        "block": str(e.dxf.name or ""),
                        "x": float(p.x),
                        "y": float(p.y),
                        "rot": float(getattr(e.dxf, "rotation", 0.0) or 0.0),
                        "sx": float(getattr(e.dxf, "xscale", 1.0) or 1.0),
                        "sy": float(getattr(e.dxf, "yscale", 1.0) or 1.0),
                    }
                )
            elif t == "CIRCLE":
                c, r = e.dxf.center, float(e.dxf.radius)
                items.append(
                    {
                        "kind": "circle",
                        "bbox": (c.x - r, c.y - r, c.x + r, c.y + r),
                        "layer": layer_tail(e.dxf.layer),
                        "handle": handle,
                        "x": float(c.x),
                        "y": float(c.y),
                        "r": r,
                    }
                )
        except Exception:
            continue
    return items


def _has_tch_appid(doc) -> bool:
    try:
        for appid in doc.appids:
            if str(appid.dxf.name).upper() == TCH_APPID:
                return True
    except Exception:
        pass
    return False


def _signature_counts(doc) -> Dict[str, int]:
    """统计天正约定图层是否存在（图层表命中即可，不扫实体）。"""
    hits = {name: 0 for name in SIGNATURE_LAYERS}
    try:
        present = {layer_tail(layer.dxf.name) for layer in doc.layers}
    except Exception:
        return hits
    for name in SIGNATURE_LAYERS:
        if name in present:
            hits[name] = 1
    return hits


def detect_t3_signature(doc) -> Dict[str, Any]:
    """廉价探测（图层表 + AppID），决定是否运行完整识别。"""
    layer_hits = _signature_counts(doc)
    has_appid = _has_tch_appid(doc)
    n_layers = sum(1 for v in layer_hits.values() if v)
    is_t3 = has_appid or n_layers >= 2
    return {
        "is_t3": bool(is_t3),
        "appid_tch": bool(has_appid),
        "signature_layers": layer_hits,
        "signature_layer_count": n_layers,
    }


# ── 视图/平面区域检测 ───────────────────────────────────────


def _is_core_item(it: dict) -> bool:
    """平面视图聚类只用墙/柱/门窗核心实体。

    排除 AXIS（轴号大幅外扩 bbox，会把平面与相邻大样连成一片）、STAIR/DOTE
    与图框标注；立面/剖面没有天正门库块与 ``_FZH`` 柱块，自然无法通过平面判定。
    """
    if it.get("kind") == "insert":
        block_up = str(it.get("block", "")).upper()
        if block_up.startswith(DOOR_BLOCK_PREFIX) or block_up.startswith(WINDOW_BLOCK_PREFIX):
            return True
        return it.get("layer") == LAYER_COLUMN
    return it.get("layer") in (LAYER_WALL, LAYER_WINDOW, LAYER_COLUMN)


def _select_plan_regions(items: Sequence[dict]) -> List[dict]:
    """把核心实体按空间聚成视图，再筛出平面视图。

    平面判定：足够多的轴对齐 WALL 线段 + 天正门库块或 ``_FZH`` 柱块
    （立面/剖面/楼梯大样均无这两类平面块），并限制面积与长宽比。
    """
    if not items:
        return []
    core_items = [it for it in items if _is_core_item(it)]
    if not core_items:
        return []
    clusters = _cluster_bbox(core_items, VIEW_GAP)
    regions: List[dict] = []
    for member in clusters:
        group = [core_items[i] for i in member]
        x0, y0, x1, y1 = _bbox_items(group)
        w_m, h_m = (x1 - x0) / 1000.0, (y1 - y0) / 1000.0
        area = w_m * h_m
        if w_m < 0.5 or h_m < 0.5:
            continue
        aspect = max(w_m, h_m) / max(min(w_m, h_m), 1e-6)
        wall_segs = sum(
            1
            for it in group
            if it["kind"] == "seg"
            and it["layer"] == LAYER_WALL
            and it["axis"] in (0, 1)
        )
        door_blocks = sum(
            1
            for it in group
            if it["kind"] == "insert" and it["block"].upper().startswith(DOOR_BLOCK_PREFIX)
        )
        col_blocks = sum(
            1 for it in group if it["kind"] == "insert" and it["layer"] == LAYER_COLUMN
        )
        win_ents = sum(1 for it in group if it["kind"] != "insert" and it["layer"] == LAYER_WINDOW)
        is_plan = (
            wall_segs >= REGION_MIN_WALL_SEGS
            and REGION_MIN_AREA <= area <= REGION_MAX_AREA
            and aspect <= REGION_MAX_ASPECT
            and (door_blocks >= 1 or col_blocks >= 1)
        )
        if not is_plan:
            continue
        regions.append(
            {
                "bbox": (x0, y0, x1, y1),
                "width_m": round(w_m, 2),
                "height_m": round(h_m, 2),
                "wall_segments": wall_segs,
                "door_blocks": door_blocks,
                "column_blocks": col_blocks,
                "window_entities": win_ents,
            }
        )
    regions.sort(key=lambda r: (r["door_blocks"] + r["column_blocks"], r["wall_segments"]), reverse=True)
    for idx, r in enumerate(regions):
        r["index"] = idx
    return regions


def _in_region(it: dict, region: dict, pad: float = 200.0) -> bool:
    x0, y0, x1, y1 = region["bbox"]
    bx0, by0, bx1, by1 = it["bbox"]
    cx, cy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    return x0 - pad <= cx <= x1 + pad and y0 - pad <= cy <= y1 + pad


# ── 墙双线配对 ──────────────────────────────────────────────


def _merge_intervals(
    intervals: List[Tuple[float, float, List[str]]],
) -> List[Tuple[float, float, List[str]]]:
    """共线（同 pos 桶）区间合并，间隙 <= WALL_FACE_MERGE_GAP。"""
    intervals = sorted(intervals, key=lambda v: v[0])
    merged: List[Tuple[float, float, List[str]]] = []
    for a, b, hs in intervals:
        if not merged or a > merged[-1][1] + WALL_FACE_MERGE_GAP:
            merged.append((a, b, list(hs)))
        else:
            pa, pb, phs = merged[-1]
            merged[-1] = (pa, max(pb, b), phs + list(hs))
    return merged


def _pair_faces(
    runs: Dict[float, List[Tuple[float, float, List[str]]]],
    orientation: int,
    region_idx: int,
) -> List[dict]:
    """把平行墙面两两配为双线墙，未配对面按单线墙输出。"""
    faces: List[dict] = []
    for pos, ivs in runs.items():
        for start, end, handles in ivs:
            if end - start < WALL_MIN_LEN:
                continue
            faces.append(
                {"pos": pos, "start": start, "end": end, "handles": handles, "paired": False}
            )
    pairs: List[dict] = []
    candidates = []
    for i, fa in enumerate(faces):
        for j in range(i + 1, len(faces)):
            fb = faces[j]
            gap = abs(fa["pos"] - fb["pos"])
            if not (WALL_FACE_MIN_GAP <= gap <= WALL_FACE_MAX_GAP):
                continue
            overlap = min(fa["end"], fb["end"]) - max(fa["start"], fb["start"])
            min_len = min(fa["end"] - fa["start"], fb["end"] - fb["start"])
            if min_len <= 0:
                continue
            ratio = overlap / min_len
            if overlap > 0 and ratio >= WALL_PAIR_MIN_OVERLAP:
                candidates.append((overlap, i, j))
    candidates.sort(reverse=True, key=lambda v: v[0])
    paired_intervals: Dict[float, List[Tuple[float, float]]] = defaultdict(list)
    for _overlap, i, j in candidates:
        fa, fb = faces[i], faces[j]
        if fa["paired"] or fb["paired"]:
            continue
        fa["paired"] = fb["paired"] = True
        start = max(fa["start"], fb["start"])
        end = min(fa["end"], fb["end"])
        pairs.append(
            {
                "kind": "wall",
                "orientation": "h" if orientation == 0 else "v",
                "pos": (fa["pos"] + fb["pos"]) / 2.0,
                "start": start,
                "end": end,
                "thickness": abs(fa["pos"] - fb["pos"]),
                "single": False,
                "handles": fa["handles"] + fb["handles"],
                "region": region_idx,
            }
        )
        paired_intervals[(fa["pos"] + fb["pos"]) / 2.0].append((start, end))
    # 二次配对：与内墙交接处某一面被分成多段时，连续长面允许复用
    # （已配对的长面再与缺口另一侧的短面配对；同一中心线上去重）。
    def _occupied(center: float, a: float, b: float) -> bool:
        for cpos, ivs in paired_intervals.items():
            if abs(cpos - center) <= 5.0:
                if any(a < pe and b > ps for ps, pe in ivs):
                    return True
        return False

    for fa in faces:
        if fa["paired"]:
            continue
        for fb in faces:
            if fb is fa:
                continue
            if not (WALL_FACE_MIN_GAP <= abs(fa["pos"] - fb["pos"]) <= WALL_FACE_MAX_GAP):
                continue
            start = max(fa["start"], fb["start"])
            end = min(fa["end"], fb["end"])
            if end - start < WALL_MIN_LEN:
                continue
            center = (fa["pos"] + fb["pos"]) / 2.0
            if _occupied(center, start, end):
                continue
            fa["paired"] = True
            pairs.append(
                {
                    "kind": "wall",
                    "orientation": "h" if orientation == 0 else "v",
                    "pos": center,
                    "start": start,
                    "end": end,
                    "thickness": abs(fa["pos"] - fb["pos"]),
                    "single": False,
                    "handles": fa["handles"] + fb["handles"],
                    "region": region_idx,
                }
            )
            paired_intervals[center].append((start, end))
            break
    for fa in faces:
        if not fa["paired"]:
            pairs.append(
                {
                    "kind": "wall",
                    "orientation": "h" if orientation == 0 else "v",
                    "pos": fa["pos"],
                    "start": fa["start"],
                    "end": fa["end"],
                    "thickness": None,
                    "single": True,
                    "handles": list(fa["handles"]),
                    "region": region_idx,
                }
            )
    return pairs


def _walls_for_region(region_items: Sequence[dict], region_idx: int) -> Tuple[List[dict], List[Tuple[float, float, float, float]]]:
    """返回墙实例 + 墙面线段（供窗贴墙判定）。"""
    h_runs: Dict[float, List[Tuple[float, float, List[str]]]] = defaultdict(list)
    v_runs: Dict[float, List[Tuple[float, float, List[str]]]] = defaultdict(list)
    face_segs: List[Tuple[float, float, float, float]] = []
    for it in region_items:
        if it["kind"] != "seg" or it["layer"] != LAYER_WALL or it["axis"] not in (0, 1):
            continue
        (x1, y1), (x2, y2) = it["p1"], it["p2"]
        length = math.hypot(x2 - x1, y2 - y1)
        if length < WALL_MIN_LEN:
            continue
        face_segs.append((x1, y1, x2, y2))
        if it["axis"] == 0:
            pos = round(y1 / 10.0) * 10.0
            h_runs[pos].append((min(x1, x2), max(x1, x2), [it["handle"]]))
        else:
            pos = round(x1 / 10.0) * 10.0
            v_runs[pos].append((min(y1, y2), max(y1, y2), [it["handle"]]))
    h_merged = {pos: _merge_intervals(ivs) for pos, ivs in h_runs.items()}
    v_merged = {pos: _merge_intervals(ivs) for pos, ivs in v_runs.items()}
    walls = _pair_faces(h_merged, 0, region_idx) + _pair_faces(v_merged, 1, region_idx)
    return walls, face_segs


# ── 门窗柱 ──────────────────────────────────────────────────


def _block_local_bbox(doc, block_name: str) -> Optional[Tuple[float, float, float, float]]:
    """块定义在插入点局部坐标系下的内容 bbox（不含嵌套块，失败返回 None）。"""
    try:
        block = doc.blocks.get(block_name)
    except Exception:
        return None
    if block is None:
        return None
    xs, ys = [], []
    for e in block:
        t = e.dxftype()
        if t == "LINE":
            xs += [e.dxf.start.x, e.dxf.end.x]
            ys += [e.dxf.start.y, e.dxf.end.y]
        elif t in ("LWPOLYLINE",):
            for x, y, *_ in e.get_points("xy"):
                xs.append(x)
                ys.append(y)
        elif t == "CIRCLE":
            xs += [e.dxf.center.x - e.dxf.radius, e.dxf.center.x + e.dxf.radius]
            ys += [e.dxf.center.y - e.dxf.radius, e.dxf.center.y + e.dxf.radius]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _openings_for_region(region_items: Sequence[dict], region_idx: int, face_segs, doc) -> Tuple[List[dict], List[dict]]:
    doors: List[dict] = []
    windows: List[dict] = []
    door_centers: List[Tuple[float, float]] = []
    for it in region_items:
        if it["kind"] != "insert":
            continue
        block_up = it["block"].upper()
        if block_up.startswith(DOOR_BLOCK_PREFIX):
            doors.append(
                {
                    "kind": "door",
                    "x": it["x"],
                    "y": it["y"],
                    "rotation": round(it["rot"] % 360.0, 3),
                    "block": it["block"],
                    "handle": it["handle"],
                    "layer": it["layer"],
                    "region": region_idx,
                }
            )
            door_centers.append((it["x"], it["y"]))
        elif block_up.startswith(WINDOW_BLOCK_PREFIX):
            local = _block_local_bbox(doc, it["block"])
            windows.append(_window_block_instance(it, local, region_idx))
    # 窗线聚类（非 INSERT 的 WINDOW 层线/折线）
    win_seg_idx = [
        i
        for i, it in enumerate(region_items)
        if it["kind"] == "seg"
        and it["layer"] == LAYER_WINDOW
        and it["axis"] in (0, 1)
        and (it["bbox"][2] - it["bbox"][0] >= 80.0 or it["bbox"][3] - it["bbox"][1] >= 80.0)
    ]
    if win_seg_idx:
        seg_items = [region_items[i] for i in win_seg_idx]
        for member in _cluster_bbox(seg_items, WINDOW_CLUSTER_GAP):
            group = [seg_items[i] for i in member]
            x0, y0, x1, y1 = _bbox_items(group)
            w, h = x1 - x0, y1 - y0
            long_side, short_side = max(w, h), min(w, h)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            singleton_ok = False
            if len(group) == 1:
                # 单根侧亮线兜底：部分门联窗仅外露一根 WINDOW 层平行线，
                # 必须紧邻门块（垂直 ≤400、沿线 ≤门宽/2+1200）才认可。
                seg_len = long_side
                if 500.0 <= seg_len <= 2500.0 and short_side <= 1.0:
                    for dx, dy in door_centers:
                        if w >= h:
                            perp, along = abs(dy - cy), abs(dx - cx)
                        else:
                            perp, along = abs(dx - cx), abs(dy - cy)
                        if perp <= 400.0 and along <= seg_len / 2.0 + 1200.0:
                            singleton_ok = True
                            break
            if len(group) < 2 and not singleton_ok:
                continue
            if not (WINDOW_MIN_LONG <= long_side <= WINDOW_MAX_LONG and short_side <= WINDOW_MAX_SHORT):
                if not singleton_ok:
                    continue
            # 门联窗（FMC）侧亮与洞口窗线与墙面共线、嵌在洞口内，窗中心到
            # 墙面端点可达窗长一半，故容差 = 长边/2 + 500。
            near_limit = long_side / 2.0 + 500.0
            if all(
                _point_seg_dist(cx, cy, *seg) > near_limit for seg in face_segs
            ):
                continue
            # 与 WINLIB 块窗去重（块优先），但门联窗侧亮保留
            if any(math.hypot(cx - wx, cy - wy) < 300.0 for wx, wy in [(w_["x"], w_["y"]) for w_ in windows]):
                continue
            windows.append(
                {
                    "kind": "window",
                    "x": cx,
                    "y": cy,
                    "width": round(w, 1),
                    "height": round(h, 1),
                    "orientation": "h" if w >= h else "v",
                    "source": "lines",
                    "block": None,
                    "handles": sorted({g["handle"] for g in group}),
                    "region": region_idx,
                }
            )
    return doors, windows


def _window_block_instance(it: dict, local, region_idx: int) -> dict:
    w = h = None
    if local:
        x0, y0, x1, y1 = local
        w, h = round((x1 - x0) * abs(it.get("sx", 1.0)), 1), round(
            (y1 - y0) * abs(it.get("sy", 1.0)), 1
        )
    rot = it["rot"] % 180.0
    return {
        "kind": "window",
        "x": it["x"],
        "y": it["y"],
        "width": w,
        "height": h,
        "orientation": "v" if 45.0 < rot < 135.0 else "h",
        "source": "block",
        "block": it["block"],
        "handles": [it["handle"]],
        "region": region_idx,
    }


def _columns_for_region(region_items: Sequence[dict], region_idx: int) -> List[dict]:
    cols: List[dict] = []
    for it in region_items:
        if it["kind"] == "insert" and it["layer"] == LAYER_COLUMN:
            cols.append(
                {
                    "kind": "column",
                    "x": it["x"],
                    "y": it["y"],
                    "rotation": round(it["rot"] % 360.0, 3),
                    "block": it["block"],
                    "handle": it["handle"],
                    "source": "block",
                    "region": region_idx,
                }
            )
        elif it["kind"] == "circle" and it["layer"] == LAYER_COLUMN:
            if COLUMN_MIN_R <= it["r"] <= COLUMN_MAX_R:
                cols.append(
                    {
                        "kind": "column",
                        "x": it["x"],
                        "y": it["y"],
                        "radius": round(it["r"], 1),
                        "block": None,
                        "handle": it["handle"],
                        "source": "circle",
                        "region": region_idx,
                    }
                )
    return cols


# ── 主入口 ──────────────────────────────────────────────────


def extract_t3(doc, *, force: bool = False) -> Dict[str, Any]:
    """识别天正 T3 平面构件。

    返回 ``{"status": dict, "regions": [...], "walls": [...], "doors": [...],
    "windows": [...], "columns": [...]}``。非 T3 图纸快速返回空构件状态；
    T3 特征命中但 0 构件时 status.diagnostic 给出明确诊断（不静默）。
    """
    signature = detect_t3_signature(doc)
    empty_status = {
        **signature,
        "storage_form": "none",
        "proxy_count": 0,
        "component_counts": {"walls": 0, "doors": 0, "windows": 0, "columns": 0},
        "diagnostic": None,
    }
    if not signature["is_t3"] and not force:
        return {"status": empty_status, "regions": [], "walls": [], "doors": [], "windows": [], "columns": []}

    msp = doc.modelspace()
    items = _collect_items(msp)
    proxy_count = 0
    try:
        proxy_count = sum(1 for e in msp if e.dxftype() == "PROXY_ENTITY")
    except Exception:
        proxy_count = 0

    regions = _select_plan_regions(items)

    walls: List[dict] = []
    doors: List[dict] = []
    windows: List[dict] = []
    columns: List[dict] = []
    for region in regions:
        idx = region["index"]
        region_items = [it for it in items if _in_region(it, region)]
        region_walls, face_segs = _walls_for_region(region_items, idx)
        region_doors, region_windows = _openings_for_region(region_items, idx, face_segs, doc)
        walls.extend(region_walls)
        doors.extend(region_doors)
        windows.extend(region_windows)
        columns.extend(_columns_for_region(region_items, idx))

    component_counts = {
        "walls": len(walls),
        "doors": len(doors),
        "windows": len(windows),
        "columns": len(columns),
    }
    if proxy_count:
        storage_form = "proxy_entity"
        diagnostic = (
            f"检测到 {proxy_count} 个 PROXY_ENTITY 代理实体：天正对象未分解，"
            "矢量信息不可读，请在 AutoCAD 中执行 T3 分解/另存为 T3 DXF 后重试。"
        )
    elif sum(component_counts.values()) == 0:
        storage_form = "t3_signature_empty"
        diagnostic = (
            "命中天正 T3 特征（AppID/约定图层）但解出 0 个墙/门/窗/柱构件："
            "可能为加密 T3 未正确分解、图纸仅含立面/系统图或实体位于外部参照。"
        )
    else:
        storage_form = "exploded_native_layers"
        diagnostic = None

    status = {
        **signature,
        "storage_form": storage_form,
        "proxy_count": proxy_count,
        "plan_region_count": len(regions),
        "component_counts": component_counts,
        "diagnostic": diagnostic,
    }
    return {
        "status": status,
        "regions": regions,
        "walls": walls,
        "doors": doors,
        "windows": windows,
        "columns": columns,
    }


# ── 分类挂接（handle 级覆盖，不丢块名/不展平）──────────────


def attach_t3_markers(primitives: Iterable, t3_components: Optional[Dict[str, Any]]) -> Iterable:
    """把 T3 识别结果按 handle 落到 RawPrimitive.properties（原地修改）。

    - 门/柱 INSERT：``_t3_native = "door"|"column"``，分类时覆盖图层误判；
    - 窗线：``_t3_native="window"`` + ``_t3_window_gid`` + ``_t3_window_bbox``，
      分类循环每个 gid 仅产出一个窗实体（四线符号合并为单实例）；
    - 窗库块 INSERT：``_t3_native="window"``（单图元即单实例）；
    - 墙线：``_t3_wall_gid`` + ``_t3_wall_seg``（中心线/厚度/区间），分类循环
      每个 gid 仅产出一个墙实体（双线配对合并为单实例，含 single 未配对面）。
    """
    if not primitives or not t3_components:
        return primitives
    handle_kind: Dict[str, str] = {}
    for door in t3_components.get("doors", []):
        h = door.get("handle")
        if h:
            handle_kind[str(h)] = "door"
    gid_by_handle: Dict[str, int] = {}
    window_bbox: Dict[int, Tuple[float, float, float, float]] = {}
    for gid, win in enumerate(t3_components.get("windows", [])):
        handles = win.get("handles") or []
        if win.get("source") == "block":
            for h in handles:
                handle_kind[str(h)] = "window"
            continue
        x, y = win["x"], win["y"]
        w = win.get("width") or 200.0
        h = win.get("height") or 200.0
        window_bbox[gid] = (x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0)
        for hh in handles:
            gid_by_handle[str(hh)] = gid
    for col in t3_components.get("columns", []):
        h = col.get("handle")
        if h and col.get("source") == "block":
            handle_kind[str(h)] = "column"
    # 一根面线可被同中心线的多个共线墙实例复用（二次配对长面复用补交接缺口），
    # handle → 墙 gid 是一对多：必须全部保留。单值覆盖会让「面线全部被共享」的
    # 墙实例（如 d3 x=7031540 中段 5.4m，4 根面线均被上下相邻段复用）在标记中
    # 彻底消失，分类输出丢整段墙。
    wall_gids_by_handle: Dict[str, List[int]] = {}
    wall_seg: Dict[int, Dict[str, Any]] = {}
    for wgid, wall in enumerate(t3_components.get("walls", [])):
        seg = {
            "orientation": wall.get("orientation"),
            "pos": wall.get("pos"),
            "start": wall.get("start"),
            "end": wall.get("end"),
            "thickness": wall.get("thickness"),
            "single": bool(wall.get("single")),
        }
        wall_seg[wgid] = seg
        for h in wall.get("handles") or []:
            wall_gids_by_handle.setdefault(str(h), []).append(wgid)

    for prim in primitives:
        handle = str(getattr(prim, "handle", "") or "")
        if not handle:
            continue
        if handle in handle_kind:
            prim.properties["_t3_native"] = handle_kind[handle]
        gid = gid_by_handle.get(handle)
        if gid is not None:
            prim.properties["_t3_native"] = "window"
            prim.properties["_t3_window_gid"] = gid
            bx0, by0, bx1, by1 = window_bbox[gid]
            prim.properties["_t3_window_bbox"] = {
                "x": bx0,
                "y": by0,
                "width": bx1 - bx0,
                "height": by1 - by0,
            }
        wgids = wall_gids_by_handle.get(handle)
        if wgids:
            # 多实例共享面线：全量 gid/seg 落库（分类回填保证每个实例都产实体）；
            # 兼容字段 _t3_wall_gid/_t3_wall_seg 取首个（gid 最小的）实例。
            prim.properties["_t3_wall_gids"] = list(wgids)
            prim.properties["_t3_wall_segs"] = {g: wall_seg[g] for g in wgids}
            prim.properties["_t3_wall_gid"] = wgids[0]
            prim.properties["_t3_wall_seg"] = wall_seg[wgids[0]]
    return primitives
