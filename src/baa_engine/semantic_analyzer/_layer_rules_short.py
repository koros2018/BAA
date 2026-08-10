"""
SHORT_LAYER_RULES: 短关键字全词匹配
"""

SHORT_LAYER_RULES = {
    # P82: "L" 已移除——全词匹配误命中 WP_L_PJ（水管道层，L=Layer非Lobby）
    # 真实 DXF 中无裸 "L" 层名（6张图纸 0 命中），lobby 实体来自 LOBBY/QT/大堂 等
    "W": "wall",  # 字段
    "D": "door",  # 字段
    "M": "door",  # 字段
    "C": "window",  # 字段
    "ST": "stair",  # 字段
    "FZ": "fire_zone",  # 字段
    "FD": "fire_door",  # 字段
    "FE": "fire_elevator",  # 字段
    "T": "equipment",  # 通信设备（real: T=通信图层，需全词匹配）
    # ── 电气设备扩展（P34） ──
    "应急": "emergency_light",  # 应急照明（real: 应急照明, 应急灯）
    "EPS": "emergency_light",  # 应急电源
    "出口指示灯": "exit_sign",  # 出口指示灯
    "双切箱": "equipment",  # 双电源切换箱
    "ALARM": "alarm_device",  # 报警设备
    "SIREN": "alarm_device",  # 警笛/声光报警器
    "控制箱": "equipment",  # 控制箱
    "消防泵": "fire_pump",  # 消防泵
    "喷淋泵": "fire_pump",  # 喷淋泵
    "消火栓泵": "fire_pump",  # 消火栓泵
    "稳压泵": "fire_pump",  # 稳压泵
    "FIRE_PUMP": "fire_pump",  # 消防泵英文
    "消防水箱": "water_tank",  # 消防水箱
    "WATER_TANK": "water_tank",  # 消防水箱英文
    "防火阀": "fire_damper",  # 防火阀
    "排烟": "smoke_exhaust",  # 排烟设备
    "正压送风": "smoke_exhaust",  # 正压送风
    "FAN": "equipment",  # 风机英文
    "疏散指示灯": "exit_sign",  # 疏散指示灯
    # ── P70 Final Batch: 62 low-frequency gaps (all 1 ref) ──
    "ACCESS_ROAD": "access_road",  # 接入道路
    "ALARM_PANEL": "alarm_panel",  # 报警面板
    "APARTMENT": "apartment",  # 住宅单元
    "AUTO_SPRINKLER": "auto_sprinkler",  # 自动喷淋
    "BASMENT_SHOP": "basement_shop",  # 地下商店
    "CAR": "car",  # 车辆
    "CENTRAL_ALARM": "central_alarm",  # 中央报警
    "COMMUNICATION": "communication",  # 通信设备
    "COMPARTMENT": "compartment",  # 舱室
    "CONTROLLER": "controller",  # 控制器
    "DISCHARGE_PIPE": "discharge_pipe",  # 排水管
    "DISPLAY_DEVICE": "display_device",  # 显示设备
    "DISTRIBUTION_PANEL": "distribution_panel",  # 配电盘
    "DUCT_SHAFT": "duct_shaft",  # 风道井
    "ELEVATOR_CTRL": "elevator_controller",  # 电梯控制
    "ELEVATOR_DOOR": "elevator_door",  # 电梯门
    "ENTRANCE": "entrance",  # 入口
    "ESCAPE_STAIR": "escape_stair",  # 疏散楼梯
    "EXHAUST_FAN": "exhaust_fan",  # 排风扇
    "EXHAUST_VENT": "exhaust_vent",  # 排风口
    "FACADE_INSULATION": "facade_insulation",  # 幕墙保温
    "FIRE_BELL": "fire_bell",  # 消防铃
    "FIRE_PUMP_ADAPTER": "fire_pump_adapter",  # 消防泵接合器
    "FIRE_PUMP_ROOM": "fire_pump_room",  # 消防泵房
    "GARAGE_ZONE": "garage_zone",  # 车库分区
    "GAS_SYSTEM": "gas_system",  # 气体系统
    "GRAPHIC_DISPLAY": "graphic_display",  # 图形显示
    "GUARDRAIL": "guardrail",  # 护栏
    "HALL": "hall",  # 走廊
    "HOTEL_ROOM": "hotel_room",  # 客房
    "HYDRANT_BOX": "hydrant_box",  # 消火栓箱
    "HYDRANT_BUTTON": "hydrant_button",  # 消火栓按钮
    "HYDRANT_RISER": "hydrant_riser",  # 消火栓立管
    "LANDING": "landing",  # 休息平台
    "LIGHTNING": "lightning_protection",  # 防雷
    "MONITOR": "monitor",  # 监视器
    "MONITORING_ROOM": "monitoring_room",  # 监控室
    "NOZZLE": "nozzle",  # 喷头
    "OBSTACLE": "obstacle",  # 障碍物
    "PANEL": "panel",  # 面板
    "PARKING_RAMP": "parking_ramp",  # 车库坡道
    "PARKING_ZONE": "parking_zone",  # 停车区
    "PARTITION": "partition",  # 隔墙
    "PUBLIC_AREA": "public_area",  # 公共区域
    "PUMP_ADAPTER": "pump_adapter",  # 水泵接合器
    "PUMP_BASE": "pump_base",  # 泵座
    "REGIONAL_ALARM": "regional_alarm",  # 区域报警
    "RISER": "riser",  # 立管
    "SCISSOR_STAIR_LOBBY": "scissor_stair_lobby",  # 剪刀梯前室
    "SCISSOR_STAIRCASE": "scissor_staircase",  # 剪刀楼梯
    "SHUTTER": "shutter",  # 百叶/卷帘
    "SIAMESE": "siamese",  # 水带接口
    "SMOKE_CONTROL": "smoke_control",  # 防烟
    "SMOKE_EXHAUST_WINDOW": "smoke_exhaust_window",  # 排烟窗
    "SMOKE_WINDOW": "smoke_window",  # 排烟窗
    "STAIR_TREAD": "stair_tread",  # 踏步
    "STAIRCASE_WINDOW": "staircase_window",  # 楼梯窗
    "SUCTION_PIPE": "suction_pipe",  # 吸水管
    "SWITCHBOARD": "switchboard",  # 开关板
    "TEMPERATURE_SENSOR": "temperature_sensor",  # 温度传感器
    "THERMAL_BRIDGE": "thermal_bridge",  # 热桥
    "VESDA": "vesda_detector",  # 吸气式探测器
}
