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

规则：不覆盖已有非零值；厚度仅注入 0.05~1.0m 合理区间；写入 ``_attribute_source``
（``text_thickness`` / ``text_code``）便于下游追溯。TEXT 文本字段名为
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
_CODE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9%])(FHM|FM|M|C)[甲乙丙]?(\d{2})(\d{2})(?![0-9])"
)


def _parse_thickness_m(text: str) -> Optional[float]:
    """从文本解析厚度（米）。仅返回 0.05~1.0m 区间内的首个可信值。"""
    if not text:
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
        prefix = m.group(1)
        w_mm = int(m.group(2)) * 100
        h_mm = int(m.group(3)) * 100
        kind = "window" if prefix == "C" else ("fire_door" if prefix in ("FM", "FHM") else "door")
        w_m = w_mm / 1000.0
        h_m = h_mm / 1000.0 if h_mm > 0 else None
        if not (_WIDTH_MIN_M <= w_m <= _WIDTH_MAX_M):
            continue
        if h_m is not None and not (_HEIGHT_MIN_M <= h_m <= _HEIGHT_MAX_M):
            h_m = None
        return kind, w_m, h_m
    return None


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

    for prim in primitives:
        if prim.dxf_type not in ("TEXT", "MTEXT"):
            continue
        text = prim.properties.get("text") or ""
        if not text:
            continue
        text_bbox = prim.bbox or {}

        # 1) 厚度类 → 就近墙/板
        thick_m = _parse_thickness_m(text)
        if thick_m is not None and wall_slab:
            ent = _nearest_entity(self, text_bbox, wall_slab, _TEXT_ATTR_MAX_DIST)
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
            candidates = window_ish if kind == "window" else door_ish
            ent = _nearest_entity(self, text_bbox, candidates, _TEXT_ATTR_MAX_DIST)
            if ent is not None:
                if kind == "window":
                    _inject_attr(ent, "width", w_m, "text_code")
                else:
                    # 门：width 为主，clear_width 同步（沿用 Step 1.6 门宽兜底口径）
                    _inject_attr(ent, "width", w_m, "text_code")
                    _inject_attr(ent, "clear_width", w_m, "text_code")
                if h_m is not None:
                    _inject_attr(ent, "height", h_m, "text_code")

    return entities
