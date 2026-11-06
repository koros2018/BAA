"""
P121 Phase 1: 图纸类型分类器
基于图层名 + 实体类型 + 文件名关键词判断图纸类型（建筑/结构/电气/给排水/暖通/其他）
"""

import re
from typing import Dict, Any

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
# 阈值是验收口径，不得调整：
#   R1 立面剖面：立面∪剖面图元占比 ≥30% 且命中图层 ≥2 且
#                (立面 ≥10% 或 剖面 ≥10%) 且 闭合面占比 <3%
#   R2 不可审查：实际用到图层 ≤2 且 单层占比 ≥95% 且 ≤1单位微图元 ≥70%
#                且 标注占比 <1% 且 图元数 ≥1000
#   R3 平面图：未触发 R1/R2 且（平面词元图层 ≥2 或（闭合面 ≥3% 且 标注 ≥1%））
#   R4 其余 → 未知：正常审查 + low_confidence

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
        if dxf_type in _SHEET_ANNOTATION_TYPES:
            annotation_count += 1
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
    if len(plan_layer_hits) >= 2 or (closed_ratio >= 0.03 and annotation_ratio >= 0.01):
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
        evidence.append(
            f"R3 未触发 R1（立面∪剖面 {elev_sect_ratio:.2%} / 闭合面 {closed_ratio:.2%}）"
            f"与 R2（图层 {used_layers} / 微图元 {micro_ratio:.2%}）"
        )
        return _result("plan", "R3", 0.85, evidence)

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
