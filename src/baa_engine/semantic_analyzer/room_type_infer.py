"""
P109 — 扫线法房间属性自动推断

使用几何特征（面积、宽高比、相邻走廊数、附近文本关键词）推断扫线法
检测到的 room 的 subtype（具体房间类型），增强 KEY_ENTITY_TYPES 覆盖率。

设计原则：
- 不覆盖 LAYER_RULES 已经识别出的具体类型（它们已经 type=pump_room 等）
- 只对扫线法产生的 entity_type="room" 且 subtype="" 的实体生效
- 高置信度命中时同时设置 subtype + 候选 override type
"""

from typing import List, Dict, Any, Optional, Tuple

# ── 房间类型规则（按优先级排列）───────────────────────────────
# area 单位: m², aspect: 长边/短边
# text_keywords: 附近 TEXT 实体中出现的关键词（大小写不敏感）
# min_corridor_adj: 至少相邻多少个 corridor/doorway 才可信
# override_type: True = 命中的高置信度时可将 entity_type 升级为 name
#                False = 仅设置 subtype，保留 entity_type="room"
ROOM_TYPE_RULES: List[Dict[str, Any]] = [
    # ── 楼梯间：中等面积、竖向/竖向矩形、相邻走廊、"楼梯" 关键词 ──
    {
        "name": "staircase",
        "area": (8, 80),
        "aspect": (1.0, 4.0),
        "min_corridor_adj": 1,
        "text_keywords": ["楼梯", "stair", "staircase"],
        "override_type": True,
    },
    # ── 电梯井：小面积、接近方形 ──
    {
        "name": "elevator",
        "area": (3, 15),
        "aspect": (0.5, 2.0),
        "min_corridor_adj": 0,
        "text_keywords": ["电梯", "elevator", "lift"],
        "override_type": True,
    },
    # ── 电梯前室：小面积、相邻楼梯+走廊 ──
    {
        "name": "elevator_lobby",
        "area": (4, 20),
        "aspect": (0.6, 3.0),
        "min_corridor_adj": 1,
        "text_keywords": ["前室", "anteroom", "前厅"],
        "override_type": True,
    },
    # ── 楼梯前室 ──
    {
        "name": "staircase_lobby",
        "area": (4, 25),
        "aspect": (0.6, 3.5),
        "min_corridor_adj": 1,
        "text_keywords": ["楼梯间前室", "staircase_lobby", "楼梯前室"],
        "override_type": True,
    },
    # ── 前室 ──
    {
        "name": "anteroom",
        "area": (4, 20),
        "aspect": (0.6, 3.0),
        "min_corridor_adj": 1,
        "text_keywords": ["前室", "anteroom"],
        "override_type": True,
    },
    # ── 泵房：中大面积、工业空间 ──
    {
        "name": "pump_room",
        "area": (15, 300),
        "aspect": (0.8, 5.0),
        "min_corridor_adj": 0,
        "text_keywords": ["泵房", "pump", "水泵"],
        "override_type": True,
    },
    # ── 设备房/配电房 ──
    {
        "name": "equipment_room",
        "area": (10, 150),
        "aspect": (0.6, 5.0),
        "min_corridor_adj": 0,
        "text_keywords": ["设备", "配电", "机房", "值班", "elevator_machine", "machine_room"],
        "override_type": True,
    },
    # ── 大堂/门厅：大面积、多走廊相邻 ──
    {
        "name": "lobby",
        "area": (60, 600),
        "aspect": (0.5, 6.0),
        "min_corridor_adj": 1,
        "text_keywords": ["大堂", "lobby", "门厅", "大厅", "入口"],
        "override_type": True,
    },
    # ── 卫生间 ──
    {
        "name": "toilet",
        "area": (3, 25),
        "aspect": (0.4, 4.0),
        "min_corridor_adj": 0,
        "text_keywords": ["卫", "wc", "toilet", "厕所", "卫生间", "洗手"],
        "override_type": False,
    },
    # ── 厨房 ──
    {
        "name": "kitchen",
        "area": (6, 40),
        "aspect": (0.5, 4.0),
        "min_corridor_adj": 0,
        "text_keywords": ["厨房", "kitchen", "厨"],
        "override_type": False,
    },
    # ── 卧室/居住 ──
    {
        "name": "bedroom",
        "area": (12, 50),
        "aspect": (0.6, 3.0),
        "min_corridor_adj": 0,
        "text_keywords": ["卧室", "bedroom", "居住", "宿舍", "病房"],
        "override_type": False,
    },
    # ── 储藏/杂物 ──
    {
        "name": "storage",
        "area": (3, 25),
        "aspect": (0.5, 3.5),
        "min_corridor_adj": 0,
        "text_keywords": ["储藏", "storage", "杂物", "仓库"],
        "override_type": False,
    },
    # ── 设备间/管道间（小面积功能空间） ──
    {
        "name": "utility",
        "area": (2, 12),
        "aspect": (0.4, 3.0),
        "min_corridor_adj": 0,
        "text_keywords": ["管道", "utility", "管井"],
        "override_type": False,
    },
]

# 置信度评分权重
_WEIGHT_AREA = 30
_WEIGHT_ASPECT = 15
_WEIGHT_CORRIDOR = 20
_WEIGHT_TEXT = 40
_SCORE_THRESHOLD = 25  # 最低分数才分配 subtype


def _score_area(area_m2: float, lo: float, hi: float) -> int:
    """面积匹配得分：范围 0~30"""
    if area_m2 < lo or area_m2 > hi:
        return 0
    # 中点附近满分，边界递减
    mid = (lo + hi) / 2
    half = (hi - lo) / 2
    dist = abs(area_m2 - mid) / max(half, 1e-6)
    return int(_WEIGHT_AREA * max(0, 1 - dist * 0.5))


def _score_aspect(aspect: float, lo: float, hi: float) -> int:
    """宽高比匹配得分：范围 0~15"""
    if aspect < lo or aspect > hi:
        return 0
    return _WEIGHT_ASPECT


def _score_corridor(adj_count: int, required: int) -> int:
    """走廊相邻数得分"""
    if required == 0:
        return 5 if adj_count == 0 else 0  # 明确要求 0 走廊
    if adj_count >= required:
        return _WEIGHT_CORRIDOR
    return 0


def _score_text(text_hits: int, text_total: int, keywords: List[str]) -> int:
    """附近文本关键词命中得分"""
    if not keywords or text_total == 0:
        return 0
    if text_hits > 0:
        return _WEIGHT_TEXT
    return 0


def infer_room_type(
    area_m2: float,
    aspect: float,
    corridor_adj_count: int = 0,
    nearby_texts: List[str] = None,
) -> Tuple[str, float, bool]:
    """
    推断房间类型。

    参数:
        area_m2: 房间面积 (m²)
        aspect: 宽高比（长边/短边，≥1.0）
        corridor_adj_count: 相邻 corridor/doorway 数量
        nearby_texts: 附近 TEXT 实体的文本列表

    返回:
        (type_name, confidence, override_type)
        - type_name: 推断的房间类型名，"" 表示无法推断
        - confidence: 0~1.0 置信度
        - override_type: True 表示建议将 entity_type 升级为 type_name
    """
    if area_m2 <= 0 or aspect <= 0:
        return "", 0.0, False

    nearby_texts = nearby_texts or []
    texts_lower = [t.lower() for t in nearby_texts]
    text_total = len(texts_lower)

    best_name = ""
    best_score = 0
    best_override = False

    for rule in ROOM_TYPE_RULES:
        score = 0
        score += _score_area(area_m2, rule["area"][0], rule["area"][1])
        score += _score_aspect(aspect, rule["aspect"][0], rule["aspect"][1])
        score += _score_corridor(corridor_adj_count, rule.get("min_corridor_adj", 0))
        # 文本关键词匹配
        if text_total > 0:
            hits = sum(1 for kw in rule["text_keywords"] if kw.lower() in " ".join(texts_lower))
            score += _score_text(hits, text_total, rule["text_keywords"])

        if score > best_score:
            best_score = score
            best_name = rule["name"]
            best_override = rule.get("override_type", False)

    if best_score >= _SCORE_THRESHOLD:
        # 归一化置信度（满分 = _WEIGHT_AREA + _WEIGHT_ASPECT + _WEIGHT_CORRIDOR + _WEIGHT_TEXT = 105）
        max_score = _WEIGHT_AREA + _WEIGHT_ASPECT + _WEIGHT_CORRIDOR + _WEIGHT_TEXT
        confidence = min(best_score / max_score, 1.0)
        return best_name, round(confidence, 3), best_override

    return "", 0.0, False
