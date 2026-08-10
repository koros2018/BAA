"""
P70 高频缺口补全第5批 + 最终高频缺口
"""

LAYER_RULES_P70_B5 = {
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
    "GAS_FIREFIGHT": "gas_fire_suppression"
}
