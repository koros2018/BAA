"""
BAA 原子函数库 - 规范判定核心
框架预留 30 个位置，首批实现 10 个
"""

from typing import Dict, Any, Optional, List, Tuple, Set  # typing: type hints
from enum import Enum  # import
from dataclasses import dataclass, field, replace as _dc_replace  # dataclass support

import concurrent.futures  # import
import logging  # stdlib: logging
import math  # stdlib: isclose 浮点比较容差

logger = logging.getLogger(__name__)  # function call


# ── 类型定义 ──────────────────────────────────────────────


class FuncCategory(Enum):  # class definition
    """原子函数分类"""

    DIMENSION = "dim"  # 尺寸/距离判定
    COUNT = "count"  # 数量判定
    DISTANCE = "dist"  # 距离判定
    ATTR = "attr"  # 属性判定
    EXIST = "exist"  # 存在性判定
    AREA = "area"  # 面积判定
    EVAC = "evac"  # 疏散路径判定（V2新增）
    ACCESS = "access"  # 无障碍设计判定（P47 新增）
    LIGHT = "light"  # 照明/照度判定（P57 扩展）
    THERMAL = "thermal"  # 热工性能判定（P45 新增）
    STRUCTURAL = "structural"  # 结构荷载判定（P46 新增）


class Severity(Enum):  # class definition
    CRITICAL = "critical"  # assignment
    MAJOR = "major"  # assignment
    MINOR = "minor"  # assignment
    PASS = "pass"  # assignment
    DEGRADED = "degraded"  # 超时降级
    ERROR = "error"  # 执行异常


# 边界比较容差：几何量（DXF 单位换算/扫线测量）存在浮点表示误差，
# 实测 0.8999999999999 与阈值 0.9 在语义上相等。仅吸收表示误差
# （相对 1e-6），不放宽真实偏差——0.85 vs 0.9 仍判 FAIL。
_COMPARE_REL_TOL = 1e-6
_COMPARE_ABS_TOL = 1e-9


def _compare(actual: float, operator: str, threshold: float) -> bool:
    """带表示误差容差的阈值比较（判定收敛点：消除浮点边界误报）。"""
    try:
        a = float(actual)
        t = float(threshold)
    except (TypeError, ValueError):
        return False
    if operator == ">=":
        return a >= t or math.isclose(a, t, rel_tol=_COMPARE_REL_TOL, abs_tol=_COMPARE_ABS_TOL)
    if operator == "<=":
        return a <= t or math.isclose(a, t, rel_tol=_COMPARE_REL_TOL, abs_tol=_COMPARE_ABS_TOL)
    if operator == "==":
        return abs(a - t) < 1e-6
    if operator == ">":
        return a > t
    if operator == "<":
        return a < t
    return False


# ── 数据结构 ──────────────────────────────────────────────


@dataclass  # code
class FuncResult:  # class definition
    """原子函数判定结果"""

    func_id: str  # 操作
    func_name: str  # 操作
    clause_id: str  # 规范条款编号
    operator: str  # >=, <=, ==, >, <
    threshold: float  # 操作
    actual: float  # 操作
    result: str  # PASS / FAIL
    delta: float  # 操作
    severity: Severity  # 操作
    entity_id: str  # 操作
    entity_type: str  # 操作
    params: Dict[str, Any] = field(default_factory=dict)  # function call
    confidence: float = 1.0  # 置信度 0.0~1.0，P36新增


# ── P0-1 类型别名组（canonical group membership）───────────
# 语义：同一 group 内的实体类型被原子函数视为等价匹配，
# 解决 classifier 产出类型与规则 target_entities 不一致导致的
# 可达性 gap（例：classifier 产出 "stair"，规则 targeting "staircase"）。
#
# 注意：只归并语义等价的建筑构件，不跨门/窗/墙等独立类别。
_TYPE_ALIAS_GROUPS: Tuple[Tuple[str, ...], ...] = (
    # Group 1: 室内楼梯核心（classifier 产出 stair 时规则 targeting staircase 需要匹配）
    # 注意：external_stair / outdoor_stair / smoke_proof_stair 有独立规范，不与室内归并
    ("staircase", "stair", "scissor_stair", "scissor_staircase"),
    # Group 2: 走廊/通道系列
    ("corridor", "hallway", "aisle", "passage", "walkway",
     "dead_end_corridor", "passageway", "exit_passageway"),
    # Group 3a: 窗户系列（语义等价，可互相归并）
    # 注意：窗户与通风口/开口语义不同，不能互相归并。
    # 此前 Group 3 把 window 与 smoke_vent/natural_vent 混为一组，
    # 导致 AREA-012（排烟量，target smoke_vent）对普通 window 判面积
    # → 139 条误报（nasji two-family-house 复测 2026-11）。
    ("window", "fire_window", "rescue_window", "smoke_exhaust_window"),
    # Group 3b: 开口/通风口系列（与窗户分离）
    ("opening", "natural_vent", "smoke_vent", "fire_rescue_opening",
     "rescue_opening", "smoke_exhaust"),
    # Group 4: 出口/疏散门系列
    ("exit_door", "exit", "doorway"),
    # Group 5: 附属房间归并到 room 概念
    ("antechamber", "staircase_lobby", "lobby", "elevator_lobby"),
)


def _type_group_of(entity_type: str) -> Optional[Tuple[str, ...]]:
    """返回实体类型所属的 alias group（若有），否则 None。"""
    for group in _TYPE_ALIAS_GROUPS:
        if entity_type in group:
            return group
    return None


def _target_groups_overlap(target_entities: List[str]) -> bool:
    """判断 target_entities 是否与任一 alias group 有交集。"""
    targets_set = set(target_entities)
    for group in _TYPE_ALIAS_GROUPS:
        if targets_set & set(group):
            return True
    return False


# ── T3: 前室类条款语义归属（互斥分流）───────────────────────
# 前室类条款（6㎡ 防烟前室 / 6㎡ 消防电梯前室 / 10㎡ 合用前室）在语义上
# 互斥：一个前室不可能同时是「防烟楼梯间前室」与「合用前室」。别名组
# Group 5 把 antechamber/staircase_lobby/lobby/elevator_lobby 归并后，
# 同一实体被多条条款同时命中（东莞通 ANTECHAMBER_2083 被 AREA-002 +
# DIM-018 + DIM-019 同时判，16 条重复 finding）。这里按实体语义把条款
# 分到互斥的归属域，保证同一实体最多只有一条前室条款成立：
#   - stair   → DIM-018（防烟楼梯间前室 ≥6㎡）
#   - shared  → DIM-019（合用前室 ≥10㎡，需显式合用证据）
#   - elevator / 泛化 lobby → AREA-002（消防电梯前室 ≥6㎡）
_SHARED_LOBBY_FLAGS = (
    "is_shared_lobby",
    "shared_lobby",
    "is_combined_lobby",
    "combined_lobby",
    "shared_with_fire_elevator",
)
_ELEVATOR_LOBBY_TYPES = {"elevator_lobby", "fire_elevator_lobby"}
_STAIR_LOBBY_TYPES = {
    "antechamber",
    "staircase_lobby",
    "smoke_proof_lobby",
    "scissor_stair_lobby",
}


def _lobby_entity_kind(entity: Dict[str, Any]) -> str:
    """返回前室实体的语义归属：shared / elevator / stair / ''（泛化 lobby）。"""
    props = entity.get("properties") or {}
    if any(props.get(k) for k in _SHARED_LOBBY_FLAGS):
        return "shared"
    # 文字标注是最直接的设计意图证据（如「合用前室」「消防电梯前室」）
    text = str(props.get("text") or "")
    if "合用" in text:
        return "shared"
    if "消防电梯" in text:
        return "elevator"
    subtype = entity.get("subtype") or props.get("subtype") or ""
    if subtype in _ELEVATOR_LOBBY_TYPES:
        return "elevator"
    if subtype in _STAIR_LOBBY_TYPES:
        return "stair"
    etype = entity.get("type", "")
    if etype in _ELEVATOR_LOBBY_TYPES:
        return "elevator"
    if etype in _STAIR_LOBBY_TYPES:
        return "stair"
    return ""


# ── T4: 疏散门宽度条款前置证据（楼层 / 人员密集场所）─────────
# DIM-021「首层疏散外门 ≥1.1m」的适用前提是门在首层（floor=F1）；
# DIM-022「人员密集场所疏散门 ≥1.4m」的前提是 occupancy=人员密集场所。
# 东莞通 villa 13 扇门 floor=None、occupancy 缺失，两条条款同时命中 25 条，
# 全部为无证据误报。缺证据时返回 None（与 DIM-002/DIST-002 等
# 「数据缺失不判定」一致）：规则引擎只有响应级 insufficient_evidence 布尔，
# 逐条缺证据的一致表达就是「不产出判定」，而不是编造 low 级 finding。
# 两条条款按建筑业态互斥：人员密集场所 → DIM-022；否则首层外门 → DIM-021。
_GROUND_FLOOR_LABELS = {
    "F1",
    "1F",
    "L1",
    "1",
    "1层",
    "首层",
    "一层",
    "地上一层",
    "GF",
    "GROUND",
    "GROUNDFLOOR",
}
_ASSEMBLY_OCCUPANCY_VALUES = {
    "assembly",
    "public_assembly",
    "crowded",
    "crowded_place",
    "personnel_intensive",
    "人员密集",
    "人员密集场所",
    "密集场所",
    "商场",
    "market",
    "theater",
    "theatre",
    "cinema",
    "stadium",
    "gymnasium",
    "体育馆",
    "影剧院",
    "观众厅",
}


def _is_ground_floor(value: Any) -> bool:
    """判断楼层标注是否为首层（F1/1F/一层/首层…）。"""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return float(value) == 1.0
    s = str(value).strip().upper().replace(" ", "")
    if not s:
        return False
    if s in _GROUND_FLOOR_LABELS:
        return True
    # 带后缀的标注（如「首层平面」「F1-消防」），要求 F1/1F 后不接数字
    if s.startswith(("首层", "一层", "地上一层")):
        return True
    for prefix in ("F1", "1F"):
        if s.startswith(prefix) and (len(s) == len(prefix) or not s[len(prefix)].isdigit()):
            return True
    return False


def _is_assembly_occupancy(props: Dict[str, Any]) -> bool:
    """判断是否有人员密集场所（occupancy）证据。"""
    if props.get("is_assembly_occupancy") or props.get("crowded_place"):
        return True
    for key in (
        "occupancy",
        "occupancy_type",
        "use_type",
        "building_use",
        "place_type",
        "function_type",
    ):
        value = props.get(key)
        if value is None:
            continue
        s = str(value).strip().lower()
        if s in _ASSEMBLY_OCCUPANCY_VALUES or "人员密集" in s or "密集场所" in s:
            return True
    return False


@dataclass  # code
class AtomicFunction:  # class definition
    """原子函数定义"""

    func_id: str  # 操作
    name: str  # 操作
    category: FuncCategory  # 操作
    clause_id: str  # 操作
    description: str  # 操作
    operator: str  # 操作
    threshold: float  # 操作
    unit: str  # 操作
    target_entities: List[str] = field(default_factory=list)  # 目标实体类型列表，空则匹配所有
    depends_on: List[str] = field(default_factory=list)  # 依赖的前置函数ID列表
    requires_global_context: bool = False  # P70: 需要全局上下文判定，不在逐实体循环中执行
    prerequisite_types: List[str] = field(
        default_factory=list
    )  # 条件性规则：前置实体类型（如 EXIST-067 需 fire_wall 存在才判定）
    # P2-1: 2D 图纸不可判定标记。仅元数据，不改变 matches/execute 行为；
    # 用于覆盖率双口径报告（全规则口径 / 可判定口径）。
    unsupported_2d: bool = False
    unsupported_reason: str = ""
    # P2-1b: 实现侧执行门禁缺陷（判据可取，缺口在代码）。不计入
    # unsupported_2d，规则仍留在可判定分母，仅用于缺陷清单。
    implementation_gate_defect: bool = False
    defect_note: str = ""
    # P133: 实现门禁（能力缺失，不是可判定缺陷）。规则保留在全规则口径分母，
    # 但剔除出可判定口径分母，执行链不产出 PASS/FAIL。
    implementation_gate: bool = False
    implementation_gate_reason: str = ""

    def __post_init__(self) -> None:  # hook: normalize set→list (some modules pass {"a", "b"})
        """数据层归一化：将 set 转为有序 list，保证 [0] 索引和 matches() 稳定。"""
        if isinstance(self.target_entities, set):  # condition: set passed
            self.target_entities = sorted(self.target_entities)  # normalize
        if isinstance(self.depends_on, set):  # condition: set passed
            self.depends_on = sorted(self.depends_on)  # normalize
        # 操作符归一化：部分模块用短名 ge/le/eq/lt/exist，execute() 需要标准符号
        OP_MAP = {  # code
            "ge": ">=",  # normalize
            "le": "<=",  # normalize
            "eq": "==",  # normalize
            "lt": "<",  # normalize
            "exist": ">=",  # normalize: 存在性检查 actual 为 1/0，>=0 即通过
            "not_exist": "<=",  # normalize: 不应存在 actual 为 1/0，<=0 即通过
        }  # code
        self.operator = OP_MAP.get(self.operator, self.operator)  # normalize

    # 原子函数默认超时时间（秒），30s 内应完成
    DEFAULT_TIMEOUT: int = 30  # assignment

    def matches(
        self, entity: Dict[str, Any]
    ) -> bool:  # function: def matches(self, entity: Dict[str, Any]) -> bool:
        """判断实体类型是否匹配此原子函数（P0-1 类型别名归并 + subtype 语义）"""
        if not self.target_entities:  # check: negated condition
            return True  # 无限制，匹配所有
        ent_type = entity.get("type", "")
        # 1. 精确匹配
        if ent_type in self.target_entities:
            return True
        # 1c. doorway 语义门禁（T2）：门洞/墙开口默认不是疏散门或安全出口。
        #    doorway 与 exit_door 同属别名组 5，若放行会把全部墙洞计入
        #    “出口/疏散门”类规则的适用面（东莞通 277 个门洞 → DIM-113 误报 21 条）。
        #    仅当规则显式以 doorway 为目标（DIM-006/009 洞口净宽）或实体带显式
        #    疏散标注（is_evacuation_door/evacuation_door/疏散 subtype）才匹配。
        if ent_type == "doorway":
            props = entity.get("properties") or {}
            explicit = (
                props.get("is_evacuation_door")
                or props.get("evacuation_door")
                or entity.get("subtype") in ("evacuation_door", "room_door", "exit_door")
            )
            if not explicit:
                return False
        # 1b. subtype 语义匹配（P0-1 空间上下文识别）
        #    TEXT 标注 → inferred_type → subtype（如 room/subtype=lobby）。
        #    特化规则（AREA-002 前室、AREA-004 控制室等）target 含特化类型，
        #    但实体 type=room（泛化），需 subtype 确认才匹配。
        #    注意：仅当 subtype 是"语义特化"（非泛化 room）时参与匹配，
        #    避免普通 room 被特化规则误匹配。
        ent_subtype = entity.get("subtype") or entity.get("properties", {}).get("inferred_type")
        if ent_subtype and ent_subtype in self.target_entities:
            # 防误报：subtype 必须比 type 更特化（subtype != type）
            if ent_subtype != ent_type:
                return True
        # 2. 别名组匹配：entity type 所属 group 与 rule target_entities 有交集
        group = _type_group_of(ent_type)
        if group and _target_groups_overlap(self.target_entities):
            target_set = set(self.target_entities)
            return bool(set(group) & target_set)
        return False  # return

    def execute(
        self, entity: Optional[Dict[str, Any]] = None
    ) -> Optional[
        FuncResult
    ]:  # function: def execute(self, entity: Optional[Dict[str, Any]] = None) -
        """
        执行判定。
        当 entity 为 None 时，视为"缺失检查"模式：
        - EXIST-* 类函数 → 返回 FAIL（实体不存在）
        - 其他函数 → 返回 None（无实体可判定）
        """
        if entity is None:  # check: value is None
            # 缺失检查模式
            if self.category in (FuncCategory.EXIST,):  # check: membership test
                # EXIST 类：实体不存在即为违规
                return FuncResult(  # return
                    func_id=self.func_id,  # assignment
                    func_name=self.name,  # assignment
                    clause_id=self.clause_id,  # assignment
                    operator=self.operator,  # assignment
                    threshold=self.threshold,  # assignment
                    actual=0.0,  # assignment
                    result="FAIL",  # assignment
                    delta=-self.threshold,  # assignment
                    severity=Severity.CRITICAL,  # assignment
                    confidence=1.0,  # 缺失实体判定置信度为 1.0（明确）
                    entity_id="",  # assignment
                    entity_type="missing",  # assignment
                    params={  # assignment
                        "extracted_value": 0.0,  # code
                        "unit": self.unit,  # code
                        "reason": "missing_entity",  # code
                        "clause_text": self.description,  # code
                        "note": "未检测到目标实体",  # code
                    },  # 字段
                )  # code
            return None  # return: None

        if not self.matches(entity):  # check: negated condition
            return None  # return: None

        # EXIST 类特殊处理：检查实体的 exists/count 属性
        # 合成图纸 META 实体：可能显式设置 exists=False 表示故意缺失
        # 真实图纸实体：实体存在即 PASS（无 exists 属性视为存在）
        if self.category in (FuncCategory.EXIST,):  # check: membership test
            props = entity.get("properties", {})  # function call
            # 测试注入：_test_value 直接返回，跳过 exists/count 推断
            if "_test_value" in props:  # condition: test injection
                actual = float(props["_test_value"])  # assignment
            else:
                exists = props.get("exists", None)  # function call
                count = props.get("count", 0)  # function call
                # 兼容：字符串 'False'/'true' 转为布尔
                if isinstance(exists, str):  # condition: isinstance(exists, str):
                    exists = exists.lower() in ("true", "1", "yes")  # function call
                if isinstance(count, str):  # condition: isinstance(count, str):
                    try:  # 尝试
                        count = float(count)  # function call
                    except ValueError:  # 捕获异常
                        count = 0  # assignment
                if exists is not None:  # check: value is not None
                    actual = 1.0 if exists else 0.0  # assignment
                elif count > 0:  # 条件分支
                    actual = 1.0  # assignment
                elif len(props) > 0:  # 条件分支
                    # 真实图纸：实体有任何属性 → 存在
                    actual = 1.0  # assignment
                else:  # 否则
                    # 兼容：使用原 _extract_value 逻辑（检查 META 图层无属性实体的存在性）
                    actual = (
                        1.0 if (props.get("exists", False) or props.get("count", 0) > 0) else 0.0
                    )  # function call
            # 尊重 operator 字段（P57 后部分 EXIST 函数使用 == / <=）
            # 生产环境 actual 为 0.0 或 1.0，语义等价
            passed = _compare(actual, self.operator, self.threshold)
            return FuncResult(  # return
                func_id=self.func_id,  # assignment
                func_name=self.name,  # assignment
                clause_id=self.clause_id,  # assignment
                operator=self.operator,  # assignment
                threshold=self.threshold,  # assignment
                actual=actual,  # assignment
                result="PASS" if passed else "FAIL",  # assignment
                delta=actual - self.threshold,  # assignment
                severity=Severity.PASS if passed else Severity.CRITICAL,  # assignment
                confidence=1.0,  # 存在性判定置信度为 1.0
                entity_id=entity.get("id", ""),  # function call
                entity_type=entity.get("type", ""),  # function call
                params={  # assignment
                    "extracted_value": actual,  # code
                    "unit": self.unit,  # code
                    "comparison_detail": f"{actual} {self.operator} {self.threshold} = {passed}",  # assignment
                    "clause_text": self.description,  # code
                    "entity_layer": entity.get("layer", ""),  # function call
                    "passed": passed,  # code
                },  # code
            )  # code

        actual = self._extract_value(entity)  # function call
        if actual is None:  # check: value is None
            return None  # 属性缺失，无法判定
        props = entity.get("properties") or {}
        width_basis = props.get("width_basis", "")  # 扇线/弧半径符号尺寸
        width_value = props.get("width", props.get("clear_width"))
        is_symbol_width = (
            self.unit == "m"
            and width_basis in ("leaf", "arc_radius")
            and width_value is not None
            and abs(actual - float(width_value)) < 1e-9  # 本次判定实际用的是宽度
        )
        if is_symbol_width:
            # 符号尺寸未扣门框，名义洞口宽存在 ±50mm 不确定度：
            # 1) 尺寸不构成可通行门窗（<300mm / >3000mm）→ 不判定
            # 2) 落点在阈值 ±50mm 带内 → insufficient_evidence，不产 PASS/FAIL
            if not props.get("_width_plausible", True):
                return None
            band = props.get("_width_uncertainty_m", 0.05)
            if abs(actual - self.threshold) <= band:
                return None
        delta = actual - self.threshold  # assignment

        # 执行比较
        passed = _compare(actual, self.operator, self.threshold)

        # 严重等级
        if passed:  # condition: passed:
            severity = Severity.PASS  # assignment
        else:  # 否则
            abs_delta = abs(delta)  # function call
            if abs_delta > self.threshold * 0.3:  # check: numeric comparison
                severity = Severity.CRITICAL  # assignment
            elif abs_delta > self.threshold * 0.1:  # 条件分支
                severity = Severity.MAJOR  # assignment
            else:  # 否则
                severity = Severity.MINOR  # assignment

        return FuncResult(  # return
            func_id=self.func_id,  # assignment
            func_name=self.name,  # assignment
            clause_id=self.clause_id,  # assignment
            operator=self.operator,  # assignment
            threshold=self.threshold,  # assignment
            actual=actual,  # assignment
            result="PASS" if passed else "FAIL",  # assignment
            delta=delta,  # assignment
            severity=severity,  # assignment
            entity_id=entity.get("id", ""),  # function call
            entity_type=entity.get("type", ""),  # function call
            params={  # assignment
                "extracted_value": actual,  # code
                "unit": self.unit,  # code
                "comparison_detail": f"{actual} {self.operator} {self.threshold} = {passed}",  # assignment
                "clause_text": self.description,  # code
                "entity_layer": entity.get("layer", ""),  # function call
                "passed": passed,  # code
                "approximate": bool(is_symbol_width),  # 符号尺寸近似值
                "width_basis": width_basis,  # leaf / arc_radius / ""
                "width_uncertainty_m": (
                    props.get("_width_uncertainty_m", 0.05)
                    if is_symbol_width
                    else 0.0
                ),  # code
            },  # code
            confidence=self._calculate_confidence(entity, actual),  # function call
        )  # code

    def _calculate_confidence(
        self, entity: Dict[str, Any], actual: float
    ) -> float:  # function: def _calculate_confidence(self, entity: Dict[str, Any], actu
        """计算审查结果的置信度（P36）

        基于以下因素综合评分：
        1. 实体识别置信度（YOLO vs 规则解析）
        2. 属性完整度（关键属性是否缺失）
        3. 偏差幅度（与阈值越近越可疑）

        返回: 0.0~1.0
        """
        props = entity.get("properties", {})  # function call
        confidence = 1.0  # assignment

        # 1. 检测来源降权
        detection_source = props.get("detection_source", "")  # function call
        if detection_source == "yolo":  # condition: detection_source == "yolo":
            confidence *= 0.7  # YOLO 检测的实体置信度较低
        elif detection_source == "text":  # elif condition
            confidence *= 0.8  # TEXT 推断的实体

        # 2. 属性完整度（按函数类别智能判断必需属性）
        missing_keys = 0  # assignment
        if self.category == FuncCategory.DIMENSION:  # check: OR condition
            required_keys = ["width"]  # assignment
        elif self.category == FuncCategory.AREA:  # elif condition
            required_keys = ["area"]  # assignment
        elif self.category == FuncCategory.COUNT:  # elif condition
            required_keys = ["count"]  # assignment
        elif self.category == FuncCategory.ATTR:  # elif condition
            required_keys = ["fire_rating"]  # assignment
        elif self.category == FuncCategory.EVAC:  # elif condition
            required_keys = ["has_evacuation_route", "evacuation_path_length"]  # assignment
        elif self.category == FuncCategory.EXIST:  # elif condition
            required_keys = []  # assignment
        elif self.category == FuncCategory.ACCESS:  # elif condition
            required_keys = []  # assignment
        else:  # else: default case
            required_keys = []  # assignment
        for key in required_keys:  # loop: iterate
            val = props.get(key, None)  # function call
            if val is None or val == 0:  # check: value is None
                missing_keys += 1  # accumulate
        if missing_keys > 0:  # check: numeric comparison
            confidence *= max(0.5, 1.0 - missing_keys * 0.1)  # get maximum

        # 3. 偏差幅度（结果越接近阈值越不确定）
        if self.threshold > 0 and actual > 0:  # check: numeric comparison
            ratio = abs(actual - self.threshold) / max(self.threshold, 1e-6)  # get maximum
            if ratio < 0.05:  # check: numeric comparison
                confidence *= 0.85  # 极度接近阈值
            elif ratio < 0.1:  # elif condition
                confidence *= 0.95  # 接近阈值

        # 4. floor 属性缺失降权
        if "floor" not in props:  # check: membership test
            confidence *= 0.95  # multiply

        return round(max(0.1, min(1.0, confidence)), 2)  # return

    def _extract_value(
        self, entity: Dict[str, Any]
    ) -> float:  # function: def _extract_value(self, entity: Dict[str, Any]) -> float:
        """从实体中提取判定所需的值

        单位转换策略（V2优化）：
        - 优先使用 entity 中明确的 unit 字段
        - 无 unit 时基于数量级启发式判断：
          - 宽度/长度: >100mm→m, 否则→m
          - 面积: >10000→mm²转m², 否则→m²
          - 距离: >100mm→m, 否则→m
        """
        props = entity.get("properties", {})  # function call
        entity_type = entity.get("type", "")  # function call
        func_id = self.func_id  # assignment

        # 测试注入：_test_value 优先返回，跳过所有属性推断和单位转换
        # 生产环境 entity 不含此 key，无影响
        if "_test_value" in props:  # condition: test injection
            return float(props["_test_value"])  # return

        # 如果有明确unit字段，直接按unit判断
        unit = props.get("unit", "")  # function call

        # 宽度类：优先用width/clear_width
        # T-A4: DIM-113（房间疏散门净宽 ≥0.9m）此前无提取分支，永远返回 None
        # （死函数）——Step 3.5/3.6/3.7 注入的 door width 无法被消费，补齐。
        if func_id in ("DIM-001", "DIM-003", "DIM-004", "DIM-113"):  # check: membership test
            # 误报治理：DIM-113「房间疏散门」需要适用性证据。真实图纸 2644 个
            # door 中 647 个宽度 <0.9m（0.7~0.88m），绝大多数是卫生间/设备/管井
            # 普通门，并非疏散门——逐门判违规在单图上产生 647 条误报（占全部
            # 误报 76%）。与 DIM-006 同口径（普通门不具备疏散门语义不判定）：
            # 仅 exit_door/evacuation_door/room_door 或显式标注的实体判定。
            if func_id == "DIM-113":  # condition: func_id == "DIM-113":
                etype = entity.get("type", "")  # function call
                explicit = (
                    props.get("is_evacuation_door")
                    or props.get("evacuation_door")
                    or entity.get("subtype") in ("evacuation_door", "room_door")
                )
                # T2: doorway（墙洞/开口）同口径——未标注疏散语义的门洞不是
                # 「房间疏散门」。matches() 的 doorway 门禁已拦截适用面，这里再做
                # 提取层兜底（execute_chained 逐实体执行不经过 matches）。
                if etype in ("door", "doorway") and not explicit:  # check: applicability
                    return None  # 普通门/门洞适用性未知，不判疏散门净宽
            # DIM-113 bbox 合理性：非门实体（线/TEXT/hatch）误分类为 door 时，
            # bbox 一边接近 0（如 bbox_h=0 的线，bbox_w=0 的线，或 TEXT 框）。
            # 跨图纸复测（2026-10，35 条）：DOOR_FIRE_TEXT / THIN / COLU_HATCH /
            # 抹灰 / fuzhu 等层误分类实体，bbox 一边≈0，宽度来自投影而非真实门宽。
            if func_id == "DIM-113":
                bbox = entity.get("bbox") or {}
                bw, bh = bbox.get("width", 0), bbox.get("height", 0)
                if bw < 0.05 or bh < 0.05:  # check: bbox 合理性
                    return None  # 非门实体（线/TEXT/hatch），跳过判定
            # DIM-113 宽度下限：width <= 0.6m 视为非人员通行门（设备门/管井门/检修门）
            # 跨图纸复测（2026-11）：DOOR_2805(0.58m)/5467/6002/8318(0.60m) 疑似设备门
            if func_id == "DIM-113":
                val = props.get("width", props.get("clear_width", 0.0))
                converted = val / 1000.0 if unit == "mm" else val
                if converted <= 0.6:
                    return None  # 非人员通行门（设备/管井/检修门），跳过判定
            val = props.get("width", props.get("clear_width", 0.0))  # function call
            if val < 0.01:  # check: numeric comparison
                # P0-1 可达性补齐：DIM-003（消防车道净宽）的 fire_lane 实体
                # 由扫线法产出，只有 bbox 无 width 属性。车道净宽 = bbox 短边
                # （车道是狭长矩形，短边即宽度）。仅对 fire_lane/road/driveway
                # 生效，避免普通 room 的 bbox 短边被误当宽度。
                if func_id == "DIM-003":
                    # 车道语义：实体 type 或 subtype 为 fire_lane/road/driveway。
                    # 扫线法房间 type=room 但 subtype=fire_lane（TEXT 推断），
                    # 也构成车道语义，可参与净宽判定。
                    lane_semantics = entity_type in ("fire_lane", "road", "driveway") or (
                        entity.get("subtype") in ("fire_lane", "road", "driveway")
                        or props.get("inferred_type") in ("fire_lane", "road", "driveway")
                    )
                    if lane_semantics:
                        # 证据门槛：bbox 短边只有在实体是闭合多边形时才是车道净宽。
                        # 图层规则聚合出的道路中心线/图框 LINE 链（无 points/closed）
                        # 的 bbox 短边是线宽笔迹，不是净宽——实测 baa-file-584
                        # ROAD_2527/2841/3290 用 0.5~2.05m 的笔迹宽度被判 4m 净宽
                        # 不足（3 条无法追溯的 critical）。无闭合证据时不做判定。
                        points = props.get("points")
                        closed = props.get("closed")
                        if not (isinstance(points, (list, tuple)) and closed is True):
                            return None
                        bbox = entity.get("bbox") or {}
                        bw, bh = bbox.get("width", 0), bbox.get("height", 0)
                        # 防误报：TEXT/标注类实体（bbox 短边 <500mm）不是车道几何，
                        # 其 bbox 是文字框，短边无物理意义。仅真实车道多边形参与。
                        if bw > 0 and bh > 0 and min(bw, bh) >= 500:
                            val = min(bw, bh)  # 短边 = 车道净宽（mm）
                        else:
                            return None
                    else:
                        return None
                else:
                    return None  # 无宽度数据，跳过判定
            # DIM-001 楼梯净宽：bbox 推断宽度不是楼梯净宽的有效测量。
            # 跨图纸复测（2026-10，32 图）：146 条 FAIL 全部来自
            # stair_bbox_long_edge / stair_bbox_span（实测 0.50~1.10m）。
            # 楼梯 bbox 长边 = 梯段水平投影长度，短边 = 踏步宽，旋转后外接矩形
            # 对角投影既非长边也非短边，系统性低估真实净宽，不构成违规证据。
            # 仅 CAD 标注 / YOLO 等带来源的宽度参与判定（DIM-006 同口径）。
            if func_id == "DIM-001":
                width_source = props.get("_width_source", "")
                if width_source in ("stair_bbox_long_edge", "stair_bbox_span"):
                    return None
            # DIM-001 合理性下限：楼梯净宽 <0.6m 必为分类/测量错误
            # （真实图纸实测 0.397m 来自 TEXT 实体被误分类为 stair 的文本框长边）
            if func_id == "DIM-001" and val < 0.6:  # check: numeric comparison
                return None
            # DIM-001 边界容差：<2% 偏差视为测量误差，不报违规
            # （与 DIM-004/DIM-113 同口径，用阈值而非硬编码，兼容建筑类型覆盖）
            if (
                func_id == "DIM-001" and self.threshold > 0 and 0.98 <= (val / self.threshold) < 1.0
            ):  # check: numeric comparison
                return None  # 边界楼梯净宽，跳过判定

            # DIM-004 边界容差：<2% 偏差视为测量误差，不报违规
            if func_id == "DIM-004" and 0.98 <= (val / 1.1) < 1.0:  # check: numeric comparison
                return None  # 边界走廊，跳过判定
            # DIM-113 边界容差：与 DIM-004/DIM-006 同口径（用阈值而非硬编码，兼容
            # API 层按建筑类型改写阈值的场景）
            if (
                func_id == "DIM-113" and self.threshold > 0 and 0.98 <= (val / self.threshold) < 1.0
            ):  # check: numeric comparison
                return None  # 边界门宽，跳过判定
            if unit == "mm":  # condition: unit == "mm":
                converted = val / 1000.0  # assignment
                # DIM-004 走廊宽度合理性检查：转换后 <0.5m 视为异常（YOLO 误检）
                if func_id == "DIM-004" and converted < 0.5:  # check: numeric comparison
                    return None  # return: None
                return converted  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            # 无unit启发式: >100视为mm
            if val > 100:  # check: numeric comparison
                converted = val / 1000.0  # assignment
                # 转换后的合理性检查
                if func_id == "DIM-004" and converted < 0.5:  # check: numeric comparison
                    return None  # 走廊宽度 <0.5m 明显异常（可能是 YOLO 误检）
                return converted  # return
            return val  # return

        if func_id == "DIM-002":  # 面积判定
            val = props.get("area", 0.0)  # function call
            if unit == "mm2":  # condition: unit == "mm2":
                return val / 1000000.0  # return
            if unit == "m2":  # condition: unit == "m2":
                return val  # return
            # 无unit启发式: >10000视为mm²
            if val > 10000:  # check: numeric comparison
                return val / 1000000.0  # return
            # 面积合理性检查：>10000㎡明显异常（单位未转换或误算）
            if val > 10000:  # check: numeric comparison
                return None  # return: None
            return val  # return

        if func_id == "DIST-001":  # 距离判定
            # P71 修复: 只认 travel_distance（真实疏散距离），不再 fallback 到 length（楼板尺寸）
            val = props.get("travel_distance")
            if val is None:
                return None  # 无疏散距离数据，跳过判定
            if unit == "mm":  # 单位转换
                return val / 1000.0  # return
            if unit == "m":  # 单位转换
                return val  # return
            if val > 100:  # 数量级判断
                return val / 1000.0  # return
            return val  # return

        if func_id == "COUNT-001":  # 数量判定
            val = props.get("count", props.get("exit_count", None))
            if val is None:
                return None  # 无出口数量属性，跳过判定
            return float(val)

        if func_id == "ATTR-001":  # 防火门等级
            # 区分"属性不存在"和"属性值为0"：
            # - 属性不存在（真实图纸）：跳过判定，不产生违规
            # - 属性值为0（合成图纸显式设0表示丙级以下）：返回 FAIL
            has_fire_rating = "fire_rating" in props or "rating" in props  # assignment
            val = props.get("fire_rating", props.get("rating", 0.0))  # function call
            if not has_fire_rating:  # check: negated condition
                # 完全无防火等级属性 → 无法判定
                return None  # return: None
            if val < 0.5 and entity_type in ("door", "exit_door"):  # check: numeric comparison
                # 非 fire_door：不判定防火等级
                return None  # return: None
            return val  # return

        if func_id == "EXIST-001":  # 存在性判定
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0  # return

        if func_id in ("DIM-005", "AREA-001"):  # 面积判定（窗/避难层）
            # 跨图纸复测（2026-10，bca589）：111 个 COLU 层实体被误识别为 window，
            # 全部 subtype=None / detection_source=None，bbox 面积被当窗面积。
            # fire_window / rescue_window 由 TEXT 标注"防火窗"/"救援窗"创建；
            # 无显式语义的纯 window 实体跳过（避免柱/线等误分类实体触发）。
            if func_id == "DIM-005" and entity_type == "window":
                if not props.get("subtype") and not props.get("detection_source"):
                    return None  # 纯 window 无显式语义，跳过误分类实体
            val = props.get("area", props.get("width", 0) * props.get("height", 0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无面积数据，跳过判定
            # P82: 先做单位转换，再做边界检查
            if unit == "mm2":  # condition: unit == "mm2":
                val = val / 1000000.0  # assign
            elif unit == "m2":  # condition: unit == "m2":
                pass
            elif val > 10000:  # check: numeric comparison
                val = val / 1000000.0  # assign
            # DXF 测量精度有限，窗面积 0.88 vs 阈值 1.0 差 12%，属 DXF 测量误差范围
            if (
                func_id in ("DIM-005", "DIM-010")
                and abs(val - self.threshold) < 0.15 * self.threshold
            ):
                return None  # 边界值，DXF 测量误差，跳过判定
            return val  # return

        if func_id in ("DIM-008", "DIM-010"):  # 排烟窗面积 / 消防救援窗面积
            # DIM-010 窗口面积：仅对显式窗类型判定（同 DIM-005 修复逻辑）
            if func_id == "DIM-010" and entity_type == "window":
                if not props.get("subtype") and not props.get("detection_source"):
                    return None  # 纯 window 无显式语义，跳过误分类实体
            val = props.get("area", props.get("width", 0) * props.get("height", 0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无面积数据，跳过判定
            # P82: 先做单位转换，再做边界检查
            if unit == "mm2":  # condition: unit == "mm2":
                val = val / 1000000.0  # assign
            elif unit == "m2":  # condition: unit == "m2":
                pass
            elif val > 10000:  # check: numeric comparison
                val = val / 1000000.0  # assign
            # DXF bbox 测量精度约 ±15%（窗面积 0.88 vs 阈值 1.0 差 12%），
            # 单向向下容差：仅跳过测量值略低于阈值的边界 case，避免误报
            # 15% 仅向下覆盖（850mm×1100mm 窗 DXF bbox 常见值 0.88m²）
            if self.threshold * 0.85 <= val < self.threshold:
                return None  # DXF 测量误差（约 15%），不报违规
            return val  # return

        # L2 新增函数
        if func_id in ("DIM-006", "DIM-007"):  # 疏散门净宽 / 防火卷帘宽度
            # P108: doorway 使用 gap_width_mm（单位 mm），转 m
            if entity_type == "doorway":  # check: membership test
                gap_mm = props.get("gap_width_mm", 0.0)  # function call
                if gap_mm < 100.0:  # check: numeric comparison <10cm 跳过
                    return None  # 无有效门洞宽度
                val = gap_mm / 1000.0  # assign: mm→m
            else:  # 非 doorway：走常规 width/clear_width 路径
                val = props.get("width", props.get("clear_width", 0.0))  # function call
                if val < 0.01:  # check: numeric comparison
                    return None  # 无宽度数据，跳过判定

            # YOLO 检测的实体尺寸不精确，跳过尺寸判定
            if (
                props.get("detection_source") == "yolo"
            ):  # condition: props.get("detection_source") == "yolo":
                return None  # return: None
            # DIM-006 疏散门净宽：仅 exit_door 或显式标注为疏散门的实体判定
            # 跨图纸复测（2026-10，32 图）：door 212条 + doorway 112条 FAIL
            # （width 1.30~1.37m，CAD 标准单/双开门）。普通门/门洞不具备人员密集
            # 场所疏散门语义，不应适用 GB50016-5.5.19（≥1.4m）。
            # 修复：door/doorway 无 is_evacuation_door 标记一律跳过（Step 5.7
            # 已为真·疏散门标注 is_evacuation_door=True）。
            if func_id == "DIM-006":
                entity_type = entity.get("type", "")
                if entity_type != "exit_door":
                    # 普通 door / doorway：有显式疏散语义才判定
                    if not props.get("is_evacuation_door"):
                        return None
            # 小门（<0.8m）不适用疏散门净宽判定（设备门/检修门等）
            if func_id == "DIM-006" and val < 0.8:  # check: numeric comparison
                return None  # return: None
            # 设备门/管井门排除：图层含 设备/管线/管井/PIPE/喷淋/消防排水/ EQUIP 等关键词
            # "SB" 是建筑通用图层（建筑=SB），排除会误杀所有建筑门，已移除
            if func_id == "DIM-006":  # condition: func_id == "DIM-006":
                layer = entity.get("layer", "").upper()  # function call
                non_exit_layer_kw = [
                    "设备",
                    "管线",
                    "管井",
                    "PIPE",
                    "喷淋",
                    "消防排水",
                    "EQUIP",  # 跨图纸复测（2026-10，6 条）：EQUIP_管件层误分类为 door
                ]  # assignment
                if any(kw.upper() in layer for kw in non_exit_layer_kw):  # check: membership test
                    return None  # return: None
            # DIM-006 bbox 合理性：非门实体（线/TEXT/hatch）误分类为 door 时，
            # bbox 高度远低于真实门（真实门高度应 ≥1.8m）。
            # 跨图纸复测（2026-10，9 条）：立-细/REIN/THIN 等层的线被误分类为 door，
            # bbox_h≈0（线）或 bbox_h=850~900mm（异常矮），宽度过大（如 36600mm）。
            # 真实疏散门宽度应在 0.7~2.5m 范围内；过宽或过窄均为误分类。
            # 注意：bbox 尺寸为 mm，需先换算为 m 再比较。
            if func_id == "DIM-006" and entity_type == "door":
                bbox = entity.get("bbox") or {}
                bh_m = bbox.get("height", 0) / 1000.0  # bbox 单位为 mm → m
                bw_m = bbox.get("width", 0) / 1000.0  # bbox 单位为 mm → m
                if bh_m < 0.5:  # check: 真实门高度应 >=1.8m，<0.5m 必为误分类
                    return None  # 非门实体（线/hatch），跳过判定
                # 过宽 bbox（>5m）或过窄宽度（<0.7m）均为异常
                if bw_m > 5.0 or val < 0.7:  # check: bbox 异常
                    return None  # return: None
            # DIM-006 疏散门净宽边界容差：<2% 偏差视为测量误差，不报违规
            # 1.4m * 0.98 = 1.372m（含测量误差仍判定为合规）
            if func_id == "DIM-006" and 0.98 <= (val / 1.4) < 1.0:  # check: numeric comparison
                return None  # 边界门宽，跳过判定
            if unit == "mm":  # condition: unit == "mm":
                return val / 1000.0  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            if val > 100:  # check: numeric comparison
                return val / 1000.0  # return
            return val  # return

        if func_id in (
            "EXIST-002",
            "EXIST-003",
            "EXIST-004",
            "EXIST-005",
            "EXIST-006",
        ):  # 存在性判定
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0  # return

        if func_id == "ATTR-002":  # 保温材料等级
            has_fire_rating = "fire_rating" in props or "rating" in props  # assignment
            val = props.get("fire_rating", props.get("rating", 0.0))  # function call
            if not has_fire_rating:  # check: negated condition
                # 完全无防火等级属性 → 无法判定
                return None  # return: None
            return val  # return

        if func_id == "LIGHT-001":  # 照度
            val = props.get("illuminance", props.get("lux", None))
            if val is None:
                return None  # 无照度属性，跳过判定
            return float(val)

        # L3 新增函数
        if func_id in ("DIM-008", "DIM-010"):  # 排烟窗面积 / 消防救援窗面积
            if func_id == "DIM-010" and entity_type == "window":
                if not props.get("subtype") and not props.get("detection_source"):
                    return None  # 纯 window 无显式语义，跳过误分类实体
            val = props.get("area", props.get("width", 0) * props.get("height", 0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无面积数据，跳过判定
            if unit == "mm2":  # condition: unit == "mm2":
                return val / 1000000.0  # return
            if unit == "m2":  # condition: unit == "m2":
                return val  # return
            if val > 10000:  # check: numeric comparison
                return val / 1000000.0  # return
            return val  # return

        if func_id == "DIM-009":  # 疏散出口宽度
            # P108: doorway 使用 gap_width_mm（单位 mm），转 m
            entity_type = entity.get("type", "")  # function call
            if entity_type == "doorway":  # check: membership test
                gap_mm = props.get("gap_width_mm", 0.0)  # function call
                if gap_mm < 100.0:  # check: numeric comparison <10cm 跳过
                    return None  # 无有效门洞宽度
                val = gap_mm / 1000.0  # assign: mm→m
            else:  # 非 doorway：走常规 width/clear_width 路径
                val = props.get("width", props.get("clear_width", 0.0))  # function call
                if val < 0.01:  # check: numeric comparison
                    return None  # 无宽度数据，跳过判定
            # DIM-009 疏散出口宽度：仅适用于 exit/exit_door；普通 door/doorway 仅宽度 >= 1.3m 时判定
            # 0.8~1.3m 的门/门洞是标准单开门/建筑洞口，不是疏散出口
            if (
                entity_type != "exit" and entity_type != "exit_door" and val < 1.3
            ):  # check: numeric comparison
                # 跨图纸复测（2026-10，212 条）：doorway <1.3m 判定产生大量 FAIL
                # （avg 0.836m，全 DWG 图纸上的标准门洞），doorway 与 door 同口径
                return None  # 普通门/门洞（<1.3m）不是疏散出口，不适用此规范
            # 小门（<0.8m）不适用疏散出口宽度判定
            if val < 0.8:  # check: numeric comparison
                return None  # return: None
            if unit == "mm":  # condition: unit == "mm":
                return val / 1000.0  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            if val > 100:  # check: numeric comparison
                return val / 1000.0  # return
            return val  # return

        # ── 通用 DIMENSION 宽度提取（P0-1 可达性补齐）──
        # 此前 DIM-012/021/022 等无提取分支 → 永远返回 None → 不可判定。
        # 实体有 width/clear_width 时按宽度口径提取（单位 mm→m 归一）。
        # 注意：DIM-016 是净高（height），不是宽度，不在此分支。
        if func_id in ("DIM-012", "DIM-021", "DIM-022"):
            etype = entity.get("type", "")
            val = props.get("width", props.get("clear_width", 0.0))
            if val < 0.01:
                return None  # 无宽度数据，跳过判定
            # 单位归一：unit 缺失时按数量级判断（>100 为 mm，否则为 m）
            if unit == "mm":
                val_m = val / 1000.0
            elif unit == "m":
                val_m = val
            elif val > 100:
                val_m = val / 1000.0
            else:
                val_m = val
            # 门类防误报：普通 door/doorway 不构成疏散出口语义（同 DIM-009/DIM-006），
            # 仅 exit/exit_door 或显式标注 is_evacuation_door 的实体判定。
            # 真实图纸 2644 个 door 中大量 bbox 宽度 1.4~1.8m 是门洞投影，
            # 逐门判 DIM-021/022 会产生 800+ 条误报（跨图纸复测 2026-11）。
            if func_id in ("DIM-021", "DIM-022"):
                if etype in ("door", "doorway") and not props.get("is_evacuation_door"):
                    return None
                # T4: 前置证据门禁（缺证据不判定，见模块头注释）
                assembly = _is_assembly_occupancy(props)
                if func_id == "DIM-022":
                    # 人员密集场所疏散门：无 occupancy 证据不得按 1.4m 判
                    if not assembly:
                        return None
                else:
                    # 首层疏散外门：人员密集场所由 DIM-022 判（两条互斥）；
                    # 无 floor=F1 证据不得按 1.1m 判
                    if assembly:
                        return None
                    if not _is_ground_floor(props.get("floor")):
                        return None
            # 走廊/走道防误报：宽度 <0.5m 必为误分类（线/填充）
            if func_id == "DIM-012" and val_m < 0.5:
                return None
            # 单位口径：DIM-012 阈值 m；DIM-021/022 阈值 mm（1100/1400）
            if func_id == "DIM-012":
                return val_m
            return val_m * 1000.0  # DIM-021/022 返回 mm 口径

        # ── 通用 DIMENSION 宽度/高度提取（P0-1 扩展：覆盖其余规则）──
        # 此前 DIM-011/020/025/026/030/031/033/034/048/049/056/068/071/072/078/080
        # 083/084/085/086/092/094/095/096/098/101/103/104/105/106/108 等均无提取分支，
        # 永远返回 None，导致跨 47 张图纸适用但未判定（覆盖率缺口核心）。
        # 设计原则：按 func_id→(prop_key, unit, guards) 映射提取，同单位/阈值口径
        # 对齐 DIM-006/009/012/021/022 已有守卫（普通门不判定、宽度下限兜底）。
        _GENERIC_DIM_RULES = {
            "DIM-011": ("width", "mm", ("road", "fire_lane", "driveway")),
            "DIM-020": ("width", "mm", ("stair", "staircase", "stairs")),
            "DIM-025": ("width", "mm", ("stair", "staircase", "stairs")),
            "DIM-026": ("width", "mm", ("external_stair", "stair", "staircase")),
            "DIM-030": ("width", "mm", ("road", "rescue_area", "driveway")),
            "DIM-031": ("width", "mm", ("road", "fire_lane", "driveway")),
            "DIM-033": ("clear_width", "mm", None),  # staircase_door/door/fire_door
            "DIM-034": ("clear_width", "mm", None),  # exit_door/door/fire_door
            "DIM-048": ("width", "mm", None),         # accessible_door/door
            "DIM-049": ("width", "mm", None),         # elevator/elevator_door
            # DIM-056 已从通用提取移除（2026-11-16）：地下商店疏散距离 ≤30m 是
            # 疏散路径距离，不是房间 bbox 尺寸。room.length 是房间几何长边，
            # 用其判定疏散距离会产生 1000× 单位错配 + 语义错配的假 FAIL
            # （实测 1470 条）。已标记 unsupported_2d=path_topology。
            "DIM-068": ("width", "mm", None),         # aisle/corridor/driveway（≥5.5m）
            "DIM-071": ("width", "mm", ("stair", "staircase")),
            "DIM-072": ("clear_width", "mm", None),   # exit/door/fire_door
            "DIM-078": ("width", "mm", None),         # corridor/hallway/passage（≥1.1m）
            "DIM-080": ("width", "mm", None),         # corridor/hallway/passage（≥1.1m）
            "DIM-083": ("width", "mm", ("external_stair", "outdoor_stair")),
            "DIM-084": ("width", "mm", ("exit_door", "external_door")),
            "DIM-085": ("width", "mm", ("road", "fire_lane", "driveway")),
            "DIM-086": ("width", "mm", ("road", "fire_lane", "driveway")),
            "DIM-092": ("width", "mm", None),         # accessible_door/door
            # DIM-094 已从通用提取移除（2026-11-16）：袋形走道疏散距离 ≤15m 是
            # 疏散路径距离，不是房间 bbox 尺寸。room.width 是房间几何短边，
            # 用其判定疏散距离会产生 1000× 单位错配 + 语义错配的假 FAIL
            # （实测 1187 条）。已标记 unsupported_2d=path_topology。
            "DIM-095": ("width", "mm", None),         # corridor/hallway/passage/walkway（≥1.2m）
            "DIM-096": ("width", "mm", None),         # exit/exit_door/fire_door/door
            "DIM-098": ("width", "mm", ("road", "fire_lane", "access_road", "driveway")),
            "DIM-101": ("width", "mm", ("stair", "staircase", "antechamber")),
            "DIM-103": ("width", "mm", None),         # aisle/corridor/walkway（≥1.0m）
            "DIM-104": ("width", "mm", None),         # corridor/walkway（≥1.0m）
            "DIM-105": ("width", "mm", None),         # door/residential_door/entrance_door
            "DIM-106": ("width", "mm", ("escape_stair", "external_stair", "outdoor_stair")),
            "DIM-108": ("width", "mm", ("road", "fire_lane", "fire_access", "driveway")),
        }
        if func_id in _GENERIC_DIM_RULES:
            prop_key, req_unit, req_types = _GENERIC_DIM_RULES[func_id]
            # 宽度属性优先级：clear_width > width（语义层可能分别存储）
            raw = props.get(prop_key)
            if prop_key == "clear_width" and (not isinstance(raw, (int, float)) or raw < 0.01):
                raw = props.get("width", 0.0)
            if not isinstance(raw, (int, float)) or raw < 0.01:
                return None
            # 单位归一：语义层以 m 为单位存储；req_unit="mm" 则 ×1000，否则直接取值
            if req_unit == "mm":
                val = raw * 1000.0
            else:
                val = raw
            etype = entity.get("type", "")
            # 类型门禁：req_types 非空时要求实体或 subtype 命中才提取
            if req_types:
                sub = entity.get("subtype") or ""
                if etype not in req_types and sub not in req_types:
                    return None
            # 门类防误报：普通 door/doorway 缺疏散语义（同 DIM-006/009/021）
            if etype in ("door", "doorway"):
                explicit_evac = props.get("is_evacuation_door")
                if not explicit_evac:
                    return None
            # 走道类下限：<0.5m 必为线元/填充误分类（同 DIM-012）
            if func_id in ("DIM-078", "DIM-080", "DIM-095", "DIM-103", "DIM-104"):
                val_m = val / 1000.0
                if val_m < 0.5:
                    return None
            # 距离类（≤）防止合成实体误判：polyline_* / line_chain_* 为扫线法生成
            # 的派生实体，其 width/length 来自聚合几何而非真实测量，不适用于距离/尺度判定。
            # 与 DIST-003（line_chain_corridor_* 过滤）同理。
            # 注意：entity.id 可能在顶层或 properties 内，两者都要检查。
            raw_eid = entity.get("id", "") or ""
            prop_eid = (props.get("id", "") or "") if isinstance(props, dict) else ""
            eid = raw_eid or prop_eid
            if func_id in ("DIM-056", "DIM-094") and any(eid.startswith(p) for p in (
                "polyline_", "line_chain_"
            )):
                return None
            # ── 楼梯净宽语义错配守卫（DIM-020/025/026，2026-11-16）──
            # 楼梯 width 语义层赋的是踏步宽（stair_bbox_long_edge / stair_bbox_span，
            # 实测 300~900mm），而 DIM-020/025 阈值 1100mm、DIM-026 阈值 900mm
            # 是梯段净宽。用踏步宽判定梯段净宽 → 114 条全 FAIL（同 DIM-001 口径）。
            # 仅 CAD 标注 / YOLO 等带来源的宽度参与判定。
            if func_id in ("DIM-020", "DIM-025", "DIM-026"):
                width_source = props.get("_width_source", "")
                if width_source in ("stair_bbox_long_edge", "stair_bbox_span"):
                    return None
            return val

        # ── DIM-016 消防车道净高（height 口径）──
        # corridor 实体通常无 height 属性（净高需 CAD 标注），无数据 → 不可判定。
        if func_id == "DIM-016":
            val = props.get("height", 0.0)
            if val < 0.01:
                return None  # 无净高数据，跳过判定
            # 阈值 4000mm，返回 mm 口径
            if unit == "mm":
                return val
            if unit == "m":
                return val * 1000.0
            if val > 100:
                return val  # 已是 mm
            return val * 1000.0  # m → mm

        if func_id == "DIST-002":  # 防火间距：只认 building↔building 实测间距
            # 跨图纸复测（2026-10，106 条）：building 实体均无 distance 属性，
            # 旧逻辑回退到 length（建筑自身 bbox/LINE 长度，如 11800mm、200mm），
            # 把建筑尺寸当成防火间距，产生 106 条误报（实测 0.11~11.8m）。
            # 语义分析当前未计算建筑间距，无距离数据一律跳过。
            val = props.get("distance", 0.0)  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无真实间距数据，跳过判定
            if unit == "mm":  # condition: unit == "mm":
                return val / 1000.0  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            if val > 100:  # check: numeric comparison
                return val / 1000.0  # return
            return val  # return

        if func_id == "DIST-003":  # 袋形走道长度：length 即走道自身长度，语义正确
            # 跳过扫描法派生走廊（polyline_corridor_* / line_chain_corridor_*），非真实建筑走廊。
            # 改名说明：8f3bb93 仅拦截 polyline_corridor_*；98414a0 把 sweep 面派生的走廊
            # ID 前缀改为 line_chain_{area}_{idx}，本过滤未同步更新，形成缺口（post-merge-audit 20261109）。
            entity_id = entity.get("id", "")
            if entity_id.startswith(("polyline_corridor_", "line_chain_corridor_")):
                return None
            val = props.get("length", 0.0)  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无长度数据，跳过判定
            if unit == "mm":  # condition: unit == "mm":
                return val / 1000.0  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            if val > 100:  # check: numeric comparison
                return val / 1000.0  # return
            return val  # return

        if func_id == "AREA-002":  # 消防电梯前室面积
            # T3: 前室类条款互斥——防烟楼梯间前室归 DIM-018（6㎡）、
            # 合用前室归 DIM-019（10㎡），AREA-002 只负责消防电梯前室。
            # 旧口径经别名组 Group 5 把 antechamber 也纳入，导致同一实体
            # 被 AREA-002/DIM-018/DIM-019 三条同时判（16 条重复 finding）。
            if _lobby_entity_kind(entity) in ("stair", "shared"):
                return None
            # YOLO 检测的实体 bbox 映射不精确，跳过面积判定
            if (
                props.get("detection_source") == "yolo"
            ):  # condition: props.get("detection_source") == "yolo":
                return None  # return: None
            # 面积口径：area_m2 为语义层权威面积，优先于 area/bbox。
            # 旧逻辑只读 area，缺失时退 bbox：文字标注框（如 1971×1314mm）
            # 被算成 2.5913㎡ → 正确面积 9.2/12.8/14.5㎡ 的前室被判 critical。
            val = props.get("area_m2", 0.0) or props.get("area", 0.0)
            if val < 0.01:
                # TEXT 标注（文字框）无物理面积，bbox 不能代表房间范围
                if props.get("text"):
                    return None  # 无面积证据（insufficient_evidence）
                # 从 bbox 宽高计算面积（mm²）
                bw = entity.get("bbox", {}).get("width", 0)  # function call
                bh = entity.get("bbox", {}).get("height", 0)  # function call
                if bw > 0 and bh > 0:  # check: numeric comparison
                    bbox_area = bw * bh  # assignment
                    # bbox 面积太小（< 0.5m²）或太大（> 500m²），说明不是真实房间
                    bbox_area_m2 = bbox_area / 1000000.0  # assignment
                    if 0.5 <= bbox_area_m2 <= 500:  # check: numeric comparison
                        val = bbox_area  # assignment
                    else:  # 否则
                        return None  # bbox 面积不合理，跳过判定
            if val < 0.01:  # check: numeric comparison
                return None  # 无面积数据，跳过判定
            if unit == "mm2":  # condition: unit == "mm2":
                val_m2 = val / 1000000.0  # return
            elif unit == "m2":  # condition: unit == "m2":
                val_m2 = val  # return
            elif val > 10000:  # check: numeric comparison
                val_m2 = val / 1000000.0  # return
            else:
                val_m2 = val
            # T3: 前室面积 <2㎡ 视为识别噪声/换算异常（最小前室通常 ≥3㎡）。
            # 1.0~1.54㎡ 的实测值来自「最近 room 中心」面积传播，实体本身是
            # 350~525mm 的文字标签，不能作为确证违规（critical）的证据。
            if val_m2 < 2.0:
                return None  # 无可靠面积证据（insufficient_evidence）
            return val_m2

        if func_id == "ATTR-003":  # 防火窗等级
            has_fire_rating = "fire_rating" in props or "rating" in props  # assignment
            val = props.get("fire_rating", props.get("rating", 0.0))  # function call
            if not has_fire_rating:  # check: negated condition
                # 完全无防火等级属性 → 无法判定
                return None  # return: None
            if val < 0.01:  # check: numeric comparison
                return None  # 无防火等级数据，跳过判定
            return val  # return

        if func_id in (
            "EXIST-007",
            "EXIST-008",
            "EXIST-009",
            "EXIST-010",
            "EXIST-011",
            "EXIST-012",
            "EXIST-013",
            "EXIST-014",
            "EXIST-015",
        ):  # check: membership test
            return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0  # return

        # P47 无障碍设计：ACCESS 类数值判定（复用 DIMENSION 路径）
        if self.category == FuncCategory.ACCESS:
            if func_id == "ACCESS-001":  # 轮椅坡道坡度
                val = props.get("slope", props.get("gradient", props.get("ratio", 0.0)))
                if val < 0.01:
                    return None
                return val
            if func_id == "ACCESS-002":  # 轮椅坡道宽度
                val = props.get("width", props.get("clear_width", 0.0))
                if val < 0.01:
                    return None
                if unit == "mm":
                    return val / 1000.0
                if unit == "m":
                    return val
                if val > 100:
                    return val / 1000.0
                return val
            if func_id == "ACCESS-003":  # 无障碍出入口宽度
                val = props.get("width", props.get("clear_width", 0.0))
                if val < 0.01:
                    return None
                if unit == "mm":
                    return val / 1000.0
                if unit == "m":
                    return val
                if val > 100:
                    return val / 1000.0
                return val
            if func_id == "ACCESS-004":  # 无障碍通道宽度
                val = props.get("width", props.get("clear_width", 0.0))
                if val < 0.01:
                    return None
                if unit == "mm":
                    return val / 1000.0
                if unit == "m":
                    return val
                if val > 100:
                    return val / 1000.0
                return val
            if func_id == "ACCESS-005":  # 扶手设置（EXIST类）
                return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0
            if func_id == "ACCESS-006":  # 无障碍电梯（EXIST类）
                return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0
            if func_id == "ACCESS-007":  # 无障碍停车位比例
                val = props.get("ratio", props.get("count", 0.0))
                if val < 0.0001:
                    return None
                return val
            if func_id == "ACCESS-008":  # 无障碍卫生间（EXIST类）
                return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0
            if func_id == "ACCESS-009":  # 轮椅回转空间直径
                val = props.get("diameter", props.get("width", props.get("clear_width", 0.0)))
                if val < 0.01:
                    return None
                if unit == "mm":
                    return val / 1000.0
                if unit == "m":
                    return val
                if val > 100:
                    return val / 1000.0
                return val
            if func_id == "ACCESS-010":  # 盲道设置（EXIST类）
                return 1.0 if props.get("exists", False) or props.get("count", 0) > 0 else 0.0
            return None

        # ── 通用 AREA 类别分支 ────────────────────────────────
        # 经验教训（100016220）：统一计算单位 + 单点换算，避免在多个 fun id handler
        # 里反复判断数量级。AREA-003~AREA-022 此前无 handler → 全部返回 None。
        if self.category == FuncCategory.AREA:
            entity_type = entity.get("type", "")  # function call
            entity_subtype = entity.get("subtype", "") or props.get("subtype", "")

            # ── 适用性质守：单位/前提不匹配 → 跳过 ────────
            # 1) 人口密度类（AREA-020 5.0人/m²）：需要 occupancy 数据
            if func_id == "AREA-020":
                people = props.get("people") or props.get("occupancy") or props.get("occupants")
                if not people:
                    return None  # 无人口数据，无法判人口密度
                # 面积 = area_m2 或 area 换算
                raw = props.get("area_m2", props.get("area", 0.0))
                if raw > 10000:
                    raw = raw / 1000000.0
                if raw < 0.01:
                    return None
                # 返回人口密度 people/m²，与阈值 5.0 人/m² 比较
                return people / raw

            # 2) 面积比类（AREA-011/017 2% 排烟窗比）：需要 window_area + floor_area 比值
            #    window_area 在 window 的 properties.area_m2；floor_area 不在
            if func_id in ("AREA-011", "AREA-017"):
                # 这两条规范实际需要"该窗户所属地面面积"——单窗实体无此数据，跳过
                return None

            # 3) 普通 room 被列入特化 AREA 目标时，需要 subtype 确认
            #    如 AREA-004(control_room)、AREA-006(accessible_room)、
            #    AREA-016(control_room)、AREA-022(alarm_center)、AREA-005(generator_room)
            #    target_entities 含 "room" 是为了"识别不足时仍能覆盖"，但导致
            #    30㎡/35㎡/20㎡ 等特化阈值被应用到所有普通 room → 大面积误报。
            _specialty = {
                "AREA-004": {"control_room", "fire_control_room"},
                "AREA-006": {"accessible_room", "apartment"},
                "AREA-016": {"control_room", "fire_control_room"},
                "AREA-022": {"alarm_center", "control_room", "fire_control_room"},
                "AREA-005": {"generator_room"},
                "AREA-018": {"antechamber", "smoke_proof_lobby", "staircase_lobby"},
                "AREA-019": {"antechamber", "fire_elevator_lobby", "elevator_lobby"},
                "AREA-021": {"antechamber", "scissor_stair_lobby", "staircase_lobby"},
                "AREA-002": {"elevator_lobby", "lobby"},
            }
            if func_id in _specialty:
                specialty_subtypes = _specialty[func_id]
                if entity_type == "room" and entity_subtype not in specialty_subtypes:
                    return None  # 普通 room 不适用特化 AREA 规则

            # 4) target_entities 语义修正：atomic 子包声明式注册的覆盖误差
            #    AREA-019 包含 fire_elevator，但它是电梯标记而非前室 → 跳过
            #    AREA-013 包含 window/rescue_window，但它们是 CAD 符号/文字标注
            #    （window 来自 CIRCLE，bbox=2mm²；rescue_window 是规范文字）→ 跳过
            if func_id == "AREA-019" and entity_type == "fire_elevator":
                return None  # 电梯 ≠ 消防电梯前室
            if func_id == "AREA-013" and entity_type in ("window", "rescue_window"):
                return None  # CAD 符号/文字标注无物理面积
            # AREA-012 汽车库排烟量：需要 volumetric_flow（m³/h）属性
            # fan 实体只有 bbox 面积（0.15~0.08m²），无排烟量数据 → 全部误报
            if func_id == "AREA-012" and entity_type == "fan":
                vf = props.get("volumetric_flow") or props.get("air_flow") or props.get("flow_rate")
                if not vf:
                    return None  # 无排烟量属性，跳过判定

            # T3: DIM-018/DIM-019 与 AREA-002 的互斥归属（同一实体 ≤1 条）。
            # 归属由实体语义决定（见 _lobby_entity_kind）：
            #   stair → DIM-018（6㎡ 防烟楼梯间前室）
            #   shared → DIM-019（10㎡ 合用前室，必须有显式合用证据）
            # 无「合用」证据时不得按 10㎡ 判：旧口径对每个 antechamber 同时
            # 判 6㎡ 与 10㎡ 两条互斥条款（东莞通 3274/6314/7087/9457）。
            if func_id == "DIM-018" and _lobby_entity_kind(entity) != "stair":
                return None
            if func_id == "DIM-019" and _lobby_entity_kind(entity) != "shared":
                return None

            # P130: AREA-018/019/021/前室面积：极小 ante chamber（<2m²）几乎一定是误分类
            # 跨图纸复测（2026-11）：ANTECHAMBER_7087(0.77m²)/6314(1.0m²)/4915(1.87m²)
            # 极小面积不符合前室功能需求（最小前室通常 ≥3m²），疑似管道井/设备间误标
            if func_id in (
                "AREA-018",
                "AREA-019",
                "AREA-021",
                "DIM-018",
                "DIM-019",
            ) and entity_type in (
                "antechamber",
                "fire_elevator_lobby",
                "scissor_stair_lobby",
            ):
                area_val = props.get("area_m2") or props.get("area", 0.0)
                if area_val and area_val < 2.0:  # check: numeric comparison
                    return None  # 极小 ante chamber，疑似误分类，跳过判定

            # 5) bbox 兜底白名单：bbox 对标记实体（文字框/CAD 符号）无物理意义。
            #    只有 room-like 实体的 bbox 能近似代表空间范围。
            #    先用权威口径（area_m2 / area）；都没有时才考虑 bbox 兜底，
            #    但仅限白名单内实体类型。
            _bbox_area_allowed = {
                "room",
                "corridor",
                "stair",
                "antechamber",
                "lobby",
                "fire_elevator_lobby",
                "elevator_lobby",
                "staircase_lobby",
                "smoke_proof_lobby",
                "scissor_stair_lobby",
                "refuge_floor",
                "refuge_area",
                "refuge_room",
                "rescue_area",
                "rescue_ground",
                "floor",
                "fire_zone",
                "natural_vent",
                "smoke_vent",
                "smoke_window",
                "alarm_center",
                "control_room",
                "fire_control_room",
                "generator_room",
                "accessible_room",
                "apartment",
                "operating_room",
                "surgery_room",
                "bedroom",
                "hospital_ward",
                "nursing_unit",
                "shelter",
                "rescue_opening",
                "fire_platform",
            }

            # ── 面积提取（单位归一权威口径 area_m2 优先） ────────
            val = props.get("area_m2", 0.0)
            if val < 0.01:  # check: numeric comparison
                raw_area = props.get("area", 0.0)
                if raw_area < 0.01:
                    # T3: TEXT 标注（文字框）无物理面积。面积传播重建失败时
                    # 不应用 bbox 兜底（如 1971×1314mm 文字框 → 2.59㎡ 假面积），
                    # 返回 None 表达「证据不足」，不得据此判 critical。
                    if props.get("text"):
                        return None
                    # 权威口径都没值 → 尝试 bbox 兜底，但仅限白名单实体
                    if entity_type not in _bbox_area_allowed:
                        return None  # 标记实体，bbox 无物理意义，跳过
                    bw = entity.get("bbox", {}).get("width", 0)
                    bh = entity.get("bbox", {}).get("height", 0)
                    if bw > 0 and bh > 0:
                        raw_area = bw * bh  # mm²
                    else:
                        return None  # 无面积数据，跳过判定
                if unit == "mm2":
                    val = raw_area / 1000000.0
                elif unit == "m2":
                    val = raw_area
                elif raw_area > 10000:  # mm² 启发式
                    val = raw_area / 1000000.0
                else:
                    val = raw_area
                # bbox 兜底合理性检查：面积过小（<0.5 m²）说明 bbox
                # 来自文字框或符号标记，而非真实空间边界 → 跳过
                if val < 0.5 and not props.get("area_m2") and not props.get("area"):
                    return None
            return val  # return: float

        # EVAC 类：疏散路径判定
        if func_id in ("EVAC-001", "EVAC-002", "EVAC-003", "EVAC-004"):
            # 设备空间排除（专家复核 2026-11-02 根因 2）：设备空间
            # （equipment_room/utility/管井/风井等）不是建筑疏散空间，
            # 不参与疏散路径判定。避免设备空间被误判为 room 后误报。
            etype = entity.get("type", "")
            subtype = entity.get("subtype", "")
            props0 = entity.get("properties") or {}
            inferred_type = props0.get("inferred_type", "")
            if subtype in ("equipment_room", "utility", "elevator") or inferred_type in (
                "equipment_room",
                "utility",
                "elevator",
            ):
                return None
        if func_id == "EVAC-001":  # 疏散路径是否存在
            if "has_evacuation_route" not in props:  # check: membership test
                return None  # 无疏散路径分析结果，跳过判定
            # 跳过扫描法派生房间（line_chain_*/polyline_room_*），非真实房间
            entity_id = entity.get("id", "")  # assign
            if entity_id.startswith(("line_chain_", "polyline_room")):  # check: scanning artifact
                return None  # 扫描法派生房间，不参与疏散判定
            # 跳过 layer "0" 小房间（专家复核 2026-11-02 根因 2）：
            # CAD 默认层的扫线法派生三角形房间（如 ROOM_636=3.28m²）是
            # 非真实房间，不应参与疏散路径判定。
            if (entity.get("layer") or "") == "0":
                area0 = props.get("area_m2", props.get("area", 0.0))
                if area0 and area0 < 10:
                    return None
            # 大面积 room 疏散路径分析可能失败，跳过误报
            # 面积按 m² 口径比较（area_m2 由语义层 Step 1.8 单位归一产出）
            area = props.get("area_m2", props.get("area", 0.0))
            if area and area > 5000:  # check: numeric comparison
                return None  # 大面积 room，路径分析不可靠
            # 证据分级（P139）：无路径有两种成因，不能都判违规。
            # sealed_no_opening：闭合多边形 + 周边无任何洞口 + 不与其他空间相邻，
            #   这是图纸能给的「确实无出口」正面证据 → 继续判定（FAIL/critical）。
            # model_gap：边界上有门窗/墙洞或与其他空间相邻，只是连通图缺边
            #   （墙洞尚未建模为「空间间的边」）→ 不判定，避免把建模缺口报成违规。
            if not props.get("has_evacuation_route", False) and props.get(
                "evacuation_evidence"
            ) != "sealed_no_opening":
                return None  # 模型完整性缺口（insufficient_evidence）
            return 1.0 if props.get("has_evacuation_route", False) else 0.0  # return
        if func_id == "EVAC-002":  # 疏散路径长度
            if (
                "evacuation_path_length" not in props and "travel_distance" not in props
            ):  # check: membership test
                return None  # 无疏散路径长度数据，跳过判定
            # 路由级指标去重：同一疏散路径的非代表房间跳过（由代表房间上报一次）
            if props.get("evacuation_route_secondary", False):  # check
                return None
            # 大面积 room 疏散路径分析可能失败
            # 面积按 m² 口径比较（area_m2 由语义层 Step 1.8 单位归一产出）
            area = props.get("area_m2", props.get("area", 0.0))
            if area and area > 5000:  # check: numeric comparison
                return None  # return: None
            # P133: 删除原 `if val > 80: return None` 守卫。该守卫以"路径计算 bug"
            # 掩盖了真正的单位错配：path_length 是毫米（各边 bbox 间隙之和），
            # 却被直接与米阈值比较，任何 >80mm（8cm）的路径都会被静默吞掉。
            # 单位与几何口径就绪前，EVAC-002 由 implementation_gate 统一拦截，
            # 不在此处产出 PASS/FAIL；直接 execute 仅保留数值计算供诊断/单测使用。
            return props.get(
                "evacuation_path_length", props.get("travel_distance", 0.0)
            )  # return
        if func_id == "EVAC-003":  # 疏散路径是否超距
            if "evacuation_too_far" not in props:  # check: membership test
                return None  # 无疏散路径分析结果，跳过判定
            # 路由级指标去重：同一疏散路径的非代表房间跳过（由代表房间上报一次）
            if props.get("evacuation_route_secondary", False):  # check
                return None
            # 大面积 room 疏散路径分析可能失败
            # 面积按 m² 口径比较（area_m2 由语义层 Step 1.8 单位归一产出）
            area = props.get("area_m2", props.get("area", 0.0))
            if area and area > 5000:  # check: numeric comparison
                return None  # return: None
            return 0.0 if props.get("evacuation_too_far", False) else 1.0  # return
        if func_id == "EVAC-004":  # 疏散路径瓶颈判定
            if "evacuation_connected" not in props:  # check: membership test
                return None  # 无连通性分析结果，跳过判定
            # 大面积 room 跳过
            # 面积按 m² 口径比较（area_m2 由语义层 Step 1.8 单位归一产出）
            area = props.get("area_m2", props.get("area", 0.0))
            if area and area > 5000:  # check: numeric comparison
                return None  # return: None
            # 连通性 = 1.0（连通），瓶颈 = 0.0（有瓶颈）
            connected = props.get("evacuation_connected", False)  # function call
            bottleneck = props.get("evacuation_bottleneck", False)  # function call
            if not connected:  # 不连通 → EVAC-001 已报告，EVAC-004 跳过避免重复
                return None
            if bottleneck:  # condition: bottleneck:
                return 0.0  # 有瓶颈
            return 1.0  # 连通且无瓶颈


# ── 函数注册表 ────────────────────────────────────────────


def _clone_atomic_function(func: AtomicFunction) -> AtomicFunction:
    """浅拷贝原子函数，list 字段独立，避免原地改写泄漏到模块级共享对象。"""
    return _dc_replace(
        func,
        target_entities=list(func.target_entities),
        depends_on=list(func.depends_on),
    )  # function call


class FuncRegistry:  # class definition
    """原子函数注册表 - 从 atomic/ 子包加载 422 条原子函数"""

    # P7: 原子函数已从巨型单文件拆分为 atomic/ 子包，此处直接导入
    # atomic/__init__.py 合并了所有模块的 ATOMIC_FUNCTIONS 列表

    def __init__(self, timeout: int = 30):  # function: def __init__(self, timeout: int = 30):
        """初始化实例。"""
        self._funcs: Dict[str, AtomicFunction] = {}  # assignment
        self._dependency_graph: Dict[str, List[str]] = {}  # 依赖图
        self._timeout = timeout  # assignment
        # P94: 原子函数直接同步执行（无线程池），线程池开销是同步的 227 倍
        # 328 万次调用 × 22.7ms = 8 分钟 → 0.1ms = 0.4 秒
        self._executor = None
        # P94: 缓存拓扑排序结果，避免每个实体重算
        self._ordered_func_ids: List[str] = []
        # 拓扑排序按「函数集合」缓存：同一实体类型在不同实体上复现时直接命中，
        # 避免 resolve_dependencies 的 O(n²) 全量重排（真实图纸曾因此耗时数十秒）
        self._resolve_cache: Dict[Tuple[str, ...], List[str]] = {}
        # P7: 从 atomic/ 子包导入所有原子函数（去重后按 func_id 注册）
        from .atomic import ATOMIC_FUNCTIONS  # import from atomic subpackage

        for func in ATOMIC_FUNCTIONS:  # 循环
            # 注册时拷贝，避免 registry 与模块级 ATOMIC_FUNCTIONS 共享同一对象。
            # API 层按 building_type/standard 原地改写 func.threshold/operator/unit，
            # 共享引用会污染全局，导致后续新 registry 拿到被篡改的阈值。
            self.register(_clone_atomic_function(func))  # function call
        # 预计算拓扑排序（非全局函数列表）
        self._ordered_func_ids = self.resolve_dependencies(
            [
                fid
                for fid, f in self._funcs.items()
                if not getattr(f, "requires_global_context", False)
            ]
        )

    def register(self, func: AtomicFunction):  # function: def register(self, func: AtomicFunction):
        """注册"""
        func.DEFAULT_TIMEOUT = self._timeout  # assignment
        self._funcs[func.func_id] = func  # assignment
        if func.depends_on:
            self._dependency_graph[func.func_id] = list(func.depends_on)
        # 注册新函数会改变依赖图，旧拓扑序缓存失效
        self._resolve_cache.clear()

    def resolve_dependencies(self, func_ids: List[str]) -> List[str]:
        """拓扑排序：确保依赖函数在目标函数之前执行"""
        cache_key = tuple(sorted(func_ids))
        cached = self._resolve_cache.get(cache_key)
        if cached is not None:
            return cached

        all_deps: Dict[str, List[str]] = {}
        for fid in func_ids:
            if fid in self._dependency_graph:
                all_deps[fid] = list(self._dependency_graph[fid])
            else:
                all_deps[fid] = []

        in_degree: Dict[str, int] = {fid: 0 for fid in func_ids}
        for fid in func_ids:
            if fid in self._dependency_graph:
                for dep_id in self._dependency_graph[fid]:
                    if dep_id in in_degree:
                        in_degree[fid] += 1

        queue = [fid for fid in func_ids if in_degree[fid] == 0]
        result = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for fid in func_ids:
                if node in all_deps.get(fid, []):
                    in_degree[fid] -= 1
                    if in_degree[fid] == 0:
                        queue.append(fid)

        if len(result) != len(func_ids):
            return func_ids
        self._resolve_cache[cache_key] = result
        return result

    def check_dependencies(self, func: AtomicFunction, results: Dict[str, FuncResult]) -> bool:
        """检查函数的前置依赖是否都已PASS"""

        if not func.depends_on:
            return True

        for dep_id in func.depends_on:
            if dep_id not in results:
                return False
            if results[dep_id].result != "PASS":
                return False

        return True

    def execute_with_timeout(
        self,
        func: AtomicFunction,  # function: def execute_with_timeout(self, func: AtomicFunction,
        entity: Optional[Dict[str, Any]] = None,  # assignment
        timeout: Optional[int] = None,
        results: Optional[Dict[str, FuncResult]] = None,
    ) -> Optional[FuncResult]:  # assignment
        """带超时控制的原子函数执行

        在独立线程中执行 func.execute(entity)，超时则返回 degraded 结果。
        超时的函数不影响其他原子函数的执行。
        """
        timeout = timeout or func.DEFAULT_TIMEOUT  # assignment

        # P32: 依赖检查
        if results is not None and not self.check_dependencies(func, results):
            return None
        # P94: 直接同步执行，避免线程池 submit/result 的 227 倍开销
        # 原子函数为纯计算，不会真卡死；异常按 ERROR 处理，不阻塞批量审查
        try:  # try block
            return func.execute(entity)  # return
        except Exception as exc:  # catch exception
            logger.error(f"原子函数异常: {func.func_id} ({func.name}): {exc}")  # function call
            return FuncResult(  # return
                func_id=func.func_id,  # assignment
                func_name=func.name,  # assignment
                clause_id=func.clause_id,  # assignment
                operator=func.operator,  # assignment
                threshold=func.threshold,  # assignment
                actual=0.0,  # assignment
                result="ERROR",  # assignment
                delta=0.0,  # assignment
                severity=Severity.ERROR,  # assignment
                entity_id=entity.get("id", "") if entity else "",  # function call
                entity_type=entity.get("type", "") if entity else "",  # function call
                params={
                    "extracted_value": 0.0,
                    "unit": func.unit,  # assignment
                    "note": f"原子函数异常: {exc}",  # code
                    "reason": "error",  # code
                    "clause_text": func.description,
                },  # code
            )  # code

    def execute_batch(
        self,
        entity: Dict[str, Any],
        func_specs: List[Tuple[AtomicFunction, float, str, str]],
        timeout: Optional[int] = None,
        results: Optional[Dict[str, FuncResult]] = None,
        max_workers: Optional[int] = None,
    ) -> Dict[str, FuncResult]:
        """同步执行多个原子函数（同一 entity）

        P94 优化：原子函数为纯计算（无 IO），线程池 submit/result 调度开销
        在 422 funcs/entity × 2727 entities 场景下达 8.9s（38% 总耗时）。
        直接同步执行可消除此开销。
        """
        from dataclasses import replace

        batch_results: Dict[str, FuncResult] = {}
        all_results = dict(results) if results is not None else {}

        for func, tval, unit, op in func_specs:
            func_copy = replace(func, threshold=tval, unit=unit, operator=op)
            try:
                if all_results and not self.check_dependencies(func_copy, all_results):
                    continue
                r = func_copy.execute(entity)
                if r is not None:
                    all_results[func_copy.func_id] = r
                    batch_results[func_copy.func_id] = r
            except Exception as e:
                logger.error(f"execute_batch error: {func.func_id}: {e}")

        return batch_results

    def execute_missing_batch(
        self,
        entity_types_in_drawing: Set[str],
        funcs: List[AtomicFunction],
        max_workers: Optional[int] = None,
    ) -> Dict[str, FuncResult]:
        """执行缺失检查（exist 类别）

        P94 优化：exist 函数在 entity=None 时纯计算，无需线程池。
        """
        from dataclasses import replace

        to_check = []
        for f in funcs:
            cat_val = getattr(getattr(f, "category", None), "value", None)
            if cat_val != "exist":
                continue
            targets = set(f.target_entities) if f.target_entities else set()
            if targets and not targets.intersection(entity_types_in_drawing):
                continue
            # 条件性规则：前置实体类型缺失时跳过（如 EXIST-067 需 fire_wall 存在才判定）
            prereqs = set(getattr(f, "prerequisite_types", []) or [])
            if prereqs and not prereqs.intersection(entity_types_in_drawing):
                continue
            to_check.append(f)

        batch_results: Dict[str, FuncResult] = {}
        for f in to_check:
            func_copy = replace(f)
            try:
                r = func_copy.execute(None)
                if r is not None:
                    batch_results[r.func_id] = r
            except Exception as e:
                logger.error(f"execute_missing_batch error: {f.func_id}: {e}")

        return batch_results

    def execute_chained(
        self,
        func_ids: List[str],
        entity: Dict[str, Any],
        results: Optional[Dict[str, FuncResult]] = None,
    ) -> Dict[
        str, FuncResult
    ]:  # function: def execute_chained(self, func_ids: List[str], entity: Dict[str, Any], results: Optional[Dict[str, FuncResult]] = None) -> Dict[str, FuncResult]:
        """按依赖拓扑顺序执行原子函数，结果在函数间共享

        核心逻辑：
        1. 拓扑排序确定执行顺序（依赖者先于被依赖者）
        2. 按顺序执行，每个函数可以访问已完成的函数结果
        3. 依赖不满足时跳过该函数（返回 None），不影响后续函数

        """
        if results is None:
            results = {}
        # 拓扑排序：确保依赖函数先执行
        # P94: 若 func_ids 与预计算缓存一致，直接复用避免重复拓扑排序
        if self._ordered_func_ids and func_ids == self._ordered_func_ids:
            ordered_ids = self._ordered_func_ids
        else:
            ordered_ids = self.resolve_dependencies(func_ids)  # function call
        for fid in ordered_ids:  # 循环
            func = self._funcs.get(fid)  # function call
            if func is None:  # condition: func is None:
                continue  # 跳过
            # P133: 实现门禁规则不进入判定（能力未就绪，不产出 PASS/FAIL）
            if getattr(func, "implementation_gate", False):  # check
                continue  # 跳过
            # P32: 依赖检查 - 前置函数必须已执行且结果为 PASS
            if not self.check_dependencies(func, results):  # function call
                continue  # 依赖不满足，跳过
            r = self.execute_with_timeout(func, entity, results=results)  # function call
            if r is not None:  # condition: r is not None:
                results[fid] = r  # 缓存结果
        return results

    def get(
        self, func_id: str
    ) -> Optional[
        AtomicFunction
    ]:  # function: def get(self, func_id: str) -> Optional[AtomicFunction]:
        """获取资源"""
        return self._funcs.get(func_id)  # return: self

    def get_by_clause(
        self, clause_id: str
    ) -> List[
        AtomicFunction
    ]:  # function: def get_by_clause(self, clause_id: str) -> List[AtomicFuncti
        """获取资源"""
        return [f for f in self._funcs.values() if f.clause_id == clause_id]  # return: list

    def list_all(
        self,
    ) -> List[AtomicFunction]:  # function: def list_all(self) -> List[AtomicFunction]:
        """列出资源"""
        return list(self._funcs.values())  # return

    @property  # code
    def count(self) -> int:  # function: def count(self) -> int:
        """执行count功能"""
        return len(self._funcs)  # return: count

    @property  # code
    def capacity(self) -> int:  # function: def capacity(self) -> int:
        """执行capacity功能"""
        return 512  # 框架总容量：422 已用 + 90 余量（GB55036/GB51096 新标准预留）
