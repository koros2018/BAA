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


# ── 规范 JSON 库 ─────────────────────────────────────────

# 首批 10 条 L1 + 10 条 L2 级规范
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


GB50016_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-8.2.2: 消防水泵判定
    Clause(
        clause_id="GB50016-8.2.2",
        standard="GB 50016-2014",
        title="消防水泵判定",
        text="一类高层应设消防水泵",
        level="L1",
        func_id="EXIST-013",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有/无", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.5.3: 排烟设备判定
    Clause(
        clause_id="GB50016-8.5.3",
        standard="GB 50016-2014",
        title="排烟设备判定",
        text="一类高层应设排烟设备",
        level="L1",
        func_id="EXIST-015",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有/无", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-10.3.2: 楼梯间应急照明照度判定
    Clause(
        clause_id="GB50016-10.3.2",
        standard="GB 50016-2014",
        title="楼梯间应急照明照度判定",
        text="楼梯间、前室等疏散照明照度不应低于5.0lx",
        level="L1",
        func_id="LIGHT-002",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5.0, unit="lx", operator=">=", building_types={"civil": 5.0, "industrial": 5.0}
        ),
    ),
    # GB50016-7.1.8: 消防车道净高判定
    Clause(
        clause_id="GB50016-7.1.8",
        standard="GB 50016-2014",
        title="消防车道净高判定",
        text="消防车道净高不应小于4.0m",
        level="L1",
        func_id="DIM-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4.0, unit="m", operator=">=", building_types={"civil": 4.0, "industrial": 4.0}
        ),
    ),
    # GB50016-6.4.14: 避难走道净宽判定
    Clause(
        clause_id="GB50016-6.4.14",
        standard="GB 50016-2014",
        title="避难走道净宽判定",
        text="避难走道净宽不应小于任一防火分区疏散总净宽",
        level="L1",
        func_id="DIM-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m", operator=">=", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.2.5: 救援窗口间距判定
    Clause(
        clause_id="GB50016-7.2.5",
        standard="GB 50016-2014",
        title="救援窗口间距判定",
        text="消防救援窗口间距不应大于20m",
        level="L1",
        func_id="DIST-004",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=20.0, unit="m", operator="<=", building_types={"civil": 20.0, "industrial": 20.0}
        ),
    ),
    # GB50016-5.3.1: 防火分区最大允许建筑面积判定
    Clause(
        clause_id="GB50016-5.3.1",
        standard="GB 50016-2014",
        title="防火分区最大允许建筑面积判定",
        text="一、二级耐火等级建筑防火分区最大允许建筑面积（GB50016-5.3.1）",
        level="L1",
        func_id="DIM-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2500.0,
            unit="sqm",
            operator="le",
            building_types={"civil": 2500.0, "industrial": 2500.0},
        ),
    ),
    # GB50016-6.4.3: 防烟楼梯间前室面积判定
    Clause(
        clause_id="GB50016-6.4.3",
        standard="GB 50016-2014",
        title="防烟楼梯间前室面积判定",
        text="防烟楼梯间前室使用面积不应小于6.0sqm（GB50016-6.4.3）",
        level="L1",
        func_id="DIM-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="sqm", operator="ge", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-5.5.2: 两个安全出口间距判定
    Clause(
        clause_id="GB50016-5.5.2",
        standard="GB 50016-2014",
        title="两个安全出口间距判定",
        text="两个安全出口之间的间距不应小于5.0m（GB50016-5.5.2）",
        level="L1",
        func_id="DIST-005",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5000.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 5000.0, "industrial": 5000.0},
        ),
    ),
    # GB50016-9.2.3: 排烟口与安全出口间距判定
    Clause(
        clause_id="GB50016-9.2.3",
        standard="GB 50016-2014",
        title="排烟口与安全出口间距判定",
        text="排烟口与安全出口之间的距离不应小于1.5m（GB50016-9.2.3）",
        level="L1",
        func_id="DIST-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1500.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 1500.0, "industrial": 1500.0},
        ),
    ),
    # GB50016-5.5.23: 高层建筑避难层数量判定
    Clause(
        clause_id="GB50016-5.5.23",
        standard="GB 50016-2014",
        title="高层建筑避难层数量判定",
        text="建筑高度大于100m时每50m应设一个避难层（GB50016-5.5.23）",
        level="L1",
        func_id="COUNT-002",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-10.3.3: 消防控制室应急照明照度判定
    Clause(
        clause_id="GB50016-10.3.3",
        standard="GB 50016-2014",
        title="消防控制室应急照明照度判定",
        text="消防控制室、消防水泵房等应保持正常照明照度（GB50016-10.3.3）",
        level="L1",
        func_id="LIGHT-003",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="lx",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.5.16: 观众厅疏散门数量判定
    Clause(
        clause_id="GB50016-5.5.16",
        standard="GB 50016-2014",
        title="观众厅疏散门数量判定",
        text="观众厅每个疏散门的平均疏散人数不应超过250人（GB50016-5.5.16）",
        level="L1",
        func_id="DIM-024",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="个", operator="ge", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.5.20: 地下建筑疏散楼梯宽度判定
    Clause(
        clause_id="GB50016-5.5.20",
        standard="GB 50016-2014",
        title="地下建筑疏散楼梯宽度判定",
        text="地下或半地下建筑疏散楼梯净宽度不应小于1.1m（GB50016-5.5.20）",
        level="L1",
        func_id="DIM-025",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1100.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 1100.0, "industrial": 1100.0},
        ),
    ),
    # GB50016-6.4.5: 室外疏散楼梯净宽判定
    Clause(
        clause_id="GB50016-6.4.5",
        standard="GB 50016-2014",
        title="室外疏散楼梯净宽判定",
        text="室外疏散楼梯净宽度不应小于0.9m（GB50016-6.4.5）",
        level="L1",
        func_id="DIM-026",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=900.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 900.0, "industrial": 900.0},
        ),
    ),
    # GB50016-8.3.3: 自动喷水灭火系统判定
    Clause(
        clause_id="GB50016-8.3.3",
        standard="GB 50016-2014",
        title="自动喷水灭火系统判定",
        text="一类高层民用建筑应设自动喷水灭火系统（GB50016-8.3.3）",
        level="L1",
        func_id="EXIST-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.6.1: 消防专用电话判定
    Clause(
        clause_id="GB50016-8.6.1",
        standard="GB 50016-2014",
        title="消防专用电话判定",
        text="消防控制室应设消防专用电话总机（GB50016-8.6.1）",
        level="L1",
        func_id="EXIST-019",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.1.6: 消防控制室判定
    Clause(
        clause_id="GB50016-8.1.6",
        standard="GB 50016-2014",
        title="消防控制室判定",
        text="设有火灾自动报警系统的建筑应设消防控制室（GB50016-8.1.6）",
        level="L1",
        func_id="EXIST-020",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-9.3.1: 机械排烟系统排烟量判定
    Clause(
        clause_id="GB50016-9.3.1",
        standard="GB 50016-2014",
        title="机械排烟系统排烟量判定",
        text="机械排烟系统最小排烟量不应小于7200m³/h（GB50016-9.3.1）",
        level="L1",
        func_id="DIM-027",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=7200.0,
            unit="m3h",
            operator="ge",
            building_types={"civil": 7200.0, "industrial": 7200.0},
        ),
    ),
    # GB50016-5.4.15: 储油间储油量判定
    Clause(
        clause_id="GB50016-5.4.15",
        standard="GB 50016-2014",
        title="储油间储油量判定",
        text="锅炉房储油间储油量不应大于1m³（GB50016-5.4.15）",
        level="L1",
        func_id="DIM-028",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m3", operator="le", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.3.8: 消防电梯运行速度判定
    Clause(
        clause_id="GB50016-7.3.8",
        standard="GB 50016-2014",
        title="消防电梯运行速度判定",
        text="消防电梯从首层到顶层运行时间不应超过60s（GB50016-7.3.8）",
        level="L1",
        func_id="DIM-029",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=60.0, unit="s", operator="le", building_types={"civil": 60.0, "industrial": 60.0}
        ),
    ),
    # GB50016-8.1.7: 消防控制室面积判定
    Clause(
        clause_id="GB50016-8.1.7",
        standard="GB 50016-2014",
        title="消防控制室面积判定",
        text="消防控制室面积不应小于30sqm（GB50016-8.1.7）",
        level="L1",
        func_id="AREA-004",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 30.0, "industrial": 30.0},
        ),
    ),
    # GB50016-7.2.2: 消防救援场地宽度判定
    Clause(
        clause_id="GB50016-7.2.2",
        standard="GB 50016-2014",
        title="消防救援场地宽度判定",
        text="消防救援场地宽度不应小于10m（GB50016-7.2.2）",
        level="L1",
        func_id="DIM-030",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=10000.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 10000.0, "industrial": 10000.0},
        ),
    ),
    # GB50016-7.1.3: 消防车道转弯半径判定
    Clause(
        clause_id="GB50016-7.1.3",
        standard="GB 50016-2014",
        title="消防车道转弯半径判定",
        text="消防车道转弯半径不应小于9m（GB50016-7.1.3）",
        level="L1",
        func_id="DIM-031",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=9000.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 9000.0, "industrial": 9000.0},
        ),
    ),
    # GB50016-5.5.25: 封闭楼梯间数量判定
    Clause(
        clause_id="GB50016-5.5.25",
        standard="GB 50016-2014",
        title="封闭楼梯间数量判定",
        text="建筑高度不大于21m的住宅建筑可采用敞开楼梯间（GB50016-5.5.25）",
        level="L1",
        func_id="COUNT-003",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.4.11: 疏散门开启方向判定
    Clause(
        clause_id="GB50016-6.4.11",
        standard="GB 50016-2014",
        title="疏散门开启方向判定",
        text="疏散门应向疏散方向开启（GB50016-6.4.11）",
        level="L1",
        func_id="EXIST-021",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.3.5: 防火阀设置判定
    Clause(
        clause_id="GB50016-6.3.5",
        standard="GB 50016-2014",
        title="防火阀设置判定",
        text="通风管道穿越防火分区处应设防火阀（GB50016-6.3.5）",
        level="L1",
        func_id="EXIST-022",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-10.2.1: 电气线路防火保护判定
    Clause(
        clause_id="GB50016-10.2.1",
        standard="GB 50016-2014",
        title="电气线路防火保护判定",
        text="消防配电线路应采用阻燃电缆并采取防火保护措施（GB50016-10.2.1）",
        level="L1",
        func_id="EXIST-024",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="个", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-5.1.2: 楼板耐火极限判定
    Clause(
        clause_id="GB50016-5.1.2",
        standard="GB 50016-2014",
        title="楼板耐火极限判定",
        text="一级耐火等级建筑楼板耐火极限不应低于1.50h（GB50016-5.1.2）",
        level="L1",
        func_id="ATTR-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.5, unit="h", operator="ge", building_types={"civil": 1.5, "industrial": 1.5}
        ),
    ),
    # GB50016-6.2.9: 建筑幕墙防火判定
    Clause(
        clause_id="GB50016-6.2.9",
        standard="GB 50016-2014",
        title="建筑幕墙防火判定",
        text="建筑幕墙在每层楼板处应采用防火封堵（GB50016-6.2.9）",
        level="L1",
        func_id="ATTR-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="h", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-5.5.17: 地下商店疏散距离判定
    Clause(
        clause_id="GB50016-5.5.17-3",
        standard="GB 50016-2014",
        title="地下商店疏散距离判定",
        text="地下商店疏散距离不应大于30m（GB50016-5.5.17-3）",
        level="L1",
        func_id="DIM-056",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-5.5.21: 歌舞娱乐放映场所疏散宽度判定
    Clause(
        clause_id="GB50016-5.5.21-2",
        standard="GB 50016-2014",
        title="歌舞娱乐放映场所疏散宽度判定",
        text="歌舞娱乐放映场所疏散总净宽不应小于每100人1.0m（GB50016-5.5.21-2）",
        level="L1",
        func_id="DIM-057",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0,
            unit="m/百人",
            operator="ge",
            building_types={"civil": 1.0, "industrial": 1.0},
        ),
    ),
    # GB50016-5.5.24: 高层病房楼避难间面积判定
    Clause(
        clause_id="GB50016-5.5.24-2",
        standard="GB 50016-2014",
        title="高层病房楼避难间面积判定",
        text="高层病房楼避难间净面积不应小于25.0sqm（GB50016-5.5.24-2）",
        level="L1",
        func_id="DIM-058",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 25.0, "industrial": 25.0},
        ),
    ),
    # GB50016-5.5.24: 手术室避难间面积判定
    Clause(
        clause_id="GB50016-5.5.24-3",
        standard="GB 50016-2014",
        title="手术室避难间面积判定",
        text="手术室避难间净面积不应小于25.0sqm（GB50016-5.5.24-3）",
        level="L1",
        func_id="AREA-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 25.0, "industrial": 25.0},
        ),
    ),
    # GB50016-7.3.2: 消防电梯数量判定
    Clause(
        clause_id="GB50016-7.3.2",
        standard="GB 50016-2014",
        title="消防电梯数量判定",
        text="高层民用建筑每个防火分区消防电梯不应少于1台（GB50016-7.3.2）",
        level="L1",
        func_id="COUNT-014",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-10.1.6: 应急电源设置判定
    Clause(
        clause_id="GB50016-10.1.6",
        standard="GB 50016-2014",
        title="应急电源设置判定",
        text="消防控制室、消防水泵房等应设应急电源（GB50016-10.1.6）",
        level="L1",
        func_id="EXIST-042",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-8.3.8: 气体灭火系统判定
    Clause(
        clause_id="GB50016-8.3.8",
        standard="GB 50016-2014",
        title="气体灭火系统判定",
        text="变配电室、计算机房等应设气体灭火系统（GB50016-8.3.8）",
        level="L1",
        func_id="EXIST-043",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="套", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-10.2.3: 配电箱防火判定
    Clause(
        clause_id="GB50016-10.2.3",
        standard="GB 50016-2014",
        title="配电箱防火判定",
        text="配电箱不应直接安装在可燃材料上（GB50016-10.2.3）",
        level="L1",
        func_id="EXIST-045",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-5.5.13: 走道最小净宽度判定
    Clause(
        clause_id="GB50016-5.5.13",
        standard="GB 50016-2014",
        title="走道最小净宽度判定",
        text="疏散走道最小净宽度不应小于1.1m（GB50016-5.5.13）",
        level="L1",
        func_id="DIM-078",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.1, unit="m", operator=">=", building_types={"civil": 1.1, "industrial": 1.1}
        ),
    ),
    # GB50016-5.5.15: 房间疏散门数量判定
    Clause(
        clause_id="GB50016-5.5.15",
        standard="GB 50016-2014",
        title="房间疏散门数量判定",
        text="公共建筑内每个房间疏散门不应少于2个（GB50016-5.5.15）",
        level="L1",
        func_id="COUNT-016",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="个", operator=">=", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.5.21: 疏散宽度指标判定
    Clause(
        clause_id="GB50016-5.5.21",
        standard="GB 50016-2014",
        title="疏散宽度指标判定",
        text="人员密集场所疏散宽度应按百人宽度指标计算（GB50016-5.5.21）",
        level="L1",
        func_id="DIM-079",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0,
            unit="m/百人",
            operator=">=",
            building_types={"civil": 1.0, "industrial": 1.0},
        ),
    ),
    # GB50016-5.5.26: 住宅剪刀楼梯判定
    Clause(
        clause_id="GB50016-5.5.26",
        standard="GB 50016-2014",
        title="住宅剪刀楼梯判定",
        text="住宅建筑剪刀楼梯间应设前室（GB50016-5.5.26）",
        level="L1",
        func_id="EXIST-050",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.5.29: 住宅安全出口数量判定
    Clause(
        clause_id="GB50016-5.5.29",
        standard="GB 50016-2014",
        title="住宅安全出口数量判定",
        text="住宅建筑每个单元安全出口不应少于2个（GB50016-5.5.29）",
        level="L1",
        func_id="COUNT-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="个", operator=">=", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.5.30: 住宅走道宽度判定
    Clause(
        clause_id="GB50016-5.5.30",
        standard="GB 50016-2014",
        title="住宅走道宽度判定",
        text="住宅建筑疏散走道净宽度不应小于1.1m（GB50016-5.5.30）",
        level="L1",
        func_id="DIM-080",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.1, unit="m", operator=">=", building_types={"civil": 1.1, "industrial": 1.1}
        ),
    ),
    # GB50016-5.5.31: 住宅楼梯间形式判定
    Clause(
        clause_id="GB50016-5.5.31",
        standard="GB 50016-2014",
        title="住宅楼梯间形式判定",
        text="住宅建筑高度大于54m时每单元应设1个防烟楼梯间（GB50016-5.5.31）",
        level="L1",
        func_id="EXIST-051",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-6.1.5: 防火墙上不应开设门窗洞口判定
    Clause(
        clause_id="GB50016-6.1.5",
        standard="GB 50016-2014",
        title="防火墙上不应开设门窗洞口判定",
        text="防火墙上不应开设门、窗、洞口（GB50016-6.1.5）",
        level="L1",
        func_id="EXIST-052",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="not_exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-6.2.5: 管道井防火封堵判定
    Clause(
        clause_id="GB50016-6.2.5",
        standard="GB 50016-2014",
        title="管道井防火封堵判定",
        text="管道井应在每层楼板处进行防火封堵（GB50016-6.2.5）",
        level="L1",
        func_id="EXIST-053",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-6.4.2: 封闭楼梯间门宽度判定
    Clause(
        clause_id="GB50016-6.4.2",
        standard="GB 50016-2014",
        title="封闭楼梯间门宽度判定",
        text="封闭楼梯间门应向疏散方向开启，净宽不小于1.0m（GB50016-6.4.2）",
        level="L1",
        func_id="DIM-082",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m", operator=">=", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.4.6: 室外楼梯净宽判定
    Clause(
        clause_id="GB50016-6.4.6",
        standard="GB 50016-2014",
        title="室外楼梯净宽判定",
        text="室外疏散楼梯净宽度不应小于0.9m（GB50016-6.4.6）",
        level="L1",
        func_id="DIM-083",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.9, unit="m", operator=">=", building_types={"civil": 0.9, "industrial": 0.9}
        ),
    ),
    # GB50016-6.4.7: 首层疏散门净宽判定
    Clause(
        clause_id="GB50016-6.4.7",
        standard="GB 50016-2014",
        title="首层疏散门净宽判定",
        text="首层疏散外门净宽度不应小于1.2m（GB50016-6.4.7）",
        level="L1",
        func_id="DIM-084",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator=">=", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-6.7.4: 保温材料燃烧性能判定
    Clause(
        clause_id="GB50016-6.7.4",
        standard="GB 50016-2014",
        title="保温材料燃烧性能判定",
        text="建筑外墙保温材料燃烧性能不应低于B1级（GB50016-6.7.4）",
        level="L1",
        func_id="ATTR-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="级", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.1.2: 消防车道净高判定
    Clause(
        clause_id="GB50016-7.1.2",
        standard="GB 50016-2014",
        title="消防车道净高判定",
        text="消防车道净高不应小于4.0m（GB50016-7.1.2）",
        level="L1",
        func_id="DIM-085",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4.0, unit="m", operator=">=", building_types={"civil": 4.0, "industrial": 4.0}
        ),
    ),
    # GB50016-7.1.4: 消防车道转弯半径判定
    Clause(
        clause_id="GB50016-7.1.4",
        standard="GB 50016-2014",
        title="消防车道转弯半径判定",
        text="消防车道转弯半径不应小于12m（GB50016-7.1.4）",
        level="L1",
        func_id="DIM-086",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=12.0, unit="m", operator=">=", building_types={"civil": 12.0, "industrial": 12.0}
        ),
    ),
    # GB50016-7.2.1: 消防救援场地面积判定
    Clause(
        clause_id="GB50016-7.2.1",
        standard="GB 50016-2014",
        title="消防救援场地面积判定",
        text="消防救援场地长度不应小于15m，宽度不应小于10m（GB50016-7.2.1）",
        level="L1",
        func_id="AREA-010",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=150.0,
            unit="㎡",
            operator=">=",
            building_types={"civil": 150.0, "industrial": 150.0},
        ),
    ),
    # GB50016-7.2.3: 救援窗口尺寸判定
    Clause(
        clause_id="GB50016-7.2.3",
        standard="GB 50016-2014",
        title="救援窗口尺寸判定",
        text="救援窗口净高不应小于1.0m，净宽不应小于1.0m（GB50016-7.2.3）",
        level="L1",
        func_id="DIM-087",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="m", operator=">=", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.1.2: 消防水源判定
    Clause(
        clause_id="GB50016-8.1.2",
        standard="GB 50016-2014",
        title="消防水源判定",
        text="建筑应设置消防水源（GB50016-8.1.2）",
        level="L1",
        func_id="EXIST-055",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-8.2.3: 自然排烟窗口面积判定
    Clause(
        clause_id="GB50016-8.2.3",
        standard="GB 50016-2014",
        title="自然排烟窗口面积判定",
        text="自然排烟窗口面积不应小于地面面积的2%（GB50016-8.2.3）",
        level="L1",
        func_id="AREA-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02, unit="%", operator="ge", building_types={"civil": 0.02, "industrial": 0.02}
        ),
    ),
    # GB50016-6.4.1: 楼梯间首层直通室外判定
    Clause(
        clause_id="GB50016-6.4.1",
        standard="GB 50016-2014",
        title="楼梯间首层直通室外判定",
        text="疏散楼梯间首层应直通室外（GB50016-6.4.1）",
        level="L1",
        func_id="EXIST-065",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
]


GB50974_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-4.3.2: 消防水池有效容积判定
    Clause(
        clause_id="GB50974-4.3.2",
        standard="GB 50974-2014",
        title="消防水池有效容积判定",
        text="消防水池有效容积应满足火灾延续时间内消防用水量（GB50974-4.3.2）",
        level="L1",
        func_id="DIM-035",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=500.0,
            unit="m3",
            operator="ge",
            building_types={"civil": 500.0, "industrial": 500.0},
        ),
    ),
    # GB50016-4.3.6: 消防水池分格判定
    Clause(
        clause_id="GB50974-4.3.6",
        standard="GB 50974-2014",
        title="消防水池分格判定",
        text="消防水池总有效容积大于500m³时宜设两格能独立使用的消防水池（GB50974-4.3.6）",
        level="L1",
        func_id="COUNT-005",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.2.1: 高位消防水箱有效容积判定
    Clause(
        clause_id="GB50974-5.2.1",
        standard="GB 50974-2014",
        title="高位消防水箱有效容积判定",
        text="一类高层公共建筑高位消防水箱有效容积不应小于36m³（GB50974-5.2.1）",
        level="L1",
        func_id="DIM-036",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=36.0, unit="m3", operator="ge", building_types={"civil": 36.0, "industrial": 36.0}
        ),
    ),
    # GB50016-5.2.2: 消防水箱有效水位判定
    Clause(
        clause_id="GB50974-5.2.2",
        standard="GB 50974-2014",
        title="消防水箱有效水位判定",
        text="高位消防水箱最低有效水位应满足灭火设施压力要求（GB50974-5.2.2）",
        level="L1",
        func_id="DIM-037",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="m", operator="ge", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-5.3.2: 稳压泵流量判定
    Clause(
        clause_id="GB50974-5.3.2",
        standard="GB 50974-2014",
        title="稳压泵流量判定",
        text="消防给水稳压泵流量不应小于1.0L/s（GB50974-5.3.2）",
        level="L1",
        func_id="DIM-038",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="L/s", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-5.4.3: 水泵接合器数量判定
    Clause(
        clause_id="GB50974-5.4.3",
        standard="GB 50974-2014",
        title="水泵接合器数量判定",
        text="消防水泵接合器数量应按消防用水量计算确定（GB50974-5.4.3）",
        level="L1",
        func_id="COUNT-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.5.12: 消防水泵房排水判定
    Clause(
        clause_id="GB50974-5.5.12",
        standard="GB 50974-2014",
        title="消防水泵房排水判定",
        text="消防水泵房应设排水设施（GB50974-5.5.12）",
        level="L1",
        func_id="EXIST-025",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-6.1.8: 室外消火栓间距判定
    Clause(
        clause_id="GB50974-6.1.8",
        standard="GB 50974-2014",
        title="室外消火栓间距判定",
        text="室外消火栓布置间距不应大于120m（GB50974-6.1.8）",
        level="L1",
        func_id="DIST-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=120.0,
            unit="m",
            operator="le",
            building_types={"civil": 120.0, "industrial": 120.0},
        ),
    ),
    # GB50016-6.2.1: 室内消火栓间距判定
    Clause(
        clause_id="GB50974-6.2.1",
        standard="GB 50974-2014",
        title="室内消火栓间距判定",
        text="室内消火栓间距不应大于30m（GB50974-6.2.1）",
        level="L1",
        func_id="DIST-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-6.4.2: 消防水带长度判定
    Clause(
        clause_id="GB50974-6.4.2",
        standard="GB 50974-2014",
        title="消防水带长度判定",
        text="消防水带长度不宜大于25m（GB50974-6.4.2）",
        level="L1",
        func_id="DIM-039",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="le", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
    # GB50016-7.4.2: 消防水枪充实水柱判定
    Clause(
        clause_id="GB50974-7.4.2",
        standard="GB 50974-2014",
        title="消防水枪充实水柱判定",
        text="消防水枪充实水柱不应小于13m（GB50974-7.4.2）",
        level="L1",
        func_id="DIM-040",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=13.0, unit="m", operator="ge", building_types={"civil": 13.0, "industrial": 13.0}
        ),
    ),
    # GB50016-8.1.2: 消防给水管道压力判定
    Clause(
        clause_id="GB50974-8.1.2",
        standard="GB 50974-2014",
        title="消防给水管道压力判定",
        text="消防给水管道最低压力不应小于0.10MPa（GB50974-8.1.2）",
        level="L1",
        func_id="ATTR-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.1, unit="MPa", operator="ge", building_types={"civil": 0.1, "industrial": 0.1}
        ),
    ),
    # GB50016-9.3.1: 消防水泵流量判定
    Clause(
        clause_id="GB50974-9.3.1",
        standard="GB 50974-2014",
        title="消防水泵流量判定",
        text="消防水泵流量不应小于设计消防用水量（GB50974-9.3.1）",
        level="L1",
        func_id="DIM-041",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=20.0,
            unit="L/s",
            operator="ge",
            building_types={"civil": 20.0, "industrial": 20.0},
        ),
    ),
    # GB50016-11.0.4: 消防水泵启动时间判定
    Clause(
        clause_id="GB50974-11.0.4",
        standard="GB 50974-2014",
        title="消防水泵启动时间判定",
        text="消防水泵从接到启泵信号到正常运转时间不应大于2min（GB50974-11.0.4）",
        level="L1",
        func_id="DIM-042",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="min", operator="le", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-12.3.1: 消防管道管径判定
    Clause(
        clause_id="GB50974-12.3.1",
        standard="GB 50974-2014",
        title="消防管道管径判定",
        text="消防给水管道管径不应小于DN100（GB50974-12.3.1）",
        level="L1",
        func_id="DIM-043",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.1.12: 消防水泵吸水高度判定
    Clause(
        clause_id="GB50974-5.1.12",
        standard="GB 50974-2014",
        title="消防水泵吸水高度判定",
        text="消防水泵吸水高度不应大于6.0m（GB50974-5.1.12）",
        level="L1",
        func_id="DIM-044",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="m", operator="le", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-5.1.13: 消防水泵出水管压力判定
    Clause(
        clause_id="GB50974-5.1.13",
        standard="GB 50974-2014",
        title="消防水泵出水管压力判定",
        text="消防水泵出水管压力不应小于设计工作压力（GB50974-5.1.13）",
        level="L1",
        func_id="DIM-045",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.8, unit="MPa", operator="ge", building_types={"civil": 0.8, "industrial": 0.8}
        ),
    ),
    # GB50016-4.3.3: 消防水池进水管管径判定
    Clause(
        clause_id="GB50974-4.3.3",
        standard="GB 50974-2014",
        title="消防水池进水管管径判定",
        text="消防水池进水管管径不应小于DN100（GB50974-4.3.3）",
        level="L1",
        func_id="DIM-046",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="mm",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.2.4: 消防水箱间温度判定
    Clause(
        clause_id="GB50974-5.2.4",
        standard="GB 50974-2014",
        title="消防水箱间温度判定",
        text="消防水箱间温度不应低于5℃（GB50974-5.2.4）",
        level="L1",
        func_id="DIM-047",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5.0, unit="℃", operator="ge", building_types={"civil": 5.0, "industrial": 5.0}
        ),
    ),
    # GB50016-5.1.6: 消防水泵数量判定
    Clause(
        clause_id="GB50974-5.1.6",
        standard="GB 50974-2014",
        title="消防水泵数量判定",
        text="消防水泵应设置不少于2台（GB50974-5.1.6）",
        level="L1",
        func_id="COUNT-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="台", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.1.11: 消防水泵试水管判定
    Clause(
        clause_id="GB50974-5.1.11",
        standard="GB 50974-2014",
        title="消防水泵试水管判定",
        text="消防水泵应设置试水管（GB50974-5.1.11）",
        level="L1",
        func_id="EXIST-027",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-8.2.3: 消防给水管道材质判定
    Clause(
        clause_id="GB50974-8.2.3",
        standard="GB 50974-2014",
        title="消防给水管道材质判定",
        text="消防给水管道应采用热镀锌钢管等金属管材（GB50974-8.2.3）",
        level="L1",
        func_id="ATTR-009",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="级", operator="ge", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-4.3.5: 消防水池取水口高度判定
    Clause(
        clause_id="GB50974-4.3.5",
        standard="GB 50974-2014",
        title="消防水池取水口高度判定",
        text="消防水池取水口高度不宜大于6.0m（GB50974-4.3.5）",
        level="L1",
        func_id="DIM-051",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="m", operator="le", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-5.5.8: 消防水泵基础高度判定
    Clause(
        clause_id="GB50974-5.5.8",
        standard="GB 50974-2014",
        title="消防水泵基础高度判定",
        text="消防水泵基础高出地面不宜小于0.10m（GB50974-5.5.8）",
        level="L1",
        func_id="DIM-052",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.1, unit="m", operator="ge", building_types={"civil": 0.1, "industrial": 0.1}
        ),
    ),
    # GB50016-12.4.1: 消防给水管网试验压力判定
    Clause(
        clause_id="GB50974-12.4.1",
        standard="GB 50974-2014",
        title="消防给水管网试验压力判定",
        text="消防给水管网试压压力不应小于1.4MPa（GB50974-12.4.1）",
        level="L1",
        func_id="DIM-055",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.4, unit="MPa", operator="ge", building_types={"civil": 1.4, "industrial": 1.4}
        ),
    ),
    # GB50016-5.4.4: 消防水泵接合器数量下限判定
    Clause(
        clause_id="GB50974-5.4.4",
        standard="GB 50974-2014",
        title="消防水泵接合器数量下限判定",
        text="消防水泵接合器数量不应少于2个（GB50974-5.4.4）",
        level="L1",
        func_id="COUNT-009",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-7.4.5: 室内消火栓竖管数量判定
    Clause(
        clause_id="GB50974-7.4.5",
        standard="GB 50974-2014",
        title="室内消火栓竖管数量判定",
        text="室内消火栓竖管数量不应少于2根（GB50974-7.4.5）",
        level="L1",
        func_id="COUNT-010",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="根", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.4.5: 水泵接合器与门窗距离判定
    Clause(
        clause_id="GB50974-5.4.5",
        standard="GB 50974-2014",
        title="水泵接合器与门窗距离判定",
        text="水泵接合器距门窗洞口不宜小于2.0m（GB50974-5.4.5）",
        level="L1",
        func_id="DIST-015",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.0, unit="m", operator="ge", building_types={"civil": 2.0, "industrial": 2.0}
        ),
    ),
    # GB50016-11.0.1: 消防水泵启泵按钮判定
    Clause(
        clause_id="GB50974-11.0.1",
        standard="GB 50974-2014",
        title="消防水泵启泵按钮判定",
        text="消防水泵应设置现场手动启泵按钮（GB50974-11.0.1）",
        level="L1",
        func_id="EXIST-030",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-4.3.8: 消防水池水位显示判定
    Clause(
        clause_id="GB50974-4.3.8",
        standard="GB 50974-2014",
        title="消防水池水位显示判定",
        text="消防水池应设置就地水位显示装置（GB50974-4.3.8）",
        level="L1",
        func_id="EXIST-031",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-5.2.3: 消防水箱进水压力（高位水箱）
    Clause(
        clause_id="GB50974-5.2.3",
        standard="GB 50974-2014",
        title="消防水箱进水压力（高位水箱）",
        text="高位消防水箱进水压力不应大于0.1MPa（GB50974-5.2.3）",
        level="L1",
        func_id="DIM-059",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.1, unit="MPa", operator="le", building_types={"civil": 0.1, "industrial": 0.1}
        ),
    ),
    # GB50016-5.2.5: 消防水箱最高水位
    Clause(
        clause_id="GB50974-5.2.5",
        standard="GB 50974-2014",
        title="消防水箱最高水位",
        text="消防水箱最高水位不应低于有效水深（GB50974-5.2.5）",
        level="L1",
        func_id="DIM-060",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.7, unit="m", operator="ge", building_types={"civil": 0.7, "industrial": 0.7}
        ),
    ),
    # GB50016-4.3.3: 消防水池储水量下限（消火栓系统）
    Clause(
        clause_id="GB50974-4.3.3-2",
        standard="GB 50974-2014",
        title="消防水池储水量下限（消火栓系统）",
        text="室外消火栓系统消防水池有效储水量不应小于100m³（GB50974-4.3.3-2）",
        level="L1",
        func_id="DIM-061",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-4.3.3: 消防水池储水量下限（自喷系统）
    Clause(
        clause_id="GB50974-4.3.3-3",
        standard="GB 50974-2014",
        title="消防水池储水量下限（自喷系统）",
        text="室内自动喷水灭火系统消防水池有效储水量不应小于150m³（GB50974-4.3.3-3）",
        level="L1",
        func_id="DIM-062",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=150.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 150.0, "industrial": 150.0},
        ),
    ),
    # GB50016-5.1.15: 消防水箱容积（临时高压系统）
    Clause(
        clause_id="GB50974-5.1.15",
        standard="GB 50974-2014",
        title="消防水箱容积（临时高压系统）",
        text="临时高压系统消防水箱有效容积不应小于100m³（GB50974-5.1.15）",
        level="L1",
        func_id="DIM-063",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-5.1.16: 消防水箱出水流量
    Clause(
        clause_id="GB50974-5.1.16",
        standard="GB 50974-2014",
        title="消防水箱出水流量",
        text="消防水箱出水流量不应小于10L/s（GB50974-5.1.16）",
        level="L1",
        func_id="DIM-064",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=10.0,
            unit="L/s",
            operator="ge",
            building_types={"civil": 10.0, "industrial": 10.0},
        ),
    ),
    # GB50016-5.2.6: 消防水箱间与卧室距离
    Clause(
        clause_id="GB50974-5.2.6",
        standard="GB 50974-2014",
        title="消防水箱间与卧室距离",
        text="消防水箱间不应设置于卧室上方或相邻（GB50974-5.2.6）",
        level="L1",
        func_id="DIST-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.0, unit="m", operator="lt", building_types={"civil": 0.0, "industrial": 0.0}
        ),
    ),
    # GB50016-5.5.4: 消防水泵房防火分隔距离
    Clause(
        clause_id="GB50974-5.5.4",
        standard="GB 50974-2014",
        title="消防水泵房防火分隔距离",
        text="消防水泵房与人员密集场所应设防火隔墙分隔（GB50974-5.5.4）",
        level="L1",
        func_id="DIST-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=6.0, unit="m", operator="ge", building_types={"civil": 6.0, "industrial": 6.0}
        ),
    ),
    # GB50016-4.3.7: 消防水池与建筑物距离
    Clause(
        clause_id="GB50974-4.3.7",
        standard="GB 50974-2014",
        title="消防水池与建筑物距离",
        text="室外消防水池与民用建筑距离不宜小于25m（GB50974-4.3.7）",
        level="L1",
        func_id="DIST-019",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="ge", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
    # GB50016-5.1.6: 消防水泵出口流量下限（临时高压）
    Clause(
        clause_id="GB50974-5.1.6-2",
        standard="GB 50974-2014",
        title="消防水泵出口流量下限（临时高压）",
        text="临时高压系统消防水泵出水流量不应少于2路（GB50974-5.1.6）",
        level="L1",
        func_id="COUNT-011",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="路", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.1.6: 消防给水系统备用泵数量
    Clause(
        clause_id="GB50974-5.1.6-1",
        standard="GB 50974-2014",
        title="消防给水系统备用泵数量",
        text="消防给水系统应设1台备用泵（GB50974-5.1.6）",
        level="L1",
        func_id="COUNT-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="台", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-5.2.7: 消防水箱间消防给水管道阀门
    Clause(
        clause_id="GB50974-5.2.7",
        standard="GB 50974-2014",
        title="消防水箱间消防给水管道阀门",
        text="消防水箱间进水管道应设止回阀（GB50974-5.2.7）",
        level="L1",
        func_id="EXIST-032",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.5.5: 消防水泵房排水设施
    Clause(
        clause_id="GB50974-5.5.5",
        standard="GB 50974-2014",
        title="消防水泵房排水设施",
        text="消防水泵房应设排水设施（GB50974-5.5.5）",
        level="L1",
        func_id="EXIST-033",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-11.0.14: 消防水泵房备用电源切换装置
    Clause(
        clause_id="GB50974-11.0.14",
        standard="GB 50974-2014",
        title="消防水泵房备用电源切换装置",
        text="消防水泵房应设备用电源切换装置（GB50974-11.0.14）",
        level="L1",
        func_id="EXIST-034",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.4.1: 消防水泵接合器设置判定
    Clause(
        clause_id="GB50974-5.4.1",
        standard="GB 50974-2014",
        title="消防水泵接合器设置判定",
        text="高层民用建筑应设消防水泵接合器（GB50974-5.4.1）",
        level="L1",
        func_id="EXIST-038",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="个", operator="ge", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-4.3.1: 消防水池最小容积判定
    Clause(
        clause_id="GB50974-4.3.1",
        standard="GB 50974-2014",
        title="消防水池最小容积判定",
        text="消防水池最小有效容积不应小于100m³（GB50974-4.3.1）",
        level="L1",
        func_id="DIM-077",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=100.0,
            unit="m³",
            operator="ge",
            building_types={"civil": 100.0, "industrial": 100.0},
        ),
    ),
    # GB50016-7.4.10: 室内消火栓间距判定
    Clause(
        clause_id="GB50974-7.4.10",
        standard="GB 50974-2014",
        title="室内消火栓间距判定",
        text="室内消火栓最大间距不应大于30m（GB50974-7.4.10）",
        level="L1",
        func_id="DIST-022",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-7.3.1: 室外消火栓间距判定
    Clause(
        clause_id="GB50974-7.3.1",
        standard="GB 50974-2014",
        title="室外消火栓间距判定",
        text="室外消火栓最大间距不应大于120m（GB50974-7.3.1）",
        level="L1",
        func_id="DIST-023",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=120.0,
            unit="m",
            operator="le",
            building_types={"civil": 120.0, "industrial": 120.0},
        ),
    ),
    # GB50016-7.4.1: 消火栓间距判定
    Clause(
        clause_id="GB50974-7.4.1",
        standard="GB 50974-2014",
        title="消火栓间距判定",
        text="室内消火栓间距不应大于30m（GB50974-7.4.1）",
        level="L1",
        func_id="DIST-025",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="<=", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-7.4.3: 消火栓保护半径判定
    Clause(
        clause_id="GB50974-7.4.3",
        standard="GB 50974-2014",
        title="消火栓保护半径判定",
        text="室内消火栓保护半径不应大于25m（GB50974-7.4.3）",
        level="L1",
        func_id="DIST-026",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="<=", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
    # GB50016-7.4.4: 消火栓出口压力判定
    Clause(
        clause_id="GB50974-7.4.4",
        standard="GB 50974-2014",
        title="消火栓出口压力判定",
        text="消火栓栓口动压不应大于0.50MPa（GB50974-7.4.4）",
        level="L1",
        func_id="ATTR-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.5, unit="MPa", operator="<=", building_types={"civil": 0.5, "industrial": 0.5}
        ),
    ),
    # GB50016-7.4.6: 消防软管卷盘判定
    Clause(
        clause_id="GB50974-7.4.6",
        standard="GB 50974-2014",
        title="消防软管卷盘判定",
        text="人员密集场所应设消防软管卷盘（GB50974-7.4.6）",
        level="L1",
        func_id="EXIST-057",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-7.4.7: 消防水喉判定
    Clause(
        clause_id="GB50974-7.4.7",
        standard="GB 50974-2014",
        title="消防水喉判定",
        text="高层民用建筑应设消防水喉（GB50974-7.4.7）",
        level="L1",
        func_id="EXIST-058",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-7.4.12: 消防水带长度判定
    Clause(
        clause_id="GB50974-7.4.12",
        standard="GB 50974-2014",
        title="消防水带长度判定",
        text="消防水带长度不应超过25m（GB50974-7.4.12）",
        level="L1",
        func_id="DIM-093",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=25.0, unit="m", operator="<=", building_types={"civil": 25.0, "industrial": 25.0}
        ),
    ),
]


GB50763_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-3.3.2: 轮椅坡道坡度判定
    Clause(
        clause_id="GB50763-3.3.2",
        standard="GB 50763-2012",
        title="轮椅坡道坡度判定",
        text="坡道坡度不应大于1:12(8.33%)",
        level="L1",
        func_id="ACCESS-001",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=8.33, unit="%", operator="<=", building_types={"civil": 8.33, "industrial": 8.33}
        ),
    ),
    # GB50016-3.3.3: 轮椅坡道宽度判定
    Clause(
        clause_id="GB50763-3.3.3",
        standard="GB 50763-2012",
        title="轮椅坡道宽度判定",
        text="坡道净宽不应小于1.20m",
        level="L1",
        func_id="ACCESS-002",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator=">=", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-3.5.2: 无障碍出入口宽度判定
    Clause(
        clause_id="GB50763-3.5.2",
        standard="GB 50763-2012",
        title="无障碍出入口宽度判定",
        text="出入口净宽不应小于0.90m",
        level="L1",
        func_id="ACCESS-003",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.9, unit="m", operator=">=", building_types={"civil": 0.9, "industrial": 0.9}
        ),
    ),
    # GB50016-3.6.1: 无障碍通道宽度判定
    Clause(
        clause_id="GB50763-3.6.1",
        standard="GB 50763-2012",
        title="无障碍通道宽度判定",
        text="通道净宽不应小于1.20m",
        level="L1",
        func_id="ACCESS-004",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator=">=", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-3.8.1: 扶手设置判定
    Clause(
        clause_id="GB50763-3.8.1",
        standard="GB 50763-2012",
        title="扶手设置判定",
        text="坡道/台阶两侧应设扶手",
        level="L1",
        func_id="ACCESS-005",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.7.1: 无障碍电梯判定
    Clause(
        clause_id="GB50763-3.7.1",
        standard="GB 50763-2012",
        title="无障碍电梯判定",
        text="二层及以上应设无障碍电梯",
        level="L1",
        func_id="ACCESS-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.11.2: 无障碍停车位判定
    Clause(
        clause_id="GB50763-3.11.2",
        standard="GB 50763-2012",
        title="无障碍停车位判定",
        text="应设不少于总车位2%的无障碍车位",
        level="L1",
        func_id="ACCESS-007",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02,
            unit="比例",
            operator=">=",
            building_types={"civil": 0.02, "industrial": 0.02},
        ),
    ),
    # GB50016-3.9.1: 无障碍卫生间判定
    Clause(
        clause_id="GB50763-3.9.1",
        standard="GB 50763-2012",
        title="无障碍卫生间判定",
        text="应设无障碍卫生间",
        level="L1",
        func_id="ACCESS-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.8.2: 轮椅回转空间判定
    Clause(
        clause_id="GB50763-3.8.2",
        standard="GB 50763-2012",
        title="轮椅回转空间判定",
        text="轮椅回转直径不应小于1.50m",
        level="L1",
        func_id="ACCESS-009",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.5, unit="m", operator=">=", building_types={"civil": 1.5, "industrial": 1.5}
        ),
    ),
    # GB50016-3.2.1: 盲道设置判定
    Clause(
        clause_id="GB50763-3.2.1",
        standard="GB 50763-2012",
        title="盲道设置判定",
        text="主要流线应设盲道",
        level="L1",
        func_id="ACCESS-010",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="有", operator="==", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-3.7.2: 无障碍电梯门洞宽度判定
    Clause(
        clause_id="GB50763-3.7.2",
        standard="GB 50763-2012",
        title="无障碍电梯门洞宽度判定",
        text="无障碍电梯门洞净宽度不应小于0.90m（GB50763-3.7.2）",
        level="L1",
        func_id="DIM-049",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.9, unit="m", operator="ge", building_types={"civil": 0.9, "industrial": 0.9}
        ),
    ),
    # GB50016-3.11.1: 无障碍停车位数量判定
    Clause(
        clause_id="GB50763-3.11.1",
        standard="GB 50763-2012",
        title="无障碍停车位数量判定",
        text="应设不少于总停车位数2%的无障碍停车位（GB50763-3.11.1）",
        level="L1",
        func_id="COUNT-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02,
            unit="比例",
            operator="ge",
            building_types={"civil": 0.02, "industrial": 0.02},
        ),
    ),
    # GB50016-3.6.2: 无障碍楼梯扶手判定
    Clause(
        clause_id="GB50763-3.6.2",
        standard="GB 50763-2012",
        title="无障碍楼梯扶手判定",
        text="无障碍楼梯两侧应设扶手（GB50763-3.6.2）",
        level="L1",
        func_id="EXIST-028",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-3.16.1: 无障碍标识判定
    Clause(
        clause_id="GB50763-3.16.1",
        standard="GB 50763-2012",
        title="无障碍标识判定",
        text="无障碍设施处应设无障碍标识（GB50763-3.16.1）",
        level="L1",
        func_id="EXIST-029",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1, unit="有/无", operator="eq", building_types={"civil": 1, "industrial": 1}
        ),
    ),
    # GB50016-3.9.2: 无障碍卫生间距离判定
    Clause(
        clause_id="GB50763-3.9.2",
        standard="GB 50763-2012",
        title="无障碍卫生间距离判定",
        text="无障碍卫生间距最近无障碍出入口距离不应大于30m（GB50763-3.9.2）",
        level="L1",
        func_id="DIST-014",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30.0, unit="m", operator="le", building_types={"civil": 30.0, "industrial": 30.0}
        ),
    ),
    # GB50016-3.13.1: 无障碍住房面积判定
    Clause(
        clause_id="GB50763-3.13.1",
        standard="GB 50763-2012",
        title="无障碍住房面积判定",
        text="无障碍住房套内使用面积不应小于35.0sqm（GB50763-3.13.1）",
        level="L1",
        func_id="AREA-006",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=35.0,
            unit="sqm",
            operator="ge",
            building_types={"civil": 35.0, "industrial": 35.0},
        ),
    ),
    # GB50016-3.13.2: 无障碍住房卧室面积
    Clause(
        clause_id="GB50763-3.13.2",
        standard="GB 50763-2012",
        title="无障碍住房卧室面积",
        text="无障碍住房卧室面积不应小于9㎡（GB50763-3.13.2）",
        level="L1",
        func_id="AREA-008",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=9.0, unit="m²", operator="ge", building_types={"civil": 9.0, "industrial": 9.0}
        ),
    ),
    # GB50016-3.7.2: 无障碍电梯轿厢深度
    Clause(
        clause_id="GB50763-3.7.2-2",
        standard="GB 50763-2012",
        title="无障碍电梯轿厢深度",
        text="无障碍电梯轿厢深度不应小于1.5m（GB50763-3.7.2）",
        level="L1",
        func_id="EXIST-035",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-3.9.6: 无障碍卫生间紧急呼叫按钮
    Clause(
        clause_id="GB50763-3.9.6",
        standard="GB 50763-2012",
        title="无障碍卫生间紧急呼叫按钮",
        text="无障碍卫生间应设紧急呼叫按钮（GB50763-3.9.6）",
        level="L1",
        func_id="EXIST-036",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-3.2.3: 盲道与障碍物距离判定
    Clause(
        clause_id="GB50763-3.2.3",
        standard="GB 50763-2012",
        title="盲道与障碍物距离判定",
        text="盲道与障碍物距离不应小于0.25m（GB50763-3.2.3）",
        level="L1",
        func_id="ACCESS-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.25, unit="m", operator="ge", building_types={"civil": 0.25, "industrial": 0.25}
        ),
    ),
    # GB50016-3.3.4: 无障碍坡道休息平台深度判定
    Clause(
        clause_id="GB50763-3.3.4",
        standard="GB 50763-2012",
        title="无障碍坡道休息平台深度判定",
        text="无障碍坡道休息平台深度不应小于1.50m（GB50763-3.3.4）",
        level="L1",
        func_id="ACCESS-013",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.5, unit="m", operator="ge", building_types={"civil": 1.5, "industrial": 1.5}
        ),
    ),
    # GB50016-3.6.3: 无障碍楼梯踏步宽度判定
    Clause(
        clause_id="GB50763-3.6.3",
        standard="GB 50763-2012",
        title="无障碍楼梯踏步宽度判定",
        text="无障碍楼梯踏步宽度不应小于0.28m（GB50763-3.6.3）",
        level="L1",
        func_id="ACCESS-014",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.28, unit="m", operator="ge", building_types={"civil": 0.28, "industrial": 0.28}
        ),
    ),
    # GB50016-7.6.1: 无障碍客房数量判定
    Clause(
        clause_id="GB50763-7.6.1",
        standard="GB 50763-2012",
        title="无障碍客房数量判定",
        text="设有客房的旅馆应设不少于总客房数2%的无障碍客房（GB50763-7.6.1）",
        level="L1",
        func_id="ACCESS-016",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.02, unit="%", operator="ge", building_types={"civil": 0.02, "industrial": 0.02}
        ),
    ),
    # GB50016-7.7.1: 无障碍观众席数量判定
    Clause(
        clause_id="GB50763-7.7.1",
        standard="GB 50763-2012",
        title="无障碍观众席数量判定",
        text="设有座位的公共场所应设不少于总座位数0.2%的无障碍观众席（GB50763-7.7.1）",
        level="L1",
        func_id="ACCESS-017",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.002,
            unit="%",
            operator="ge",
            building_types={"civil": 0.002, "industrial": 0.002},
        ),
    ),
    # GB50016-3.1.2: 缘石坡道宽度判定
    Clause(
        clause_id="GB50763-3.1.2",
        standard="GB 50763-2012",
        title="缘石坡道宽度判定",
        text="缘石坡道宽度不应小于1.20m（GB50763-3.1.2）",
        level="L1",
        func_id="ACCESS-018",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.2, unit="m", operator="ge", building_types={"civil": 1.2, "industrial": 1.2}
        ),
    ),
    # GB50016-3.6.4: 无障碍扶手高度判定
    Clause(
        clause_id="GB50763-3.6.4",
        standard="GB 50763-2012",
        title="无障碍扶手高度判定",
        text="无障碍楼梯扶手高度不应小于0.85m，无障碍坡道扶手高度不应小于0.85m（GB50763-3.6.4）",
        level="L1",
        func_id="ACCESS-019",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.85, unit="m", operator="ge", building_types={"civil": 0.85, "industrial": 0.85}
        ),
    ),
    # GB50016-3.9.3: 无障碍厕所洗手盆深度判定
    Clause(
        clause_id="GB50763-3.9.3",
        standard="GB 50763-2012",
        title="无障碍厕所洗手盆深度判定",
        text="无障碍厕所洗手盆中心距侧墙不应小于0.55m（GB50763-3.9.3）",
        level="L1",
        func_id="ACCESS-020",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.55, unit="m", operator="ge", building_types={"civil": 0.55, "industrial": 0.55}
        ),
    ),
    # GB50016-3.8.3: 无障碍通道门宽度判定
    Clause(
        clause_id="GB50763-3.8.3",
        standard="GB 50763-2012",
        title="无障碍通道门宽度判定",
        text="无障碍通道上的门净宽不应小于0.80m（GB50763-3.8.3）",
        level="L1",
        func_id="DIM-092",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0.8, unit="m", operator=">=", building_types={"civil": 0.8, "industrial": 0.8}
        ),
    ),
    # GB50016-3.12.1: 无障碍厕所求助按钮判定
    Clause(
        clause_id="GB50763-3.12.1",
        standard="GB 50763-2012",
        title="无障碍厕所求助按钮判定",
        text="无障碍厕所应设求助呼叫按钮（GB50763-3.12.1）",
        level="L1",
        func_id="EXIST-066",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
]


GB50067_CLAUSES = [
    # 自动生成的规范条款（匹配现有原子函数）
    # GB50016-6.0.10: 汽车疏散坡道宽度判定
    Clause(
        clause_id="GB50067-6.0.10",
        standard="GB 50067-2014",
        title="汽车疏散坡道宽度判定",
        text="汽车疏散坡道宽度不应小于4.0m，双车道不应小于7.0m（GB50067-6.0.10）",
        level="L1",
        func_id="DIM-065",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4.0, unit="m", operator="ge", building_types={"civil": 4.0, "industrial": 4.0}
        ),
    ),
    # GB50016-4.1.5: 停车位宽度判定
    Clause(
        clause_id="GB50067-4.1.5",
        standard="GB 50067-2014",
        title="停车位宽度判定",
        text="平行停车位宽度不应小于2.4m，垂直停车位宽度不应小于2.5m（GB50067-4.1.5）",
        level="L1",
        func_id="DIM-066",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2.4, unit="m", operator="ge", building_types={"civil": 2.4, "industrial": 2.4}
        ),
    ),
    # GB50016-4.1.6: 汽车通道宽度判定
    Clause(
        clause_id="GB50067-4.1.6",
        standard="GB 50067-2014",
        title="汽车通道宽度判定",
        text="汽车库内汽车通道宽度不应小于5.5m（GB50067-4.1.6）",
        level="L1",
        func_id="DIM-068",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=5.5, unit="m", operator="ge", building_types={"civil": 5.5, "industrial": 5.5}
        ),
    ),
    # GB50016-5.1.1: 汽车库防火分区面积判定
    Clause(
        clause_id="GB50067-5.1.1",
        standard="GB 50067-2014",
        title="汽车库防火分区面积判定",
        text="地下汽车库防火分区最大允许面积不应大于2000㎡（GB50067-5.1.1）",
        level="L1",
        func_id="DIM-069",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2000.0,
            unit="㎡",
            operator="le",
            building_types={"civil": 2000.0, "industrial": 2000.0},
        ),
    ),
    # GB50016-6.0.3: 汽车库疏散楼梯宽度判定
    Clause(
        clause_id="GB50067-6.0.3",
        standard="GB 50067-2014",
        title="汽车库疏散楼梯宽度判定",
        text="汽车库内疏散楼梯净宽度不应小于1.1m（GB50067-6.0.3）",
        level="L1",
        func_id="DIM-071",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.1, unit="m", operator="ge", building_types={"civil": 1.1, "industrial": 1.1}
        ),
    ),
    # GB50016-6.0.5: 汽车库疏散距离判定
    Clause(
        clause_id="GB50067-6.0.5",
        standard="GB 50067-2014",
        title="汽车库疏散距离判定",
        text="汽车库内最远点到疏散出口距离不应大于45m（GB50067-6.0.5）",
        level="L1",
        func_id="DIST-020",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=45.0, unit="m", operator="le", building_types={"civil": 45.0, "industrial": 45.0}
        ),
    ),
    # GB50016-4.2.1: 汽车库与相邻建筑防火间距判定
    Clause(
        clause_id="GB50067-4.2.1",
        standard="GB 50067-2014",
        title="汽车库与相邻建筑防火间距判定",
        text="汽车库与相邻建筑的防火间距不应小于10m（GB50067-4.2.1）",
        level="L1",
        func_id="DIST-021",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=10.0, unit="m", operator="ge", building_types={"civil": 10.0, "industrial": 10.0}
        ),
    ),
    # GB50016-7.1.1: 汽车库消防给水判定
    Clause(
        clause_id="GB50067-7.1.1",
        standard="GB 50067-2014",
        title="汽车库消防给水判定",
        text="汽车库应设置消防给水系统（GB50067-7.1.1）",
        level="L1",
        func_id="EXIST-046",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-7.2.1: 汽车库自动喷水灭火系统判定
    Clause(
        clause_id="GB50067-7.2.1",
        standard="GB 50067-2014",
        title="汽车库自动喷水灭火系统判定",
        text="地下汽车库应设置自动喷水灭火系统（GB50067-7.2.1）",
        level="L1",
        func_id="EXIST-047",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-9.0.7: 汽车库火灾报警系统判定
    Clause(
        clause_id="GB50067-9.0.7",
        standard="GB 50067-2014",
        title="汽车库火灾报警系统判定",
        text="一、二类汽车库应设置火灾自动报警系统（GB50067-9.0.7）",
        level="L1",
        func_id="EXIST-048",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-8.2.1: 汽车库排烟设施判定
    Clause(
        clause_id="GB50067-8.2.1",
        standard="GB 50067-2014",
        title="汽车库排烟设施判定",
        text="地下汽车库应设置排烟设施（GB50067-8.2.1）",
        level="L1",
        func_id="EXIST-049",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=1.0, unit="", operator="eq", building_types={"civil": 1.0, "industrial": 1.0}
        ),
    ),
    # GB50016-6.0.2: 汽车库疏散出口数量判定
    Clause(
        clause_id="GB50067-6.0.2",
        standard="GB 50067-2014",
        title="汽车库疏散出口数量判定",
        text="汽车库每个防火分区安全出口不应少于2个（GB50067-6.0.2）",
        level="L1",
        func_id="COUNT-013",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=2, unit="个", operator="ge", building_types={"civil": 2, "industrial": 2}
        ),
    ),
    # GB50016-5.1.2: 汽车库防火卷帘判定
    Clause(
        clause_id="GB50067-5.1.2",
        standard="GB 50067-2014",
        title="汽车库防火卷帘判定",
        text="汽车库防火分区间的防火卷帘耐火极限不应低于3.00h（GB50067-5.1.2）",
        level="L1",
        func_id="EXIST-063",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-5.1.4: 汽车库自动灭火分区面积判定
    Clause(
        clause_id="GB50067-5.1.4",
        standard="GB 50067-2014",
        title="汽车库自动灭火分区面积判定",
        text="设有自动灭火系统时，汽车库防火分区面积可增加1倍（GB50067-5.1.4）",
        level="L1",
        func_id="DIM-091",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=4000.0,
            unit="㎡",
            operator="<=",
            building_types={"civil": 4000.0, "industrial": 4000.0},
        ),
    ),
    # GB50016-6.0.6: 汽车库封闭楼梯间判定
    Clause(
        clause_id="GB50067-6.0.6",
        standard="GB 50067-2014",
        title="汽车库封闭楼梯间判定",
        text="汽车库疏散楼梯应设封闭楼梯间（GB50067-6.0.6）",
        level="L1",
        func_id="EXIST-064",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=0, unit="", operator="exist", building_types={"civil": 0, "industrial": 0}
        ),
    ),
    # GB50016-8.2.2: 汽车库排烟量判定
    Clause(
        clause_id="GB50067-8.2.2",
        standard="GB 50067-2014",
        title="汽车库排烟量判定",
        text="汽车库排烟量不应小于30000m³/h（GB50067-8.2.2）",
        level="L1",
        func_id="AREA-012",
        category="fire_safety",
        params={"threshold": 1.0},
        threshold=Threshold(
            value=30000.0,
            unit="m³/h",
            operator=">=",
            building_types={"civil": 30000.0, "industrial": 30000.0},
        ),
    ),
]


class SpecRepository:  # class definition
    """规范 JSON 知识库（多标准支持）

    支持 GB 50016（中国建筑防火规范）、NFPA 101（生命安全规范）、
    NFPA 5000（建筑规范）等多套标准。
    规范通过 (standard, clause_id) 唯一标识。
    """

    def __init__(self):  # function: def __init__(self):
        """初始化规范知识库，加载 GB 50016 和 NFPA 规范条款"""
        self._clauses: Dict[str, Clause] = {}  # key: "{standard}:{clause_id}"
        # 遍历处理
        for clause in INITIAL_CLAUSES:  # 循环
            key = f"{clause.standard}:{clause.clause_id}"  # assignment
            self._clauses[key] = clause  # assignment
        # 加载 NFPA 规范
        for clause in NFPA_CLAUSES:  # loop: iterate
            key = f"{clause.standard}:{clause.clause_id}"  # assignment
            self._clauses[key] = clause  # assignment
        # 加载扩展规范：GB50016 补充条款、GB50974、GB50763、GB50067
        for clause_list in [GB50016_CLAUSES, GB50974_CLAUSES, GB50763_CLAUSES, GB50067_CLAUSES]:
            for clause in clause_list:  # loop: iterate
                key = f"{clause.standard}:{clause.clause_id}"  # assignment
                self._clauses[key] = clause  # assignment

    def get(
        self, clause_id: str, standard: str = "GB 50016-2014"
    ) -> Optional[Clause]:  # function: def get(self, clause_id: str, standard: str = "GB 50016-2014
        """按 (clause_id, standard) 查询规范条款

        Args:
            clause_id: 规范条款 ID，如 "GB50016-5.5.18"
            standard: 标准名称，默认为 GB 50016-2014
        """
        return self._clauses.get(f"{standard}:{clause_id}")  # return: self

    def get_by_func(
        self, func_id: str, standard: str = None
    ) -> List[Clause]:  # function: def get_by_func(self, func_id: str, standard: str = None) ->
        """通过原子函数 ID 查询所有关联的规范条款

        一条规范可能对应多个原子函数（如 EXIST-002 同时用于
        管道井封堵和设备井防火隔墙两个条款）。
        """
        clauses = list(self._clauses.values())  # function call
        if standard:  # check: AND condition
            clauses = [c for c in clauses if c.standard == standard]  # equality check
        return [c for c in clauses if c.func_id == func_id]  # return: list

    def list_all(
        self, standard: str = None
    ) -> List[Clause]:  # function: def list_all(self, standard: str = None) -> List[Clause]:
        """列出所有规范条款，可选按标准过滤

        Args:
            standard: 标准名称，为 None 时返回全部标准
        """
        if standard:  # check: AND condition
            return [c for c in self._clauses.values() if c.standard == standard]  # return: list
        return list(self._clauses.values())  # return

    def list_by_level(
        self, level: str, standard: str = None
    ) -> List[Clause]:  # function: def list_by_level(self, level: str, standard: str = None) ->
        """按规范等级（L1/L2/L3）过滤条款

        L1：强制性条文，必须遵守
        L2：推荐性条文，一般应遵守
        L3：补充条文，视情况执行
        """
        clauses = self.list_all(standard)  # check all true
        return [c for c in clauses if c.level == level]  # return: list

    def list_by_category(
        self, category: str, standard: str = None
    ) -> List[Clause]:  # function: def list_by_category(self, category: str, standard: str = No
        """按规范类别过滤条款

        类别包括：fire_safety（防火）、evacuation（疏散）、
        structure（结构）、lighting（照明）、hvac（暖通）。
        """
        clauses = self.list_all(standard)  # check all true
        return [c for c in clauses if c.category == category]  # return: list

    def get_threshold(
        self, clause_id: str, building_type: str = "civil", standard: str = "GB 50016-2014"
    ) -> Tuple[
        float, str, str
    ]:  # function: def get_threshold(self, clause_id: str, building_type: str =
        """获取指定建筑类型和标准的阈值
        返回: (value, unit, operator)
        """
        clause = self.get(clause_id, standard)  # function call
        # 条件分支：if not clause
        if not clause:  # check: negated condition
            # 尝试 GB 标准兜底
            clause = self.get(clause_id, "GB 50016-2014")  # function call
        if not clause:  # check: negated condition
            # 找不到时返回默认值（不抛异常，让原子函数自身判定）
            return 0.0, "", ">="  # return

        params = clause.params  # assignment
        value = float(params["threshold"])  # function call
        unit = params.get("unit", "")  # function call
        operator = params.get("operator", ">=")  # function call

        # 如果有 building_type 维度的阈值，覆盖
        if clause.threshold and clause.threshold.building_types:  # check: AND condition
            bt = (
                building_type if building_type in clause.threshold.building_types else "civil"
            )  # assignment
            value = clause.threshold.building_types.get(bt, value)  # function call

        return value, unit, operator  # return

    def to_json(self) -> str:  # function: def to_json(self) -> str:
        """序列化为 JSON"""
        data = []  # assignment
        # 遍历处理
        for c in self._clauses.values():  # 循环
            entry = {  # assignment
                "clause_id": c.clause_id,  # 字段
                "standard": c.standard,  # 字段
                "title": c.title,  # 字段
                "text": c.text,  # 字段
                "level": c.level,  # 字段
                "func_id": c.func_id,  # 字段
                "category": c.category,  # 字段
                "params": c.params,  # 字段
            }  # code
            # 条件分支：if c.threshold and c.threshold.building_types
            if c.threshold and c.threshold.building_types:  # check: AND condition
                entry["building_type_thresholds"] = c.threshold.building_types  # 操作
            data.append(entry)  # append to list
        return json.dumps(data, ensure_ascii=False, indent=2)  # return

    def save_json(self, file_path: str):  # function: def save_json(self, file_path: str):
        """保存为 JSON 文件"""
        # 上下文管理器
        with open(file_path, "w", encoding="utf-8") as f:  # 上下文
            f.write(self.to_json())  # function call

    def set_threshold(
        self, clause_id: str, building_type: str, value: float, standard: str = "GB 50016-2014"
    ):  # function: def set_threshold(self, clause_id: str, building_type: str,
        """设置指定建筑类型的阈值（用于反馈闭环微调）"""
        clause = self.get(clause_id, standard)  # function call
        # 条件分支：if not clause
        if not clause:  # check: negated condition
            raise ValueError(f"规范 {standard}:{clause_id} 不存在")  # 抛出

        # 条件分支：if not clause.threshold
        if not clause.threshold:  # check: negated condition
            clause.threshold = Threshold()  # function call
        # 条件分支：if not clause.threshold.building_types
        if not clause.threshold.building_types:  # check: negated condition
            clause.threshold.building_types = {}  # assignment
        clause.threshold.building_types[building_type] = value  # 操作

    def list_standards(self) -> List[str]:  # function: def list_standards(self) -> List[str]:
        """获取支持的标准列表"""
        return sorted(set(c.standard for c in self._clauses.values()))  # return: sorted list

    @property  # code
    def count(self) -> int:  # function: def count(self) -> int:
        """获取当前加载的规范条款总数"""
        return len(self._clauses)  # return: count
