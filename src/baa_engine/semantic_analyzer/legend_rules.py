"""图例查表器基线（Roadmap v4 T-A2，关联缺口 G7）

把消防/建筑图纸中高频图例词汇整理为纯数据表 `LEGEND_RULES`，供
`classify.py` 在 INSERT 块名未命中时，用块属性（ATTRIB）文本做兜底分类
（README 图例/设备表常把设备标注在 ATTRIB 里）。

- 只建表，不重复 `classify.py` TEXT 分支已内联的全部 100+ 条判据，
  仅覆盖并复用其中高价值词条。
- 本模块不 import `classify`（避免循环依赖）。
"""

from __future__ import annotations

from typing import Optional, Tuple

# 有序 (图例/标注文本关键字, entity_type) 表；对 text.upper() 做子串包含匹配，
# 首个命中即返回。英文关键字统一大写；更具体的词条排在泛化词条之前。
LEGEND_RULES: Tuple[Tuple[str, str], ...] = (
    # ── 防火门/防火窗/卷帘 ──
    ("防火卷帘", "fire_curtain"),
    ("FIRE_SHUTTER", "fire_curtain"),
    ("防火门", "fire_door"),
    ("FIRE_DOOR", "fire_door"),
    ("防火窗", "fire_window"),
    ("FIRE_WINDOW", "fire_window"),
    ("卷帘", "fire_curtain"),
    ("CURTAIN", "fire_curtain"),
    # ── 出口/楼梯 ──
    ("疏散指示", "exit_sign"),
    ("EXIT", "exit"),
    ("出口", "exit"),
    ("楼梯", "stair"),
    ("STAIR", "stair"),
    # ── 消防设施 ──
    ("消火栓", "fire_hydrant"),
    ("HYDRANT", "fire_hydrant"),
    ("喷淋", "sprinkler"),
    ("洒水", "sprinkler"),
    ("SPRINKLER", "sprinkler"),
    ("灭火器", "fire_extinguisher"),
    ("灭火", "fire_extinguisher"),
    ("烟感", "smoke_detector"),
    ("烟雾探测", "smoke_detector"),
    ("探测器", "smoke_detector"),
    ("SMOKE", "smoke_detector"),
    ("报警", "fire_alarm"),
    ("ALARM", "fire_alarm"),
    # ── 消防电源/照明/电梯/水泵 ──
    ("应急照明", "evacuation_lighting"),
    ("EVAC", "evacuation_lighting"),
    ("消防电梯", "fire_elevator"),
    ("消防泵", "fire_pump"),
    ("水泵接合器", "siamese_connection"),
    # ── 弱电/信息点位（T-A2 精化新增专用类型 telecom_point；ATTRIB 高频词） ──
    ("办公网网络点", "telecom_point"),
    ("网络点", "telecom_point"),
    ("语音点", "telecom_point"),
    ("信息点", "telecom_point"),
    ("数据点", "telecom_point"),
    ("电话点", "telecom_point"),
    ("光纤点", "telecom_point"),
    ("无线AP", "telecom_point"),
    # ── 电气/弱电设备 + 灯具（ATTRIB 高频词，真实图纸实测补充；具体词在前） ──
    ("照明配电箱", "distribution_box"),
    ("配电箱", "distribution_box"),
    ("配电柜", "distribution_box"),
    ("配电", "distribution_box"),
    ("半球摄像机", "equipment"),
    ("电视摄像机", "equipment"),
    ("摄像机", "equipment"),
    ("发电机", "equipment"),
    ("变压器", "equipment"),
    ("电抗器", "equipment"),
    ("电容器", "equipment"),
    ("开关柜", "equipment"),
    ("接触器", "equipment"),
    ("桥架", "equipment"),
    ("吸顶灯", "light"),
    ("吊灯", "light"),
    ("路灯", "light"),
    ("灯具", "light"),
)


def lookup_legend(text: str) -> Optional[str]:
    """按 LEGEND_RULES 对图例/标注文本查表。

    对 `text.upper()` 做子串包含匹配，首个命中即返回；
    空/None 或未命中返回 None。
    """
    if not text:
        return None
    upper = str(text).upper()
    for keyword, entity_type in LEGEND_RULES:
        if keyword in upper:
            return entity_type
    return None


__all__ = ["LEGEND_RULES", "lookup_legend"]
