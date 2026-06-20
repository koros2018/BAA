"""
BAA 规范JSON知识库
首批 10 条 L1 级规范（GB50016 建筑防火规范）
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import json


@dataclass
class Clause:
    """规范条款"""
    clause_id: str
    standard: str
    title: str
    text: str
    level: str            # L1 / L2 / L3
    func_id: str          # 对应原子函数 ID
    category: str         # fire_safety / evacuation / structure
    params: Dict = field(default_factory=dict)


# ── 规范 JSON 库 ─────────────────────────────────────────

class SpecRepository:
    """规范 JSON 知识库"""

    # 首批 10 条 L1 级规范（GB50016-2014）
    INITIAL_CLAUSES = [
        Clause(
            clause_id="GB50016-5.5.18",
            standard="GB 50016-2014",
            title="疏散楼梯净宽",
            text="高层公共建筑的疏散楼梯，其净宽度不应小于1.2m。",
            level="L1",
            func_id="DIM-001",
            category="evacuation",
            params={"target_entity": "staircase", "property": "clear_width",
                    "operator": ">=", "threshold": 1.2, "unit": "m"}
        ),
        Clause(
            clause_id="GB50016-6.1.1",
            standard="GB 50016-2014",
            title="防火分区面积",
            text="每个防火分区的最大允许建筑面积不应大于2500㎡。",
            level="L1",
            func_id="DIM-002",
            category="fire_safety",
            params={"target_entity": "fire_zone", "property": "area",
                    "operator": "<=", "threshold": 2500, "unit": "㎡"}
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
            text="房间内任一点至最近安全出口的直线距离不应大于30m。",
            level="L1",
            func_id="DIST-001",
            category="evacuation",
            params={"target_entity": "room", "property": "travel_distance",
                    "operator": "<=", "threshold": 30.0, "unit": "m"}
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
            text="疏散走道的净宽度不应小于1.1m。",
            level="L1",
            func_id="DIM-004",
            category="evacuation",
            params={"target_entity": "corridor", "property": "clear_width",
                    "operator": ">=", "threshold": 1.1, "unit": "m"}
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
    ]

    def __init__(self):
        self._clauses: Dict[str, Clause] = {}
        for clause in self.INITIAL_CLAUSES:
            self._clauses[clause.clause_id] = clause

    def get(self, clause_id: str) -> Optional[Clause]:
        return self._clauses.get(clause_id)

    def get_by_func(self, func_id: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.func_id == func_id]

    def list_all(self) -> List[Clause]:
        return list(self._clauses.values())

    def list_by_level(self, level: str) -> List[Clause]:
        return [c for c in self._clauses.values() if c.level == level]

    def to_json(self) -> str:
        """序列化为 JSON"""
        data = []
        for c in self._clauses.values():
            data.append({
                "clause_id": c.clause_id,
                "standard": c.standard,
                "title": c.title,
                "text": c.text,
                "level": c.level,
                "func_id": c.func_id,
                "category": c.category,
                "params": c.params,
            })
        return json.dumps(data, ensure_ascii=False, indent=2)

    def save_json(self, file_path: str):
        """保存为 JSON 文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @property
    def count(self) -> int:
        return len(self._clauses)