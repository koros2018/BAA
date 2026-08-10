"""
P74 准确率专项补全（16 张图纸 audit）
"""

LAYER_RULES_P74 = {
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
    "电井": "equipment_room"
}
