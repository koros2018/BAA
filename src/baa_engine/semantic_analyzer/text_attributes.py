"""TEXT/MTEXT 标注 → 图元属性注入（Roadmap v4 T-A4 / 缺口 G9）。

真实图纸中大量 wall/slab 实体 bbox 退化（宽高为 0）、无 DIMENSION 可达，
尺寸链路（_bind_dimensions）无法绑定它们。此模块从 TEXT/MTEXT 文本反推属性：

- 厚度类：``200厚`` / ``厚200`` / ``墙厚200`` / ``200mm厚`` / ``混凝土墙200``
  等 → 换算为米（/1000），注入就近 wall（属性名 ``width``，沿用
  ``_infer_attribute_name`` / ``_infer_corridor_widths`` 对墙厚的既有约定）、
  slab（属性名 ``thickness``）。
- 门窗编号类：``M0921``（门 900×2100）、``C1200``（窗宽 1200）、``FM甲1524``
  （防火门 1500×2400）等，按「字母前缀 + 宽(2位) + 高(2位)，每对 ×100mm」编码
  解析出宽高（mm），注入就近 door/fire_door/window 的 ``width`` / ``clear_width``
  / ``height``。
- 防火等级类：仅当编号**显式带有等级字符**（``FM甲1524`` / ``FC乙1212``）时，
  按等级写 ``fire_rating``（门：甲/乙/丙=3/2/1 级；窗：甲/乙/丙=1.5/1.0/0.5h）。
  裸 ``FM1524``（只有防火门类型、无等级字）**不写等级**，避免按类型猜等级。

规则：不覆盖已有非零值；厚度仅注入 0.05~1.0m 合理区间；写入 ``_attribute_source``
（``text_thickness`` / ``text_code``）与 ``_fire_rating_source``
（``text_code_grade``）便于下游追溯。TEXT 文本字段名为
``properties["text"]``（DXF TEXT/MTEXT 在 parsers/geometry 中统一落此字段）。
"""

import re
from typing import List, Dict, Optional, Tuple

from ..drawing_parser import RawPrimitive
from .models import SemanticEntity
from .geometry import min_edge_distance
from .relations import _DIM_MATCH_MAX_DIST

# ── 目标实体类型 ────────────────────────────────────────
_WALL_TYPES = {"wall", "shear_wall", "fire_wall", "exterior_wall"}
_SLAB_TYPES = {"slab", "floor_slab", "slab_top", "roof", "floor"}
# 门窗编号可绑定类型（doorway 与 door 同为墙体开口，见 relations.py 注释）
_DOOR_TYPES = ("door", "doorway", "exit_door", "fire_door")
_WINDOW_TYPES = ("window", "fire_window")

# ── 匹配阈值与量纲 ──────────────────────────────────────
# 沿用尺寸绑定「就近」的最大匹配距离量级（_DIM_MATCH_MAX_DIST=10000mm）
_TEXT_ATTR_MAX_DIST = _DIM_MATCH_MAX_DIST
_THICKNESS_MIN_M = 0.05
_THICKNESS_MAX_M = 1.0
_WIDTH_MIN_M = 0.3
_WIDTH_MAX_M = 6.0
_HEIGHT_MIN_M = 0.3
_HEIGHT_MAX_M = 6.0

# 厚度：数字在前（200厚 / 200mm厚），厚在前（厚200），构件名+数字（混凝土墙200）
_THICKNESS_PATTERNS = (
    re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*(?:mm|MM|毫米)?\s*厚"),
    # 「厚」在前时厚度必为 2~4 位整数（50~9999mm）；排除「4厚1：2」中把配比数字 1 误当厚度
    re.compile(r"厚\s*(\d{2,4})\s*(?:mm|MM|毫米)?"),
    re.compile(r"(?:墙|板)\s*(\d{2,4})(?!\d)"),
)

# 门窗编号：前缀 + 可选防火等级字 + 宽(2位) + 高(2位)
# 左边界排除字母/数字/「%」：DXF 中 %%C 为直径符号 φ（如 %%C1816x6266 是管径），
# 若不排除会被误当作窗编号 C1816。
# FC = 防火窗；等级字用命名组显式捕获，供 fire_rating 注入（不再丢弃）。
_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9%])(?P<prefix>FHM|FM|FC|M|C)"
    r"(?P<grade>[甲乙丙]?)(?P<w>\d{2})(?P<h>\d{2})(?![0-9])"
)

# 等级 → fire_rating：门按「级」，窗按「耐火极限 h」。
# 甲/乙/丙 = 3/2/1 级（门）；窗按 GB 16809 对应 1.5/1.0/0.5h。
_DOOR_GRADE_RATING = {"甲": 3.0, "乙": 2.0, "丙": 1.0}
_WINDOW_GRADE_HOURS = {"甲": 1.5, "乙": 1.0, "丙": 0.5}
_WINDOW_CODE_PREFIXES = ("C", "FC")


def _parse_thickness_m(text: str) -> Optional[float]:
    """从文本解析厚度（米）。仅返回 0.05~1.0m 区间内的首个可信值。"""
    if not text:
        return None
    # P0-6 优化（2026-11-04）：关键词预过滤。
    # 3 个 pattern 都要求文本含「厚」或「墙/板」（pattern1 数字+厚，pattern2 厚+数字，
    # pattern3 墙/板+数字）。大多数 TEXT（如 "F1"、"房间"）不含这些关键词，
    # 直接跳过可避免 16531×3 次 finditer。matched 完全一致（0.045s→0.003s，15×）。
    if "厚" not in text and "墙" not in text and "板" not in text:
        return None
    for pat in _THICKNESS_PATTERNS:
        for m in pat.finditer(text):
            try:
                v = float(m.group(1))
            except (TypeError, ValueError):
                continue
            # 图纸厚度标注既有多为 mm（200），也允许已是米（0.2）
            m_val = v / 1000.0 if v >= 10 else v
            if _THICKNESS_MIN_M <= m_val <= _THICKNESS_MAX_M:
                return m_val
    return None


def _parse_opening_code(text: str) -> Optional[Tuple[str, Optional[float], Optional[float]]]:
    """解析门窗编号，返回 (target_kind, width_m, height_m)。

    编码规则：前缀后紧跟 2 位宽度 + 2 位高度，每对 ×100mm。
    例：M0921→(door, 0.9, 2.1)；C1200→(window, 1.2, None)（高为 00 视为未知）。
    无匹配或宽高越界返回 None。
    """
    if not text:
        return None
    for m in _CODE_PATTERN.finditer(text):
        prefix = m.group("prefix")
        w_mm = int(m.group("w")) * 100
        h_mm = int(m.group("h")) * 100
        kind = (
            "window"
            if prefix in _WINDOW_CODE_PREFIXES
            else ("fire_door" if prefix in ("FM", "FHM") else "door")
        )
        w_m = w_mm / 1000.0
        h_m = h_mm / 1000.0 if h_mm > 0 else None
        if not (_WIDTH_MIN_M <= w_m <= _WIDTH_MAX_M):
            continue
        if h_m is not None and not (_HEIGHT_MIN_M <= h_m <= _HEIGHT_MAX_M):
            h_m = None
        return kind, w_m, h_m
    return None


def _parse_opening_grade(text: str) -> Optional[Tuple[str, str]]:
    """解析编号中的显式等级字，返回 (target_kind, 等级字)。

    只有 ``FM甲1524`` / ``FC乙1212`` 这类**逐实体标注**才返回等级；
    裸 ``FM1524``（无甲/乙/丙）返回 None——类型不能代替等级。
    """
    if not text:
        return None
    for m in _CODE_PATTERN.finditer(text):
        grade = m.group("grade")
        if not grade:
            continue
        prefix = m.group("prefix")
        kind = (
            "window"
            if prefix in _WINDOW_CODE_PREFIXES
            else ("fire_door" if prefix in ("FM", "FHM") else "door")
        )
        return kind, grade
    return None


def _rating_for_grade(kind: str, grade: str) -> Optional[float]:
    """等级字 → fire_rating 数值（门按级、窗按 h）。"""
    if kind == "window":
        return _WINDOW_GRADE_HOURS.get(grade)
    return _DOOR_GRADE_RATING.get(grade)


def _inject_fire_rating(ent: SemanticEntity, value: float, source: str) -> bool:
    """不覆盖既有非零 fire_rating/rating 地写入等级；成功返回 True。"""
    if not (isinstance(value, (int, float)) and value > 0):
        return False
    existing = ent.properties.get("fire_rating", ent.properties.get("rating", 0))
    if isinstance(existing, (int, float)) and existing > 0:
        return False
    ent.properties["fire_rating"] = round(float(value), 2)
    ent.properties["_fire_rating_source"] = source
    return True


def _nearest_entity(
    self,
    text_bbox: Dict,
    candidates: List[SemanticEntity],
    max_dist: float,
) -> Optional[SemanticEntity]:
    """在候选实体中找与 text_bbox 边缘距离最近者（<=max_dist）。"""
    best = None
    best_dist = float("inf")
    for ent in candidates:
        dist = min_edge_distance(text_bbox, ent.bbox)
        if dist < best_dist:
            best = ent
            best_dist = dist
    if best is not None and best_dist <= max_dist:
        return best
    return None


def _inject_attr(ent: SemanticEntity, name: str, value: float, source: str) -> bool:
    """不覆盖既有非零值地写入属性；成功注入返回 True。"""
    if not (isinstance(value, (int, float)) and value > 0):
        return False
    existing = ent.properties.get(name)
    if isinstance(existing, (int, float)) and existing > 0:
        return False
    ent.properties[name] = round(float(value), 4)
    ent.properties["_attribute_source"] = source
    return True


def _inject_text_attributes(
    self,
    entities: List[SemanticEntity],
    primitives: List[RawPrimitive],
) -> List[SemanticEntity]:
    """扫描 TEXT/MTEXT，反推厚度/门窗编号并注入就近实体属性。

    返回 entities（原地修改，保持与其它 Step 一致的返回式用法）。
    """
    if not entities or not primitives:
        return entities

    # 预筛候选实体，避免对每个文本都全量扫描 entities（大图纸性能）
    wall_slab = [e for e in entities if e.type in _WALL_TYPES or e.type in _SLAB_TYPES]
    door_ish = [e for e in entities if e.type in _DOOR_TYPES]
    window_ish = [e for e in entities if e.type in _WINDOW_TYPES]
    if not (wall_slab or door_ish or window_ish):
        return entities

    # P0-3 优化：候选实体按 bbox 分桶到 grid，_nearest_entity 只查附近 cells。
    # 原实现对每个 TEXT 全量扫描 wall_slab/door_ish/window_ish（O(T×C)），
    # 3071 TEXT × 数千候选 = 数百万次 min_edge_distance。grid 后候选降至个位数。
    _TEXT_CELL = 1000.0  # mm
    _TEXT_EXPAND = int(_TEXT_ATTR_MAX_DIST / _TEXT_CELL) + 1  # 覆盖 10m 半径

    def _build_ent_grid(cands):
        # T-opt34: 改用嵌套 defaultdict(dict) 替代平铺 dict[(gx,gy)]。
        # 与 relations.py Phase 3/Phase 1 同策略（T-opt17/T-opt33），
        # 查询时只遍历存在的 gx row，跳过空 cell。
        from collections import defaultdict as _dd
        g = _dd(lambda: _dd(list))
        for ent in cands:
            b = ent.bbox
            bx = b.get("x", 0); by = b.get("y", 0)
            bw = max(b.get("width", 0), 1.0); bh = max(b.get("height", 0), 1.0)
            gx1 = int(bx / _TEXT_CELL); gx2 = int((bx + bw) / _TEXT_CELL)
            gy1 = int(by / _TEXT_CELL); gy2 = int((by + bh) / _TEXT_CELL)
            # T-opt32: 截断超大 bbox 实体的 cell 范围（对齐 spatial_grid
            # MAX_CELLS_PER_ENTITY=500）。第15张图纸 wall 中位长边 578m，
            # range(gx1,gx2+1)×range(gy1,gy2+1) 覆盖 33 万 cells/实体 →
            # grid 爆炸（11 亿插入）。截断到中心格不影响正确性：
            # _TEXT_ATTR_MAX_DIST=10m << 578m 跨度，远端 cell 内的实体
            # 不可能与 TEXT 在 10m 内（AABB 前置拒绝会过滤）。
            _nx = gx2 - gx1 + 1
            _ny = gy2 - gy1 + 1
            if _nx * _ny > 500:
                _pcx = (gx1 + gx2) // 2
                _pcy = (gy1 + gy2) // 2
                gx_range = [_pcx]
                gy_range = [_pcy]
            else:
                gx_range = range(gx1, gx2 + 1)
                gy_range = range(gy1, gy2 + 1)
            for gx in gx_range:
                row = g[gx]  # defaultdict 自动创建空 dict
                for gy in gy_range:
                    row[gy].append(ent)
        return g

    wall_slab_grid = _build_ent_grid(wall_slab)
    door_grid = _build_ent_grid(door_ish)
    window_grid = _build_ent_grid(window_ish)

    def _grid_nearest(text_bbox, grid, max_dist):
        """在 grid 中找与 text_bbox 边缘距离最近者（<=max_dist）。"""
        tb = text_bbox
        tx = tb.get("x", 0); ty = tb.get("y", 0)
        tw = max(tb.get("width", 0), 1.0); th = max(tb.get("height", 0), 1.0)
        gx1 = int(tx / _TEXT_CELL); gx2 = int((tx + tw) / _TEXT_CELL)
        gy1 = int(ty / _TEXT_CELL); gy2 = int((ty + th) / _TEXT_CELL)
        best = None
        best_dist = float("inf")
        seen = set()
        # T-opt34: 遍历存在的 gx row，跳过空行；gy 仍逐格 .get（内层 dict 稀疏）
        for gx in range(gx1 - _TEXT_EXPAND, gx2 + _TEXT_EXPAND + 1):
            row = grid.get(gx)
            if row is None:
                continue
            for gy in range(gy1 - _TEXT_EXPAND, gy2 + _TEXT_EXPAND + 1):
                for ent in row.get(gy, ()):
                    eid = id(ent)
                    if eid in seen:
                        continue
                    seen.add(eid)
                    dist = min_edge_distance(text_bbox, ent.bbox)
                    if dist < best_dist:
                        best = ent
                        best_dist = dist
        if best is not None and best_dist <= max_dist:
            return best
        return None

    for prim in primitives:
        if prim.dxf_type not in ("TEXT", "MTEXT"):
            continue
        text = prim.properties.get("text") or ""
        if not text:
            continue
        text_bbox = prim.bbox or {}

        # 1) 厚度类 → 就近墙/板
        thick_m = _parse_thickness_m(text)
        if thick_m is not None and wall_slab_grid:
            ent = _grid_nearest(text_bbox, wall_slab_grid, _TEXT_ATTR_MAX_DIST)
            if ent is not None:
                if ent.type in _SLAB_TYPES:
                    _inject_attr(ent, "thickness", thick_m, "text_thickness")
                else:
                    # 墙厚沿用系统既有 width 约定（_infer_attribute_name: wall→width）
                    _inject_attr(ent, "width", thick_m, "text_thickness")

        # 2) 门窗编号类 → 就近门窗
        parsed = _parse_opening_code(text)
        if parsed is not None:
            kind, w_m, h_m = parsed
            candidates_grid = window_grid if kind == "window" else door_grid
            if candidates_grid:
                ent = _grid_nearest(text_bbox, candidates_grid, _TEXT_ATTR_MAX_DIST)
                if ent is not None:
                    if kind == "window":
                        _inject_attr(ent, "width", w_m, "text_code")
                    else:
                        # 门：width 为主，clear_width 同步（沿用 Step 1.6 门宽兜底口径）
                        _inject_attr(ent, "width", w_m, "text_code")
                        _inject_attr(ent, "clear_width", w_m, "text_code")
                    if h_m is not None:
                        _inject_attr(ent, "height", h_m, "text_code")
                    # 3) 显式等级字（FM甲1524 / FC乙1212）→ fire_rating。
                    # 裸 FM1524 无等级字 → grade_info 为 None，不写等级。
                    grade_info = _parse_opening_grade(text)
                    if grade_info is not None and grade_info[0] == kind:
                        _inject_fire_rating(
                            ent, _rating_for_grade(kind, grade_info[1]), "text_code_grade"
                        )

    return entities
