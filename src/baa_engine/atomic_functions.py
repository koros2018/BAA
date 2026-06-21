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
        entity_type = entity.get("type", "")
        func_id = self.func_id

        # 根据函数类型和实体类型智能提取
        # 宽度类：优先用width/clear_width，根据实体类型自适应
        if func_id in ("DIM-001", "DIM-003", "DIM-004"):  # 宽度判定
            val = props.get("width", props.get("clear_width", 0.0))
            if val > 100:  # 100mm以上视为mm单位
                val = val / 1000
            return val

        if func_id == "DIM-002":  # 面积判定
            val = props.get("area", 0.0)
            if val >= 100:  # mm²→m²
                val = val / 1000000
            return val

        if func_id == "DIST-001":  # 距离判定
            val = props.get("travel_distance", props.get("length", 0.0))
            if val > 100:  # mm→m
                val = val / 1000
            return val

        if func_id == "COUNT-001":  # 数量判定
            return props.get("count", props.get("exit_count", 1.0))

        if func_id == "ATTR-001":  # 防火门等级
            return props.get("fire_rating", props.get("rating", 0.0))

        if func_id == "EXIST-001":  # 存在性判定
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0

        if func_id in ("DIM-005", "AREA-001"):  # 面积判定（窗/避难层）
            val = props.get("area", props.get("width", 0) * props.get("height", 0))
            if val >= 100:  # ≥100mm²即视为mm²→m²
                val = val / 1000000
            return val

        # L2 新增函数
        if func_id in ("DIM-006", "DIM-007"):  # 疏散门净宽 / 防火卷帘宽度
            val = props.get("width", props.get("clear_width", 0.0))
            if val > 100:  # mm→m
                val = val / 1000
            return val

        if func_id in ("EXIST-002", "EXIST-003", "EXIST-004", "EXIST-005", "EXIST-006"):  # 存在性判定
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0

        if func_id == "ATTR-002":  # 保温材料等级
            return props.get("fire_rating", props.get("rating", 0.0))

        if func_id == "LIGHT-001":  # 照度
            return props.get("illuminance", props.get("lux", 0.0))

        # 兜底：直接用value或0
        return props.get("value", 0.0)


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
        # L2 规范原子函数（5个）
        AtomicFunction("DIM-006", "疏散门净宽判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.19", "人员密集场所疏散门净宽不应小于1.4m", ">=", 1.4, "m"),
        AtomicFunction("DIM-007", "防火卷帘宽度判定", FuncCategory.DIMENSION,
                       "GB50016-6.5.3", "防火分隔防火卷帘宽度不应大于10m", "<=", 10.0, "m"),
        AtomicFunction("EXIST-002", "管道井封堵判定", FuncCategory.EXIST,
                       "GB50016-6.6.1", "管道井应每层用不燃材料封堵", "==", 1.0, "有/无"),
        AtomicFunction("EXIST-003", "剪刀楼梯分隔判定", FuncCategory.EXIST,
                       "GB50016-5.5.24", "剪刀楼梯梯段间应设置防火隔墙", "==", 1.0, "有/无"),
        AtomicFunction("EXIST-004", "疏散指示标志判定", FuncCategory.EXIST,
                       "GB50016-10.3.1", "疏散走道和安全出口应设疏散指示标志", "==", 1.0, "有/无"),
        AtomicFunction("EXIST-005", "自动灭火系统判定", FuncCategory.EXIST,
                       "GB50016-8.3.1", "一类高层应设置自动灭火系统", "==", 1.0, "有/无"),
        AtomicFunction("EXIST-006", "火灾报警系统判定", FuncCategory.EXIST,
                       "GB50016-8.4.1", "一类高层应设置火灾自动报警系统", "==", 1.0, "有/无"),
        AtomicFunction("ATTR-002", "保温材料等级判定", FuncCategory.ATTR,
                       "GB50016-6.7.1", "保温材料应选用A或B1级", ">=", 2.0, "级"),
        AtomicFunction("LIGHT-001", "应急照明照度判定", FuncCategory.DIMENSION,
                       "GB50016-10.1.5", "疏散照明照度不应低于1.0lx", ">=", 1.0, "lx"),
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