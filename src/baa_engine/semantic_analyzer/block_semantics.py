"""块语义分类（Roadmap v4 T-A2，关联缺口 G7）

把原先内联在 `classify.py` INSERT 分支里的「块名 → 构件类型」子串匹配
抽取为纯数据表 `BLOCK_NAME_RULES`，并新增：

- `classify_block_name`：按表匹配块名（UPPER 后子串包含，首个命中即返回）。
- `attach_block_refs`：把 DrawingParser 产出的结构化块引用（ATTRIB/旋转/缩放）
  落库到对应 INSERT 图元的 `properties`，供分类时做图例兜底。

规则表**逐条按 `classify.py` 原文顺序**抽取为 `BLOCK_NAME_RULES_V1`（108 条，内容与顺序
保持不变）；生效的 `BLOCK_NAME_RULES` 在此基础上插入灯具规则（置于「柱」规则之前，修复
「挂灯、柱灯」被误判为 column）并追加电气/弱电设备规则。对 `block_name.upper()` 做子串包含
匹配，首个命中即返回。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# 未命中块名规则、且图例兜底也未命中时的兜底类型（保持既有行为）。
BLOCK_FALLBACK_TYPE = "wall"

# ── T-A2 原始规则快照（108 条） ──
# 逐条按 `classify.py` 原文顺序抽取，内容与相对顺序保持不变；
# 作为验收脚本的 pre-T-A2 基线（V1），扩充规则另行组合（见文件末尾）。
BLOCK_NAME_RULES_V1: Tuple[Tuple[str, str], ...] = (
    # ── 防火门/防火窗 ──
    ("FIRE_DOOR", "fire_door"),
    ("防火门", "fire_door"),
    ("FIRE_WINDOW", "fire_window"),
    ("防火窗", "fire_window"),
    # ── 建筑构件 ──
    ("DOOR", "door"),
    ("门", "door"),
    ("WINDOW", "window"),
    ("窗", "window"),
    ("STAIR", "stair"),
    ("ST", "stair"),
    ("COLUMN", "column"),
    ("柱", "column"),
    # ── 出口/疏散指示 ──
    ("EXIT", "exit"),
    ("出口", "exit"),
    ("EXIT_SIGN", "exit_sign"),
    ("SIGN", "exit_sign"),
    ("疏散指示", "exit_sign"),
    # ── 消防设施 ──
    ("HYDRANT", "fire_hydrant"),
    ("消火栓", "fire_hydrant"),
    ("SPRINKLER", "sprinkler"),
    ("喷淋", "sprinkler"),
    ("洒水", "sprinkler"),
    ("FIRE_EXT", "fire_extinguisher"),
    ("灭火器", "fire_extinguisher"),
    ("灭火", "fire_extinguisher"),
    ("SMOKE_DETECTOR", "smoke_detector"),
    ("烟感", "smoke_detector"),
    ("FIRE_ALARM", "fire_alarm"),
    ("报警", "fire_alarm"),
    ("WATER_TANK", "water_tank"),
    ("水箱", "water_tank"),
    ("WATER_RESERVOIR", "water_reservoir"),
    ("消防水池", "water_reservoir"),
    ("水池", "water_reservoir"),
    ("FIRE_ELEV", "fire_elevator"),
    ("消防电梯", "fire_elevator"),
    ("SPEAKER", "emergency_broadcast"),
    ("广播", "emergency_broadcast"),
    ("应急广播", "emergency_broadcast"),
    ("EVAC_LIGHT", "evacuation_lighting"),
    ("应急照明", "evacuation_lighting"),
    ("CURTAIN", "fire_curtain"),
    ("卷帘", "fire_curtain"),
    # ── 电气设备（新增） ──
    ("DISTRIBUTION_BOX", "distribution_box"),
    ("配电箱", "distribution_box"),
    ("配电", "distribution_box"),
    ("EMERGENCY_LIGHT", "emergency_lighting"),
    ("应急照明", "emergency_lighting"),
    ("应急灯", "emergency_lighting"),
    ("SMOKE_DETECTOR", "smoke_detector"),
    ("烟感", "smoke_detector"),
    ("烟探测器", "smoke_detector"),
    ("HEAT_DETECTOR", "heat_detector"),
    ("温感", "heat_detector"),
    ("温探测器", "heat_detector"),
    ("ALARM_BUTTON", "alarm_button"),
    ("报警按钮", "alarm_button"),
    ("手报", "alarm_button"),
    ("GAS_SUPPRESSION", "gas_suppression"),
    ("气体灭火", "gas_suppression"),
    ("气灭", "gas_suppression"),
    ("BELL", "fire_bell"),
    ("警铃", "fire_bell"),
    ("声光", "fire_bell"),
    # ── P70 泵控制柜（必须在通用 PUMP 之前，避免误匹配） ──
    ("PUMP_CONTROLLER", "pump_controller"),
    ("PUMP_CTRL", "pump_controller"),
    ("PUMPCTRL", "pump_controller"),
    ("泵控", "pump_controller"),
    ("启泵柜", "pump_controller"),
    ("水泵控制柜", "pump_controller"),
    # ── P70 消防泵/水泵接合器/启泵按钮 ──
    ("FIRE_PUMP", "fire_pump"),
    ("SPRINKLER_PUMP", "fire_pump"),
    ("STABLE_PRESSURE_PUMP", "fire_pump"),
    ("消防泵", "fire_pump"),
    ("喷淋泵", "fire_pump"),
    ("稳压泵", "fire_pump"),
    ("消火栓泵", "fire_pump"),
    ("水泵", "fire_pump"),
    ("PUMP", "fire_pump"),
    ("SIAMESE", "siamese_connection"),
    ("FIRE_DEPT_CONN", "siamese_connection"),
    ("SIAMESE_CONN", "siamese_connection"),
    ("水泵接合器", "siamese_connection"),
    ("接合器", "siamese_connection"),
    ("CALL_POINT", "hydrant_call_button"),
    ("消火栓按钮", "hydrant_call_button"),
    ("栓", "hydrant_call_button"),
    ("VESDA", "vesda_detector"),
    ("极早期", "vesda_detector"),
    ("吸气式", "vesda_detector"),
    ("EMERGENCY_POWER", "emergency_power"),
    ("应急电源", "emergency_power"),
    ("EPS", "emergency_power"),
    # ── 其他楼层/空间 ──
    ("ROOM", "room"),
    ("房间", "room"),
    ("室", "room"),
    ("CORRIDOR", "corridor"),
    ("走廊", "corridor"),
    ("走道", "corridor"),
    ("SHAFT", "shaft"),
    ("井道", "shaft"),
    ("竖井", "shaft"),
    ("ELEVATOR", "elevator"),
    ("电梯", "elevator"),
    ("LOBBY", "lobby"),
    ("前室", "lobby"),
    ("FIRE_ZONE", "fire_zone"),
    ("防火分区", "fire_zone"),
)

# ── T-A2 扩充规则 ──
# 灯具规则：必须插入到「柱」规则之前，避免「挂灯、柱灯」「柱灯」被判为 column（误报修复）。
_LAMP_RULES: Tuple[Tuple[str, str], ...] = (
    ("高杆灯", "light"),
    ("园林灯", "light"),
    ("柱灯", "light"),
    ("挂灯", "light"),
    ("路灯", "light"),
    ("吸顶灯", "light"),
    ("吊灯", "light"),
    ("灯具", "light"),
    ("LAMP", "light"),
)

# 弱电/信息点位规则（T-A2 精化新增专用类型 telecom_point）。
# 这类块名是信息/通信点位而非物理设备，归位 telecom_point 可避免落入 equipment
# 而被「设备类」原子函数（如 EXIST-087 气体灭火）统计引起的审查误报。
# 排序：更具体的「办公网网络点」在「网络点」之前；「无线AP」为唯一 AP 判据，
# 不再使用裸 "AP" 子串规则（"AP" 过泛，会命中 APPAREL 等无关块名）。
_TELECOM_RULES: Tuple[Tuple[str, str], ...] = (
    ("办公网网络点", "telecom_point"),
    ("网络点", "telecom_point"),
    ("语音点", "telecom_point"),
    ("信息点", "telecom_point"),
    ("数据点", "telecom_point"),
    ("电话点", "telecom_point"),
    ("光纤点", "telecom_point"),
    ("无线AP", "telecom_point"),
)

# 弱电/电气设备补充规则：追加到末尾，保持既有规则优先级不变。
# 实测高频块名：摄像机/变压器/发电机/接触器/智能照明控制面板…
# 明确不映射（保持 None，避免新增误报）：天正/AVE 系统块、图框、匿名块（见 T-A2 验收记录）。
_ELECTRICAL_WEAK_RULES: Tuple[Tuple[str, str], ...] = _TELECOM_RULES + (
    ("WIFI", "equipment"),
    ("网络", "equipment"),
    ("语音", "equipment"),
    ("摄像机", "equipment"),
    ("球机", "equipment"),
    ("CAMERA", "equipment"),
    ("变压器", "equipment"),
    ("发电机", "equipment"),
    ("接触器", "equipment"),
    ("控制箱", "equipment"),
    ("控制面板", "equipment"),
    ("桥架", "equipment"),
    ("母线", "equipment"),
)


def _compose_block_name_rules() -> Tuple[Tuple[str, str], ...]:
    """组合生效规则表：V1 + 灯具规则（插在「柱」前）+ 电气/弱电规则（末尾）。"""
    rules: List[Tuple[str, str]] = []
    for keyword, entity_type in BLOCK_NAME_RULES_V1:
        if keyword == "COLUMN" and entity_type == "column":
            rules.extend(_LAMP_RULES)
        rules.append((keyword, entity_type))
    rules.extend(_ELECTRICAL_WEAK_RULES)
    return tuple(rules)


# 生效的块名规则表（有序，子串包含匹配，首个命中即返回）。
BLOCK_NAME_RULES: Tuple[Tuple[str, str], ...] = _compose_block_name_rules()

# 坐标匹配容差（mm）
_COORD_TOLERANCE = 1e-3

# 图纸/标题类名称标记（图框、系统图、说明、目录等）。这类字符串不是构件块名，
# 命中任意标记即直接判为「非构件块」，避免规则表把图纸标题误报成构件。
_SHEET_NAME_MARKERS = (
    "平面图",
    "系统图",
    "立面图",
    "剖面图",
    "大样图",
    "详图",
    "节点图",
    "模板图",
    "配筋",
    "说明",
    "目录",
    "图框",
    "总平面",
    "TITLE-BLOCK",
    "TITLEBLOCK",
)

# 非建筑构件块守卫（T-A4 落地时发现的最大污染源，关联 G7）。
# 真实图纸库实测：`$LinePat$岩棉板` 等填充线型块单图可达 1900+ 实例，
# 五金紧固件（铆钉/螺栓）、定位标记也被块名兜底误判为 wall，既污染墙实例
# 又拉低属性覆盖率。命中以下模式直接判 "other"（非构件），不走 wall 兜底。
_NON_ARCH_BLOCK_PREFIXES = (
    "$LINEPAT$",  # AutoCAD 填充线型定义块（$LinePat$<图案名>）
    # 天正电气/系统库块（M3 扩面：治理后诊断显示 $TelecSys$/$TCHSYS$/$DorLib2D$
    # 系列是剩余缺失墙主要来源之一，均为电气系统/门窗库符号，非建筑构件）
    "$TELECSYS$",
    "$TCHSYS$",
    "$DORLIB2D$",
)
_NON_ARCH_BLOCK_KEYWORDS = (
    "铆",  # 铆钉/铆厚/铆接（五金紧固件）
    "螺栓",
    "螺钉",
    "螺丝",
    "销钉",
    "膨胀栓",
    "定位点",
    # 电气系统图符号（M3 扩面：断路器/熔断器等出现在电气图中被 wall 兜底污染）
    "断路器",
    "熔断器",
    "互感器",
    "继电器",
)


def classify_block_name(block_name: str) -> Optional[str]:
    """按 BLOCK_NAME_RULES 对块名分类。

    对 `block_name.upper()` 做子串包含匹配，首个命中即返回；
    空/None 或未命中返回 None（由调用方兜底）。
    """
    if not block_name:
        return None
    name = str(block_name).upper()
    # 图纸/标题类名称（图框、系统图、说明、目录等）不是构件块，
    # 命中标记直接返回 None，避免误报（如「运维网桥架平面图」含"桥架"）。
    if any(m in name for m in _SHEET_NAME_MARKERS):
        return None
    # 非建筑构件块（填充线型/五金紧固件/定位标记）→ "other"，不走 wall 兜底。
    if name.startswith(_NON_ARCH_BLOCK_PREFIXES) or any(
        k in name for k in _NON_ARCH_BLOCK_KEYWORDS
    ):
        return "other"
    for keyword, entity_type in BLOCK_NAME_RULES:
        if keyword in name:
            return entity_type
    return None


def _coords_from_props(props: Dict) -> Optional[Tuple[float, float]]:
    """从图元 properties 中取 (insert_x, insert_y)；缺失返回 None。"""
    if not isinstance(props, dict):
        return None
    x = props.get("insert_x")
    y = props.get("insert_y")
    if x is None or y is None:
        return None
    try:
        return (float(x), float(y))
    except (TypeError, ValueError):
        return None


def _coords_from_ref(ref: Dict) -> Optional[Tuple[float, float]]:
    """从块引用 dict 中取插入点 (x, y)；缺失返回 None。"""
    if not isinstance(ref, dict):
        return None
    pt = ref.get("insert_point")
    if not pt:
        return None
    try:
        return (float(pt[0]), float(pt[1]))
    except (TypeError, IndexError, KeyError, ValueError):
        return None


def _match_by_coords(prim, refs: List[Dict], consumed) -> Optional[Dict]:
    """按插入点坐标匹配块引用（容差 1e-3），跳过已消费项。"""
    coords = _coords_from_props(getattr(prim, "properties", None))
    if coords is None:
        return None
    px, py = coords
    for ref in refs:
        if not isinstance(ref, dict) or id(ref) in consumed:
            continue
        rc = _coords_from_ref(ref)
        if rc is None:
            continue
        if abs(rc[0] - px) <= _COORD_TOLERANCE and abs(rc[1] - py) <= _COORD_TOLERANCE:
            return ref
    return None


def _apply_ref(prim, ref: Dict) -> None:
    """把块引用的 ATTRIB/旋转/缩放写入图元 properties。"""
    props = getattr(prim, "properties", None)
    if props is None:
        return
    attribs = ref.get("attribs")
    if isinstance(attribs, dict):
        props["block_attribs"] = dict(attribs)
    for ref_key, prop_key in (
        ("rotation", "block_rotation"),
        ("x_scale", "block_x_scale"),
        ("y_scale", "block_y_scale"),
    ):
        value = ref.get(ref_key)
        if prop_key not in props and value is not None:
            props[prop_key] = value


def attach_block_refs(primitives, block_refs) -> List:
    """把块引用语义落库到 INSERT 图元的标注结构（原地修改并返回）。

    匹配优先级：prim.handle == ref.handle（handle 非空）；否则用
    properties 的 insert_x/insert_y 与 ref.insert_point 坐标（容差 1e-3）。
    命中后写入 block_attribs / block_rotation / block_x_scale / block_y_scale。
    不修改非 INSERT 图元；block_refs 为空/None 或字段缺失时静默跳过。
    """
    if not primitives or not block_refs:
        return primitives

    refs = [r for r in block_refs if isinstance(r, dict)]
    if not refs:
        return primitives

    by_handle: Dict[str, Dict] = {}
    for ref in refs:
        handle = ref.get("handle")
        if handle:
            by_handle.setdefault(str(handle), ref)

    consumed = set()
    for prim in primitives:
        if getattr(prim, "dxf_type", None) != "INSERT":
            continue
        ref = None
        handle = getattr(prim, "handle", None)
        if handle:
            cand = by_handle.get(str(handle))
            if cand is not None and id(cand) not in consumed:
                ref = cand
        if ref is None:
            ref = _match_by_coords(prim, refs, consumed)
        if ref is None:
            continue
        consumed.add(id(ref))
        _apply_ref(prim, ref)

    return primitives


__all__ = [
    "BLOCK_FALLBACK_TYPE",
    "BLOCK_NAME_RULES",
    "BLOCK_NAME_RULES_V1",
    "classify_block_name",
    "attach_block_refs",
]
