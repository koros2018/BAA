"""
防火分区疏散宽度聚合判定（GB50016-5.5.19 / 5.5.21）

两级口径，本模块负责第二级：

1. 实体级最小净宽（不在本模块）：单扇疏散门净宽不得小于规范最小值
   （DIM-006 = 1.4m，DIM-113 = 0.9m）。
2. 分区级总净宽（本模块）：同一防火分区内多扇疏散门的宽度应求和，再与
   该防火分区**所需疏散总净宽**比较：

       所需总净宽 = 疏散人数 / 100 × 每百人疏散净宽度指标
       疏散人数   = 疏散面积 / 人均面积指标

数据不足时的回退策略（不臆造数据）：

- 图纸未标注建筑用途 → 无法算疏散人数 → 回退到「分区内疏散门宽度之和
  ≥ 单门阈值」的既有保守口径；
- 图纸无防火分区实体 → 不做分区聚合，逐门判定。

统计汇总（供审计）：`WidthContext.stats` 记录分区数、求和口径、人数换算
命中次数与回退次数。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# 防火分区实体类型
COMPARTMENT_TYPES = {"fire_compartment", "fire_zone"}

# 可作为疏散出口的门实体类型
DOOR_TYPES = {"door", "exit_door", "doorway", "evacuation_door", "room_door"}

# 明确标注为疏散语义的类型/子类型
EXPLICIT_EVAC_TYPES = {"exit_door", "evacuation_door", "room_door"}

# 非疏散门图层关键词（设备门/管井门/立管门等）
NON_EXIT_LAYER_KEYWORDS = ("设备", "管线", "管井", "消防排水", "PIPE", "EQUIP")

# 小于该宽度的门视为设备门/检修门，不计入疏散总净宽（m）
MIN_COUNTABLE_DOOR_WIDTH = 0.6

# 人均面积指标（m²/人）
# 来源：GB50016-5.5.21-2（商店、展览）与 GB50016-5.5.21-4（办公）
# 只收录条文明确给出的类别；未收录的类别返回 None，交由回退口径处理。
AREA_PER_PERSON: Dict[str, Dict[str, float]] = {
    # 商店：按楼层位置取值
    "shop": {
        "ground_1_2": 0.60,
        "ground_3": 0.40,
        "ground_4_up": 0.30,
        "basement": 0.30,
    },
    # 展览建筑：各层统一
    "exhibition": {"all": 0.75},
    # 办公建筑：办公用房
    "office": {"all": 4.00},
}

# 每百人疏散净宽度指标（m/百人）
# 来源：GB50016-5.5.21-1，一、二级耐火等级
WIDTH_PER_100: Dict[str, float] = {
    "ground_1_2": 0.65,
    "ground_3": 0.75,
    "ground_4_up": 1.00,
    "basement_shallow": 0.75,  # 室内地面与室外出入口地坪高差 ≤ 10m
    "basement_deep": 1.00,  # 高差 > 10m
}

# 实体子类型/类型 → 用途类别
USAGE_ALIASES: Dict[str, str] = {
    "shop": "shop",
    "store": "shop",
    "basement_shop": "shop",
    "retail": "shop",
    "exhibition": "exhibition",
    "exhibition_hall": "exhibition",
    "office": "office",
    "office_room": "office",
    "office_building": "office",
}

# 用途字段名（优先读取实体自身属性）
USAGE_PROPERTY_KEYS = ("usage", "building_usage", "occupancy_type", "building_type", "room_use")

# 直接给出人数字段名
PEOPLE_PROPERTY_KEYS = ("people", "occupancy", "occupants", "evacuation_people")

# 地下埋深字段名
DEPTH_PROPERTY_KEYS = ("basement_depth_m", "basement_depth", "depth_below_ground_m")


# ── 几何工具 ────────────────────────────────────────────────


def _bbox(e: Dict[str, Any]) -> Optional[Dict[str, float]]:
    bbox = e.get("bbox")
    if not isinstance(bbox, dict):
        return None
    try:
        return {
            "x": float(bbox.get("x", 0) or 0),
            "y": float(bbox.get("y", 0) or 0),
            "width": float(bbox.get("width", 0) or 0),
            "height": float(bbox.get("height", 0) or 0),
        }
    except (TypeError, ValueError):
        return None


def center_of(e: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """实体中心点（mm）。"""
    b = _bbox(e)
    if b is None:
        return None
    return (b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)


def build_compartments(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """提取可用的防火分区（需有有效 bbox）。

    保留源实体引用（``entity``），供后续读取用途/楼层等属性。
    """
    comps = []
    for e in entities:
        if e.get("type") not in COMPARTMENT_TYPES:
            continue
        b = _bbox(e)
        if b is None or b["width"] <= 0 or b["height"] <= 0:
            continue
        comps.append({"id": e.get("id"), "bbox": b, "entity": e})
    return comps


def compartment_of(e: Dict[str, Any], compartments: List[Dict[str, Any]]) -> Optional[str]:
    """实体中心点落在哪个防火分区 bbox 内。"""
    c = center_of(e)
    if c is None:
        return None
    px, py = c
    for comp in compartments:
        b = comp["bbox"]
        if b["x"] <= px <= b["x"] + b["width"] and b["y"] <= py <= b["y"] + b["height"]:
            return comp["id"]
    return None


def is_elevation_door(e: Dict[str, Any], compartments: List[Dict[str, Any]]) -> bool:
    """立面图门：不属于任何防火分区，且处于立面图层或 y>0 区域。

    立面图门不是平面图的疏散门，不应参与疏散净宽判定
    （c157664 的 `立-门窗` 层 16 扇 1.15m 门即此类）。
    """
    if compartment_of(e, compartments) is not None:
        return False
    layer = (e.get("layer") or "").upper()
    if "立" in layer or "立面" in layer:
        return True
    b = _bbox(e)
    if b is not None and b["y"] > 0:
        return True
    return False


def _door_width_m(e: Dict[str, Any]) -> Optional[float]:
    """门净宽（m），带单位归一。"""
    props = e.get("properties") or {}
    raw = props.get("width", props.get("clear_width", 0.0))
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None
    if raw <= 0:
        return None
    # 单位归一：>100 视为 mm，否则 m
    return raw / 1000.0 if raw > 100 else raw


def _is_non_exit_layer(e: Dict[str, Any]) -> bool:
    layer = (e.get("layer") or "").upper()
    return any(kw.upper() in layer for kw in NON_EXIT_LAYER_KEYWORDS)


def _is_explicit_evac_door(e: Dict[str, Any]) -> bool:
    props = e.get("properties") or {}
    etype = e.get("type") or ""
    return bool(
        props.get("is_evacuation_door")
        or props.get("evacuation_door")
        or etype in EXPLICIT_EVAC_TYPES
        or (e.get("subtype") or "") in EXPLICIT_EVAC_TYPES
    )


# ── 疏散人数换算 ────────────────────────────────────────────


def parse_storey(floor_label: Optional[str]) -> Tuple[Optional[int], bool]:
    """解析楼层标注 → (层号, 是否地下)。

    支持 F1/F2/F10、1F、B1/B2、-1F 等常见写法。
    """
    if not floor_label or not isinstance(floor_label, str):
        return (None, False)
    label = floor_label.strip().upper()
    is_basement = label.startswith(("B", "-"))
    digits = "".join(ch for ch in label if ch.isdigit())
    if not digits:
        return (None, is_basement)
    try:
        return (int(digits), is_basement)
    except ValueError:
        return (None, is_basement)


def storey_width_key(storey: Optional[int], is_basement: bool, depth_m: Optional[float]) -> str:
    """楼层位置 → 每百人指标查表键。"""
    if is_basement:
        if depth_m is not None and depth_m > 10.0:
            return "basement_deep"
        return "basement_shallow"
    if storey is None or storey <= 2:
        return "ground_1_2"
    if storey == 3:
        return "ground_3"
    return "ground_4_up"


def resolve_usage(*candidates: Dict[str, Any]) -> Optional[str]:
    """从若干实体中解析建筑用途类别。

    优先读取实体属性中的用途字段，其次按实体 type/subtype 映射。
    未识别时返回 None（不臆造用途）。
    """
    for e in candidates:
        if not e:
            continue
        props = e.get("properties") or {}
        for key in USAGE_PROPERTY_KEYS:
            val = props.get(key)
            if val:
                mapped = USAGE_ALIASES.get(str(val).strip().lower())
                if mapped:
                    return mapped
        for key in ("subtype", "type"):
            val = e.get(key)
            if val:
                mapped = USAGE_ALIASES.get(str(val).strip().lower())
                if mapped:
                    return mapped
    return None


def explicit_people(*candidates: Dict[str, Any]) -> Optional[float]:
    """图纸直接给出疏散人数时优先采用。"""
    for e in candidates:
        if not e:
            continue
        props = e.get("properties") or {}
        for key in PEOPLE_PROPERTY_KEYS:
            val = props.get(key)
            if val:
                try:
                    people = float(val)
                except (TypeError, ValueError):
                    continue
                if people > 0:
                    return people
    return None


def basement_depth(*candidates: Dict[str, Any]) -> Optional[float]:
    for e in candidates:
        if not e:
            continue
        props = e.get("properties") or {}
        for key in DEPTH_PROPERTY_KEYS:
            val = props.get(key)
            if val:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
    return None


def area_per_person(usage: str, storey: Optional[int], is_basement: bool) -> Optional[float]:
    """人均面积指标（m²/人）。未收录的类别返回 None。"""
    table = AREA_PER_PERSON.get(usage)
    if not table:
        return None
    if "all" in table:
        return table["all"]
    if is_basement:
        # 商店/展览地下部分不区分埋深，统一取 basement 指标
        return table.get("basement")
    key = storey_width_key(storey, is_basement, None)
    # 商店按楼层位置：地上1-2 / 地上3 / 地上4+
    return table.get(key)


def estimate_occupants(
    area_m2: Optional[float],
    usage: Optional[str],
    storey: Optional[int],
    is_basement: bool,
) -> Optional[float]:
    """疏散人数 = 疏散面积 / 人均面积指标。

    面积或用途缺失、或该用途未收录指标时返回 None。
    """
    if not area_m2 or area_m2 <= 0 or not usage:
        return None
    per_person = area_per_person(usage, storey, is_basement)
    if not per_person:
        return None
    return area_m2 / per_person


def required_total_width(
    area_m2: Optional[float],
    usage: Optional[str],
    storey: Optional[int],
    is_basement: bool,
    depth_m: Optional[float] = None,
    people: Optional[float] = None,
) -> Optional[float]:
    """所需疏散总净宽（m）= 疏散人数 / 100 × 每百人净宽指标。

    人数优先用图纸给出值，其次按面积换算；均不可得时返回 None。
    """
    occupants = people if people else estimate_occupants(area_m2, usage, storey, is_basement)
    if not occupants or occupants <= 0:
        return None
    key = storey_width_key(storey, is_basement, depth_m)
    per_100 = WIDTH_PER_100.get(key)
    if not per_100:
        return None
    return occupants / 100.0 * per_100


def compartment_area_m2(compartment_bbox: Dict[str, float]) -> float:
    """防火分区面积（m²），bbox 单位 mm。"""
    return (compartment_bbox["width"] / 1000.0) * (compartment_bbox["height"] / 1000.0)


# ── 分区级聚合判定 ──────────────────────────────────────────


class WidthContext:
    """单张图纸的疏散宽度聚合上下文（建议每张图纸构建一次）。"""

    def __init__(self, entities: List[Dict[str, Any]]):
        self.entities = entities
        self.compartments = build_compartments(entities)
        self._comp_by_id = {c["id"]: c for c in self.compartments}
        self.width_sums: Dict[str, float] = {}
        self.sum_modes: Dict[str, str] = {}
        self.stats = {
            "compartments": len(self.compartments),
            "explicit_sum_compartments": 0,
            "all_doors_sum_compartments": 0,
            "occupancy_based": 0,  # 按人数换算得到所需总净宽
            "threshold_fallback": 0,  # 无用途数据，回退单门阈值
            "no_compartment": 0,  # 实体无分区归属
        }
        self._build_width_sums()

    def _build_width_sums(self) -> None:
        """按防火分区汇总疏散门宽度。

        口径优先级：
        1) 分区内存在显式疏散门标注 → 只汇总显式疏散门；
        2) 分区内无任何显式标注 → 汇总该分区全部可计数门（唯一可得证据）；
        均排除立面图门、设备/管井图层门、宽度 < 0.6m 的小门。
        """
        explicit: Dict[str, float] = {}
        all_doors: Dict[str, float] = {}
        for e in self.entities:
            etype = e.get("type") or ""
            if etype not in DOOR_TYPES:
                continue
            if _is_non_exit_layer(e):
                continue
            width_m = _door_width_m(e)
            if width_m is None or width_m < MIN_COUNTABLE_DOOR_WIDTH:
                continue
            sid = compartment_of(e, self.compartments)
            if sid is None:
                continue
            if is_elevation_door(e, self.compartments):
                continue
            all_doors[sid] = all_doors.get(sid, 0.0) + width_m
            if _is_explicit_evac_door(e):
                explicit[sid] = explicit.get(sid, 0.0) + width_m

        for sid in all_doors:
            if explicit.get(sid):
                self.width_sums[sid] = explicit[sid]
                self.sum_modes[sid] = "explicit"
                self.stats["explicit_sum_compartments"] += 1
            else:
                self.width_sums[sid] = all_doors[sid]
                self.sum_modes[sid] = "all_doors"
                self.stats["all_doors_sum_compartments"] += 1

    def aggregate_pass(self, entity: Dict[str, Any], per_door_min: float) -> bool:
        """分区级聚合判定：该实体所属分区的疏散总净宽是否满足。

        返回 True 表示按分区口径合规（可抑制该实体的逐门判定）。
        """
        sid = compartment_of(entity, self.compartments)
        if sid is None:
            # 立面图门不参与平面疏散净宽判定（先于无分区判断，避免误判）
            if is_elevation_door(entity, self.compartments):
                return True
            self.stats["no_compartment"] += 1
            return False
        if is_elevation_door(entity, self.compartments):
            return True

        comp = self._comp_by_id.get(sid) or {}
        comp_entity = comp.get("entity") or {}
        props = entity.get("properties") or {}
        building = next(
            (x for x in self.entities if x.get("type") in ("building", "building_outline")),
            None,
        )
        usage = resolve_usage(entity, building, comp_entity)
        people = explicit_people(entity, building, comp_entity)
        comp_props = comp_entity.get("properties") or {}
        storey, is_basement = parse_storey(
            props.get("floor")
            or comp_props.get("floor")
            or (building or {}).get("properties", {}).get("floor")
        )
        depth = basement_depth(entity, building, comp_entity)

        required = None
        if people:
            required = required_total_width(
                0.0, usage, storey, is_basement, depth_m=depth, people=people
            )
        if required is None and usage:
            area_m2 = compartment_area_m2(comp.get("bbox", {}))
            required = required_total_width(area_m2, usage, storey, is_basement, depth_m=depth)

        if required is None:
            # 数据不足：回退到「分区总宽 ≥ 单门阈值」的保守口径
            self.stats["threshold_fallback"] += 1
            required = float(per_door_min)
        else:
            self.stats["occupancy_based"] += 1

        # 分区口径不得弱于单门最小净宽
        required = max(float(required), float(per_door_min))
        return self.width_sums.get(sid, 0.0) >= required

    def summary(self) -> str:
        """统计汇总（审计用）。"""
        s = self.stats
        return (
            f"分区 {s['compartments']} 个"
            f"（显式疏散门汇总 {s['explicit_sum_compartments']}，"
            f"全门汇总 {s['all_doors_sum_compartments']}）；"
            f"人数换算 {s['occupancy_based']} 次，"
            f"阈值回退 {s['threshold_fallback']} 次，"
            f"无分区归属 {s['no_compartment']} 次"
        )
