"""Semantic classifier — layer + geometry + entity-level.
"""
from typing import List
from .layer_rules import LAYER_RULES, SHORT_LAYER_RULES
from .models import SemanticEntity
from .merge import _merge_overlapping
from .meta import _parse_meta_entities
from .room import _is_near_closed
from ..drawing_parser import RawPrimitive

def _classify_entities(
    self, primitives: List[RawPrimitive]
) -> List[
    SemanticEntity
]:
    """图元分类归并"""
    # 优先解析 META 图层（合成图纸结构化数据）
    meta_entities = _parse_meta_entities(self, primitives)
    if meta_entities:
        return meta_entities

    entities = []

    for prim in primitives:
        # P101: PDF 源数据预过滤——来自 pdf_parser 的线条全在 "lines" 层，
        # 大量短装饰线（<300mm）和短斜线（标注线/文字笔画）混入。
        # 这些线段对建筑审查无意义，直接跳过可消除 60% 噪声。
        # 长斜线（>=2000mm）保留——可能是真实斜墙。
        if prim.layer == "lines":
            bbox = prim.bbox
            length = max(bbox.get("width", 0), bbox.get("height", 0))
            if length < 300:
                continue
            if length < 2000:
                angle = abs(prim.properties.get("angle", 0) or 0) % 180
                if 5 < angle < 85 or 95 < angle < 175:
                    continue

        # 图层规则匹配
        entity_type = _classify_by_layer(self, prim.layer)
        # P80+P82 修复：图层规则返回"other"时，让几何分类兜底为wall，
        # 否则闭合多边形（如 DOTE 层实线围合区域）被误判为非建筑实体，
        # 导致 _merge_line_chains_to_rooms 无法找到 room，疏散分析返回空。
        # 但仅接受 "wall"：PUB_HATCH 等填充图案层的 LINE（~550mm）会被
        # 几何误判为 door（宽度线），产生大量假门（2210个）导致 EVAC 假阳性。
        if (
            entity_type == "unknown" or entity_type == "other"
        ):  # condition: entity_type == "unknown" or entity_type == "other"
            geo_type = _classify_by_geometry(self, prim)
            if (
                geo_type != "unknown" and geo_type != "other"
            ):  # P80: 几何兜底接受所有有效类型（wall/door/window等），
                # PUB_HATCH 等填充层已由 LAYER_RULES 正确返回 "other" 被过滤，
                # 真实 DOOR_FIRE/SLAB/窗图层返回 "unknown" 走几何兜底保留 door/window
                entity_type = geo_type

        if entity_type == "unknown":  # condition: entity_type == "unknown":
            continue  # 继续循环

        self._entity_counter += 1
        # 过滤 NaN properties
        cleaned_props = {}
        for pk, pv in prim.properties.items():  # 循环
            if isinstance(pv, float):  # condition: isinstance(pv, float):
                import math  # stdlib: math functions

                if not math.isnan(pv):  # check: negated condition
                    cleaned_props[pk] = pv
            else:  # 否则
                cleaned_props[pk] = pv
        entity = SemanticEntity(
            entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",
            entity_type=entity_type,
            bbox=prim.bbox,
            layer=prim.layer,
            confidence=0.9 if entity_type != "unknown" else 0.5,  # compare: inequality
            properties=cleaned_props,
        )  # code
        entities.append(entity)  # append: add to list

    # 归并同类重叠图元
    entities = _merge_overlapping(self, entities)

    # 过滤过小的走廊实体（LINE 类型容易被误识别为走廊）
    # 走廊宽度 < 500mm 且 bbox 短边 < 500mm 的实体可能是微小图元误标
    filtered = []
    for e in entities:  # 循环
        if e.type == "corridor":  # check: OR condition
            bb = e.bbox
            bw = bb.get("width", 0)
            bh = bb.get("height", 0)
            short_edge = min(bw, bh) if bw > 0 and bh > 0 else max(bw, bh)
            if short_edge < 500:  # 短边 < 500mm 不可能是走廊
                continue  # 继续循环
        filtered.append(e)  # append: add to list
    entities = filtered

    return entities




def _classify_by_layer(
    self, layer: str
) -> str:
    """图层规则归类

    长关键字（≥3字符）：子串匹配
    短关键字（1-2字符）：全词匹配（前后是_或边界），防止误匹配
    """
    if not layer:  # check: negated condition
        return "unknown"
    layer_upper = layer.upper()

    # 长关键字（≥3字符）：子串匹配
    for keyword, entity_type in LAYER_RULES.items():  # 循环
        if keyword in layer_upper:  # check: membership test
            return entity_type

    # 短关键字（1-2字符）：全词匹配
    for keyword, entity_type in SHORT_LAYER_RULES.items():  # 循环
        if keyword in layer_upper:  # check: membership test
            # 检查全词边界
            idx = layer_upper.find(keyword)
            while idx >= 0:  # 循环
                pre_ok = idx == 0 or layer_upper[idx - 1] == "_"  # compare: equality
                post_ok = (
                    idx + len(keyword) >= len(layer_upper)
                    or layer_upper[idx + len(keyword)] == "_"
                )  # compare: equality
                if pre_ok and post_ok:  # check: AND condition
                    return entity_type
                idx = layer_upper.find(keyword, idx + 1)

    return "unknown"




def _classify_by_geometry(
    self, prim: RawPrimitive
) -> str:
    """几何特征兜底归类（V2深度升级版）

    新增规则：
    - 短 LINE 且靠近 DIMENSION 标注的 defpoint → door
    - 小面积闭合多边形（门打开轨迹）→ door
    - 靠近门的 ARC → door
    - 狭长闭合多边形 → corridor
    - 大尺寸 CIRCLE（>3000mm）→ stair
    """
    dxf_type = prim.dxf_type
    bbox = prim.bbox
    bw = bbox.get("width", 0)
    bh = bbox.get("height", 0)
    area = bw * bh
    props = prim.properties
    length = props.get("length", 0) or max(bw, bh)
    short_edge = min(bw, bh) if bw > 0 and bh > 0 else length

    if dxf_type == "LINE":  # condition: dxf_type == "LINE":
        if length >= 2000:  # P84-E: 东莞通中有 54 条恰好 2000.0mm 的 hv LINE
            # 是墙线，不是门，>= 确保边界情况归为 wall
            return "wall"
        # P84-E fix: LINE 是 1D 对象，hv 线的 bbox short_edge 错误回退到 length
        # 用端点坐标计算真实短边 = min(|dx|, |dy|)
        sp = props.get("start_point", {})
        ep = props.get("end_point", {})
        if sp and ep:
            real_se = min(
                abs(ep.get("x", 0) - sp.get("x", 0)),
                abs(ep.get("y", 0) - sp.get("y", 0)),
            )  # 赋值
        else:
            real_se = short_edge
        # P84-E: 建筑门宽 ≥700mm 是基本约束，50-700mm 段的密集水平线
        # 在东莞通中是填充图案（y 聚类 21-27 条/行），不是真实门
        # 中等长度 LINE（700~2000mm）且近乎 hv → door
        # P84 fix: 门宽 700mm 是下限边界，700mm 门 + 1mm 浮点容差
        if 700 <= length + 1 < 2000 and real_se < 50:  # check: numeric comparison
            return "door"
        # 短 LINE（<700mm）：填充图案/标注线/引线 → other
        return "other"

    if dxf_type in ("LWPOLYLINE", "POLYLINE"):  # check: membership test
        pts_count = props.get("point_count", 0)
        if pts_count == 2:  # condition: pts_count == 2:
            # 2 点 LWPOLYLINE：视为 LINE 等价
            if length > 2000:  # check: numeric comparison
                return "wall"
            # P84-E fix: 同样用端点坐标算真实短边
            pts = props.get("points", [])
            if len(pts) >= 2:
                real_se = min(
                    abs(pts[1][0] - pts[0][0]),
                    abs(pts[1][1] - pts[0][1]),
                )  # 赋值
            else:
                real_se = short_edge
            # P84-E: 建筑门宽 ≥700mm，短 LINE 归为 other
            # P84 fix: 门宽 700mm 是下限边界，同样用 +1mm 浮点容差
            if 700 <= length + 1 < 2000 and real_se < 50:  # check: numeric comparison
                return "door"
            return "other"

        # 闭合多边形判断（含缺口补全）
        is_closed = props.get("area", 0) > 0 or (pts_count >= 3)
        if not is_closed and pts_count >= 3:  # check: numeric comparison
            is_closed = _is_near_closed(self, prim, gap_threshold_mm=500.0)
        if is_closed:  # condition: is_closed:
            aspect_ratio = max(bw, bh) / max(short_edge, 1)
            # P77：area=0 的闭合多边形（stair 2 点 LWPOLYLINE 等退化几何）
            # 不是真正的房间，跳过 room 判定
            if area == 0 and pts_count == 2:  # check: numeric comparison
                return "other"
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
            ]
            if any(
                kw in prim.layer.upper() for kw in non_room_layers
            ):  # check: membership test
                if aspect_ratio > 3:  # check: numeric comparison
                    return "other"
                return "wall"
            # 默认图层（0/00）上的闭合多边形：电气图中大量线槽/表格轮廓在此
            # P84-E fix: 原规则面积<10m² OR aspect>3 即拒绝，过于激进——
            # 东莞通中 45.5% 的真实小房间（1~10m²）被误杀。
            # 改为：面积<5m² AND aspect>5 才拒绝（两者必须同时满足）
            if prim.layer.strip() in ("0", "00", ""):  # check: membership test
                if area < 5000000 and aspect_ratio > 5:  # < 5m² 且极狭长
                    return "other"
            # room 最小面积 1m²（1,000,000mm²），过滤小框/文字标注
            # room 最大面积 500m²（500,000,000mm²），过滤图纸边界框/标题栏框
            if area > 500000000:  # > 500m² → 图纸边界/标题栏，不是房间
                return "other"
            if area > 1000000:  # > 1m²
                if aspect_ratio > 5:  # check: numeric comparison
                    # 狭长 → 走廊
                    if length > 3000:  # check: numeric comparison
                        return "wall"
                    return "corridor"
                return "room"
            elif area > 50000:  # 大面积但 < 1m²
                if aspect_ratio > 5:  # check: numeric comparison
                    if length > 3000:  # check: numeric comparison
                        return "wall"
                    return "corridor"
                return "wall"
            elif area > 50000:  # 条件分支
                # 中等面积（0.05~1m²）：可能是小房间或设备间
                if aspect_ratio > 4:  # check: numeric comparison
                    return "corridor"
                return "room"
            elif area > 5000:  # 条件分支
                # 小面积（0.005~0.05m²）：通常是文字框/图例框/标注框，不是房间
                return "other"
            else:  # 否则
                # 小面积闭合多边形（500~5000mm²）→ door 或 window
                if aspect_ratio > 3:  # check: numeric comparison
                    # 狭长小面积 → 门的开合轨迹
                    return "door"
                elif aspect_ratio < 1.5:  # 条件分支
                    # 接近正方形的小面积 → column
                    return "column"
                return "door"
        return "corridor"

    # ARC：门弧、窗或弧形房间
    if dxf_type == "ARC":  # condition: dxf_type == "ARC":
        radius = props.get("radius", 0)
        # 大半径 ARC（>3000mm）且弧线角度大 → 弧形房间轮廓
        if radius > 3000:  # check: numeric comparison
            angle_span = (
                abs(props.get("start_angle", 0) - props.get("end_angle", 0)) or 0
            )
            # 弧线跨度 > 90° 视为房间轮廓
            if angle_span > 90:  # check: numeric comparison
                return "room"
        if 100 < radius < 2000:  # check: numeric comparison
            return "door"
        return "window"

    if dxf_type == "CIRCLE":  # condition: dxf_type == "CIRCLE":
        radius = props.get("radius", 0)
        if radius > 3000:  # check: numeric comparison
            return "stair"
        elif radius > 1000:  # 条件分支
            return "stair"
        elif radius > 300:  # 条件分支
            return "column"
        # P34: 小半径 CIRCLE 可能是消防设备
        if 50 <= radius <= 300:  # check: numeric comparison
            # 结合图层判断
            layer = prim.layer.upper()
            if any(
                kw in layer
                for kw in ["消防", "FIRE", "FAS", "报警", "ALARM", "喷淋", "SPRINKLER"]
            ):  # check: membership test
                return "sprinkler"
            if any(
                kw in layer for kw in ["设备", "EQUIP", "电-", "电气", "ELEC"]
            ):  # check: membership test
                return "equipment"
            if any(
                kw in layer for kw in ["照明", "LIGHT", "应急", "EVAC"]
            ):  # check: membership test
                return "evacuation_lighting"
            return "column"
        return "column"

    # P34: SOLID/HATCH 实体可能是消防设备填充
    if dxf_type == "SOLID":  # condition: dxf_type == "SOLID":
        layer = prim.layer.upper()
        if any(
            kw in layer for kw in ["消防", "FIRE", "喷淋", "SPRINKLER", "消火栓", "HYDRANT"]
        ):  # check: membership test
            return "sprinkler"
        if any(
            kw in layer for kw in ["设备", "EQUIP", "电-", "电气", "ELEC"]
        ):  # check: membership test
            return "equipment"
        return "other"

    if dxf_type == "HATCH":  # condition: dxf_type == "HATCH":
        layer = prim.layer.upper()
        if any(
            kw in layer for kw in ["消防", "FIRE", "喷淋", "SPRINKLER"]
        ):  # check: membership test
            return "sprinkler"
        return "other"

    if dxf_type == "TEXT":  # condition: dxf_type == "TEXT":
        text = props.get("text", "")
        if not text:  # check: negated condition
            return "text"
        text_upper = text.upper()
        if "出口" in text or "EXIT" in text_upper:  # check: membership test
            return "exit"
        if "楼梯" in text or "STAIR" in text_upper:  # check: membership test
            return "stair"
        # "防火" 关键词需配合 "门" 或 "窗" 才能归类，避免文本描述被误标
        if "防火门" in text or (
            "FIRE" in text_upper and "DOOR" in text_upper
        ):  # check: membership test
            return "fire_door"
        if "防火窗" in text or (
            "FIRE" in text_upper and "WINDOW" in text_upper
        ):  # check: membership test
            return "fire_window"
        # ── 消防设施/系统关键词（用于真实图纸 TEXT 辅助识别） ──
        if "消火栓" in text or "HYDRANT" in text_upper:  # check: membership test
            return "fire_hydrant"
        if (
            "喷淋" in text or "洒水" in text or "SPRINKLER" in text_upper
        ):  # check: membership test
            return "sprinkler"
        if "灭火器" in text or "灭火" in text:  # check: membership test
            return "fire_extinguisher"
        if (
            "烟感" in text or "烟雾探测" in text or "探测器" in text or "SMOKE" in text_upper
        ):  # check: membership test
            return "smoke_detector"
        if "报警" in text or "ALARM" in text_upper:  # check: membership test
            return "fire_alarm"
        if "消防水箱" in text or "水箱" in text:  # check: membership test
            return "water_tank"
        if "消防水池" in text or "水池" in text:  # check: membership test
            return "water_reservoir"
        if (
            "广播" in text or "音箱" in text or "SPEAKER" in text_upper
        ):  # check: membership test
            return "emergency_broadcast"
        if "应急照明" in text or "EVAC" in text_upper:  # check: membership test
            return "evacuation_lighting"
        if "卷帘" in text or "CURTAIN" in text_upper:  # check: membership test
            return "fire_curtain"
        if "消防电梯" in text or "FIRE_ELEV" in text_upper:  # check: membership test
            return "fire_elevator"
        if "声光" in text:  # check: membership test
            return "fire_alarm"
        # ── P70 消防泵/水泵接合器/启泵按钮 TEXT 识别 ──
        if (
            "消防泵" in text
            or "喷淋泵" in text
            or "稳压泵" in text
            or "消火栓泵" in text
            or "PUMP" in text_upper
        ):
            return "fire_pump"
        if "水泵接合器" in text or "接合器" in text or "SIAMESE" in text_upper:
            return "siamese_connection"
        if "启泵按钮" in text or "消火栓按钮" in text or "CALL_POINT" in text_upper:
            return "hydrant_call_button"
        if "泵控制柜" in text or "启泵柜" in text or "PUMP_CTRL" in text_upper:
            return "pump_controller"
        # ── P70 高频缺口 TEXT 识别 ──
        if "探测器" in text or "detector" in text_upper or "DET" in text_upper:
            return "detector"
        if "楼层" in text or "FLOOR" in text_upper or "层" in text:
            return "floor"
        if "泵房" in text or "PUMP_ROOM" in text_upper:
            return "pump_room"
        if "防火墙" in text or "FIRE_WALL" in text_upper:
            return "fire_wall"
        if "防火卷帘" in text or "FIRE_SHUTTER" in text_upper:
            return "fire_shutter"
        if "控制室" in text or "FIRE_CONTROL" in text_upper or "消防控制" in text:
            return "control_room"
        if "救援窗" in text or "RESCUE_WIN" in text_upper or "救援口" in text:
            return "rescue_window"
        if "扬声器" in text or "SPEAKER" in text_upper or "喇叭" in text:
            return "speaker"
        if "道路" in text or "ROAD" in text_upper or "消防车道" in text:
            return "road"
        if "车道" in text or "DRIVE" in text_upper:
            return "driveway"
        if "电源" in text or "POWER_SUPPLY" in text_upper:
            return "power_supply"
        # ── P70 高频缺口 TEXT 识别（第2批） ──
        if "楼梯间" in text or "STAIRCASE" in text_upper or "STAIR_CASE" in text_upper:
            return "staircase"
        if "出口门" in text or "EXIT_DOOR" in text_upper or "安全出口门" in text:
            return "exit_door"
        if (
            "泵" in text
            and "消防泵" not in text
            and "喷淋泵" not in text
            and "消火栓泵" not in text
        ):
            return "pump"
        if "避难层" in text or "REFUGE_FLOOR" in text_upper:
            return "refuge_floor"
        if "前室" in text or "ANTEROOM" in text_upper:
            return "antechamber"
        if "消防车道" in text and "road" not in text_lower:
            return "fire_lane"
        if "消防水箱" in text or "FIRE_WATER_TANK" in text_upper:
            return "fire_water_tank"
        if "室内消火栓" in text or "INDOOR_HYDRANT" in text_upper:
            return "indoor_hydrant"
        if "避难区" in text or "REFUGE_AREA" in text_upper:
            return "refuge_area"
        if "避难间" in text or "REFUGE_ROOM" in text_upper:
            return "refuge_room"
        if "消防广播" in text or "FIRE_BROADCAST" in text_upper:
            return "fire_broadcast"
        if "楼梯间前室" in text or "STAIRCASE_LOBBY" in text_upper:
            return "staircase_lobby"
        if "设备间" in text or "EQ_ROOM" in text_upper:
            return "equipment_room"
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
        return "text"

    # INSERT 块：从块名推断实体类型（完整映射表）
    if dxf_type == "INSERT":  # condition: dxf_type == "INSERT":
        block_name = props.get("block_name", "").upper()
        # ── 防火门/防火窗 ──
        if "FIRE_DOOR" in block_name or "防火门" in block_name:  # check: membership test
            return "fire_door"
        if "FIRE_WINDOW" in block_name or "防火窗" in block_name:  # check: membership test
            return "fire_window"
        # ── 建筑构件 ──
        if "DOOR" in block_name or "门" in block_name:  # check: membership test
            return "door"
        if "WINDOW" in block_name or "窗" in block_name:  # check: membership test
            return "window"
        if "STAIR" in block_name or "ST" in block_name:  # check: membership test
            return "stair"
        if "COLUMN" in block_name or "柱" in block_name:  # check: membership test
            return "column"
        # ── 出口/疏散指示 ──
        if "EXIT" in block_name or "出口" in block_name:  # check: membership test
            return "exit"
        if (
            "EXIT_SIGN" in block_name or "SIGN" in block_name or "疏散指示" in block_name
        ):  # check: membership test
            return "exit_sign"
        # ── 消防设施 ──
        if "HYDRANT" in block_name or "消火栓" in block_name:  # check: membership test
            return "fire_hydrant"
        if (
            "SPRINKLER" in block_name or "喷淋" in block_name or "洒水" in block_name
        ):  # check: membership test
            return "sprinkler"
        if (
            "FIRE_EXT" in block_name or "灭火器" in block_name or "灭火" in block_name
        ):  # check: membership test
            return "fire_extinguisher"
        if "SMOKE_DETECTOR" in block_name or "烟感" in block_name:  # check: membership test
            return "smoke_detector"
        if "FIRE_ALARM" in block_name or "报警" in block_name:  # check: membership test
            return "fire_alarm"
        if "WATER_TANK" in block_name or "水箱" in block_name:  # check: membership test
            return "water_tank"
        if (
            "WATER_RESERVOIR" in block_name or "消防水池" in block_name or "水池" in block_name
        ):  # check: membership test
            return "water_reservoir"
        if "FIRE_ELEV" in block_name or "消防电梯" in block_name:  # check: membership test
            return "fire_elevator"
        if (
            "SPEAKER" in block_name or "广播" in block_name or "应急广播" in block_name
        ):  # check: membership test
            return "emergency_broadcast"
        if "EVAC_LIGHT" in block_name or "应急照明" in block_name:  # check: membership test
            return "evacuation_lighting"
        if "CURTAIN" in block_name or "卷帘" in block_name:  # check: membership test
            return "fire_curtain"
        # ── 电气设备（新增） ──
        if (
            "DISTRIBUTION_BOX" in block_name or "配电箱" in block_name or "配电" in block_name
        ):  # check: membership test
            return "distribution_box"
        if (
            "EMERGENCY_LIGHT" in block_name
            or "应急照明" in block_name
            or "应急灯" in block_name
        ):  # check: membership test
            return "emergency_lighting"
        if (
            "SMOKE_DETECTOR" in block_name or "烟感" in block_name or "烟探测器" in block_name
        ):  # check: membership test
            return "smoke_detector"
        if (
            "HEAT_DETECTOR" in block_name or "温感" in block_name or "温探测器" in block_name
        ):  # check: membership test
            return "heat_detector"
        if (
            "ALARM_BUTTON" in block_name or "报警按钮" in block_name or "手报" in block_name
        ):  # check: membership test
            return "alarm_button"
        if (
            "GAS_SUPPRESSION" in block_name or "气体灭火" in block_name or "气灭" in block_name
        ):  # check: membership test
            return "gas_suppression"
        if (
            "BELL" in block_name or "警铃" in block_name or "声光" in block_name
        ):  # check: membership test
            return "fire_bell"
        # ── P70 泵控制柜（必须在通用 PUMP 之前，避免误匹配） ──
        if (
            "PUMP_CONTROLLER" in block_name
            or "PUMP_CTRL" in block_name
            or "PUMPCTRL" in block_name
            or "泵控" in block_name
            or "启泵柜" in block_name
            or "水泵控制柜" in block_name
        ):
            return "pump_controller"
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
            return "fire_pump"
        if (
            "SIAMESE" in block_name
            or "FIRE_DEPT_CONN" in block_name
            or "SIAMESE_CONN" in block_name
            or "水泵接合器" in block_name
            or "接合器" in block_name
        ):  # check: membership test
            return "siamese_connection"
        if (
            "CALL_POINT" in block_name or "消火栓按钮" in block_name or "栓" in block_name
        ):  # check: membership test
            return "hydrant_call_button"
        if (
            "VESDA" in block_name or "极早期" in block_name or "吸气式" in block_name
        ):  # check: membership test
            return "vesda_detector"
        if (
            "EMERGENCY_POWER" in block_name or "应急电源" in block_name or "EPS" in block_name
        ):  # check: membership test
            return "emergency_power"
        # ── 其他楼层/空间 ──
        if (
            "ROOM" in block_name or "房间" in block_name or "室" in block_name
        ):  # check: membership test
            return "room"
        if (
            "CORRIDOR" in block_name or "走廊" in block_name or "走道" in block_name
        ):  # check: membership test
            return "corridor"
        if (
            "SHAFT" in block_name or "井道" in block_name or "竖井" in block_name
        ):  # check: membership test
            return "shaft"
        if "ELEVATOR" in block_name or "电梯" in block_name:  # check: membership test
            return "elevator"
        if "LOBBY" in block_name or "前室" in block_name:  # check: membership test
            return "lobby"
        if "FIRE_ZONE" in block_name or "防火分区" in block_name:  # check: membership test
            return "fire_zone"
        # ── 未知块名 → 回退到 wall ──
        return "wall"

    return "unknown"
