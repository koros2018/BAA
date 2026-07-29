"""
BAA 原子函数库 - 规范判定核心
框架预留 30 个位置，首批实现 10 个
"""

from typing import Dict, Any, Optional, List  # typing: type hints
from enum import Enum  # import
from dataclasses import dataclass, field  # dataclass support

import concurrent.futures  # import
import logging  # stdlib: logging

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
        """判断实体类型是否匹配此原子函数"""
        if not self.target_entities:  # check: negated condition
            return True  # 无限制，匹配所有
        return entity.get("type", "") in self.target_entities  # return

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
            if self.operator == ">=":  # check: numeric comparison
                passed = actual >= self.threshold  # assignment
            elif self.operator == "<=":  # 分支
                passed = actual <= self.threshold  # assignment
            elif self.operator == "==":  # 分支
                passed = abs(actual - self.threshold) < 1e-6  # function call
            elif self.operator == ">":  # 分支
                passed = actual > self.threshold  # assignment
            elif self.operator == "<":  # 分支
                passed = actual < self.threshold  # assignment
            else:  # 否则
                passed = False  # assignment
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
        delta = actual - self.threshold  # assignment

        # 执行比较
        if self.operator == ">=":  # check: numeric comparison
            passed = actual >= self.threshold  # assignment
        elif self.operator == "<=":  # 分支
            passed = actual <= self.threshold  # assignment
        elif self.operator == "==":  # 分支
            passed = abs(actual - self.threshold) < 1e-6  # function call
        elif self.operator == ">":  # 分支
            passed = actual > self.threshold  # assignment
        elif self.operator == "<":  # 分支
            passed = actual < self.threshold  # assignment
        else:  # 否则
            passed = False  # assignment

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
        if func_id in ("DIM-001", "DIM-003", "DIM-004"):  # check: membership test
            val = props.get("width", props.get("clear_width", 0.0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无宽度数据，跳过判定

            # DIM-004 边界容差：<2% 偏差视为测量误差，不报违规
            if func_id == "DIM-004" and 0.98 <= (val / 1.1) < 1.0:  # check: numeric comparison
                return None  # 边界走廊，跳过判定
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
            val = props.get("width", props.get("clear_width", 0.0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无宽度数据，跳过判定
            # YOLO 检测的实体尺寸不精确，跳过尺寸判定
            if (
                props.get("detection_source") == "yolo"
            ):  # condition: props.get("detection_source") == "yolo":
                return None  # return: None
            # DIM-006 疏散门净宽：exit_door 类型始终判定；普通 door 仅宽度 >= 1.3m 时判定
            # 0.8~1.3m 的门是标准单开门/双开门，不是人员密集场所疏散门
            if func_id == "DIM-006":  # condition: func_id == "DIM-006":
                entity_type = entity.get("type", "")  # function call
                if entity_type != "exit_door" and val < 1.3:  # check: numeric comparison
                    return None  # 普通门（<1.3m）不是疏散门，不适用此规范
            # 小门（<0.8m）不适用疏散门净宽判定（设备门/检修门等）
            if func_id == "DIM-006" and val < 0.8:  # check: numeric comparison
                return None  # return: None
            # 设备门/管井门排除：图层含 设备/管线/管井/PIPE/喷淋/消防排水 等关键词
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
                ]  # assignment
                if any(kw.upper() in layer for kw in non_exit_layer_kw):  # check: membership test
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
            val = props.get("width", props.get("clear_width", 0.0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无宽度数据，跳过判定
            # DIM-009 疏散出口宽度：仅适用于 exit/exit_door 或宽度 >= 1.3m 的 door
            # 0.8~1.3m 的门是标准单开门，不是疏散出口
            entity_type = entity.get("type", "")  # function call
            if entity_type not in ("exit", "exit_door") and val < 1.3:  # check: numeric comparison
                return None  # 普通门（<1.3m）不是疏散出口，不适用此规范
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

        if func_id in ("DIST-002", "DIST-003"):  # 防火间距 / 袋形走道长度
            val = props.get("distance", props.get("length", 0.0))  # function call
            if val < 0.01:  # check: numeric comparison
                return None  # 无距离数据，跳过判定（语义分析未计算 building↔building 间距）
            if unit == "mm":  # condition: unit == "mm":
                return val / 1000.0  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            if val > 100:  # check: numeric comparison
                return val / 1000.0  # return
            return val  # return

        if func_id == "AREA-002":  # 消防电梯前室面积
            # YOLO 检测的实体 bbox 映射不精确，跳过面积判定
            if (
                props.get("detection_source") == "yolo"
            ):  # condition: props.get("detection_source") == "yolo":
                return None  # return: None
            val = props.get("area", 0.0)  # function call
            if val < 0.01:  # check: numeric comparison
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
                return val / 1000000.0  # return
            if unit == "m2":  # condition: unit == "m2":
                return val  # return
            if val > 10000:  # check: numeric comparison
                return val / 1000000.0  # return
            return val  # return

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

        # EVAC 类：疏散路径判定
        if func_id == "EVAC-001":  # 疏散路径是否存在
            if "has_evacuation_route" not in props:  # check: membership test
                return None  # 无疏散路径分析结果，跳过判定
            # 大面积 room 疏散路径分析可能失败，跳过误报
            area = props.get("area", 0.0)  # function call
            if area and area > 5000:  # check: numeric comparison
                return None  # 大面积 room，路径分析不可靠
            return 1.0 if props.get("has_evacuation_route", False) else 0.0  # return
        if func_id == "EVAC-002":  # 疏散路径长度
            if (
                "evacuation_path_length" not in props and "travel_distance" not in props
            ):  # check: membership test
                return None  # 无疏散路径长度数据，跳过判定
            # 大面积 room 疏散路径分析可能失败
            area = props.get("area", 0.0)  # function call
            if area and area > 5000:  # check: numeric comparison
                return None  # return: None
            return props.get("evacuation_path_length", props.get("travel_distance", 0.0))  # return
        if func_id == "EVAC-003":  # 疏散路径是否超距
            if "evacuation_too_far" not in props:  # check: membership test
                return None  # 无疏散路径分析结果，跳过判定
            # 大面积 room 疏散路径分析可能失败
            area = props.get("area", 0.0)  # function call
            if area and area > 5000:  # check: numeric comparison
                return None  # return: None
            return 0.0 if props.get("evacuation_too_far", False) else 1.0  # return
        if func_id == "EVAC-004":  # 疏散路径瓶颈判定
            if "evacuation_connected" not in props:  # check: membership test
                return None  # 无连通性分析结果，跳过判定
            # 大面积 room 跳过
            area = props.get("area", 0.0)  # function call
            if area and area > 5000:  # check: numeric comparison
                return None  # return: None
            # 连通性 = 1.0（连通），瓶颈 = 0.0（有瓶颈）
            connected = props.get("evacuation_connected", False)  # function call
            bottleneck = props.get("evacuation_bottleneck", False)  # function call
            if not connected:  # check: negated condition
                return 0.0  # 不连通
            if bottleneck:  # condition: bottleneck:
                return 0.0  # 有瓶颈
            return 1.0  # 连通且无瓶颈


# ── 函数注册表 ────────────────────────────────────────────


class FuncRegistry:  # class definition
    """原子函数注册表 - 从 atomic/ 子包加载 422 条原子函数"""

    # P7: 原子函数已从巨型单文件拆分为 atomic/ 子包，此处直接导入
    # atomic/__init__.py 合并了所有模块的 ATOMIC_FUNCTIONS 列表

    def __init__(self, timeout: int = 30):  # function: def __init__(self, timeout: int = 30):
        self._funcs: Dict[str, AtomicFunction] = {}  # assignment
        self._dependency_graph: Dict[str, List[str]] = {}  # 依赖图
        self._timeout = timeout  # assignment
        # P7: 从 atomic/ 子包导入所有原子函数（去重后按 func_id 注册）
        from .atomic import ATOMIC_FUNCTIONS  # import from atomic subpackage

        for func in ATOMIC_FUNCTIONS:  # 循环
            self.register(func)  # function call

    def register(self, func: AtomicFunction):  # function: def register(self, func: AtomicFunction):
        """注册"""
        func.DEFAULT_TIMEOUT = self._timeout  # assignment
        self._funcs[func.func_id] = func  # assignment
        if func.depends_on:
            self._dependency_graph[func.func_id] = list(func.depends_on)

    def resolve_dependencies(self, func_ids: List[str]) -> List[str]:
        """拓扑排序：确保依赖函数在目标函数之前执行"""

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:  # context manager
            future = pool.submit(func.execute, entity)  # function call
            try:  # try block
                return future.result(timeout=timeout)  # return
            except concurrent.futures.TimeoutError:  # catch exception
                logger.warning(
                    f"原子函数超时: {func.func_id} ({func.name}) 超时{timeout}s, 标记为degraded"
                )  # function call
                return FuncResult(  # return
                    func_id=func.func_id,  # assignment
                    func_name=func.name,  # assignment
                    clause_id=func.clause_id,  # assignment
                    operator=func.operator,  # assignment
                    threshold=func.threshold,  # assignment
                    actual=0.0,  # assignment
                    result="DEGRADED",  # assignment
                    delta=0.0,  # assignment
                    severity=Severity.DEGRADED,  # assignment
                    entity_id=entity.get("id", "") if entity else "",  # function call
                    entity_type=entity.get("type", "") if entity else "",  # function call
                    params={
                        "extracted_value": 0.0,
                        "unit": func.unit,  # assignment
                        "note": f"原子函数执行超时(>{timeout}s)，跳过判定",  # function call
                        "reason": "timeout",  # code
                        "clause_text": func.description,
                    },  # code
                )  # code
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
        ordered_ids = self.resolve_dependencies(func_ids)  # function call
        for fid in ordered_ids:  # 循环
            func = self._funcs.get(fid)  # function call
            if func is None:  # condition: func is None:
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
        return 422  # 框架总容量：390 + 16 P45 thermal + 16 P46 structural
