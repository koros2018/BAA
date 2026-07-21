"""
BAA 规范JSON知识库
10 条 L1 + 10 条 L2 级规范（GB50016-2014 / GB50016-2018 建筑防火规范）
支持 building_type 维度阈值（民用/工业）
"""

from typing import Dict, List, Optional, Tuple  # typing: type hints
from dataclasses import dataclass, field  # dataclass support
import json  # stdlib: JSON


@dataclass  # code
class Threshold:  # class definition
    """规范阈值，支持按建筑类型区分"""

    value: float  # 操作
    unit: str  # 操作
    operator: str  # >=, <=, ==, !=
    building_types: Optional[Dict[str, float]] = None  # {"civil": 值, "industrial": 值}


@dataclass  # code
class Clause:  # class definition
    """规范条款"""

    clause_id: str  # 操作
    standard: str  # 操作
    title: str  # 操作
    text: str  # 操作
    level: str  # L1 / L2 / L3
    func_id: str  # 对应原子函数 ID
    category: str  # fire_safety / evacuation / structure / lighting / hvac
    params: Dict = field(default_factory=dict)  # function call
    threshold: Optional[Threshold] = None  # 可选：带建筑类型区分的阈值


# ════════════════════════════════════════════════════════════
# NFPA 101 / NFPA 5000 规范（美国标准）
# 与 GB 50016 条款对照，同一原子函数复用，仅阈值不同
# ════════════════════════════════════════════════════════════

NFPA_CLAUSES = [  # assignment
    # =============================================
    # 疏散楼梯净宽 — NFPA 101:7.2.1.2
    # GB 对照: DIM-001 / GB50016-5.5.18
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.2.1.2",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Stairway Width",  # assignment
        text="The clear width of stairways shall be not less than 1120 mm (44 in) for occupancy loads exceeding 49.",  # function call
        level="L1",  # assignment
        func_id="DIM-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "staircase",
            "property": "clear_width",  # assignment
            "operator": ">=",
            "threshold": 1.12,
            "unit": "m",
        },  # assignment
        threshold=Threshold(
            value=1.12,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 1.12, "industrial": 1.12},
        ),  # assignment
    ),  # code
    # =============================================
    # 疏散距离 — NFPA 101:7.7.1
    # GB 对照: DIST-001 / GB50016-5.5.17
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.7.1",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Travel Distance to Exit",  # assignment
        text="The travel distance to an exit shall not exceed 61 m (200 ft) for sprinklered buildings.",  # function call
        level="L1",  # assignment
        func_id="DIST-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "room",
            "property": "travel_distance",  # assignment
            "operator": "<=",
            "threshold": 61.0,
            "unit": "m",
        },  # assignment
        threshold=Threshold(
            value=61.0,
            unit="m",
            operator="<=",  # assignment
            building_types={"civil": 61.0, "industrial": 76.0},
        ),  # assignment
    ),  # code
    # =============================================
    # 安全出口数量 — NFPA 101:7.4.1
    # GB 对照: COUNT-001 / GB50016-5.5.8
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.4.1",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Number of Exits",  # assignment
        text="Every floor or space shall have not less than two exits.",  # assignment
        level="L1",  # assignment
        func_id="COUNT-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "fire_zone",
            "property": "exit_count",  # assignment
            "operator": ">=",
            "threshold": 2.0,
            "unit": "个",
        },  # assignment
        threshold=Threshold(
            value=2.0,
            unit="个",
            operator=">=",  # assignment
            building_types={"civil": 2.0, "industrial": 2.0},
        ),  # assignment
    ),  # code
    # =============================================
    # 疏散门宽度 — NFPA 101:7.2.1.2
    # GB 对照: DIM-006 / GB50016-5.5.18
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.2.1.2.2",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Door Clear Width",  # assignment
        text="The clear width of doorways shall be not less than 810 mm (32 in).",  # function call
        level="L1",  # assignment
        func_id="DIM-006",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "exit_door",
            "property": "clear_width",  # assignment
            "operator": ">=",
            "threshold": 0.81,
            "unit": "m",
        },  # assignment
        threshold=Threshold(
            value=0.81,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 0.81, "industrial": 0.81},
        ),  # assignment
    ),  # code
    # =============================================
    # 防火分区面积 — NFPA 5000:8.3.1
    # GB 对照: DIM-002 / GB50016-6.1.1
    # =============================================
    Clause(  # code
        clause_id="NFPA5000-8.3.1",  # assignment
        standard="NFPA 5000-2021",  # assignment
        title="Floor Area per Occupancy",  # assignment
        text="The maximum floor area per fire area shall not exceed 2323 m² (25,000 ft²) for business occupancies.",  # function call
        level="L1",  # assignment
        func_id="DIM-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_zone",
            "property": "area",  # assignment
            "operator": "<=",
            "threshold": 2323,
            "unit": "㎡",
        },  # assignment
        threshold=Threshold(
            value=2323,
            unit="㎡",
            operator="<=",  # assignment
            building_types={"civil": 2323, "industrial": 3716},
        ),  # assignment
    ),  # code
    # =============================================
    # 走廊宽度 — NFPA 101:7.3.3
    # GB 对照: DIM-004 / GB50016-5.5.18
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.3.3",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Corridor Width",  # assignment
        text="The width of any corridor serving an occupant load of 50 or more shall be not less than 1118 mm (44 in).",  # function call
        level="L1",  # assignment
        func_id="DIM-004",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "corridor",
            "property": "width",  # assignment
            "operator": ">=",
            "threshold": 1.12,
            "unit": "m",
        },  # assignment
        threshold=Threshold(
            value=1.12,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 1.12, "industrial": 1.12},
        ),  # assignment
    ),  # code
    # =============================================
    # 消防车道 — NFPA 5000:18.3.1
    # GB 对照: DIM-003 / GB50016-7.1.1
    # =============================================
    Clause(  # code
        clause_id="NFPA5000-18.3.1",  # assignment
        standard="NFPA 5000-2021",  # assignment
        title="Fire Apparatus Access Road Width",  # assignment
        text="Fire apparatus access roads shall have an unobstructed width of not less than 6.1 m (20 ft).",  # function call
        level="L1",  # assignment
        func_id="DIM-003",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_lane",
            "property": "width",  # assignment
            "operator": ">=",
            "threshold": 6.1,
            "unit": "m",
        },  # assignment
        threshold=Threshold(
            value=6.1,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 6.1, "industrial": 6.1},
        ),  # assignment
    ),  # code
    # =============================================
    # 消防栓间距 — NFPA 14:7.3
    # GB 对照: EXIST-002 / GB50016-8.2.1
    # =============================================
    Clause(  # code
        clause_id="NFPA14-7.3",  # assignment
        standard="NFPA 14-2021",  # assignment
        title="Standpipe System Spacing",  # assignment
        text="Standpipe systems shall be provided in all buildings with a travel distance exceeding 61 m.",  # assignment
        level="L2",  # assignment
        func_id="EXIST-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "standpipe",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # assignment
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    # =============================================
    # 自动喷淋 — NFPA 13:5.1
    # GB 对照: EXIST-006 / GB50016-8.3.1
    # =============================================
    Clause(  # code
        clause_id="NFPA13-5.1",  # assignment
        standard="NFPA 13-2021",  # assignment
        title="Automatic Sprinkler System",  # assignment
        text="Automatic sprinkler systems shall be provided in all buildings exceeding 465 m² in fire area.",  # assignment
        level="L2",  # assignment
        func_id="EXIST-006",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "sprinkler",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # assignment
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    # =============================================
    # 应急照明 — NFPA 101:7.9.2
    # GB 对照: EXIST-004 / GB50016-10.3.1
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.9.2",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Emergency Lighting",  # assignment
        text="Emergency lighting shall be provided in all means of egress.",  # assignment
        level="L2",  # assignment
        func_id="EXIST-004",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "emergency_light",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # assignment
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    # =============================================
    # 疏散标志 — NFPA 101:7.10.1
    # GB 对照: EXIST-001 / GB50016-6.6.1
    # =============================================
    Clause(  # code
        clause_id="NFPA101-7.10.1",  # assignment
        standard="NFPA 101-2021",  # assignment
        title="Exit Signs",  # assignment
        text="Exit signs shall be placed at every exit door and along the means of egress where necessary.",  # assignment
        level="L2",  # assignment
        func_id="EXIST-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "exit_sign",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # assignment
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
]  # code
