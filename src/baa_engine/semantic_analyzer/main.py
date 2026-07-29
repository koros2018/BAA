"""
BAA 语义识别引擎 - 图元分类 + 空间关系构建（规则版）
"""

import os  # stdlib: filesystem ops
import math  # stdlib: math functions
from collections import deque  # stdlib: O(1) queue for BFS
from typing import List, Dict, Any, Optional, Tuple  # typing: type hints
from ..drawing_parser import RawPrimitive  # 导入
import logging  # 导入

logger = logging.getLogger(__name__)  # assign


# ── 图层规则表 ────────────────────────────────────────────

# 短关键字（单字母/2字母）使用全词匹配（前后是_或边界），防止误匹配
# 例如 "D" 不匹配 "DIM"、"DIMENSION"、"DWG"、"DOOR"
LAYER_RULES = {  # assign
    # ── 墙 ──
    "WALL": "wall",
    "墙体": "wall",
    "墙": "wall",  # 字段
    "BEAM": "wall",  # 结构梁图层（real: BEAM, BEAM_SE, beam-line）
    "COLUMN": "wall",  # 柱子（real: column-line, COLUMN-hatch）
    # ── 门 ──
    "DOOR": "door",
    "门": "door",  # 字段
    "SB": "door",  # 水消防设备层门标记
    # ── 窗 ──
    "WINDOW": "window",
    "窗": "window",
    "WIND": "window",  # 字段
    # ── 楼梯 ──
    "STAIR": "stair",
    "楼梯": "stair",
    "STAIRS": "stair",  # 字段
    # ── 走廊/走道 ──
    "CORRIDOR": "corridor",
    "走道": "corridor",
    "走廊": "corridor",  # 字段
    # ── 防火分区 ──
    "FIRE_ZONE": "fire_zone",
    "防火分区": "fire_zone",  # 字段
    # ── 尺寸标注 ──
    "DIM": "dimension",
    "标注": "dimension",
    "尺寸": "dimension",  # 字段
    "DIMENSION": "dimension",  # 字段
    "DIM_": "dimension",  # real: DIM_ELEV, DIM_SYMB, AXIS_DIM
    # ── 出口 ──
    "EXIT": "exit",
    "出口": "exit",
    "安全出口": "exit",  # 字段
    # ── 防火门 ──
    "FIRE_DOOR": "fire_door",
    "防火门": "fire_door",  # 字段
    # ── 消防电梯 ──
    "FIRE_ELEV": "fire_elevator",
    "消防电梯": "fire_elevator",  # 字段
    # ── 设备（电气/消防） ──
    "电-": "equipment",  # 电气设备图层（real: 电-系统-设备）
    "设备": "equipment",  # 设备
    "GCD": "equipment",  # 供电设备（real）
    "NET": "equipment",  # 网络设备（real）
    "气体": "equipment",  # 气体灭火设备
    "通风": "equipment",  # 通风设备
    # ── 消防设施图层（真实图纸图层名） ──
    "EQUIP-消防": "equipment",  # 天正消防设备图层
    "EQUIP_消火栓": "fire_hydrant",  # 消火栓设备
    "EQUIP-广播": "equipment",  # 消防广播设备
    "消防设备层": "equipment",  # 消防设备图层
    "消防平面尺寸": "dimension",  # 消防尺寸标注
    "消防标注": "dimension",  # 消防标注
    "FAS-": "equipment",  # 火灾报警系统图层
    "WIRE-消防": "equipment",  # 消防线路图层
    "消通讯": "equipment",  # 消防通讯
    "消设备层": "equipment",  # 消防设备
    "消标注": "dimension",  # 消防标注
    "VALVE_喷淋": "sprinkler",  # 喷淋阀门
    "VESDA": "smoke_detector",  # 极早期烟雾探测
    "TERM": "equipment",  # 终端设备
    "布线设备": "equipment",  # 布线设备
    "WIRE-防火门": "equipment",  # 防火门监控
    "消防泵": "fire_pump",  # P70 消防泵设备
    "消火栓按钮": "hydrant_call_button",  # P70 消火栓启泵按钮
    "启泵": "hydrant_call_button",  # P70 启泵按钮
    "水泵接合器": "siamese_connection",  # P70 水泵接合器
    # ── P70 高频缺口补全（atomic functions 引用最多，语义分析器产不出） ──
    # detector（19 refs）：不能与"烟感"/"温感"冲突，专用于通用探测器
    "探测器": "detector",
    "DET_": "detector",  # 天正探测器图层（real: DET_烟感, DET_温感）
    # floor（18 refs）：楼层
    "楼层": "floor",
    "FLOOR": "floor",
    # pump_room（12 refs）：泵房
    "泵房": "pump_room",
    "PUMP_ROOM": "pump_room",
    # fire_wall（7 refs）：防火墙
    "防火墙": "fire_wall",
    "FIRE_WALL": "fire_wall",
    # fire_shutter（5 refs）：防火卷帘
    "防火卷帘": "fire_shutter",
    "FIRE_SHUTTER": "fire_shutter",
    # control_room（9 refs）：控制室
    "控制室": "control_room",
    "FIRE_CONTROL": "control_room",
    # rescue_window（9 refs）：救援窗
    "救援窗": "rescue_window",
    "RESCUE_WIN": "rescue_window",
    # speaker（8 refs）：扬声器/广播
    "扬声器": "speaker",
    "SPEAKER": "speaker",
    # road（11 refs）：道路（长关键字子串匹配，与"车道"不冲突）
    "道路": "road",
    "ROAD": "road",
    # driveway（10 refs）：车道/入口坡道
    "车道": "driveway",
    "DRIVE": "driveway",
    # power_supply（7 refs）：电源
    "电源": "power_supply",  # 注意：优先匹配"电源"，避免被"双电源切换箱"的"控制箱"短关键字覆盖
    # ── P70 高频缺口补全（第2批：staircase/exit_door/fire_system/pump/refuge 等） ──
    "STAIRCASE": "staircase",  # 楼梯间（real: STAIRCASE, STAIR_CASE）
    "楼梯间": "staircase",
    "STAIR_CASE": "staircase",
    "EXIT_DOOR": "exit_door",  # 安全出口门（real: EXIT_DOOR）
    "出口门": "exit_door",
    "安全出口门": "exit_door",
    "泵": "pump",  # 通用水泵（与具体泵图层不冲突）
    "PUMP": "pump",
    "REFUGE_FLOOR": "refuge_floor",  # 避难层
    "避难层": "refuge_floor",
    "ANTEROOM": "anteroom",  # 前室
    "前室": "anteroom",
    "FIRE_LANE": "fire_lane",  # 消防车道
    "消防车道": "fire_lane",
    "FIRE_WATER_TANK": "fire_water_tank",  # 消防水箱（具体）
    "消火栓系统": "hydrant",  # 消火栓系统
    "INDOOR_HYDRANT": "indoor_hydrant",  # 室内消火栓
    "室内消火栓": "indoor_hydrant",
    "控制柜": "control_panel",  # 控制面板
    "CONTROL_PANEL": "control_panel",
    "REFUGE_AREA": "refuge_area",  # 避难区
    "避难区": "refuge_area",
    "REFUGE_ROOM": "refuge_room",  # 避难间
    "避难间": "refuge_room",
    "FIRE_BROADCAST": "fire_broadcast",  # 消防广播
    "消防广播": "fire_broadcast",
    "STAIRCASE_LOBBY": "staircase_lobby",  # 楼梯间前室
    "楼梯间前室": "staircase_lobby",
    "EQ_ROOM": "equipment_room",  # 设备间（缩写）
    # ── P70 高频缺口补全（第3批：fire_system/electrical/insulation/sprinkler_system 等） ──
    "FIRE_SYSTEM": "fire_system",  # 消防系统（real: FIRE_SYSTEM）
    "消防系统": "fire_system",
    "电气": "electrical",  # 电气系统
    "ELECTRICAL": "electrical",
    "电": "electrical",  # 电专业
    "INSULATION": "insulation",  # 保温材料
    "保温": "insulation",
    "SMOKE_VENT": "smoke_vent",  # 排烟窗/排烟口
    "排烟窗": "smoke_vent",
    "排烟口": "smoke_vent",
    "EXT_WALL": "exterior_wall",  # 外墙（real: EXT_WALL）
    "外墙": "exterior_wall",
    "FAN_": "fan",  # 风机（real: FAN_EX, FAN_SU）
    "风机": "fan",
    "GARAGE": "garage",  # 车库
    "车库": "garage",
    "PASSAGE": "passage",  # 通道
    "通道": "passage",
    "SPACE": "space",  # 空间
    "空间": "space",
    "ALARM_SYSTEM": "alarm_system",  # 报警系统
    "报警系统": "alarm_system",
    "BUILDING": "building",  # 建筑
    "建筑": "building",
    "SPRINKLER_SYSTEM": "sprinkler_system",  # 喷淋系统
    "喷淋系统": "sprinkler_system",
    "AISLE": "aisle",  # 走道/通道
    "EXT_WINDOW": "exterior_window",  # 外窗
    "外窗": "exterior_window",
    "FACADE": "facade",  # 立面
    "立面": "facade",
    "HALLWAY": "hallway",  # 走廊
    "MANUAL_CALL_POINT": "manual_call_point",  # 手动报警按钮
    "手动报警": "manual_call_point",
    "MANUAL_STATION": "manual_station",  # 手动报警站
    "OPENING": "opening",  # 洞口/开口
    "洞口": "opening",
    "PIPE": "pipe",  # 管道
    "管道": "pipe",
    "SIGN": "sign",  # 标志/标识
    "标识": "sign",
    "SLAB": "slab",  # 板
    "板": "slab",
    "CABLE": "cable",  # 电缆
    "电缆": "cable",
    "CONDUIT": "conduit",  # 管线
    "管线": "conduit",
    "CURTAIN_WALL": "curtain_wall",  # 幕墙
    "幕墙": "curtain_wall",
    "厕所": "toilet",
    "ELEVATOR": "elevator",  # 电梯
    "电梯": "elevator",
    # ── P70 高频缺口补全（第4批：duct/roof/pipe/parking 等） ──
    "DUCT": "duct",  # 风管
    "风管": "duct",
    "FIRE_CONTROL_ROOM": "fire_control_room",  # 消防控制室
    "消防控制室": "fire_control_room",
    "FIRE_HOSE": "fire_hose",  # 消防水带
    "消防水带": "fire_hose",
    "FIRE_MAIN": "fire_main",  # 消防主管
    "消防主管": "fire_main",
    "PARKING_LOT": "parking_lot",  # 停车场
    "停车场": "parking_lot",
    "PIPE_SHAFT": "pipe_shaft",  # 管井
    "管井": "pipe_shaft",
    "PIPING": "piping",  # 管道系统
    "管道系统": "piping",
    "RESCUE_AREA": "rescue_area",  # 救援区
    "救援区": "rescue_area",
    "ROOF": "roof",  # 屋顶
    "屋顶": "roof",
    "STAIRCASE_DOOR": "staircase_door",  # 楼梯间门
    "楼梯间门": "staircase_door",
    "STRUCTURE": "structure",  # 结构
    "结构": "structure",
    "WALKWAY": "walkway",  # 天桥/连廊
    "连廊": "walkway",
    "WATER_PIPE": "water_pipe",  # 水管
    "水管": "water_pipe",
    "VALVE": "check_valve",  # 阀门
    "阀门": "check_valve",
    "VENTILATOR": "ventilator",  # 通风器
    "通风器": "ventilator",
    "VENT": "vent",  # 风口
    "风口": "vent",
    "GAS_EXT": "gas_extinguishing",  # 气体灭火
    "气体灭火": "gas_extinguishing",
    "DRIP": "drain",  # 排水
    "排水": "drain",
    # ── P74 准确率专项：补充真实图纸高频层名覆盖（基于 16 张图纸 audit） ──
    # 高频建筑类型
    "RESIDENTIAL": "residential",  # 住宅（real: RESIDENTIAL, RES_）
    "住宅": "residential",
    "OFFICE": "office",  # 办公
    "办公": "office",
    # 疏散/消防通道
    "EVACUATION": "evacuation_route",  # 疏散路径
    "疏散路线": "evacuation_route",
    "EVAC_PATH": "evacuation_route",
    "疏散路线": "evacuation_route",
    # 防火门（补充英文/混写变体）
    "FI_DOOR": "fire_door",  # 天正防火门
    "DF_": "fire_door",  # 防火门门洞
    "防火门洞": "fire_door",
    # 防火卷帘/防火墙（补充变体）
    "FI_SHUTTER": "fire_shutter",  # 防火卷帘英文
    "FI_WALL": "fire_wall",  # 防火墙英文缩写
    "FIRE_WALL_": "fire_wall",
    "防火墙": "fire_wall",
    # 楼梯/疏散门/前室（补充天正/南方CAX变体）
    "STAIR_DOOR": "staircase_door",  # 楼梯间门英文
    "STAI_DOOR": "staircase_door",
    "前室门": "staircase_door",
    "ANTIROOM": "staircase_lobby",  # 前室英文
    "ANTI-ROOM": "staircase_lobby",
    "EXIT_PATH": "exit_path",  # 疏散出口路径
    "安全出口标志": "exit_sign",
    # 消防车道/登高面
    "FIRE_LN": "fire_lane",  # 消防车道英文缩写
    "FI_LN": "fire_lane",
    "FI_ACCESS": "fire_access",  # 消防车道
    "消防登高面": "fire_operation_area",
    "登高面": "fire_operation_area",
    "FI_AREA": "fire_operation_area",
    # 消火栓/喷淋（补充变体）
    "HYDR": "indoor_hydrant",  # 消火栓英文缩写
    "IND_HYD": "indoor_hydrant",
    "SPRK": "sprinkler",  # 喷淋英文缩写
    "SPRINK": "sprinkler",
    "SPRK_HEAD": "sprinkler",
    "喷头": "sprinkler_head",
    "消防喷头": "sprinkler_head",
    # 探测器（补充变体）
    "SMOKE_DET": "smoke_detector",  # 烟感英文
    "HEAT_DET": "heat_detector",  # 温感英文
    "烟感": "smoke_detector",
    "温感": "heat_detector",
    "感烟": "smoke_detector",
    # 防火门监控/电气（补充变体）
    "FI_MON": "equipment",  # 防火门监控
    "FD_MON": "equipment",
    "应急照明": "emergency_light",
    "EMERGENCY_LIGHT": "emergency_light",
    "应急灯": "emergency_light",
    # 无障碍设施
    "ACCESS": "accessible_door",  # 无障碍门
    "WHEEL": "accessible_elevator",  # 无障碍电梯
    "无障碍": "accessible_door",
    "无障碍电梯": "accessible_elevator",
    # 管道井/电梯井（补充变体）
    "SHAFT": "shaft",  # 管道井
    "竖井": "shaft",
    "电井": "shaft",
    "水井": "shaft",
    # 屋面/结构
    "ROOF_": "roof",  # 屋面
    "SLAB_": "slab",  # 楼板
    "基础": "foundation",  # 基础
    "FOUNDATION": "foundation",
    "FRAME": "structure",  # 框架
    "梁": "beam",
    "COLUMN_": "column",  # 柱
    "柱": "column",
    # 车库/停车位
    "PARK": "parking_lot",  # 停车场
    "车位": "parking_spot",
    "PARKING": "parking_spot",
    # 室外设施
    "FACADE_": "facade",  # 立面
    "LOBBY": "lobby",  # 大堂
    "Lobby": "lobby",
    "大堂": "lobby",
    "ANTEROOM_": "anteroom",  # 前室
    "前室_": "anteroom",
    # 室外/总图
    "OUTDOOR": "outdoor_stair",  # 室外楼梯
    "OUTDOOR_STAIR": "outdoor_stair",
    "室外楼梯": "outdoor_stair",
    "GROUNDS": "outdoor_area",  # 总图
    "总图": "outdoor_area",
    "FIRE_EXIT": "exit_door",  # 安全出口门英文
    "FI_EXIT": "exit_door",
    "FI_DOOR": "fire_door",
    # 设备间
    "EQ_": "equipment_room",  # 设备间
    "DB": "equipment_room",  # 电井设备
    "电井": "equipment_room",
    # ── P70 高频缺口补全（第5批：3 refs 层级） ──
    "ACCESSIBLE_ROOM": "accessible_room",  # 无障碍房间
    "无障碍房间": "accessible_room",
    "ALARM_CENTER": "alarm_center",  # 报警中心
    "报警中心": "alarm_center",
    "CURTAIN": "curtain",  # 窗帘/卷帘（通配）
    "电梯厅": "elevator_lobby",
    "ELEVATOR_LOBBY": "elevator_lobby",
    "疏散门": "evacuation_door",
    "EVACUATION_DOOR": "evacuation_door",
    "疏散标志": "evacuation_sign",
    "EVACUATION_SIGN": "evacuation_sign",
    "室外楼梯": "external_stair",
    "EXTERNAL_STAIR": "external_stair",
    "FIRE_DEPT_CONN": "fire_department_connection",  # 消防部门连接
    "FIRE_PHONE": "fire_phone",  # 消防电话
    "消防电话": "fire_phone",
    "FIRE_POOL": "fire_pool",  # 消防水池
    "FIRE_STOP": "fire_stop",  # 阻火
    "阻火": "fire_stop",
    "GROUNDING": "grounding",  # 接地
    "接地": "grounding",
    "GND": "grounding",
    "LIFT": "lift",  # 货梯
    "货物梯": "lift",
    "PASSAGEWAY": "passageway",  # 通道
    "RESCUE_OPENING": "rescue_opening",  # 救援口
    "救援口": "rescue_opening",
    "SAFETY_EXIT": "safety_exit",  # 安全出口
    "SOUND_ALARM": "sound_alarm",  # 声响报警
    "声响报警": "sound_alarm",
    "SOUNDER": "sounder",  # 警笛
    "警笛": "sounder",
    "STEP": "step",  # 踏步
    "踏步": "step",
    "TRUNKING": "trunking",  # 线槽
    "线槽": "trunking",
    "WALL_INSULATION": "wall_insulation",  # 墙体保温
    "墙体保温": "wall_insulation",
    "WIRING": "wiring",  # 布线
    "布线": "wiring",
    "BEAM_": "beam",  # 梁（real: BEAM_SE）
    "梁": "beam",
    # ── P70 最终高频缺口补全（剩余 2-3 refs） ──
    "EARTH": "earth",  # 地基土
    "地基": "earth",
    "ELECTRICAL_ROOM": "electrical_room",  # 配电室
    "配电室": "electrical_room",
    "电气室": "electrical_room",
    "GROUND_BUS": "ground_bus",  # 接地母线
    "接地母线": "ground_bus",
    "MECH_VENT": "mechanical_vent",  # 机械通风
    "自然通风": "natural_vent",
    "NATURAL_VENT": "natural_vent",
    "SMOKE_PROOF_LOBBY": "smoke_proof_lobby",  # 防烟前室
    "防烟前室": "smoke_proof_lobby",
    "AUDIO": "audio_system",  # 音响系统
    "音响系统": "audio_system",
    "AUDITORIUM": "auditorium",  # 礼堂
    "礼堂": "auditorium",
    "BATTERY": "battery",  # 电池
    "电池": "battery",
    "BEDROOM": "bedroom",  # 卧室
    "卧室": "bedroom",
    "BROADCAST_SPEAKER": "broadcast_speaker",  # 广播扬声器
    "电缆井": "cable_shaft",
    "CABLE_SHAFT": "cable_shaft",
    "CLADDING": "cladding",  # 外墙覆层
    "外墙覆层": "cladding",
    "电话": "phone",
    "PHONE": "phone",
    "INTERCOM": "intercom",  # 对讲
    "对讲": "intercom",
    "LIGHT_": "light",  # 灯具
    "灯": "light",
    "LIGHTING": "lighting",
    "BREAKER": "breaker",  # 断路器
    "断路器": "breaker",
    "发电机": "generator",
    "GENERATOR": "generator",
    "发电机房": "generator_room",
    "GENERATOR_ROOM": "generator_room",
    "GIRDER": "girder",  # 桁架
    "桁架": "girder",
    "GLAZING": "glazing",  # 玻璃幕墙
    "幕墙玻璃": "glazing",
    "高层": "highrise_building",
    "HIGHRISE": "highrise_building",
    "HOSE": "hose",  # 水带
    "软管": "hose",
    "油机房": "oil_room",
    "OIL_ROOM": "oil_room",
    "室外消火栓": "outdoor_hydrant",
    "OUTDOOR_HYDRANT": "outdoor_hydrant",
    "停车线": "parking_spot",
    "PARKING_SPOT": "parking_spot",
    "桩": "pile",
    "PILE": "pile",
    "柱": "pillar",
    "PILLAR": "pillar",
    "平台": "platform",
    "PLATFORM": "platform",
    "抗剪墙": "shear_wall",
    "SHEAR_WALL": "shear_wall",
    "FIRE_ACCESS": "fire_access",  # 消防登高
    "FIRE_COMPARTMENT": "fire_compartment",  # 防火单元
    "FIRE_DETECTOR": "fire_detector",  # 火灾探测器
    "FIRE_ELEV_LOBBY": "fire_elevator_lobby",  # 消防电梯前室
    "FIRE_EXT": "fire_extinguishing",  # 灭火系统
    "FIRE_RES_OPENING": "fire_rescue_opening",
    "FIRE_SPRINKLER": "fire_sprinkler",  # 消防喷淋
    "FIRE_TANK": "fire_tank",  # 消防水罐
    "FIRE_WATER": "fire_water",  # 消防用水
    "FIRE_BARRIER": "fire_barrier",  # 防火屏障
    "FIRE_CONNECTION": "fire_connection",  # 消防接口
    "FIRE_HOSE_REEL": "fire_hose_reel",  # 消防卷盘
    "FIRE_HYD_CONN": "fire_hydrant_connection",
    "FIRE_OPER_AREA": "fire_operation_area",  # 消防操作区
    "FIRE_PARTITION": "fire_partition",  # 防火分隔
    "FIRE_PIPE": "fire_pipe",  # 消防管道
    "FIRE_PLATFORM": "fire_platform",  # 消防平台
    "FIRE_RESERVOIR": "fire_reservoir",  # 消防水池
    "FIRE_STAIR": "fire_stair",  # 消防楼梯
    "FIRE_SUPP": "fire_suppression",  # 消防抑制
    "FIRE_WATER_POND": "fire_water_pond",  # 消防水池
    "GAS_FIREFIGHT": "gas_fire_suppression",
    # ── P70 尾批：2-ref 类型 ──
    "COMM_DEVICE": "communication_device",  # 通信设备
    "灯报警": "light_alarm",
    "LIGHT_ALARM": "light_alarm",
    "POOL": "pool",  # 泳池
    "RAILING": "railing",  # 栏杆
    "栏杆": "railing",
    "RESCUE_GROUND": "rescue_ground",  # 救援地面
    "救援地面": "rescue_ground",
    "ROOM_DOOR": "room_door",  # 房间门
    "房间门": "room_door",
    "SCISSOR_STAIR": "scissor_stair",  # 剪刀楼梯
    "剪刀楼梯": "scissor_stair",
    "SENSOR": "sensor",  # 传感器
    "传感器": "sensor",
    "SHELTER": "shelter",  # 避难所
    "避难所": "shelter",
    "SIDEWALK": "sidewalk",  # 人行道
    "人行道": "sidewalk",
    "SLAB_TOP": "slab_top",  # 板顶
    "板顶": "slab_top",
    "SMOKE_PROOF_STAIR": "smoke_proof_stair",  # 防烟楼梯
    "防烟楼梯": "smoke_proof_stair",
    "SMOKE_SENSOR": "smoke_sensor",  # 烟感传感器
    "STAIR_HANDRAIL": "stair_handrail",  # 楼梯扶手
    "楼梯扶手": "stair_handrail",
    "START_BUTTON": "start_button",  # 启动按钮
    "启动按钮": "start_button",
    "TACTILE_PAVING": "tactile_paving",  # 盲道砖
    "盲道砖": "tactile_paving",
    "TELEPHONE": "telephone",  # 电话
    "UNDERGROUND_GARAGE": "underground_garage",  # 地下车库
    "地下车库": "underground_garage",
    "UPS": "ups",  # 不间断电源
    "不间断电源": "ups",
    "ROOF_INSULATION": "roof_insulation",  # 屋顶保温
    "屋顶保温": "roof_insulation",
    "FIRE_WINDOW": "fire_window",  # 消防窗
    "消防窗": "fire_window",
    "WINDOW_GLASS": "window_glass",  # 窗玻璃
    "窗玻璃": "window_glass",
    "线槽": "trunking",
    "保温层": "wall_insulation",
    "WASHBASIN": "washbasin",  # 洗手盆
    "洗手盆": "washbasin",
    "SEAT": "seat",  # 座椅
    "座椅": "seat",
    "STORE": "store",  # 商店
    "商店": "store",
    "FACTORY": "factory",  # 厂房
    "厂房": "factory",
    "HOTEL": "hotel",  # 酒店
    "酒店": "hotel",
    "OFFICE": "office",  # 办公室
    "办公室": "office",
    "SHOP": "shop",  # 商铺
    "商铺": "shop",
    "WAREHOUSE": "warehouse",  # 仓库
    "仓库": "warehouse",
    "NURSING_UNIT": "nursing_unit",  # 护理单元
    "护理单元": "nursing_unit",
    "SURGERY_ROOM": "surgery_room",  # 手术室
    "手术室": "surgery_room",
    "OPERATING_ROOM": "operating_room",  # 手术室（英文）
    "CLASSROOM": "classroom",  # 教室
    "教室": "classroom",
    "KTV": "ktv",  # KTV
    "THEATER": "theater",  # 影院
    "影院": "theater",
    "DANCE_HALL": "dance_hall",  # 舞厅
    "舞厅": "dance_hall",
    "ASSEMBLY_HALL": "assembly_hall",  # 大厅
    "大厅": "assembly_hall",
    "PUBLIC_ROOM": "public_room",  # 公共用房
    "公共用房": "public_room",
    "ENTERTAINMENT_VENUE": "entertainment_venue",  # 娱乐场所
    "娱乐场所": "entertainment_venue",
    "HOSPITAL_WARD": "hospital_ward",  # 病房
    "病房": "hospital_ward",
    "RESIDENTIAL_UNIT": "residential_unit",  # 住宅单元
    "住宅单元": "residential_unit",
    "BATHROOM": "bathroom",  # 浴室
    "浴室": "bathroom",
    "RESTROOM": "restroom",  # 洗手间
    "洗手间": "restroom",
    "BOILER_ROOM": "boiler_room",  # 锅炉房
    "锅炉房": "boiler_room",
    "SERVER_ROOM": "server_room",  # 机房
    "机房": "server_room",
    "MATERIAL": "material",  # 材料
    "材料": "material",
    "COMBUSTIBLE": "combustible",  # 可燃物
    "可燃物": "combustible",
    "FIRE_ZONE": "fire_zone",  # 防火分区（已有，补充）
    "JUNCTION": "junction",  # 连接点
    "连接点": "junction",
    "GAP": "gap",  # 间隙
    "间隙": "gap",
    "REPAIR_ZONE": "repair_zone",  # 维修区
    "维修区": "repair_zone",
    "FIRE_WIDE": "fire_water_tank",  # alias
    "WATER_SOURCE": "water_source",  # 水源
    "水源": "water_source",
    "WATER_INTAKE": "water_intake",  # 取水口
    "取水口": "water_intake",
    "WATER_RESERVOIR": "water_reservoir",  # 水池
    "WATER_TANK_ROOM": "water_tank_room",  # 水箱间
    "水箱间": "water_tank_room",
    "GROUND_FLOOR": "ground_floor",  # 首层
    "首层": "ground_floor",
    "RESIDENTIAL_DOOR": "residential_door",  # 住宅门
    "住宅门": "residential_door",
    "EXTERNAL_DOOR": "external_door",  # 外门
    "外门": "external_door",
    "ENTRANCE_DOOR": "entrance_door",  # 入户门
    "入户门": "entrance_door",
    "ROOM_DOOR": "room_door",  # 房间门
    "FLOOR_SLAB": "floor_slab",  # 楼板
    "楼板": "floor_slab",
    "SLAB": "slab",  # 板
    "混凝土": "concrete",
    "CONCRETE": "concrete",
    "EARTH": "earth",  # 地基土（补充）
    "PILE": "pile",  # 桩
    "PILE_CAP": "pile_cap",  # 承台
    "承台": "pile_cap",
    "FOOTING": "footing",  # 基础
    "基础": "footing",
    "SHADING": "shading",  # 遮阳
    "遮阳": "shading",
    "SINK": "sink",  # 水池
    "STEP_WIDTH": "step_width",  # 踏步宽度
    "CURB_RAMP": "curb_ramp",  # 缘石坡道
    "缘石坡道": "curb_ramp",
    "ACCESSIBLE_ENTRANCE": "accessible_entrance",  # 无障碍入口
    "无障碍入口": "accessible_entrance",
    "ACCESSIBLE_PARKING": "accessible_parking",  # 无障碍停车位
    "无障碍停车位": "accessible_parking",
    "ACCESSIBLE_RAMP": "accessible_ramp",  # 无障碍坡道
    "无障碍坡道": "accessible_ramp",
    "ACCESSIBLE_SIGN": "accessible_sign",  # 无障碍标志
    "无障碍标志": "accessible_sign",
    "ACCESSIBLE_FACILITY": "accessible_facility",  # 无障碍设施
    "无障碍设施": "accessible_facility",
    "WHEELCHAIR_SPACE": "wheelchair_space",  # 轮椅空间
    "轮椅空间": "wheelchair_space",
    "EMERGENCY_EXIT": "emergency_exit",  # 紧急出口
    "紧急出口": "emergency_exit",
    "EVACUATION_ROUTE": "evacuation_route",  # 疏散路线
    "疏散路线": "evacuation_route",
    "EVACUATION_LIGHTING": "evacuation_lighting",  # 疏散照明
    "疏散照明": "evacuation_lighting",
    "EMERGENCY_LIGHTING": "emergency_lighting",  # 应急照明
    "POWER_SUPPLY": "power_supply",  # 电源
    "电源": "power_supply",
    "BACKUP_POWER": "backup_power",  # 备用电源
    "备用电源": "backup_power",
    "FIRE_LANE": "fire_lane",  # 消防车道
    "消防车道": "fire_lane",
    "FIRE_OPERATION_AREA": "fire_operation_area",  # 消防登高操作场地
    "消防登高": "fire_operation_area",
    "FIRE_PLATFORM": "fire_platform",  # 消防平台
    "消防平台": "fire_platform",
    "EXTERIOR_WINDOW": "exterior_window",  # 外窗
    "外窗": "exterior_window",
    "FIRE_WINDOW": "fire_window",  # 消防窗
    "消防窗": "fire_window",
    "RESQ_OPENING": "rescue_opening",  # 救援口（补充）
    "RESCUE_OPENING": "rescue_opening",  # 救援口
    "RESCUE_WINDOW": "rescue_window",  # 救援窗
    "救援窗": "rescue_window",
    "EXTERIOR_WALL": "exterior_wall",  # 外墙
    "外墙": "exterior_wall",
    "DEAD_END_CORRIDOR": "dead_end_corridor",  # 袋形走道
    "袋形走道": "dead_end_corridor",
    "EXIT_PASSAGEWAY": "exit_passageway",  # 疏散走道
    "疏散走道": "exit_passageway",
    "EXIT_SIGN": "exit_sign",  # 出口标志
    "出口标志": "exit_sign",
    "DIRECTIONAL_SIGN": "directional_sign",  # 方向标志
    "方向标志": "directional_sign",
    "LIGHT_ALARM": "light_alarm",  # 声光报警
    "声光报警": "light_alarm",
    "ELEVATOR_LOBBY": "elevator_lobby",  # 电梯厅
    "电梯厅": "elevator_lobby",
    "FIRE_ELEV_LOBBY": "fire_elevator_lobby",  # 消防电梯前室
    "消防电梯前室": "fire_elevator_lobby",
    "LIFT": "lift",  # 货梯
    "货物梯": "lift",
    "HALLWAY": "hallway",  # 走廊
    "PASSAGE": "passage",  # 通道
    "通道": "passage",
    "STAIRCASE": "staircase",  # 楼梯间
    "STAIR_CASE": "staircase",
    "STAIRCASE_DOOR": "staircase_door",  # 楼梯间门
    "STAIRCASE_LOBBY": "staircase_lobby",  # 楼梯间前室
    "SAFETY_EXIT": "safety_exit",  # 安全出口
    "EMERGENCY_CALL": "emergency_call",  # 紧急呼叫
    "紧急呼叫": "emergency_call",
    "EVACUATION_DOOR": "evacuation_door",  # 疏散门
    "疏散门": "evacuation_door",
    "EVACUATION_SIGN": "evacuation_sign",  # 疏散标志
    "疏散标志": "evacuation_sign",
    "LEVEL_INDICATOR": "level_indicator",  # 层标
    "层标": "level_indicator",
    "FLOOR_SLAB": "floor_slab",  # 楼板
    "楼板": "floor_slab",
    "MUNICIPAL_WATER": "municipal_water",  # 市政用水
    "市政用水": "municipal_water",
    "FIRE_WATER_POND": "fire_water_pond",  # 消防水池
    "消防水池": "fire_water_pond",
    "SUMP": "sump",  # 集水井
    "集水井": "sump",
    "DRAIN": "drain",  # 排水
    "排水": "drain",
    "IRRIGATION": "drainage",  # 灌溉排水
    "竖向管": "vertical_pipe",
    "VERTICAL_PIPE": "vertical_pipe",
    "VERTICAL_SHAFT": "vertical_shaft",  # 竖井
    "竖井": "vertical_shaft",
    "车道": "driveway",
    "EXTERNAL_STAIR": "external_stair",  # 室外楼梯
    "室外楼梯": "external_stair",
    "FLOOR_SLAB": "floor_slab",  # 楼板（补充）
    "BLOCK": "block",  # 区块
    "分区": "block",
    # ── 结构基础 ──
    "BASE": "foundation",  # 基础（real: BASE_SING）
    # ── 非建筑实体 ──
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
    # ── 电气设备图层（新增） ──
    "电设备": "equipment",  # 电气设备
    "配电": "equipment",  # 配电设备
    "配电箱": "equipment",  # 配电箱
    "动力": "equipment",  # 动力设备
    "弱电": "equipment",  # 弱电设备
    "照明": "equipment",  # 照明设备
    "应急照明": "equipment",  # 应急照明设备
    # ── 消防设施图层（新增） ──
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
    # ── P79 真实图纸常见图层补全（基于 7 张 DXF audit，覆盖 148 个未匹配层名中的高频/有意义项）──
    # HVAC / 暖通
    "暖通": "hvac_equipment",  # 暖通系统图层前缀（real: 暖通-排风-法兰, 暖通-排风-2d边线）
    "暖通-": "hvac_equipment",  # 暖通系统分层（real: 暖通-排风-阀门）
    "暖通-排风-法兰": "duct_fitting",  # 排风法兰
    "暖通-排风-2d边线": "duct",  # 排风风管边线
    "暖通-排烟-法兰": "duct_fitting",  # 排烟法兰
    "暖-说明": "other",  # 暖通说明文字
    "a-空调机组": "hvac_equipment",  # 空调机组
    "A_空调机组": "hvac_equipment",  # 空调机组
    "M-EQPM": "hvac_equipment",  # 空调设备（real: m-eqpm）
    "0D-EQPM-P": "hvac_equipment",  # 空调设备布置
    "FG": "hvac_equipment",  # 风柜（real: fg=风管/风柜）
    "a_fg": "hvac_equipment",  # 风管
    "a_fgend": "hvac_equipment",  # 风管端头
    "FFFS": "fire_system",  # 火灾报警系统缩写
    "K-FF": "hvac_equipment",  # 空调风口
    "BZ_F_PY": "hvac_equipment",  # 排烟风口标注
    "vac_fm_py": "duct",  # 排烟风口
    "AT_PF": "hvac_equipment",  # 排风
    "SD": "other",  # 说明文字图层
    "FUZHU": "other",  # 辅助线图层
    "TH": "other",  # 文字标注
    "HT": "other",  # 文字标注
    "INS": "other",  # 文字标注
    "STE": "other",  # 文字标注
    "PM": "other",  # 图框标记
    "INS": "other",  # 文字标注（重复）
    "ZX": "axis",  # 轴线中心线（real: zx-内看线）
    "ZX-内看线": "axis",  # 轴线上内看线
    "RD-中心线": "other",  # 道路中心线
    "IRON": "other",  # 钢筋
    "铁": "other",  # 钢筋
    "TREE": "vegetation",  # 树木（real: tree）
    "树": "vegetation",  # 树木
    "绿地": "landscape",  # 绿化用地
    "绿化": "landscape",  # 绿化（real: 绿化轮廓线）
    "绿化轮廓线": "landscape",  # 绿化轮廓
    "绿线": "landscape",  # 绿线（规划）
    "规划": "planning",  # 规划（real: 规划）
    "拟选址": "planning",  # 规划选址
    "村界": "boundary",  # 村庄边界线
    "路名": "other",  # 道路名称标注
    "通-参照": "other",  # 通用参照
    "通-图框": "titleblock",  # 图框
    "通-图框-图签": "titleblock",  # 图框图签
    "通-图框-文字": "titleblock",  # 图框文字
    "通-图框-标题块": "titleblock",  # 图框标题块
    "C-SHET": "titleblock",  # 图框
    "图纸说明": "other",  # 图纸说明文字
    "性质": "other",  # 文字标注
    "抹灰": "other",  # 装修抹灰标注
    "截断线": "other",  # 详图截断线
    "建-标高": "dimension",  # 建筑标高
    "建-留洞": "opening",  # 建筑留洞
    "建-面积": "other",  # 建筑面积标注
    "建.17.图框": "titleblock",  # 建筑图框
    "排烟说明": "other",  # 排烟系统说明
    "暖-说明": "other",  # 暖通说明
    "防排烟说明": "other",  # 防排烟说明
    "风井": "shaft",  # 通风竖井
    "立剖-细": "other",  # 立剖细线
    "细线": "other",  # 细线图层
    "结-详图-线": "other",  # 结构详图线
    "视口": "viewport",  # 布局视口
    "设计院修改内容": "other",  # 设计变更标注
    "0D-CHIM": "hvac_equipment",  # 空调设备
    "0D-CHIM-C": "hvac_equipment",  # 空调设备（冷却）
    "0D-CHIM-INSU": "insulation",  # 空调保温
    "G-IMPT": "other",  # 图框标记
    "J02-QG": "other",  # 标注图层
    "J02-QH": "other",  # 标注图层
    "I01-DH": "other",  # 标注图层
    "I02-DG": "other",  # 标注图层
    "JMD": "other",  # 标注图层
    "JIANZHU": "building",  # 建筑标注
    "C": "window",  # 窗（real: C 短关键字，但此处为长匹配兜底）
    "X": "other",  # 坐标标注
    "0": "other",  # 图层 0（默认图层）
    "DEFPOINTS": "other",  # 尺寸标注辅助点
    "DM-坐标": "dimension",  # 坐标标注
    "EQUIP_雨水斗": "drain",  # 雨水斗
    "PROYECCIONES": "other",  # 投影
    "NT": "other",  # 文字图层
    "NT1": "other",  # 文字图层
    "NT2017": "other",  # 文字图层
    "NT面积线": "other",  # 面积线
    "NNT": "other",  # 文字标注
    "P-KX1": "other",  # 图框标记
    "PP-BZ-ZB": "other",  # 标注图层
    "PP-COM": "other",  # 图框标记
    "OP": "other",  # 文字标注
    "VDWG": "other",  # 图框
    "AC": "other",  # 标注图层
    "TQHZ": "other",  # 标注图层
    "TMZT": "other",  # 标注图层
    "TC": "other",  # 标注图层
    "CHC": "other",  # 标注图层
    "AREA_1": "other",  # 面积标注
    "ARC": "other",  # 弧线标记
    "BORDER": "other",  # 图框边界
    "OTHER": "other",  # 通用 other 层
    "图层1": "other",  # 默认图层
    "图则": "other",  # 图则说明
    "图例框": "other",  # 图例框
    "分车带": "landscape",  # 道路分车绿化带
    "内部文字": "other",  # 内部文字标注
    "公服图例": "other",  # 公共服务图例
    "规划建筑": "building",  # 规划建筑
    "水-套管": "pipe",  # 排水套管
    "水－雨水－窨井": "drain",  # 雨水窨井
    "水-套管": "pipe",  # 套管
    "3T_WOOD": "other",  # 天正家具填充（real: 3T_WOOD）
    "IHY-ROOM NAME": "other",  # 房间名称标注
    "建.17.图框文字": "titleblock",  # 建筑图框文字
    # ── P47 无障碍设施图层 ──
    "RAMP": "ramp",
    "SLOPE": "ramp",
    "坡道": "ramp",
    "HANDRAIL": "handrail",
    "扶手": "handrail",
    "ACCESSIBLE": "accessible_path",
    "无障碍": "accessible_path",
    "WHEELCHAIR": "accessible_path",
    "TACTILE": "tactile_guide",
    "盲道": "tactile_guide",
    "PARKING": "parking_space",
    "车位": "parking_space",
    "停车": "parking_space",
    "TOILET": "accessible_toilet",
    "卫生间": "accessible_toilet",
    "WC": "accessible_toilet",
    # ── P70 Final Batch: 18 high-frequency gaps (all >1 ref) ──
    "D_ACCESS": "accessible_door",
    "ELEVATOR": "accessible_elevator",
    "FIRE_WARN_PANEL": "alarm_button",
    "FIRE_ALARM_SYSTEM": "fire_alarm",
    "ANTEROOM": "antechamber",
    "AXIS": "column",
    "DQ": "distribution_box",
    "SP": "emergency_broadcast",
    "EPS_POWER": "emergency_power",
    "FIRE_CURT": "fire_curtain",
    "QMQJ": "gas_suppression",
    "JBR": "heat_detector",  # 火灾探测器常见简写
    "L": "lobby",
    "OUTDOOR_STAIR": "outdoor_stair",
    "STAIRS": "stairs",
    "FB": "pump_controller",
    "PLAN": "room",
    "HOLE": "shaft",
}  # code

# 短关键字（单字母/2字母）使用全词匹配
SHORT_LAYER_RULES = {  # assign
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
}  # code


# ── 语义实体 ──────────────────────────────────────────────


class SemanticEntity:  # class: class SemanticEntity:
    """语义化图元"""

    def __init__(
        self,
        entity_id: str,
        entity_type: str,  # method: def __init__(self, entity_id: str, entity_type: str,
        bbox: Dict[str, float],
        layer: str = "",  # 操作
        subtype: str = "",
        confidence: float = 1.0,  # assign
        properties: Dict[str, Any] = None,
    ):  # init: set to None
        self.id = entity_id  # assign: self attribute
        self.type = entity_type  # assign: self attribute
        self.bbox = bbox  # assign: self attribute
        self.layer = layer  # assign: self attribute
        self.subtype = subtype  # assign: self attribute
        self.confidence = confidence  # assign: self attribute
        self.properties = properties or {}  # assign: self attribute

    def to_dict(self) -> dict:  # method: def to_dict(self) -> dict:
        return {  # return: dict result
            "id": self.id,  # 字段
            "type": self.type,  # 字段
            "subtype": self.subtype,  # 字段
            "bbox": self.bbox,  # 字段
            "layer": self.layer,  # 字段
            "confidence": self.confidence,  # 字段
            "properties": self.properties,  # 字段
        }  # code


class SpatialRelation:  # class: class SpatialRelation:
    """空间关系"""

    def __init__(
        self,
        source_id: str,
        target_id: str,  # method: def __init__(self, source_id: str, target_id: str,
        rel_type: str,
        distance: float = 0,  # 操作
        via: str = "",
        confidence: float = 1.0,
    ):  # assign
        self.source_id = source_id  # assign: self attribute
        self.target_id = target_id  # assign: self attribute
        self.type = rel_type  # adjacent / contains / connects_to
        self.distance = distance  # assign: self attribute
        self.via = via  # assign: self attribute
        self.confidence = confidence  # assign: self attribute


# ── 语义分析引擎 ──────────────────────────────────────────


class SemanticAnalyzer:  # class: class SemanticAnalyzer:
    """语义识别引擎（规则版，不做ML）"""

    ADJACENT_THRESHOLD = 50.0  # 相邻距离阈值(mm)

    def __init__(self):  # method: def __init__(self):
        self._entity_counter = 0  # assign: self attribute
        self._analyze_cache: Dict[str, Dict[str, Any]] = {}  # hash -> result
        self._cache_max = 50  # assign: self attribute

    def analyze(
        self,
        primitives: List[RawPrimitive],  # method: def analyze(self, primitives: List[RawPrimitive],
        dimensions: List[Dict] = None,  # 操作
        max_entities: int = 10000,  # 性能优化后默认提升到 10000
        building_type: str = "civil",  # assign
        dxf_path: Optional[str] = None,
    ) -> Dict[str, Any]:  # init: set to None
        """
        执行语义分析

        参数:
            primitives: 原始图元列表
            dimensions: 尺寸标注列表
            max_entities: 最大处理实体数（超过则采样，防OOM）
            dxf_path: DXF 文件路径（可选），提供后启用 YOLO 检测增强

        输出: 结构化语义数据（entities + relations + attributes）
        """
        self._entity_counter = 0  # assign: self attribute

        # ── 缓存检查：相同 primitives hash 秒级返回 ──────
        try:  # try: operation block
            import hashlib  # stdlib import

            # 使用前100个图元的type+bbox近似指纹
            fingerprint_parts = []  # init: empty list
            for p in primitives[:100]:  # loop: for p in primitives[:100]:
                fingerprint_parts.append(f"{p.dxf_type}:{p.bbox}")  # append: add to list
            fingerprint = hashlib.sha256("".join(fingerprint_parts).encode()).hexdigest()[
                :32
            ]  # assign
            cached = self._analyze_cache.get(fingerprint)  # assign
            if cached is not None:  # check: value is not None
                return cached  # return
        except Exception:  # catch: exception handler
            fingerprint = None  # init: set to None

        # 采样限制，防止全量关系构建OOM
        if len(primitives) > max_entities:  # check: numeric comparison
            import random  # stdlib import

            random.seed(42)  # call
            primitives = random.sample(primitives, max_entities)  # assign

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)  # assign

        # Step 1.05: 楼层/区域检测（P35新增）
        floor_levels = self._detect_floor_levels(primitives)  # assign
        floor_assignments = self._assign_entities_to_floors(
            entities, primitives, floor_levels
        )  # assign

        # Step 1.1: YOLO 检测增强（可选，通过 dxf_path 触发）
        if dxf_path:  # condition: dxf_path:
            try:  # 尝试
                yolo_entities = self._yolo_enhance(dxf_path)  # assign
                if yolo_entities:  # condition: yolo_entities:
                    entities = self._merge_yolo_results(entities, yolo_entities)  # assign
                    logger.info(
                        f"YOLO 增强: 新增 {len(yolo_entities)} 个实体, 合并后共 {len(entities)} 个"
                    )  # len: get length
            except Exception as e:  # 捕获异常
                logger.warning(f"YOLO 增强失败: {e}")  # call

        # Step 1.4: 多段线复合房间识别（LINE 链闭合检测）
        entities = self._merge_line_chains_to_rooms(entities, primitives)  # assign

        # Step 1.5: 走廊宽度推断（平行线聚类 + bbox 短边）
        entities = self._infer_corridor_widths(entities, primitives)  # assign

        # Step 1.6: door/fire_door 属性增强（宽度兜底 + 防火等级推断）
        for ent in entities:  # 循环
            if ent.type in ("door", "fire_door", "exit_door"):  # check: membership test
                # 宽度兜底：bbox长边优先推断（门扇的宽度是长边，短边是门扇厚度）
                if (
                    ent.properties.get("width", 0) < 0.3
                    and ent.properties.get("clear_width", 0) < 0.3
                ):  # check: numeric comparison
                    bbox = ent.bbox  # assign
                    bw = bbox.get("width", 0)  # assign
                    bh = bbox.get("height", 0)  # assign
                    if bw > 0 and bh > 0:  # check: numeric comparison
                        # 优先用长边推断门的宽度（短边是门扇厚度）
                        long_edge = max(bw, bh)  # assign
                        short_edge = min(bw, bh)  # assign
                        # 门宽度的常见模数值（mm）：700/800/900/1000/1200/1500
                        COMMON_DOOR_WIDTHS = [700, 800, 900, 1000, 1200, 1500]  # assign
                        # 如果长边是短边的 3 倍以上，说明长边是门宽、短边是厚度
                        if (
                            short_edge > 0 and long_edge / short_edge >= 3.0
                        ):  # check: numeric comparison
                            w_mm = long_edge  # assign
                        else:  # 否则
                            w_mm = long_edge  # assign
                        # 匹配最近的模数
                        best_match = min(COMMON_DOOR_WIDTHS, key=lambda x: abs(x - w_mm))  # assign
                        if abs(w_mm - best_match) / max(best_match, 1) < 0.3:  # 偏差 < 30%，取模数
                            w_mm = best_match  # assign
                        w_m = w_mm * 0.001  # assign
                        if 0.3 < w_m < 3.0:  # check: numeric comparison
                            ent.properties["width"] = w_m  # 操作
                            ent.properties["clear_width"] = w_m  # 操作
                # 防火等级推断：从图层名和实体名推断
                if ent.type == "fire_door":  # check: OR condition
                    existing_rating = ent.properties.get(
                        "fire_rating", ent.properties.get("rating", 0)
                    )  # assign
                    if existing_rating < 0.5:  # check: numeric comparison
                        # 图层名包含关键字推断
                        # 注意：META 图层可能含有 A/B/C，要用完整单词匹配避免误触
                        layer_upper = (ent.layer or "").upper()  # assign
                        words = layer_upper.replace("-", " ").replace("_", " ").split()  # assign
                        if "甲" in layer_upper or "A" in words:  # check: membership test
                            ent.properties["fire_rating"] = 3.0  # 甲级=3.0
                        elif "乙" in layer_upper or "B" in words:  # 分支
                            ent.properties["fire_rating"] = 2.0  # 乙级=2.0
                        elif "丙" in layer_upper or "C" in words:  # 分支
                            ent.properties["fire_rating"] = 1.0  # 丙级=1.0
                        # 不设默认值——无法推断时留空，让原子函数处理

        # Step 2: 空间关系构建（V2拓扑关系）
        relations = self._build_relations(entities)  # assign

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])  # assign

        # Step 4: 走廊拓扑网络（V2新增）
        corridor_topology = self.build_corridor_topology(entities, relations)  # assign

        # Step 5: 疏散路径分析（V2新增）
        evacuation_routes = self.analyze_evacuation_routes(entities, relations) or []  # assign

        # Step 5.3: 疏散路径连通性验证（P33新增）
        connectivity = self.verify_evacuation_connectivity(
            entities, relations, evacuation_routes
        )  # assign

        # Step 5.5: 疏散路径结果注入到实体属性（EVAC原子函数用）
        route_by_room = {}  # init: empty dict
        for route in evacuation_routes:  # 循环
            route_by_room[route["room_id"]] = route  # 操作
        dead_end_ids = set(
            d["id"] for d in corridor_topology.get("dead_ends", [])
        )  # assign: membership check
        for ent in entities:  # 循环
            if ent.id in dead_end_ids:  # check: membership test
                ent.properties["is_dead_end"] = True  # 操作
            if ent.id in route_by_room:  # check: membership test
                r = route_by_room[ent.id]  # assign
                ent.properties["has_evacuation_route"] = r.get("has_route", False)  # 操作
                if r.get("path_length") is not None:  # check: value is not None
                    ent.properties["evacuation_path_length"] = r["path_length"]  # 操作
                ent.properties["evacuation_too_far"] = r.get("exceeds_max_distance", False)  # 操作
            # 对未找到路径的实体：如果疏散路径分析有结果但房间不在其中，标记为无路径
            # 如果分析结果为空（无出口/无拓扑），则不标记——让 EVAC 原子函数跳过判定
            elif ent.type in ("room", "corridor"):  # 分支
                if (
                    "has_evacuation_route" not in ent.properties and evacuation_routes
                ):  # check: membership test
                    ent.properties["has_evacuation_route"] = False  # 操作
                    ent.properties["evacuation_too_far"] = True  # 操作

        # Step 5.6: 连通性验证结果注入实体属性
        conn_by_room = {}  # init: empty dict
        for item in connectivity:  # loop: for item in connectivity:
            conn_by_room[item["room_id"]] = item  # assign
        for ent in entities:  # loop: for ent in entities:
            if ent.id in conn_by_room:  # check: membership test
                c = conn_by_room[ent.id]  # assign
                ent.properties["evacuation_connected"] = c.get("connected", False)  # assign
                ent.properties["evacuation_bottleneck"] = c.get("bottleneck", False)  # assign
                if c.get("bottleneck_details"):  # condition: c.get("bottleneck_details"):
                    ent.properties["evacuation_bottleneck_details"] = c[
                        "bottleneck_details"
                    ]  # assign

        result = {  # assign
            "entities": [e.to_dict() for e in entities],  # 字段
            "relations": [r.__dict__ if hasattr(r, "__dict__") else r for r in relations],  # 字段
            "attributes": attributes,  # 字段
            "building_type": building_type,  # 字段
            "corridor_topology": corridor_topology,  # 字段
            "evacuation_routes": evacuation_routes,  # 字段
            "evacuation_connectivity": connectivity,  # 字段
            "floor_levels": floor_levels,  # 字段
            "floor_assignments": floor_assignments,  # 字段
        }  # code

        # ── 写入缓存 ──────────────────────────────────────
        if fingerprint and result:  # check: AND condition
            if len(self._analyze_cache) >= self._cache_max:  # check: numeric comparison
                old_key = next(iter(self._analyze_cache))  # assign
                del self._analyze_cache[old_key]  # code
            self._analyze_cache[fingerprint] = result  # assign: self attribute

        return result  # return

    def _detect_floor_levels(
        self, primitives: List[RawPrimitive]
    ) -> List[Dict]:  # method: def _detect_floor_levels(self, primitives: List[RawPrimitive
        """检测图纸中的楼层分隔线和标高文字（P35）

        策略：
        1. 寻找跨越图纸宽度 80% 以上的水平 LINE/LWPOLYLINE（楼层分隔线）
        2. 提取 TEXT 中的标高信息（如 "±0.000", "F1", "第2层", "标高"）
        3. 返回按 Y 坐标排序的楼层列表

        返回:
            [
                {"level": 1, "label": "F1", "elevation": 0.0, "y_range": [y_min, y_max], "source": "separator"},
                ...
            ]
        """
        if not primitives:  # check: negated condition
            return []  # return: list of items

        # 计算图纸总宽度
        all_x = []  # init: empty list
        all_y = []  # init: empty list
        for p in primitives:  # loop: for p in primitives:
            bbox = p.bbox  # assign
            if bbox.get("width", 0) > 0:  # check: numeric comparison
                all_x.append(bbox["x"])  # append: add to list
                all_x.append(bbox["x"] + bbox["width"])  # append: add to list
            if bbox.get("height", 0) > 0:  # check: numeric comparison
                all_y.append(bbox["y"])  # append: add to list
                all_y.append(bbox["y"] + bbox["height"])  # append: add to list

        if not all_x or not all_y:  # check: negated condition
            return []  # return: list of items

        drawing_width = max(all_x) - min(all_x) if all_x else 0  # assign
        drawing_height = max(all_y) - min(all_y) if all_y else 0  # assign
        if drawing_width <= 0:  # check: numeric comparison
            return []  # return: list of items

        width_threshold = drawing_width * 0.8  # 跨越 80% 以上宽度视为楼层分隔线

        # 1. 收集水平分隔线
        separators = []  # init: empty list
        for p in primitives:  # loop: for p in primitives:
            if p.dxf_type not in ("LINE", "LWPOLYLINE"):  # check: membership test
                continue  # code
            bbox = p.bbox  # assign
            bw = bbox.get("width", 0)  # assign
            bh = bbox.get("height", 0)  # assign
            center_y = bbox.get("y", 0) + bh / 2  # assign

            # 水平线：宽度远大于高度
            if bw > 0 and bh > 0 and bw / max(bh, 1) > 20:  # check: numeric comparison
                if bw >= width_threshold:  # check: numeric comparison
                    separators.append(
                        {  # code
                            "y": center_y,  # code
                            "width": bw,  # code
                            "layer": p.layer,  # code
                        }
                    )  # code

        # 2. 提取标高文字
        elevation_texts = []  # init: empty list
        for p in primitives:  # loop: for p in primitives:
            if p.dxf_type != "TEXT":  # condition: p.dxf_type != "TEXT":
                continue  # code
            text = p.properties.get("text", "").strip()  # assign
            if not text:  # check: negated condition
                continue  # code
            bbox = p.bbox  # assign
            center_y = bbox.get("y", 0) + bbox.get("height", 0) / 2  # assign

            # 匹配标高模式
            level = None  # init: set to None
            label = text  # assign

            # "±0.000" 或 "+0.000" 或 "-0.000" 标高
            if any(c in text for c in ["±", "+", "-"]) and "." in text:  # check: membership test
                try:  # try: operation block
                    # 尝试提取数值
                    num_str = text.replace("±", "").replace("+", "").strip()  # assign
                    elevation = float(num_str) if num_str else 0.0  # assign
                    if "±" in text:  # check: membership test
                        elevation = 0.0  # init: set to 0
                    level = elevation  # assign
                    label = (
                        f"F{int(elevation) + 1}" if elevation >= 0 else f"B{abs(int(elevation))}"
                    )  # assign
                except ValueError:  # catch: exception handler
                    pass  # code

            # "F1", "F2", "1F", "2F", "B1", "B2"
            if level is None:  # check: value is None
                import re  # stdlib: regex

                m = re.match(r"^[Ff](\d+)$", text)  # assign
                if m:  # condition: m:
                    level = int(m.group(1))  # assign
                    label = f"F{level}"  # assign
                m = re.match(r"^(\d+)[Ff]$", text)  # assign
                if m:  # condition: m:
                    level = int(m.group(1))  # assign
                    label = f"F{level}"  # assign
                m = re.match(r"^[Bb](\d+)$", text)  # assign
                if m:  # condition: m:
                    level = -int(m.group(1))  # assign
                    label = f"B{m.group(1)}"  # assign

            # "第1层", "第2层", "首层", "二层"
            if level is None:  # check: value is None
                if "首层" in text or "一层" in text:  # check: membership test
                    level = 1  # assign
                    label = "F1"  # assign
                elif "二层" in text:  # elif: "二层" in text:
                    level = 2  # assign
                    label = "F2"  # assign
                elif "三层" in text:  # elif: "三层" in text:
                    level = 3  # assign
                    label = "F3"  # assign
                elif "层" in text:  # elif: "层" in text:
                    import re  # stdlib: regex

                    m = re.search(r"(\d+)层", text)  # assign
                    if m:  # condition: m:
                        level = int(m.group(1))  # assign
                        label = f"F{level}"  # assign

            # "标高" + 数值
            if level is None and "标高" in text:  # check: value is None
                import re  # stdlib: regex

                nums = re.findall(r"[-+]?\d+\.?\d*", text)  # assign
                if nums:  # condition: nums:
                    try:  # try: operation block
                        level = float(nums[0])  # assign
                        label = (
                            f"F{int(level) + 1}" if level >= 0 else f"B{abs(int(level))}"
                        )  # assign
                    except ValueError:  # catch: exception handler
                        pass  # code

            if level is not None:  # check: value is not None
                elevation_texts.append(
                    {  # code
                        "y": center_y,  # code
                        "level": level,  # code
                        "label": label,  # code
                        "text": text,  # code
                    }
                )  # code

        # 3. 合并分隔线和标高文字，按 Y 排序生成楼层
        floor_levels = []  # init: empty list

        # 先按分隔线 Y 排序
        sorted_seps = sorted(separators, key=lambda s: s["y"])  # assign
        sorted_texts = sorted(elevation_texts, key=lambda t: t["y"])  # assign

        if not sorted_seps and not sorted_texts:  # check: negated condition
            return []  # return: list of items

        # 如果有分隔线，用分隔线定义楼层
        if sorted_seps:  # check: OR condition
            # 添加最底层边界
            prev_y = min(all_y) if all_y else 0  # assign
            for i, sep in enumerate(sorted_seps):  # loop: for i, sep in enumerate(sorted_seps):
                floor_levels.append(
                    {  # code
                        "level": i + 1,  # code
                        "label": f"F{i + 1}",  # code
                        "elevation": None,  # code
                        "y_range": [prev_y, sep["y"]],  # code
                        "source": "separator",  # code
                    }
                )  # code
                prev_y = sep["y"]  # assign
            # 添加最顶层边界
            floor_levels.append(
                {  # code
                    "level": len(sorted_seps) + 1,  # len: get length
                    "label": f"F{len(sorted_seps) + 1}",  # len: get length
                    "elevation": None,  # code
                    "y_range": [prev_y, max(all_y) if all_y else prev_y + 1],  # max: get maximum
                    "source": "separator",  # code
                }
            )  # code

        # 用标高文字补充楼层标签（仅在分隔线模式下）
        if sorted_seps and sorted_texts:  # check: OR condition
            for fl in floor_levels:  # loop: for fl in floor_levels:
                y_min, y_max = fl["y_range"]  # assign
                for et in sorted_texts:  # loop: for et in sorted_texts:
                    if y_min <= et["y"] <= y_max:  # check: numeric comparison
                        fl["label"] = et["label"]  # assign
                        fl["elevation"] = et["level"]  # assign
                        fl["source"] = "text"  # assign
                        break  # code

        # 无分隔线时，按标高文字聚类
        if not sorted_seps and len(sorted_texts) >= 1:  # check: numeric comparison
            # 按文字 Y 坐标聚类
            clusters = []  # init: empty list
            current_cluster = [sorted_texts[0]]  # assign
            for i in range(1, len(sorted_texts)):  # loop: for i in range(1, len(sorted_texts)):
                if (
                    abs(sorted_texts[i]["y"] - sorted_texts[i - 1]["y"]) < drawing_height * 0.1
                ):  # check: numeric comparison
                    current_cluster.append(sorted_texts[i])  # append: add to list
                else:  # else: default case
                    clusters.append(current_cluster)  # append: add to list
                    current_cluster = [sorted_texts[i]]  # assign
            if current_cluster:  # condition: current_cluster:
                clusters.append(current_cluster)  # append: add to list

            # 取每个簇中心 Y 作为楼层分界
            cluster_centers = []  # init: empty list
            for cluster in clusters:  # loop: for cluster in clusters:
                avg_y = sum(t["y"] for t in cluster) / len(cluster)  # assign: membership check
                cluster_centers.append(
                    {"y": avg_y, "label": cluster[0]["label"], "level": cluster[0]["level"]}
                )  # append: add to list

            cluster_centers.sort(key=lambda c: c["y"])  # assign

            prev_y = min(all_y) if all_y else 0  # assign
            for i, cc in enumerate(
                cluster_centers
            ):  # loop: for i, cc in enumerate(cluster_centers):
                floor_levels.append(
                    {  # code
                        "level": i + 1,  # code
                        "label": cc["label"],  # code
                        "elevation": cc["level"],  # code
                        "y_range": [prev_y, cc["y"] + drawing_height * 0.05],  # code
                        "source": "text",  # code
                    }
                )  # code
                prev_y = cc["y"] + drawing_height * 0.05  # assign

        if not floor_levels:  # check: negated condition
            return []  # return: list of items

        # 去重 + 排序
        seen_labels = set()  # init: empty set
        unique = []  # init: empty list
        for fl in floor_levels:  # loop: for fl in floor_levels:
            if fl["label"] not in seen_labels:  # check: membership test
                seen_labels.add(fl["label"])  # call
                unique.append(fl)  # append: add to list

        unique.sort(key=lambda f: f["level"])  # assign
        return unique  # return

    def _assign_entities_to_floors(
        self,  # method: def _assign_entities_to_floors(self,
        entities: List[SemanticEntity],  # code
        primitives: List[RawPrimitive],  # code
        floor_levels: List[Dict],
    ) -> Dict[str, str]:  # code
        """将实体分配到对应楼层

        返回:
            {entity_id: floor_label}  # e.g. {"ROOM_001": "F1", "DOOR_002": "F2"}
        """
        if not floor_levels or not entities:  # check: negated condition
            return {}  # return: dict result

        assignments = {}  # init: empty dict
        for ent in entities:  # loop: for ent in entities:
            bbox = ent.bbox  # assign
            center_y = bbox.get("y", 0) + bbox.get("height", 0) / 2  # assign

            assigned = False  # assign
            for fl in floor_levels:  # loop: for fl in floor_levels:
                y_min, y_max = fl["y_range"]  # assign
                if y_min <= center_y <= y_max:  # check: numeric comparison
                    assignments[ent.id] = fl["label"]  # assign
                    ent.properties["floor"] = fl["label"]  # assign
                    assigned = True  # assign
                    break  # code

            if not assigned:  # check: negated condition
                # 默认归属最近楼层
                if floor_levels:  # check: OR condition
                    closest = min(
                        floor_levels,
                        key=lambda f: abs((f["y_range"][0] + f["y_range"][1]) / 2 - center_y),
                    )  # assign
                    assignments[ent.id] = closest["label"]  # assign
                    ent.properties["floor"] = closest["label"]  # assign

        return assignments  # return

    def _parse_meta_entities(
        self, primitives: List[RawPrimitive]
    ) -> List[
        SemanticEntity
    ]:  # method: def _parse_meta_entities(self, primitives: List[RawPrimitive
        """
        解析 META 图层的结构化实体元数据。
        格式: ENTITY:<type>|x:<x>|y:<y>|w:<w>|h:<h>|key:value|...
        用于合成图纸测试场景，跳过常规几何归并直接构建实体。
        """
        entities = []  # init: empty list
        for prim in primitives:  # 循环
            if prim.layer.upper() != "META":  # condition: prim.layer.upper() != "META":
                continue  # 继续循环
            text = prim.properties.get("text", "")  # assign
            if not text.startswith("ENTITY:"):  # check: negated condition
                continue  # 继续循环
            parts = text.split("|")  # assign
            if len(parts) < 5:  # check: numeric comparison
                continue  # 继续循环
            # 解析类型
            etype = parts[0].replace("ENTITY:", "").strip()  # assign
            # 解析bbox和属性
            props = {}  # init: empty dict
            bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}  # assign
            for part in parts[1:]:  # 循环
                if ":" not in part:  # check: membership test
                    continue  # 继续循环
                k, v = part.split(":", 1)  # 操作
                k = k.strip()  # assign
                v = v.strip()  # assign
                if k == "x":  # condition: k == "x":
                    bbox["x"] = float(v)  # 操作
                elif k == "y":  # 分支
                    bbox["y"] = float(v)  # 操作
                elif k == "w":  # 分支
                    bbox["width"] = float(v)  # 操作
                elif k == "h":  # 分支
                    bbox["height"] = float(v)  # 操作
                else:  # 否则
                    # 尝试转数字，失败保留字符串
                    try:  # 尝试
                        props[k] = float(v)  # assign
                    except ValueError:  # 捕获异常
                        props[k] = v  # assign

            self._entity_counter += 1  # assign: self attribute
            entity = SemanticEntity(  # assign
                entity_id=f"{etype.upper()}_{self._entity_counter:03d}",  # assign
                entity_type=etype,  # assign
                bbox=bbox,  # assign
                layer="META",  # assign
                confidence=1.0,  # assign
                properties=props,  # assign
            )  # code
            entities.append(entity)  # append: add to list

        return entities  # return

    def _classify_entities(
        self, primitives: List[RawPrimitive]
    ) -> List[
        SemanticEntity
    ]:  # method: def _classify_entities(self, primitives: List[RawPrimitive])
        """图元分类归并"""
        # 优先解析 META 图层（合成图纸结构化数据）
        meta_entities = self._parse_meta_entities(primitives)  # assign
        if meta_entities:  # condition: meta_entities:
            return meta_entities  # return

        entities = []  # init: empty list

        for prim in primitives:  # 循环
            # 图层规则匹配
            entity_type = self._classify_by_layer(prim.layer)  # assign
            # P80 修复：图层规则返回"other"时，让几何分类兜底，
            # 否则闭合多边形（如 DOTE 层实线围合区域）被误判为非建筑实体，
            # 导致 _merge_line_chains_to_rooms 无法找到 room，疏散分析返回空
            if entity_type == "unknown" or entity_type == "other":  # condition: entity_type == "unknown" or entity_type == "other"
                geo_type = self._classify_by_geometry(prim)  # assign
                if geo_type != "unknown" and geo_type != "other":  # condition: geo_type is meaningful
                    entity_type = geo_type  # assign

            if entity_type == "unknown":  # condition: entity_type == "unknown":
                continue  # 继续循环

            self._entity_counter += 1  # assign: self attribute
            # 过滤 NaN properties
            cleaned_props = {}  # init: empty dict
            for pk, pv in prim.properties.items():  # 循环
                if isinstance(pv, float):  # condition: isinstance(pv, float):
                    import math  # stdlib: math functions

                    if not math.isnan(pv):  # check: negated condition
                        cleaned_props[pk] = pv  # assign
                else:  # 否则
                    cleaned_props[pk] = pv  # assign
            entity = SemanticEntity(  # assign
                entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",  # assign
                entity_type=entity_type,  # assign
                bbox=prim.bbox,  # assign
                layer=prim.layer,  # assign
                confidence=0.9 if entity_type != "unknown" else 0.5,  # compare: inequality
                properties=cleaned_props,  # assign
            )  # code
            entities.append(entity)  # append: add to list

        # 归并同类重叠图元
        entities = self._merge_overlapping(entities)  # assign

        # 过滤过小的走廊实体（LINE 类型容易被误识别为走廊）
        # 走廊宽度 < 500mm 且 bbox 短边 < 500mm 的实体可能是微小图元误标
        filtered = []  # init: empty list
        for e in entities:  # 循环
            if e.type == "corridor":  # check: OR condition
                bb = e.bbox  # assign
                bw = bb.get("width", 0)  # assign
                bh = bb.get("height", 0)  # assign
                short_edge = min(bw, bh) if bw > 0 and bh > 0 else max(bw, bh)  # assign
                if short_edge < 500:  # 短边 < 500mm 不可能是走廊
                    continue  # 继续循环
            filtered.append(e)  # append: add to list
        entities = filtered  # assign

        return entities  # return

    def _is_near_closed(
        self, prim: RawPrimitive, gap_threshold_mm: float = 500.0
    ) -> bool:  # method: def _is_near_closed(self, prim: RawPrimitive, gap_threshold_
        """接近闭合检测：开放多边形首尾点距离 < 阈值 → 视为闭合

        用于处理缺口房间（L 形/U 形房间在墙体断开处形成缺口）
        """
        pts = prim.properties.get("points")  # assign
        if not pts or len(pts) < 3:  # check: numeric comparison
            return False  # return: boolean
        # 校验 pts 结构（可能是 [(x,y), ...] 或 [[x,y], ...]）
        try:  # try: operation block
            first = pts[0]  # assign
            last = pts[-1]  # assign
            if isinstance(first, (list, tuple)) and len(first) >= 2:  # check: numeric comparison
                start = (float(first[0]), float(first[1]))  # assign
                end = (float(last[0]), float(last[1]))  # assign
            else:  # else: default case
                return False  # return: boolean
        except (TypeError, IndexError, ValueError):  # catch: exception handler
            return False  # return: boolean
        dx = end[0] - start[0]  # assign
        dy = end[1] - start[1]  # assign
        gap = math.sqrt(dx * dx + dy * dy)  # assign
        return gap < gap_threshold_mm  # return

    def _merge_line_chains_to_rooms(
        self, entities: List[SemanticEntity], primitives: List[RawPrimitive]
    ) -> List[
        SemanticEntity
    ]:  # method: def _merge_line_chains_to_rooms(self, entities: List[Semanti
        """多段线复合房间识别：LINE 链闭合检测

        将首尾相连的 LINE 图元组合成闭合链，满足条件后合并为 room 实体。
        处理建筑师用多个 LINE 绘制房间轮廓的情况。
        """
        # 收集 LINE 图元（未被分类为 room 的）
        lines = []  # init: empty list
        for prim in primitives:  # loop: for prim in primitives:
            if prim.dxf_type == "LINE":  # condition: prim.dxf_type == "LINE":
                lines.append(prim)  # append: add to list
        if len(lines) < 3:  # check: numeric comparison
            return entities  # return

        # 端点匹配阈值（mm）
        match_threshold = 100.0  # assign

        # 建立邻接表（使用坐标四舍五入到 mm 精度，避免浮点误差）
        def _round_point(p):  # method: def _round_point(p):
            return (round(p[0], 1), round(p[1], 1))  # return: tuple

        point_to_lines = {}  # init: empty dict
        for i, line in enumerate(lines):  # loop: for i, line in enumerate(lines):
            sp = line.properties.get("start_point", {})  # assign
            ep = line.properties.get("end_point", {})  # assign
            p1 = (sp.get("x", 0), sp.get("y", 0))  # assign
            p2 = (ep.get("x", 0), ep.get("y", 0))  # assign
            rp1 = _round_point(p1)  # assign
            rp2 = _round_point(p2)  # assign
            point_to_lines.setdefault(rp1, []).append((i, 0, p1, p2))  # append: add to list
            point_to_lines.setdefault(rp2, []).append((i, 1, p1, p2))  # append: add to list

        # DFS 找闭合链
        visited = [False] * len(lines)  # assign
        closed_chains = []  # init: empty list

        for start_i in range(len(lines)):  # loop: for start_i in range(len(lines)):
            if visited[start_i]:  # condition: visited[start_i]:
                continue  # code
            chain = [start_i]  # assign
            visited[start_i] = True  # assign
            current = start_i  # assign
            current_end = 1  # 0=start, 1=end
            # 记录遍历路径中的端点（用于面积计算）
            path_pts = []  # init: empty list

            # 获取起始线的端点
            sl = lines[start_i]  # assign
            sp = sl.properties.get("start_point", {})  # assign
            ep = sl.properties.get("end_point", {})  # assign
            path_pts.append((sp.get("x", 0), sp.get("y", 0)))  # append: add to list
            path_pts.append((ep.get("x", 0), ep.get("y", 0)))  # append: add to list

            # 遍历链
            max_depth = 50  # 防止无限循环
            depth = 0  # init: set to 0
            while depth < max_depth:  # loop: while depth < max_depth:
                depth += 1  # accumulate
                # 获取当前线的端点
                line = lines[current]  # assign
                sp = line.properties.get("start_point", {})  # assign
                ep = line.properties.get("end_point", {})  # assign
                p1 = (sp.get("x", 0), sp.get("y", 0))  # assign
                p2 = (ep.get("x", 0), ep.get("y", 0))  # assign
                rp1 = _round_point(p1)  # assign
                rp2 = _round_point(p2)  # assign

                # 当前端点（四舍五入后）
                current_rp = rp1 if current_end == 0 else rp2  # compare: equality

                # 找下一个线
                found_next = False  # assign
                for ni, nend, nsp, nep in point_to_lines.get(
                    current_rp, []
                ):  # loop: for (ni, nend, nsp, nep) in point_to_lines.get(cur
                    if ni == current:  # condition: ni == current:
                        continue  # code
                    if visited[ni]:  # condition: visited[ni]:
                        # 如果回到起点且链长度 >= 3 → 闭合
                        if ni == start_i and len(chain) >= 3:  # check: numeric comparison
                            closed_chains.append((chain, path_pts))  # append: add to list
                            break  # code
                        continue  # code
                    visited[ni] = True  # assign
                    chain.append(ni)  # append: add to list
                    # 添加新线的另一个端点（非连接点）到路径
                    if nend == 0:  # 连接点是 start，新端点是 end
                        path_pts.append((nep[0], nep[1]))  # append: add to list
                    else:  # 连接点是 end，新端点是 start
                        path_pts.append((nsp[0], nsp[1]))  # append: add to list
                    current = ni  # assign
                    # 确定下一个线的起始端点
                    current_end = 1 - nend  # assign
                    found_next = True  # assign
                    break  # code
                if not found_next:  # check: negated condition
                    break  # code

            # 检查是否闭合回到起点（通过距离阈值）
            if len(chain) >= 3:  # check: numeric comparison
                # 路径最后一个点
                last_pt = path_pts[-1] if path_pts else None  # assign
                # 起始线的两个端点
                sl = lines[start_i]  # assign
                sp = sl.properties.get("start_point", {})  # assign
                ep = sl.properties.get("end_point", {})  # assign
                sp_start = (sp.get("x", 0), sp.get("y", 0))  # assign
                sp_end = (ep.get("x", 0), ep.get("y", 0))  # assign
                if last_pt and (  # check: AND condition
                    (
                        abs(last_pt[0] - sp_start[0]) < match_threshold
                        and abs(last_pt[1] - sp_start[1]) < match_threshold
                    )  # call
                    or (
                        abs(last_pt[0] - sp_end[0]) < match_threshold
                        and abs(last_pt[1] - sp_end[1]) < match_threshold
                    )
                ):  # call
                    # 检查是否已存在
                    is_dup = False  # assign
                    for (
                        existing_chain,
                        _,
                    ) in closed_chains:  # loop: for existing_chain, _ in closed_chains:
                        if set(chain) == set(
                            existing_chain
                        ):  # condition: set(chain) == set(existing_chain):
                            is_dup = True  # assign
                            break  # code
                    if not is_dup:  # check: negated condition
                        closed_chains.append((chain, path_pts))  # append: add to list

        # 对闭合链计算面积，符合条件的合并为 room
        non_room_layers = [
            "COLU",
            "视口",
            "洞口",
            "板边",
            "梁边",
            "轴",
            "BASE",
            "梁",
            "吊筋",
            "板层",
            "文字",
            "钢筋",
            "标注",
            "DIM",
            "立面看线",
            "立面",
            "看线",
            "园林",
            "井",
            "电-",
            "电气",
            "照明",
            "插座",
            "弱电",
            "消防",
            "火灾",
            "报警",
            "设备",
            "电缆",
            "系统",
            "Defpoints",
        ]  # assign
        new_rooms = []  # init: empty list
        for chain, pts in closed_chains:  # loop: for chain, pts in closed_chains:
            if len(pts) < 3:  # check: numeric comparison
                continue  # code

            # 检查链中是否有非建筑图元（任一 LINE 在非建筑图层上）
            has_non_building = False  # assign
            for idx in chain:  # loop: for idx in chain:
                prim = lines[idx]  # assign
                if any(
                    kw in prim.layer.upper() for kw in non_room_layers
                ):  # check: membership test
                    has_non_building = True  # assign
                    break  # code
            if has_non_building:  # condition: has_non_building:
                continue  # code

            # 计算面积（鞋带公式）
            area = abs(
                sum(
                    pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                    for i in range(len(pts))
                )
                / 2
            )  # assign: membership check

            # 面积条件：1m² < area < 500m²
            if area < 1000000 or area > 500000000:  # check: numeric comparison
                continue  # code

            # bbox
            xs = [p[0] for p in pts]  # assign: membership check
            ys = [p[1] for p in pts]  # assign: membership check

            # 宽高比过滤：极端长条形不是房间
            bw = max(xs) - min(xs)  # assign
            bh = max(ys) - min(ys)  # assign
            if bw > 0 and bh > 0:  # check: both positive
                aspect = max(bw, bh) / min(bw, bh)  # assign
                if aspect > 8.0:  # 宽高比 > 8:1 不是房间（走廊/管道/线槽）
                    continue  # code

            # bbox dict
            bbox = {
                "x": min(xs),
                "y": min(ys),
                "width": max(xs) - min(xs),
                "height": max(ys) - min(ys),
            }  # assign

            # 创建 room 实体
            room_id = f"line_chain_room_{self._entity_counter}"  # assign
            self._entity_counter += 1  # assign: self attribute
            room = SemanticEntity(  # assign
                entity_id=room_id,  # assign
                entity_type="room",  # assign
                layer="",  # assign
                properties={"area": area / 1000000},  # 转为 m²
                bbox=bbox,  # assign
            )  # code
            new_rooms.append(room)  # append: add to list

        return entities + new_rooms  # return

    def _classify_by_layer(
        self, layer: str
    ) -> str:  # method: def _classify_by_layer(self, layer: str) -> str:
        """图层规则归类

        长关键字（≥3字符）：子串匹配
        短关键字（1-2字符）：全词匹配（前后是_或边界），防止误匹配
        """
        if not layer:  # check: negated condition
            return "unknown"  # return
        layer_upper = layer.upper()  # assign

        # 长关键字（≥3字符）：子串匹配
        for keyword, entity_type in LAYER_RULES.items():  # 循环
            if keyword in layer_upper:  # check: membership test
                return entity_type  # return

        # 短关键字（1-2字符）：全词匹配
        for keyword, entity_type in SHORT_LAYER_RULES.items():  # 循环
            if keyword in layer_upper:  # check: membership test
                # 检查全词边界
                idx = layer_upper.find(keyword)  # assign
                while idx >= 0:  # 循环
                    pre_ok = idx == 0 or layer_upper[idx - 1] == "_"  # compare: equality
                    post_ok = (
                        idx + len(keyword) >= len(layer_upper)
                        or layer_upper[idx + len(keyword)] == "_"
                    )  # compare: equality
                    if pre_ok and post_ok:  # check: AND condition
                        return entity_type  # return
                    idx = layer_upper.find(keyword, idx + 1)  # assign

        return "unknown"  # return

    def _classify_by_geometry(
        self, prim: RawPrimitive
    ) -> str:  # method: def _classify_by_geometry(self, prim: RawPrimitive) -> str:
        """几何特征兜底归类（V2深度升级版）

        新增规则：
        - 短 LINE 且靠近 DIMENSION 标注的 defpoint → door
        - 小面积闭合多边形（门打开轨迹）→ door
        - 靠近门的 ARC → door
        - 狭长闭合多边形 → corridor
        - 大尺寸 CIRCLE（>3000mm）→ stair
        """
        dxf_type = prim.dxf_type  # assign
        bbox = prim.bbox  # assign
        bw = bbox.get("width", 0)  # assign
        bh = bbox.get("height", 0)  # assign
        area = bw * bh  # assign
        props = prim.properties  # assign
        length = props.get("length", 0) or max(bw, bh)  # assign
        short_edge = min(bw, bh) if bw > 0 and bh > 0 else length  # assign

        if dxf_type == "LINE":  # condition: dxf_type == "LINE":
            if length > 2000:  # check: numeric comparison
                return "wall"  # return
            # 中等长度 LINE（700~2000mm）：典型门宽范围 → door
            if 700 < length < 2000 and short_edge < 50:  # check: numeric comparison
                return "door"  # return
            # 短 LINE（50~700mm）可能是门的宽度线或小构件
            if 50 < length < 700 and short_edge < 5:  # check: numeric comparison
                return "door"  # return
            # LINE 类型 bbox 短边≈0（纯线无宽度），不可能是走廊
            # 只有长度 > 2000mm 的 LINE 才可能归类为 wall（已处理）
            return "other"  # return

        if dxf_type in ("LWPOLYLINE", "POLYLINE"):  # check: membership test
            pts_count = props.get("point_count", 0)  # assign
            if pts_count == 2:  # condition: pts_count == 2:
                # 2 点 LWPOLYLINE：视为 LINE 等价
                if length > 2000:  # check: numeric comparison
                    return "wall"  # return
                if 700 < length < 2000 and short_edge < 50:  # check: numeric comparison
                    return "door"  # return
                if 50 < length < 700 and short_edge < 5:  # check: numeric comparison
                    return "door"  # return
                return "other"  # return

            # 闭合多边形判断（含缺口补全）
            is_closed = props.get("area", 0) > 0 or (pts_count >= 3)  # assign
            if not is_closed and pts_count >= 3:  # check: numeric comparison
                is_closed = self._is_near_closed(prim, gap_threshold_mm=500.0)  # assign
            if is_closed:  # condition: is_closed:
                aspect_ratio = max(bw, bh) / max(short_edge, 1)  # assign
                # P77：area=0 的闭合多边形（stair 2 点 LWPOLYLINE 等退化几何）
                # 不是真正的房间，跳过 room 判定
                if area == 0 and pts_count == 2:  # check: numeric comparison
                    return "other"  # return: 2 点退化多边形，不是房间
                # 图层排除：非建筑图层上的闭合多边形不可能是房间
                non_room_layers = [
                    "COLU",
                    "视口",
                    "洞口",
                    "板边",
                    "梁边",
                    "轴",
                    "BASE",
                    "梁",
                    "吊筋",
                    "板层",
                    "文字",
                    "钢筋",
                    "标注",
                    "DIM",
                    "立面看线",
                    "立面",
                    "看线",
                    "园林",
                    "井",
                    "电-",
                    "电气",
                    "照明",
                    "插座",
                    "弱电",
                    "消防",
                    "火灾",
                    "报警",
                    "系统",
                    "设备",
                    "电缆",
                    "WIRE",
                    "线槽",
                    "DOTLN",
                    "DOT",
                    "Defpoints",
                ]  # assign
                if any(
                    kw in prim.layer.upper() for kw in non_room_layers
                ):  # check: membership test
                    if aspect_ratio > 3:  # check: numeric comparison
                        return "other"  # return
                    return "wall"  # return
                # 默认图层（0/00）上的闭合多边形：电气图中大量线槽/表格轮廓在此
                # 只有宽高比 < 3 且面积 > 10m² 才可能为房间
                if prim.layer.strip() in ("0", "00", ""):  # check: membership test
                    if area < 10000000 or aspect_ratio > 3:  # < 10m² 或狭长
                        return "other"  # return
                # room 最小面积 1m²（1,000,000mm²），过滤小框/文字标注
                # room 最大面积 500m²（500,000,000mm²），过滤图纸边界框/标题栏框
                if area > 500000000:  # > 500m² → 图纸边界/标题栏，不是房间
                    return "other"  # return
                if area > 1000000:  # > 1m²
                    if aspect_ratio > 5:  # check: numeric comparison
                        # 狭长 → 走廊
                        if length > 3000:  # check: numeric comparison
                            return "wall"  # return
                        return "corridor"  # return
                    return "room"  # return
                elif area > 50000:  # 大面积但 < 1m²
                    if aspect_ratio > 5:  # check: numeric comparison
                        if length > 3000:  # check: numeric comparison
                            return "wall"  # return
                        return "corridor"  # return
                    return "wall"  # return
                elif area > 50000:  # 条件分支
                    # 中等面积（0.05~1m²）：可能是小房间或设备间
                    if aspect_ratio > 4:  # check: numeric comparison
                        return "corridor"  # return
                    return "room"  # return
                elif area > 5000:  # 条件分支
                    # 小面积（0.005~0.05m²）：通常是文字框/图例框/标注框，不是房间
                    return "other"  # return
                else:  # 否则
                    # 小面积闭合多边形（500~5000mm²）→ door 或 window
                    if aspect_ratio > 3:  # check: numeric comparison
                        # 狭长小面积 → 门的开合轨迹
                        return "door"  # return
                    elif aspect_ratio < 1.5:  # 条件分支
                        # 接近正方形的小面积 → column
                        return "column"  # return
                    return "door"  # return
            return "corridor"  # return

        # ARC：门弧、窗或弧形房间
        if dxf_type == "ARC":  # condition: dxf_type == "ARC":
            radius = props.get("radius", 0)  # assign
            # 大半径 ARC（>3000mm）且弧线角度大 → 弧形房间轮廓
            if radius > 3000:  # check: numeric comparison
                angle_span = (
                    abs(props.get("start_angle", 0) - props.get("end_angle", 0)) or 0
                )  # assign
                # 弧线跨度 > 90° 视为房间轮廓
                if angle_span > 90:  # check: numeric comparison
                    return "room"  # return
            if 100 < radius < 2000:  # check: numeric comparison
                return "door"  # return
            return "window"  # return

        if dxf_type == "CIRCLE":  # condition: dxf_type == "CIRCLE":
            radius = props.get("radius", 0)  # assign
            if radius > 3000:  # check: numeric comparison
                return "stair"  # return
            elif radius > 1000:  # 条件分支
                return "stair"  # return
            elif radius > 300:  # 条件分支
                return "column"  # return
            # P34: 小半径 CIRCLE 可能是消防设备
            if 50 <= radius <= 300:  # check: numeric comparison
                # 结合图层判断
                layer = prim.layer.upper()  # assign
                if any(
                    kw in layer
                    for kw in ["消防", "FIRE", "FAS", "报警", "ALARM", "喷淋", "SPRINKLER"]
                ):  # check: membership test
                    return "sprinkler"  # return
                if any(
                    kw in layer for kw in ["设备", "EQUIP", "电-", "电气", "ELEC"]
                ):  # check: membership test
                    return "equipment"  # return
                if any(
                    kw in layer for kw in ["照明", "LIGHT", "应急", "EVAC"]
                ):  # check: membership test
                    return "evacuation_lighting"  # return
                return "column"  # return
            return "column"  # return

        # P34: SOLID/HATCH 实体可能是消防设备填充
        if dxf_type == "SOLID":  # condition: dxf_type == "SOLID":
            layer = prim.layer.upper()  # assign
            if any(
                kw in layer for kw in ["消防", "FIRE", "喷淋", "SPRINKLER", "消火栓", "HYDRANT"]
            ):  # check: membership test
                return "sprinkler"  # return
            if any(
                kw in layer for kw in ["设备", "EQUIP", "电-", "电气", "ELEC"]
            ):  # check: membership test
                return "equipment"  # return
            return "other"  # return

        if dxf_type == "HATCH":  # condition: dxf_type == "HATCH":
            layer = prim.layer.upper()  # assign
            if any(
                kw in layer for kw in ["消防", "FIRE", "喷淋", "SPRINKLER"]
            ):  # check: membership test
                return "sprinkler"  # return
            return "other"  # return

        if dxf_type == "TEXT":  # condition: dxf_type == "TEXT":
            text = props.get("text", "")  # assign
            if not text:  # check: negated condition
                return "text"  # return
            text_upper = text.upper()  # assign
            if "出口" in text or "EXIT" in text_upper:  # check: membership test
                return "exit"  # return
            if "楼梯" in text or "STAIR" in text_upper:  # check: membership test
                return "stair"  # return
            # "防火" 关键词需配合 "门" 或 "窗" 才能归类，避免文本描述被误标
            if "防火门" in text or (
                "FIRE" in text_upper and "DOOR" in text_upper
            ):  # check: membership test
                return "fire_door"  # return
            if "防火窗" in text or (
                "FIRE" in text_upper and "WINDOW" in text_upper
            ):  # check: membership test
                return "fire_window"  # return
            # ── 消防设施/系统关键词（用于真实图纸 TEXT 辅助识别） ──
            if "消火栓" in text or "HYDRANT" in text_upper:  # check: membership test
                return "fire_hydrant"  # return
            if (
                "喷淋" in text or "洒水" in text or "SPRINKLER" in text_upper
            ):  # check: membership test
                return "sprinkler"  # return
            if "灭火器" in text or "灭火" in text:  # check: membership test
                return "fire_extinguisher"  # return
            if (
                "烟感" in text or "烟雾探测" in text or "探测器" in text or "SMOKE" in text_upper
            ):  # check: membership test
                return "smoke_detector"  # return
            if "报警" in text or "ALARM" in text_upper:  # check: membership test
                return "fire_alarm"  # return
            if "消防水箱" in text or "水箱" in text:  # check: membership test
                return "water_tank"  # return
            if "消防水池" in text or "水池" in text:  # check: membership test
                return "water_reservoir"  # return
            if (
                "广播" in text or "音箱" in text or "SPEAKER" in text_upper
            ):  # check: membership test
                return "emergency_broadcast"  # return
            if "应急照明" in text or "EVAC" in text_upper:  # check: membership test
                return "evacuation_lighting"  # return
            if "卷帘" in text or "CURTAIN" in text_upper:  # check: membership test
                return "fire_curtain"  # return
            if "消防电梯" in text or "FIRE_ELEV" in text_upper:  # check: membership test
                return "fire_elevator"  # return
            if "声光" in text:  # check: membership test
                return "fire_alarm"  # return
            # ── P70 消防泵/水泵接合器/启泵按钮 TEXT 识别 ──
            if (
                "消防泵" in text
                or "喷淋泵" in text
                or "稳压泵" in text
                or "消火栓泵" in text
                or "PUMP" in text_upper
            ):
                return "fire_pump"  # return
            if "水泵接合器" in text or "接合器" in text or "SIAMESE" in text_upper:
                return "siamese_connection"  # return
            if "启泵按钮" in text or "消火栓按钮" in text or "CALL_POINT" in text_upper:
                return "hydrant_call_button"  # return
            if "泵控制柜" in text or "启泵柜" in text or "PUMP_CTRL" in text_upper:
                return "pump_controller"  # return
            # ── P70 高频缺口 TEXT 识别 ──
            if "探测器" in text or "detector" in text_upper or "DET" in text_upper:
                return "detector"  # return
            if "楼层" in text or "FLOOR" in text_upper or "层" in text:
                return "floor"  # return
            if "泵房" in text or "PUMP_ROOM" in text_upper:
                return "pump_room"  # return
            if "防火墙" in text or "FIRE_WALL" in text_upper:
                return "fire_wall"  # return
            if "防火卷帘" in text or "FIRE_SHUTTER" in text_upper:
                return "fire_shutter"  # return
            if "控制室" in text or "FIRE_CONTROL" in text_upper or "消防控制" in text:
                return "control_room"  # return
            if "救援窗" in text or "RESCUE_WIN" in text_upper or "救援口" in text:
                return "rescue_window"  # return
            if "扬声器" in text or "SPEAKER" in text_upper or "喇叭" in text:
                return "speaker"  # return
            if "道路" in text or "ROAD" in text_upper or "消防车道" in text:
                return "road"  # return
            if "车道" in text or "DRIVE" in text_upper:
                return "driveway"  # return
            if "电源" in text or "POWER_SUPPLY" in text_upper:
                return "power_supply"  # return
            # ── P70 高频缺口 TEXT 识别（第2批） ──
            if "楼梯间" in text or "STAIRCASE" in text_upper or "STAIR_CASE" in text_upper:
                return "staircase"  # return
            if "出口门" in text or "EXIT_DOOR" in text_upper or "安全出口门" in text:
                return "exit_door"  # return
            if (
                "泵" in text
                and "消防泵" not in text
                and "喷淋泵" not in text
                and "消火栓泵" not in text
            ):
                return "pump"  # return
            if "避难层" in text or "REFUGE_FLOOR" in text_upper:
                return "refuge_floor"  # return
            if "前室" in text or "ANTEROOM" in text_upper:
                return "antechamber"  # return
            if "消防车道" in text and "road" not in text_lower:
                return "fire_lane"  # return
            if "消防水箱" in text or "FIRE_WATER_TANK" in text_upper:
                return "fire_water_tank"  # return
            if "室内消火栓" in text or "INDOOR_HYDRANT" in text_upper:
                return "indoor_hydrant"  # return
            if "避难区" in text or "REFUGE_AREA" in text_upper:
                return "refuge_area"  # return
            if "避难间" in text or "REFUGE_ROOM" in text_upper:
                return "refuge_room"  # return
            if "消防广播" in text or "FIRE_BROADCAST" in text_upper:
                return "fire_broadcast"  # return
            if "楼梯间前室" in text or "STAIRCASE_LOBBY" in text_upper:
                return "staircase_lobby"  # return
            if "设备间" in text or "EQ_ROOM" in text_upper:
                return "equipment_room"  # return
            # ── P47 无障碍 TEXT 识别 ──
            if "坡道" in text or "RAMP" in text_upper:
                return "ramp"
            if "扶手" in text or "HANDRAIL" in text_upper:
                return "handrail"
            if "盲道" in text or "TACTILE" in text_upper:
                return "tactile_guide"
            if "无障碍卫生间" in text or "无障碍厕所" in text:
                return "accessible_toilet"
            if "无障碍电梯" in text or "ACCESSIBLE_ELEV" in text_upper:
                return "accessible_elevator"
            if (
                "无障碍出入口" in text
                or "ACCESSIBLE_DOOR" in text_upper
                or "残疾人入口" in text
                or "无障碍入口" in text
            ):
                return "accessible_door"
            if "轮椅" in text or "WHEELCHAIR" in text_upper:
                return "wheelchair_space"
            if "无障碍车位" in text or "无障碍停车" in text:
                return "parking_space"
            if "无障碍" in text or "ACCESSIBLE" in text_upper:
                return "accessible_path"
            return "text"  # return

        # INSERT 块：从块名推断实体类型（完整映射表）
        if dxf_type == "INSERT":  # condition: dxf_type == "INSERT":
            block_name = props.get("block_name", "").upper()  # assign
            # ── 防火门/防火窗 ──
            if "FIRE_DOOR" in block_name or "防火门" in block_name:  # check: membership test
                return "fire_door"  # return
            if "FIRE_WINDOW" in block_name or "防火窗" in block_name:  # check: membership test
                return "fire_window"  # return
            # ── 建筑构件 ──
            if "DOOR" in block_name or "门" in block_name:  # check: membership test
                return "door"  # return
            if "WINDOW" in block_name or "窗" in block_name:  # check: membership test
                return "window"  # return
            if "STAIR" in block_name or "ST" in block_name:  # check: membership test
                return "stair"  # return
            if "COLUMN" in block_name or "柱" in block_name:  # check: membership test
                return "column"  # return
            # ── 出口/疏散指示 ──
            if "EXIT" in block_name or "出口" in block_name:  # check: membership test
                return "exit"  # return
            if (
                "EXIT_SIGN" in block_name or "SIGN" in block_name or "疏散指示" in block_name
            ):  # check: membership test
                return "exit_sign"  # return
            # ── 消防设施 ──
            if "HYDRANT" in block_name or "消火栓" in block_name:  # check: membership test
                return "fire_hydrant"  # return
            if (
                "SPRINKLER" in block_name or "喷淋" in block_name or "洒水" in block_name
            ):  # check: membership test
                return "sprinkler"  # return
            if (
                "FIRE_EXT" in block_name or "灭火器" in block_name or "灭火" in block_name
            ):  # check: membership test
                return "fire_extinguisher"  # return
            if "SMOKE_DETECTOR" in block_name or "烟感" in block_name:  # check: membership test
                return "smoke_detector"  # return
            if "FIRE_ALARM" in block_name or "报警" in block_name:  # check: membership test
                return "fire_alarm"  # return
            if "WATER_TANK" in block_name or "水箱" in block_name:  # check: membership test
                return "water_tank"  # return
            if (
                "WATER_RESERVOIR" in block_name or "消防水池" in block_name or "水池" in block_name
            ):  # check: membership test
                return "water_reservoir"  # return
            if "FIRE_ELEV" in block_name or "消防电梯" in block_name:  # check: membership test
                return "fire_elevator"  # return
            if (
                "SPEAKER" in block_name or "广播" in block_name or "应急广播" in block_name
            ):  # check: membership test
                return "emergency_broadcast"  # return
            if "EVAC_LIGHT" in block_name or "应急照明" in block_name:  # check: membership test
                return "evacuation_lighting"  # return
            if "CURTAIN" in block_name or "卷帘" in block_name:  # check: membership test
                return "fire_curtain"  # return
            # ── 电气设备（新增） ──
            if (
                "DISTRIBUTION_BOX" in block_name or "配电箱" in block_name or "配电" in block_name
            ):  # check: membership test
                return "distribution_box"  # return
            if (
                "EMERGENCY_LIGHT" in block_name
                or "应急照明" in block_name
                or "应急灯" in block_name
            ):  # check: membership test
                return "emergency_lighting"  # return
            if (
                "SMOKE_DETECTOR" in block_name or "烟感" in block_name or "烟探测器" in block_name
            ):  # check: membership test
                return "smoke_detector"  # return
            if (
                "HEAT_DETECTOR" in block_name or "温感" in block_name or "温探测器" in block_name
            ):  # check: membership test
                return "heat_detector"  # return
            if (
                "ALARM_BUTTON" in block_name or "报警按钮" in block_name or "手报" in block_name
            ):  # check: membership test
                return "alarm_button"  # return
            if (
                "GAS_SUPPRESSION" in block_name or "气体灭火" in block_name or "气灭" in block_name
            ):  # check: membership test
                return "gas_suppression"  # return
            if (
                "BELL" in block_name or "警铃" in block_name or "声光" in block_name
            ):  # check: membership test
                return "fire_bell"  # return
            # ── P70 泵控制柜（必须在通用 PUMP 之前，避免误匹配） ──
            if (
                "PUMP_CONTROLLER" in block_name
                or "PUMP_CTRL" in block_name
                or "PUMPCTRL" in block_name
                or "泵控" in block_name
                or "启泵柜" in block_name
                or "水泵控制柜" in block_name
            ):
                return "pump_controller"  # return
            # ── P70 消防泵/水泵接合器/启泵按钮 ──
            if (
                "FIRE_PUMP" in block_name
                or "SPRINKLER_PUMP" in block_name
                or "STABLE_PRESSURE_PUMP" in block_name
                or "消防泵" in block_name
                or "喷淋泵" in block_name
                or "稳压泵" in block_name
                or "消火栓泵" in block_name
                or "水泵" in block_name
                or "PUMP" in block_name
            ):  # check: membership test
                return "fire_pump"  # return
            if (
                "SIAMESE" in block_name
                or "FIRE_DEPT_CONN" in block_name
                or "SIAMESE_CONN" in block_name
                or "水泵接合器" in block_name
                or "接合器" in block_name
            ):  # check: membership test
                return "siamese_connection"  # return
            if (
                "CALL_POINT" in block_name or "消火栓按钮" in block_name or "栓" in block_name
            ):  # check: membership test
                return "hydrant_call_button"  # return
            if (
                "VESDA" in block_name or "极早期" in block_name or "吸气式" in block_name
            ):  # check: membership test
                return "vesda_detector"  # return
            if (
                "EMERGENCY_POWER" in block_name or "应急电源" in block_name or "EPS" in block_name
            ):  # check: membership test
                return "emergency_power"  # return
            # ── 其他楼层/空间 ──
            if (
                "ROOM" in block_name or "房间" in block_name or "室" in block_name
            ):  # check: membership test
                return "room"  # return
            if (
                "CORRIDOR" in block_name or "走廊" in block_name or "走道" in block_name
            ):  # check: membership test
                return "corridor"  # return
            if (
                "SHAFT" in block_name or "井道" in block_name or "竖井" in block_name
            ):  # check: membership test
                return "shaft"  # return
            if "ELEVATOR" in block_name or "电梯" in block_name:  # check: membership test
                return "elevator"  # return
            if "LOBBY" in block_name or "前室" in block_name:  # check: membership test
                return "lobby"  # return
            if "FIRE_ZONE" in block_name or "防火分区" in block_name:  # check: membership test
                return "fire_zone"  # return
            # ── 未知块名 → 回退到 wall ──
            return "wall"  # return

        return "unknown"  # return

    def _infer_corridor_widths(
        self,
        entities: List[
            SemanticEntity
        ],  # method: def _infer_corridor_widths(self, entities: List[SemanticEnti
        primitives: List[RawPrimitive] = None,
    ) -> List[SemanticEntity]:  # 操作
        """从 bbox 短边和平行线聚类推断走廊/门的宽度（真实图纸适配）

        两层策略：
        1. 平行线聚类（primitives 可用时）：收集走廊图元，按方向分组，
           找平行线间距作为走廊宽度
        2. bbox 短边：对已有非零 bbox 的实体，短边*0.001 为宽度
        """
        import math  # stdlib: math functions
        from collections import defaultdict  # stdlib import

        # 防御性过滤：修复 NaN bbox
        for ent in entities:  # 循环
            bbox = ent.bbox  # assign
            for k in ("x", "y", "width", "height"):  # loop: for k in ('X', 'y', 'width', 'height'):
                v = bbox.get(k, 0)  # assign
                if isinstance(v, float) and math.isnan(v):  # check: AND condition
                    bbox[k] = 0.0  # init: set to 0

        # ── 策略1：平行线聚类宽度推断（按空间分区）──
        if primitives:  # condition: primitives:
            # 收集可能的走廊原始图元（LINE + 2点LWPOLYLINE）
            edge_candidates = []  # init: empty list
            for p in primitives:  # 循环
                bbox = p.bbox  # assign
                cx = bbox.get("x", 0) + bbox.get("width", 0) / 2  # assign
                cy = bbox.get("y", 0) + bbox.get("height", 0) / 2  # assign
                # 排除坐标偏移的图元
                if abs(cx) < 100 and abs(cy) < 100:  # check: numeric comparison
                    continue  # 继续循环
                if abs(cx) > 1e7 or abs(cy) > 1e7:  # check: numeric comparison
                    continue  # 继续循环
                bw = bbox.get("width", 0)  # assign
                bh = bbox.get("height", 0)  # assign
                span = max(bw, bh)  # assign
                if span < 100 or span > 100000:  # 0.1m~100m 合理范围
                    continue  # 继续循环
                if p.dxf_type == "LINE":  # condition: p.dxf_type == "LINE":
                    angle = p.properties.get("angle", 0) % 180  # assign
                    if angle > 90:
                        angle = 180 - angle  # check: numeric comparison
                    edge_candidates.append(
                        {  # code
                            "cx": cx,
                            "cy": cy,
                            "bw": bw,
                            "bh": bh,  # 字段
                            "span": span,
                            "angle": angle,  # 字段
                        }
                    )  # code
                elif p.dxf_type == "LWPOLYLINE" and p.properties.get("point_count", 0) == 2:  # 分支
                    angle = 0 if bw > bh else 90  # init: set to 0
                    edge_candidates.append(
                        {  # code
                            "cx": cx,
                            "cy": cy,
                            "bw": bw,
                            "bh": bh,  # 字段
                            "span": span,
                            "angle": angle,  # 字段
                        }
                    )  # code

            if edge_candidates:  # check: AND condition
                # 按方向分组
                h_edges = [
                    e for e in edge_candidates if e["angle"] < 30
                ]  # assign: membership check
                v_edges = [
                    e for e in edge_candidates if e["angle"] > 60
                ]  # assign: membership check

                # 水平线：按cy排序，收集所有gap
                h_sorted = sorted(h_edges, key=lambda e: e["cy"])  # assign
                h_gaps = []  # init: empty list
                for i in range(min(300, len(h_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(h_sorted))):  # 循环
                        gap = abs(h_sorted[i]["cy"] - h_sorted[j]["cy"])  # assign
                        if 500 < gap < 10000:  # check: numeric comparison
                            h_gaps.append(
                                {
                                    "gap": gap,
                                    "y1": h_sorted[i]["cy"],
                                    "y2": h_sorted[j]["cy"],  # code
                                    "cx1": h_sorted[i]["cx"],
                                    "cx2": h_sorted[j]["cx"],
                                }
                            )  # 字段

                # 垂直线：按cx排序，收集所有gap
                v_sorted = sorted(v_edges, key=lambda e: e["cx"])  # assign
                v_gaps = []  # init: empty list
                for i in range(min(300, len(v_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(v_sorted))):  # 循环
                        gap = abs(v_sorted[i]["cx"] - v_sorted[j]["cx"])  # assign
                        if 500 < gap < 10000:  # check: numeric comparison
                            v_gaps.append(
                                {
                                    "gap": gap,
                                    "x1": v_sorted[i]["cx"],
                                    "x2": v_sorted[j]["cx"],  # code
                                    "cy1": v_sorted[i]["cy"],
                                    "cy2": v_sorted[j]["cy"],
                                }
                            )  # 字段

                all_gaps = h_gaps + v_gaps  # assign
                if all_gaps and len(all_gaps) > 10:  # check: numeric comparison
                    # 空间分区聚类：每条走廊取离它最近的 gap 作为宽度
                    # 1) 对每个 gap，按位置分到最近的走廊
                    # 2) 每个走廊取其区域内 gap 众数
                    corridor_entities = [
                        e for e in entities if e.type == "corridor"
                    ]  # compare: equality
                    if corridor_entities:  # check: OR condition
                        for ent in corridor_entities:  # 循环
                            cx = ent.bbox.get("x", 0) + ent.bbox.get("width", 0) / 2  # assign
                            cy = ent.bbox.get("y", 0) + ent.bbox.get("height", 0) / 2  # assign
                            bw = ent.bbox.get("width", 0)  # assign
                            bh = ent.bbox.get("height", 0)  # assign
                            # 先用 bbox 短边推断宽度（LINE 类型用长边）
                            if bw > 0 and bh > 0:  # check: numeric comparison
                                w_mm = min(bw, bh)  # assign
                                w_m = w_mm * 0.001  # assign
                                if (
                                    0.3 < w_m < 3.0 and ent.properties.get("width", 0) < w_m
                                ):  # check: numeric comparison
                                    ent.properties["width"] = w_m  # 操作
                                    ent.properties["clear_width"] = w_m  # 操作
                                    ent.properties["_width_source"] = "bbox_short_edge"  # 操作
                                    continue  # 继续循环

                            # bbox 短边≈0（LINE类型）：找附近gap
                            if ent.properties.get("width", 0) < 0.3:  # check: numeric comparison
                                # 找附近 gap
                                nearby_gaps = []  # init: empty list
                                for g in all_gaps:  # 循环
                                    if "y1" in g:  # 水平gap
                                        mid_y = (g["y1"] + g["y2"]) / 2  # assign
                                        mid_x = (g["cx1"] + g["cx2"]) / 2  # assign
                                        if (
                                            abs(cy - mid_y) < 3000 and abs(cx - mid_x) < 3000
                                        ):  # check: numeric comparison
                                            nearby_gaps.append(g["gap"])  # append: add to list
                                    else:  # 垂直gap
                                        mid_x = (g["x1"] + g["x2"]) / 2  # assign
                                        mid_y = (g["cy1"] + g["cy2"]) / 2  # assign
                                        if (
                                            abs(cx - mid_x) < 3000 and abs(cy - mid_y) < 3000
                                        ):  # check: numeric comparison
                                            nearby_gaps.append(g["gap"])  # append: add to list

                                if nearby_gaps:  # condition: nearby_gaps:
                                    # 取附近gap的众数作为此走廊宽度
                                    gap_buckets = defaultdict(list)  # assign
                                    for g in nearby_gaps:  # 循环
                                        bucket = round(g / 100) * 100  # assign
                                        gap_buckets[bucket].append(g)  # 操作
                                    best_bucket = max(
                                        gap_buckets.items(), key=lambda x: len(x[1])
                                    )  # assign
                                    w_m = (
                                        sum(best_bucket[1]) / len(best_bucket[1])
                                    ) / 1000.0  # assign
                                    if 0.3 < w_m < 3.0:  # check: numeric comparison
                                        ent.properties["width"] = w_m  # 操作
                                        ent.properties["clear_width"] = w_m  # 操作
                                        ent.properties["_width_source"] = "nearby_gap"  # 操作
                                else:  # 否则
                                    # 无附近gap：用bbox长边
                                    span_mm = max(bw, bh)  # assign
                                    w_m = span_mm * 0.001  # assign
                                    if 0.3 < w_m < 3.0:  # check: numeric comparison
                                        ent.properties["width"] = w_m  # 操作
                                        ent.properties["clear_width"] = w_m  # 操作
                                        ent.properties["_width_source"] = "bbox_long_edge"  # 操作

        # ── 策略1.5：door/window 宽度推断（V2增强）──
        for ent in entities:  # 循环
            if ent.type not in (
                "door",
                "window",
                "fire_door",
                "exit_door",
            ):  # check: membership test
                continue  # 继续循环
            existing = ent.properties.get("width", 0)  # assign
            if existing > 0.5:  # check: numeric comparison
                continue  # 继续循环
            # 从 ARC 半径推断门宽度（门弧半径 ≈ 门宽度）
            radius = ent.properties.get("radius", 0)  # assign
            if radius > 100 and radius < 2000:  # check: numeric comparison
                w_m = radius * 0.001  # mm → m
                if 0.3 < w_m < 2.0:  # check: numeric comparison
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
                    continue  # 继续循环
            # bbox 推断
            bbox = ent.bbox  # assign
            bw = bbox.get("width", 0)  # assign
            bh = bbox.get("height", 0)  # assign
            if bw > 0 and bh > 0:  # check: numeric comparison
                w_mm = min(bw, bh)  # assign
                w_m = w_mm * 0.001  # assign
                if (
                    0.3 < w_m < 2.0 and ent.properties.get("width", 0) < w_m
                ):  # check: numeric comparison
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
            # LINE 类型（短边≈0）：用长边作为宽度
            if ent.properties.get("width", 0) < 0.3:  # check: numeric comparison
                span_mm = max(bw, bh)  # assign
                if 300 < span_mm < 2000:  # 300mm~2m
                    w_m = span_mm * 0.001  # assign
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
            # Polygon 类 door（闭合多边形）：短边可能是门扇厚度，用长边推断宽度
            if ent.properties.get("width", 0) < 0.3:  # check: numeric comparison
                long_edge_mm = max(bw, bh)  # assign
                if 300 < long_edge_mm < 2000:  # check: numeric comparison
                    w_m = long_edge_mm * 0.001  # assign
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作

        # ── 策略2：bbox 短边推断（覆盖所有类型） ──
        for ent in entities:  # 循环
            if ent.type not in (
                "corridor",
                "door",
                "window",
                "room",
                "wall",
            ):  # check: membership test
                continue  # 继续循环
            bbox = ent.bbox  # assign
            bw = bbox.get("width", 0)  # assign
            bh = bbox.get("height", 0)  # assign

            if bw == 0 and bh == 0:  # check: AND condition
                continue  # 继续循环

            # bbox 两边非零 → 短边为宽度（mm→m），长边为 length
            if bw > 0 and bh > 0:  # check: numeric comparison
                w_mm = min(bw, bh)  # assign
                w_m = w_mm * 0.001  # assign
                if not math.isnan(w_m) and w_m > 0.01 and w_m < 10:  # check: numeric comparison
                    current_w = ent.properties.get("width", 0)  # assign
                    if current_w < w_m:  # check: numeric comparison
                        ent.properties["width"] = w_m  # 操作
                        ent.properties["clear_width"] = w_m  # 操作
                l_mm = max(bw, bh)  # assign
                if l_mm > 0:  # check: numeric comparison
                    ent.properties["length"] = l_mm * 0.001  # 操作
                continue  # 继续循环

            # bbox 只有一边非零（LINE / 2 点 LWPOLYLINE）
            span_mm = max(bw, bh)  # assign
            if span_mm > 0:  # check: numeric comparison
                span_m = span_mm * 0.001  # assign
                if not math.isnan(span_m) and span_m > 0.05:  # check: numeric comparison
                    ent.properties["length"] = span_m  # 操作
                    # 对 corridor/room：bbox短边≈宽度
                    if ent.type in (
                        "corridor",
                        "room",
                        "door",
                        "fire_door",
                        "exit_door",
                    ):  # check: membership test
                        short_mm = min(bw, bh) if bw > 0 and bh > 0 else 0  # assign
                        if short_mm > 0:  # check: numeric comparison
                            short_m = short_mm * 0.001  # assign
                            current_w = ent.properties.get("width", 0)  # assign
                            if (
                                current_w < 0.01 and 0.05 < short_m < 3.0
                            ):  # check: numeric comparison
                                ent.properties["width"] = short_m  # 操作
                                ent.properties["clear_width"] = short_m  # 操作

        return entities  # return

    def _merge_overlapping(
        self, entities: List[SemanticEntity]
    ) -> List[
        SemanticEntity
    ]:  # method: def _merge_overlapping(self, entities: List[SemanticEntity])
        """合并重叠/相邻的同类图元（空间哈希加速版）

        小数据量（<2000）直接 O(n²) 全量对比；
        大数据量使用网格分桶，只对比同网格或相邻网格内的实体。
        """
        n = len(entities)  # assign
        if n < 2:  # check: numeric comparison
            return entities  # return

        # ── 小数据量：直接 O(n²) 全量对比（开销小，无额外内存） ──
        if n < 2000:  # check: numeric comparison
            merged = []  # init: empty list
            used = set()  # init: empty set
            for i, a in enumerate(entities):  # loop: for i, a in enumerate(entities):
                if i in used:  # check: membership test
                    continue  # code
                cluster = [a]  # assign
                used.add(i)  # call
                for j, b in enumerate(entities):  # loop: for j, b in enumerate(entities):
                    if j in used:  # check: membership test
                        continue  # code
                    if (
                        a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5
                    ):  # check: numeric comparison
                        cluster.append(b)  # append: add to list
                        used.add(j)  # call
                if len(cluster) > 1:  # check: numeric comparison
                    merged_bbox = self._union_bbox(
                        [e.bbox for e in cluster]
                    )  # assign: membership check
                    merged.append(
                        SemanticEntity(  # code
                            entity_id=a.id,
                            entity_type=a.type,  # assign
                            bbox=merged_bbox,
                            layer=a.layer,  # assign
                            confidence=max(
                                e.confidence for e in cluster
                            ),  # assign: membership check
                            properties=a.properties,  # assign
                        )
                    )  # code
                else:  # else: default case
                    merged.append(a)  # append: add to list
            return merged  # return

        # ── 大数据量：空间哈希分桶 ──
        CELL_SIZE = 500.0  # mm，网格大小
        from collections import defaultdict  # stdlib import

        # 构建网格索引：{(gx, gy): [idx, ...]}
        grid = defaultdict(list)  # assign
        for idx, e in enumerate(entities):  # loop: for idx, e in enumerate(entities):
            bx = e.bbox.get("x", 0)  # assign
            by = e.bbox.get("y", 0)  # assign
            bw = max(e.bbox.get("width", 0), 1.0)  # assign
            bh = max(e.bbox.get("height", 0), 1.0)  # assign
            gx1 = int(bx / CELL_SIZE)  # assign
            gx2 = int((bx + bw) / CELL_SIZE)  # assign
            gy1 = int(by / CELL_SIZE)  # assign
            gy2 = int((by + bh) / CELL_SIZE)  # assign
            for gx in range(gx1, gx2 + 1):  # loop: for gx in range(gx1, gx2 + 1):
                for gy in range(gy1, gy2 + 1):  # loop: for gy in range(gy1, gy2 + 1):
                    grid[(gx, gy)].append(idx)  # append: add to list

        # 去重标记
        merged = []  # init: empty list
        used = set()  # init: empty set

        for i, a in enumerate(entities):  # loop: for i, a in enumerate(entities):
            if i in used:  # check: membership test
                continue  # code

            cluster = [a]  # assign
            used.add(i)  # call

            # 找到 a 所在的网格
            bx = a.bbox.get("x", 0)  # assign
            by = a.bbox.get("y", 0)  # assign
            bw = max(a.bbox.get("width", 0), 1.0)  # assign
            bh = max(a.bbox.get("height", 0), 1.0)  # assign
            gx1 = int(bx / CELL_SIZE)  # assign
            gx2 = int((bx + bw) / CELL_SIZE)  # assign
            gy1 = int(by / CELL_SIZE)  # assign
            gy2 = int((by + bh) / CELL_SIZE)  # assign

            # 收集相邻网格中的候选实体
            candidates = set()  # init: empty set
            for gx in range(gx1 - 1, gx2 + 2):  # loop: for gx in range(gx1 - 1, gx2 + 2):
                for gy in range(gy1 - 1, gy2 + 2):  # loop: for gy in range(gy1 - 1, gy2 + 2):
                    for idx in grid.get((gx, gy), []):  # loop: for idx in grid.get((gx, gy), []):
                        if idx not in used:  # check: membership test
                            candidates.add(idx)  # call

            for j in sorted(candidates):  # loop: for j in sorted(candidates):
                if j in used:  # check: membership test
                    continue  # code
                b = entities[j]  # assign
                if (
                    a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5
                ):  # check: numeric comparison
                    cluster.append(b)  # append: add to list
                    used.add(j)  # call

            if len(cluster) > 1:  # check: numeric comparison
                merged_bbox = self._union_bbox(
                    [e.bbox for e in cluster]
                )  # assign: membership check
                merged.append(
                    SemanticEntity(  # code
                        entity_id=a.id,
                        entity_type=a.type,  # assign
                        bbox=merged_bbox,
                        layer=a.layer,  # assign
                        confidence=max(e.confidence for e in cluster),  # assign: membership check
                        properties=a.properties,  # assign
                    )
                )  # code
            else:  # else: default case
                merged.append(a)  # append: add to list

        return merged  # return

    def _build_relations(
        self, entities: List[SemanticEntity]
    ) -> List[
        SpatialRelation
    ]:  # method: def _build_relations(self, entities: List[SemanticEntity]) -
        """构建空间关系（V2深度升级版）

        包括：
        - 相邻关系（相邻距离阈值，>500实体用空间哈希加速）
        - 墙体-门窗拓扑关系（精确匹配门在墙上的位置）
        - 走廊连通关系（门连接走廊与房间）
        - 包含关系（房间包含设备）

        性能优化：实体数 > 2000 时跳过全量相邻关系构建，
        仅保留墙体-门窗拓扑和包含关系。相邻关系主要用于
        疏散路径分析，大图纸 room 数量少，影响可控。
        """
        relations = []  # init: empty list
        n_entities = len(entities)  # assign

        # ── 1. 相邻关系（空间哈希加速，>2000 实体只构建关键实体对）──
        # 关键实体类型：room/corridor/door/exit/stair/fire_door/exit_door + wall
        # P76 修复：真实图纸 room 识别不足，fallback 到 lobby/pump_room/space 等空间类型，
        # 必须也参与相邻关系构建，否则 BFS 拓扑为空（has_route=False）
        # wall 必须包含：room↔wall adjacent 是 step 5 (room-wall-door 传递) 的基础
        KEY_ENTITY_TYPES = {
            "room",
            "corridor",
            "door",
            "exit",
            "stair",
            "fire_door",
            "exit_door",
            "lobby",
            "pump_room",
            "space",
            "anteroom",
            "elevator_lobby",
            "staircase_lobby",
            "entrance_hall",
        }

        CELL_SIZE = 100.0  # mm
        grid: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}

        # 选择需要构建相邻关系的实体
        if n_entities <= 2000:
            adj_candidates = list(enumerate(entities))
        else:
            # 大图纸：只对关键实体构建相邻关系
            adj_candidates = [(i, e) for i, e in enumerate(entities) if e.type in KEY_ENTITY_TYPES]

        for idx, e in adj_candidates:
            bx = e.bbox.get("x", 0)
            by = e.bbox.get("y", 0)
            bw = e.bbox.get("width", 0)
            bh = e.bbox.get("height", 0)
            x1_cell = int(bx / CELL_SIZE)
            x2_cell = int((bx + bw) / CELL_SIZE)
            y1_cell = int(by / CELL_SIZE)
            y2_cell = int((by + bh) / CELL_SIZE)
            for gx in range(x1_cell, x2_cell + 1):
                for gy in range(y1_cell, y2_cell + 1):
                    grid.setdefault((gx, gy), []).append((idx, e))

        compared = set()
        for idx_a, a in adj_candidates:
            bx = a.bbox.get("x", 0)
            by = a.bbox.get("y", 0)
            bw = a.bbox.get("width", 0)
            bh = a.bbox.get("height", 0)
            x1_cell = int(bx / CELL_SIZE)
            x2_cell = int((bx + bw) / CELL_SIZE)
            y1_cell = int(by / CELL_SIZE)
            y2_cell = int((by + bh) / CELL_SIZE)
            for gx in range(x1_cell - 1, x2_cell + 2):
                for gy in range(y1_cell - 1, y2_cell + 2):
                    for idx_b, b in grid.get((gx, gy), []):
                        if idx_b <= idx_a:
                            continue
                        pair_key = (idx_a, idx_b)
                        if pair_key in compared:
                            continue
                        compared.add(pair_key)
                        dist = self._min_edge_distance(a.bbox, b.bbox)
                        if dist < self.ADJACENT_THRESHOLD:
                            relations.append(
                                SpatialRelation(
                                    source_id=a.id,
                                    target_id=b.id,
                                    rel_type="adjacent",
                                    distance=dist,
                                    confidence=1.0 - dist / self.ADJACENT_THRESHOLD,
                                )
                            )

        # ── 2. 墙体-门窗拓扑关系（V2升级）──
        # 用几何方法精确匹配门/窗在墙上的位置：
        #   门 bbox 必须与墙 bbox 的某条边重叠（门在墙上）
        #   取最近/重叠最大的墙作为门的宿主墙
        walls = [e for e in entities if e.type == "wall"]  # compare: equality
        openings = [
            e for e in entities if e.type in ("door", "window", "fire_door", "exit_door")
        ]  # assign: membership check

        for opening in openings:  # 循环
            best_wall = None  # init: set to None
            best_overlap = 0.0  # init: set to 0
            best_distance = float("inf")  # assign

            ob = opening.bbox  # assign
            ox1, oy1 = ob.get("x", 0), ob.get("y", 0)  # 操作
            ox2 = ox1 + ob.get("width", 0)  # assign
            oy2 = oy1 + ob.get("height", 0)  # assign
            o_cx = (ox1 + ox2) / 2  # assign
            o_cy = (oy1 + oy2) / 2  # assign

            for wall in walls:  # 循环
                wb = wall.bbox  # assign
                wx1, wy1 = wb.get("x", 0), wb.get("y", 0)  # 操作
                wx2 = wx1 + wb.get("width", 0)  # assign
                wy2 = wy1 + wb.get("height", 0)  # assign

                # 计算门中心到墙边的距离
                # 到左/右垂直边的水平距离
                dx_left = abs(o_cx - wx1)  # assign
                dx_right = abs(o_cx - wx2)  # assign
                # 到上/下水平边的垂直距离
                dy_bottom = abs(o_cy - wy1)  # assign
                dy_top = abs(o_cy - wy2)  # assign

                min_dx = min(dx_left, dx_right)  # assign
                min_dy = min(dy_bottom, dy_top)  # assign
                dist_to_edge = min(min_dx, min_dy)  # assign

                # 检查重叠：门必须接触墙的边界（距离<50mm）
                if dist_to_edge > 50.0:  # check: numeric comparison
                    continue  # 继续循环

                # 计算门在墙边上的投影重叠长度
                overlap = 0.0  # init: set to 0

                if min_dx <= min_dy:  # check: numeric comparison
                    # 门接触垂直边（墙的左或右边）
                    # 投影重叠在 y 方向
                    overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))  # assign
                    overlap = overlap_y / max(ob.get("height", 1), 1)  # assign
                else:  # 否则
                    # 门接触水平边（墙的上或下边）
                    overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))  # assign
                    overlap = overlap_x / max(ob.get("width", 1), 1)  # assign

                if overlap > best_overlap or (
                    overlap == best_overlap and dist_to_edge < best_distance
                ):  # check: numeric comparison
                    best_overlap = overlap  # assign
                    best_distance = dist_to_edge  # assign
                    best_wall = wall  # assign

            if best_wall:  # condition: best_wall:
                relations.append(
                    SpatialRelation(  # code
                        source_id=best_wall.id,
                        target_id=opening.id,  # assign
                        rel_type="contains",  # assign
                        confidence=min(0.95, best_overlap),  # assign
                    )
                )  # code
                # 给门注入宿主墙信息
                opening.properties["host_wall_id"] = best_wall.id  # 操作
                opening.properties["host_wall_overlap"] = round(best_overlap, 2)  # 操作

        # ── 3. 走廊-门-房间拓扑（V2：基于边缘距离）──
        # 用 _min_edge_distance 判断门是否连接走廊/房间
        corridors = [e for e in entities if e.type == "corridor"]  # compare: equality
        rooms = [e for e in entities if e.type == "room"]  # compare: equality
        doors = [
            e for e in entities if e.type in ("door", "fire_door", "exit_door")
        ]  # assign: membership check

        for door in doors:  # 循环
            for c in corridors:  # 循环
                dist = self._min_edge_distance(door.bbox, c.bbox)  # assign
                if dist < 200.0:  # 门边缘距走廊 < 200mm
                    relations.append(
                        SpatialRelation(  # code
                            source_id=c.id,
                            target_id=door.id,  # assign
                            rel_type="connects_to",
                            distance=dist,  # assign
                            via="door",  # assign
                        )
                    )  # code
            for r in rooms:  # 循环
                dist = self._min_edge_distance(door.bbox, r.bbox)  # assign
                if dist < 200.0:  # check: numeric comparison
                    relations.append(
                        SpatialRelation(  # code
                            source_id=r.id,
                            target_id=door.id,  # assign
                            rel_type="connects_to",
                            distance=dist,  # assign
                            via="door",  # assign
                        )
                    )  # code

        # ── 4. 包含关系（房间包含设备/柱）──
        contained_types = {"column", "stair", "exit", "fire_door"}  # assign
        containables = [
            e for e in entities if e.type in contained_types
        ]  # assign: membership check
        for room in rooms:  # 循环
            for item in containables:  # 循环
                if self._is_inside(
                    item.bbox, room.bbox
                ):  # condition: self._is_inside(item.bbox, room.bbox):
                    relations.append(
                        SpatialRelation(  # code
                            source_id=room.id,
                            target_id=item.id,  # assign
                            rel_type="contains",
                            confidence=0.9,  # assign
                        )
                    )  # code

        # ── 5. 房间-门间接连接（通过墙传递）──
        # 使用 door.properties["host_wall_id"] 直接定位门所在的墙
        # 然后遍历该墙相邻的 room，建立 room↔door 连接
        # wall 不在 KEY_ENTITY_TYPES 中，避免大图纸 wall×wall adjacency 超时
        # 先构建 wall_id -> set(room_id) 映射：只有 room↔wall 相邻关系中的墙才收录
        wall_rooms: Dict[str, set] = {}  # init: empty dict
        for rel in relations:  # 循环
            if rel.type == "adjacent":  # condition: rel.type == "adjacent":
                sid, tid = rel.source_id, rel.target_id
                if sid in {r.id for r in rooms} and tid in {w.id for w in walls}:  # room→wall
                    wall_rooms.setdefault(tid, set()).add(sid)  # call
                elif tid in {r.id for r in rooms} and sid in {w.id for w in walls}:  # wall→room
                    wall_rooms.setdefault(sid, set()).add(tid)  # call
        # 大图纸 room 数量少但 wall 极多，相邻关系不足时用 bbox 检测补全
        # 只检测 room 与门所在墙的 bbox 距离，不走全量 wall adjacency
        door_wall_map: Dict[str, SemanticEntity] = {}  # init: empty dict
        for door in doors:  # 循环
            host_id = door.properties.get("host_wall_id")  # function call
            if host_id:  # check: truthy
                wall_ent = next((w for w in walls if w.id == host_id), None)  # assign
                if wall_ent:  # check: truthy
                    door_wall_map[host_id] = wall_ent  # call
        # 对每个 room，找所有与门所在墙 bbox 接近的墙
        for room in rooms:  # 循环
            if room.id in wall_rooms:  # 已有相邻墙
                continue  # 跳过已覆盖的 room
            for wid, wall_ent in door_wall_map.items():  # 循环
                if self._min_edge_distance(room.bbox, wall_ent.bbox) < 500.0:  # function call
                    wall_rooms.setdefault(wid, set()).add(room.id)  # call
        # 建立 room↔door connects_to：遍历每个门，找相邻的 room
        seen_conn: set = set()  # init: empty set
        for door in doors:  # 循环
            host_id = door.properties.get("host_wall_id")  # function call
            if not host_id:  # check: negated condition
                continue  # 无宿主墙，跳过
            for room_id in wall_rooms.get(host_id, set()):  # 循环
                pair = (room_id, door.id)  # assign
                if pair in seen_conn:  # check: membership test
                    continue  # 避免重复
                seen_conn.add(pair)  # call
                relations.append(
                    SpatialRelation(  # code
                        source_id=room_id,
                        target_id=door.id,  # assign
                        rel_type="connects_to",
                        distance=0.0,  # assign
                        via="door",  # assign
                    )
                )  # code

        return relations  # return

    def _bind_dimensions(
        self,
        entities: List[
            SemanticEntity
        ],  # method: def _bind_dimensions(self, entities: List[SemanticEntity],
        dimensions: List[Dict],
    ) -> Dict[str, Dict]:  # 操作
        """尺寸标注绑定到实体"""
        bindings = {}  # init: empty dict

        for dim in dimensions:  # 循环
            dim_pos = dim.get("position", {})  # assign
            if not dim_pos:  # check: negated condition
                continue  # 继续循环

            nearest = None  # init: set to None
            nearest_dist = float("inf")  # assign

            for entity in entities:  # 循环
                center = self._bbox_center(entity.bbox)  # assign
                dist = self._point_distance(dim_pos, center)  # assign
                if dist < nearest_dist and dist < 500:  # check: numeric comparison
                    nearest = entity  # assign
                    nearest_dist = dist  # assign

            if nearest:  # condition: nearest:
                if nearest.id not in bindings:  # check: membership test
                    bindings[nearest.id] = {}  # 操作
                attr_name = self._infer_attribute_name(dim, nearest)  # assign
                bindings[nearest.id][attr_name] = dim.get("measurement", 0)  # 操作

        return bindings  # return

    # ── 几何工具函数 ────────────────────────────────────

    @staticmethod
    def _compute_iou(bbox1, bbox2):
        from .geometry import compute_iou

        return compute_iou(bbox1, bbox2)

    @staticmethod
    def _union_bbox(bboxes):
        from .geometry import union_bbox

        return union_bbox(bboxes)

    @staticmethod
    def _min_edge_distance(bbox1, bbox2):
        # P76 修复：零 bbox 退化处理
        # 当 bbox 的 width=0 且 height=0 时（真实图纸中楼梯/门常为点状几何），
        # 边距退化为点间中心距，否则用标准边缘距离
        bw1, bh1 = bbox1.get("width", 0), bbox1.get("height", 0)
        bw2, bh2 = bbox2.get("width", 0), bbox2.get("height", 0)
        degenerate = (bw1 == 0 and bh1 == 0) or (bw2 == 0 and bh2 == 0)
        if degenerate:
            from .geometry import bbox_center, point_distance

            c1 = bbox_center(bbox1)  # 操作
            c2 = bbox_center(bbox2)  # 操作
            return point_distance(c1, c2)  # 返回点间距离
        from .geometry import min_edge_distance

        return min_edge_distance(bbox1, bbox2)

    @staticmethod
    def _is_inside(inner, outer):
        from .geometry import is_inside

        return is_inside(inner, outer)

    @staticmethod
    def _bbox_center(bbox):
        from .geometry import bbox_center

        return bbox_center(bbox)

    @staticmethod
    def _point_distance(p1, p2):
        from .geometry import point_distance

        return point_distance(p1, p2)

    @staticmethod  # code
    def _infer_attribute_name(
        dim: Dict, entity: SemanticEntity
    ) -> str:  # method: def _infer_attribute_name(dim: Dict, entity: SemanticEntity)
        """推断属性名"""
        entity_type = entity.type  # assign

        if entity_type == "wall":  # condition: entity_type == "wall":
            return "width"  # return
        elif entity_type in ("door", "fire_door"):  # 分支
            return "clear_width"  # return
        elif entity_type == "window":  # 分支
            return "width"  # return
        elif entity_type == "stair":  # 分支
            return "step_width"  # return
        elif entity_type == "corridor":  # 分支
            return "clear_width"  # return
        elif entity_type == "fire_zone":  # 分支
            return "area"  # return
        else:  # 否则
            return "measurement"  # return

    # ── 走廊拓扑网络 ────────────────────────────────────

    def build_corridor_topology(self, entities, relations):
        from .evacuation import _build_corridor_topology_impl

        return _build_corridor_topology_impl(self, entities, relations)

    def analyze_evacuation_routes(self, entities, topology=None):
        from .evacuation import _analyze_evacuation_routes_impl

        return _analyze_evacuation_routes_impl(self, entities, topology)

    def verify_evacuation_connectivity(self, entities, relations=None, evacuation_routes=None):
        from .evacuation import _verify_evacuation_connectivity_impl

        return _verify_evacuation_connectivity_impl(self, entities, relations, evacuation_routes)

    def _yolo_enhance(self, dxf_path):
        from .enhancement import _yolo_enhance_impl

        return _yolo_enhance_impl(self, dxf_path)

    def _merge_yolo_results(self, rule_entities, yolo_detections):
        from .enhancement import _merge_yolo_results_impl

        return _merge_yolo_results_impl(self, rule_entities, yolo_detections)
