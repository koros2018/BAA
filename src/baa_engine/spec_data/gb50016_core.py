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


INITIAL_CLAUSES = [  # assignment
    # =============================================
    # L1 规范（10条）
    # =============================================
    Clause(  # code
        clause_id="GB50016-5.5.18",  # assignment
        standard="GB 50016-2014",  # assignment
        title="疏散楼梯净宽",  # assignment
        text="高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。",  # assignment
        level="L1",  # assignment
        func_id="DIM-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "staircase",
            "property": "clear_width",  # assignment
            "operator": ">=",
            "threshold": 1.2,
            "unit": "m",
        },  # 字段
        threshold=Threshold(
            value=1.2,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 1.2, "industrial": 1.1},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.1.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="防火分区面积",  # assignment
        text="每个防火分区的最大允许建筑面积不应大于2500㎡（民用）/ 4000㎡（工业，一二级单层）。",  # assignment
        level="L1",  # assignment
        func_id="DIM-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_zone",
            "property": "area",  # assignment
            "operator": "<=",
            "threshold": 2500,
            "unit": "㎡",
        },  # 字段
        threshold=Threshold(
            value=2500,
            unit="㎡",
            operator="<=",  # assignment
            building_types={"civil": 2500, "industrial": 4000},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-7.1.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防车道宽度",  # assignment
        text="消防车道的净宽度和净高度均不应小于4.0m。",  # assignment
        level="L1",  # assignment
        func_id="DIM-003",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_lane",
            "property": "width",  # assignment
            "operator": ">=",
            "threshold": 4.0,
            "unit": "m",
        },  # 字段
        # 消防车道宽度工业/民用无差异，但厂房占地面积>3000㎡时需环形消防车道
        threshold=Threshold(
            value=4.0,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 4.0, "industrial": 4.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.17",  # assignment
        standard="GB 50016-2014",  # assignment
        title="疏散距离",  # assignment
        text="房间内任一点至最近安全出口的直线距离不应大于30m（民用）/ 40m（工业）。",  # assignment
        level="L1",  # assignment
        func_id="DIST-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "room",
            "property": "travel_distance",  # assignment
            "operator": "<=",
            "threshold": 30.0,
            "unit": "m",
        },  # 字段
        threshold=Threshold(
            value=30.0,
            unit="m",
            operator="<=",  # assignment
            building_types={"civil": 30.0, "industrial": 40.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.8",  # assignment
        standard="GB 50016-2014",  # assignment
        title="安全出口数量",  # assignment
        text="每个防火分区或一个防火分区的每个楼层，其安全出口不应少于2个。",  # assignment
        level="L1",  # assignment
        func_id="COUNT-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "floor",
            "property": "exit_count",  # assignment
            "operator": ">=",
            "threshold": 2.0,
            "unit": "个",
        },  # 字段
        # 工业厂房每个防火分区也要求≥2个安全出口（GB50016 3.7.2）
        threshold=Threshold(
            value=2.0,
            unit="个",
            operator=">=",  # assignment
            building_types={"civil": 2.0, "industrial": 2.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.5.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="防火门等级",  # assignment
        text="防火门的耐火等级应符合设计要求，甲级防火门耐火极限不低于1.5h。",  # assignment
        level="L1",  # assignment
        func_id="ATTR-001",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_door",
            "property": "fire_rating",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "级",
        },  # 字段
        # 工业/民用防火门等级要求一致（按GB50016 6.5.1/3.2.9）
        threshold=Threshold(
            value=1.0,
            unit="级",
            operator=">=",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.18-2",  # assignment
        standard="GB 50016-2014",  # assignment
        title="疏散走道宽度",  # assignment
        text="疏散走道的净宽度不应小于1.1m（民用）/ 1.0m（工业）。",  # assignment
        level="L1",  # assignment
        func_id="DIM-004",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "corridor",
            "property": "clear_width",  # assignment
            "operator": ">=",
            "threshold": 1.1,
            "unit": "m",
        },  # 字段
        threshold=Threshold(
            value=1.1,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 1.1, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-7.4.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="避难层面积",  # assignment
        text="避难层（间）的净面积应按不小于5人/㎡计算。",  # assignment
        level="L1",  # assignment
        func_id="AREA-001",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "refuge_floor",
            "property": "area_per_person",  # assignment
            "operator": ">=",
            "threshold": 5.0,
            "unit": "㎡/人",
        },  # 字段
        # 避难层仅用于民用高层建筑，工业建筑通常无此要求
        threshold=Threshold(
            value=5.0,
            unit="㎡/人",
            operator=">=",  # assignment
            building_types={"civil": 5.0, "industrial": 0.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.12",  # assignment
        standard="GB 50016-2014",  # assignment
        title="楼梯间设置",  # assignment
        text="一类高层公共建筑应设置防烟楼梯间。",  # assignment
        level="L1",  # assignment
        func_id="EXIST-001",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "staircase",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 工业厂房也需疏散楼梯（GB50016 3.7.6），高层厂房设封闭楼梯间
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-7.2.4",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防窗面积",  # assignment
        text="消防救援窗的净面积不应小于1.0㎡。",  # assignment
        level="L1",  # assignment
        func_id="DIM-005",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_window",
            "property": "net_area",  # assignment
            "operator": ">=",
            "threshold": 1.0,
            "unit": "㎡",
        },  # 字段
        # 工业厂房也需设置消防救援窗（GB50016 7.2.4），要求一致
        threshold=Threshold(
            value=1.0,
            unit="㎡",
            operator=">=",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    # =============================================
    # L2 规范（10条）
    # =============================================
    Clause(  # code
        clause_id="GB50016-5.5.19",  # assignment
        standard="GB 50016-2014",  # assignment
        title="人员密集场所疏散门净宽",  # assignment
        text="人员密集场所的疏散门，其净宽度不应小于1.4m。",  # assignment
        level="L2",  # assignment
        func_id="DIM-006",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "exit_door",
            "property": "clear_width",  # assignment
            "operator": ">=",
            "threshold": 1.4,
            "unit": "m",
        },  # 字段
        # 工业厂房疏散门也需≥1.2m（GB50016 3.7.5），人员密集时≥1.4m
        threshold=Threshold(
            value=1.4,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 1.4, "industrial": 1.2},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.6.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="管道井封堵",  # assignment
        text="电缆井、管道井应在每层楼板处用不低于楼板耐火极限的不燃材料封堵。",  # assignment
        level="L2",  # assignment
        func_id="EXIST-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "shaft",
            "property": "sealed",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 工业厂房管道井封堵要求一致
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.5.3",  # assignment
        standard="GB 50016-2014",  # assignment
        title="防火卷帘宽度",  # assignment
        text="除中庭外，防火分隔部位的防火卷帘宽度不应大于10m。",  # assignment
        level="L2",  # assignment
        func_id="DIM-007",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_curtain",
            "property": "width",  # assignment
            "operator": "<=",
            "threshold": 10.0,
            "unit": "m",
        },  # 字段
        # 工业厂房防火卷帘要求一致（GB50016 6.5.3适用于所有建筑类型）
        threshold=Threshold(
            value=10.0,
            unit="m",
            operator="<=",  # assignment
            building_types={"civil": 10.0, "industrial": 10.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.24",  # assignment
        standard="GB 50016-2014",  # assignment
        title="高层住宅剪刀楼梯",  # assignment
        text="高层住宅建筑的疏散楼梯，当采用剪刀楼梯时，梯段间应设置防火隔墙。",  # assignment
        level="L2",  # assignment
        func_id="EXIST-003",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "scissor_staircase",
            "property": "fire_wall_exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 剪刀楼梯仅用于民用住宅，工业厂房不适用
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 0.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-10.1.5",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防应急照明",  # assignment
        text="建筑内疏散照明的地面最低水平照度不应低于1.0lx。",  # assignment
        level="L2",  # assignment
        func_id="LIGHT-001",  # assignment
        category="lighting",  # assignment
        params={
            "target_entity": "evacuation_lighting",
            "property": "illuminance",  # assignment
            "operator": ">=",
            "threshold": 1.0,
            "unit": "lx",
        },  # 字段
        # 工业厂房应急照明要求一致（GB50016 10.1.5/10.3.1）
        threshold=Threshold(
            value=1.0,
            unit="lx",
            operator=">=",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-10.3.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="疏散指示标志",  # assignment
        text="疏散走道和安全出口处应设置疏散指示标志。",  # assignment
        level="L2",  # assignment
        func_id="EXIST-004",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "exit_sign",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 工业厂房也需设置疏散指示标志（GB50016 10.3.1）
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-8.3.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="自动灭火系统（一类高层）",  # assignment
        text="一类高层公共建筑（除游泳池、溜冰场外）应设置自动灭火系统。",  # assignment
        level="L2",  # assignment
        func_id="EXIST-005",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "sprinkler_system",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 工业厂房也需自动灭火系统（GB50016 8.3.1，高层厂房和仓库）
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-8.4.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="火灾自动报警系统",  # assignment
        text="一类高层公共建筑应设置火灾自动报警系统。",  # assignment
        level="L2",  # assignment
        func_id="EXIST-006",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_alarm",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 工业厂房也需火灾自动报警系统（GB50016 8.4.1，高层厂房和仓库）
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.7.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="保温材料燃烧等级",  # assignment
        text="建筑内外保温系统应选用A级或B1级保温材料。",  # assignment
        level="L2",  # assignment
        func_id="ATTR-002",  # assignment
        category="structure",  # assignment
        params={
            "target_entity": "insulation",
            "property": "fire_rating",  # assignment
            "operator": ">=",
            "threshold": 2.0,
            "unit": "级",
        },  # A=3, B1=2
        # 工业厂房保温要求更严，通常要求A级（GB50016 6.7.5/6.7.6）
        threshold=Threshold(
            value=2.0,
            unit="级",
            operator=">=",  # assignment
            building_types={"civil": 2.0, "industrial": 3.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.2.4",  # assignment
        standard="GB 50016-2014",  # assignment
        title="设备井防火隔墙",  # assignment
        text="电缆井、管道井与房间、走道等相连通的孔洞，应采用防火封堵材料封堵。",  # assignment
        level="L2",  # assignment
        func_id="EXIST-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "shaft",
            "property": "hole_sealed",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        # 工业厂房封堵要求一致
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    # ===== L3 新增规范（11条，对应 RESERVED_FUNCS） =====
    Clause(  # code
        clause_id="GB50016-3.4.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="防火间距判定",  # assignment
        text="厂房之间及与乙、丙、丁、戊类仓库等的防火间距不应小于表3.4.1的规定。",  # assignment
        level="L3",  # assignment
        func_id="DIST-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "building",
            "property": "distance",  # assignment
            "operator": ">=",
            "threshold": 12.0,
            "unit": "m",
        },  # 字段
        # 工业厂房防火间距要求更严
        threshold=Threshold(
            value=12.0,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 10.0, "industrial": 12.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-9.2.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="排烟窗面积判定",  # assignment
        text="排烟窗净面积不应小于房间面积的2%。",  # assignment
        level="L3",  # assignment
        func_id="DIM-008",  # assignment
        category="hvac",  # assignment
        params={
            "target_entity": "smoke_exhaust_window",
            "property": "area",  # assignment
            "operator": ">=",
            "threshold": 0.02,
            "unit": "㎡",
        },  # 字段
        threshold=Threshold(
            value=0.02,
            unit="㎡",
            operator=">=",  # assignment
            building_types={"civil": 0.02, "industrial": 0.02},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-7.3.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防电梯判定",  # assignment
        text="一类高层公共建筑和建筑高度大于32m的二类高层公共建筑应设置消防电梯。",  # assignment
        level="L3",  # assignment
        func_id="EXIST-007",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_elevator",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-7.3.5",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防电梯前室面积判定",  # assignment
        text="消防电梯前室的使用面积不应小于6㎡。",  # assignment
        level="L3",  # assignment
        func_id="AREA-002",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "elevator_lobby",
            "property": "area",  # assignment
            "operator": ">=",
            "threshold": 6.0,
            "unit": "㎡",
        },  # 字段
        threshold=Threshold(
            value=6.0,
            unit="㎡",
            operator=">=",  # assignment
            building_types={"civil": 6.0, "industrial": 6.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.17-2",  # assignment
        standard="GB 50016-2014",  # assignment
        title="袋形走道长度判定",  # assignment
        text="袋形走道长度不应大于20m。",  # assignment
        level="L3",  # assignment
        func_id="DIST-003",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "corridor",
            "property": "length",  # assignment
            "operator": "<=",
            "threshold": 20.0,
            "unit": "m",
        },  # 字段
        threshold=Threshold(
            value=20.0,
            unit="m",
            operator="<=",  # assignment
            building_types={"civil": 20.0, "industrial": 15.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-5.5.18-3",  # assignment
        standard="GB 50016-2014",  # assignment
        title="疏散出口宽度判定",  # assignment
        text="疏散出口净宽度不应小于0.9m。",  # assignment
        level="L3",  # assignment
        func_id="DIM-009",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "exit",
            "property": "clear_width",  # assignment
            "operator": ">=",
            "threshold": 0.9,
            "unit": "m",
        },  # 字段
        threshold=Threshold(
            value=0.9,
            unit="m",
            operator=">=",  # assignment
            building_types={"civil": 0.9, "industrial": 0.9},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-6.5.1-2",  # assignment
        standard="GB 50016-2014",  # assignment
        title="防火窗等级判定",  # assignment
        text="防火窗耐火极限不应低于1.0h。",  # assignment
        level="L3",  # assignment
        func_id="ATTR-003",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "fire_window",
            "property": "fire_rating",  # assignment
            "operator": ">=",
            "threshold": 1.0,
            "unit": "h",
        },  # 字段
        threshold=Threshold(
            value=1.0,
            unit="h",
            operator=">=",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-8.2.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防水箱判定",  # assignment
        text="一类高层公共建筑应设置屋顶消防水箱。",  # assignment
        level="L3",  # assignment
        func_id="EXIST-008",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "water_tank",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-8.1.3",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防水池判定",  # assignment
        text="市政供水不足时应设置消防水池。",  # assignment
        level="L3",  # assignment
        func_id="EXIST-009",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "water_reservoir",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-7.2.4-2",  # assignment
        standard="GB 50016-2014",  # assignment
        title="消防救援窗面积判定",  # assignment
        text="消防救援窗口净面积不应小于1.0㎡。",  # assignment
        level="L3",  # assignment
        func_id="DIM-010",  # assignment
        category="fire_safety",  # assignment
        params={
            "target_entity": "rescue_window",
            "property": "area",  # assignment
            "operator": ">=",
            "threshold": 1.0,
            "unit": "㎡",
        },  # 字段
        threshold=Threshold(
            value=1.0,
            unit="㎡",
            operator=">=",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
    Clause(  # code
        clause_id="GB50016-8.5.1",  # assignment
        standard="GB 50016-2014",  # assignment
        title="应急广播判定",  # assignment
        text="一类高层公共建筑应设置应急广播系统。",  # assignment
        level="L3",  # assignment
        func_id="EXIST-010",  # assignment
        category="evacuation",  # assignment
        params={
            "target_entity": "emergency_broadcast",
            "property": "exists",  # assignment
            "operator": "==",
            "threshold": 1.0,
            "unit": "有/无",
        },  # 字段
        threshold=Threshold(
            value=1.0,
            unit="有/无",
            operator="==",  # assignment
            building_types={"civil": 1.0, "industrial": 1.0},
        ),  # assignment
    ),  # code
]  # code
