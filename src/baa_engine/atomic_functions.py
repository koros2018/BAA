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
            passed = actual >= self.threshold  # assignment
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
            val = props.get("travel_distance", props.get("length", 0.0))  # function call
            if unit == "mm":  # condition: unit == "mm":
                return val / 1000.0  # return
            if unit == "m":  # condition: unit == "m":
                return val  # return
            if val > 100:  # check: numeric comparison
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
            if unit == "mm2":  # condition: unit == "mm2":
                return val / 1000000.0  # return
            if unit == "m2":  # condition: unit == "m2":
                return val  # return
            if val > 10000:  # check: numeric comparison
                return val / 1000000.0  # return
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
            # 设备门/管井门排除：图层含 设备/管线/PIPE/SB 等关键词
            if func_id == "DIM-006":  # condition: func_id == "DIM-006":
                layer = entity.get("layer", "").upper()  # function call
                non_exit_layer_kw = [
                    "设备",
                    "管线",
                    "管井",
                    "PIPE",
                    "SB",
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
    """原子函数注册表 - 框架30个位置"""

    # 首批 10 个原子函数（L1级，与规范JSON库对齐）
    INITIAL_FUNCS = [  # assignment
        AtomicFunction(
            "DIM-001",
            "疏散楼梯净宽判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-5.5.18",
            "疏散楼梯净宽度不应小于1.2m",
            ">=",
            1.2,
            "m",  # assignment
            target_entities=["staircase", "stair"],
        ),  # assignment
        AtomicFunction(
            "DIM-002",
            "防火分区面积判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-6.1.1",
            "防火分区面积不应大于2500㎡",
            "<=",
            2500,
            "㎡",  # assignment
            target_entities=["fire_zone"],
        ),  # assignment
        AtomicFunction(
            "DIM-003",
            "消防车道宽度判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-7.1.1",
            "消防车道宽度不应小于4m",
            ">=",
            4.0,
            "m",  # assignment
            target_entities=["fire_lane", "road", "driveway"],
        ),  # assignment
        AtomicFunction(
            "DIST-001",
            "疏散距离判定",
            FuncCategory.DISTANCE,  # code
            "GB50016-5.5.17",
            "疏散距离不应大于30m",
            "<=",
            30.0,
            "m",  # assignment
            target_entities=["room", "floor", "space"],
        ),  # assignment
        AtomicFunction(
            "COUNT-001",
            "安全出口数量判定",
            FuncCategory.COUNT,  # code
            "GB50016-5.5.8",
            "安全出口不应少于2个",
            ">=",
            2.0,
            "个",  # assignment
            target_entities=["floor", "fire_zone"],
        ),  # assignment
        AtomicFunction(
            "ATTR-001",
            "防火门等级判定",
            FuncCategory.ATTR,  # code
            "GB50016-6.5.1",
            "防火门等级不应低于丙级",
            ">=",
            1.0,
            "级",  # assignment
            target_entities=["fire_door", "door"],
        ),  # assignment
        AtomicFunction(
            "DIM-004",
            "疏散走道宽度判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-5.5.18",
            "疏散走道净宽度不应小于1.1m",
            ">=",
            1.1,
            "m",  # assignment
            target_entities=["corridor", "aisle", "passage"],
        ),  # assignment
        AtomicFunction(
            "AREA-001",
            "避难层面积判定",
            FuncCategory.AREA,  # code
            "GB50016-7.4.1",
            "避难层净面积不宜小于5㎡/人",
            ">=",
            5.0,
            "㎡/人",  # assignment
            target_entities=["refuge_floor", "refuge_area", "floor"],
        ),  # assignment
        AtomicFunction(
            "EXIST-001",
            "楼梯间存在判定",
            FuncCategory.EXIST,  # code
            "GB50016-5.5.12",
            "建筑应设置楼梯间",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["staircase", "stair"],
        ),  # assignment
        AtomicFunction(
            "DIM-005",
            "窗净面积判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-7.2.4",
            "消防窗净面积不应小于1.0㎡",
            ">=",
            1.0,
            "㎡",  # assignment
            target_entities=["fire_window", "window"],
        ),  # assignment
        # L2 规范原子函数（9个）
        AtomicFunction(
            "DIM-006",
            "疏散门净宽判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-5.5.19",
            "人员密集场所疏散门净宽不应小于1.4m",
            ">=",
            1.4,
            "m",  # assignment
            target_entities=["exit_door", "door"],
        ),  # assignment
        AtomicFunction(
            "DIM-007",
            "防火卷帘宽度判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-6.5.3",
            "防火分隔防火卷帘宽度不应大于10m",
            "<=",
            10.0,
            "m",  # assignment
            target_entities=["fire_curtain", "curtain"],
        ),  # assignment
        AtomicFunction(
            "EXIST-002",
            "管道井封堵判定",
            FuncCategory.EXIST,  # code
            "GB50016-6.6.1",
            "管道井应每层用不燃材料封堵",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["shaft", "pipe_shaft", "cable_shaft"],
        ),  # assignment
        AtomicFunction(
            "EXIST-003",
            "剪刀楼梯分隔判定",
            FuncCategory.EXIST,  # code
            "GB50016-5.5.24",
            "剪刀楼梯梯段间应设置防火隔墙",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["scissor_staircase", "staircase"],
        ),  # assignment
        AtomicFunction(
            "EXIST-004",
            "疏散指示标志判定",
            FuncCategory.EXIST,  # code
            "GB50016-10.3.1",
            "疏散走道和安全出口应设疏散指示标志",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["exit_sign", "sign", "evacuation_sign"],
        ),  # assignment
        AtomicFunction(
            "EXIST-005",
            "自动灭火系统判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.3.1",
            "一类高层应设置自动灭火系统",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=[
                "sprinkler_system",
                "sprinkler",
                "fire_hydrant",
                "fire_extinguisher",
                "fire_system",
            ],
        ),  # assignment
        AtomicFunction(
            "EXIST-006",
            "火灾报警系统判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.4.1",
            "一类高层应设置火灾自动报警系统",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["fire_alarm", "alarm_system", "smoke_detector", "fire_system"],
        ),  # assignment
        AtomicFunction(
            "ATTR-002",
            "保温材料等级判定",
            FuncCategory.ATTR,  # code
            "GB50016-6.7.1",
            "保温材料应选用A或B1级",
            ">=",
            2.0,
            "级",  # assignment
            target_entities=["insulation", "wall_insulation", "roof_insulation"],
        ),  # assignment
        AtomicFunction(
            "LIGHT-001",
            "应急照明照度判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-10.1.5",
            "疏散照明照度不应低于1.0lx",
            ">=",
            1.0,
            "lx",  # assignment
            target_entities=["evacuation_lighting", "light", "lighting"],
        ),  # assignment
    ]  # code

    # 框架预留 20 个位置（V2.0扩展）
    RESERVED_FUNCS = [  # assignment
        # ===== L3 新增（11个，从19→30）=====
        # 防火间距
        AtomicFunction(
            "DIST-002",
            "防火间距判定",
            FuncCategory.DISTANCE,  # code
            "GB50016-3.4.1",
            "厂房之间防火间距不应小于表3.4.1规定",
            ">=",
            12.0,
            "m",  # assignment
            target_entities=["building", "factory", "warehouse"],
        ),  # assignment
        # 排烟窗面积
        AtomicFunction(
            "DIM-008",
            "排烟窗面积判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-9.2.1",
            "排烟窗净面积不应小于房间面积2%",
            ">=",
            0.02,
            "㎡",  # assignment
            target_entities=["smoke_exhaust_window", "window", "room"],
        ),  # assignment
        # 消防电梯
        AtomicFunction(
            "EXIST-007",
            "消防电梯判定",
            FuncCategory.EXIST,  # code
            "GB50016-7.3.1",
            "一类高层公共建筑应设消防电梯",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["fire_elevator", "elevator"],
        ),  # assignment
        # 消防电梯前室面积
        AtomicFunction(
            "AREA-002",
            "消防电梯前室面积判定",
            FuncCategory.AREA,  # code
            "GB50016-7.3.5",
            "消防电梯前室面积不应小于6㎡",
            ">=",
            6.0,
            "㎡",  # assignment
            target_entities=["elevator_lobby", "lobby"],
        ),  # assignment
        # 疏散走道长度
        AtomicFunction(
            "DIST-003",
            "袋形走道长度判定",
            FuncCategory.DISTANCE,  # code
            "GB50016-5.5.17",
            "袋形走道长度不应大于20m",
            "<=",
            20.0,
            "m",  # assignment
            target_entities=["corridor", "aisle", "passage"],
        ),  # assignment
        # 疏散出口宽度
        AtomicFunction(
            "DIM-009",
            "疏散出口宽度判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-5.5.18",
            "疏散出口净宽度不应小于0.9m",
            ">=",
            0.9,
            "m",  # assignment
            target_entities=["exit", "exit_door", "door"],
        ),  # assignment
        # 防火窗耐火极限
        AtomicFunction(
            "ATTR-003",
            "防火窗等级判定",
            FuncCategory.ATTR,  # code
            "GB50016-6.5.1",
            "防火窗耐火极限不应低于1.0h",
            ">=",
            1.0,
            "h",  # assignment
            target_entities=["fire_window", "window"],
        ),  # assignment
        # 屋顶消防水箱
        AtomicFunction(
            "EXIST-008",
            "消防水箱判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.2.1",
            "一类高层应设消防水箱",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["water_tank", "fire_system"],
        ),  # assignment
        # 消防水池
        AtomicFunction(
            "EXIST-009",
            "消防水池判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.1.3",
            "市政供水不足时应设消防水池",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["water_reservoir", "fire_system"],
        ),  # assignment
        # 消防救援窗
        AtomicFunction(
            "DIM-010",
            "消防救援窗面积判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-7.2.4",
            "消防救援窗口净面积不应小于1.0㎡",
            ">=",
            1.0,
            "㎡",  # assignment
            target_entities=["rescue_window", "window"],
        ),  # assignment
        # 应急广播
        AtomicFunction(
            "EXIST-010",
            "应急广播判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.5.1",
            "一类高层应设应急广播系统",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["emergency_broadcast", "speaker", "fire_system"],
        ),  # assignment
        # ===== 设备类判定（P34 新增，5个）=====
        AtomicFunction(
            "EXIST-011",
            "应急照明判定",
            FuncCategory.EXIST,  # code
            "GB50016-10.3.1",
            "疏散走道应设应急照明",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["emergency_light", "exit_sign"],
        ),  # assignment
        AtomicFunction(
            "EXIST-012",
            "消防广播判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.5.1",
            "一类高层应设消防广播",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["alarm_device", "speaker", "emergency_broadcast"],
        ),  # assignment
        AtomicFunction(
            "EXIST-013",
            "消防水泵判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.2.2",
            "一类高层应设消防水泵",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["fire_pump", "fire_hydrant"],
        ),  # assignment
        AtomicFunction(
            "EXIST-014",
            "消防水箱判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.2.1",
            "一类高层应设消防水箱",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["water_tank", "fire_system"],
        ),  # assignment
        AtomicFunction(
            "EXIST-015",
            "排烟设备判定",
            FuncCategory.EXIST,  # code
            "GB50016-8.5.3",
            "一类高层应设排烟设备",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["smoke_exhaust", "fan"],
        ),  # assignment
        # ===== EVAC 疏散路径判定（V2新增，3个）=====
        AtomicFunction(
            "EVAC-001",
            "疏散路径连通性判定",
            FuncCategory.EVAC,  # code
            "GB50016-5.5.17",
            "每个房间应有通往安全出口的疏散路径",
            "==",
            1.0,
            "有/无",  # assignment
            target_entities=["room", "space", "floor"],
        ),  # assignment
        AtomicFunction(
            "EVAC-002",
            "疏散路径长度判定",
            FuncCategory.EVAC,  # code
            "GB50016-5.5.17",
            "房间到最近安全出口的疏散距离不应大于30m",
            "<=",
            30.0,
            "m",  # assignment
            target_entities=["room", "space", "floor"],
            depends_on=["EVAC-001"],  # 依赖：路径存在才能测长度
        ),  # assignment
        AtomicFunction(
            "EVAC-003",
            "疏散路径合规性判定",
            FuncCategory.EVAC,  # code
            "GB50016-5.5.17",
            "房间到安全出口的疏散路径应满足规范要求",
            "==",
            1.0,
            "合规/违规",  # assignment
            target_entities=["room", "space", "floor"],
            depends_on=["EVAC-001"],  # 依赖：路径存在才能测合规性
        ),  # assignment
        # P33: 疏散路径连通性验证
        AtomicFunction(
            "EVAC-004",
            "疏散路径瓶颈判定",
            FuncCategory.EVAC,  # code
            "GB50016-5.5.18",
            "疏散路径上的走廊净宽不应小于1.2m，门净宽不应小于0.8m",
            "==",
            1.0,
            "通畅/瓶颈",  # assignment
            target_entities=["room", "space", "floor"],
            depends_on=["EVAC-001"],  # 依赖：路径存在才能测瓶颈
        ),  # assignment
        # ===== P47 无障碍设计（GB50763，10条）=====
        AtomicFunction(
            "ACCESS-001",
            "轮椅坡道坡度判定",
            FuncCategory.ACCESS,
            "GB50763-3.3.2",
            "坡道坡度不应大于1:12(8.33%)",
            "<=",
            8.33,
            "%",
            target_entities=["ramp"],
        ),
        AtomicFunction(
            "ACCESS-002",
            "轮椅坡道宽度判定",
            FuncCategory.ACCESS,
            "GB50763-3.3.3",
            "坡道净宽不应小于1.20m",
            ">=",
            1.20,
            "m",
            target_entities=["ramp"],
        ),
        AtomicFunction(
            "ACCESS-003",
            "无障碍出入口宽度判定",
            FuncCategory.ACCESS,
            "GB50763-3.5.2",
            "出入口净宽不应小于0.90m",
            ">=",
            0.90,
            "m",
            target_entities=["accessible_door"],
        ),
        AtomicFunction(
            "ACCESS-004",
            "无障碍通道宽度判定",
            FuncCategory.ACCESS,
            "GB50763-3.6.1",
            "通道净宽不应小于1.20m",
            ">=",
            1.20,
            "m",
            target_entities=["corridor", "accessible_path"],
        ),
        AtomicFunction(
            "ACCESS-005",
            "扶手设置判定",
            FuncCategory.EXIST,
            "GB50763-3.8.1",
            "坡道/台阶两侧应设扶手",
            "==",
            1.0,
            "有",
            target_entities=["handrail"],
        ),
        AtomicFunction(
            "ACCESS-006",
            "无障碍电梯判定",
            FuncCategory.EXIST,
            "GB50763-3.7.1",
            "二层及以上应设无障碍电梯",
            "==",
            1.0,
            "有",
            target_entities=["accessible_elevator"],
        ),
        AtomicFunction(
            "ACCESS-007",
            "无障碍停车位判定",
            FuncCategory.ACCESS,
            "GB50763-3.11.2",
            "应设不少于总车位2%的无障碍车位",
            ">=",
            0.02,
            "比例",
            target_entities=["parking_space"],
        ),
        AtomicFunction(
            "ACCESS-008",
            "无障碍卫生间判定",
            FuncCategory.EXIST,
            "GB50763-3.9.1",
            "应设无障碍卫生间",
            "==",
            1.0,
            "有",
            target_entities=["accessible_toilet"],
        ),
        AtomicFunction(
            "ACCESS-009",
            "轮椅回转空间判定",
            FuncCategory.ACCESS,
            "GB50763-3.8.2",
            "轮椅回转直径不应小于1.50m",
            ">=",
            1.50,
            "m",
            target_entities=["wheelchair_space"],
        ),
        AtomicFunction(
            "ACCESS-010",
            "盲道设置判定",
            FuncCategory.EXIST,
            "GB50763-3.2.1",
            "主要流线应设盲道",
            "==",
            1.0,
            "有",
            target_entities=["tactile_guide"],
        ),
        # ===== P26 防火规范扩展（V2.5新增，4个）=====
        AtomicFunction(
            "LIGHT-002",
            "楼梯间应急照明照度判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-10.3.2",
            "楼梯间、前室等疏散照明照度不应低于5.0lx",
            ">=",
            5.0,
            "lx",  # assignment
            target_entities=["staircase", "stair", "lobby", "corridor"],
        ),  # assignment
        AtomicFunction(
            "DIM-011",
            "消防车道净高判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-7.1.8",
            "消防车道净高不应小于4.0m",
            ">=",
            4.0,
            "m",  # assignment
            target_entities=["fire_lane", "road", "driveway"],
        ),  # assignment
        AtomicFunction(
            "DIM-012",
            "避难走道净宽判定",
            FuncCategory.DIMENSION,  # code
            "GB50016-6.4.14",
            "避难走道净宽不应小于任一防火分区疏散总净宽",
            ">=",
            1.0,
            "m",  # assignment
            target_entities=["exit_passageway", "passage", "corridor"],
        ),  # assignment
        AtomicFunction(
            "DIST-004",
            "救援窗口间距判定",
            FuncCategory.DISTANCE,  # code
            "GB50016-7.2.5",
            "消防救援窗口间距不应大于20m",
            "<=",
            20.0,
            "m",  # assignment
            target_entities=["rescue_window", "window"],
        ),  # assignment
        # ── P57 补充（2026-07-13）：5 条 GB50016 扩展 ──
        AtomicFunction(
            func_id="DIM-013",
            name="安全出口净高不应小于2.0m",
            description="疏散走道和楼梯的最小净宽度不应小于2.0m（GB50016-5.5.18）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.18",
            target_entities={"room", "corridor"},
            operator="ge",
            threshold=2000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-014",
            name="疏散指示标志间距不应大于20m",
            description="疏散指示标志间距不大于20m（GB50016-10.3.1）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-10.3.1",
            target_entities={"exit_sign"},
            operator="le",
            threshold=20000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-015",
            name="袋形走道疏散距离不应大于15m",
            description="袋形走道的疏散距离不应大于15m（GB50016-5.5.17）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-5.5.17",
            target_entities={"room", "corridor"},
            operator="le",
            threshold=15000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXI-016",
            name="安全出口宽度不足时应设双向疏散",
            description="房间安全出口宽度不满足要求时需设两个出口（GB50016-5.5.8）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-5.5.8",
            target_entities={"exit", "fire_door"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-016",
            name="消防车道净高不应小于4.0m",
            description="消防车道的净高不应小于4.0m（GB50016-7.1.8）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-7.1.8",
            target_entities={"corridor"},
            operator="ge",
            threshold=4000.0,
            unit="mm",
            depends_on=[],
        ),
        # ── P57 扩展 2026-07-14：GB50016 防火分区/疏散/消防设施 15条 ──
        AtomicFunction(
            func_id="DIM-017",
            name="防火分区最大允许建筑面积判定",
            description="一、二级耐火等级建筑防火分区最大允许建筑面积（GB50016-5.3.1）",
            category=FuncCategory.AREA,
            clause_id="GB50016-5.3.1",
            target_entities={"fire_zone", "room", "floor"},
            operator="le",
            threshold=2500.0,
            unit="sqm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-018",
            name="防烟楼梯间前室面积判定",
            description="防烟楼梯间前室使用面积不应小于6.0sqm（GB50016-6.4.3）",
            category=FuncCategory.AREA,
            clause_id="GB50016-6.4.3",
            target_entities={"staircase", "lobby", "anteroom"},
            operator="ge",
            threshold=6.0,
            unit="sqm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-019",
            name="合用前室面积判定",
            description="消防电梯与防烟楼梯间合用前室使用面积不应小于10.0sqm（GB50016-6.4.3）",
            category=FuncCategory.AREA,
            clause_id="GB50016-6.4.3",
            target_entities={"lobby", "anteroom", "staircase"},
            operator="ge",
            threshold=10.0,
            unit="sqm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-020",
            name="疏散楼梯最小净宽判定",
            description="疏散楼梯最小净宽度不应小于1.1m（GB50016-5.5.18）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.18",
            target_entities={"stair", "staircase", "stairs"},
            operator="ge",
            threshold=1100.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-021",
            name="首层疏散外门净宽判定",
            description="首层疏散外门净宽度不应小于1.1m（GB50016-5.5.19）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.19",
            target_entities={"exit", "door", "fire_door"},
            operator="ge",
            threshold=1100.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-022",
            name="人员密集场所疏散门净宽判定",
            description="人员密集场所疏散门净宽度不应小于1.4m（GB50016-5.5.19）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.19",
            target_entities={"exit", "door", "fire_door"},
            operator="ge",
            threshold=1400.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-005",
            name="两个安全出口间距判定",
            description="两个安全出口之间的间距不应小于5.0m（GB50016-5.5.2）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-5.5.2",
            target_entities={"exit", "fire_door"},
            operator="ge",
            threshold=5000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-006",
            name="排烟口与安全出口间距判定",
            description="排烟口与安全出口之间的距离不应小于1.5m（GB50016-9.2.3）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-9.2.3",
            target_entities={"smoke_vent", "exit", "fire_door"},
            operator="ge",
            threshold=1500.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-002",
            name="高层建筑避难层数量判定",
            description="建筑高度大于100m时每50m应设一个避难层（GB50016-5.5.23）",
            category=FuncCategory.COUNT,
            clause_id="GB50016-5.5.23",
            target_entities={"refuge_floor", "floor"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-016",
            name="避难层消防设施判定",
            description="避难层应设消火栓、消防专线电话和应急广播（GB50016-5.5.23）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-5.5.23",
            target_entities={"refuge_floor"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-017",
            name="消防电梯设置判定",
            description="一类高层建筑应设消防电梯（GB50016-7.3.1）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-7.3.1",
            target_entities={"elevator", "fire_elevator"},
            operator="ge",
            threshold=1.0,
            unit="台",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="ATTR-004",
            name="防火墙耐火极限判定",
            description="防火墙的耐火极限不应低于3.00h（GB50016-6.1.1）",
            category=FuncCategory.ATTR,
            clause_id="GB50016-6.1.1",
            target_entities={"fire_wall", "wall"},
            operator="ge",
            threshold=3.0,
            unit="h",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="AREA-003",
            name="避难层净面积判定",
            description="避难层净面积按5.0人/sqm设计（GB50016-5.5.23）",
            category=FuncCategory.AREA,
            clause_id="GB50016-5.5.23",
            target_entities={"refuge_floor"},
            operator="ge",
            threshold=50.0,
            unit="sqm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="LIGHT-003",
            name="消防控制室应急照明照度判定",
            description="消防控制室、消防水泵房等应保持正常照明照度（GB50016-10.3.3）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-10.3.3",
            target_entities={"control_room", "pump_room", "equipment_room"},
            operator="ge",
            threshold=100.0,
            unit="lx",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-023",
            name="防火卷帘宽度判定",
            description="防火卷帘宽度不应超过规范允许值（GB50016-6.5.3）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-6.5.3",
            target_entities={"fire_curtain", "fire_shutter"},
            operator="le",
            threshold=4000.0,
            unit="mm",
            depends_on=[],
        ),
        # ── P57 扩展 2026-07-14：GB50016 疏散/消防给水/防排烟/电气 15条 ──
        AtomicFunction(
            func_id="DIM-024",
            name="观众厅疏散门数量判定",
            description="观众厅每个疏散门的平均疏散人数不应超过250人（GB50016-5.5.16）",
            category=FuncCategory.COUNT,
            clause_id="GB50016-5.5.16",
            target_entities={"exit", "door", "fire_door"},
            operator="ge",
            threshold=2.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-025",
            name="地下建筑疏散楼梯宽度判定",
            description="地下或半地下建筑疏散楼梯净宽度不应小于1.1m（GB50016-5.5.20）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.20",
            target_entities={"stair", "staircase", "stairs"},
            operator="ge",
            threshold=1100.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-026",
            name="室外疏散楼梯净宽判定",
            description="室外疏散楼梯净宽度不应小于0.9m（GB50016-6.4.5）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-6.4.5",
            target_entities={"stair", "staircase", "external_stair"},
            operator="ge",
            threshold=900.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-007",
            name="消防水源间距判定",
            description="室外消火栓间距不应大于120m（GB50016-8.1.3）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-8.1.3",
            target_entities={"hydrant", "fire_hydrant"},
            operator="le",
            threshold=120000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-008",
            name="防火分区安全出口间距判定",
            description="同一防火分区两个安全出口间距不应小于5m（GB50016-5.5.2）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-5.5.2",
            target_entities={"exit", "fire_door", "fire_zone"},
            operator="ge",
            threshold=5000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-018",
            name="自动喷水灭火系统判定",
            description="一类高层民用建筑应设自动喷水灭火系统（GB50016-8.3.3）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-8.3.3",
            target_entities={"sprinkler", "fire_sprinkler", "equipment"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-019",
            name="消防专用电话判定",
            description="消防控制室应设消防专用电话总机（GB50016-8.6.1）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-8.6.1",
            target_entities={"control_room", "phone", "equipment"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-020",
            name="消防控制室判定",
            description="设有火灾自动报警系统的建筑应设消防控制室（GB50016-8.1.6）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-8.1.6",
            target_entities={"control_room", "room"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-027",
            name="机械排烟系统排烟量判定",
            description="机械排烟系统最小排烟量不应小于7200m³/h（GB50016-9.3.1）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-9.3.1",
            target_entities={"smoke_exhaust", "equipment", "ventilator"},
            operator="ge",
            threshold=7200.0,
            unit="m3h",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-028",
            name="储油间储油量判定",
            description="锅炉房储油间储油量不应大于1m³（GB50016-5.4.15）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.4.15",
            target_entities={"oil_room", "boiler_room", "room"},
            operator="le",
            threshold=1.0,
            unit="m3",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-029",
            name="消防电梯运行速度判定",
            description="消防电梯从首层到顶层运行时间不应超过60s（GB50016-7.3.8）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-7.3.8",
            target_entities={"fire_elevator", "elevator"},
            operator="le",
            threshold=60.0,
            unit="s",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="AREA-004",
            name="消防控制室面积判定",
            description="消防控制室面积不应小于30sqm（GB50016-8.1.7）",
            category=FuncCategory.AREA,
            clause_id="GB50016-8.1.7",
            target_entities={"control_room", "room"},
            operator="ge",
            threshold=30.0,
            unit="sqm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="ATTR-005",
            name="防火门耐火等级判定",
            description="疏散楼梯间及其前室应采用乙级防火门（GB50016-6.4.3）",
            category=FuncCategory.ATTR,
            clause_id="GB50016-6.4.3",
            target_entities={"fire_door", "door"},
            operator="ge",
            threshold=2.0,
            unit="级",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-030",
            name="消防救援场地宽度判定",
            description="消防救援场地宽度不应小于10m（GB50016-7.2.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-7.2.2",
            target_entities={"rescue_area", "road", "driveway"},
            operator="ge",
            threshold=10000.0,
            unit="mm",
            depends_on=[],
        ),
        # ── P57 扩展 2026-07-14：GB50016 剩余核心条款 15条 ──
        AtomicFunction(
            func_id="DIM-031",
            name="消防车道转弯半径判定",
            description="消防车道转弯半径不应小于9m（GB50016-7.1.3）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-7.1.3",
            target_entities={"fire_lane", "road", "driveway"},
            operator="ge",
            threshold=9000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-032",
            name="消防救援窗口尺寸判定",
            description="消防救援窗口净高和净宽均不应小于1.0m（GB50016-7.2.4）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-7.2.4",
            target_entities={"rescue_window", "window"},
            operator="ge",
            threshold=1000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-033",
            name="封闭楼梯间门宽度判定",
            description="封闭楼梯间门净宽度不应小于0.9m（GB50016-5.5.18）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.18",
            target_entities={"staircase_door", "door", "fire_door"},
            operator="ge",
            threshold=900.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-034",
            name="疏散门开启净宽度判定",
            description="疏散门开启后净宽度应按门扇净宽减去0.05m计算（GB50016-5.5.18）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-5.5.18",
            target_entities={"exit_door", "door", "fire_door"},
            operator="ge",
            threshold=850.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-009",
            name="高层建筑消防登高场地间距判定",
            description="高层建筑消防登高操作场地间隔不应大于30m（GB50016-7.2.2）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-7.2.2",
            target_entities={"rescue_area", "road", "driveway"},
            operator="le",
            threshold=30000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-010",
            name="室外消火栓保护半径判定",
            description="室外消火栓保护半径不应大于150m（GB50016-8.1.3）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50016-8.1.3",
            target_entities={"hydrant", "fire_hydrant"},
            operator="le",
            threshold=150000.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-003",
            name="封闭楼梯间数量判定",
            description="建筑高度不大于21m的住宅建筑可采用敞开楼梯间（GB50016-5.5.25）",
            category=FuncCategory.COUNT,
            clause_id="GB50016-5.5.25",
            target_entities={"staircase", "stair"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-004",
            name="柴油发电机储油量判定",
            description="柴油发电机房储油间储油量不应大于1m³（GB50016-5.4.15）",
            category=FuncCategory.COUNT,
            clause_id="GB50016-5.4.15",
            target_entities={"generator_room", "oil_room", "room"},
            operator="le",
            threshold=1.0,
            unit="m3",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-021",
            name="疏散门开启方向判定",
            description="疏散门应向疏散方向开启（GB50016-6.4.11）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-6.4.11",
            target_entities={"exit_door", "door", "fire_door"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-022",
            name="防火阀设置判定",
            description="通风管道穿越防火分区处应设防火阀（GB50016-6.3.5）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-6.3.5",
            target_entities={"fire_damper", "equipment", "duct"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-023",
            name="室内消火栓设置判定",
            description="高层建筑和体积大于5000m³的公共建筑应设室内消火栓（GB50016-8.2.1）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-8.2.1",
            target_entities={"fire_hydrant", "hydrant", "equipment"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-024",
            name="电气线路防火保护判定",
            description="消防配电线路应采用阻燃电缆并采取防火保护措施（GB50016-10.2.1）",
            category=FuncCategory.EXIST,
            clause_id="GB50016-10.2.1",
            target_entities={"cable", "conduit", "equipment"},
            operator="ge",
            threshold=1.0,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="ATTR-006",
            name="楼板耐火极限判定",
            description="一级耐火等级建筑楼板耐火极限不应低于1.50h（GB50016-5.1.2）",
            category=FuncCategory.ATTR,
            clause_id="GB50016-5.1.2",
            target_entities={"floor_slab", "floor", "structure"},
            operator="ge",
            threshold=1.5,
            unit="h",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="ATTR-007",
            name="建筑幕墙防火判定",
            description="建筑幕墙在每层楼板处应采用防火封堵（GB50016-6.2.9）",
            category=FuncCategory.ATTR,
            clause_id="GB50016-6.2.9",
            target_entities={"curtain_wall", "wall", "facade"},
            operator="ge",
            threshold=1.0,
            unit="h",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="AREA-005",
            name="柴油发电机房面积判定",
            description="柴油发电机房建筑面积不宜大于400m²（GB50016-5.4.15）",
            category=FuncCategory.AREA,
            clause_id="GB50016-5.4.15",
            target_entities={"generator_room", "room"},
            operator="le",
            threshold=400.0,
            unit="sqm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="LIGHT-004",
            name="疏散走道疏散照明照度判定",
            description="疏散走道疏散照明地面最低照度不应低于1.0lx（GB50016-10.3.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50016-10.3.2",
            target_entities={"corridor", "aisle", "passage"},
            operator="ge",
            threshold=1.0,
            unit="lx",
            depends_on=[],
        ),
        # ── P57 扩展 2026-07-14：GB50974 消防给水 ──
        AtomicFunction(
            func_id="DIM-035",
            name="消防水池有效容积判定",
            description="消防水池有效容积应满足火灾延续时间内消防用水量（GB50974-4.3.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-4.3.2",
            target_entities={"fire_water_tank", "water_tank", "equipment"},
            operator="ge",
            threshold=500.0,
            unit="m3",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-005",
            name="消防水池分格判定",
            description="消防水池总有效容积大于500m³时宜设两格能独立使用的消防水池（GB50974-4.3.6）",
            category=FuncCategory.COUNT,
            clause_id="GB50974-4.3.6",
            target_entities={"fire_water_tank", "water_tank", "compartment"},
            operator="ge",
            threshold=2,
            unit="个",
            depends_on=["DIM-035"],
        ),
        AtomicFunction(
            func_id="DIM-036",
            name="高位消防水箱有效容积判定",
            description="一类高层公共建筑高位消防水箱有效容积不应小于36m³（GB50974-5.2.1）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-5.2.1",
            target_entities={"water_tank", "roof_tank", "equipment"},
            operator="ge",
            threshold=36.0,
            unit="m3",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-037",
            name="消防水箱有效水位判定",
            description="高位消防水箱最低有效水位应满足灭火设施压力要求（GB50974-5.2.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-5.2.2",
            target_entities={"water_tank", "roof_tank", "equipment"},
            operator="ge",
            threshold=2.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-038",
            name="稳压泵流量判定",
            description="消防给水稳压泵流量不应小于1.0L/s（GB50974-5.3.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-5.3.2",
            target_entities={"pressure_pump", "pump", "equipment"},
            operator="ge",
            threshold=1.0,
            unit="L/s",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-006",
            name="水泵接合器数量判定",
            description="消防水泵接合器数量应按消防用水量计算确定（GB50974-5.4.3）",
            category=FuncCategory.COUNT,
            clause_id="GB50974-5.4.3",
            target_entities={"siamese_connection", "fire_department_connection", "equipment"},
            operator="ge",
            threshold=2,
            unit="个",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-025",
            name="消防水泵房排水判定",
            description="消防水泵房应设排水设施（GB50974-5.5.12）",
            category=FuncCategory.EXIST,
            clause_id="GB50974-5.5.12",
            target_entities={"pump_room", "room", "drain"},
            operator="eq",
            threshold=1,
            unit="有/无",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-011",
            name="室外消火栓间距判定",
            description="室外消火栓布置间距不应大于120m（GB50974-6.1.8）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50974-6.1.8",
            target_entities={"outdoor_hydrant", "hydrant", "equipment"},
            operator="le",
            threshold=120.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-012",
            name="室内消火栓间距判定",
            description="室内消火栓间距不应大于30m（GB50974-6.2.1）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50974-6.2.1",
            target_entities={"indoor_hydrant", "hydrant", "equipment"},
            operator="le",
            threshold=30.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-039",
            name="消防水带长度判定",
            description="消防水带长度不宜大于25m（GB50974-6.4.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-6.4.2",
            target_entities={"fire_hose", "hose", "equipment"},
            operator="le",
            threshold=25.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-040",
            name="消防水枪充实水柱判定",
            description="消防水枪充实水柱不应小于13m（GB50974-7.4.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-7.4.2",
            target_entities={"nozzle", "fire_hose", "equipment"},
            operator="ge",
            threshold=13.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="ATTR-008",
            name="消防给水管道压力判定",
            description="消防给水管道最低压力不应小于0.10MPa（GB50974-8.1.2）",
            category=FuncCategory.ATTR,
            clause_id="GB50974-8.1.2",
            target_entities={"piping", "pipe", "fire_main"},
            operator="ge",
            threshold=0.10,
            unit="MPa",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-041",
            name="消防水泵流量判定",
            description="消防水泵流量不应小于设计消防用水量（GB50974-9.3.1）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-9.3.1",
            target_entities={"fire_pump", "pump", "equipment"},
            operator="ge",
            threshold=20.0,
            unit="L/s",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-042",
            name="消防水泵启动时间判定",
            description="消防水泵从接到启泵信号到正常运转时间不应大于2min（GB50974-11.0.4）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-11.0.4",
            target_entities={"fire_pump", "pump", "equipment"},
            operator="le",
            threshold=2.0,
            unit="min",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-043",
            name="消防管道管径判定",
            description="消防给水管道管径不应小于DN100（GB50974-12.3.1）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-12.3.1",
            target_entities={"piping", "pipe", "fire_main"},
            operator="ge",
            threshold=100.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-026",
            name="消防水泵电源判定",
            description="消防水泵应设置双电源或双回路供电（GB50974-11.0.4强条）",
            category=FuncCategory.EXIST,
            clause_id="GB50974-11.0.4",
            target_entities={"fire_pump", "power_supply", "electrical"},
            operator="eq",
            threshold=1,
            unit="有/无",
            depends_on=[],
        ),
        # ── P57 扩展 2026-07-14：GB50974 剩余条款（8条）──
        AtomicFunction(
            func_id="DIM-044",
            name="消防水泵吸水高度判定",
            description="消防水泵吸水高度不应大于6.0m（GB50974-5.1.12）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-5.1.12",
            target_entities={"fire_pump", "pump", "equipment"},
            operator="le",
            threshold=6.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-045",
            name="消防水泵出水管压力判定",
            description="消防水泵出水管压力不应小于设计工作压力（GB50974-5.1.13）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-5.1.13",
            target_entities={"fire_pump", "pump", "equipment"},
            operator="ge",
            threshold=0.8,
            unit="MPa",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-046",
            name="消防水池进水管管径判定",
            description="消防水池进水管管径不应小于DN100（GB50974-4.3.3）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-4.3.3",
            target_entities={"fire_water_tank", "water_tank", "equipment"},
            operator="ge",
            threshold=100.0,
            unit="mm",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-047",
            name="消防水箱间温度判定",
            description="消防水箱间温度不应低于5℃（GB50974-5.2.4）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50974-5.2.4",
            target_entities={"water_tank_room", "pump_room", "room"},
            operator="ge",
            threshold=5.0,
            unit="℃",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-007",
            name="消防水泵数量判定",
            description="消防水泵应设置不少于2台（GB50974-5.1.6）",
            category=FuncCategory.COUNT,
            clause_id="GB50974-5.1.6",
            target_entities={"fire_pump", "pump", "equipment"},
            operator="ge",
            threshold=2,
            unit="台",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-013",
            name="室内消火栓保护半径判定",
            description="室内消火栓保护半径不应大于25m（GB50974-7.4.2）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50974-7.4.2",
            target_entities={"indoor_hydrant", "hydrant", "equipment"},
            operator="le",
            threshold=25.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-027",
            name="消防水泵试水管判定",
            description="消防水泵应设置试水管（GB50974-5.1.11）",
            category=FuncCategory.EXIST,
            clause_id="GB50974-5.1.11",
            target_entities={"fire_pump", "pump", "equipment"},
            operator="eq",
            threshold=1,
            unit="有/无",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="ATTR-009",
            name="消防给水管道材质判定",
            description="消防给水管道应采用热镀锌钢管等金属管材（GB50974-8.2.3）",
            category=FuncCategory.ATTR,
            clause_id="GB50974-8.2.3",
            target_entities={"piping", "pipe", "fire_main"},
            operator="ge",
            threshold=1.0,
            unit="级",
            depends_on=[],
        ),
        # ── P57 扩展 2026-07-14：GB50763 无障碍细则（8条）──
        AtomicFunction(
            func_id="DIM-048",
            name="无障碍门洞宽度判定",
            description="无障碍出入口门洞净宽度不应小于0.90m（GB50763-3.5.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50763-3.5.2",
            target_entities={"accessible_door", "door", "accessible_entrance"},
            operator="ge",
            threshold=0.90,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-049",
            name="无障碍电梯门洞宽度判定",
            description="无障碍电梯门洞净宽度不应小于0.90m（GB50763-3.7.2）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50763-3.7.2",
            target_entities={"accessible_elevator", "elevator", "elevator_door"},
            operator="ge",
            threshold=0.90,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIM-050",
            name="无障碍坡道长度判定",
            description="无障碍坡道每段最大高度0.75m时水平长度不应大于9.0m（GB50763-3.3.3）",
            category=FuncCategory.DIMENSION,
            clause_id="GB50763-3.3.3",
            target_entities={"ramp", "accessible_ramp"},
            operator="le",
            threshold=9.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="COUNT-008",
            name="无障碍停车位数量判定",
            description="应设不少于总停车位数2%的无障碍停车位（GB50763-3.11.1）",
            category=FuncCategory.COUNT,
            clause_id="GB50763-3.11.1",
            target_entities={"parking_space", "accessible_parking"},
            operator="ge",
            threshold=0.02,
            unit="比例",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-028",
            name="无障碍楼梯扶手判定",
            description="无障碍楼梯两侧应设扶手（GB50763-3.6.2）",
            category=FuncCategory.EXIST,
            clause_id="GB50763-3.6.2",
            target_entities={"handrail", "stair_handrail", "staircase"},
            operator="eq",
            threshold=1,
            unit="有/无",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="EXIST-029",
            name="无障碍标识判定",
            description="无障碍设施处应设无障碍标识（GB50763-3.16.1）",
            category=FuncCategory.EXIST,
            clause_id="GB50763-3.16.1",
            target_entities={"accessible_sign", "sign", "accessible_facility"},
            operator="eq",
            threshold=1,
            unit="有/无",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="DIST-014",
            name="无障碍卫生间距离判定",
            description="无障碍卫生间距最近无障碍出入口距离不应大于30m（GB50763-3.9.2）",
            category=FuncCategory.DISTANCE,
            clause_id="GB50763-3.9.2",
            target_entities={"accessible_toilet", "toilet", "restroom"},
            operator="le",
            threshold=30.0,
            unit="m",
            depends_on=[],
        ),
        AtomicFunction(
            func_id="AREA-006",
            name="无障碍住房面积判定",
            description="无障碍住房套内使用面积不应小于35.0sqm（GB50763-3.13.1）",
            category=FuncCategory.AREA,
            clause_id="GB50763-3.13.1",
            target_entities={"accessible_room", "room", "apartment"},
            operator="ge",
            threshold=35.0,
            unit="sqm",
            depends_on=[],
        ),
    ]  # code

    def __init__(self, timeout: int = 30):  # function: def __init__(self, timeout: int = 30):
        self._funcs: Dict[str, AtomicFunction] = {}  # assignment
        self._dependency_graph: Dict[str, List[str]] = {}  # 依赖图
        self._timeout = timeout  # assignment
        for func in self.INITIAL_FUNCS + self.RESERVED_FUNCS:  # 循环
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
        return 136  # 框架总容量：119 + 16 P57扩展2026-07-14（GB50974剩余8条+GB50763无障碍8条）+ 1预留
