"""
BAA 规范JSON知识库
10 条 L1 + 10 条 L2 级规范（GB50016-2014 / GB50016-2018 建筑防火规范）
支持 building_type 维度阈值（民用/工业）
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import json


@dataclass
class Threshold:
    """规范阈值，支持按建筑类型区分"""
    value: float  # 操作
    unit: str  # 操作
    operator: str      # >=, <=, ==, !=
    building_types: Optional[Dict[str, float]] = None  # {"civil": 值, "industrial": 值}


@dataclass
class Clause:
    """规范条款"""
    clause_id: str  # 操作
    standard: str  # 操作
    title: str  # 操作
    text: str  # 操作
    level: str            # L1 / L2 / L3
    func_id: str          # 对应原子函数 ID
    category: str         # fire_safety / evacuation / structure / lighting / hvac
    params: Dict = field(default_factory=dict)
    threshold: Optional[Threshold] = None  # 可选：带建筑类型区分的阈值


# ── 规范 JSON 库 ─────────────────────────────────────────

# 首批 10 条 L1 + 10 条 L2 级规范
INITIAL_CLAUSES = [
    # =============================================
    # L1 规范（10条）
    # =============================================
    Clause(
        clause_id="GB50016-5.5.18",
        standard="GB 50016-2014",
        title="疏散楼梯净宽",
        text="高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。",
        level="L1",
        func_id="DIM-001",
        category="evacuation",
        params={"target_entity": "staircase", "property": "clear_width",
                "operator": ">=", "threshold": 1.2, "unit": "m"},  # 字段
        threshold=Threshold(value=1.2, unit="m", operator=">=",
                            building_types={"civil": 1.2, "industrial": 1.1})
    ),
    Clause(
        clause_id="GB50016-6.1.1",
        standard="GB 50016-2014",
        title="防火分区面积",
        text="每个防火分区的最大允许建筑面积不应大于2500㎡（民用）/ 4000㎡（工业，一二级单层）。",
        level="L1",
        func_id="DIM-002",
        category="fire_safety",
        params={"target_entity": "fire_zone", "property": "area",
                "operator": "<=", "threshold": 2500, "unit": "㎡"},  # 字段
        threshold=Threshold(value=2500, unit="㎡", operator="<=",
                            building_types={"civil": 2500, "industrial": 4000})
    ),
    Clause(
        clause_id="GB50016-7.1.1",
        standard="GB 50016-2014",
        title="消防车道宽度",
        text="消防车道的净宽度和净高度均不应小于4.0m。",
        level="L1",
        func_id="DIM-003",
        category="fire_safety",
        params={"target_entity": "fire_lane", "property": "width",
                "operator": ">=", "threshold": 4.0, "unit": "m"},  # 字段
        # 消防车道宽度工业/民用无差异，但厂房占地面积>3000㎡时需环形消防车道
        threshold=Threshold(value=4.0, unit="m", operator=">=",
                            building_types={"civil": 4.0, "industrial": 4.0})
    ),
    Clause(
        clause_id="GB50016-5.5.17",
        standard="GB 50016-2014",
        title="疏散距离",
        text="房间内任一点至最近安全出口的直线距离不应大于30m（民用）/ 40m（工业）。",
        level="L1",
        func_id="DIST-001",
        category="evacuation",
        params={"target_entity": "room", "property": "travel_distance",
                "operator": "<=", "threshold": 30.0, "unit": "m"},  # 字段
        threshold=Threshold(value=30.0, unit="m", operator="<=",
                            building_types={"civil": 30.0, "industrial": 40.0})
    ),
    Clause(
        clause_id="GB50016-5.5.8",
        standard="GB 50016-2014",
        title="安全出口数量",
        text="每个防火分区或一个防火分区的每个楼层，其安全出口不应少于2个。",
        level="L1",
        func_id="COUNT-001",
        category="evacuation",
        params={"target_entity": "floor", "property": "exit_count",
                "operator": ">=", "threshold": 2.0, "unit": "个"},  # 字段
        # 工业厂房每个防火分区也要求≥2个安全出口（GB50016 3.7.2）
        threshold=Threshold(value=2.0, unit="个", operator=">=",
                            building_types={"civil": 2.0, "industrial": 2.0})
    ),
    Clause(
        clause_id="GB50016-6.5.1",
        standard="GB 50016-2014",
        title="防火门等级",
        text="防火门的耐火等级应符合设计要求，甲级防火门耐火极限不低于1.5h。",
        level="L1",
        func_id="ATTR-001",
        category="fire_safety",
        params={"target_entity": "fire_door", "property": "fire_rating",
                "operator": "==", "threshold": 1.0, "unit": "级"},  # 字段
        # 工业/民用防火门等级要求一致（按GB50016 6.5.1/3.2.9）
        threshold=Threshold(value=1.0, unit="级", operator=">=",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-5.5.18-2",
        standard="GB 50016-2014",
        title="疏散走道宽度",
        text="疏散走道的净宽度不应小于1.1m（民用）/ 1.0m（工业）。",
        level="L1",
        func_id="DIM-004",
        category="evacuation",
        params={"target_entity": "corridor", "property": "clear_width",
                "operator": ">=", "threshold": 1.1, "unit": "m"},  # 字段
        threshold=Threshold(value=1.1, unit="m", operator=">=",
                            building_types={"civil": 1.1, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-7.4.1",
        standard="GB 50016-2014",
        title="避难层面积",
        text="避难层（间）的净面积应按不小于5人/㎡计算。",
        level="L1",
        func_id="AREA-001",
        category="fire_safety",
        params={"target_entity": "refuge_floor", "property": "area_per_person",
                "operator": ">=", "threshold": 5.0, "unit": "㎡/人"},  # 字段
        # 避难层仅用于民用高层建筑，工业建筑通常无此要求
        threshold=Threshold(value=5.0, unit="㎡/人", operator=">=",
                            building_types={"civil": 5.0, "industrial": 0.0})
    ),
    Clause(
        clause_id="GB50016-5.5.12",
        standard="GB 50016-2014",
        title="楼梯间设置",
        text="一类高层公共建筑应设置防烟楼梯间。",
        level="L1",
        func_id="EXIST-001",
        category="evacuation",
        params={"target_entity": "staircase", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需疏散楼梯（GB50016 3.7.6），高层厂房设封闭楼梯间
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-7.2.4",
        standard="GB 50016-2014",
        title="消防窗面积",
        text="消防救援窗的净面积不应小于1.0㎡。",
        level="L1",
        func_id="DIM-005",
        category="fire_safety",
        params={"target_entity": "fire_window", "property": "net_area",
                "operator": ">=", "threshold": 1.0, "unit": "㎡"},  # 字段
        # 工业厂房也需设置消防救援窗（GB50016 7.2.4），要求一致
        threshold=Threshold(value=1.0, unit="㎡", operator=">=",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),

    # =============================================
    # L2 规范（10条）
    # =============================================
    Clause(
        clause_id="GB50016-5.5.19",
        standard="GB 50016-2014",
        title="人员密集场所疏散门净宽",
        text="人员密集场所的疏散门，其净宽度不应小于1.4m。",
        level="L2",
        func_id="DIM-006",
        category="evacuation",
        params={"target_entity": "exit_door", "property": "clear_width",
                "operator": ">=", "threshold": 1.4, "unit": "m"},  # 字段
        # 工业厂房疏散门也需≥1.2m（GB50016 3.7.5），人员密集时≥1.4m
        threshold=Threshold(value=1.4, unit="m", operator=">=",
                            building_types={"civil": 1.4, "industrial": 1.2})
    ),
    Clause(
        clause_id="GB50016-6.6.1",
        standard="GB 50016-2014",
        title="管道井封堵",
        text="电缆井、管道井应在每层楼板处用不低于楼板耐火极限的不燃材料封堵。",
        level="L2",
        func_id="EXIST-002",
        category="fire_safety",
        params={"target_entity": "shaft", "property": "sealed",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房管道井封堵要求一致
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-6.5.3",
        standard="GB 50016-2014",
        title="防火卷帘宽度",
        text="除中庭外，防火分隔部位的防火卷帘宽度不应大于10m。",
        level="L2",
        func_id="DIM-007",
        category="fire_safety",
        params={"target_entity": "fire_curtain", "property": "width",
                "operator": "<=", "threshold": 10.0, "unit": "m"},  # 字段
        # 工业厂房防火卷帘要求一致（GB50016 6.5.3适用于所有建筑类型）
        threshold=Threshold(value=10.0, unit="m", operator="<=",
                            building_types={"civil": 10.0, "industrial": 10.0})
    ),
    Clause(
        clause_id="GB50016-5.5.24",
        standard="GB 50016-2014",
        title="高层住宅剪刀楼梯",
        text="高层住宅建筑的疏散楼梯，当采用剪刀楼梯时，梯段间应设置防火隔墙。",
        level="L2",
        func_id="EXIST-003",
        category="evacuation",
        params={"target_entity": "scissor_staircase", "property": "fire_wall_exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 剪刀楼梯仅用于民用住宅，工业厂房不适用
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 0.0})
    ),
    Clause(
        clause_id="GB50016-10.1.5",
        standard="GB 50016-2014",
        title="消防应急照明",
        text="建筑内疏散照明的地面最低水平照度不应低于1.0lx。",
        level="L2",
        func_id="LIGHT-001",
        category="lighting",
        params={"target_entity": "evacuation_lighting", "property": "illuminance",
                "operator": ">=", "threshold": 1.0, "unit": "lx"},  # 字段
        # 工业厂房应急照明要求一致（GB50016 10.1.5/10.3.1）
        threshold=Threshold(value=1.0, unit="lx", operator=">=",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-10.3.1",
        standard="GB 50016-2014",
        title="疏散指示标志",
        text="疏散走道和安全出口处应设置疏散指示标志。",
        level="L2",
        func_id="EXIST-004",
        category="evacuation",
        params={"target_entity": "exit_sign", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需设置疏散指示标志（GB50016 10.3.1）
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-8.3.1",
        standard="GB 50016-2014",
        title="自动灭火系统（一类高层）",
        text="一类高层公共建筑（除游泳池、溜冰场外）应设置自动灭火系统。",
        level="L2",
        func_id="EXIST-005",
        category="fire_safety",
        params={"target_entity": "sprinkler_system", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需自动灭火系统（GB50016 8.3.1，高层厂房和仓库）
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-8.4.1",
        standard="GB 50016-2014",
        title="火灾自动报警系统",
        text="一类高层公共建筑应设置火灾自动报警系统。",
        level="L2",
        func_id="EXIST-006",
        category="fire_safety",
        params={"target_entity": "fire_alarm", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需火灾自动报警系统（GB50016 8.4.1，高层厂房和仓库）
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-6.7.1",
        standard="GB 50016-2014",
        title="保温材料燃烧等级",
        text="建筑内外保温系统应选用A级或B1级保温材料。",
        level="L2",
        func_id="ATTR-002",
        category="structure",
        params={"target_entity": "insulation", "property": "fire_rating",
                "operator": ">=", "threshold": 2.0, "unit": "级"},  # A=3, B1=2
        # 工业厂房保温要求更严，通常要求A级（GB50016 6.7.5/6.7.6）
        threshold=Threshold(value=2.0, unit="级", operator=">=",
                            building_types={"civil": 2.0, "industrial": 3.0})
    ),
    Clause(
        clause_id="GB50016-6.2.4",
        standard="GB 50016-2014",
        title="设备井防火隔墙",
        text="电缆井、管道井与房间、走道等相连通的孔洞，应采用防火封堵材料封堵。",
        level="L2",
        func_id="EXIST-002",
        category="fire_safety",
        params={"target_entity": "shaft", "property": "hole_sealed",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房封堵要求一致
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),

    # ===== L3 新增规范（11条，对应 RESERVED_FUNCS） =====
    Clause(
        clause_id="GB50016-3.4.1",
        standard="GB 50016-2014",
        title="防火间距判定",
        text="厂房之间及与乙、丙、丁、戊类仓库等的防火间距不应小于表3.4.1的规定。",
        level="L3",
        func_id="DIST-002",
        category="fire_safety",
        params={"target_entity": "building", "property": "distance",
                "operator": ">=", "threshold": 12.0, "unit": "m"},  # 字段
        # 工业厂房防火间距要求更严
        threshold=Threshold(value=12.0, unit="m", operator=">=",
                            building_types={"civil": 10.0, "industrial": 12.0})
    ),
    Clause(
        clause_id="GB50016-9.2.1",
        standard="GB 50016-2014",
        title="排烟窗面积判定",
        text="排烟窗净面积不应小于房间面积的2%。",
        level="L3",
        func_id="DIM-008",
        category="hvac",
        params={"target_entity": "smoke_exhaust_window", "property": "area",
                "operator": ">=", "threshold": 0.02, "unit": "㎡"},  # 字段
        threshold=Threshold(value=0.02, unit="㎡", operator=">=",
                            building_types={"civil": 0.02, "industrial": 0.02})
    ),
    Clause(
        clause_id="GB50016-7.3.1",
        standard="GB 50016-2014",
        title="消防电梯判定",
        text="一类高层公共建筑和建筑高度大于32m的二类高层公共建筑应设置消防电梯。",
        level="L3",
        func_id="EXIST-007",
        category="fire_safety",
        params={"target_entity": "fire_elevator", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-7.3.5",
        standard="GB 50016-2014",
        title="消防电梯前室面积判定",
        text="消防电梯前室的使用面积不应小于6㎡。",
        level="L3",
        func_id="AREA-002",
        category="fire_safety",
        params={"target_entity": "elevator_lobby", "property": "area",
                "operator": ">=", "threshold": 6.0, "unit": "㎡"},  # 字段
        threshold=Threshold(value=6.0, unit="㎡", operator=">=",
                            building_types={"civil": 6.0, "industrial": 6.0})
    ),
    Clause(
        clause_id="GB50016-5.5.17-2",
        standard="GB 50016-2014",
        title="袋形走道长度判定",
        text="袋形走道长度不应大于20m。",
        level="L3",
        func_id="DIST-003",
        category="evacuation",
        params={"target_entity": "corridor", "property": "length",
                "operator": "<=", "threshold": 20.0, "unit": "m"},  # 字段
        threshold=Threshold(value=20.0, unit="m", operator="<=",
                            building_types={"civil": 20.0, "industrial": 15.0})
    ),
    Clause(
        clause_id="GB50016-5.5.18-3",
        standard="GB 50016-2014",
        title="疏散出口宽度判定",
        text="疏散出口净宽度不应小于0.9m。",
        level="L3",
        func_id="DIM-009",
        category="evacuation",
        params={"target_entity": "exit", "property": "clear_width",
                "operator": ">=", "threshold": 0.9, "unit": "m"},  # 字段
        threshold=Threshold(value=0.9, unit="m", operator=">=",
                            building_types={"civil": 0.9, "industrial": 0.9})
    ),
    Clause(
        clause_id="GB50016-6.5.1-2",
        standard="GB 50016-2014",
        title="防火窗等级判定",
        text="防火窗耐火极限不应低于1.0h。",
        level="L3",
        func_id="ATTR-003",
        category="fire_safety",
        params={"target_entity": "fire_window", "property": "fire_rating",
                "operator": ">=", "threshold": 1.0, "unit": "h"},  # 字段
        threshold=Threshold(value=1.0, unit="h", operator=">=",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-8.2.1",
        standard="GB 50016-2014",
        title="消防水箱判定",
        text="一类高层公共建筑应设置屋顶消防水箱。",
        level="L3",
        func_id="EXIST-008",
        category="fire_safety",
        params={"target_entity": "water_tank", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-8.1.3",
        standard="GB 50016-2014",
        title="消防水池判定",
        text="市政供水不足时应设置消防水池。",
        level="L3",
        func_id="EXIST-009",
        category="fire_safety",
        params={"target_entity": "water_reservoir", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-7.2.4-2",
        standard="GB 50016-2014",
        title="消防救援窗面积判定",
        text="消防救援窗口净面积不应小于1.0㎡。",
        level="L3",
        func_id="DIM-010",
        category="fire_safety",
        params={"target_entity": "rescue_window", "property": "area",
                "operator": ">=", "threshold": 1.0, "unit": "㎡"},  # 字段
        threshold=Threshold(value=1.0, unit="㎡", operator=">=",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    Clause(
        clause_id="GB50016-8.5.1",
        standard="GB 50016-2014",
        title="应急广播判定",
        text="一类高层公共建筑应设置应急广播系统。",
        level="L3",
        func_id="EXIST-010",
        category="evacuation",
        params={"target_entity": "emergency_broadcast", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
]


# ════════════════════════════════════════════════════════════
# NFPA 101 / NFPA 5000 规范（美国标准）
# 与 GB 50016 条款对照，同一原子函数复用，仅阈值不同
# ════════════════════════════════════════════════════════════

NFPA_CLAUSES = [
    # =============================================
    # 疏散楼梯净宽 — NFPA 101:7.2.1.2
    # GB 对照: DIM-001 / GB50016-5.5.18
    # =============================================
    Clause(
        clause_id="NFPA101-7.2.1.2",
        standard="NFPA 101-2021",
        title="Stairway Width",
        text="The clear width of stairways shall be not less than 1120 mm (44 in) for occupancy loads exceeding 49.",
        level="L1",
        func_id="DIM-001",
        category="evacuation",
        params={"target_entity": "staircase", "property": "clear_width",
                "operator": ">=", "threshold": 1.12, "unit": "m"},
        threshold=Threshold(value=1.12, unit="m", operator=">=",
                            building_types={"civil": 1.12, "industrial": 1.12})
    ),
    # =============================================
    # 疏散距离 — NFPA 101:7.7.1
    # GB 对照: DIST-001 / GB50016-5.5.17
    # =============================================
    Clause(
        clause_id="NFPA101-7.7.1",
        standard="NFPA 101-2021",
        title="Travel Distance to Exit",
        text="The travel distance to an exit shall not exceed 61 m (200 ft) for sprinklered buildings.",
        level="L1",
        func_id="DIST-001",
        category="evacuation",
        params={"target_entity": "room", "property": "travel_distance",
                "operator": "<=", "threshold": 61.0, "unit": "m"},
        threshold=Threshold(value=61.0, unit="m", operator="<=",
                            building_types={"civil": 61.0, "industrial": 76.0})
    ),
    # =============================================
    # 安全出口数量 — NFPA 101:7.4.1
    # GB 对照: COUNT-001 / GB50016-5.5.8
    # =============================================
    Clause(
        clause_id="NFPA101-7.4.1",
        standard="NFPA 101-2021",
        title="Number of Exits",
        text="Every floor or space shall have not less than two exits.",
        level="L1",
        func_id="COUNT-001",
        category="evacuation",
        params={"target_entity": "fire_zone", "property": "exit_count",
                "operator": ">=", "threshold": 2.0, "unit": "个"},
        threshold=Threshold(value=2.0, unit="个", operator=">=",
                            building_types={"civil": 2.0, "industrial": 2.0})
    ),
    # =============================================
    # 疏散门宽度 — NFPA 101:7.2.1.2
    # GB 对照: DIM-006 / GB50016-5.5.18
    # =============================================
    Clause(
        clause_id="NFPA101-7.2.1.2.2",
        standard="NFPA 101-2021",
        title="Door Clear Width",
        text="The clear width of doorways shall be not less than 810 mm (32 in).",
        level="L1",
        func_id="DIM-006",
        category="evacuation",
        params={"target_entity": "exit_door", "property": "clear_width",
                "operator": ">=", "threshold": 0.81, "unit": "m"},
        threshold=Threshold(value=0.81, unit="m", operator=">=",
                            building_types={"civil": 0.81, "industrial": 0.81})
    ),
    # =============================================
    # 防火分区面积 — NFPA 5000:8.3.1
    # GB 对照: DIM-002 / GB50016-6.1.1
    # =============================================
    Clause(
        clause_id="NFPA5000-8.3.1",
        standard="NFPA 5000-2021",
        title="Floor Area per Occupancy",
        text="The maximum floor area per fire area shall not exceed 2323 m² (25,000 ft²) for business occupancies.",
        level="L1",
        func_id="DIM-002",
        category="fire_safety",
        params={"target_entity": "fire_zone", "property": "area",
                "operator": "<=", "threshold": 2323, "unit": "㎡"},
        threshold=Threshold(value=2323, unit="㎡", operator="<=",
                            building_types={"civil": 2323, "industrial": 3716})
    ),
    # =============================================
    # 走廊宽度 — NFPA 101:7.3.3
    # GB 对照: DIM-004 / GB50016-5.5.18
    # =============================================
    Clause(
        clause_id="NFPA101-7.3.3",
        standard="NFPA 101-2021",
        title="Corridor Width",
        text="The width of any corridor serving an occupant load of 50 or more shall be not less than 1118 mm (44 in).",
        level="L1",
        func_id="DIM-004",
        category="evacuation",
        params={"target_entity": "corridor", "property": "width",
                "operator": ">=", "threshold": 1.12, "unit": "m"},
        threshold=Threshold(value=1.12, unit="m", operator=">=",
                            building_types={"civil": 1.12, "industrial": 1.12})
    ),
    # =============================================
    # 消防车道 — NFPA 5000:18.3.1
    # GB 对照: DIM-003 / GB50016-7.1.1
    # =============================================
    Clause(
        clause_id="NFPA5000-18.3.1",
        standard="NFPA 5000-2021",
        title="Fire Apparatus Access Road Width",
        text="Fire apparatus access roads shall have an unobstructed width of not less than 6.1 m (20 ft).",
        level="L1",
        func_id="DIM-003",
        category="fire_safety",
        params={"target_entity": "fire_lane", "property": "width",
                "operator": ">=", "threshold": 6.1, "unit": "m"},
        threshold=Threshold(value=6.1, unit="m", operator=">=",
                            building_types={"civil": 6.1, "industrial": 6.1})
    ),
    # =============================================
    # 消防栓间距 — NFPA 14:7.3
    # GB 对照: EXIST-002 / GB50016-8.2.1
    # =============================================
    Clause(
        clause_id="NFPA14-7.3",
        standard="NFPA 14-2021",
        title="Standpipe System Spacing",
        text="Standpipe systems shall be provided in all buildings with a travel distance exceeding 61 m.",
        level="L2",
        func_id="EXIST-002",
        category="fire_safety",
        params={"target_entity": "standpipe", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    # =============================================
    # 自动喷淋 — NFPA 13:5.1
    # GB 对照: EXIST-006 / GB50016-8.3.1
    # =============================================
    Clause(
        clause_id="NFPA13-5.1",
        standard="NFPA 13-2021",
        title="Automatic Sprinkler System",
        text="Automatic sprinkler systems shall be provided in all buildings exceeding 465 m² in fire area.",
        level="L2",
        func_id="EXIST-006",
        category="fire_safety",
        params={"target_entity": "sprinkler", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    # =============================================
    # 应急照明 — NFPA 101:7.9.2
    # GB 对照: EXIST-004 / GB50016-10.3.1
    # =============================================
    Clause(
        clause_id="NFPA101-7.9.2",
        standard="NFPA 101-2021",
        title="Emergency Lighting",
        text="Emergency lighting shall be provided in all means of egress.",
        level="L2",
        func_id="EXIST-004",
        category="fire_safety",
        params={"target_entity": "emergency_light", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
    # =============================================
    # 疏散标志 — NFPA 101:7.10.1
    # GB 对照: EXIST-001 / GB50016-6.6.1
    # =============================================
    Clause(
        clause_id="NFPA101-7.10.1",
        standard="NFPA 101-2021",
        title="Exit Signs",
        text="Exit signs shall be placed at every exit door and along the means of egress where necessary.",
        level="L2",
        func_id="EXIST-001",
        category="evacuation",
        params={"target_entity": "exit_sign", "property": "exists",
                "operator": "==", "threshold": 1.0, "unit": "有/无"},
        threshold=Threshold(value=1.0, unit="有/无", operator="==",
                            building_types={"civil": 1.0, "industrial": 1.0})
    ),
]


class SpecRepository:
    """规范 JSON 知识库（多标准支持）

    支持 GB 50016（中国建筑防火规范）、NFPA 101（生命安全规范）、
    NFPA 5000（建筑规范）等多套标准。
    规范通过 (standard, clause_id) 唯一标识。
    """

    def __init__(self):
        self._clauses: Dict[str, Clause] = {}  # key: "{standard}:{clause_id}"
        # 遍历处理
        for clause in INITIAL_CLAUSES:  # 循环
            key = f"{clause.standard}:{clause.clause_id}"
            self._clauses[key] = clause
        # 加载 NFPA 规范
        for clause in NFPA_CLAUSES:
            key = f"{clause.standard}:{clause.clause_id}"
            self._clauses[key] = clause

    def get(self, clause_id: str, standard: str = "GB 50016-2014") -> Optional[Clause]:
        return self._clauses.get(f"{standard}:{clause_id}")

    def get_by_func(self, func_id: str, standard: str = None) -> List[Clause]:
        clauses = list(self._clauses.values())
        if standard:
            clauses = [c for c in clauses if c.standard == standard]
        return [c for c in clauses if c.func_id == func_id]

    def list_all(self, standard: str = None) -> List[Clause]:
        if standard:
            return [c for c in self._clauses.values() if c.standard == standard]
        return list(self._clauses.values())

    def list_by_level(self, level: str, standard: str = None) -> List[Clause]:
        clauses = self.list_all(standard)
        return [c for c in clauses if c.level == level]

    def list_by_category(self, category: str, standard: str = None) -> List[Clause]:
        clauses = self.list_all(standard)
        return [c for c in clauses if c.category == category]

    def get_threshold(self, clause_id: str, building_type: str = "civil", standard: str = "GB 50016-2014") -> Tuple[float, str, str]:
        """获取指定建筑类型和标准的阈值
        返回: (value, unit, operator)
        """
        clause = self.get(clause_id, standard)
        # 条件分支：if not clause
        if not clause:
            # 尝试 GB 标准兜底
            clause = self.get(clause_id, "GB 50016-2014")
        if not clause:
            # 找不到时返回默认值（不抛异常，让原子函数自身判定）
            return 0.0, "", ">="

        params = clause.params
        value = float(params["threshold"])
        unit = params.get("unit", "")
        operator = params.get("operator", ">=")

        # 如果有 building_type 维度的阈值，覆盖
        if clause.threshold and clause.threshold.building_types:
            bt = building_type if building_type in clause.threshold.building_types else "civil"
            value = clause.threshold.building_types.get(bt, value)

        return value, unit, operator

    def to_json(self) -> str:
        """序列化为 JSON"""
        data = []
        # 遍历处理
        for c in self._clauses.values():  # 循环
            entry = {
                "clause_id": c.clause_id,  # 字段
                "standard": c.standard,  # 字段
                "title": c.title,  # 字段
                "text": c.text,  # 字段
                "level": c.level,  # 字段
                "func_id": c.func_id,  # 字段
                "category": c.category,  # 字段
                "params": c.params,  # 字段
            }
            # 条件分支：if c.threshold and c.threshold.building_types
            if c.threshold and c.threshold.building_types:
                entry["building_type_thresholds"] = c.threshold.building_types  # 操作
            data.append(entry)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def save_json(self, file_path: str):
        """保存为 JSON 文件"""
        # 上下文管理器
        with open(file_path, "w", encoding="utf-8") as f:  # 上下文
            f.write(self.to_json())

    def set_threshold(self, clause_id: str, building_type: str, value: float, standard: str = "GB 50016-2014"):
        """设置指定建筑类型的阈值（用于反馈闭环微调）"""
        clause = self.get(clause_id, standard)
        # 条件分支：if not clause
        if not clause:
            raise ValueError(f"规范 {standard}:{clause_id} 不存在")  # 抛出

        # 条件分支：if not clause.threshold
        if not clause.threshold:
            clause.threshold = ClauseThreshold()
        # 条件分支：if not clause.threshold.building_types
        if not clause.threshold.building_types:
            clause.threshold.building_types = {}
        clause.threshold.building_types[building_type] = value  # 操作

    def list_standards(self) -> List[str]:
        """获取支持的标准列表"""
        return sorted(set(c.standard for c in self._clauses.values()))

    @property
    def count(self) -> int:
        return len(self._clauses)
