"""原生实例字段 / 几何长度 → 图元属性注入（Roadmap v4 T-A4 / 缺口 G9 收尾）。

尺寸链路（Step 3.5）与 TEXT 标注链路（Step 3.6）之后仍有两类系统性缺失
（真实图纸库 20 张实测：可标注类型关键属性缺失率 48.7%，缺失实体 100% 为
bbox 退化的线元实体或携带未提升的原生字段）：

1. **T3 native 实例字段未提升**（t3_gap_report.md §6.1 动作 1）：
   - 墙：``_t3_wall_seg``（中心线/起止/厚度，mm）已随分类落 properties，
     但从未提升为原子函数可读的 ``width``（=厚度）/ ``length``（=跨度）。
   - 窗：``_t3_window_bbox``（整窗 bbox，mm）同样未提升为 ``width``。
   - 柱：``_t3_native=column``（块/圆/分解态多段线）bbox 未提升为
     ``width`` / ``height``。

2. **线元实体 bbox 退化**：普通 DXF 图纸的墙/梯/门窗由轴对齐 LINE 分类而来，
   bbox 一维为 0（另一维即图元真实跨度）。跨度是图元自身的真实几何量，
   注入 ``length`` 不引入臆测值；厚度/净宽不做几何臆测（误报风险），
   仍由尺寸/TEXT 链路或 T3 native 字段供给。

规则（与 text_attributes 一致）：
- 不覆盖既有非零值；写入 ``_attribute_source`` 便于下游追溯
  （``t3_native`` / ``geometry_length``）。
- 单位归一复用 ``_measurement_to_meters``（>100 视为 mm），并叠加
  合理区间双保险（长度 0.3~100m、厚度 0.05~1.0m、门窗 0.3~6m、柱 0.08~1.5m），
  落区间外的值一律不注入（宁缺勿错）。
"""

from typing import Dict, List, Optional

from ..drawing_parser import RawPrimitive
from .models import SemanticEntity
from .relations import _measurement_to_meters
from .text_attributes import (
    _THICKNESS_MAX_M,
    _THICKNESS_MIN_M,
    _WIDTH_MAX_M,
    _WIDTH_MIN_M,
    _inject_attr,
)

# ── 目标实体类型 ────────────────────────────────────────
_WALL_TYPES = {"wall", "shear_wall", "fire_wall", "exterior_wall"}
# 线元长度注入范围：尺寸可标注类型（与 tools/dimension_coverage.py 口径一致）
# + 墙族。不对 "other"/设备类注入，避免噪声。
_LENGTH_TYPES = (
    _WALL_TYPES
    | {"door", "doorway", "exit_door", "fire_door", "window", "fire_window"}
    | {"corridor", "staircase", "stair", "fire_lane", "room", "exit"}
)

# ── 合理区间（米）──────────────────────────────────────
_LENGTH_MIN_M, _LENGTH_MAX_M = 0.3, 100.0
_COLUMN_MIN_M, _COLUMN_MAX_M = 0.08, 1.5
# bbox 退化判定阈值（mm）：一维 ≤1mm 视为线元
_DEGENERATE_MM = 1.0
# 线元跨度最小值（mm）：<300mm 的碎片不注入
_MIN_SPAN_MM = 300.0


def _to_meters(value, lo: float, hi: float) -> Optional[float]:
    """图纸单位 → 米，并做区间双保险；不可信返回 None。"""
    m_val = _measurement_to_meters(value)
    if m_val is None or not (lo <= m_val <= hi):
        return None
    return m_val


def _to_meters_small(value, lo: float, hi: float) -> Optional[float]:
    """小尺寸构件（厚度/柱截面 0.05~1.5m）的单位归一。

    共享启发式 ``_measurement_to_meters`` 的 mm 判据下限为 0.3m，
    墙厚 200mm→0.2m、柱边 300mm 会落空被判回「米」原值。此处按构件
    量级定向归一：值 ≤3 视为已是米，>3 视为 mm（÷1000），再验区间。
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    m_val = v if v <= 3.0 else v / 1000.0
    if not (lo <= m_val <= hi):
        return None
    return m_val


def _bbox_span_m(bbox: Dict) -> tuple:
    """返回 bbox (长边m, 短边m, 是否退化)。空/非法 bbox 返回 (None, None, True)。"""
    if not isinstance(bbox, dict):
        return None, None, True
    try:
        w = float(bbox.get("width") or 0)
        h = float(bbox.get("height") or 0)
    except (TypeError, ValueError):
        return None, None, True
    long_mm = max(w, h)
    short_mm = min(w, h)
    degenerate = short_mm <= _DEGENERATE_MM
    return long_mm, short_mm, degenerate


def _inject_native_instance_fields(entities: List[SemanticEntity]) -> List[SemanticEntity]:
    """提升 T3 native 实例字段为原子函数可读属性（t3_gap_report §6.1 动作 1）。"""
    for ent in entities:
        props = ent.properties

        # 1) 墙：_t3_wall_seg（mm）→ width=厚度 / length=跨度
        seg = props.get("_t3_wall_seg")
        if isinstance(seg, dict) and ent.type in _WALL_TYPES:
            thick_m = _to_meters_small(seg.get("thickness"), _THICKNESS_MIN_M, _THICKNESS_MAX_M)
            if thick_m is not None:
                _inject_attr(ent, "width", thick_m, "t3_native")
            try:
                span_mm = abs(float(seg.get("end") or 0) - float(seg.get("start") or 0))
            except (TypeError, ValueError):
                span_mm = 0.0
            span_m = _to_meters(span_mm, _LENGTH_MIN_M, _LENGTH_MAX_M)
            if span_m is not None:
                _inject_attr(ent, "length", span_m, "t3_native")

        # 2) 窗：_t3_window_bbox（mm）→ width=长边（洞口跨度）
        wb = props.get("_t3_window_bbox")
        if isinstance(wb, dict) and ent.type in ("window", "fire_window"):
            try:
                span_mm = max(float(wb.get("width") or 0), float(wb.get("height") or 0))
            except (TypeError, ValueError):
                span_mm = 0.0
            span_m = _to_meters(span_mm, _WIDTH_MIN_M, _WIDTH_MAX_M)
            if span_m is not None:
                _inject_attr(ent, "width", span_m, "t3_native")

        # 3) 柱：_t3_native=column → width/height=bbox 短/长边（块/圆/分解态多段线）
        if props.get("_t3_native") == "column" and ent.type == "column":
            long_mm, short_mm, degenerate = _bbox_span_m(ent.bbox)
            if not degenerate and long_mm is not None:
                w_m = _to_meters_small(short_mm, _COLUMN_MIN_M, _COLUMN_MAX_M)
                h_m = _to_meters_small(long_mm, _COLUMN_MIN_M, _COLUMN_MAX_M)
                if w_m is not None:
                    _inject_attr(ent, "width", w_m, "t3_native")
                if h_m is not None:
                    _inject_attr(ent, "height", h_m, "t3_native")

    return entities


def _inject_geometry_lengths(entities: List[SemanticEntity]) -> List[SemanticEntity]:
    """bbox 退化的线元实体：注入 length=长边（图元真实跨度，非臆测）。

    仅处理「长边 ≥300mm 且短边 ≤1mm」的退化实体；厚度/净宽不做几何臆测。
    """
    for ent in entities:
        if ent.type not in _LENGTH_TYPES:
            continue
        existing = ent.properties.get("length")
        if isinstance(existing, (int, float)) and existing > 0:
            continue
        long_mm, _short_mm, degenerate = _bbox_span_m(ent.bbox)
        if not degenerate or long_mm is None or long_mm < _MIN_SPAN_MM:
            continue
        span_m = _to_meters(long_mm, _LENGTH_MIN_M, _LENGTH_MAX_M)
        if span_m is not None:
            _inject_attr(ent, "length", span_m, "geometry_length")
    return entities


def _inject_geometry_attributes(
    self,
    entities: List[SemanticEntity],
    primitives: List[RawPrimitive],
) -> List[SemanticEntity]:
    """Step 3.7 入口（签名与其它 Step 一致；primitives 预留后续配对推断）。"""
    del primitives  # 当前实现只消费实体自身字段
    if not entities:
        return entities
    entities = _inject_native_instance_fields(entities)
    entities = _inject_geometry_lengths(entities)
    return entities
