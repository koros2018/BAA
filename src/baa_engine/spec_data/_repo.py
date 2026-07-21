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


from .gb50016_core import INITIAL_CLAUSES  # type: ignore[attr-defined]
from .gb50016_extra import GB50016_CLAUSES  # type: ignore[attr-defined]
from .gb50974 import GB50974_CLAUSES  # type: ignore[attr-defined]
from .gb50763 import GB50763_CLAUSES  # type: ignore[attr-defined]
from .gb50067 import GB50067_CLAUSES  # type: ignore[attr-defined]
from .nfpa import NFPA_CLAUSES  # type: ignore[attr-defined]


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
