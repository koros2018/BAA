"""
P70 高频缺口补全 第1-4批
"""

LAYER_RULES_P70_FREQ = {
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
}
