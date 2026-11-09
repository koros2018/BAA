"""
P121 Phase 1: 图纸类型分类器
基于图层名 + 实体类型 + 文件名关键词判断图纸类型（建筑/结构/电气/给排水/暖通/其他）
"""

import math
import re
import statistics
from typing import Dict, Any, List, Tuple

# ── 分类规则 ──────────────────────────────────────────────


def _is_ascii_alpha(ch: str) -> bool:
    return ch.isascii() and ch.isalpha()


# 需要按词元边界匹配的短 ASCII 关键词最大长度
# 例：EL / STR / MEP / ELT 太短，用 `in` 会把 elevator / instrument / shelter 误吃
_SHORT_TOKEN_MAX_LEN = 3


def _kw_match(keyword: str, text_lower: str, force_boundary: bool = False) -> bool:
    """关键词匹配：短 ASCII 词元走边界匹配，其余保持子串匹配（T5）。

    历史问题：`"EL"` 用 `in` 匹配时 `elevator` / `level` / `panel` 都会命中，
    导致消防电梯图被判成电气图并跳过审查。

    规则：
    - 长度 ≤3、首尾均为 ASCII 字母数字的关键词（EL/STR/MEP/ELT…）要求
      两侧不是 ASCII 字母（数字/下划线/连字符视为分隔），即按词元边界匹配；
      `EL` 命中 `EL` / `EL1` / `EL_1` / `EL-POWER`，不命中 `elev` / `panel`。
    - CJK 关键词保持子串（中文无需分词）。
    - 长英文关键词保持子串（`electric` 需命中 `electrical`，`VENT` 需命中
      `VENTILATION`，`REIN` 需命中 `REINFORCED`）。
    - 以分隔符收尾的关键词（`EL_` / `FE_` / `STR_` / `DWG_`）首尾非字母数字，
      也保持子串语义。
    - ``force_boundary=True``：不论长度，ASCII 字母数字词元一律按边界匹配。
      供图幅类型识别使用：`elev` 不得命中 `ELEVATOR`，`sect` 不得命中
      `SECTION` 之外的单词内部片段；旧调用不传该参数，行为不变。
    """
    kw = keyword.lower()
    if not kw:
        return False
    if (
        not force_boundary
        and len(kw) > _SHORT_TOKEN_MAX_LEN
    ) or (
        not kw.isascii()
        or not (_is_ascii_alpha(kw[0]) or kw[0].isdigit())
        or not (_is_ascii_alpha(kw[-1]) or kw[-1].isdigit())
    ):
        return kw in text_lower
    pos = text_lower.find(kw)
    while pos >= 0:
        end = pos + len(kw)
        left_ok = pos == 0 or not _is_ascii_alpha(text_lower[pos - 1])
        right_ok = end >= len(text_lower) or not _is_ascii_alpha(text_lower[end])
        if left_ok and right_ok:
            return True
        pos = text_lower.find(kw, pos + 1)
    return False


# 文件名关键词 → 类型（优先级从高到低）
_FILENAME_RULES: Dict[str, list] = {
    "结构": ["结构", "STR", "structure", "梁", "柱", "板", "基础", "基础", "配筋", "结构图"],
    "电气": ["电气", "配电", "动力", "照明", "火灾自动报警", "消防", "气体灭火", "EL", "ELEC", "electric"],
    "暖通": ["暖通", "通风", "HVAC", "空调", "给排水", "消防水", "水消防", "给排水", "MEP", "水暖"],
    "建筑": ["建筑", "ARCH", "architectural", "平面", "立面", "剖面", "楼层", "总平面"],
}

# 图层名关键词 → 类型
# 权重策略：结构/电气/暖通关键词权重 1.5（精准、出现即强信号），
# 建筑关键词权重 0.5（AXIS/DIM_ 等通用层在所有图纸都有，弱信号）
_LAYER_RULES: Dict[str, list] = {
    "结构": [
        "STR_",
        "BEAM",
        "COLUMN",
        "SLAB",
        "WALL_STR",
        "结构",
        "STR_LAYER",
        "柱",
        "梁",
        "板",
        "REIN",
        "REBAR",
        "PUB_DIM",
        "1-梁",
        "2-板",
        "3-柱",
        "7-详图",
        "梁-TEXT",
        "板层",
        "板筋",
        "钢夹层",
    ],
    "电气": [
        "EL_",
        "EL",
        "ELEC",
        "POWER",
        "LIGHT",
        "配电",
        "照明",
        "电气",
        "ELT",
        "FE_",
        "消防电气",
        "火灾报警",
        "distribution",
    ],
    "暖通": [
        "HVAC",
        "DUCT",
        "PIPE",
        "给排水",
        "暖通",
        "水暖",
        "MEP",
        "PLUMB",
        "VENT",
        "风管",
        "水管",
        "水消防",
        "消防系统",
        "给水系统",
        "喷淋",
        "风口",
        "A_HVAC",
    ],
    # 建筑关键词权重最低（所有专业图纸都有 AXIS/DIM）
    "建筑": ["ARCH", "DWG_", "墙", "门", "窗", "房间", "楼板"],
}

# 通用层关键词（所有图纸都可能有 → 权重 0，仅当无其他信号时兜底）
_COMMON_LAYER_TOKENS = {"AXIS", "DIM_", "TEXT", "图层", "图框", "C-SHET"}

# 实体类型分布特征 → 类型（基于解析后的实体统计）
# key = "type比例过高即判为此类"
_ENTITY_DOMINANCE_RULES: Dict[str, list] = {
    "结构": ["beam", "column", "slab", "rebar", "foundation"],
}

# 实体类型 → 非疏散图的辅助信号（出现即加结构/电气/暖通分）
_ENTITY_HINTS: Dict[str, str] = {
    "beam": "结构",
    "column": "结构",
    "slab": "结构",
    "rebar": "结构",
    "foundation": "结构",
    "reinforcement": "结构",
    "HVAC_EQUIPMENT": "暖通",
    "hvac_equipment": "暖通",
    "pipe": "暖通",
    "pump": "暖通",
    "fire_alarm": "电气",
    "electrical": "电气",
    "distribution_box": "电气",
}

# Layer 关键词 → 类型（设计院自定义命名常见模式）
# 放在 _LAYER_RULES 之后、未知兜底之前，用于处理 conf=0 的 hash ID 文件
_LAYER_PATTERN_HINTS: Dict[str, list] = {
    "结构": [
        "BEAM",
        "COLU",
        "SLAB",
        "REIN",
        "REBAR",
        "PUB_DIM",
        "梁",
        "柱",
        "板",
        "钢筋",
        "结构",
        "详图",
        "1-梁",
        "2-板",
        "3-柱",
        "7-详图",
    ],
    "暖通": [
        "P-KX",
        "A_风口",
        "A_风口",
        "A_HVAC",
        "DUCT",
        "VENT",
        "风管",
        "水管",
        "消防系统",
        "给水系统",
        "喷淋",
    ],
    "电气": [
        "EL_",
        "EL",
        "ELEC",
        "distribution",
        "配电",
        "照明",
        "火灾报警",
        "气体灭火",
    ],
}


def classify_drawing(
    filename: str,
    layer_names: list = None,
    entity_types: list = None,
    file_size_mb: float = 0,
) -> Dict[str, Any]:
    """
    判断图纸类型

    参数:
        filename: 图纸文件名
        layer_names: 图纸中的图层名列表（可选）
        entity_types: 实体类型列表（可选）
        file_size_mb: 文件大小 MB（可选，辅助判断）

    返回:
        {
            "type": "建筑|结构|电气|暖通|未知",
            "confidence": 0.0~1.0,
            "reason": "判断依据",
            "suggested_action": "推荐处理方式"
        }
    """
    filename_lower = filename.lower()

    scores: Dict[str, int] = {}
    reasons: Dict[str, list] = {}

    # 1. 文件名匹配（权重最高，一次命中即盖过 layer 总和）
    for dtype, keywords in _FILENAME_RULES.items():
        for kw in keywords:
            if _kw_match(kw, filename_lower):
                scores[dtype] = scores.get(dtype, 0) + 10
                reasons.setdefault(dtype, []).append(f"文件名含'{kw}'")

    # 2. 图层名匹配（非建筑关键词权重 1.0，建筑通用层权重 0.3）
    # filename 已命中则跳过 layer 匹配，避免信号稀释
    if not scores and layer_names:
        for dtype, keywords in _LAYER_RULES.items():
            weight = 1.0 if dtype != "建筑" else 0.3
            for kw in keywords:
                for layer in layer_names:
                    if _kw_match(kw, layer.lower()):
                        scores[dtype] = scores.get(dtype, 0) + weight
                        reasons.setdefault(dtype, []).append(f"图层'{layer}'匹配'{kw}'")
                        break  # 每个关键词只计一次

    # 3. 实体类型提示（非疏散图辅助信号）—— 仅 filename 无信号时启用
    if not scores and entity_types:
        type_counts: Dict[str, int] = {}
        for et in entity_types[:2000]:
            type_counts[et] = type_counts.get(et, 0) + 1
        total = sum(type_counts.values()) or 1
        # 实体类型比例启发式：某类结构实体占比 > 15% 即判为结构
        for dtype, expected in _ENTITY_DOMINANCE_RULES.items():
            dom_count = sum(type_counts.get(e, 0) for e in expected)
            if dom_count / total > 0.15:
                scores[dtype] = scores.get(dtype, 0) + 2
                reasons.setdefault(dtype, []).append(f"结构实体占比{dom_count/total*100:.0f}%")
        # 实体类型提示（出现即加分，权重低）
        seen = set()
        for et in entity_types[:2000]:
            hint = _ENTITY_HINTS.get(et)
            if hint and hint not in seen:
                seen.add(hint)
                scores[hint] = scores.get(hint, 0) + 1
                reasons.setdefault(hint, []).append(f"含实体'{et}'")

    # 4. Layer 模式启发式（设计院自定义命名）—— 权重低，兜底用
    if layer_names and not scores:
        for dtype, patterns in _LAYER_PATTERN_HINTS.items():
            matched_layers = []
            for pattern in patterns:
                for layer in layer_names:
                    if _kw_match(pattern, layer.lower()):
                        matched_layers.append(layer)
                        break
            if matched_layers:
                scores[dtype] = scores.get(dtype, 0) + len(matched_layers)
                reasons.setdefault(dtype, []).extend(
                    f"图层'{layer}'匹配模式" for layer in matched_layers[:3]
                )

    # 判定
    if not scores:
        return {
            "type": "未知",
            "confidence": 0.0,
            "reason": "无特征可判定",
            "suggested_action": "按通用图纸处理",
        }

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score >= 3:
        confidence = min(best_score / 6.0, 1.0)
        reason = "; ".join(reasons.get(best_type, [])[:3])
    elif best_score >= 2:
        confidence = 0.5
        reason = "; ".join(reasons.get(best_type, [])[:3])
    else:
        confidence = 0.3
        reason = "; ".join(reasons.get(best_type, [])[:3])

    # 建议
    if best_type == "结构":
        action = "结构图暂不支持AI审查，可渲染预览但跳过原子函数"
    elif best_type == "电气":
        action = "电气图暂不支持AI审查，可渲染预览但跳过原子函数"
    elif best_type == "暖通":
        action = "暖通图暂不支持AI审查，可渲染预览但跳过原子函数"
    elif best_type == "建筑":
        action = "标准建筑图，正常审查"
    else:
        action = "未知类型，按通用图纸处理"

    return {
        "type": best_type,
        "confidence": round(confidence, 2),
        "reason": reason,
        "suggested_action": action,
    }


# ── P121 图幅类型识别（平面图 / 立面剖面 / 不可审查 / 未知）──────
# 阈值是验收口径，R1/R2/R4 不得调整；R3 本轮新增「平面证据」门槛，见下。
#   R1 立面剖面：立面∪剖面图元占比 ≥30% 且命中图层 ≥2 且
#                (立面 ≥10% 或 剖面 ≥10%) 且 闭合面占比 <3%
#   R2 不可审查：实际用到图层 ≤2 且 单层占比 ≥95% 且 ≤1单位微图元 ≥70%
#                且 标注占比 <1% 且 图元数 ≥1000
#   R3 平面图：未触发 R1/R2 且（平面词元图层 ≥2 或（闭合面 ≥3% 且 标注 ≥1%））
#               且具备平面证据（见下）；仅图层词元不足以判平面
#   R4 其余 → 未知：正常审查 + low_confidence
#
# 为什么 R3 需要「平面证据」：立面图/大样图的图层名同样会含 door/window/wall/axis
# 等平面词元（villa-details 命中 7 个），单靠图层词元会把立面图误判为平面图。
# 平面证据取以下任一：
#   A. 平面型标注：房间名（2–8 字纯中文）、门窗编号、尺寸数字（≥3 位或带小数）、
#      DIMENSION 图元；
#   B. 房间状闭合多边形：闭合多段线 ≥10 个且面积 ≥0.5㎡ 的占比 ≥15%
#      （单位按 LINE 长度中位数自动判定 mm/m）；
#   C. 完全无文字标注（无从用标注否定平面）→ 保留图层词元判据。
# 三条都不满足 → 判未知/低置信，不进入平面审查域。

_SHEET_ELEV_TOKENS = ("elev", "elevation", "立面")
_SHEET_SECT_TOKENS = ("sect", "section", "剖面")
# 立面/剖面简写一律强制词元边界，避免 ELEV 命中 ELEVATOR / LEVEL / fire_elevator
_SHEET_FORCE_BOUNDARY_TOKENS = {"elev", "sect"}

# 平面图强信号图层词元（墙体/门窗/房间/楼梯/家具/轴网/楼板/分区）
_SHEET_PLAN_TOKENS = (
    "plan",
    "平面",
    "wall",
    "墙",
    "door",
    "门",
    "window",
    "窗",
    "room",
    "房间",
    "column",
    "柱",
    "partition",
    "stair",
    "楼梯",
    "furniture",
    "家具",
    "floor",
    "楼板",
    "axis",
    "轴",
)

# 标注类图元（文字/尺寸标注/引线）；DIMENSION 与 TEXT 同属标注
_SHEET_ANNOTATION_TYPES = {
    "TEXT",
    "MTEXT",
    "DIMENSION",
    "LEADER",
    "MLEADER",
    "ATTRIB",
    "ATTDEF",
}
# 线状/面状微图元类型（描线矢量化产物通常由这些极短图元构成）
_SHEET_GEOMETRY_TYPES = {
    "LINE",
    "ARC",
    "LWPOLYLINE",
    "POLYLINE",
    "CIRCLE",
    "ELLIPSE",
    "SOLID",
}

# ── R3 平面证据（见上方注释 A/B/C）──────────────────────────
# 尺寸数字：≥3 位整数或带小数（排除轴号 1–2 位数字），可带 × 宽×高
_SHEET_DIM_NUM_RE = re.compile(
    r"^[±\-+]?(?:\d{3,}(?:\.\d+)?|\d+(?:\.\d+)+)(?:\s*[xX×]\s*\d+(?:\.\d+)?)?$"
)
# 门窗编号：字母前缀 + 2–4 位数字，如 HM1220 / HFM1220(6) / M1020
_SHEET_DOOR_CODE_RE = re.compile(
    r"(?<![A-Za-z])(?:HFM|FM|MLC|TLM|PYC|GC|LC|TC|HM|M|C)[甲乙丙丁]?"
    r"\s?\d{2,4}(?:[（(]\d+[）)])?(?![A-Za-z0-9])",
    re.I,
)
# 房间名：2–8 字纯中文
_SHEET_ROOM_LABEL_RE = re.compile(r"^[\u4e00-\u9fff]{2,8}$")

_SHEET_ROOM_MIN_AREA_M2 = 0.5   # 房间状闭合面的最小面积
_SHEET_ROOM_MIN_POLYGONS = 10   # 闭合面数量下限（少于该数不构成平面轮廓）
_SHEET_ROOM_MIN_RATIO = 0.15    # 房间状闭合面占全部闭合面的比例下限
_SHEET_MM_LINE_MEDIAN = 50.0    # LINE 长度中位数 ≥ 该值 → 图纸单位为 mm


def _polygon_area(props: dict) -> float:
    """闭合多段线面积（图纸原始单位），退化多边形返回 0。"""
    pts = props.get("points") or []
    if len(pts) < 3:
        return 0.0
    xy = []
    for p in pts:
        if isinstance(p, dict):
            xy.append((float(p.get("x", 0) or 0), float(p.get("y", 0) or 0)))
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            xy.append((float(p[0] or 0), float(p[1] or 0)))
        else:
            return 0.0
    s = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _area_unit_scale(line_lengths: list) -> float:
    """按 LINE 长度中位数推断面积换算系数：mm → 1e-6，m → 1。"""
    if not line_lengths:
        return 1.0
    return 1e-6 if statistics.median(line_lengths) >= _SHEET_MM_LINE_MEDIAN else 1.0


_SHEET_TYPE_LABELS = {
    "plan": "平面图",
    "elevation_section": "立面/剖面图",
    "unreviewable": "不可审查（描线/矢量化产物）",
    "unknown": "未知图幅",
}


def _prim_get(prim, name: str, default=None):
    """兼容 RawPrimitive 对象与 dict 读取字段。"""
    if isinstance(prim, dict):
        return prim.get(name, default)
    return getattr(prim, name, default)


def _layer_matches_any(layer_lower: str, tokens) -> bool:
    for kw in tokens:
        if _kw_match(kw, layer_lower, force_boundary=kw in _SHEET_FORCE_BOUNDARY_TOKENS):
            return True
    return False


def classify_sheet_type(primitives: list) -> Dict[str, Any]:
    """判定图幅类型（平面图 / 立面剖面 / 不可审查 / 未知）。

    只依据图元分布与图层名构成，不改变语义分析与规则判定：
    - 立面/剖面、描线矢量化产物 → ``scope_mode="non_plan"``，不出 findings、
      不计入覆盖率分母；
    - 未知 → 正常审查，标记 ``low_confidence=True``，判据不放宽；
      **仅命中平面词元图层但无平面证据（标注/房间状闭合面）的，判未知而非平面**；
    - 平面图 → ``scope_mode="plan"``。

    参数:
        primitives: 解析后的图元列表（RawPrimitive 或 dict）

    返回:
        {
            "sheet_type": "plan|elevation_section|unreviewable|unknown",
            "label": 中文标签,
            "rule": "R1|R2|R3|R4",
            "scope_mode": "plan|non_plan|unknown",
            "reviewable": bool,
            "low_confidence": bool,
            "confidence": float,
            "evidence": [判定证据…],
            "metrics": {…},
        }
    """
    n = len(primitives or [])
    empty = {
        "sheet_type": "unknown",
        "label": _SHEET_TYPE_LABELS["unknown"],
        "rule": "R4",
        "scope_mode": "unknown",
        "reviewable": True,
        "low_confidence": True,
        "confidence": 0.0,
        "evidence": ["无图元，无法判定图幅类型"],
        "metrics": {"total": 0},
    }
    if n == 0:
        return empty

    layer_counts: Dict[str, int] = {}
    elev_sect_layer_hits: set = set()
    elev_layer_hits: set = set()
    sect_layer_hits: set = set()
    plan_layer_hits: set = set()
    elev_count = 0
    sect_count = 0
    elev_sect_count = 0
    closed_count = 0
    annotation_count = 0
    micro_count = 0
    text_count = 0
    plan_annotation_count = 0
    closed_polygon_count = 0
    closed_area_raw: list = []
    line_lengths: list = []

    # 图层词元结果按图层缓存，O(unique_layer) 次匹配
    layer_flags: Dict[str, Dict[str, bool]] = {}

    for p in primitives:
        layer = (_prim_get(p, "layer", "") or "") or ""
        layer_lower = layer.lower()
        layer_counts[layer] = layer_counts.get(layer, 0) + 1

        flags = layer_flags.get(layer_lower)
        if flags is None:
            is_elev = _layer_matches_any(layer_lower, _SHEET_ELEV_TOKENS)
            is_sect = _layer_matches_any(layer_lower, _SHEET_SECT_TOKENS)
            flags = {
                "elev": is_elev,
                "sect": is_sect,
                "plan": _layer_matches_any(layer_lower, _SHEET_PLAN_TOKENS),
            }
            layer_flags[layer_lower] = flags
        if flags["elev"]:
            elev_layer_hits.add(layer)
            elev_count += 1
        if flags["sect"]:
            sect_layer_hits.add(layer)
            sect_count += 1
        if flags["elev"] or flags["sect"]:
            elev_sect_layer_hits.add(layer)
            elev_sect_count += 1
        if flags["plan"]:
            plan_layer_hits.add(layer)

        dxf_type = _prim_get(p, "dxf_type", "") or ""
        props = _prim_get(p, "properties", {}) or {}

        if dxf_type in ("LWPOLYLINE", "POLYLINE") and (
            props.get("closed") or (props.get("point_count") or 0) >= 4
        ):
            # 闭合面：显式闭合或 ≥4 顶点（矩形/多边形面），与 T5 诊断口径一致
            closed_count += 1
        if dxf_type in ("LWPOLYLINE", "POLYLINE") and props.get("closed"):
            area_raw = _polygon_area(props)
            if area_raw > 0:
                closed_polygon_count += 1
                closed_area_raw.append(area_raw)
        if dxf_type in _SHEET_ANNOTATION_TYPES:
            annotation_count += 1
        if dxf_type in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
            text = str(props.get("text") or props.get("content") or "").strip()
            if text:
                text_count += 1
                if (
                    _SHEET_ROOM_LABEL_RE.match(text)
                    or _SHEET_DIM_NUM_RE.match(text)
                    or _SHEET_DOOR_CODE_RE.search(text)
                ):
                    plan_annotation_count += 1
        elif dxf_type == "DIMENSION":
            plan_annotation_count += 1
        if dxf_type == "LINE":
            length = props.get("length")
            if length is None:
                bbox = _prim_get(p, "bbox", {}) or {}
                length = max(
                    abs(bbox.get("width", 0) or 0), abs(bbox.get("height", 0) or 0)
                )
            try:
                length = abs(float(length))
            except (TypeError, ValueError):
                length = 0.0
            if length > 0:
                line_lengths.append(length)
        if dxf_type in _SHEET_GEOMETRY_TYPES:
            bbox = _prim_get(p, "bbox", {}) or {}
            if dxf_type == "LINE":
                length = props.get("length")
                dim = abs(length) if length is not None else max(
                    abs(bbox.get("width", 0) or 0), abs(bbox.get("height", 0) or 0)
                )
            else:
                dim = max(
                    abs(bbox.get("width", 0) or 0), abs(bbox.get("height", 0) or 0)
                )
            if dim <= 1:
                micro_count += 1

    used_layers = len(layer_counts)
    max_layer_share = max(layer_counts.values()) / n
    elevation_ratio = elev_count / n
    section_ratio = sect_count / n
    elev_sect_ratio = elev_sect_count / n
    closed_ratio = closed_count / n
    annotation_ratio = annotation_count / n
    micro_ratio = micro_count / n
    area_scale = _area_unit_scale(line_lengths)
    room_like_count = sum(
        1 for a in closed_area_raw if a * area_scale >= _SHEET_ROOM_MIN_AREA_M2
    )
    room_like_ratio = (
        room_like_count / closed_polygon_count if closed_polygon_count else 0.0
    )
    geometry_plan = (
        closed_polygon_count >= _SHEET_ROOM_MIN_POLYGONS
        and room_like_ratio >= _SHEET_ROOM_MIN_RATIO
    )

    metrics = {
        "total": n,
        "used_layers": used_layers,
        "max_layer_share": round(max_layer_share, 4),
        "elevation_ratio": round(elevation_ratio, 4),
        "section_ratio": round(section_ratio, 4),
        "elevation_section_ratio": round(elev_sect_ratio, 4),
        "elevation_section_layers": len(elev_sect_layer_hits),
        "elevation_layers": len(elev_layer_hits),
        "section_layers": len(sect_layer_hits),
        "plan_layer_count": len(plan_layer_hits),
        "closed_face_ratio": round(closed_ratio, 4),
        "annotation_ratio": round(annotation_ratio, 4),
        "micro_primitive_ratio": round(micro_ratio, 4),
        "text_count": text_count,
        "plan_annotation_count": plan_annotation_count,
        "closed_polygon_count": closed_polygon_count,
        "room_like_polygon_count": room_like_count,
        "room_like_polygon_ratio": round(room_like_ratio, 4),
        "area_unit": "mm" if area_scale == 1e-6 else "m",
        "top_layers": sorted(layer_counts.items(), key=lambda kv: -kv[1])[:5],
    }

    def _result(sheet_type: str, rule: str, confidence: float, evidence: list):
        scope_mode = "non_plan" if sheet_type in ("elevation_section", "unreviewable") else (
            "plan" if sheet_type == "plan" else "unknown"
        )
        return {
            "sheet_type": sheet_type,
            "label": _SHEET_TYPE_LABELS[sheet_type],
            "rule": rule,
            "scope_mode": scope_mode,
            "reviewable": scope_mode != "non_plan",
            "low_confidence": sheet_type == "unknown",
            "confidence": confidence,
            "evidence": evidence,
            "metrics": metrics,
        }

    # ── R1 立面/剖面图 ──
    if (
        elev_sect_ratio >= 0.30
        and len(elev_sect_layer_hits) >= 2
        and (elevation_ratio >= 0.10 or section_ratio >= 0.10)
        and closed_ratio < 0.03
    ):
        evidence = [
            f"R1 立面∪剖面图元占比 {elev_sect_ratio:.2%} ≥ 30%",
            f"R1 命中立面/剖面图层 {len(elev_sect_layer_hits)} 个 ≥ 2："
            + "、".join(sorted(elev_sect_layer_hits)[:6]),
            f"R1 立面占比 {elevation_ratio:.2%} / 剖面占比 {section_ratio:.2%}"
            f"（至少一项 ≥ 10%）",
            f"R1 闭合面占比 {closed_ratio:.2%} < 3%",
        ]
        return _result("elevation_section", "R1", 0.95, evidence)

    # ── R2 不可审查（描线矢量化产物）──
    if (
        used_layers <= 2
        and max_layer_share >= 0.95
        and micro_ratio >= 0.70
        and annotation_ratio < 0.01
        and n >= 1000
    ):
        evidence = [
            f"R2 实际用到图层 {used_layers} 个 ≤ 2",
            f"R2 单层占比 {max_layer_share:.2%} ≥ 95%",
            f"R2 ≤1单位微图元占比 {micro_ratio:.2%} ≥ 70%",
            f"R2 标注占比 {annotation_ratio:.2%} < 1%",
            f"R2 图元数 {n} ≥ 1000",
        ]
        return _result("unreviewable", "R2", 0.9, evidence)

    # ── R3 平面图 ──
    plan_evidence = []
    if text_count == 0:
        plan_evidence.append("无文字标注：无从以标注否定平面，保留图层词元判据")
    else:
        if plan_annotation_count > 0:
            plan_evidence.append(
                f"平面型标注 {plan_annotation_count} 条（房间名/门窗编号/尺寸数字/尺寸标注）"
            )
        if geometry_plan:
            plan_evidence.append(
                f"房间状闭合多边形 {room_like_count}/{closed_polygon_count}，"
                f"≥{_SHEET_ROOM_MIN_AREA_M2}㎡ 占 {room_like_ratio:.0%} ≥ "
                f"{_SHEET_ROOM_MIN_RATIO:.0%}（单位 {metrics['area_unit']}）"
            )

    r3_triggered = len(plan_layer_hits) >= 2 or (
        closed_ratio >= 0.03 and annotation_ratio >= 0.01
    )
    if r3_triggered and plan_evidence:
        evidence = []
        if len(plan_layer_hits) >= 2:
            evidence.append(
                f"R3 平面词元图层 {len(plan_layer_hits)} 个 ≥ 2："
                + "、".join(sorted(plan_layer_hits)[:6])
            )
        if closed_ratio >= 0.03 and annotation_ratio >= 0.01:
            evidence.append(
                f"R3 闭合面占比 {closed_ratio:.2%} ≥ 3% 且 标注占比 "
                f"{annotation_ratio:.2%} ≥ 1%"
            )
        evidence.extend(f"R3 平面证据：{e}" for e in plan_evidence)
        evidence.append(
            f"R3 未触发 R1（立面∪剖面 {elev_sect_ratio:.2%} / 闭合面 {closed_ratio:.2%}）"
            f"与 R2（图层 {used_layers} / 微图元 {micro_ratio:.2%}）"
        )
        return _result("plan", "R3", 0.85, evidence)

    if r3_triggered:
        # 触发了图层/几何平面阈值，但图上没有任何平面证据 → 未知/低置信
        evidence = [
            f"R4 图层/几何触发平面阈值（平面词元图层 {len(plan_layer_hits)} 个"
            f" / 闭合面 {closed_ratio:.2%} / 标注 {annotation_ratio:.2%}），"
            "但缺少平面证据",
            f"R4 文字 {text_count} 条，其中平面型标注 {plan_annotation_count} 条"
            "（房间名/门窗编号/尺寸数字/尺寸标注）",
            f"R4 房间状闭合多边形 {room_like_count}/{closed_polygon_count}"
            f"（≥{_SHEET_ROOM_MIN_AREA_M2}㎡ 占 {room_like_ratio:.0%}，"
            f"低于 {_SHEET_ROOM_MIN_RATIO:.0%}）",
            "R4 → 判未知/低置信，不进入平面审查域",
        ]
        return _result("unknown", "R4", 0.0, evidence)

    # ── R4 未知 ──
    evidence = [
        f"R4 立面∪剖面 {elev_sect_ratio:.2%} < 30% 或命中图层 "
        f"{len(elev_sect_layer_hits)} < 2 或闭合面 {closed_ratio:.2%} ≥ 3%",
        f"R4 图层 {used_layers} / 单层 {max_layer_share:.2%} / 微图元 {micro_ratio:.2%}"
        f" / 标注 {annotation_ratio:.2%}（未满足不可审查阈值）",
        f"R4 平面词元图层 {len(plan_layer_hits)} < 2 且（闭合面 {closed_ratio:.2%} < 3%"
        f" 或 标注 {annotation_ratio:.2%} < 1%）",
    ]
    return _result("unknown", "R4", 0.0, evidence)


# ── 损坏/无效文件检测 ────────────────────────────────────


def is_likely_corrupt(filepath: str, min_size_bytes: int = 10000) -> Dict[str, Any]:
    """
    检测文件是否疑似损坏或占位文件
    """
    from pathlib import Path

    path = Path(filepath)
    size = path.stat().st_size

    # 先检查 DXF 文件头（可能文件大但无有效结构）
    try:
        with open(filepath, "rb") as f:
            header = f.read(1024)
        if b"SECTION" not in header and b"HEADER" not in header:
            if size >= min_size_bytes:
                return {
                    "corrupt": True,
                    "reason": f"缺少 DXF 标准头（SECTION/HEADER），文件 {size}B 但结构无效",
                    "recoverable": False,
                }
    except Exception:
        return {"corrupt": True, "reason": "无法读取文件头", "recoverable": False}

    # 过小的 DXF：仅当结构不完整时才判损坏
    # 单房间/局部详图的合法 DXF 可以只有几百字节（本引擎反向生成的简易房间
    # 仅 ~754B），不能只按体积否掉；有 ENTITIES + EOF 闭合即可视为有效
    if size < min_size_bytes:
        try:
            with open(filepath, "rb") as f:
                body = f.read()
        except Exception:
            body = b""
        if b"ENTITIES" in body and b"EOF" in body:
            return {"corrupt": False, "reason": "", "recoverable": True}
        return {
            "corrupt": True,
            "reason": f"文件大小仅 {size} 字节（有效 DXF 通常 >{min_size_bytes}B），疑似占位或损坏",
            "recoverable": False,
        }

    return {"corrupt": False, "reason": "", "recoverable": True}


# ── P121（视图级延伸）：混合图集内部按 Y 带分区 ───────────────────────
# 部分真实 DXF 在同一图纸里同时摆放「平面图区」和「立面/剖面/大样区」。
# 全局 `classify_sheet_type` 只能给出整张图纸一个 scope_mode；
# 当整体被误判为 plan 时（如 Stadion），非平面区里扫线派生的假房间/假走廊
# 会照常进入逐实体判定，产出一堆无意义的 findings。
#
# 本函数通过几何聚类 + 内容得分，将图元按 Y 坐标拆成多个子视框，并对每个
# 子视框给出 ``scope_mode``；用于 ``fp_rate_audit.py`` 做实体级局部过滤。
# 不改变绘图解析主链路；返回空列表表示无需按视图拆分（单视幅图集）。

_VIEW_GAP_MM = 5_000       # 子视图间距阈值（mm）：两簇之间 >5m 视为不同视框
_VIEW_MIN_PRIMS = 30        # 形成有效子视框所需最少图元数
_VIEW_NON_PLAN_SCORE = 20   # 得分 < 此值 → non_plan（非平面区噪声多、缺乏平面证据）
_VIEW_LINEJUMP_THRESH = 20  # LINE% 突变阈值（pp）：相邻带差值 ≥ 此值则切分
_VIEW_LINE_STRIP_MM = 3000  # LINE% 滑动窗口带高（mm）
_VIEW_MIN_SPLIT_MM = 10_000 # 仅对跨度 ≥10m 的簇做 LINE% 二次切分
_VIEW_LONG_HLINE_PENALTY = 6  # 每根超长横线扣分（>=0.2n 时触发），提高以压制密集线性网格


def _centroid(p: Any) -> Tuple[float, float]:
    """取单个原始图元的 bbox 中心点；bbox 缺失或非法返回 (nan,nan)。"""
    bb = getattr(p, "bbox", None) or getattr(p, "get", lambda k, default=None: default)("bbox") or {}
    if not isinstance(bb, dict):
        bb = {}
    w = max(float(bb.get("width", 0) or 0), 0.0)
    h = max(float(bb.get("height", 0) or 0), 0.0)
    x = float(bb.get("x", 0) or 0)
    y = float(bb.get("y", 0) or 0)
    if w <= 0 or h <= 0:
        # 退化图元退化为端点中位
        props = getattr(p, "properties", None) or {} or {}
        sp = props.get("start_point")
        ep = props.get("end_point")
        try:
            sx, sy = float(sp["x"] or 0), float(sp["y"] or 0)
            ex, ey = float(ep["x"] or 0), float(ep["y"] or 0)
            return (sx + ex) / 2, (sy + ey) / 2
        except Exception:
            pass
        return float('nan'), float('nan')
    return x + w / 2, y + h / 2


def _cluster_y_by_gap(coords: list, gap: float) -> List[List[float]]:
    """把一维坐标按 gap 阈值聚类（相邻差值 > gap 则切段），只保留长度 >=2 的段。"""
    if not coords:
        return []
    coords = sorted(coords)
    clusters: List[List[float]] = [[coords[0]]]
    for c in coords[1:]:
        if c - clusters[-1][-1] > gap:
            clusters.append([c])
        else:
            clusters[-1].append(c)
    return [c for c in clusters if len(c) >= 2]


def classify_view_frames(primitives: list) -> List[Dict[str, Any]]:
    """将原始图元按 Y 轴几何密度拆分为若干子视框并判定各自的作用域。

    用途：供外部审计工具做「实体级」scope_mode 覆盖，避免混合图集（plan+section
    共处一 DXF）中非平面子区的派生实体污染 findings。

    算法步骤：
      1. 收集所有有合法 bbox 的原始图元的质心 (cx,cy)；
      2. 按 cy 升序排序后做「gap 聚类」（≥2 个坐标且相邻差值 > _VIEW_GAP_MM
         才切段），每段代表一张可能含多个局部的子视框；
      3. 对每一段，统计其中的图元类型比例和内容词元作为得分依据；
      4. 根据得分决定是否标记为 plan/non_plan/unknown。

    返回格式：
      [
          {
              "cluster_id": int,
              "y_min": float, "y_max": float,
              "primitive_count": int,
              "scope_mode": "plan|non_plan|unknown",
              "score": int,
              "evidence": List[str],
          },
          ...
      ]
    """
    n = len(primitives or [])
    if n < 10:
        return []

    centroids: List[Tuple[float, float, Any]] = []
    for p in primitives:
        cx, cy = _centroid(p)
        if math.isnan(cx) or math.isnan(cy):
            continue
        centroids.append((cx, cy, p))

    if len(centroids) < _VIEW_MIN_PRIMS:
        return []

    # 1. 按 cy 聚类（初识切分）
    ys_sorted = [cy for _, cy, _ in centroids]
    raw_clusters = _cluster_y_by_gap(ys_sorted, _VIEW_GAP_MM)
    if len(raw_clusters) <= 1:
        pass
    elif len(raw_clusters) <= 1:
        return []

    # 2. 对每个初识簇做二次切分：跨度 ≥10m 的簇，用 LINE% 突变点进一步拆分
    #    原因：如 Stadion 图元在 Y 轴连续分布（无 >5m 断层），但内部存在明显
    #    视图类型切换（plan LINE%=30% → section LINE%=76%+）。
    refined_bounds: List[Tuple[float, float]] = []
    for cl in raw_clusters:
        lo, hi = min(cl), max(cl)
        span = hi - lo
        if span >= _VIEW_MIN_SPLIT_MM:
            # 滑动窗口检测 LINE% 跳变点
            step = _VIEW_LINE_STRIP_MM
            prev_line_pct: Optional[float] = None
            split_ys: List[float] = [lo]
            y = lo
            while y < hi:
                w_lo, w_hi = y, min(y + step, hi)
                strip_prims = [p for (_, cy, p) in centroids
                               if w_lo <= cy <= w_hi]
                n_total = len(strip_prims)
                n_line = sum(1 for p in strip_prims
                             if (getattr(p, "dxf_type", "") or "") == "LINE")
                line_pct = n_line / n_total * 100 if n_total > 0 else 0
                if prev_line_pct is not None and line_pct - prev_line_pct >= _VIEW_LINEJUMP_THRESH:
                    split_ys.append(round((y + w_hi) / 2))
                prev_line_pct = line_pct
                y += step
            split_ys.append(hi)
            # 去重 + 排序 + 合并相邻重复点
            split_ys = sorted(set(split_ys))
            merged: List[float] = [split_ys[0]]
            for sy in split_ys[1:]:
                if sy - merged[-1] >= _VIEW_LINE_STRIP_MM:
                    merged.append(sy)
            for i in range(len(merged) - 1):
                refined_bounds.append((merged[i], merged[i + 1]))
        else:
            refined_bounds.append((lo, hi))

    cluster_bounds = refined_bounds
    cent_to_cluster: Dict[int, int] = {}
    for i, (_, cy, _) in enumerate(centroids):
        for ci, (lo, hi) in enumerate(cluster_bounds):
            if lo <= cy <= hi:
                cent_to_cluster[i] = ci
                break

    # 3. 对每个 cluster 打分
    RESULTS: List[Dict[str, Any]] = []
    room_keywords = ("房间", "厅", "室", "卫", "厨", "卧", "套", "厕")
    door_keywords = ("门", "door", "exit", "防火门")
    floor_keywords = ("楼梯", "台阶", "平台", "层")
    elev_keywords = ("立面", "elev", "section", "剖面")

    for ci, (lo, hi) in enumerate(cluster_bounds):
        span = hi - lo
        if span < 5000:
            continue

        prims_in_cl = [
            centroids[i][2] for i in range(len(centroids))
            if cent_to_cluster.get(i) == ci
        ]
        n_prim = len(prims_in_cl)

        closed_polygon_n = 0
        room_area_total = 0.0
        plan_text_n = 0
        dim_text_n = 0
        door_exit_n = 0
        stair_floor_n = 0
        elev_n = 0
        long_hlines_n = 0  # 超长横线（立面/剖面常见）

        for p in prims_in_cl:
            t = getattr(p, "dxf_type", "") or ""
            pr = getattr(p, "properties", None) or {} or {}

            if t in ("LWPOLYLINE", "POLYLINE"):
                pts = pr.get("points")
                if pts and len(pts) >= 3:
                    area = _polygon_area({"points": pts})
                    if area > 0:
                        closed_polygon_n += 1
                        if area * 1e-6 >= 0.5:  # mm² → m²
                            room_area_total += area * 1e-6
            elif t in ("TEXT", "MTEXT"):
                val = str(pr.get("text") or pr.get("content") or "").strip()
                if val:
                    vlow = val.lower()
                    if any(kw in val for kw in room_keywords):
                        plan_text_n += 1
                    if any(kw in vlow for kw in door_keywords):
                        door_exit_n += 1
                    if any(kw in vlow for kw in floor_keywords):
                        stair_floor_n += 1
                    if any(kw in vlow for kw in elev_keywords):
                        elev_n += 1
            elif t == "DIMENSION":
                dim_text_n += 1
            elif t == "LINE":
                length = pr.get("length")
                bb = getattr(p, "bbox", {}) or {}
                hdim = abs(bb.get("height", 0) or 0)
                wdim = abs(bb.get("width", 0) or 0)
                try:
                    length = abs(float(length))
                except (TypeError, ValueError):
                    length = max(wdim, hdim)
                if length >= 5000 and hdim < 300:
                    long_hlines_n += 1

        score = 0
        evidence: List[str] = []

        if closed_polygon_n >= 8 and room_area_total >= 2.0:
            score += min(closed_polygon_n, 30) * 2
            evidence.append(f"closed_polygons={closed_polygon_n},room_area≈{room_area_total:.1f}㎡")
        if plan_text_n > 0:
            score += plan_text_n * 3
            evidence.append(f"room_texts={plan_text_n}")
        if dim_text_n >= 5:
            score += dim_text_n * 2
            evidence.append(f"dims={dim_text_n}")
        if door_exit_n > 0:
            score += door_exit_n * 3
            evidence.append(f"door_texts={door_exit_n}")
        if stair_floor_n > 0:
            score += stair_floor_n
            evidence.append(f"stair_texts={stair_floor_n}")
        if elev_n > 0:
            score -= elev_n * 10
            evidence.append(f"elev_texts={elev_n}(−)")
        if long_hlines_n > n_prim * 0.2:
            score -= min(long_hlines_n, 30) * _VIEW_LONG_HLINE_PENALTY
            evidence.append(f"long_h_lines={long_hlines_n}(−)")
        density = n_prim / max(span / 1000.0, 1)
        if density < 3:
            score -= 10
            evidence.append(f"density={density:.1f}/m(<)")

        effective_scope = "plan"
        if score < _VIEW_NON_PLAN_SCORE:
            effective_scope = "non_plan"
        elif score < _VIEW_NON_PLAN_SCORE + 10:
            effective_scope = "unknown"
            evidence.append("borderline_score")

        RESULTS.append({
            "cluster_id": ci,
            "y_min": round(lo, 1),
            "y_max": round(hi, 1),
            "span_mm": round(span, 1),
            "primitive_count": n_prim,
            "scope_mode": effective_scope,
            "score": int(score),
            "evidence": evidence,
        })

    trimmed: List[Dict[str, Any]] = []
    for r in RESULTS:
        if r["primitive_count"] < 10 and r["scope_mode"] != "plan":
            continue
        trimmed.append(r)
    return trimmed
