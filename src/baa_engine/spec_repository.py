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
    value: float
    unit: str
    operator: str      # >=, <=, ==, !=
    building_types: Optional[Dict[str, float]] = None  # {"civil": 值, "industrial": 值}


@dataclass
class Clause:
    """规范条款"""
    clause_id: str
    standard: str
    title: str
    text: str
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
                "operator": ">=", "threshold": 1.2, "unit": "m"},
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
                "operator": "<=", "threshold": 2500, "unit": "㎡"},
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
                "operator": ">=", "threshold": 4.0, "unit": "m"}
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
                "operator": "<=", "threshold": 30.0, "unit": "m"},
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
                "operator": ">=", "threshold": 2.0, "unit": "个"}
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
                "operator": "==", "threshold": 1.0, "unit": "级"}
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
                "operator": ">=", "threshold": 1.1, "unit": "m"},
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
                "operator": ">=", "threshold": 5.0, "unit": "㎡/人"}
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
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
                "operator": ">=", "threshold": 1.0, "unit": "㎡"}
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
                "operator": ">=", "threshold": 1.4, "unit": "m"}
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
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
                "operator": "<=", "threshold": 10.0, "unit": "m"}
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
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
                "operator": ">=", "threshold": 1.0, "unit": "lx"}
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
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
                "operator": ">=", "threshold": 2.0, "unit": "级"}  # A=3, B1=2
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
                "operator": "==", "threshold": 1.0, "unit": "有/无"}
    ),
]


class SpecRepository:
    """规范 JSON 知识库"""

    def __init__(self):
        self._clauses: Dict[str, Clause] = {}
        for clause in INITIAL_CLAUSES:
            self._clauses[clause.clause_id] = clause

    def get(self, clause_id: str) -> Optional[Clause]:
        return self._clauses.get(clause_id)

    def get_by_func(self, func_id: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.func_id == func_id]

    def list_all(self) -> List[Clause]:
        return list(self._clauses.values())

    def list_by_level(self, level: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.level == level]

    def list_by_category(self, category: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.category == category]

    def get_threshold(self, clause_id: str, building_type: str = "civil") -> Tuple[float, str, str]:
        """获取指定建筑类型的阈值
        返回: (value, unit, operator)
        """
        clause = self.get(clause_id)
        if not clause:
            raise ValueError(f"规范 {clause_id} 不存在")

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
        for c in self._clauses.values():
            entry = {
                "clause_id": c.clause_id,
                "standard": c.standard,
                "title": c.title,
                "text": c.text,
                "level": c.level,
                "func_id": c.func_id,
                "category": c.category,
                "params": c.params,
            }
            if c.threshold and c.threshold.building_types:
                entry["building_type_thresholds"] = c.threshold.building_types
            data.append(entry)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def save_json(self, file_path: str):
        """保存为 JSON 文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @property
    def count(self) -> int:
        return len(self._clauses)