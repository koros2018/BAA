"""
BAA 语义识别引擎 - 图元分类 + 空间关系构建（规则版）
"""
import os
from typing import List, Dict, Any, Optional, Tuple
from .drawing_parser import RawPrimitive  # 导入
import logging  # 导入

logger = logging.getLogger(__name__)


# ── 图层规则表 ────────────────────────────────────────────

# 短关键字（单字母/2字母）使用全词匹配（前后是_或边界），防止误匹配
# 例如 "D" 不匹配 "DIM"、"DIMENSION"、"DWG"、"DOOR"
LAYER_RULES = {
    # ── 墙 ──
    "WALL": "wall", "墙体": "wall", "墙": "wall",  # 字段
    "BEAM": "wall",  # 结构梁图层（real: BEAM, BEAM_SE, beam-line）
    "COLUMN": "wall",  # 柱子（real: column-line, COLUMN-hatch）
    # ── 门 ──
    "DOOR": "door", "门": "door",  # 字段
    "SB": "door",  # 水消防设备层门标记
    # ── 窗 ──
    "WINDOW": "window", "窗": "window", "WIND": "window",  # 字段
    # ── 楼梯 ──
    "STAIR": "stair", "楼梯": "stair", "STAIRS": "stair",  # 字段
    # ── 走廊/走道 ──
    "CORRIDOR": "corridor", "走道": "corridor", "走廊": "corridor",  # 字段
    # ── 防火分区 ──
    "FIRE_ZONE": "fire_zone", "防火分区": "fire_zone",  # 字段
    # ── 尺寸标注 ──
    "DIM": "dimension", "标注": "dimension", "尺寸": "dimension",  # 字段
    "DIMENSION": "dimension",  # 字段
    "DIM_": "dimension",  # real: DIM_ELEV, DIM_SYMB, AXIS_DIM
    # ── 出口 ──
    "EXIT": "exit", "出口": "exit", "安全出口": "exit",  # 字段
    # ── 防火门 ──
    "FIRE_DOOR": "fire_door", "防火门": "fire_door",  # 字段
    # ── 消防电梯 ──
    "FIRE_ELEV": "fire_elevator", "消防电梯": "fire_elevator",  # 字段
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
    "钢夹层": "other",  # 钢结构夹层
}

# 短关键字（单字母/2字母）使用全词匹配
SHORT_LAYER_RULES = {
    "W": "wall",  # 字段
    "D": "door",  # 字段
    "M": "door",  # 字段
    "C": "window",  # 字段
    "ST": "stair",  # 字段
    "FZ": "fire_zone",  # 字段
    "FD": "fire_door",  # 字段
    "FE": "fire_elevator",  # 字段
    "T": "equipment",  # 通信设备（real: T=通信图层，需全词匹配）
}


# ── 语义实体 ──────────────────────────────────────────────

class SemanticEntity:
    """语义化图元"""
    def __init__(self, entity_id: str, entity_type: str,
                 bbox: Dict[str, float], layer: str = "",  # 操作
                 subtype: str = "", confidence: float = 1.0,
                 properties: Dict[str, Any] = None):
        self.id = entity_id
        self.type = entity_type
        self.bbox = bbox
        self.layer = layer
        self.subtype = subtype
        self.confidence = confidence
        self.properties = properties or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,  # 字段
            "type": self.type,  # 字段
            "subtype": self.subtype,  # 字段
            "bbox": self.bbox,  # 字段
            "layer": self.layer,  # 字段
            "confidence": self.confidence,  # 字段
            "properties": self.properties,  # 字段
        }


class SpatialRelation:
    """空间关系"""
    def __init__(self, source_id: str, target_id: str,
                 rel_type: str, distance: float = 0,  # 操作
                 via: str = "", confidence: float = 1.0):
        self.source_id = source_id
        self.target_id = target_id
        self.type = rel_type      # adjacent / contains / connects_to
        self.distance = distance
        self.via = via
        self.confidence = confidence


# ── 语义分析引擎 ──────────────────────────────────────────

class SemanticAnalyzer:
    """语义识别引擎（规则版，不做ML）"""

    ADJACENT_THRESHOLD = 50.0  # 相邻距离阈值(mm)

    def __init__(self):
        self._entity_counter = 0
        self._analyze_cache: Dict[str, Dict[str, Any]] = {}  # hash -> result
        self._cache_max = 50

    def analyze(self, primitives: List[RawPrimitive],
                dimensions: List[Dict] = None,  # 操作
                max_entities: int = 10000,  # 性能优化后默认提升到 10000
                building_type: str = "civil",
                dxf_path: Optional[str] = None) -> Dict[str, Any]:
        """
        执行语义分析

        参数:
            primitives: 原始图元列表
            dimensions: 尺寸标注列表
            max_entities: 最大处理实体数（超过则采样，防OOM）
            dxf_path: DXF 文件路径（可选），提供后启用 YOLO 检测增强

        输出: 结构化语义数据（entities + relations + attributes）
        """
        self._entity_counter = 0

        # ── 缓存检查：相同 primitives hash 秒级返回 ──────
        try:
            import hashlib
            prim_hash = hashlib.md5(str(id(primitives))).hexdigest()[:16]
            # 使用前100个图元的type+bbox近似指纹
            fingerprint_parts = []
            for p in primitives[:100]:
                fingerprint_parts.append(f"{p.dxf_type}:{p.bbox}")
            fingerprint = hashlib.sha256("".join(fingerprint_parts).encode()).hexdigest()[:32]
            cached = self._analyze_cache.get(fingerprint)
            if cached is not None:
                return cached
        except Exception:
            fingerprint = None

        # 采样限制，防止全量关系构建OOM
        if len(primitives) > max_entities:
            import random
            random.seed(42)
            primitives = random.sample(primitives, max_entities)

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)

        # Step 1.1: YOLO 检测增强（可选，通过 dxf_path 触发）
        if dxf_path:
            try:  # 尝试
                yolo_entities = self._yolo_enhance(dxf_path)
                if yolo_entities:
                    entities = self._merge_yolo_results(entities, yolo_entities)
                    logger.info(f"YOLO 增强: 新增 {len(yolo_entities)} 个实体, 合并后共 {len(entities)} 个")
            except Exception as e:  # 捕获异常
                logger.warning(f"YOLO 增强失败: {e}")

        # Step 1.5: 走廊宽度推断（平行线聚类 + bbox 短边）
        entities = self._infer_corridor_widths(entities, primitives)

        # Step 1.6: door/fire_door 属性增强（宽度兜底 + 防火等级推断）
        for ent in entities:  # 循环
            if ent.type in ("door", "fire_door", "exit_door"):
                # 宽度兜底：bbox长边优先推断（门扇的宽度是长边，短边是门扇厚度）
                if ent.properties.get("width", 0) < 0.3 and ent.properties.get("clear_width", 0) < 0.3:
                    bbox = ent.bbox
                    bw = bbox.get("width", 0)
                    bh = bbox.get("height", 0)
                    if bw > 0 and bh > 0:
                        # 优先用长边推断门的宽度（短边是门扇厚度）
                        long_edge = max(bw, bh)
                        short_edge = min(bw, bh)
                        # 门宽度的常见模数值（mm）：700/800/900/1000/1200/1500
                        COMMON_DOOR_WIDTHS = [700, 800, 900, 1000, 1200, 1500]
                        # 如果长边是短边的 3 倍以上，说明长边是门宽、短边是厚度
                        if short_edge > 0 and long_edge / short_edge >= 3.0:
                            w_mm = long_edge
                        else:  # 否则
                            w_mm = long_edge
                        # 匹配最近的模数
                        best_match = min(COMMON_DOOR_WIDTHS, key=lambda x: abs(x - w_mm))
                        if abs(w_mm - best_match) / max(best_match, 1) < 0.3:  # 偏差 < 30%，取模数
                            w_mm = best_match
                        w_m = w_mm * 0.001
                        if 0.3 < w_m < 3.0:
                            ent.properties["width"] = w_m  # 操作
                            ent.properties["clear_width"] = w_m  # 操作
                # 防火等级推断：从图层名和实体名推断
                if ent.type == "fire_door":
                    existing_rating = ent.properties.get("fire_rating", ent.properties.get("rating", 0))
                    if existing_rating < 0.5:
                        # 图层名包含关键字推断
                        # 注意：META 图层可能含有 A/B/C，要用完整单词匹配避免误触
                        layer_upper = (ent.layer or "").upper()
                        words = layer_upper.replace("-", " ").replace("_", " ").split()
                        if "甲" in layer_upper or "A" in words:
                            ent.properties["fire_rating"] = 3.0  # 甲级=3.0
                        elif "乙" in layer_upper or "B" in words:  # 分支
                            ent.properties["fire_rating"] = 2.0  # 乙级=2.0
                        elif "丙" in layer_upper or "C" in words:  # 分支
                            ent.properties["fire_rating"] = 1.0  # 丙级=1.0
                        # 不设默认值——无法推断时留空，让原子函数处理

        # Step 2: 空间关系构建（V2拓扑关系）
        relations = self._build_relations(entities)

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])

        # Step 4: 走廊拓扑网络（V2新增）
        corridor_topology = self.build_corridor_topology(entities, relations)

        # Step 5: 疏散路径分析（V2新增）
        evacuation_routes = self.analyze_evacuation_routes(entities, relations) or []

        # Step 5.5: 疏散路径结果注入到实体属性（EVAC原子函数用）
        route_by_room = {}
        for route in evacuation_routes:  # 循环
            route_by_room[route["room_id"]] = route  # 操作
        dead_end_ids = set(d["id"] for d in corridor_topology.get("dead_ends", []))
        for ent in entities:  # 循环
            if ent.id in dead_end_ids:
                ent.properties["is_dead_end"] = True  # 操作
            if ent.id in route_by_room:
                r = route_by_room[ent.id]
                ent.properties["has_evacuation_route"] = r.get("has_route", False)  # 操作
                if r.get("path_length") is not None:
                    ent.properties["evacuation_path_length"] = r["path_length"]  # 操作
                ent.properties["evacuation_too_far"] = r.get("exceeds_max_distance", False)  # 操作
            # 对未找到路径的实体：如果疏散路径分析有结果但房间不在其中，标记为无路径
            # 如果分析结果为空（无出口/无拓扑），则不标记——让 EVAC 原子函数跳过判定
            elif ent.type in ("room", "corridor"):  # 分支
                if "has_evacuation_route" not in ent.properties and evacuation_routes:
                    ent.properties["has_evacuation_route"] = False  # 操作
                    ent.properties["evacuation_too_far"] = True  # 操作

        result = {
            "entities": [e.to_dict() for e in entities],  # 字段
            "relations": [r.__dict__ if hasattr(r, '__dict__') else r for r in relations],  # 字段
            "attributes": attributes,  # 字段
            "building_type": building_type,  # 字段
            "corridor_topology": corridor_topology,  # 字段
            "evacuation_routes": evacuation_routes,  # 字段
        }

        # ── 写入缓存 ──────────────────────────────────────
        if fingerprint and result:
            if len(self._analyze_cache) >= self._cache_max:
                old_key = next(iter(self._analyze_cache))
                del self._analyze_cache[old_key]
            self._analyze_cache[fingerprint] = result

        return result

    def _parse_meta_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
        """
        解析 META 图层的结构化实体元数据。
        格式: ENTITY:<type>|x:<x>|y:<y>|w:<w>|h:<h>|key:value|...
        用于合成图纸测试场景，跳过常规几何归并直接构建实体。
        """
        entities = []
        for prim in primitives:  # 循环
            if prim.layer.upper() != "META":
                continue  # 继续循环
            text = prim.properties.get("text", "")
            if not text.startswith("ENTITY:"):
                continue  # 继续循环
            parts = text.split("|")
            if len(parts) < 5:
                continue  # 继续循环
            # 解析类型
            etype = parts[0].replace("ENTITY:", "").strip()
            # 解析bbox和属性
            props = {}
            bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
            for part in parts[1:]:  # 循环
                if ":" not in part:
                    continue  # 继续循环
                k, v = part.split(":", 1)  # 操作
                k = k.strip()
                v = v.strip()
                if k == "x":
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
                        props[k] = float(v)
                    except ValueError:  # 捕获异常
                        props[k] = v

            self._entity_counter += 1
            entity = SemanticEntity(
                entity_id=f"{etype.upper()}_{self._entity_counter:03d}",
                entity_type=etype,
                bbox=bbox,
                layer="META",
                confidence=1.0,
                properties=props,
            )
            entities.append(entity)

        return entities

    def _classify_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:
        """图元分类归并"""
        # 优先解析 META 图层（合成图纸结构化数据）
        meta_entities = self._parse_meta_entities(primitives)
        if meta_entities:
            return meta_entities

        entities = []

        for prim in primitives:  # 循环
            # 图层规则匹配
            entity_type = self._classify_by_layer(prim.layer)
            if entity_type == "unknown":
                entity_type = self._classify_by_geometry(prim)

            if entity_type == "unknown":
                continue  # 继续循环

            self._entity_counter += 1
            # 过滤 NaN properties
            cleaned_props = {}
            for pk, pv in prim.properties.items():  # 循环
                if isinstance(pv, float):
                    import math
                    if not math.isnan(pv):
                        cleaned_props[pk] = pv
                else:  # 否则
                    cleaned_props[pk] = pv
            entity = SemanticEntity(
                entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",
                entity_type=entity_type,
                bbox=prim.bbox,
                layer=prim.layer,
                confidence=0.9 if entity_type != "unknown" else 0.5,
                properties=cleaned_props,
            )
            entities.append(entity)

        # 归并同类重叠图元
        entities = self._merge_overlapping(entities)

        # 过滤过小的走廊实体（LINE 类型容易被误识别为走廊）
        # 走廊宽度 < 500mm 且 bbox 短边 < 500mm 的实体可能是微小图元误标
        filtered = []
        for e in entities:  # 循环
            if e.type == "corridor":
                bb = e.bbox
                bw = bb.get("width", 0)
                bh = bb.get("height", 0)
                short_edge = min(bw, bh) if bw > 0 and bh > 0 else max(bw, bh)
                if short_edge < 500:  # 短边 < 500mm 不可能是走廊
                    continue  # 继续循环
            filtered.append(e)
        entities = filtered

        return entities

    def _is_near_closed(self, prim: RawPrimitive, gap_threshold_mm: float = 500.0) -> bool:
        """接近闭合检测：开放多边形首尾点距离 < 阈值 → 视为闭合

        用于处理缺口房间（L 形/U 形房间在墙体断开处形成缺口）
        """
        pts = prim.properties.get("points")
        if not pts or len(pts) < 3:
            return False
        # 获取首尾点
        start = (pts[0][0], pts[0][1])
        end = (pts[-1][0], pts[-1][1])
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        gap = math.sqrt(dx * dx + dy * dy)
        return gap < gap_threshold_mm

    def _classify_by_layer(self, layer: str) -> str:
        """图层规则归类

        长关键字（≥3字符）：子串匹配
        短关键字（1-2字符）：全词匹配（前后是_或边界），防止误匹配
        """
        if not layer:
            return "unknown"
        layer_upper = layer.upper()

        # 长关键字（≥3字符）：子串匹配
        for keyword, entity_type in LAYER_RULES.items():  # 循环
            if keyword in layer_upper:
                return entity_type

        # 短关键字（1-2字符）：全词匹配
        for keyword, entity_type in SHORT_LAYER_RULES.items():  # 循环
            if keyword in layer_upper:
                # 检查全词边界
                idx = layer_upper.find(keyword)
                while idx >= 0:  # 循环
                    pre_ok = (idx == 0 or layer_upper[idx-1] == '_')
                    post_ok = (idx + len(keyword) >= len(layer_upper) or layer_upper[idx+len(keyword)] == '_')
                    if pre_ok and post_ok:
                        return entity_type
                    idx = layer_upper.find(keyword, idx + 1)

        return "unknown"

    def _classify_by_geometry(self, prim: RawPrimitive) -> str:
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

        if dxf_type == "LINE":
            if length > 2000:
                return "wall"
            # 中等长度 LINE（700~2000mm）：典型门宽范围 → door
            if 700 < length < 2000 and short_edge < 50:
                return "door"
            # 短 LINE（50~700mm）可能是门的宽度线或小构件
            if 50 < length < 700 and short_edge < 5:
                return "door"
            # LINE 类型 bbox 短边≈0（纯线无宽度），不可能是走廊
            # 只有长度 > 2000mm 的 LINE 才可能归类为 wall（已处理）
            return "other"

        if dxf_type in ("LWPOLYLINE", "POLYLINE"):
            pts_count = props.get("point_count", 0)
            if pts_count == 2:
                # 2 点 LWPOLYLINE：视为 LINE 等价
                if length > 2000:
                    return "wall"
                if 700 < length < 2000 and short_edge < 50:
                    return "door"
                if 50 < length < 700 and short_edge < 5:
                    return "door"
                return "other"
            
            # 闭合多边形判断（含缺口补全）
            is_closed = props.get("area", 0) > 0 or (pts_count >= 3)
            if not is_closed and pts_count >= 3:
                is_closed = self._is_near_closed(prim, gap_threshold_mm=500.0)
            if is_closed:
                aspect_ratio = max(bw, bh) / max(short_edge, 1)
                # 图层排除：非建筑图层上的闭合多边形不可能是房间
                non_room_layers = ["COLU", "视口", "洞口", "板边", "梁边", "轴", "BASE", "梁", "吊筋", "板层", "文字", "钢筋", "标注", "DIM", "立面看线", "立面", "看线", "园林", "井", "电-", "系统", "设备", "电缆", "Defpoints"]
                if any(kw in prim.layer.upper() for kw in non_room_layers):
                    if aspect_ratio > 3:
                        return "other"
                    return "wall"
                # room 最小面积 1m²（1,000,000mm²），过滤小框/文字标注
                # room 最大面积 500m²（500,000,000mm²），过滤图纸边界框/标题栏框
                if area > 500000000:  # > 500m² → 图纸边界/标题栏，不是房间
                    return "other"
                if area > 1000000:  # > 1m²
                    if aspect_ratio > 5:
                        # 狭长 → 走廊
                        if length > 3000:
                            return "wall"
                        return "corridor"
                    return "room"
                elif area > 50000:  # 大面积但 < 1m²
                    if aspect_ratio > 5:
                        if length > 3000:
                            return "wall"
                        return "corridor"
                    return "wall"
                elif area > 50000:  # 条件分支
                    # 中等面积（0.05~1m²）：可能是小房间或设备间
                    if aspect_ratio > 4:
                        return "corridor"
                    return "room"
                elif area > 5000:  # 条件分支
                    # 小面积（0.005~0.05m²）：通常是文字框/图例框/标注框，不是房间
                    return "other"
                else:  # 否则
                    # 小面积闭合多边形（500~5000mm²）→ door 或 window
                    if aspect_ratio > 3:
                        # 狭长小面积 → 门的开合轨迹
                        return "door"
                    elif aspect_ratio < 1.5:  # 条件分支
                        # 接近正方形的小面积 → column
                        return "column"
                    return "door"
            return "corridor"

        # ARC：门弧、窗或弧形房间
        if dxf_type == "ARC":
            radius = props.get("radius", 0)
            # 大半径 ARC（>3000mm）且弧线角度大 → 弧形房间轮廓
            if radius > 3000:
                angle_span = abs(props.get("start_angle", 0) - props.get("end_angle", 0)) or 0
                # 弧线跨度 > 90° 视为房间轮廓
                if angle_span > 90:
                    return "room"
            if 100 < radius < 2000:
                return "door"
            return "window"

        if dxf_type == "CIRCLE":
            radius = props.get("radius", 0)
            if radius > 3000:
                return "stair"
            elif radius > 1000:  # 条件分支
                return "stair"
            elif radius > 300:  # 条件分支
                return "column"
            return "column"

        if dxf_type == "TEXT":
            text = props.get("text", "")
            if not text:
                return "text"
            text_upper = text.upper()
            if "出口" in text or "EXIT" in text_upper:
                return "exit"
            if "楼梯" in text or "STAIR" in text_upper:
                return "stair"
            # "防火" 关键词需配合 "门" 或 "窗" 才能归类，避免文本描述被误标
            if "防火门" in text or ("FIRE" in text_upper and "DOOR" in text_upper):
                return "fire_door"
            if "防火窗" in text or ("FIRE" in text_upper and "WINDOW" in text_upper):
                return "fire_window"
            # ── 消防设施/系统关键词（用于真实图纸 TEXT 辅助识别） ──
            if "消火栓" in text or "HYDRANT" in text_upper:
                return "fire_hydrant"
            if "喷淋" in text or "洒水" in text or "SPRINKLER" in text_upper:
                return "sprinkler"
            if "灭火器" in text or "灭火" in text:
                return "fire_extinguisher"
            if "烟感" in text or "烟雾探测" in text or "探测器" in text or "SMOKE" in text_upper:
                return "smoke_detector"
            if "报警" in text or "ALARM" in text_upper:
                return "fire_alarm"
            if "消防水箱" in text or "水箱" in text:
                return "water_tank"
            if "消防水池" in text or "水池" in text:
                return "water_reservoir"
            if "广播" in text or "音箱" in text or "SPEAKER" in text_upper:
                return "emergency_broadcast"
            if "应急照明" in text or "EVAC" in text_upper:
                return "evacuation_lighting"
            if "卷帘" in text or "CURTAIN" in text_upper:
                return "fire_curtain"
            if "消防电梯" in text or "FIRE_ELEV" in text_upper:
                return "fire_elevator"
            if "声光" in text:
                return "fire_alarm"
            return "text"

        # INSERT 块：从块名推断实体类型（完整映射表）
        if dxf_type == "INSERT":
            block_name = props.get("block_name", "").upper()
            # ── 防火门/防火窗 ──
            if "FIRE_DOOR" in block_name or "防火门" in block_name:
                return "fire_door"
            if "FIRE_WINDOW" in block_name or "防火窗" in block_name:
                return "fire_window"
            # ── 建筑构件 ──
            if "DOOR" in block_name or "门" in block_name:
                return "door"
            if "WINDOW" in block_name or "窗" in block_name:
                return "window"
            if "STAIR" in block_name or "ST" in block_name:
                return "stair"
            if "COLUMN" in block_name or "柱" in block_name:
                return "column"
            # ── 出口/疏散指示 ──
            if "EXIT" in block_name or "出口" in block_name:
                return "exit"
            if "EXIT_SIGN" in block_name or "SIGN" in block_name or "疏散指示" in block_name:
                return "exit_sign"
            # ── 消防设施 ──
            if "HYDRANT" in block_name or "消火栓" in block_name:
                return "fire_hydrant"
            if "SPRINKLER" in block_name or "喷淋" in block_name or "洒水" in block_name:
                return "sprinkler"
            if "FIRE_EXT" in block_name or "灭火器" in block_name or "灭火" in block_name:
                return "fire_extinguisher"
            if "SMOKE_DETECTOR" in block_name or "烟感" in block_name:
                return "smoke_detector"
            if "FIRE_ALARM" in block_name or "报警" in block_name:
                return "fire_alarm"
            if "WATER_TANK" in block_name or "水箱" in block_name:
                return "water_tank"
            if "WATER_RESERVOIR" in block_name or "消防水池" in block_name or "水池" in block_name:
                return "water_reservoir"
            if "FIRE_ELEV" in block_name or "消防电梯" in block_name:
                return "fire_elevator"
            if "SPEAKER" in block_name or "广播" in block_name or "应急广播" in block_name:
                return "emergency_broadcast"
            if "EVAC_LIGHT" in block_name or "应急照明" in block_name:
                return "evacuation_lighting"
            if "CURTAIN" in block_name or "卷帘" in block_name:
                return "fire_curtain"
            # ── 其他楼层/空间 ──
            if "ROOM" in block_name or "房间" in block_name or "室" in block_name:
                return "room"
            if "CORRIDOR" in block_name or "走廊" in block_name or "走道" in block_name:
                return "corridor"
            if "SHAFT" in block_name or "井道" in block_name or "竖井" in block_name:
                return "shaft"
            if "ELEVATOR" in block_name or "电梯" in block_name:
                return "elevator"
            if "LOBBY" in block_name or "前室" in block_name:
                return "lobby"
            if "FIRE_ZONE" in block_name or "防火分区" in block_name:
                return "fire_zone"
            # ── 未知块名 → 回退到 wall ──
            return "wall"

        return "unknown"

    def _infer_corridor_widths(self, entities: List[SemanticEntity],
                              primitives: List[RawPrimitive] = None) -> List[SemanticEntity]:  # 操作
        """从 bbox 短边和平行线聚类推断走廊/门的宽度（真实图纸适配）

        两层策略：
        1. 平行线聚类（primitives 可用时）：收集走廊图元，按方向分组，
           找平行线间距作为走廊宽度
        2. bbox 短边：对已有非零 bbox 的实体，短边*0.001 为宽度
        """
        import math
        from collections import defaultdict

        # 防御性过滤：修复 NaN bbox
        for ent in entities:  # 循环
            bbox = ent.bbox
            for k in ('x', 'y', 'width', 'height'):
                v = bbox.get(k, 0)
                if isinstance(v, float) and math.isnan(v):
                    bbox[k] = 0.0

        # ── 策略1：平行线聚类宽度推断（按空间分区）──
        if primitives:
            # 收集可能的走廊原始图元（LINE + 2点LWPOLYLINE）
            edge_candidates = []
            for p in primitives:  # 循环
                bbox = p.bbox
                cx = bbox.get("x", 0) + bbox.get("width", 0) / 2
                cy = bbox.get("y", 0) + bbox.get("height", 0) / 2
                # 排除坐标偏移的图元
                if abs(cx) < 100 and abs(cy) < 100:
                    continue  # 继续循环
                if abs(cx) > 1e7 or abs(cy) > 1e7:
                    continue  # 继续循环
                bw = bbox.get("width", 0)
                bh = bbox.get("height", 0)
                span = max(bw, bh)
                if span < 100 or span > 100000:  # 0.1m~100m 合理范围
                    continue  # 继续循环
                if p.dxf_type == "LINE":
                    angle = p.properties.get("angle", 0) % 180
                    if angle > 90: angle = 180 - angle
                    edge_candidates.append({
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,  # 字段
                        "span": span, "angle": angle,  # 字段
                    })
                elif p.dxf_type == "LWPOLYLINE" and p.properties.get("point_count", 0) == 2:  # 分支
                    angle = 0 if bw > bh else 90
                    edge_candidates.append({
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,  # 字段
                        "span": span, "angle": angle,  # 字段
                    })

            if edge_candidates:
                # 按方向分组
                h_edges = [e for e in edge_candidates if e["angle"] < 30]
                v_edges = [e for e in edge_candidates if e["angle"] > 60]

                # 水平线：按cy排序，收集所有gap
                h_sorted = sorted(h_edges, key=lambda e: e["cy"])
                h_gaps = []
                for i in range(min(300, len(h_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(h_sorted))):  # 循环
                        gap = abs(h_sorted[i]["cy"] - h_sorted[j]["cy"])
                        if 500 < gap < 10000:
                            h_gaps.append({"gap": gap, "y1": h_sorted[i]["cy"], "y2": h_sorted[j]["cy"],
                                          "cx1": h_sorted[i]["cx"], "cx2": h_sorted[j]["cx"]})  # 字段

                # 垂直线：按cx排序，收集所有gap
                v_sorted = sorted(v_edges, key=lambda e: e["cx"])
                v_gaps = []
                for i in range(min(300, len(v_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(v_sorted))):  # 循环
                        gap = abs(v_sorted[i]["cx"] - v_sorted[j]["cx"])
                        if 500 < gap < 10000:
                            v_gaps.append({"gap": gap, "x1": v_sorted[i]["cx"], "x2": v_sorted[j]["cx"],
                                          "cy1": v_sorted[i]["cy"], "cy2": v_sorted[j]["cy"]})  # 字段

                all_gaps = h_gaps + v_gaps
                if all_gaps and len(all_gaps) > 10:
                    # 空间分区聚类：每条走廊取离它最近的 gap 作为宽度
                    # 1) 对每个 gap，按位置分到最近的走廊
                    # 2) 每个走廊取其区域内 gap 众数
                    corridor_entities = [e for e in entities if e.type == "corridor"]
                    if corridor_entities:
                        for ent in corridor_entities:  # 循环
                            cx = ent.bbox.get("x", 0) + ent.bbox.get("width", 0) / 2
                            cy = ent.bbox.get("y", 0) + ent.bbox.get("height", 0) / 2
                            bw = ent.bbox.get("width", 0)
                            bh = ent.bbox.get("height", 0)
                            # 先用 bbox 短边推断宽度（LINE 类型用长边）
                            if bw > 0 and bh > 0:
                                w_mm = min(bw, bh)
                                w_m = w_mm * 0.001
                                if 0.3 < w_m < 3.0 and ent.properties.get("width", 0) < w_m:
                                    ent.properties["width"] = w_m  # 操作
                                    ent.properties["clear_width"] = w_m  # 操作
                                    ent.properties["_width_source"] = "bbox_short_edge"  # 操作
                                    continue  # 继续循环
                            
                            # bbox 短边≈0（LINE类型）：找附近gap
                            if ent.properties.get("width", 0) < 0.3:
                                # 找附近 gap
                                nearby_gaps = []
                                for g in all_gaps:  # 循环
                                    if "y1" in g:  # 水平gap
                                        mid_y = (g["y1"] + g["y2"]) / 2
                                        mid_x = (g["cx1"] + g["cx2"]) / 2
                                        if abs(cy - mid_y) < 3000 and abs(cx - mid_x) < 3000:
                                            nearby_gaps.append(g["gap"])
                                    else:  # 垂直gap
                                        mid_x = (g["x1"] + g["x2"]) / 2
                                        mid_y = (g["cy1"] + g["cy2"]) / 2
                                        if abs(cx - mid_x) < 3000 and abs(cy - mid_y) < 3000:
                                            nearby_gaps.append(g["gap"])
                                
                                if nearby_gaps:
                                    # 取附近gap的众数作为此走廊宽度
                                    gap_buckets = defaultdict(list)
                                    for g in nearby_gaps:  # 循环
                                        bucket = round(g / 100) * 100
                                        gap_buckets[bucket].append(g)  # 操作
                                    best_bucket = max(gap_buckets.items(), key=lambda x: len(x[1]))
                                    w_m = (sum(best_bucket[1]) / len(best_bucket[1])) / 1000.0
                                    if 0.3 < w_m < 3.0:
                                        ent.properties["width"] = w_m  # 操作
                                        ent.properties["clear_width"] = w_m  # 操作
                                        ent.properties["_width_source"] = "nearby_gap"  # 操作
                                else:  # 否则
                                    # 无附近gap：用bbox长边
                                    span_mm = max(bw, bh)
                                    w_m = span_mm * 0.001
                                    if 0.3 < w_m < 3.0:
                                        ent.properties["width"] = w_m  # 操作
                                        ent.properties["clear_width"] = w_m  # 操作
                                        ent.properties["_width_source"] = "bbox_long_edge"  # 操作
        
        # ── 策略1.5：door/window 宽度推断（V2增强）──
        for ent in entities:  # 循环
            if ent.type not in ("door", "window", "fire_door", "exit_door"):
                continue  # 继续循环
            existing = ent.properties.get("width", 0)
            if existing > 0.5:
                continue  # 继续循环
            # 从 ARC 半径推断门宽度（门弧半径 ≈ 门宽度）
            radius = ent.properties.get("radius", 0)
            if radius > 100 and radius < 2000:
                w_m = radius * 0.001  # mm → m
                if 0.3 < w_m < 2.0:
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
                    continue  # 继续循环
            # bbox 推断
            bbox = ent.bbox
            bw = bbox.get("width", 0)
            bh = bbox.get("height", 0)
            if bw > 0 and bh > 0:
                w_mm = min(bw, bh)
                w_m = w_mm * 0.001
                if 0.3 < w_m < 2.0 and ent.properties.get("width", 0) < w_m:
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
            # LINE 类型（短边≈0）：用长边作为宽度
            if ent.properties.get("width", 0) < 0.3:
                span_mm = max(bw, bh)
                if 300 < span_mm < 2000:  # 300mm~2m
                    w_m = span_mm * 0.001
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
            # Polygon 类 door（闭合多边形）：短边可能是门扇厚度，用长边推断宽度
            if ent.properties.get("width", 0) < 0.3:
                long_edge_mm = max(bw, bh)
                if 300 < long_edge_mm < 2000:
                    w_m = long_edge_mm * 0.001
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作

        # ── 策略2：bbox 短边推断（覆盖所有类型） ──
        for ent in entities:  # 循环
            if ent.type not in ("corridor", "door", "window", "room", "wall"):
                continue  # 继续循环
            bbox = ent.bbox
            bw = bbox.get("width", 0)
            bh = bbox.get("height", 0)

            if bw == 0 and bh == 0:
                continue  # 继续循环

            # bbox 两边非零 → 短边为宽度（mm→m），长边为 length
            if bw > 0 and bh > 0:
                w_mm = min(bw, bh)
                w_m = w_mm * 0.001
                if not math.isnan(w_m) and w_m > 0.01 and w_m < 10:
                    current_w = ent.properties.get("width", 0)
                    if current_w < w_m:
                        ent.properties["width"] = w_m  # 操作
                        ent.properties["clear_width"] = w_m  # 操作
                l_mm = max(bw, bh)
                if l_mm > 0:
                    ent.properties["length"] = l_mm * 0.001  # 操作
                continue  # 继续循环

            # bbox 只有一边非零（LINE / 2 点 LWPOLYLINE）
            span_mm = max(bw, bh)
            if span_mm > 0:
                span_m = span_mm * 0.001
                if not math.isnan(span_m) and span_m > 0.05:
                    ent.properties["length"] = span_m  # 操作
                    # 对 corridor/room：bbox短边≈宽度
                    if ent.type in ("corridor", "room", "door", "fire_door", "exit_door"):
                        short_mm = min(bw, bh) if bw > 0 and bh > 0 else 0
                        if short_mm > 0:
                            short_m = short_mm * 0.001
                            current_w = ent.properties.get("width", 0)
                            if current_w < 0.01 and 0.05 < short_m < 3.0:
                                ent.properties["width"] = short_m  # 操作
                                ent.properties["clear_width"] = short_m  # 操作

        return entities

    def _merge_overlapping(self, entities: List[SemanticEntity]) -> List[SemanticEntity]:
        """合并重叠/相邻的同类图元（空间哈希加速版）

        小数据量（<2000）直接 O(n²) 全量对比；
        大数据量使用网格分桶，只对比同网格或相邻网格内的实体。
        """
        n = len(entities)
        if n < 2:
            return entities

        # ── 小数据量：直接 O(n²) 全量对比（开销小，无额外内存） ──
        if n < 2000:
            merged = []
            used = set()
            for i, a in enumerate(entities):
                if i in used:
                    continue
                cluster = [a]
                used.add(i)
                for j, b in enumerate(entities):
                    if j in used:
                        continue
                    if a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5:
                        cluster.append(b)
                        used.add(j)
                if len(cluster) > 1:
                    merged_bbox = self._union_bbox([e.bbox for e in cluster])
                    merged.append(SemanticEntity(
                        entity_id=a.id, entity_type=a.type,
                        bbox=merged_bbox, layer=a.layer,
                        confidence=max(e.confidence for e in cluster),
                        properties=a.properties,
                    ))
                else:
                    merged.append(a)
            return merged

        # ── 大数据量：空间哈希分桶 ──
        CELL_SIZE = 500.0  # mm，网格大小
        from collections import defaultdict

        # 构建网格索引：{(gx, gy): [idx, ...]}
        grid = defaultdict(list)
        for idx, e in enumerate(entities):
            bx = e.bbox.get("x", 0)
            by = e.bbox.get("y", 0)
            bw = max(e.bbox.get("width", 0), 1.0)
            bh = max(e.bbox.get("height", 0), 1.0)
            gx1 = int(bx / CELL_SIZE)
            gx2 = int((bx + bw) / CELL_SIZE)
            gy1 = int(by / CELL_SIZE)
            gy2 = int((by + bh) / CELL_SIZE)
            for gx in range(gx1, gx2 + 1):
                for gy in range(gy1, gy2 + 1):
                    grid[(gx, gy)].append(idx)

        # 去重标记
        merged = []
        used = set()

        for i, a in enumerate(entities):
            if i in used:
                continue

            cluster = [a]
            used.add(i)

            # 找到 a 所在的网格
            bx = a.bbox.get("x", 0)
            by = a.bbox.get("y", 0)
            bw = max(a.bbox.get("width", 0), 1.0)
            bh = max(a.bbox.get("height", 0), 1.0)
            gx1 = int(bx / CELL_SIZE)
            gx2 = int((bx + bw) / CELL_SIZE)
            gy1 = int(by / CELL_SIZE)
            gy2 = int((by + bh) / CELL_SIZE)

            # 收集相邻网格中的候选实体
            candidates = set()
            for gx in range(gx1 - 1, gx2 + 2):
                for gy in range(gy1 - 1, gy2 + 2):
                    for idx in grid.get((gx, gy), []):
                        if idx not in used:
                            candidates.add(idx)

            for j in sorted(candidates):
                if j in used:
                    continue
                b = entities[j]
                if a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5:
                    cluster.append(b)
                    used.add(j)

            if len(cluster) > 1:
                merged_bbox = self._union_bbox([e.bbox for e in cluster])
                merged.append(SemanticEntity(
                    entity_id=a.id, entity_type=a.type,
                    bbox=merged_bbox, layer=a.layer,
                    confidence=max(e.confidence for e in cluster),
                    properties=a.properties,
                ))
            else:
                merged.append(a)

        return merged

    def _build_relations(self, entities: List[SemanticEntity]) -> List[SpatialRelation]:
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
        relations = []
        n_entities = len(entities)

        # ── 1. 相邻关系（空间哈希加速，>2000 实体跳过）──
        # 大图纸跳过全量相邻关系构建（相邻关系主要用于疏散路径分析，
        # 大图 room 数量少，跳过不影响规范判定准确性）
        # ── 1. 相邻关系（空间哈希加速，>2000 实体跳过）──
        # 大图纸跳过全量相邻关系构建（相邻关系主要用于疏散路径分析，
        # 大图 room 数量少，跳过不影响规范判定准确性）
        if n_entities <= 2000:
            CELL_SIZE = 100.0  # mm
            # 空间哈希网格
            grid: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}
            for idx, e in enumerate(entities):
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

            # 只比较同一或相邻网格的实体
            compared = set()
            for idx_a, a in enumerate(entities):
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
                                relations.append(SpatialRelation(
                                    source_id=a.id, target_id=b.id,
                                    rel_type="adjacent", distance=dist,
                                    confidence=1.0 - dist / self.ADJACENT_THRESHOLD,
                                ))

        # ── 2. 墙体-门窗拓扑关系（V2升级）──
        # 用几何方法精确匹配门/窗在墙上的位置：
        #   门 bbox 必须与墙 bbox 的某条边重叠（门在墙上）
        #   取最近/重叠最大的墙作为门的宿主墙
        walls = [e for e in entities if e.type == "wall"]
        openings = [e for e in entities if e.type in ("door", "window", "fire_door", "exit_door")]
        
        for opening in openings:  # 循环
            best_wall = None
            best_overlap = 0.0
            best_distance = float('inf')
            
            ob = opening.bbox
            ox1, oy1 = ob.get("x", 0), ob.get("y", 0)  # 操作
            ox2 = ox1 + ob.get("width", 0)
            oy2 = oy1 + ob.get("height", 0)
            o_cx = (ox1 + ox2) / 2
            o_cy = (oy1 + oy2) / 2
            
            for wall in walls:  # 循环
                wb = wall.bbox
                wx1, wy1 = wb.get("x", 0), wb.get("y", 0)  # 操作
                wx2 = wx1 + wb.get("width", 0)
                wy2 = wy1 + wb.get("height", 0)
                
                # 计算门中心到墙边的距离
                # 到左/右垂直边的水平距离
                dx_left = abs(o_cx - wx1)
                dx_right = abs(o_cx - wx2)
                # 到上/下水平边的垂直距离
                dy_bottom = abs(o_cy - wy1)
                dy_top = abs(o_cy - wy2)
                
                min_dx = min(dx_left, dx_right)
                min_dy = min(dy_bottom, dy_top)
                dist_to_edge = min(min_dx, min_dy)
                
                # 检查重叠：门必须接触墙的边界（距离<50mm）
                if dist_to_edge > 50.0:
                    continue  # 继续循环
                
                # 计算门在墙边上的投影重叠长度
                overlap = 0.0
                is_horizontal_wall = (wb.get("width", 0) > wb.get("height", 0))
                
                if min_dx <= min_dy:
                    # 门接触垂直边（墙的左或右边）
                    # 投影重叠在 y 方向
                    overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))
                    overlap = overlap_y / max(ob.get("height", 1), 1)
                else:  # 否则
                    # 门接触水平边（墙的上或下边）
                    overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))
                    overlap = overlap_x / max(ob.get("width", 1), 1)
                
                if overlap > best_overlap or (overlap == best_overlap and dist_to_edge < best_distance):
                    best_overlap = overlap
                    best_distance = dist_to_edge
                    best_wall = wall
            
            if best_wall:
                relations.append(SpatialRelation(
                    source_id=best_wall.id, target_id=opening.id,
                    rel_type="contains",
                    confidence=min(0.95, best_overlap),
                ))
                # 给门注入宿主墙信息
                opening.properties["host_wall_id"] = best_wall.id  # 操作
                opening.properties["host_wall_overlap"] = round(best_overlap, 2)  # 操作

        # ── 3. 走廊-门-房间拓扑（V2：基于边缘距离）──
        # 用 _min_edge_distance 判断门是否连接走廊/房间
        corridors = [e for e in entities if e.type == "corridor"]
        rooms = [e for e in entities if e.type == "room"]
        doors = [e for e in entities if e.type in ("door", "fire_door", "exit_door")]
        
        for door in doors:  # 循环
            for c in corridors:  # 循环
                dist = self._min_edge_distance(door.bbox, c.bbox)
                if dist < 200.0:  # 门边缘距走廊 < 200mm
                    relations.append(SpatialRelation(
                        source_id=c.id, target_id=door.id,
                        rel_type="connects_to", distance=dist,
                        via="door",
                    ))
            for r in rooms:  # 循环
                dist = self._min_edge_distance(door.bbox, r.bbox)
                if dist < 200.0:
                    relations.append(SpatialRelation(
                        source_id=r.id, target_id=door.id,
                        rel_type="connects_to", distance=dist,
                        via="door",
                    ))

        # ── 4. 包含关系（房间包含设备/柱）──
        contained_types = {"column", "stair", "exit", "fire_door"}
        containables = [e for e in entities if e.type in contained_types]
        for room in rooms:  # 循环
            for item in containables:  # 循环
                if self._is_inside(item.bbox, room.bbox):
                    relations.append(SpatialRelation(
                        source_id=room.id, target_id=item.id,
                        rel_type="contains", confidence=0.9,
                    ))

        # ── 5. 房间-门间接连接（通过墙传递）──
        # 如果房间与墙相邻，且门被墙包含，则建立房间-门的连接
        # 这样 BFS 才能从房间走到门再到出口
        room_wall_adj = {}
        wall_door_contains = {}
        for rel in relations:  # 循环
            if rel.type == "adjacent":
                if rel.source_id in {r.id for r in rooms} and rel.target_id in {w.id for w in walls}:
                    room_wall_adj.setdefault(rel.source_id, set()).add(rel.target_id)
                if rel.target_id in {r.id for r in rooms} and rel.source_id in {w.id for w in walls}:
                    room_wall_adj.setdefault(rel.target_id, set()).add(rel.source_id)
            if rel.type == "contains":
                if rel.source_id in {w.id for w in walls} and rel.target_id in {d.id for d in doors}:
                    wall_door_contains.setdefault(rel.source_id, set()).add(rel.target_id)
        for room_id, wall_ids in room_wall_adj.items():  # 循环
            for wall_id in wall_ids:  # 循环
                for door_id in wall_door_contains.get(wall_id, set()):  # 循环
                    relations.append(SpatialRelation(
                        source_id=room_id, target_id=door_id,
                        rel_type="connects_to", distance=0.0,
                        via="door",
                    ))

        return relations

    def _bind_dimensions(self, entities: List[SemanticEntity],
                         dimensions: List[Dict]) -> Dict[str, Dict]:  # 操作
        """尺寸标注绑定到实体"""
        bindings = {}

        for dim in dimensions:  # 循环
            dim_pos = dim.get("position", {})
            if not dim_pos:
                continue  # 继续循环

            nearest = None
            nearest_dist = float("inf")

            for entity in entities:  # 循环
                center = self._bbox_center(entity.bbox)
                dist = self._point_distance(dim_pos, center)
                if dist < nearest_dist and dist < 500:
                    nearest = entity
                    nearest_dist = dist

            if nearest:
                if nearest.id not in bindings:
                    bindings[nearest.id] = {}  # 操作
                attr_name = self._infer_attribute_name(dim, nearest)
                bindings[nearest.id][attr_name] = dim.get("measurement", 0)  # 操作

        return bindings

    # ── 几何工具函数 ────────────────────────────────────

    @staticmethod
    def _compute_iou(bbox1: Dict, bbox2: Dict) -> float:
        """计算 IoU"""
        x1 = max(bbox1["x"], bbox2["x"])
        y1 = max(bbox1["y"], bbox2["y"])
        x2 = min(bbox1["x"] + bbox1["width"], bbox2["x"] + bbox2["width"])
        y2 = min(bbox1["y"] + bbox1["height"], bbox2["y"] + bbox2["height"])

        if x2 <= x1 or y2 <= y1:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)
        area1 = bbox1["width"] * bbox1["height"]
        area2 = bbox2["width"] * bbox2["height"]
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _union_bbox(bboxes: List[Dict]) -> Dict[str, float]:
        """合并多个边界框"""
        xs = [b["x"] for b in bboxes]
        ys = [b["y"] for b in bboxes]
        x2s = [b["x"] + b["width"] for b in bboxes]
        y2s = [b["y"] + b["height"] for b in bboxes]
        return {
            "x": min(xs), "y": min(ys),  # 字段
            "width": max(x2s) - min(xs),  # 字段
            "height": max(y2s) - min(ys),  # 字段
        }

    @staticmethod
    def _min_edge_distance(bbox1: Dict, bbox2: Dict) -> float:
        """最小边缘距离"""
        x1a, y1a = bbox1["x"], bbox1["y"]  # 操作
        x2a = x1a + bbox1["width"]
        y2a = y1a + bbox1["height"]
        x1b, y1b = bbox2["x"], bbox2["y"]  # 操作
        x2b = x1b + bbox2["width"]
        y2b = y1b + bbox2["height"]

        dx = max(x1b - x2a, x1a - x2b, 0)
        dy = max(y1b - y2a, y1a - y2b, 0)
        return (dx**2 + dy**2) ** 0.5

    @staticmethod
    def _is_inside(inner: Dict, outer: Dict) -> bool:
        """判断内部"""
        return (inner["x"] >= outer["x"]
                and inner["y"] >= outer["y"]  # 操作
                and inner["x"] + inner["width"] <= outer["x"] + outer["width"]  # 操作
                and inner["y"] + inner["height"] <= outer["y"] + outer["height"])  # 操作

    @staticmethod
    def _bbox_center(bbox: Dict) -> Dict[str, float]:
        return {"x": bbox["x"] + bbox["width"] / 2,
                "y": bbox["y"] + bbox["height"] / 2}  # 字段

    @staticmethod
    def _point_distance(p1: Dict, p2: Dict) -> float:
        return ((p1.get("x", 0) - p2.get("x", 0))**2
                + (p1.get("y", 0) - p2.get("y", 0))**2) ** 0.5  # 欧氏距离计算

    @staticmethod
    def _infer_attribute_name(dim: Dict, entity: SemanticEntity) -> str:
        """推断属性名"""
        entity_type = entity.type
        dim_text = dim.get("text", "")

        if entity_type == "wall":
            return "width"
        elif entity_type in ("door", "fire_door"):  # 分支
            return "clear_width"
        elif entity_type == "window":  # 分支
            return "width"
        elif entity_type == "stair":  # 分支
            return "step_width"
        elif entity_type == "corridor":  # 分支
            return "clear_width"
        elif entity_type == "fire_zone":  # 分支
            return "area"
        else:  # 否则
            return "measurement"

    # ── 走廊拓扑网络 ────────────────────────────────────

    def build_corridor_topology(self, entities: List[SemanticEntity],
                                 relations: List[SpatialRelation]) -> Dict[str, Any]:  # 操作
        """构建走廊拓扑网络
        
        将走廊实体按空间相邻关系连接为图，识别：
        - 连通分量（哪些走廊连通）
        - 死胡同（只有一条连接的走廊段）
        - 疏散路径（走廊到出口的可达性）
        """
        corridor_map = {e.id: e for e in entities if e.type == "corridor"}
        
        if len(corridor_map) < 2:
            return {
                "corridors": [e.to_dict() for e in corridor_map.values()],  # 字段
                "components": 1,  # 字段
                "dead_ends": [],  # 字段
                "network": {"nodes": list(corridor_map.keys()), "edges": []},  # 字段
            }

        # 构建走廊-走廊相邻图
        adjacency: Dict[str, List[Tuple[str, float]]] = {eid: [] for eid in corridor_map}  # 操作
        
        for rel in relations:  # 循环
            src = rel.source_id
            tgt = rel.target_id
            if src in corridor_map and tgt in corridor_map and rel.type == "adjacent":
                adjacency[src].append((tgt, rel.distance))  # 操作
                adjacency[tgt].append((src, rel.distance))  # 操作
        
        # 门连接：门关联的走廊也算连通
        for rel in relations:  # 循环
            if rel.type != "connects_to":
                continue  # 继续循环
            door_id = rel.target_id
            corridor_id = rel.source_id
            if corridor_id not in corridor_map:
                continue  # 继续循环
            # 找门连接的另一侧（room或其他走廊）
            for rel2 in relations:  # 循环
                if rel2.source_id == door_id and rel2.target_id != corridor_id:
                    other_id = rel2.target_id
                    if other_id in corridor_map:
                        adjacency[corridor_id].append((other_id, rel2.distance))  # 操作
                        adjacency[other_id].append((corridor_id, rel2.distance))  # 操作

        # 找连通分量（BFS）
        visited = set()
        components = []
        for eid in corridor_map:  # 循环
            if eid in visited:
                continue  # 继续循环
            comp = []
            queue = [eid]
            while queue:  # 循环
                current = queue.pop(0)
                if current in visited:
                    continue  # 继续循环
                visited.add(current)
                comp.append(current)
                for neighbor, _ in adjacency.get(current, []):  # 循环
                    if neighbor not in visited:
                        queue.append(neighbor)
            if comp:
                components.append(comp)

        # 找死胡同（度=1的走廊节点）
        dead_ends = []
        for eid, neighbors in adjacency.items():  # 循环
            if len(neighbors) == 1:
                ent = corridor_map[eid]
                dead_ends.append({
                    "id": eid,  # 字段
                    "width": ent.properties.get("width", 0),  # 字段
                    "length": ent.properties.get("length", 0),  # 字段
                    "bbox": ent.bbox,  # 字段
                })

        # 走廊宽度统计
        widths = [e.properties.get("width", 0) for e in corridor_map.values()]
        valid_widths = [w for w in widths if w > 0]

        return {
            "corridors": [e.to_dict() for e in corridor_map.values()],  # 字段
            "components": len(components),  # 字段
            "component_sizes": [len(c) for c in components],  # 字段
            "dead_ends": dead_ends,  # 字段
            "dead_end_count": len(dead_ends),  # 字段
            "width_avg": round(sum(valid_widths) / len(valid_widths), 2) if valid_widths else 0,  # 字段
            "width_min": round(min(valid_widths), 2) if valid_widths else 0,  # 字段
            "width_max": round(max(valid_widths), 2) if valid_widths else 0,  # 字段
            "network": {  # 字段
                "nodes": list(corridor_map.keys()),  # 字段
                "edges": [  # 字段
                    {"source": s, "target": t, "distance": d}  # 字面量
                    for s, neighbors in adjacency.items()  # 循环
                    for t, d in neighbors  # 循环
                    if s < t  # 去重
                ],
            },
        }

    def analyze_evacuation_routes(self, entities: List[SemanticEntity],
                                    relations: List[SpatialRelation]) -> List[Dict]:  # 操作
        """疏散路径分析
        
        检查从每个 room 到最近 exit 的路径：
        1. 是否所有房间都有通往出口的路径
        2. 路径长度是否超过疏散距离阈值
        3. 路径上的走廊宽度是否满足要求
        """
        # 构建全量实体邻接表
        adj: Dict[str, List[Tuple[str, str, float]]] = {}  # 操作
        for e in entities:  # 循环
            adj[e.id] = []
        
        for rel in relations:  # 循环
            if rel.type not in ("adjacent", "connects_to", "contains"):
                continue  # 继续循环
            adj.setdefault(rel.source_id, []).append((rel.target_id, rel.type, rel.distance))
            adj.setdefault(rel.target_id, []).append((rel.source_id, rel.type, rel.distance))

                # 出口识别：优先用明确的 exit/exit_door
        strict_exits = [e for e in entities if e.type in ("exit", "exit_door")]
        fallback_exits = [e for e in entities if e.type in ("door", "fire_door")]
        # 有明确出口就用明确出口，否则用 door/fire_door 兜底
        exits = strict_exits if strict_exits else fallback_exits
        
        rooms = [e for e in entities if e.type == "room"]
        
        if not exits:
            return []

        # 无明确 exit 时，room 面积 < 10m² 跳过 EVAC 判定（非疏散空间）
        skip_small_rooms = not strict_exits and bool(fallback_exits)

        # 如果没有 room 但有 corridor，用 corridor 作为起点分析连通性
        if not rooms:
            corridors = [e for e in entities if e.type == "corridor"]
            if corridors:
                rooms = corridors  # 兜底：用走廊代替房间作为起点
            else:  # 否则
                return []
        
        # 优先用 type=exit 的，兜底用 door/fire_door
        has_exit_type = any(e.type == "exit" for e in exits)
        if not has_exit_type:
            pass  # 占位

        routes = []
        for room in rooms:  # 循环
            # 兜底模式（无明确exit）且 room 面积 < 10m²：跳过 EVAC 判定
            if skip_small_rooms:
                bw = room.bbox.get("width", 0)
                bh = room.bbox.get("height", 0)
                area = bw * bh / 1e6
                if area < 10:
                    route_info = {
                        "room_id": room.id,  # 字段
                        "room_type": room.type,  # 字段
                        "room_bbox": room.bbox,  # 字段
                        "has_route": True,  # 字段
                        "path_length": None,  # 字段
                        "exit_id": None,  # 字段
                    }
                    routes.append(route_info)
                    continue  # 继续循环

            # BFS 找最近出口
            visited = {room.id}
            queue = [(room.id, [room.id], 0.0)]
            found_route = None

            while queue:  # 循环
                current, path, distance = queue.pop(0)  # 解包
                if current in {e.id for e in exits}:
                    found_route = (path, distance)
                    break  # 跳出循环
                for neighbor, rel_type, dist in adj.get(current, []):  # 循环
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, path + [neighbor], distance + dist))

            route_info = {
                "room_id": room.id,  # 字段
                "room_type": room.type,  # 字段
                "room_bbox": room.bbox,  # 字段
                "has_route": found_route is not None,  # 字段
                "path_length": round(found_route[1], 2) if found_route else None,  # 字段
                "path": found_route[0] if found_route else [],  # 字段
                "is_dead_end_room": room.properties.get("is_dead_end", False),  # 字段
                # 死胡同走廊（袋形走道）：疏散距离 ≤ 20m（GB50016-5.5.17注1）
                # 其他走廊/房间：≤ 30m
                "evac_distance_limit": 20.0 if room.properties.get("is_dead_end", False) else 30.0,  # 字段
                "exceeds_max_distance": found_route is not None and found_route[1] > (20.0 if room.properties.get("is_dead_end", False) else 30.0),  # 字段
            }
            routes.append(route_info)

        return routes

    def _yolo_enhance(self, dxf_path: str) -> List[SemanticEntity]:
        """对 DXF 执行 YOLO 检测，返回增强实体列表

        当前只保留 YOLO 检测精度高的实体类型：
        - room (mAP50=0.995)：房间检测极准确
        - corridor (mAP50=0.709)：走廊检测良好
        """
        from .yolo_integrator import YOLODetectionIntegrator  # 导入

        integrator = YOLODetectionIntegrator()
        if not integrator.load_model():
            logger.warning("YOLO 模型加载失败")
            return []

        # 渲染 DXF 并预测
        image_path, detections = integrator.render_and_predict(dxf_path, dpi=72)
        if not image_path or not detections:
            return []

        # 只保留高精度类型（room, corridor）
        # room mAP50=0.995, corridor mAP50=0.709
        HIGH_CONF_TYPES = {"room", "corridor"}
        filtered = [d for d in detections if d["type"] in HIGH_CONF_TYPES and d["confidence"] >= 0.35]

        # 对 room 类型：过滤掉 bbox 面积过小或过大的（不合理房间）
        # YOLO 的 bbox 是像素坐标，需要先转为世界坐标再判断面积
        # 用 bbox 的像素宽高比辅助判断：房间应该是矩形（宽高比 < 3）
        filtered = [d for d in filtered if d["type"] != "room" or (
            d["bbox"]["width"] > 20 and d["bbox"]["height"] > 20 and  # 最小尺寸 20 像素
            max(d["bbox"]["width"], d["bbox"]["height"]) / max(d["bbox"]["height"], d["bbox"]["width"], 1) < 5.0  # 宽高比 < 5
        )]

        # P25: YOLO 后置规则层兜底过滤
        from .yolo_integrator import filter_yolo_detections
        filtered = filter_yolo_detections(filtered, verbose=True)

        if not filtered:
            return []

        # 转换为 SemanticEntity
        entities = []
        for det in filtered:  # 循环
            self._entity_counter += 1
            entity = SemanticEntity(
                entity_id=f"YOLO_{det['type'].upper()}_{self._entity_counter:03d}",
                entity_type=det["type"],
                bbox=det["bbox"],
                layer="YOLO",
                confidence=det["confidence"],
                properties={
                    **det.get("properties", {}),  # 展开
                    "detection_source": "yolo",  # 字段
                },
            )
            entities.append(entity)

        # 清理临时图片
        try:  # 尝试
            os.remove(image_path)
        except Exception:  # 捕获异常
            pass  # 忽略

        return entities

    def _merge_yolo_results(self, rule_entities: List[SemanticEntity],
                             yolo_entities: List[SemanticEntity]) -> List[SemanticEntity]:
        """合并规则解析和 YOLO 检测的实体

        策略：
        1. 规则解析的实体优先保留（含已识别的 room）
        2. YOLO 检测的 room/corridor 只在规则未识别到时添加
        3. 通过 IOU 判断重叠——YOLO 框与规则框高度重叠时不重复添加
        4. YOLO 实体标记 detection_source="yolo"，原子函数对 YOLO 实体放宽判定
        """
        if not yolo_entities:
            return rule_entities

        merged = list(rule_entities)
        added_ids = set()

        for yolo_ent in yolo_entities:  # 循环
            yolo_bbox = yolo_ent.bbox
            yolo_center_x = yolo_bbox["x"] + yolo_bbox["width"] / 2
            yolo_center_y = yolo_bbox["y"] + yolo_bbox["height"] / 2

            # 检查是否与规则实体重叠
            is_duplicate = False
            for rule_ent in rule_entities:  # 循环
                # 只检查同类型（room 可能被归为 wall，所以放宽限制）
                if yolo_ent.type == "room" and rule_ent.type not in ("room", "wall"):
                    continue  # 继续循环
                if yolo_ent.type == "corridor" and rule_ent.type != "corridor":
                    continue  # 继续循环

                rule_bbox = rule_ent.bbox
                # 检查 YOLO 中心点是否在规则实体的 bbox 内
                if (rule_bbox["x"] <= yolo_center_x <= rule_bbox["x"] + rule_bbox["width"] and
                    rule_bbox["y"] <= yolo_center_y <= rule_bbox["y"] + rule_bbox["height"]):
                    is_duplicate = True
                    break  # 跳出循环

                # 计算 IOU
                inter_x = max(0, min(yolo_bbox["x"] + yolo_bbox["width"], rule_bbox["x"] + rule_bbox["width"]) -
                                 max(yolo_bbox["x"], rule_bbox["x"]))
                inter_y = max(0, min(yolo_bbox["y"] + yolo_bbox["height"], rule_bbox["y"] + rule_bbox["height"]) -
                                 max(yolo_bbox["y"], rule_bbox["y"]))
                union = yolo_bbox["width"] * yolo_bbox["height"] + rule_bbox["width"] * rule_bbox["height"] - inter_x * inter_y
                iou = (inter_x * inter_y) / max(union, 1)
                if iou > 0.3:
                    is_duplicate = True
                    break  # 跳出循环

            if not is_duplicate and yolo_ent.id not in added_ids:
                # YOLO 实体标记检测来源，原子函数会据此放宽尺寸相关判定
                yolo_ent.properties["detection_source"] = "yolo"  # 操作
                # 对 YOLO 检测的 room 不设置 area 属性（bbox 映射不精确）
                if yolo_ent.type == "room":
                    yolo_ent.properties.pop("area", None)  # 操作
                merged.append(yolo_ent)
                added_ids.add(yolo_ent.id)

        return merged
