"""
P79 真实图纸补全 + P47 无障碍 + P70 Final
"""

LAYER_RULES_P79 = {
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
}
