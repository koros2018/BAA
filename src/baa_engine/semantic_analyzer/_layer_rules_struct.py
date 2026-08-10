"""
结构基础 + 非建筑实体 + 电气设备 + 消防设施
"""

LAYER_RULES_STRUCT = {
    "BASE": "foundation",  # 基础（real: BASE_SING）
    "HATCH": "other",  # 填充图案
    "BAR": "other",  # 钢筋标记
    "REIN": "other",  # 钢筋
    "AXIS": "other",  # 轴线标记
    "AXS": "other",  # 轴线（real）
    "AXIS_": "other",  # 轴线前缀（real: AXIS_NUM, AXIS_DIM）
    "NUM": "other",  # 编号标记（real: COLU_NUM, AXIS_NUM）
    "钢筋": "other",  # 钢筋（中文）
    "THIN": "other",  # 细线（real）
    "DOTE": "other",  # 点线（real）
    "TEXT": "other",  # 纯文字图层
    "PUB_": "other",  # 公共标记
    "COLU_": "other",  # 柱子标注
    "钢吊柱": "other",  # 钢柱
    "焊缝": "other",  # 焊缝标记
    "水池": "other",  # 水池边线
    "外部参照": "other",  # 外部参照
    "电设备": "equipment",  # 电气设备
    "配电": "equipment",  # 配电设备
    "配电箱": "equipment",  # 配电箱
    "动力": "equipment",  # 动力设备
    "弱电": "equipment",  # 弱电设备
    "照明": "equipment",  # 照明设备
    "应急照明": "equipment",  # 应急照明设备
    "应急照明线路": "evacuation_lighting",  # 应急照明线路
    "应急照明灯": "evacuation_lighting",  # 应急照明灯头
    "应急灯": "evacuation_lighting",  # 应急灯
    "EVAC_LIGHT": "evacuation_lighting",  # 疏散照明
    "消防": "fire_equipment",  # 消防设备
    "消火栓": "fire_hydrant",  # 消火栓设备
    "灭火器": "fire_extinguisher",  # 灭火器设备
    "喷淋": "sprinkler",  # 喷淋设备
    "烟感": "smoke_detector",  # 烟感探测器
    "温感": "smoke_detector",  # 温感探测器
    "报警": "alarm_device",  # 报警设备
    "广播": "alarm_device",  # 广播设备
    "疏散指示": "alarm_device",  # 疏散指示设备
    "钢夹层": "other",  # 钢结构夹层
}
