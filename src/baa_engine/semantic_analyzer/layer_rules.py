"""Layer classification rules.

Extracted from main.py: LAYER_RULES, SHORT_LAYER_RULES, NON_ROOM_LAYER_KW,
EXIT_LAYER_KW, EXIT_LIKE_LAYER_KW, NON_EXIT_LAYER_KW, KEY_ENTITY_TYPES,
FIRE_LAYERS, FIRE_SUPP_LAYERS, FIRE_PROT_LAYERS, FIRE_PROT_LAYER_MAP,
EVAC_ENTITY_MAP, EVAC_LIKE_LAYER_KW, EVAC_KW, EVAC_LAYER_KW,
EVAC_LAYER_KW_EXTRA, EVAC_LAYER_KW_FLOOR, EVAC_LAYER_KW_CEILING,
EVAC_DIRECTION_KW, EVAC_DIRECTION_LAYER, VENT_LAYER_KW,
FIRE_DOOR_LAYER_KW, FIRE_VALVE_LAYER_KW, LAYER_RULES_V2,
FIRE_EXT_LAYER_MAP, SMOKE_DET_LAYER_MAP, MANUAL_CALL_LAYER_MAP,
VESDA_LAYER_MAP.
"""


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
    "出口指示灯": "exit_sign",  # 出口指示灯
    "安全出口标志": "exit_sign",  # 安全出口标志
    "疏散指示灯": "exit_sign",  # 疏散指示灯
    "EMERGENCY_EXIT_SIGN": "exit_sign",  # 应急出口标志
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
    "应急照明线路": "evacuation_lighting",  # 应急照明线路
    "应急照明灯": "evacuation_lighting",  # 应急照明灯头
    "应急灯": "evacuation_lighting",  # 应急灯
    "EVAC_LIGHT": "evacuation_lighting",  # 疏散照明
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
    "上线井": "shaft",  # 管线竖井（红土深汕 DXF）
    "通风井": "shaft",  # 通风竖井
    "井道": "shaft",  # 管道井道
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
    # P82: "L" 已移至 SHORT_LAYER_RULES 做全词匹配，防止 TEL_LEAD 等引线层误匹配为 lobby
    "OUTDOOR_STAIR": "outdoor_stair",
    "STAIRS": "stairs",
    "FB": "pump_controller",
    "PLAN": "room",
    "HOLE": "shaft",
}  # code

# 短关键字（单字母/2字母）使用全词匹配
SHORT_LAYER_RULES = {  # assign
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
}  # code


