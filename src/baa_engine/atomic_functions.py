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
    EVAC = "evac"         # 疏散路径判定（V2新增）


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
    target_entities: List[str] = field(default_factory=list)  # 目标实体类型列表，空则匹配所有

    def matches(self, entity: Dict[str, Any]) -> bool:
        """判断实体类型是否匹配此原子函数"""
        if not self.target_entities:
            return True  # 无限制，匹配所有
        return entity.get("type", "") in self.target_entities

    def execute(self, entity: Optional[Dict[str, Any]] = None) -> Optional[FuncResult]:
        """
        执行判定。
        当 entity 为 None 时，视为"缺失检查"模式：
        - EXIST-* 类函数 → 返回 FAIL（实体不存在）
        - 其他函数 → 返回 None（无实体可判定）
        """
        if entity is None:
            # 缺失检查模式
            if self.category in (FuncCategory.EXIST,):
                # EXIST 类：实体不存在即为违规
                return FuncResult(
                    func_id=self.func_id,
                    func_name=self.name,
                    clause_id=self.clause_id,
                    operator=self.operator,
                    threshold=self.threshold,
                    actual=0.0,
                    result="FAIL",
                    delta=-self.threshold,
                    severity=Severity.CRITICAL,
                    entity_id="",
                    entity_type="missing",
                    params={"extracted_value": 0.0, "unit": self.unit,
                            "note": "未检测到目标实体"},
                )
            return None

        if not self.matches(entity):
            return None
        
        # EXIST 类特殊处理：检查实体的 exists/count 属性
        # 合成图纸 META 实体：可能显式设置 exists=False 表示故意缺失
        # 真实图纸实体：实体存在即 PASS（无 exists 属性视为存在）
        if self.category in (FuncCategory.EXIST,):
            props = entity.get("properties", {})
            exists = props.get("exists", None)
            count = props.get("count", 0)
            # 兼容：字符串 'False'/'true' 转为布尔
            if isinstance(exists, str):
                exists = exists.lower() in ("true", "1", "yes")
            if isinstance(count, str):
                try:
                    count = float(count)
                except ValueError:
                    count = 0
            if exists is not None:
                actual = 1.0 if exists else 0.0
            elif count > 0:
                actual = 1.0
            elif len(props) > 0:
                # 真实图纸：实体有任何属性 → 存在
                actual = 1.0
            else:
                # 兼容：使用原 _extract_value 逻辑（检查 META 图层无属性实体的存在性）
                actual = 1.0 if (props.get("exists", False) or props.get("count", 0) > 0) else 0.0
            passed = actual >= self.threshold
            return FuncResult(
                func_id=self.func_id,
                func_name=self.name,
                clause_id=self.clause_id,
                operator=self.operator,
                threshold=self.threshold,
                actual=actual,
                result="PASS" if passed else "FAIL",
                delta=actual - self.threshold,
                severity=Severity.PASS if passed else Severity.CRITICAL,
                entity_id=entity.get("id", ""),
                entity_type=entity.get("type", ""),
                params={"extracted_value": actual, "unit": self.unit},
            )
        
        actual = self._extract_value(entity)
        if actual is None:
            return None  # 属性缺失，无法判定
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
        """从实体中提取判定所需的值
        
        单位转换策略（V2优化）：
        - 优先使用 entity 中明确的 unit 字段
        - 无 unit 时基于数量级启发式判断：
          - 宽度/长度: >100mm→m, 否则→m
          - 面积: >10000→mm²转m², 否则→m²
          - 距离: >100mm→m, 否则→m
        """
        props = entity.get("properties", {})
        entity_type = entity.get("type", "")
        func_id = self.func_id

        # 如果有明确unit字段，直接按unit判断
        unit = props.get("unit", "")
        
        # 宽度类：优先用width/clear_width
        if func_id in ("DIM-001", "DIM-003", "DIM-004"):
            val = props.get("width", props.get("clear_width", 0.0))
            if val < 0.01:
                return None  # 无宽度数据，跳过判定
            if unit == "mm":
                return val / 1000.0
            if unit == "m":
                return val
            # 无unit启发式: >100视为mm
            if val > 100:
                return val / 1000.0
            return val

        if func_id == "DIM-002":  # 面积判定
            val = props.get("area", 0.0)
            if unit == "mm2":
                return val / 1000000.0
            if unit == "m2":
                return val
            # 无unit启发式: 阈值10000，>10000视为mm²
            if val > 10000:
                return val / 1000000.0
            return val

        if func_id == "DIST-001":  # 距离判定
            val = props.get("travel_distance", props.get("length", 0.0))
            if unit == "mm":
                return val / 1000.0
            if unit == "m":
                return val
            if val > 100:
                return val / 1000.0
            return val

        if func_id == "COUNT-001":  # 数量判定
            return props.get("count", props.get("exit_count", 1.0))

        if func_id == "ATTR-001":  # 防火门等级
            val = props.get("fire_rating", props.get("rating", 0.0))
            if val < 0.5 and entity_type in ("door", "exit_door"):
                # 非 fire_door：不判定防火等级
                return None
            return val

        if func_id == "EXIST-001":  # 存在性判定
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0

        if func_id in ("DIM-005", "AREA-001"):  # 面积判定（窗/避难层）
            val = props.get("area", props.get("width", 0) * props.get("height", 0))
            if val < 0.01:
                return None  # 无面积数据，跳过判定
            if unit == "mm2":
                return val / 1000000.0
            if unit == "m2":
                return val
            if val > 10000:
                return val / 1000000.0
            return val

        # L2 新增函数
        if func_id in ("DIM-006", "DIM-007"):  # 疏散门净宽 / 防火卷帘宽度
            val = props.get("width", props.get("clear_width", 0.0))
            if val < 0.01:
                return None  # 无宽度数据，跳过判定
            # 小门（<0.8m）不适用疏散门净宽判定（设备门/检修门等）
            if func_id == "DIM-006" and val < 0.8:
                return None
            # 设备门/管井门排除：图层含 设备/管线/PIPE/SB 等关键词
            if func_id == "DIM-006":
                layer = entity.get("layer", "").upper()
                non_exit_layer_kw = ["设备", "管线", "管井", "PIPE", "SB", "喷淋", "消防排水"]
                if any(kw.upper() in layer for kw in non_exit_layer_kw):
                    return None
            if unit == "mm":
                return val / 1000.0
            if unit == "m":
                return val
            if val > 100:
                return val / 1000.0
            return val

        if func_id in ("EXIST-002", "EXIST-003", "EXIST-004", "EXIST-005", "EXIST-006"):  # 存在性判定
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0

        if func_id == "ATTR-002":  # 保温材料等级
            return props.get("fire_rating", props.get("rating", 0.0))

        if func_id == "LIGHT-001":  # 照度
            return props.get("illuminance", props.get("lux", 0.0))

        # L3 新增函数
        if func_id in ("DIM-008", "DIM-010"):  # 排烟窗面积 / 消防救援窗面积
            val = props.get("area", props.get("width", 0) * props.get("height", 0))
            if val < 0.01:
                return None  # 无面积数据，跳过判定
            if unit == "mm2":
                return val / 1000000.0
            if unit == "m2":
                return val
            if val > 10000:
                return val / 1000000.0
            return val

        if func_id == "DIM-009":  # 疏散出口宽度
            val = props.get("width", props.get("clear_width", 0.0))
            if val < 0.01:
                return None  # 无宽度数据，跳过判定
            # 小门（<0.8m）不适用疏散出口宽度判定
            if val < 0.8:
                return None
            if unit == "mm":
                return val / 1000.0
            if unit == "m":
                return val
            if val > 100:
                return val / 1000.0
            return val

        if func_id in ("DIST-002", "DIST-003"):  # 防火间距 / 袋形走道长度
            val = props.get("distance", props.get("length", 0.0))
            if unit == "mm":
                return val / 1000.0
            if unit == "m":
                return val
            if val > 100:
                return val / 1000.0
            return val

        if func_id == "AREA-002":  # 消防电梯前室面积
            val = props.get("area", 0.0)
            if val < 0.01:
                # 从 bbox 宽高计算面积（mm²）
                bw = entity.get("bbox", {}).get("width", 0)
                bh = entity.get("bbox", {}).get("height", 0)
                if bw > 0 and bh > 0:
                    val = bw * bh
            if unit == "mm2":
                return val / 1000000.0
            if unit == "m2":
                return val
            if val > 10000:
                return val / 1000000.0
            return val

        if func_id == "ATTR-003":  # 防火窗等级
            val = props.get("fire_rating", props.get("rating", 0.0))
            if val < 0.01:
                return None  # 无防火等级数据，跳过判定
            return val

        if func_id in ("EXIST-007", "EXIST-008", "EXIST-009", "EXIST-010"):
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0

        # EVAC 类：疏散路径判定
        if func_id == "EVAC-001":  # 疏散路径是否存在
            return 1.0 if props.get("has_evacuation_route", False) else 0.0
        if func_id == "EVAC-002":  # 疏散路径长度
            return props.get("evacuation_path_length", props.get("travel_distance", 0.0))
        if func_id == "EVAC-003":  # 疏散路径是否超距
            return 0.0 if props.get("evacuation_too_far", False) else 1.0

        # 兜底：直接用value或0
        return props.get("value", 0.0)


# ── 函数注册表 ────────────────────────────────────────────

class FuncRegistry:
    """原子函数注册表 - 框架30个位置"""

    # 首批 10 个原子函数（L1级，与规范JSON库对齐）
    INITIAL_FUNCS = [
        AtomicFunction("DIM-001", "疏散楼梯净宽判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.18", "疏散楼梯净宽度不应小于1.2m", ">=", 1.2, "m",
                       target_entities=["staircase", "stair"]),
        AtomicFunction("DIM-002", "防火分区面积判定", FuncCategory.DIMENSION,
                       "GB50016-6.1.1", "防火分区面积不应大于2500㎡", "<=", 2500, "㎡",
                       target_entities=["fire_zone", "room", "floor"]),
        AtomicFunction("DIM-003", "消防车道宽度判定", FuncCategory.DIMENSION,
                       "GB50016-7.1.1", "消防车道宽度不应小于4m", ">=", 4.0, "m",
                       target_entities=["fire_lane", "road", "driveway"]),
        AtomicFunction("DIST-001", "疏散距离判定", FuncCategory.DISTANCE,
                       "GB50016-5.5.17", "疏散距离不应大于30m", "<=", 30.0, "m",
                       target_entities=["room", "floor", "space"]),
        AtomicFunction("COUNT-001", "安全出口数量判定", FuncCategory.COUNT,
                       "GB50016-5.5.8", "安全出口不应少于2个", ">=", 2.0, "个",
                       target_entities=["floor", "fire_zone"]),
        AtomicFunction("ATTR-001", "防火门等级判定", FuncCategory.ATTR,
                       "GB50016-6.5.1", "防火门等级不应低于丙级", ">=", 1.0, "级",
                       target_entities=["fire_door", "door"]),
        AtomicFunction("DIM-004", "疏散走道宽度判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.18", "疏散走道净宽度不应小于1.1m", ">=", 1.1, "m",
                       target_entities=["corridor", "aisle", "passage"]),
        AtomicFunction("AREA-001", "避难层面积判定", FuncCategory.AREA,
                       "GB50016-7.4.1", "避难层净面积不宜小于5㎡/人", ">=", 5.0, "㎡/人",
                       target_entities=["refuge_floor", "refuge_area", "floor"]),
        AtomicFunction("EXIST-001", "楼梯间存在判定", FuncCategory.EXIST,
                       "GB50016-5.5.12", "建筑应设置楼梯间", "==", 1.0, "有/无",
                       target_entities=["staircase", "stair"]),
        AtomicFunction("DIM-005", "窗净面积判定", FuncCategory.DIMENSION,
                       "GB50016-7.2.4", "消防窗净面积不应小于1.0㎡", ">=", 1.0, "㎡",
                       target_entities=["fire_window", "window"]),
        # L2 规范原子函数（9个）
        AtomicFunction("DIM-006", "疏散门净宽判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.19", "人员密集场所疏散门净宽不应小于1.4m", ">=", 1.4, "m",
                       target_entities=["exit_door", "door"]),
        AtomicFunction("DIM-007", "防火卷帘宽度判定", FuncCategory.DIMENSION,
                       "GB50016-6.5.3", "防火分隔防火卷帘宽度不应大于10m", "<=", 10.0, "m",
                       target_entities=["fire_curtain", "curtain"]),
        AtomicFunction("EXIST-002", "管道井封堵判定", FuncCategory.EXIST,
                       "GB50016-6.6.1", "管道井应每层用不燃材料封堵", "==", 1.0, "有/无",
                       target_entities=["shaft", "pipe_shaft", "cable_shaft"]),
        AtomicFunction("EXIST-003", "剪刀楼梯分隔判定", FuncCategory.EXIST,
                       "GB50016-5.5.24", "剪刀楼梯梯段间应设置防火隔墙", "==", 1.0, "有/无",
                       target_entities=["scissor_staircase", "staircase"]),
        AtomicFunction("EXIST-004", "疏散指示标志判定", FuncCategory.EXIST,
                       "GB50016-10.3.1", "疏散走道和安全出口应设疏散指示标志", "==", 1.0, "有/无",
                       target_entities=["exit_sign", "sign"]),
        AtomicFunction("EXIST-005", "自动灭火系统判定", FuncCategory.EXIST,
                       "GB50016-8.3.1", "一类高层应设置自动灭火系统", "==", 1.0, "有/无",
                       target_entities=["sprinkler_system", "sprinkler", "fire_system"]),
        AtomicFunction("EXIST-006", "火灾报警系统判定", FuncCategory.EXIST,
                       "GB50016-8.4.1", "一类高层应设置火灾自动报警系统", "==", 1.0, "有/无",
                       target_entities=["fire_alarm", "alarm_system", "fire_system"]),
        AtomicFunction("ATTR-002", "保温材料等级判定", FuncCategory.ATTR,
                       "GB50016-6.7.1", "保温材料应选用A或B1级", ">=", 2.0, "级",
                       target_entities=["insulation", "wall_insulation", "roof_insulation"]),
        AtomicFunction("LIGHT-001", "应急照明照度判定", FuncCategory.DIMENSION,
                       "GB50016-10.1.5", "疏散照明照度不应低于1.0lx", ">=", 1.0, "lx",
                       target_entities=["evacuation_lighting", "light", "lighting"]),
    ]

    # 框架预留 20 个位置（V2.0扩展）
    RESERVED_FUNCS = [
        # ===== L3 新增（11个，从19→30）=====
        # 防火间距
        AtomicFunction("DIST-002", "防火间距判定", FuncCategory.DISTANCE,
                       "GB50016-3.4.1", "厂房之间防火间距不应小于表3.4.1规定", ">=", 12.0, "m",
                       target_entities=["building", "factory", "warehouse"]),
        # 排烟窗面积
        AtomicFunction("DIM-008", "排烟窗面积判定", FuncCategory.DIMENSION,
                       "GB50016-9.2.1", "排烟窗净面积不应小于房间面积2%", ">=", 0.02, "㎡",
                       target_entities=["smoke_exhaust_window", "window", "room"]),
        # 消防电梯
        AtomicFunction("EXIST-007", "消防电梯判定", FuncCategory.EXIST,
                       "GB50016-7.3.1", "一类高层公共建筑应设消防电梯", "==", 1.0, "有/无",
                       target_entities=["fire_elevator", "elevator"]),
        # 消防电梯前室面积
        AtomicFunction("AREA-002", "消防电梯前室面积判定", FuncCategory.AREA,
                       "GB50016-7.3.5", "消防电梯前室面积不应小于6㎡", ">=", 6.0, "㎡",
                       target_entities=["elevator_lobby", "lobby", "room"]),
        # 疏散走道长度
        AtomicFunction("DIST-003", "袋形走道长度判定", FuncCategory.DISTANCE,
                       "GB50016-5.5.17", "袋形走道长度不应大于20m", "<=", 20.0, "m",
                       target_entities=["corridor", "aisle", "passage"]),
        # 疏散出口宽度
        AtomicFunction("DIM-009", "疏散出口宽度判定", FuncCategory.DIMENSION,
                       "GB50016-5.5.18", "疏散出口净宽度不应小于0.9m", ">=", 0.9, "m",
                       target_entities=["exit", "exit_door", "door"]),
        # 防火窗耐火极限
        AtomicFunction("ATTR-003", "防火窗等级判定", FuncCategory.ATTR,
                       "GB50016-6.5.1", "防火窗耐火极限不应低于1.0h", ">=", 1.0, "h",
                       target_entities=["fire_window", "window"]),
        # 屋顶消防水箱
        AtomicFunction("EXIST-008", "消防水箱判定", FuncCategory.EXIST,
                       "GB50016-8.2.1", "一类高层应设消防水箱", "==", 1.0, "有/无",
                       target_entities=["water_tank", "fire_system"]),
        # 消防水池
        AtomicFunction("EXIST-009", "消防水池判定", FuncCategory.EXIST,
                       "GB50016-8.1.3", "市政供水不足时应设消防水池", "==", 1.0, "有/无",
                       target_entities=["water_reservoir", "fire_system"]),
        # 消防救援窗
        AtomicFunction("DIM-010", "消防救援窗面积判定", FuncCategory.DIMENSION,
                       "GB50016-7.2.4", "消防救援窗口净面积不应小于1.0㎡", ">=", 1.0, "㎡",
                       target_entities=["rescue_window", "window"]),
        # 应急广播
        AtomicFunction("EXIST-010", "应急广播判定", FuncCategory.EXIST,
                       "GB50016-8.5.1", "一类高层应设应急广播系统", "==", 1.0, "有/无",
                       target_entities=["emergency_broadcast", "speaker", "fire_system"]),
        # ===== EVAC 疏散路径判定（V2新增，3个）=====
        AtomicFunction("EVAC-001", "疏散路径连通性判定", FuncCategory.EVAC,
                       "GB50016-5.5.17", "每个房间应有通往安全出口的疏散路径", "==", 1.0, "有/无",
                       target_entities=["room", "space", "floor"]),
        AtomicFunction("EVAC-002", "疏散路径长度判定", FuncCategory.EVAC,
                       "GB50016-5.5.17", "房间到最近安全出口的疏散距离不应大于30m", "<=", 30.0, "m",
                       target_entities=["room", "space", "floor"]),
        AtomicFunction("EVAC-003", "疏散路径合规性判定", FuncCategory.EVAC,
                       "GB50016-5.5.17", "房间到安全出口的疏散路径应满足规范要求", "==", 1.0, "合规/违规",
                       target_entities=["room", "space", "floor"]),
    ]

    def __init__(self):
        self._funcs: Dict[str, AtomicFunction] = {}
        for func in self.INITIAL_FUNCS + self.RESERVED_FUNCS:
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
        return 33  # 框架总容量：30 INITIAL + 3 EVAC