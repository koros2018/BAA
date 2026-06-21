"""
BAA 自动图纸修正引擎
基于审查违规结果，生成具体的修正方案（修改建议 + 变更参数）

支持19条规范的修正建议生成：
- DIM类（尺寸不足）：计算需要增加的尺寸
- EXIST类（缺失构件）：建议添加何种构件及位置
- ATTR类（等级不足）：建议替换为指定等级
- COUNT类（数量不足）：建议增加数量
- DIST类（距离超标）：建议调整布局
- LIGHT类（照度不足）：建议增加照明
- AREA类（面积不足）：建议扩大面积
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class CorrectionAction(Enum):
    """修正操作类型"""
    RESIZE = "resize"              # 调整尺寸
    ADD = "add"                    # 增加构件
    REPLACE = "replace"            # 替换材料/等级
    RELOCATE = "relocate"          # 重新布局
    SEAL = "seal"                  # 封堵
    UPGRADE = "upgrade"            # 升级等级
    ENLARGE = "enlarge"            # 扩大面积
    ADD_LIGHTING = "add_lighting"  # 增加照明


@dataclass
class CorrectionSuggestion:
    """单条修正建议"""
    entity_id: str
    entity_type: str
    clause_id: str
    clause_title: str
    action: CorrectionAction
    description: str
    current_value: float
    required_value: float
    delta: float                    # 差值（正数=缺少多少）
    recommendation: str             # 具体建议
    parameters: Dict = field(default_factory=dict)  # 修正参数


# ── 修正建议模板库 ──────────────────────────────────────────

CORRECTION_TEMPLATES = {
    "DIM-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "staircase"),
        clause_id="GB50016-5.5.18",
        clause_title="疏散楼梯净宽",
        action=CorrectionAction.RESIZE,
        description=f"疏散楼梯净宽不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将楼梯宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m，需增加{r.delta:.2f}m。建议扩宽梯段或调整相邻房间布局。",
        parameters={"target_width": r.threshold, "increase_by": r.delta}
    ),
    "DIM-002": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "fire_zone"),
        clause_id="GB50016-6.1.1",
        clause_title="防火分区面积",
        action=CorrectionAction.RESIZE,
        description=f"防火分区面积超标：当前{r.actual:.0f}㎡，需要≤{r.threshold:.0f}㎡",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"防火分区面积超出{r.delta:.0f}㎡。建议：①增设防火隔墙划分分区；②采用防火卷帘或防火水幕进行分隔；③减少该分区内的可燃烧荷载。",
        parameters={"excess_area": r.delta, "max_allowed": r.threshold}
    ),
    "DIM-003": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "fire_lane"),
        clause_id="GB50016-7.1.1",
        clause_title="消防车道宽度",
        action=CorrectionAction.RESIZE,
        description=f"消防车道宽度不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将消防车道宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m，需增加{r.delta:.2f}m。建议移除车道两侧障碍物或拓宽路面。",
        parameters={"target_width": r.threshold, "increase_by": r.delta}
    ),
    "DIST-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "room"),
        clause_id="GB50016-5.5.17",
        clause_title="疏散距离",
        action=CorrectionAction.RELOCATE,
        description=f"疏散距离超标：当前{r.actual:.1f}m，需要≤{r.threshold:.1f}m",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"疏散距离超出{r.delta:.1f}m。建议：①增加安全出口位置；②调整房间布局使最远点靠近出口；③增设疏散走道连接至最近安全出口。",
        parameters={"excess_distance": r.delta, "max_allowed": r.threshold}
    ),
    "COUNT-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "floor"),
        clause_id="GB50016-5.5.8",
        clause_title="安全出口数量",
        action=CorrectionAction.ADD,
        description=f"安全出口数量不足：当前{r.actual:.0f}个，需要≥{r.threshold:.0f}个",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"需要增加{r.delta:.0f}个安全出口。建议：①在防火分区远端增设疏散门；②利用已有窗户改造为消防救援出口；③确保新增出口净宽≥0.9m。",
        parameters={"needed_exits": r.delta, "total_required": r.threshold}
    ),
    "ATTR-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "fire_door"),
        clause_id="GB50016-6.5.1",
        clause_title="防火门等级",
        action=CorrectionAction.REPLACE,
        description=f"防火门等级不足：当前等级{r.actual:.0f}，需要等级{r.threshold:.0f}",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将现有防火门更换为甲级防火门（耐火极限≥1.5h）。建议：①检查门框与墙体的防火密封；②更换防火五金件；③确保自闭器正常工作。",
        parameters={"required_rating": "甲级", "required_fire_resistance_h": 1.5}
    ),
    "DIM-004": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "corridor"),
        clause_id="GB50016-5.5.18",
        clause_title="疏散走道宽度",
        action=CorrectionAction.RESIZE,
        description=f"疏散走道宽度不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将走道宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m，需增加{r.delta:.2f}m。建议调整走道两侧墙体或减少走道内障碍物。",
        parameters={"target_width": r.threshold, "increase_by": r.delta}
    ),
    "AREA-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "refuge_floor"),
        clause_id="GB50016-7.4.1",
        clause_title="避难层面积",
        action=CorrectionAction.ENLARGE,
        description=f"避难层面积不足：当前{r.actual:.1f}㎡/人，需要≥{r.threshold:.1f}㎡/人",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"避难层有效面积需增加{r.delta:.1f}㎡/人。建议：①移除避难层内非必要隔墙和设备；②扩大避难区域范围；③减少该层可容纳人数。",
        parameters={"required_increase_per_person": r.delta}
    ),
    "EXIST-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "staircase"),
        clause_id="GB50016-5.5.12",
        clause_title="楼梯间设置",
        action=CorrectionAction.ADD,
        description="未检测到防烟楼梯间",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="一类高层公共建筑应设置防烟楼梯间。建议：①在适当位置增设防烟楼梯间；②确保楼梯间前室面积≥6㎡；③楼梯间应设置防烟设施。",
        parameters={"staircase_type": "防烟楼梯间"}
    ),
    "DIM-005": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "fire_window"),
        clause_id="GB50016-7.2.4",
        clause_title="消防窗面积",
        action=CorrectionAction.RESIZE,
        description=f"消防窗净面积不足：当前{r.actual:.2f}㎡，需要≥{r.threshold:.2f}㎡",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将消防救援窗面积从{r.actual:.2f}㎡扩大至{r.threshold:.2f}㎡。建议：①增大窗户开口尺寸；②改为推拉式或平开式以增加有效开口面积。",
        parameters={"target_area": r.threshold, "increase_by": r.delta}
    ),
    "DIM-006": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "exit_door"),
        clause_id="GB50016-5.5.19",
        clause_title="疏散门净宽",
        action=CorrectionAction.RESIZE,
        description=f"疏散门净宽不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将疏散门宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m。建议：①更换为更大尺寸的门扇；②将单开门改为双开门；③调整门洞位置避开结构柱。",
        parameters={"target_width": r.threshold, "increase_by": r.delta}
    ),
    "DIM-007": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "fire_curtain"),
        clause_id="GB50016-6.5.3",
        clause_title="防火卷帘宽度",
        action=CorrectionAction.RESIZE,
        description=f"防火卷帘宽度超标：当前{r.actual:.2f}m，需要≤{r.threshold:.2f}m",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"防火卷帘宽度超出{r.delta:.2f}m。建议：①将单幅卷帘拆分为多幅，每幅≤10m；②改用防火隔墙替代部分卷帘；③采用防火水幕系统替代。",
        parameters={"excess_width": r.delta, "max_allowed": r.threshold}
    ),
    "EXIST-002": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "shaft"),
        clause_id="GB50016-6.6.1",
        clause_title="管道井封堵",
        action=CorrectionAction.SEAL,
        description="管道井未封堵或封堵不完整",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="每层楼板处应采用不低于楼板耐火极限的不燃材料封堵。建议：①检查所有管道井穿越楼板处；②使用防火封堵材料（防火泥/防火板）封堵；③确保封堵密实无缝隙。",
        parameters={"sealing_material": "防火封堵材料"}
    ),
    "EXIST-003": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "scissor_staircase"),
        clause_id="GB50016-5.5.24",
        clause_title="剪刀楼梯分隔",
        action=CorrectionAction.ADD,
        description="剪刀楼梯梯段间未设置防火隔墙",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="剪刀楼梯梯段之间应设置耐火极限不低于1.0h的防火隔墙。建议：①在楼梯梯段之间增设防火隔墙；②隔墙应从基础到屋顶贯通。",
        parameters={"fire_wall_type": "耐火极限≥1.0h防火隔墙"}
    ),
    "EXIST-004": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "exit_sign"),
        clause_id="GB50016-10.3.1",
        clause_title="疏散指示标志",
        action=CorrectionAction.ADD,
        description="未检测到疏散指示标志",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="疏散走道和安全出口处应设置疏散指示标志。建议：①在走道转角处、交叉口设置标志；②安全出口正上方设置出口标志；③确保标志距地面高度≤1.0m；④采用消防应急标志灯。",
        parameters={"sign_type": "消防应急疏散指示标志"}
    ),
    "EXIST-005": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "sprinkler_system"),
        clause_id="GB50016-8.3.1",
        clause_title="自动灭火系统",
        action=CorrectionAction.ADD,
        description="未检测到自动灭火系统",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="一类高层公共建筑应设置自动灭火系统。建议：①安装自动喷水灭火系统；②喷头布置满足全覆盖要求；③确保消防水池容量满足持续喷水时间≥1h。",
        parameters={"system_type": "自动喷水灭火系统"}
    ),
    "EXIST-006": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "fire_alarm"),
        clause_id="GB50016-8.4.1",
        clause_title="火灾自动报警系统",
        action=CorrectionAction.ADD,
        description="未检测到火灾自动报警系统",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="一类高层公共建筑应设置火灾自动报警系统。建议：①安装感烟/感温探测器；②设置手动报警按钮；③报警信号应传至消防控制室。",
        parameters={"system_type": "火灾自动报警系统"}
    ),
    "ATTR-002": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "insulation"),
        clause_id="GB50016-6.7.1",
        clause_title="保温材料等级",
        action=CorrectionAction.REPLACE,
        description=f"保温材料等级不足：当前等级{r.actual:.0f}，需要≥{r.threshold:.0f}（A=3, B1=2）",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"将保温材料更换为A级（不燃材料）或B1级（难燃材料）。建议：①外保温系统采用岩棉板等A级材料；②内保温采用B1级以上材料；③注意防火隔离带设置。",
        parameters={"required_min_rating": "B1级", "preferred_rating": "A级"}
    ),
    "LIGHT-001": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "evacuation_lighting"),
        clause_id="GB50016-10.1.5",
        clause_title="应急照明照度",
        action=CorrectionAction.ADD_LIGHTING,
        description=f"疏散照明照度不足：当前{r.actual:.1f}lx，需要≥{r.threshold:.1f}lx",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"疏散照明照度需达到{r.threshold:.1f}lx。建议：①增加疏散照明灯具数量；②调整灯具间距（≤20m）；③确保应急电源持续供电时间≥0.5h；④选用消防应急照明灯具。",
        parameters={"required_illuminance": r.threshold, "min_lighting_duration_h": 0.5}
    ),
}


class CorrectionEngine:
    """图纸修正建议生成引擎"""

    def __init__(self):
        self._templates = CORRECTION_TEMPLATES

    def generate(self, findings: List[Dict], entities: List[Dict]) -> List[CorrectionSuggestion]:
        """根据审查结果生成修正建议

        Args:
            findings: 审查违规结果列表
            entities: 原始实体列表

        Returns:
            修正建议列表
        """
        suggestions = []
        entity_map = {e.get("id", ""): e for e in entities}

        for f in findings:
            clause_id = f.get("clause_id", "")
            entity_id = f.get("entity_id", "")
            entity = entity_map.get(entity_id, {})
            func_id = self._clause_to_func(clause_id)

            # 创建简易 FuncResult 对象供模板使用
            result = _FuncResult(
                actual=f.get("extracted_value", 0),
                threshold=f.get("required_value", 0),
                delta=f.get("difference", 0),
            )

            template = self._templates.get(func_id)
            if template:
                try:
                    suggestion = template(entity, result)
                    suggestions.append(suggestion)
                except Exception:
                    pass

        return suggestions

    def generate_for_result(self, review_result: dict) -> List[Dict]:
        """从 /review 返回结果生成修正建议（用于API返回）

        Args:
            review_result: /review 端点的完整返回

        Returns:
            修正建议列表（可序列化为JSON）
        """
        findings = review_result.get("findings", [])
        suggestions = self.generate(findings, [])

        output = []
        for s in suggestions:
            output.append({
                "entity_id": s.entity_id,
                "entity_type": s.entity_type,
                "clause_id": s.clause_id,
                "clause_title": s.clause_title,
                "action": s.action.value,
                "description": s.description,
                "recommendation": s.recommendation,
                "parameters": s.parameters,
                "priority": self._calc_priority(s),
            })
        return output

    @staticmethod
    def _clause_to_func(clause_id: str) -> str:
        """规范ID → 原子函数ID（简化映射）"""
        mapping = {
            "GB50016-5.5.18": "DIM-001",
            "GB50016-5.5.18-2": "DIM-004",
            "GB50016-6.1.1": "DIM-002",
            "GB50016-7.1.1": "DIM-003",
            "GB50016-5.5.17": "DIST-001",
            "GB50016-5.5.8": "COUNT-001",
            "GB50016-6.5.1": "ATTR-001",
            "GB50016-7.4.1": "AREA-001",
            "GB50016-5.5.12": "EXIST-001",
            "GB50016-7.2.4": "DIM-005",
            "GB50016-5.5.19": "DIM-006",
            "GB50016-6.5.3": "DIM-007",
            "GB50016-6.6.1": "EXIST-002",
            "GB50016-5.5.24": "EXIST-003",
            "GB50016-10.3.1": "EXIST-004",
            "GB50016-8.3.1": "EXIST-005",
            "GB50016-8.4.1": "EXIST-006",
            "GB50016-6.7.1": "ATTR-002",
            "GB50016-10.1.5": "LIGHT-001",
        }
        return mapping.get(clause_id, "")

    @staticmethod
    def _calc_priority(s: CorrectionSuggestion) -> str:
        """计算修正优先级"""
        urgent_categories = {"ADD", "REPLACE", "UPGRADE"}
        if s.action.value in {a.value for a in [CorrectionAction.ADD, CorrectionAction.REPLACE, CorrectionAction.UPGRADE]}:
            return "high"
        if s.delta > s.required_value * 0.5:
            return "high"
        if s.delta > s.required_value * 0.2:
            return "medium"
        return "low"


class _FuncResult:
    """内部简易结果对象"""
    def __init__(self, actual: float, threshold: float, delta: float):
        self.actual = actual
        self.threshold = threshold
        self.delta = delta
        self.result = "FAIL" if delta > 0 else "PASS"
