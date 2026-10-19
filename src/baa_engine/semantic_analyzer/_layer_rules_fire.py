"""
消防设施图层（真实图纸图层名）
"""

LAYER_RULES_FIRE = {
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
    # 防火分区边界图层（real: 平面布置底图0712 A-FIRE 闭合多边形, xref 嵌套
    # 形态 底图平面图$0$11$0$A-FIRE 亦含子串 A-FIRE）。配合 classify 区域守卫:
    # 仅闭合多边形/HATCH 且 bbox≥25m² 才产分区实体, 分隔线/标注被滤除。
    "A-FIRE": "fire_compartment",
}
