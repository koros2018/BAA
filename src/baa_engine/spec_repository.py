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
    params: Dict = field(default_factory=dict)  # 赋值
    threshold: Optional[Threshold] = None  # 可选：带建筑类型区分的阈值


# ── 规范 JSON 库 ─────────────────────────────────────────

# 首批 10 条 L1 + 10 条 L2 级规范
INITIAL_CLAUSES = [  # 赋值
    # =============================================
    # L1 规范（10条）
    # =============================================
    Clause(  # 调用
        clause_id="GB50016-5.5.18",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="疏散楼梯净宽",  # 赋值
        text="高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。",  # 赋值
        level="L1",  # 赋值
        func_id="DIM-001",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "staircase", "property": "clear_width",  # 赋值
                "operator": ">=", "threshold": 1.2, "unit": "m"},  # 字段
        threshold=Threshold(value=1.2, unit="m", operator=">=",  # 赋值
                            building_types={"civil": 1.2, "industrial": 1.1})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.1.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="防火分区面积",  # 赋值
        text="每个防火分区的最大允许建筑面积不应大于2500㎡（民用）/ 4000㎡（工业，一二级单层）。",  # 赋值
        level="L1",  # 赋值
        func_id="DIM-002",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_zone", "property": "area",  # 赋值
                "operator": "<=", "threshold": 2500, "unit": "㎡"},  # 字段
        threshold=Threshold(value=2500, unit="㎡", operator="<=",  # 赋值
                            building_types={"civil": 2500, "industrial": 4000})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-7.1.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防车道宽度",  # 赋值
        text="消防车道的净宽度和净高度均不应小于4.0m。",  # 赋值
        level="L1",  # 赋值
        func_id="DIM-003",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_lane", "property": "width",  # 赋值
                "operator": ">=", "threshold": 4.0, "unit": "m"},  # 字段
        # 消防车道宽度工业/民用无差异，但厂房占地面积>3000㎡时需环形消防车道
        threshold=Threshold(value=4.0, unit="m", operator=">=",  # 赋值
                            building_types={"civil": 4.0, "industrial": 4.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.17",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="疏散距离",  # 赋值
        text="房间内任一点至最近安全出口的直线距离不应大于30m（民用）/ 40m（工业）。",  # 赋值
        level="L1",  # 赋值
        func_id="DIST-001",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "room", "property": "travel_distance",  # 赋值
                "operator": "<=", "threshold": 30.0, "unit": "m"},  # 字段
        threshold=Threshold(value=30.0, unit="m", operator="<=",  # 赋值
                            building_types={"civil": 30.0, "industrial": 40.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.8",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="安全出口数量",  # 赋值
        text="每个防火分区或一个防火分区的每个楼层，其安全出口不应少于2个。",  # 赋值
        level="L1",  # 赋值
        func_id="COUNT-001",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "floor", "property": "exit_count",  # 赋值
                "operator": ">=", "threshold": 2.0, "unit": "个"},  # 字段
        # 工业厂房每个防火分区也要求≥2个安全出口（GB50016 3.7.2）
        threshold=Threshold(value=2.0, unit="个", operator=">=",  # 赋值
                            building_types={"civil": 2.0, "industrial": 2.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.5.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="防火门等级",  # 赋值
        text="防火门的耐火等级应符合设计要求，甲级防火门耐火极限不低于1.5h。",  # 赋值
        level="L1",  # 赋值
        func_id="ATTR-001",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_door", "property": "fire_rating",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "级"},  # 字段
        # 工业/民用防火门等级要求一致（按GB50016 6.5.1/3.2.9）
        threshold=Threshold(value=1.0, unit="级", operator=">=",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.18-2",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="疏散走道宽度",  # 赋值
        text="疏散走道的净宽度不应小于1.1m（民用）/ 1.0m（工业）。",  # 赋值
        level="L1",  # 赋值
        func_id="DIM-004",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "corridor", "property": "clear_width",  # 赋值
                "operator": ">=", "threshold": 1.1, "unit": "m"},  # 字段
        threshold=Threshold(value=1.1, unit="m", operator=">=",  # 赋值
                            building_types={"civil": 1.1, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-7.4.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="避难层面积",  # 赋值
        text="避难层（间）的净面积应按不小于5人/㎡计算。",  # 赋值
        level="L1",  # 赋值
        func_id="AREA-001",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "refuge_floor", "property": "area_per_person",  # 赋值
                "operator": ">=", "threshold": 5.0, "unit": "㎡/人"},  # 字段
        # 避难层仅用于民用高层建筑，工业建筑通常无此要求
        threshold=Threshold(value=5.0, unit="㎡/人", operator=">=",  # 赋值
                            building_types={"civil": 5.0, "industrial": 0.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.12",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="楼梯间设置",  # 赋值
        text="一类高层公共建筑应设置防烟楼梯间。",  # 赋值
        level="L1",  # 赋值
        func_id="EXIST-001",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "staircase", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需疏散楼梯（GB50016 3.7.6），高层厂房设封闭楼梯间
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-7.2.4",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防窗面积",  # 赋值
        text="消防救援窗的净面积不应小于1.0㎡。",  # 赋值
        level="L1",  # 赋值
        func_id="DIM-005",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_window", "property": "net_area",  # 赋值
                "operator": ">=", "threshold": 1.0, "unit": "㎡"},  # 字段
        # 工业厂房也需设置消防救援窗（GB50016 7.2.4），要求一致
        threshold=Threshold(value=1.0, unit="㎡", operator=">=",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合

    # =============================================
    # L2 规范（10条）
    # =============================================
    Clause(  # 调用
        clause_id="GB50016-5.5.19",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="人员密集场所疏散门净宽",  # 赋值
        text="人员密集场所的疏散门，其净宽度不应小于1.4m。",  # 赋值
        level="L2",  # 赋值
        func_id="DIM-006",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "exit_door", "property": "clear_width",  # 赋值
                "operator": ">=", "threshold": 1.4, "unit": "m"},  # 字段
        # 工业厂房疏散门也需≥1.2m（GB50016 3.7.5），人员密集时≥1.4m
        threshold=Threshold(value=1.4, unit="m", operator=">=",  # 赋值
                            building_types={"civil": 1.4, "industrial": 1.2})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.6.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="管道井封堵",  # 赋值
        text="电缆井、管道井应在每层楼板处用不低于楼板耐火极限的不燃材料封堵。",  # 赋值
        level="L2",  # 赋值
        func_id="EXIST-002",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "shaft", "property": "sealed",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房管道井封堵要求一致
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.5.3",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="防火卷帘宽度",  # 赋值
        text="除中庭外，防火分隔部位的防火卷帘宽度不应大于10m。",  # 赋值
        level="L2",  # 赋值
        func_id="DIM-007",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_curtain", "property": "width",  # 赋值
                "operator": "<=", "threshold": 10.0, "unit": "m"},  # 字段
        # 工业厂房防火卷帘要求一致（GB50016 6.5.3适用于所有建筑类型）
        threshold=Threshold(value=10.0, unit="m", operator="<=",  # 赋值
                            building_types={"civil": 10.0, "industrial": 10.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.24",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="高层住宅剪刀楼梯",  # 赋值
        text="高层住宅建筑的疏散楼梯，当采用剪刀楼梯时，梯段间应设置防火隔墙。",  # 赋值
        level="L2",  # 赋值
        func_id="EXIST-003",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "scissor_staircase", "property": "fire_wall_exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 剪刀楼梯仅用于民用住宅，工业厂房不适用
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 0.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-10.1.5",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防应急照明",  # 赋值
        text="建筑内疏散照明的地面最低水平照度不应低于1.0lx。",  # 赋值
        level="L2",  # 赋值
        func_id="LIGHT-001",  # 赋值
        category="lighting",  # 赋值
        params={"target_entity": "evacuation_lighting", "property": "illuminance",  # 赋值
                "operator": ">=", "threshold": 1.0, "unit": "lx"},  # 字段
        # 工业厂房应急照明要求一致（GB50016 10.1.5/10.3.1）
        threshold=Threshold(value=1.0, unit="lx", operator=">=",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-10.3.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="疏散指示标志",  # 赋值
        text="疏散走道和安全出口处应设置疏散指示标志。",  # 赋值
        level="L2",  # 赋值
        func_id="EXIST-004",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "exit_sign", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需设置疏散指示标志（GB50016 10.3.1）
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-8.3.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="自动灭火系统（一类高层）",  # 赋值
        text="一类高层公共建筑（除游泳池、溜冰场外）应设置自动灭火系统。",  # 赋值
        level="L2",  # 赋值
        func_id="EXIST-005",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "sprinkler_system", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需自动灭火系统（GB50016 8.3.1，高层厂房和仓库）
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-8.4.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="火灾自动报警系统",  # 赋值
        text="一类高层公共建筑应设置火灾自动报警系统。",  # 赋值
        level="L2",  # 赋值
        func_id="EXIST-006",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_alarm", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房也需火灾自动报警系统（GB50016 8.4.1，高层厂房和仓库）
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.7.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="保温材料燃烧等级",  # 赋值
        text="建筑内外保温系统应选用A级或B1级保温材料。",  # 赋值
        level="L2",  # 赋值
        func_id="ATTR-002",  # 赋值
        category="structure",  # 赋值
        params={"target_entity": "insulation", "property": "fire_rating",  # 赋值
                "operator": ">=", "threshold": 2.0, "unit": "级"},  # A=3, B1=2
        # 工业厂房保温要求更严，通常要求A级（GB50016 6.7.5/6.7.6）
        threshold=Threshold(value=2.0, unit="级", operator=">=",  # 赋值
                            building_types={"civil": 2.0, "industrial": 3.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.2.4",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="设备井防火隔墙",  # 赋值
        text="电缆井、管道井与房间、走道等相连通的孔洞，应采用防火封堵材料封堵。",  # 赋值
        level="L2",  # 赋值
        func_id="EXIST-002",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "shaft", "property": "hole_sealed",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        # 工业厂房封堵要求一致
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合

    # ===== L3 新增规范（11条，对应 RESERVED_FUNCS） =====
    Clause(  # 调用
        clause_id="GB50016-3.4.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="防火间距判定",  # 赋值
        text="厂房之间及与乙、丙、丁、戊类仓库等的防火间距不应小于表3.4.1的规定。",  # 赋值
        level="L3",  # 赋值
        func_id="DIST-002",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "building", "property": "distance",  # 赋值
                "operator": ">=", "threshold": 12.0, "unit": "m"},  # 字段
        # 工业厂房防火间距要求更严
        threshold=Threshold(value=12.0, unit="m", operator=">=",  # 赋值
                            building_types={"civil": 10.0, "industrial": 12.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-9.2.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="排烟窗面积判定",  # 赋值
        text="排烟窗净面积不应小于房间面积的2%。",  # 赋值
        level="L3",  # 赋值
        func_id="DIM-008",  # 赋值
        category="hvac",  # 赋值
        params={"target_entity": "smoke_exhaust_window", "property": "area",  # 赋值
                "operator": ">=", "threshold": 0.02, "unit": "㎡"},  # 字段
        threshold=Threshold(value=0.02, unit="㎡", operator=">=",  # 赋值
                            building_types={"civil": 0.02, "industrial": 0.02})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-7.3.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防电梯判定",  # 赋值
        text="一类高层公共建筑和建筑高度大于32m的二类高层公共建筑应设置消防电梯。",  # 赋值
        level="L3",  # 赋值
        func_id="EXIST-007",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_elevator", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-7.3.5",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防电梯前室面积判定",  # 赋值
        text="消防电梯前室的使用面积不应小于6㎡。",  # 赋值
        level="L3",  # 赋值
        func_id="AREA-002",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "elevator_lobby", "property": "area",  # 赋值
                "operator": ">=", "threshold": 6.0, "unit": "㎡"},  # 字段
        threshold=Threshold(value=6.0, unit="㎡", operator=">=",  # 赋值
                            building_types={"civil": 6.0, "industrial": 6.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.17-2",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="袋形走道长度判定",  # 赋值
        text="袋形走道长度不应大于20m。",  # 赋值
        level="L3",  # 赋值
        func_id="DIST-003",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "corridor", "property": "length",  # 赋值
                "operator": "<=", "threshold": 20.0, "unit": "m"},  # 字段
        threshold=Threshold(value=20.0, unit="m", operator="<=",  # 赋值
                            building_types={"civil": 20.0, "industrial": 15.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-5.5.18-3",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="疏散出口宽度判定",  # 赋值
        text="疏散出口净宽度不应小于0.9m。",  # 赋值
        level="L3",  # 赋值
        func_id="DIM-009",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "exit", "property": "clear_width",  # 赋值
                "operator": ">=", "threshold": 0.9, "unit": "m"},  # 字段
        threshold=Threshold(value=0.9, unit="m", operator=">=",  # 赋值
                            building_types={"civil": 0.9, "industrial": 0.9})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-6.5.1-2",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="防火窗等级判定",  # 赋值
        text="防火窗耐火极限不应低于1.0h。",  # 赋值
        level="L3",  # 赋值
        func_id="ATTR-003",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "fire_window", "property": "fire_rating",  # 赋值
                "operator": ">=", "threshold": 1.0, "unit": "h"},  # 字段
        threshold=Threshold(value=1.0, unit="h", operator=">=",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-8.2.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防水箱判定",  # 赋值
        text="一类高层公共建筑应设置屋顶消防水箱。",  # 赋值
        level="L3",  # 赋值
        func_id="EXIST-008",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "water_tank", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-8.1.3",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防水池判定",  # 赋值
        text="市政供水不足时应设置消防水池。",  # 赋值
        level="L3",  # 赋值
        func_id="EXIST-009",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "water_reservoir", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-7.2.4-2",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="消防救援窗面积判定",  # 赋值
        text="消防救援窗口净面积不应小于1.0㎡。",  # 赋值
        level="L3",  # 赋值
        func_id="DIM-010",  # 赋值
        category="fire_safety",  # 赋值
        params={"target_entity": "rescue_window", "property": "area",  # 赋值
                "operator": ">=", "threshold": 1.0, "unit": "㎡"},  # 字段
        threshold=Threshold(value=1.0, unit="㎡", operator=">=",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
    Clause(  # 调用
        clause_id="GB50016-8.5.1",  # 赋值
        standard="GB 50016-2014",  # 赋值
        title="应急广播判定",  # 赋值
        text="一类高层公共建筑应设置应急广播系统。",  # 赋值
        level="L3",  # 赋值
        func_id="EXIST-010",  # 赋值
        category="evacuation",  # 赋值
        params={"target_entity": "emergency_broadcast", "property": "exists",  # 赋值
                "operator": "==", "threshold": 1.0, "unit": "有/无"},  # 字段
        threshold=Threshold(value=1.0, unit="有/无", operator="==",  # 赋值
                            building_types={"civil": 1.0, "industrial": 1.0})  # 赋值
    ),  # 闭合
]  # 闭合


class SpecRepository:
    """规范 JSON 知识库"""

    def __init__(self):
        self._clauses: Dict[str, Clause] = {}  # 赋值
        for clause in INITIAL_CLAUSES:  # 循环
            self._clauses[clause.clause_id] = clause  # 赋值

    def get(self, clause_id: str) -> Optional[Clause]:
        return self._clauses.get(clause_id)  # 返回

    def get_by_func(self, func_id: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.func_id == func_id]  # 返回

    def list_all(self) -> List[Clause]:
        return list(self._clauses.values())  # 返回

    def list_by_level(self, level: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.level == level]  # 返回

    def list_by_category(self, category: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.category == category]  # 返回

    def get_threshold(self, clause_id: str, building_type: str = "civil") -> Tuple[float, str, str]:
        """获取指定建筑类型的阈值
        返回: (value, unit, operator)
        """
        clause = self.get(clause_id)  # 赋值
        if not clause:  # 条件判断
            raise ValueError(f"规范 {clause_id} 不存在")  # 抛出

        params = clause.params  # 赋值
        value = float(params["threshold"])  # 赋值
        unit = params.get("unit", "")  # 赋值
        operator = params.get("operator", ">=")  # 赋值

        # 如果有 building_type 维度的阈值，覆盖
        if clause.threshold and clause.threshold.building_types:  # 条件判断
            bt = building_type if building_type in clause.threshold.building_types else "civil"  # 赋值
            value = clause.threshold.building_types.get(bt, value)  # 赋值

        return value, unit, operator  # 返回

    def to_json(self) -> str:
        """序列化为 JSON"""
        data = []  # 赋值
        for c in self._clauses.values():  # 循环
            entry = {  # 赋值
                "clause_id": c.clause_id,  # 字段
                "standard": c.standard,  # 字段
                "title": c.title,  # 字段
                "text": c.text,  # 字段
                "level": c.level,  # 字段
                "func_id": c.func_id,  # 字段
                "category": c.category,  # 字段
                "params": c.params,  # 字段
            }  # 闭合
            if c.threshold and c.threshold.building_types:  # 条件判断
                entry["building_type_thresholds"] = c.threshold.building_types  # 操作
            data.append(entry)  # 调用
        return json.dumps(data, ensure_ascii=False, indent=2)  # 返回

    def save_json(self, file_path: str):
        """保存为 JSON 文件"""
        with open(file_path, "w", encoding="utf-8") as f:  # 上下文
            f.write(self.to_json())  # 调用

    def set_threshold(self, clause_id: str, building_type: str, value: float):
        """设置指定建筑类型的阈值（用于反馈闭环微调）"""
        clause = self.get(clause_id)  # 赋值
        if not clause:  # 条件判断
            raise ValueError(f"规范 {clause_id} 不存在")  # 抛出

        if not clause.threshold:  # 条件判断
            clause.threshold = ClauseThreshold()  # 赋值
        if not clause.threshold.building_types:  # 条件判断
            clause.threshold.building_types = {}  # 赋值
        clause.threshold.building_types[building_type] = value  # 操作

    @property
    def count(self) -> int:
        return len(self._clauses)  # 返回
