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

from typing import Dict, List
from dataclasses import dataclass, field
from enum import Enum


class CorrectionAction(Enum):  # 类定义: CorrectionAction
    """修正操作类型"""

    RESIZE = "resize"  # 调整尺寸
    ADD = "add"  # 增加构件
    REPLACE = "replace"  # 替换材料/等级
    RELOCATE = "relocate"  # 重新布局
    SEAL = "seal"  # 封堵
    UPGRADE = "upgrade"  # 升级等级
    ENLARGE = "enlarge"  # 扩大面积
    ADD_LIGHTING = "add_lighting"  # 增加照明


@dataclass  # 装饰器
class CorrectionSuggestion:  # 类定义: CorrectionSuggestion
    """单条修正建议"""

    entity_id: str  # 操作
    entity_type: str  # 操作
    clause_id: str  # 操作
    clause_title: str  # 操作
    action: CorrectionAction  # 操作
    description: str  # 操作
    current_value: float  # 操作
    required_value: float  # 操作
    delta: float  # 差值（正数=缺少多少）
    recommendation: str  # 具体建议
    parameters: Dict = field(default_factory=dict)  # 修正参数


# ── 修正建议模板库 ──────────────────────────────────────────

CORRECTION_TEMPLATES = {  # 赋值: CORRECTION_TEMPLATES
    "DIM-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "staircase"),  # 安全获取值
        clause_id="GB50016-5.5.18",  # 赋值: clause_id
        clause_title="疏散楼梯净宽",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"疏散楼梯净宽不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将楼梯宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m，需增加{r.delta:.2f}m。建议扩宽梯段或调整相邻房间布局。",  # 赋值: recommendation
        parameters={"target_width": r.threshold, "increase_by": r.delta},  # 赋值: parameters
    ),
    "DIM-002": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "fire_zone"),  # 安全获取值
        clause_id="GB50016-6.1.1",  # 赋值: clause_id
        clause_title="防火分区面积",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"防火分区面积超标：当前{r.actual:.0f}㎡，需要≤{r.threshold:.0f}㎡",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"防火分区面积超出{r.delta:.0f}㎡。建议：①增设防火隔墙划分分区；②采用防火卷帘或防火水幕进行分隔；③减少该分区内的可燃烧荷载。",  # 赋值: recommendation
        parameters={"excess_area": r.delta, "max_allowed": r.threshold},  # 赋值: parameters
    ),
    "DIM-003": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "fire_lane"),  # 安全获取值
        clause_id="GB50016-7.1.1",  # 赋值: clause_id
        clause_title="消防车道宽度",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"消防车道宽度不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将消防车道宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m，需增加{r.delta:.2f}m。建议移除车道两侧障碍物或拓宽路面。",  # 赋值: recommendation
        parameters={"target_width": r.threshold, "increase_by": r.delta},  # 赋值: parameters
    ),
    "DIST-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "room"),  # 安全获取值
        clause_id="GB50016-5.5.17",  # 赋值: clause_id
        clause_title="疏散距离",  # 赋值: clause_title
        action=CorrectionAction.RELOCATE,  # 赋值: action
        description=f"疏散距离超标：当前{r.actual:.1f}m，需要≤{r.threshold:.1f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"疏散距离超出{r.delta:.1f}m。建议：①增加安全出口位置；②调整房间布局使最远点靠近出口；③增设疏散走道连接至最近安全出口。",  # 赋值: recommendation
        parameters={"excess_distance": r.delta, "max_allowed": r.threshold},  # 赋值: parameters
    ),
    "COUNT-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "floor"),  # 安全获取值
        clause_id="GB50016-5.5.8",  # 赋值: clause_id
        clause_title="安全出口数量",  # 赋值: clause_title
        action=CorrectionAction.ADD,  # 赋值: action
        description=f"安全出口数量不足：当前{r.actual:.0f}个，需要≥{r.threshold:.0f}个",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"需要增加{r.delta:.0f}个安全出口。建议：①在防火分区远端增设疏散门；②利用已有窗户改造为消防救援出口；③确保新增出口净宽≥0.9m。",  # 赋值: recommendation
        parameters={"needed_exits": r.delta, "total_required": r.threshold},  # 赋值: parameters
    ),
    "ATTR-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "fire_door"),  # 安全获取值
        clause_id="GB50016-6.5.1",  # 赋值: clause_id
        clause_title="防火门等级",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"防火门等级不足：当前等级{r.actual:.0f}，需要等级{r.threshold:.0f}",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将现有防火门更换为甲级防火门（耐火极限≥1.5h）。建议：①检查门框与墙体的防火密封；②更换防火五金件；③确保自闭器正常工作。",  # 赋值: recommendation
        parameters={
            "required_rating": "甲级",
            "required_fire_resistance_h": 1.5,
        },  # 赋值: parameters
    ),
    "DIM-004": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "corridor"),  # 安全获取值
        clause_id="GB50016-5.5.18",  # 赋值: clause_id
        clause_title="疏散走道宽度",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"疏散走道宽度不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将走道宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m，需增加{r.delta:.2f}m。建议调整走道两侧墙体或减少走道内障碍物。",  # 赋值: recommendation
        parameters={"target_width": r.threshold, "increase_by": r.delta},  # 赋值: parameters
    ),
    "AREA-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "refuge_floor"),  # 安全获取值
        clause_id="GB50016-7.4.1",  # 赋值: clause_id
        clause_title="避难层面积",  # 赋值: clause_title
        action=CorrectionAction.ENLARGE,  # 赋值: action
        description=f"避难层面积不足：当前{r.actual:.1f}㎡/人，需要≥{r.threshold:.1f}㎡/人",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"避难层有效面积需增加{r.delta:.1f}㎡/人。建议：①移除避难层内非必要隔墙和设备；②扩大避难区域范围；③减少该层可容纳人数。",  # 赋值: recommendation
        parameters={"required_increase_per_person": r.delta},  # 赋值: parameters
    ),
    "EXIST-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "staircase"),  # 安全获取值
        clause_id="GB50016-5.5.12",  # 赋值: clause_id
        clause_title="楼梯间设置",  # 赋值: clause_title
        action=CorrectionAction.ADD,  # 赋值: action
        description="未检测到防烟楼梯间",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation="一类高层公共建筑应设置防烟楼梯间。建议：①在适当位置增设防烟楼梯间；②确保楼梯间前室面积≥6㎡；③楼梯间应设置防烟设施。",  # 赋值: recommendation
        parameters={"staircase_type": "防烟楼梯间"},  # 赋值: parameters
    ),
    "DIM-005": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "fire_window"),  # 安全获取值
        clause_id="GB50016-7.2.4",  # 赋值: clause_id
        clause_title="消防窗面积",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"消防窗净面积不足：当前{r.actual:.2f}㎡，需要≥{r.threshold:.2f}㎡",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将消防救援窗面积从{r.actual:.2f}㎡扩大至{r.threshold:.2f}㎡。建议：①增大窗户开口尺寸；②改为推拉式或平开式以增加有效开口面积。",  # 赋值: recommendation
        parameters={"target_area": r.threshold, "increase_by": r.delta},  # 赋值: parameters
    ),
    "DIM-006": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "exit_door"),  # 安全获取值
        clause_id="GB50016-5.5.19",  # 赋值: clause_id
        clause_title="疏散门净宽",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"疏散门净宽不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将疏散门宽度从{r.actual:.2f}m加宽至{r.threshold:.2f}m。建议：①更换为更大尺寸的门扇；②将单开门改为双开门；③调整门洞位置避开结构柱。",  # 赋值: recommendation
        parameters={"target_width": r.threshold, "increase_by": r.delta},  # 赋值: parameters
    ),
    "DIM-007": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "fire_curtain"),  # 安全获取值
        clause_id="GB50016-6.5.3",  # 赋值: clause_id
        clause_title="防火卷帘宽度",  # 赋值: clause_title
        action=CorrectionAction.RESIZE,  # 赋值: action
        description=f"防火卷帘宽度超标：当前{r.actual:.2f}m，需要≤{r.threshold:.2f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"防火卷帘宽度超出{r.delta:.2f}m。建议：①将单幅卷帘拆分为多幅，每幅≤10m；②改用防火隔墙替代部分卷帘；③采用防火水幕系统替代。",  # 赋值: recommendation
        parameters={"excess_width": r.delta, "max_allowed": r.threshold},  # 赋值: parameters
    ),
    "EXIST-002": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "shaft"),  # 安全获取值
        clause_id="GB50016-6.6.1",  # 赋值: clause_id
        clause_title="管道井封堵",  # 赋值: clause_title
        action=CorrectionAction.SEAL,  # 赋值: action
        description="管道井未封堵或封堵不完整",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation="每层楼板处应采用不低于楼板耐火极限的不燃材料封堵。建议：①检查所有管道井穿越楼板处；②使用防火封堵材料（防火泥/防火板）封堵；③确保封堵密实无缝隙。",  # 赋值: recommendation
        parameters={"sealing_material": "防火封堵材料"},  # 赋值: parameters
    ),
    "EXIST-003": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "scissor_staircase"),  # 安全获取值
        clause_id="GB50016-5.5.24",  # 赋值: clause_id
        clause_title="剪刀楼梯分隔",  # 赋值: clause_title
        action=CorrectionAction.ADD,  # 赋值: action
        description="剪刀楼梯梯段间未设置防火隔墙",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation="剪刀楼梯梯段之间应设置耐火极限不低于1.0h的防火隔墙。建议：①在楼梯梯段之间增设防火隔墙；②隔墙应从基础到屋顶贯通。",  # 赋值: recommendation
        parameters={"fire_wall_type": "耐火极限≥1.0h防火隔墙"},  # 赋值: parameters
    ),
    "EXIST-004": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "exit_sign"),  # 安全获取值
        clause_id="GB50016-10.3.1",  # 赋值: clause_id
        clause_title="疏散指示标志",  # 赋值: clause_title
        action=CorrectionAction.ADD,  # 赋值: action
        description="未检测到疏散指示标志",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation="疏散走道和安全出口处应设置疏散指示标志。建议：①在走道转角处、交叉口设置标志；②安全出口正上方设置出口标志；③确保标志距地面高度≤1.0m；④采用消防应急标志灯。",  # 赋值: recommendation
        parameters={"sign_type": "消防应急疏散指示标志"},  # 赋值: parameters
    ),
    "EXIST-005": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "sprinkler_system"),  # 安全获取值
        clause_id="GB50016-8.3.1",  # 赋值: clause_id
        clause_title="自动灭火系统",  # 赋值: clause_title
        action=CorrectionAction.ADD,  # 赋值: action
        description="未检测到自动灭火系统",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation="一类高层公共建筑应设置自动灭火系统。建议：①安装自动喷水灭火系统；②喷头布置满足全覆盖要求；③确保消防水池容量满足持续喷水时间≥1h。",  # 赋值: recommendation
        parameters={"system_type": "自动喷水灭火系统"},  # 赋值: parameters
    ),
    "EXIST-006": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "fire_alarm"),  # 安全获取值
        clause_id="GB50016-8.4.1",  # 赋值: clause_id
        clause_title="火灾自动报警系统",  # 赋值: clause_title
        action=CorrectionAction.ADD,  # 赋值: action
        description="未检测到火灾自动报警系统",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation="一类高层公共建筑应设置火灾自动报警系统。建议：①安装感烟/感温探测器；②设置手动报警按钮；③报警信号应传至消防控制室。",  # 赋值: recommendation
        parameters={"system_type": "火灾自动报警系统"},  # 赋值: parameters
    ),
    "ATTR-002": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "insulation"),  # 安全获取值
        clause_id="GB50016-6.7.1",  # 赋值: clause_id
        clause_title="保温材料等级",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"保温材料等级不足：当前等级{r.actual:.0f}，需要≥{r.threshold:.0f}（A=3, B1=2）",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"将保温材料更换为A级（不燃材料）或B1级（难燃材料）。建议：①外保温系统采用岩棉板等A级材料；②内保温采用B1级以上材料；③注意防火隔离带设置。",  # 赋值: recommendation
        parameters={"required_min_rating": "B1级", "preferred_rating": "A级"},  # 赋值: parameters
    ),
    "LIGHT-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "evacuation_lighting"),  # 安全获取值
        clause_id="GB50016-10.1.5",  # 赋值: clause_id
        clause_title="应急照明照度",  # 赋值: clause_title
        action=CorrectionAction.ADD_LIGHTING,  # 赋值: action
        description=f"疏散照明照度不足：当前{r.actual:.1f}lx，需要≥{r.threshold:.1f}lx",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"疏散照明照度需达到{r.threshold:.1f}lx。建议：①增加疏散照明灯具数量；②调整灯具间距（≤20m）；③确保应急电源持续供电时间≥0.5h；④选用消防应急照明灯具。",  # 赋值: recommendation
        parameters={
            "required_illuminance": r.threshold,
            "min_lighting_duration_h": 0.5,
        },  # 赋值: parameters
    ),
    # ── 热工性能修正建议（P45）────────────────────────────
    "THERM-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "exterior_wall"),  # 安全获取值
        clause_id="GB55015-3.2.2",  # 赋值: clause_id
        clause_title="外墙传热系数",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"外墙传热系数超标：当前{r.actual:.3f} W/(m²·K)，需要≤{r.threshold:.3f} W/(m²·K)",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"外墙K值需降至{r.threshold:.3f} W/(m²·K)以下。建议：①加厚外墙保温层（岩棉/聚苯板）；②采用外保温系统；③消除热桥部位保温连续性。",  # 赋值: recommendation
        parameters={"target_k_value": r.threshold, "current_k_value": r.actual},  # 赋值: parameters
    ),
    "THERM-002": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "roof"),  # 安全获取值
        clause_id="GB55015-3.2.2",  # 赋值: clause_id
        clause_title="屋顶传热系数",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"屋顶传热系数超标：当前{r.actual:.3f} W/(m²·K)，需要≤{r.threshold:.3f} W/(m²·K)",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"屋顶K值需降至{r.threshold:.3f} W/(m²·K)以下。建议：①加厚屋顶保温层（聚氨酯/岩棉）；②设置通风隔热层；③采用反射屋面或种植屋面。",  # 赋值: recommendation
        parameters={"target_k_value": r.threshold, "current_k_value": r.actual},  # 赋值: parameters
    ),
    "THERM-004": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "exterior_window"),  # 安全获取值
        clause_id="GB55015-3.2.2",  # 赋值: clause_id
        clause_title="外窗传热系数",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"外窗传热系数超标：当前{r.actual:.3f} W/(m²·K)，需要≤{r.threshold:.3f} W/(m²·K)",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"外窗K值需降至{r.threshold:.3f} W/(m²·K)以下。建议：①更换为断热铝合金/塑钢窗；②采用双层或三层中空玻璃；③充惰性气体（氩气）。",  # 赋值: recommendation
        parameters={"target_k_value": r.threshold, "current_k_value": r.actual},  # 赋值: parameters
    ),
    "THERM-008": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "insulation"),  # 安全获取值
        clause_id="GB55015-3.2.2",  # 赋值: clause_id
        clause_title="外墙保温层厚度",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"外墙保温层厚度不足：当前{r.actual:.1f}mm，需要≥{r.threshold:.1f}mm",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"外墙保温层需增厚至{r.threshold:.1f}mm以上。建议按实际K值反算所需厚度，优先采用外保温系统。",  # 赋值: recommendation
        parameters={
            "min_thickness_mm": r.threshold,
            "current_thickness_mm": r.actual,
        },  # 赋值: parameters
    ),
    "THERM-012": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "exterior_window"),  # 安全获取值
        clause_id="GB7106-5.1",  # 赋值: clause_id
        clause_title="外窗气密性等级",  # 赋值: clause_title
        action=CorrectionAction.UPGRADE,  # 赋值: action
        description=f"外窗气密性等级不足：当前{r.actual:.0f}级，需要≥{r.threshold:.0f}级",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"外窗气密性需提升至{r.threshold:.0f}级以上。建议：①更换为高气密性窗型（如内开内倒、推拉窗改为平开窗）；②加强密封胶条；③提高五金件密封性能。",  # 赋值: recommendation
        parameters={
            "target_sealing_level": r.threshold,
            "current_sealing_level": r.actual,
        },  # 赋值: parameters
    ),
    # ── 热工性能修正建议（P45 补全 11 条）────────────────
    "THERM-003": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "ground_floor"),
        clause_id="GB55015-3.2.2",
        clause_title="地面传热系数",
        action=CorrectionAction.REPLACE,
        description=f"地面传热系数超标：当前{r.actual:.3f} W/(m²·K)，需要≤{r.threshold:.3f} W/(m²·K)",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"地面K值需降至{r.threshold:.3f} W/(m²·K)以下。建议：①铺设地面保温层（挤塑板/聚氨酯板）；②设置断热层；③采用架空地板加保温填充。",
        parameters={"target_k_value": r.threshold, "current_k_value": r.actual},
    ),
    "THERM-005": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "window_glass"),
        clause_id="GB55015-3.2.2",
        clause_title="外窗玻璃传热系数",
        action=CorrectionAction.REPLACE,
        description=f"外窗玻璃传热系数超标：当前{r.actual:.3f} W/(m²·K)，需要≤{r.threshold:.3f} W/(m²·K)",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"玻璃K值需降至{r.threshold:.3f} W/(m²·K)以下。建议：①采用中空玻璃（双层/三层）；②Low-E 镀膜玻璃；③充氩气中空玻璃。",
        parameters={"target_k_value": r.threshold, "current_k_value": r.actual},
    ),
    "THERM-006": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "exterior_window"),
        clause_id="GB50189-6.3.4",
        clause_title="外窗遮阳系数",
        action=CorrectionAction.ADD,
        description=f"外窗遮阳系数Sc超标：当前{r.actual:.3f}，需要≤{r.threshold:.3f}",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"外窗遮阳系数需降至{r.threshold:.3f}以下。建议：①加装外遮阳百叶或卷帘；②采用镀膜玻璃；③设置绿化/雨棚遮阳；④采用低遮阳玻璃。",
        parameters={
            "target_shading_coefficient": r.threshold,
            "current_shading_coefficient": r.actual,
        },
    ),
    "THERM-007": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "wall"),
        clause_id="GB55015-3.2.2",
        clause_title="窗墙面积比",
        action=CorrectionAction.REVIEW,
        description=f"窗墙比超标：当前{r.actual:.3f}，需要≤{r.threshold:.3f}",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"窗墙比需控制在{r.threshold:.3f}以下。建议：①调整外立面开窗面积；②缩小开窗尺寸；③采用竖向分窗减小单扇窗面积；④结合遮阳设计减少有效窗面积。",
        parameters={"target_window_wall_ratio": r.threshold, "current_window_wall_ratio": r.actual},
    ),
    "THERM-009": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "roof_insulation"),
        clause_id="GB55015-3.2.2",
        clause_title="屋顶保温层厚度",
        action=CorrectionAction.REPLACE,
        description=f"屋顶保温层厚度不足：当前{r.actual:.1f}mm，需要≥{r.threshold:.1f}mm",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"屋顶保温层需增厚至{r.threshold:.1f}mm以上。建议按实际K值反算所需厚度，优先采用屋面内保温或外保温系统。",
        parameters={"min_thickness_mm": r.threshold, "current_thickness_mm": r.actual},
    ),
    "THERM-010": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "window_insulation"),
        clause_id="GB55015-3.2.2",
        clause_title="外窗保温层厚度",
        action=CorrectionAction.REPLACE,
        description=f"外窗保温层厚度不足：当前{r.actual:.1f}mm，需要≥{r.threshold:.1f}mm",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"外窗保温层需增厚至{r.threshold:.1f}mm以上。建议：①采用断热铝合金型材；②增加窗框保温芯材厚度；③选用三玻两腔窗型。",
        parameters={"min_thickness_mm": r.threshold, "current_thickness_mm": r.actual},
    ),
    "THERM-011": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "thermal_bridge"),
        clause_id="GB50176-4.3.3",
        clause_title="热桥部位保温连续性",
        action=CorrectionAction.REVIEW,
        description=f"热桥部位保温不连续：当前值{r.actual:.0f}（1=连续，0=不连续），需要={r.threshold:.0f}（连续）",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="热桥部位需采取保温连续措施。建议：①外墙与内墙连接处设保温过渡层；②梁柱节点采用保温包裹；③楼板边缘设置保温边条；④消除结构热桥。",
        parameters={"required_continuity": r.threshold, "current_continuity": r.actual},
    ),
    "THERM-013": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "exterior_window"),
        clause_id="GB50016-6.3.2",
        clause_title="外窗存在判定",
        action=CorrectionAction.ADD,
        description=f"外窗缺失：当前{r.actual:.0f}（1=有，0=无），需要={r.threshold:.0f}（有）",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="建筑外墙应设置外窗以保证通风采光。建议：①在缺失位置增设外窗；②若结构不允许开窗，采用通风设备或采光板替代。",
        parameters={"required_window_presence": r.threshold, "current_window_presence": r.actual},
    ),
    "THERM-014": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "exterior_wall"),
        clause_id="GB55015-3.2.2",
        clause_title="外墙保温面积比",
        action=CorrectionAction.ADD,
        description=f"外墙保温面积比不足：当前{r.actual:.1%}，需要≥{r.threshold:.1%}",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"外墙保温面积比需达到{r.threshold:.1%}以上。建议：①将局部保温改为全墙保温；②采用外保温系统覆盖全部外墙面积；③热桥部位补强保温。",
        parameters={"target_insulation_ratio": r.threshold, "current_insulation_ratio": r.actual},
    ),
    "THERM-015": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "roof"),
        clause_id="GB55015-3.2.2",
        clause_title="屋顶保温面积比",
        action=CorrectionAction.ADD,
        description=f"屋顶保温面积比不足：当前{r.actual:.1%}，需要≥{r.threshold:.1%}",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"屋顶保温面积比需达到{r.threshold:.1%}以上。建议：①全屋面铺设保温层；②阁楼/坡屋顶增设保温覆盖；③天窗周边加强保温。",
        parameters={"target_insulation_ratio": r.threshold, "current_insulation_ratio": r.actual},
    ),
    "THERM-016": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "exterior_window"),
        clause_id="GB55015-3.2.2",
        clause_title="外窗综合传热系数",
        action=CorrectionAction.REPLACE,
        description=f"外窗综合传热系数超标：当前{r.actual:.3f} W/(m²·K)，需要≤{r.threshold:.3f} W/(m²·K)",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"外窗综合K值需降至{r.threshold:.3f} W/(m²·K)以下。建议：①更换为高性能窗型；②优化窗框/玻璃组合；③控制窗墙比以平衡综合传热。",
        parameters={"target_k_value": r.threshold, "current_k_value": r.actual},
    ),
    # ── 结构荷载修正建议（P46）────────────────────────────
    "STR-001": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "floor"),  # 安全获取值
        clause_id="GB50009-5.1.1",  # 赋值: clause_id
        clause_title="楼面活荷载",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"楼面活荷载不足：当前{r.actual:.2f} kN/㎡，需要≥{r.threshold:.2f} kN/㎡",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"楼面活荷载需提升至{r.threshold:.2f} kN/㎡以上。建议：①复核楼板厚度及配筋；②采用高强度混凝土；③必要时增设梁或提高结构等级。",  # 赋值: recommendation
        parameters={
            "required_load_kN_m2": r.threshold,
            "current_load_kN_m2": r.actual,
        },  # 赋值: parameters
    ),
    "STR-005": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "beam"),  # 安全获取值
        clause_id="GB50010-9.2.1",  # 赋值: clause_id
        clause_title="梁最小配筋率",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"梁配筋率不足：当前{r.actual:.3f}%，需要≥{r.threshold:.3f}%",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"梁受拉纵筋配筋率需≥{r.threshold:.3f}%。建议：①增大受拉钢筋直径或数量；②提高混凝土等级；③复核梁截面尺寸。",  # 赋值: recommendation
        parameters={
            "min_reinforcement_ratio": r.threshold,
            "current_reinforcement_ratio": r.actual,
        },  # 赋值: parameters
    ),
    "STR-008": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "foundation"),  # 安全获取值
        clause_id="GB50007-5.1.3",  # 赋值: clause_id
        clause_title="基础埋深",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"基础埋深不足：当前{r.actual:.2f}m，需要≥{r.threshold:.2f}m",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"基础埋深需≥{r.threshold:.2f}m。建议：①加深基础；②采用桩基础；③考虑冻结深度影响。",  # 赋值: recommendation
        parameters={"min_depth_m": r.threshold, "current_depth_m": r.actual},  # 赋值: parameters
    ),
    "STR-014": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "concrete"),  # 安全获取值
        clause_id="GB50010-4.1.2",  # 赋值: clause_id
        clause_title="混凝土强度等级",  # 赋值: clause_title
        action=CorrectionAction.UPGRADE,  # 赋值: action
        description=f"混凝土强度不足：当前{r.actual:.0f}MPa，需要≥{r.threshold:.0f}MPa",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"混凝土强度等级需提升至C{r.threshold:.0f}以上。建议：①改用高强度水泥；②添加矿物掺合料（粉煤灰/矿渣）；③调整水胶比和养护工艺。",  # 赋值: recommendation
        parameters={
            "min_concrete_grade_MPa": r.threshold,
            "current_concrete_grade_MPa": r.actual,
        },  # 赋值: parameters
    ),
    "STR-015": lambda e, r: CorrectionSuggestion(  # 模板定义
        entity_id=e.get("id", ""),  # 安全获取值
        entity_type=e.get("type", "slab"),  # 安全获取值
        clause_id="GB50010-9.1.2",  # 赋值: clause_id
        clause_title="楼板厚度",  # 赋值: clause_title
        action=CorrectionAction.REPLACE,  # 赋值: action
        description=f"楼板厚度不足：当前{r.actual:.1f}mm，需要≥{r.threshold:.1f}mm",  # 赋值: description
        current_value=r.actual,  # 赋值: current_value
        required_value=r.threshold,  # 赋值: required_value
        delta=r.delta,  # 赋值: delta
        recommendation=f"楼板厚度需≥{r.threshold:.1f}mm。建议：①增大楼板厚度；②增加配筋量；③采用预应力混凝土。",  # 赋值: recommendation
        parameters={
            "min_slab_thickness_mm": r.threshold,
            "current_slab_thickness_mm": r.actual,
        },  # 赋值: parameters
    ),
    # ── 结构荷载修正建议（P46 补全 11 条）────────────────
    "STR-002": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "floor"),
        clause_id="GB50009-5.1.1",
        clause_title="办公楼面活荷载",
        action=CorrectionAction.REPLACE,
        description=f"办公楼面活荷载不足：当前{r.actual:.2f} kN/㎡，需要≥{r.threshold:.2f} kN/㎡",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"办公楼面活荷载需≥{r.threshold:.2f} kN/㎡。建议：①复核楼板截面与配筋；②提高混凝土强度等级；③增加楼板厚度或设次梁分担荷载。",
        parameters={"required_load_kN_m2": r.threshold, "current_load_kN_m2": r.actual},
    ),
    "STR-003": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "floor"),
        clause_id="GB50009-5.1.1",
        clause_title="商业楼面活荷载",
        action=CorrectionAction.REPLACE,
        description=f"商业楼面活荷载不足：当前{r.actual:.2f} kN/㎡，需要≥{r.threshold:.2f} kN/㎡",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"商业楼面活荷载需≥{r.threshold:.2f} kN/㎡。建议：①按商业荷载等级复核楼板设计；②采用重载楼板构造（厚板+双向配筋）；③必要时增设柱子。",
        parameters={"required_load_kN_m2": r.threshold, "current_load_kN_m2": r.actual},
    ),
    "STR-004": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "roof"),
        clause_id="GB50009-5.1.1",
        clause_title="屋面活荷载",
        action=CorrectionAction.REPLACE,
        description=f"屋面活荷载不足：当前{r.actual:.2f} kN/㎡，需要≥{r.threshold:.2f} kN/㎡",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"屋面活荷载需≥{r.threshold:.2f} kN/㎡（上人屋面）。建议：①复核屋面荷载等级；②上人屋面按2.0 kN/㎡设计；③不上人屋面按0.5 kN/㎡设计。",
        parameters={"required_load_kN_m2": r.threshold, "current_load_kN_m2": r.actual},
    ),
    "STR-006": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "column"),
        clause_id="GB50010-11.4.12",
        clause_title="柱纵向配筋率下限",
        action=CorrectionAction.ADD,
        description=f"柱纵向配筋率不足：当前{r.actual:.2f}%，需要≥{r.threshold:.2f}%",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"柱纵筋配筋率需≥{r.threshold:.2f}%。建议：①增加纵向钢筋数量；②增大钢筋直径；③必要时增大柱截面尺寸。",
        parameters={
            "min_reinforcement_ratio": r.threshold,
            "current_reinforcement_ratio": r.actual,
        },
    ),
    "STR-007": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "column"),
        clause_id="GB50010-11.4.12",
        clause_title="柱纵向配筋率上限",
        action=CorrectionAction.REPLACE,
        description=f"柱纵向配筋率过高：当前{r.actual:.2f}%，需要≤{r.threshold:.2f}%",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"柱纵筋配筋率需≤{r.threshold:.2f}%。建议：①减少纵向钢筋数量；②增大柱截面以降低配筋率；③避免钢筋拥挤影响混凝土浇筑。",
        parameters={
            "max_reinforcement_ratio": r.threshold,
            "current_reinforcement_ratio": r.actual,
        },
    ),
    "STR-009": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "pile"),
        clause_id="GB55008-4.1.1",
        clause_title="桩基础数量",
        action=CorrectionAction.ADD,
        description=f"桩基数量不足：当前{r.actual:.0f}根，需要≥{r.threshold:.0f}根",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"桩基数量需≥{r.threshold:.0f}根。建议：①增加桩基数量满足规范要求；②按桩基承载力复核桩数；③考虑桩基布置对称性。",
        parameters={"min_pile_count": r.threshold, "current_pile_count": r.actual},
    ),
    "STR-010": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "shear_wall"),
        clause_id="GB55008-4.3.1",
        clause_title="剪力墙洞口面积比",
        action=CorrectionAction.REVIEW,
        description=f"剪力墙洞口面积比超标：当前{r.actual:.1%}，需要≤{r.threshold:.1%}",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"剪力墙洞口面积比需≤{r.threshold:.1%}。建议：①减少洞口数量或尺寸；②增设边缘构件加强洞口周边；③必要时改为框支剪力墙体系。",
        parameters={"max_opening_ratio": r.threshold, "current_opening_ratio": r.actual},
    ),
    "STR-011": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "shear_wall"),
        clause_id="GB55008-4.3.1",
        clause_title="墙肢最小厚度",
        action=CorrectionAction.REPLACE,
        description=f"剪力墙墙肢厚度不足：当前{r.actual:.1f}mm，需要≥{r.threshold:.1f}mm",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"墙肢厚度需≥{r.threshold:.1f}mm。建议：①增大剪力墙厚度；②增设暗柱加强墙肢边缘；③框支层墙肢厚度需≥200mm。",
        parameters={"min_wall_thickness_mm": r.threshold, "current_wall_thickness_mm": r.actual},
    ),
    "STR-012": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "building"),
        clause_id="GB55008-3.1.1",
        clause_title="抗震设防烈度",
        action=CorrectionAction.UPGRADE,
        description=f"抗震设防烈度不足：当前{r.actual:.0f}度，需要≥{r.threshold:.0f}度",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"抗震设防烈度需≥{r.threshold:.0f}度。建议：①按当地抗震设防要求提高设计烈度；②复核地震动参数；③调整抗震构造措施。",
        parameters={
            "required_seismic_intensity": r.threshold,
            "current_seismic_intensity": r.actual,
        },
    ),
    "STR-013": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "building"),
        clause_id="GB55008-3.2.1",
        clause_title="抗震等级标注",
        action=CorrectionAction.ADD,
        description=f"抗震等级未标注：当前{r.actual:.0f}（1=有，0=无），需要={r.threshold:.0f}（有）",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation="抗震设计建筑应明确标注抗震等级。建议：①在设计文件中补充抗震等级标注；②根据设防烈度和建筑类型确定抗震等级。",
        parameters={"required_seismic_grade": r.threshold, "current_seismic_grade": r.actual},
    ),
    "STR-016": lambda e, r: CorrectionSuggestion(
        entity_id=e.get("id", ""),
        entity_type=e.get("type", "beam"),
        clause_id="GB50010-9.2.3",
        clause_title="梁截面最小高度",
        action=CorrectionAction.REPLACE,
        description=f"梁截面高度不足：当前{r.actual:.3f}（高跨比），需要≥{r.threshold:.3f}（高跨比≥1/12≈0.083）",
        current_value=r.actual,
        required_value=r.threshold,
        delta=r.delta,
        recommendation=f"梁高需满足高跨比≥{r.threshold:.3f}（约1/12）。建议：①增大梁高；②减少梁跨度；③采用预应力或钢-混凝土组合梁。",
        parameters={"min_height_span_ratio": r.threshold, "current_height_span_ratio": r.actual},
    ),
}


class CorrectionEngine:  # 类定义: CorrectionEngine
    """图纸修正建议生成引擎"""

    def __init__(self):  # 内部方法: __init__
        self._templates = CORRECTION_TEMPLATES  # 实例属性: _templates

    def generate(
        self, findings: List[Dict], entities: List[Dict]
    ) -> List[CorrectionSuggestion]:  # 函数定义: generate
        """根据审查结果生成修正建议

        Args:
            findings: 审查违规结果列表
            entities: 原始实体列表

        Returns:
            修正建议列表
        """
        suggestions = []  # 赋值: suggestions
        entity_map = {e.get("id", ""): e for e in entities}  # 安全获取值

        # 遍历处理
        for f in findings:  # 循环: f ← findings
            clause_id = f.get("clause_id", f.get("func_id", ""))  # clause_id 或 func_id
            entity_id = f.get("entity_id", "")  # 安全获取值
            entity = entity_map.get(entity_id, {})  # 安全获取值
            func_id = self._clause_to_func(clause_id)  # 赋值: func_id

            # 创建简易 FuncResult 对象供模板使用
            result = _FuncResult(  # 赋值: result
                actual=f.get("actual_value", f.get("extracted_value", 0)),  # 兼容两种字段名
                threshold=f.get("threshold", f.get("required_value", 0)),  # 兼容两种字段名
                delta=f.get("delta", f.get("difference", 0)),  # 兼容两种字段名
            )

            template = self._templates.get(func_id)  # 安全获取值
            # 条件分支：if template
            if template:  # 判断: template
                # 异常保护
                try:  # 异常捕获
                    suggestion = template(entity, result)  # 赋值: suggestion
                    suggestions.append(suggestion)  # 追加元素
                # 异常处理
                except Exception:  # 异常处理
                    pass  # 空实现

        return suggestions  # 返回结果

    def generate_for_result(
        self, review_result: dict
    ) -> List[Dict]:  # 函数定义: generate_for_result
        """从 /review 返回结果生成修正建议（用于API返回）

        Args:
            review_result: /review 端点的完整返回

        Returns:
            修正建议列表（可序列化为JSON）
        """
        findings = review_result.get("findings", [])  # 安全获取值
        suggestions = self.generate(findings, [])  # 赋值: suggestions

        output = []  # 赋值: output
        # 遍历处理
        for s in suggestions:  # 循环: s ← suggestions
            output.append(
                {  # 追加元素
                    "entity_id": s.entity_id,  # entity_id
                    "entity_type": s.entity_type,  # entity_type
                    "clause_id": s.clause_id,  # clause_id
                    "clause_title": s.clause_title,  # clause_title
                    "action": s.action.value,  # action
                    "description": s.description,  # description
                    "recommendation": s.recommendation,  # recommendation
                    "parameters": s.parameters,  # parameters
                    "priority": self._calc_priority(s),  # 实例属性: _calc_priority
                }
            )
        return output  # 返回结果

    @staticmethod  # 装饰器
    def _clause_to_func(clause_id: str) -> str:  # 函数定义: _clause_to_func
        """规范ID → 原子函数ID（简化映射）"""
        mapping = {  # 赋值: mapping
            "GB50016-5.5.18": "DIM-001",  # GB50016-5.5.18
            "GB50016-5.5.18-2": "DIM-004",  # GB50016-5.5.18-2
            "GB50016-6.1.1": "DIM-002",  # GB50016-6.1.1
            "GB50016-7.1.1": "DIM-003",  # GB50016-7.1.1
            "GB50016-5.5.17": "DIST-001",  # GB50016-5.5.17
            "GB50016-5.5.8": "COUNT-001",  # GB50016-5.5.8
            "GB50016-6.5.1": "ATTR-001",  # GB50016-6.5.1
            "GB50016-7.4.1": "AREA-001",  # GB50016-7.4.1
            "GB50016-5.5.12": "EXIST-001",  # GB50016-5.5.12
            "GB50016-7.2.4": "DIM-005",  # GB50016-7.2.4
            "GB50016-5.5.19": "DIM-006",  # GB50016-5.5.19
            "GB50016-6.5.3": "DIM-007",  # GB50016-6.5.3
            "GB50016-6.6.1": "EXIST-002",  # GB50016-6.6.1
            "GB50016-5.5.24": "EXIST-003",  # GB50016-5.5.24
            "GB50016-10.3.1": "EXIST-004",  # GB50016-10.3.1
            "GB50016-8.3.1": "EXIST-005",  # GB50016-8.3.1
            "GB50016-8.4.1": "EXIST-006",  # GB50016-8.4.1
            "GB50016-6.7.1": "ATTR-002",  # GB50016-6.7.1
            "GB50016-10.1.5": "LIGHT-001",  # GB50016-10.1.5
        }
        return mapping.get(clause_id, clause_id)  # 已为 func_id 则直接返回

    @staticmethod  # 装饰器
    def _calc_priority(s: CorrectionSuggestion) -> str:  # 函数定义: _calc_priority
        """计算修正优先级"""
        # 条件分支：if s.action.value in {a.value for a in [CorrectionAction.ADD, CorrectionAction.REPLACE, CorrectionAction.UPGRADE]}
        if s.action.value in {
            a.value
            for a in [CorrectionAction.ADD, CorrectionAction.REPLACE, CorrectionAction.UPGRADE]
        }:  # 判断: s.action.value in {a.value for a in [...
            return "high"  # 返回结果
        # 条件分支：if s.delta > s.required_value * 0.5
        if s.delta > s.required_value * 0.5:  # 判断: s.delta > s.required_value * 0.5
            return "high"  # 返回结果
        # 条件分支：if s.delta > s.required_value * 0.2
        if s.delta > s.required_value * 0.2:  # 判断: s.delta > s.required_value * 0.2
            return "medium"  # 返回结果
        return "low"  # 返回结果


class _FuncResult:  # 类定义: _FuncResult
    """内部简易结果对象"""

    def __init__(self, actual: float, threshold: float, delta: float):  # 内部方法: __init__
        self.actual = actual  # 实例属性: actual
        self.threshold = threshold  # 实例属性: threshold
        self.delta = delta  # 实例属性: delta
        self.result = "FAIL" if delta > 0 else "PASS"  # 实例属性: result
