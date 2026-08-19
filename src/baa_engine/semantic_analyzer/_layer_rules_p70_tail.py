"""
P70 尾批：2-ref 类型
"""

LAYER_RULES_P70_TAIL = {
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
}
