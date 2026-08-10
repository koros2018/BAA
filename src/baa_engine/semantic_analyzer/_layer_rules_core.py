"""
墙/门/窗/楼梯/走廊/防火分区/尺寸/出口/防火门/消防电梯/设备
"""

LAYER_RULES_CORE = {
    "WALL": "wall",
    "墙体": "wall",
    "墙": "wall",  # 字段
    "BEAM": "wall",  # 结构梁图层（real: BEAM, BEAM_SE, beam-line）
    "COLUMN": "wall",  # 柱子（real: column-line, COLUMN-hatch）
    "DOOR": "door",
    "门": "door",  # 字段
    "SB": "door",  # 水消防设备层门标记
    "WINDOW": "window",
    "窗": "window",
    "WIND": "window",  # 字段
    "STAIR": "stair",
    "楼梯": "stair",
    "STAIRS": "stair",  # 字段
    "CORRIDOR": "corridor",
    "走道": "corridor",
    "走廊": "corridor",  # 字段
    "FIRE_ZONE": "fire_zone",
    "防火分区": "fire_zone",  # 字段
    "DIM": "dimension",
    "标注": "dimension",
    "尺寸": "dimension",  # 字段
    "DIMENSION": "dimension",  # 字段
    "DIM_": "dimension",  # real: DIM_ELEV, DIM_SYMB, AXIS_DIM
    "EXIT": "exit",
    "出口": "exit",
    "安全出口": "exit",  # 字段
    "FIRE_DOOR": "fire_door",
    "防火门": "fire_door",  # 字段
    "FIRE_ELEV": "fire_elevator",
    "消防电梯": "fire_elevator",  # 字段
    "电-": "equipment",  # 电气设备图层（real: 电-系统-设备）
    "设备": "equipment",  # 设备
    "GCD": "equipment",  # 供电设备（real）
    "NET": "equipment",  # 网络设备（real）
    "气体": "equipment",  # 气体灭火设备
    "通风": "equipment",  # 通风设备
}
