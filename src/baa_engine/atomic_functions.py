"""
BAA 原子函数库 - 规范判定核心
框架预留 30 个位置，首批实现 10 个
"""
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field


# ── 类型定义 ──────────────────────────────────────────────

class FuncCategory(Enum):
    """原子函数分类"""
    DIMENSION = "dim"     # 尺寸/距离判定
    COUNT = "count"       # 数量判定
    DISTANCE = "dist"     # 距离判定
    ATTR = "attr"         # 属性判定
    EXIST = "exist"       # 存在性判定
    AREA = "area"         # 面积判定


class Severity(Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    PASS = "pass"


# ── 数据结构 ──────────────────────────────────────────────

@dataclass
class FuncResult:
    """原子函数判定结果"""
    func_id: str
    func_name: str
    clause_id: str           # 规范条款编号
    operator: str            # >=, <=, ==, >, <
    threshold: float
    actual: float
    result: str              # PASS / FAIL
    delta: float
    severity: Severity
    entity_id: str
    entity_type: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AtomicFunction:
    """原子函数定义"""
    func_id: str
    name: str
    category: FuncCategory
    clause_id: str
    description: str
    operator: str
    threshold: float
    unit: str

    def execute(self, entity: Dict[str, Any]) -> FuncResult:
        """执行判定"""
        actual = self._extract_value(entity)
        delta = actual - self.threshold

        # 执行比较
        if self.operator == ">=":
            passed = actual >= self.threshold
        elif self.operator == "<=":
            passed = actual <= self.threshold
        elif self.operator == "==":
            passed = abs(actual - self.threshold) < 1e-6
        elif self.operator == ">":
            passed = actual > self.threshold
        elif self.operator == "<":
            passed = actual < self.threshold
        else:
            passed = False

        # 严重等级
        if passed:
            severity = Severity.PASS
        else:
            abs_delta = abs(delta)
            if abs_delta > self.threshold * 0.3:
                severity = Severity.CRITICAL
            elif abs_delta > self.threshold * 0.1:
                severity = Severity.MAJOR
            else:
                severity = Severity.MINOR

        return FuncResult(
            func_id=self.func_id,
            func_name=self.name,
            clause_id=self.clause_id,
            operator=self.operator,
            threshold=self.threshold,
            actual=actual,
            result="PASS" if passed else "FAIL",
            delta=delta,
            severity=severity,
            entity_id=entity.get("id", ""),
            entity_type=entity.get("type", ""),
            params={"extracted_value": actual, "unit": self.unit},
        )

    def _extract_value(self, entity: Dict[str, Any]) -> float:
        """从实体中提取判定所需的值"""
        props = entity.get("properties", {})
        # 不同类型有不同的属性提取方式
        key_map = {
            "DIM-001": "clear_width",   # 疏散楼梯净宽
            "DIM-002": "area",          # 防火分区面积
            "DIM-003": "width",         # 消防车道宽度
            "DIST-001": "travel_distance", # 疏散距离
            "COUNT-001": "count",       # 安全出口数量
            "ATTR-001": "fire_rating",  # 防火门等级
            "EXIST-001": "exists",      # 楼梯间存在性
        }
        key = key_map.get(self.func_id, "value")
        return props.get(key, 0.0)


# ── 函数注册表 ────────────────────────────────────────────

class FuncRegistry:
    """原子函数注册表 - 框架30个位置"""

    # 首批 10 个原子函数（L1级，与规范JSON库对齐）
    INITIAL_FUNCS = [
        AtomicFunction("DIM-001", "疏散楼梯净宽判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.18", "疏散楼梯净宽度不应小于1.2m", ">=", 1.2, "m"),
        AtomicFunction("DIM-002", "防火分区面积判定", FuncCategory.DIMENSION,
                       "GB50016-6.1.1", "防火分区面积不应大于2500㎡", "<=", 2500, "㎡"),
        AtomicFunction("DIM-003", "消防车道宽度判定", FuncCategory.DIMENSION,
                       "GB50016-7.1.1", "消防车道宽度不应小于4m", ">=", 4.0, "m"),
        AtomicFunction("DIST-001", "疏散距离判定", FuncCategory.DISTANCE,
                       "GB50016-5.5.17", "疏散距离不应大于30m", "<=", 30.0, "m"),
        AtomicFunction("COUNT-001", "安全出口数量判定", FuncCategory.COUNT,
                       "GB50016-5.5.8", "安全出口不应少于2个", ">=", 2.0, "个"),
        AtomicFunction("ATTR-001", "防火门等级判定", FuncCategory.ATTR,
                       "GB50016-6.5.1", "防火门等级应为甲级", "==", 1.0, "级"),
        AtomicFunction("DIM-004", "疏散走道宽度判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.18", "疏散走道净宽度不应小于1.1m", ">=", 1.1, "m"),
        AtomicFunction("AREA-001", "避难层面积判定", FuncCategory.AREA,
                       "GB50016-7.4.1", "避难层净面积不宜小于5㎡/人", ">=", 5.0, "㎡/人"),
        AtomicFunction("EXIST-001", "楼梯间存在判定", FuncCategory.EXIST,
                       "GB50016-5.5.12", "建筑应设置楼梯间", "==", 1.0, "有/无"),
        AtomicFunction("DIM-005", "窗净面积判定", FuncCategory.DIMENSION,
                       "GB50016-7.2.4", "消防窗净面积不应小于1.0㎡", ">=", 1.0, "㎡"),
    ]

    # 框架预留 20 个位置（V2.0扩展）
    RESERVED_FUNCS = [
        # 预留位 1-20
    ]

    def __init__(self):
        self._funcs: Dict[str, AtomicFunction] = {}
        for func in self.INITIAL_FUNCS:
            self.register(func)

    def register(self, func: AtomicFunction):
        self._funcs[func.func_id] = func

    def get(self, func_id: str) -> Optional[AtomicFunction]:
        return self._funcs.get(func_id)

    def get_by_clause(self, clause_id: str) -> List[AtomicFunction]:
        return [f for f in self._funcs.values() if f.clause_id == clause_id]

    def list_all(self) -> List[AtomicFunction]:
        return list(self._funcs.values())

    @property
    def count(self) -> int:
        return len(self._funcs)

    @property
    def capacity(self) -> int:
        return 30  # 框架总容量