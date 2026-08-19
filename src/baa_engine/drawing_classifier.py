"""
P121 Phase 1: 图纸类型分类器
基于图层名 + 实体类型 + 文件名关键词判断图纸类型（建筑/结构/电气/给排水/暖通/其他）
"""

import re
from typing import Dict, Any

# ── 分类规则 ──────────────────────────────────────────────

# 文件名关键词 → 类型（优先级从高到低）
_FILENAME_RULES: Dict[str, list] = {
    "结构": ["结构", "STR", "structure", "梁", "柱", "板", "基础", "基础", "配筋", "结构图"],
    "电气": ["电气", "配电", "动力", "照明", "火灾自动报警", "消防", "气体灭火", "EL", "electric"],
    "暖通": ["暖通", "通风", "HVAC", "空调", "给排水", "消防水", "水消防", "给排水", "MEP", "水暖"],
    "建筑": ["建筑", "ARCH", "architectural", "平面", "立面", "剖面", "楼层", "总平面"],
}

# 图层名关键词 → 类型
_LAYER_RULES: Dict[str, list] = {
    "结构": ["STR_", "BEAM", "COLUMN", "SLAB", "WALL_STR", "结构", "STR_LAYER", "柱", "梁", "板"],
    "电气": [
        "EL_",
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
    ],
    "建筑": ["ARCH", "DWG_", "AXIS", "DIM_", "TEXT", "墙", "门", "窗", "房间", "楼板"],
}

# 实体类型分布特征 → 类型（基于解析后的实体统计）
_ENTITY_SIGNATURES: Dict[str, list] = {
    "建筑": ["room", "wall", "door", "window", "staircase", "corridor"],
    "结构": ["beam", "column", "slab", "rebar", "foundation"],
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

    # 1. 文件名匹配（权重最高）
    for dtype, keywords in _FILENAME_RULES.items():
        for kw in keywords:
            if kw.lower() in filename_lower:
                scores[dtype] = scores.get(dtype, 0) + 3
                reasons.setdefault(dtype, []).append(f"文件名含'{kw}'")

    # 2. 图层名匹配
    if layer_names:
        for dtype, keywords in _LAYER_RULES.items():
            for kw in keywords:
                for layer in layer_names:
                    if kw.lower() in layer.lower():
                        scores[dtype] = scores.get(dtype, 0) + 1
                        reasons.setdefault(dtype, []).append(f"图层'{layer}'匹配'{kw}'")
                        break  # 每个关键词只计一次

    # 3. 实体类型签名
    if entity_types:
        entity_set = set(entity_types[:100])  # 采样前100
        for dtype, expected in _ENTITY_SIGNATURES.items():
            match_count = sum(1 for e in expected if e in entity_set)
            if match_count >= 2:
                scores[dtype] = scores.get(dtype, 0) + match_count

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

    # 过小的 DXF 文件（有效 DXF 通常 >10KB）
    if size < min_size_bytes:
        return {
            "corrupt": True,
            "reason": f"文件大小仅 {size} 字节（有效 DXF 通常 >{min_size_bytes}B），疑似占位或损坏",
            "recoverable": False,
        }

    return {"corrupt": False, "reason": "", "recoverable": True}
