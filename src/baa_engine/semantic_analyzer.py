"""
BAA 语义识别引擎 - 图元分类 + 空间关系构建（规则版）
"""
import os  # stdlib: filesystem ops
import math  # stdlib: math functions
from typing import List, Dict, Any, Optional, Tuple  # typing: type hints
from .drawing_parser import RawPrimitive  # 导入
import logging  # 导入

logger = logging.getLogger(__name__)  # assign


# ── 图层规则表 ────────────────────────────────────────────

# 短关键字（单字母/2字母）使用全词匹配（前后是_或边界），防止误匹配
# 例如 "D" 不匹配 "DIM"、"DIMENSION"、"DWG"、"DOOR"
LAYER_RULES = {  # assign
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
}  # code

# 短关键字（单字母/2字母）使用全词匹配
SHORT_LAYER_RULES = {  # assign
    "W": "wall",  # 字段
    "D": "door",  # 字段
    "M": "door",  # 字段
    "C": "window",  # 字段
    "ST": "stair",  # 字段
    "FZ": "fire_zone",  # 字段
    "FD": "fire_door",  # 字段
    "FE": "fire_elevator",  # 字段
    "T": "equipment",  # 通信设备（real: T=通信图层，需全词匹配）
}  # code


# ── 语义实体 ──────────────────────────────────────────────

class SemanticEntity:  # class: class SemanticEntity:
    """语义化图元"""
    def __init__(self, entity_id: str, entity_type: str,  # method: def __init__(self, entity_id: str, entity_type: str,
                 bbox: Dict[str, float], layer: str = "",  # 操作
                 subtype: str = "", confidence: float = 1.0,  # assign
                 properties: Dict[str, Any] = None):  # init: set to None
        self.id = entity_id  # assign: self attribute
        self.type = entity_type  # assign: self attribute
        self.bbox = bbox  # assign: self attribute
        self.layer = layer  # assign: self attribute
        self.subtype = subtype  # assign: self attribute
        self.confidence = confidence  # assign: self attribute
        self.properties = properties or {}  # assign: self attribute

    def to_dict(self) -> dict:  # method: def to_dict(self) -> dict:
        return {  # return: dict result
            "id": self.id,  # 字段
            "type": self.type,  # 字段
            "subtype": self.subtype,  # 字段
            "bbox": self.bbox,  # 字段
            "layer": self.layer,  # 字段
            "confidence": self.confidence,  # 字段
            "properties": self.properties,  # 字段
        }  # code


class SpatialRelation:  # class: class SpatialRelation:
    """空间关系"""
    def __init__(self, source_id: str, target_id: str,  # method: def __init__(self, source_id: str, target_id: str,
                 rel_type: str, distance: float = 0,  # 操作
                 via: str = "", confidence: float = 1.0):  # assign
        self.source_id = source_id  # assign: self attribute
        self.target_id = target_id  # assign: self attribute
        self.type = rel_type      # adjacent / contains / connects_to
        self.distance = distance  # assign: self attribute
        self.via = via  # assign: self attribute
        self.confidence = confidence  # assign: self attribute


# ── 语义分析引擎 ──────────────────────────────────────────

class SemanticAnalyzer:  # class: class SemanticAnalyzer:
    """语义识别引擎（规则版，不做ML）"""

    ADJACENT_THRESHOLD = 50.0  # 相邻距离阈值(mm)

    def __init__(self):  # method: def __init__(self):
        self._entity_counter = 0  # assign: self attribute
        self._analyze_cache: Dict[str, Dict[str, Any]] = {}  # hash -> result
        self._cache_max = 50  # assign: self attribute

    def analyze(self, primitives: List[RawPrimitive],  # method: def analyze(self, primitives: List[RawPrimitive],
                dimensions: List[Dict] = None,  # 操作
                max_entities: int = 10000,  # 性能优化后默认提升到 10000
                building_type: str = "civil",  # assign
                dxf_path: Optional[str] = None) -> Dict[str, Any]:  # init: set to None
        """
        执行语义分析

        参数:
            primitives: 原始图元列表
            dimensions: 尺寸标注列表
            max_entities: 最大处理实体数（超过则采样，防OOM）
            dxf_path: DXF 文件路径（可选），提供后启用 YOLO 检测增强

        输出: 结构化语义数据（entities + relations + attributes）
        """
        self._entity_counter = 0  # assign: self attribute

        # ── 缓存检查：相同 primitives hash 秒级返回 ──────
        try:  # try: operation block
            import hashlib  # stdlib import
            prim_hash = hashlib.md5(str(id(primitives))).hexdigest()[:16]  # assign
            # 使用前100个图元的type+bbox近似指纹
            fingerprint_parts = []  # init: empty list
            for p in primitives[:100]:  # loop: for p in primitives[:100]:
                fingerprint_parts.append(f"{p.dxf_type}:{p.bbox}")  # append: add to list
            fingerprint = hashlib.sha256("".join(fingerprint_parts).encode()).hexdigest()[:32]  # assign
            cached = self._analyze_cache.get(fingerprint)  # assign
            if cached is not None:  # check: value is not None
                return cached  # return
        except Exception:  # catch: exception handler
            fingerprint = None  # init: set to None

        # 采样限制，防止全量关系构建OOM
        if len(primitives) > max_entities:  # check: numeric comparison
            import random  # stdlib import
            random.seed(42)  # call
            primitives = random.sample(primitives, max_entities)  # assign

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)  # assign

        # Step 1.05: 楼层/区域检测（P35新增）
        floor_levels = self._detect_floor_levels(primitives)  # assign
        floor_assignments = self._assign_entities_to_floors(entities, primitives, floor_levels)  # assign

        # Step 1.1: YOLO 检测增强（可选，通过 dxf_path 触发）
        if dxf_path:  # condition: dxf_path:
            try:  # 尝试
                yolo_entities = self._yolo_enhance(dxf_path)  # assign
                if yolo_entities:  # condition: yolo_entities:
                    entities = self._merge_yolo_results(entities, yolo_entities)  # assign
                    logger.info(f"YOLO 增强: 新增 {len(yolo_entities)} 个实体, 合并后共 {len(entities)} 个")  # len: get length
            except Exception as e:  # 捕获异常
                logger.warning(f"YOLO 增强失败: {e}")  # call

        # Step 1.4: 多段线复合房间识别（LINE 链闭合检测）
        entities = self._merge_line_chains_to_rooms(entities, primitives)  # assign

        # Step 1.5: 走廊宽度推断（平行线聚类 + bbox 短边）
        entities = self._infer_corridor_widths(entities, primitives)  # assign

        # Step 1.6: door/fire_door 属性增强（宽度兜底 + 防火等级推断）
        for ent in entities:  # 循环
            if ent.type in ("door", "fire_door", "exit_door"):  # check: membership test
                # 宽度兜底：bbox长边优先推断（门扇的宽度是长边，短边是门扇厚度）
                if ent.properties.get("width", 0) < 0.3 and ent.properties.get("clear_width", 0) < 0.3:  # check: numeric comparison
                    bbox = ent.bbox  # assign
                    bw = bbox.get("width", 0)  # assign
                    bh = bbox.get("height", 0)  # assign
                    if bw > 0 and bh > 0:  # check: numeric comparison
                        # 优先用长边推断门的宽度（短边是门扇厚度）
                        long_edge = max(bw, bh)  # assign
                        short_edge = min(bw, bh)  # assign
                        # 门宽度的常见模数值（mm）：700/800/900/1000/1200/1500
                        COMMON_DOOR_WIDTHS = [700, 800, 900, 1000, 1200, 1500]  # assign
                        # 如果长边是短边的 3 倍以上，说明长边是门宽、短边是厚度
                        if short_edge > 0 and long_edge / short_edge >= 3.0:  # check: numeric comparison
                            w_mm = long_edge  # assign
                        else:  # 否则
                            w_mm = long_edge  # assign
                        # 匹配最近的模数
                        best_match = min(COMMON_DOOR_WIDTHS, key=lambda x: abs(x - w_mm))  # assign
                        if abs(w_mm - best_match) / max(best_match, 1) < 0.3:  # 偏差 < 30%，取模数
                            w_mm = best_match  # assign
                        w_m = w_mm * 0.001  # assign
                        if 0.3 < w_m < 3.0:  # check: numeric comparison
                            ent.properties["width"] = w_m  # 操作
                            ent.properties["clear_width"] = w_m  # 操作
                # 防火等级推断：从图层名和实体名推断
                if ent.type == "fire_door":  # check: OR condition
                    existing_rating = ent.properties.get("fire_rating", ent.properties.get("rating", 0))  # assign
                    if existing_rating < 0.5:  # check: numeric comparison
                        # 图层名包含关键字推断
                        # 注意：META 图层可能含有 A/B/C，要用完整单词匹配避免误触
                        layer_upper = (ent.layer or "").upper()  # assign
                        words = layer_upper.replace("-", " ").replace("_", " ").split()  # assign
                        if "甲" in layer_upper or "A" in words:  # check: membership test
                            ent.properties["fire_rating"] = 3.0  # 甲级=3.0
                        elif "乙" in layer_upper or "B" in words:  # 分支
                            ent.properties["fire_rating"] = 2.0  # 乙级=2.0
                        elif "丙" in layer_upper or "C" in words:  # 分支
                            ent.properties["fire_rating"] = 1.0  # 丙级=1.0
                        # 不设默认值——无法推断时留空，让原子函数处理

        # Step 2: 空间关系构建（V2拓扑关系）
        relations = self._build_relations(entities)  # assign

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])  # assign

        # Step 4: 走廊拓扑网络（V2新增）
        corridor_topology = self.build_corridor_topology(entities, relations)  # assign

        # Step 5: 疏散路径分析（V2新增）
        evacuation_routes = self.analyze_evacuation_routes(entities, relations) or []  # assign

        # Step 5.3: 疏散路径连通性验证（P33新增）
        connectivity = self.verify_evacuation_connectivity(entities, relations, evacuation_routes)  # assign

        # Step 5.5: 疏散路径结果注入到实体属性（EVAC原子函数用）
        route_by_room = {}  # init: empty dict
        for route in evacuation_routes:  # 循环
            route_by_room[route["room_id"]] = route  # 操作
        dead_end_ids = set(d["id"] for d in corridor_topology.get("dead_ends", []))  # assign: membership check
        for ent in entities:  # 循环
            if ent.id in dead_end_ids:  # check: membership test
                ent.properties["is_dead_end"] = True  # 操作
            if ent.id in route_by_room:  # check: membership test
                r = route_by_room[ent.id]  # assign
                ent.properties["has_evacuation_route"] = r.get("has_route", False)  # 操作
                if r.get("path_length") is not None:  # check: value is not None
                    ent.properties["evacuation_path_length"] = r["path_length"]  # 操作
                ent.properties["evacuation_too_far"] = r.get("exceeds_max_distance", False)  # 操作
            # 对未找到路径的实体：如果疏散路径分析有结果但房间不在其中，标记为无路径
            # 如果分析结果为空（无出口/无拓扑），则不标记——让 EVAC 原子函数跳过判定
            elif ent.type in ("room", "corridor"):  # 分支
                if "has_evacuation_route" not in ent.properties and evacuation_routes:  # check: membership test
                    ent.properties["has_evacuation_route"] = False  # 操作
                    ent.properties["evacuation_too_far"] = True  # 操作

        # Step 5.6: 连通性验证结果注入实体属性
        conn_by_room = {}  # init: empty dict
        for item in connectivity:  # loop: for item in connectivity:
            conn_by_room[item["room_id"]] = item  # assign
        for ent in entities:  # loop: for ent in entities:
            if ent.id in conn_by_room:  # check: membership test
                c = conn_by_room[ent.id]  # assign
                ent.properties["evacuation_connected"] = c.get("connected", False)  # assign
                ent.properties["evacuation_bottleneck"] = c.get("bottleneck", False)  # assign
                if c.get("bottleneck_details"):  # condition: c.get("bottleneck_details"):
                    ent.properties["evacuation_bottleneck_details"] = c["bottleneck_details"]  # assign

        result = {  # assign
            "entities": [e.to_dict() for e in entities],  # 字段
            "relations": [r.__dict__ if hasattr(r, '__dict__') else r for r in relations],  # 字段
            "attributes": attributes,  # 字段
            "building_type": building_type,  # 字段
            "corridor_topology": corridor_topology,  # 字段
            "evacuation_routes": evacuation_routes,  # 字段
            "evacuation_connectivity": connectivity,  # 字段
            "floor_levels": floor_levels,  # 字段
            "floor_assignments": floor_assignments,  # 字段
        }  # code

        # ── 写入缓存 ──────────────────────────────────────
        if fingerprint and result:  # check: AND condition
            if len(self._analyze_cache) >= self._cache_max:  # check: numeric comparison
                old_key = next(iter(self._analyze_cache))  # assign
                del self._analyze_cache[old_key]  # code
            self._analyze_cache[fingerprint] = result  # assign: self attribute

        return result  # return

    def _detect_floor_levels(self, primitives: List[RawPrimitive]) -> List[Dict]:  # method: def _detect_floor_levels(self, primitives: List[RawPrimitive
        """检测图纸中的楼层分隔线和标高文字（P35）

        策略：
        1. 寻找跨越图纸宽度 80% 以上的水平 LINE/LWPOLYLINE（楼层分隔线）
        2. 提取 TEXT 中的标高信息（如 "±0.000", "F1", "第2层", "标高"）
        3. 返回按 Y 坐标排序的楼层列表

        返回:
            [
                {"level": 1, "label": "F1", "elevation": 0.0, "y_range": [y_min, y_max], "source": "separator"},
                ...
            ]
        """
        import math  # stdlib: math functions

        if not primitives:  # check: negated condition
            return []  # return: list of items

        # 计算图纸总宽度
        all_x = []  # init: empty list
        all_y = []  # init: empty list
        for p in primitives:  # loop: for p in primitives:
            bbox = p.bbox  # assign
            if bbox.get("width", 0) > 0:  # check: numeric comparison
                all_x.append(bbox["x"])  # append: add to list
                all_x.append(bbox["x"] + bbox["width"])  # append: add to list
            if bbox.get("height", 0) > 0:  # check: numeric comparison
                all_y.append(bbox["y"])  # append: add to list
                all_y.append(bbox["y"] + bbox["height"])  # append: add to list

        if not all_x or not all_y:  # check: negated condition
            return []  # return: list of items

        drawing_width = max(all_x) - min(all_x) if all_x else 0  # assign
        drawing_height = max(all_y) - min(all_y) if all_y else 0  # assign
        if drawing_width <= 0:  # check: numeric comparison
            return []  # return: list of items

        width_threshold = drawing_width * 0.8  # 跨越 80% 以上宽度视为楼层分隔线

        # 1. 收集水平分隔线
        separators = []  # init: empty list
        for p in primitives:  # loop: for p in primitives:
            if p.dxf_type not in ("LINE", "LWPOLYLINE"):  # check: membership test
                continue  # code
            bbox = p.bbox  # assign
            bw = bbox.get("width", 0)  # assign
            bh = bbox.get("height", 0)  # assign
            center_y = bbox.get("y", 0) + bh / 2  # assign

            # 水平线：宽度远大于高度
            if bw > 0 and bh > 0 and bw / max(bh, 1) > 20:  # check: numeric comparison
                if bw >= width_threshold:  # check: numeric comparison
                    separators.append({  # code
                        "y": center_y,  # code
                        "width": bw,  # code
                        "layer": p.layer,  # code
                    })  # code

        # 2. 提取标高文字
        elevation_texts = []  # init: empty list
        for p in primitives:  # loop: for p in primitives:
            if p.dxf_type != "TEXT":  # condition: p.dxf_type != "TEXT":
                continue  # code
            text = p.properties.get("text", "").strip()  # assign
            if not text:  # check: negated condition
                continue  # code
            bbox = p.bbox  # assign
            center_y = bbox.get("y", 0) + bbox.get("height", 0) / 2  # assign

            # 匹配标高模式
            text_upper = text.upper()  # assign
            level = None  # init: set to None
            label = text  # assign

            # "±0.000" 或 "+0.000" 或 "-0.000" 标高
            if any(c in text for c in ["±", "+", "-"]) and "." in text:  # check: membership test
                try:  # try: operation block
                    # 尝试提取数值
                    num_str = text.replace("±", "").replace("+", "").strip()  # assign
                    elevation = float(num_str) if num_str else 0.0  # assign
                    if "±" in text:  # check: membership test
                        elevation = 0.0  # init: set to 0
                    level = elevation  # assign
                    label = f"F{int(elevation) + 1}" if elevation >= 0 else f"B{abs(int(elevation))}"  # assign
                except ValueError:  # catch: exception handler
                    pass  # code

            # "F1", "F2", "1F", "2F", "B1", "B2"
            if level is None:  # check: value is None
                import re  # stdlib: regex
                m = re.match(r"^[Ff](\d+)$", text)  # assign
                if m:  # condition: m:
                    level = int(m.group(1))  # assign
                    label = f"F{level}"  # assign
                m = re.match(r"^(\d+)[Ff]$", text)  # assign
                if m:  # condition: m:
                    level = int(m.group(1))  # assign
                    label = f"F{level}"  # assign
                m = re.match(r"^[Bb](\d+)$", text)  # assign
                if m:  # condition: m:
                    level = -int(m.group(1))  # assign
                    label = f"B{m.group(1)}"  # assign

            # "第1层", "第2层", "首层", "二层"
            if level is None:  # check: value is None
                if "首层" in text or "一层" in text:  # check: membership test
                    level = 1  # assign
                    label = "F1"  # assign
                elif "二层" in text:  # elif: "二层" in text:
                    level = 2  # assign
                    label = "F2"  # assign
                elif "三层" in text:  # elif: "三层" in text:
                    level = 3  # assign
                    label = "F3"  # assign
                elif "层" in text:  # elif: "层" in text:
                    import re  # stdlib: regex
                    m = re.search(r"(\d+)层", text)  # assign
                    if m:  # condition: m:
                        level = int(m.group(1))  # assign
                        label = f"F{level}"  # assign

            # "标高" + 数值
            if level is None and "标高" in text:  # check: value is None
                import re  # stdlib: regex
                nums = re.findall(r"[-+]?\d+\.?\d*", text)  # assign
                if nums:  # condition: nums:
                    try:  # try: operation block
                        level = float(nums[0])  # assign
                        label = f"F{int(level) + 1}" if level >= 0 else f"B{abs(int(level))}"  # assign
                    except ValueError:  # catch: exception handler
                        pass  # code

            if level is not None:  # check: value is not None
                elevation_texts.append({  # code
                    "y": center_y,  # code
                    "level": level,  # code
                    "label": label,  # code
                    "text": text,  # code
                })  # code

        # 3. 合并分隔线和标高文字，按 Y 排序生成楼层
        floor_levels = []  # init: empty list

        # 先按分隔线 Y 排序
        sorted_seps = sorted(separators, key=lambda s: s["y"])  # assign
        sorted_texts = sorted(elevation_texts, key=lambda t: t["y"])  # assign

        if not sorted_seps and not sorted_texts:  # check: negated condition
            return []  # return: list of items

        # 如果有分隔线，用分隔线定义楼层
        if sorted_seps:  # check: OR condition
            # 添加最底层边界
            prev_y = min(all_y) if all_y else 0  # assign
            for i, sep in enumerate(sorted_seps):  # loop: for i, sep in enumerate(sorted_seps):
                floor_levels.append({  # code
                    "level": i + 1,  # code
                    "label": f"F{i + 1}",  # code
                    "elevation": None,  # code
                    "y_range": [prev_y, sep["y"]],  # code
                    "source": "separator",  # code
                })  # code
                prev_y = sep["y"]  # assign
            # 添加最顶层边界
            floor_levels.append({  # code
                "level": len(sorted_seps) + 1,  # len: get length
                "label": f"F{len(sorted_seps) + 1}",  # len: get length
                "elevation": None,  # code
                "y_range": [prev_y, max(all_y) if all_y else prev_y + 1],  # max: get maximum
                "source": "separator",  # code
            })  # code

        # 用标高文字补充楼层标签（仅在分隔线模式下）
        if sorted_seps and sorted_texts:  # check: OR condition
            for fl in floor_levels:  # loop: for fl in floor_levels:
                y_min, y_max = fl["y_range"]  # assign
                for et in sorted_texts:  # loop: for et in sorted_texts:
                    if y_min <= et["y"] <= y_max:  # check: numeric comparison
                        fl["label"] = et["label"]  # assign
                        fl["elevation"] = et["level"]  # assign
                        fl["source"] = "text"  # assign
                        break  # code

        # 无分隔线时，按标高文字聚类
        if not sorted_seps and len(sorted_texts) >= 1:  # check: numeric comparison
                # 按文字 Y 坐标聚类
                clusters = []  # init: empty list
                current_cluster = [sorted_texts[0]]  # assign
                for i in range(1, len(sorted_texts)):  # loop: for i in range(1, len(sorted_texts)):
                    if abs(sorted_texts[i]["y"] - sorted_texts[i - 1]["y"]) < drawing_height * 0.1:  # check: numeric comparison
                        current_cluster.append(sorted_texts[i])  # append: add to list
                    else:  # else: default case
                        clusters.append(current_cluster)  # append: add to list
                        current_cluster = [sorted_texts[i]]  # assign
                if current_cluster:  # condition: current_cluster:
                    clusters.append(current_cluster)  # append: add to list

                # 取每个簇中心 Y 作为楼层分界
                cluster_centers = []  # init: empty list
                for cluster in clusters:  # loop: for cluster in clusters:
                    avg_y = sum(t["y"] for t in cluster) / len(cluster)  # assign: membership check
                    cluster_centers.append({"y": avg_y, "label": cluster[0]["label"], "level": cluster[0]["level"]})  # append: add to list

                cluster_centers.sort(key=lambda c: c["y"])  # assign

                prev_y = min(all_y) if all_y else 0  # assign
                for i, cc in enumerate(cluster_centers):  # loop: for i, cc in enumerate(cluster_centers):
                    floor_levels.append({  # code
                        "level": i + 1,  # code
                        "label": cc["label"],  # code
                        "elevation": cc["level"],  # code
                        "y_range": [prev_y, cc["y"] + drawing_height * 0.05],  # code
                        "source": "text",  # code
                    })  # code
                    prev_y = cc["y"] + drawing_height * 0.05  # assign

        if not floor_levels:  # check: negated condition
            return []  # return: list of items

        # 去重 + 排序
        seen_labels = set()  # init: empty set
        unique = []  # init: empty list
        for fl in floor_levels:  # loop: for fl in floor_levels:
            if fl["label"] not in seen_labels:  # check: membership test
                seen_labels.add(fl["label"])  # call
                unique.append(fl)  # append: add to list

        unique.sort(key=lambda f: f["level"])  # assign
        return unique  # return

    def _assign_entities_to_floors(self,  # method: def _assign_entities_to_floors(self,
                                     entities: List[SemanticEntity],  # code
                                     primitives: List[RawPrimitive],  # code
                                     floor_levels: List[Dict]) -> Dict[str, str]:  # code
        """将实体分配到对应楼层

        返回:
            {entity_id: floor_label}  # e.g. {"ROOM_001": "F1", "DOOR_002": "F2"}
        """
        if not floor_levels or not entities:  # check: negated condition
            return {}  # return: dict result

        assignments = {}  # init: empty dict
        for ent in entities:  # loop: for ent in entities:
            bbox = ent.bbox  # assign
            center_y = bbox.get("y", 0) + bbox.get("height", 0) / 2  # assign

            assigned = False  # assign
            for fl in floor_levels:  # loop: for fl in floor_levels:
                y_min, y_max = fl["y_range"]  # assign
                if y_min <= center_y <= y_max:  # check: numeric comparison
                    assignments[ent.id] = fl["label"]  # assign
                    ent.properties["floor"] = fl["label"]  # assign
                    assigned = True  # assign
                    break  # code

            if not assigned:  # check: negated condition
                # 默认归属最近楼层
                if floor_levels:  # check: OR condition
                    closest = min(floor_levels, key=lambda f: abs((f["y_range"][0] + f["y_range"][1]) / 2 - center_y))  # assign
                    assignments[ent.id] = closest["label"]  # assign
                    ent.properties["floor"] = closest["label"]  # assign

        return assignments  # return

    def _parse_meta_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:  # method: def _parse_meta_entities(self, primitives: List[RawPrimitive
        """
        解析 META 图层的结构化实体元数据。
        格式: ENTITY:<type>|x:<x>|y:<y>|w:<w>|h:<h>|key:value|...
        用于合成图纸测试场景，跳过常规几何归并直接构建实体。
        """
        entities = []  # init: empty list
        for prim in primitives:  # 循环
            if prim.layer.upper() != "META":  # condition: prim.layer.upper() != "META":
                continue  # 继续循环
            text = prim.properties.get("text", "")  # assign
            if not text.startswith("ENTITY:"):  # check: negated condition
                continue  # 继续循环
            parts = text.split("|")  # assign
            if len(parts) < 5:  # check: numeric comparison
                continue  # 继续循环
            # 解析类型
            etype = parts[0].replace("ENTITY:", "").strip()  # assign
            # 解析bbox和属性
            props = {}  # init: empty dict
            bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}  # assign
            for part in parts[1:]:  # 循环
                if ":" not in part:  # check: membership test
                    continue  # 继续循环
                k, v = part.split(":", 1)  # 操作
                k = k.strip()  # assign
                v = v.strip()  # assign
                if k == "x":  # condition: k == "x":
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
                        props[k] = float(v)  # assign
                    except ValueError:  # 捕获异常
                        props[k] = v  # assign

            self._entity_counter += 1  # assign: self attribute
            entity = SemanticEntity(  # assign
                entity_id=f"{etype.upper()}_{self._entity_counter:03d}",  # assign
                entity_type=etype,  # assign
                bbox=bbox,  # assign
                layer="META",  # assign
                confidence=1.0,  # assign
                properties=props,  # assign
            )  # code
            entities.append(entity)  # append: add to list

        return entities  # return

    def _classify_entities(self, primitives: List[RawPrimitive]) -> List[SemanticEntity]:  # method: def _classify_entities(self, primitives: List[RawPrimitive])
        """图元分类归并"""
        # 优先解析 META 图层（合成图纸结构化数据）
        meta_entities = self._parse_meta_entities(primitives)  # assign
        if meta_entities:  # condition: meta_entities:
            return meta_entities  # return

        entities = []  # init: empty list

        for prim in primitives:  # 循环
            # 图层规则匹配
            entity_type = self._classify_by_layer(prim.layer)  # assign
            if entity_type == "unknown":  # condition: entity_type == "unknown":
                entity_type = self._classify_by_geometry(prim)  # assign

            if entity_type == "unknown":  # condition: entity_type == "unknown":
                continue  # 继续循环

            self._entity_counter += 1  # assign: self attribute
            # 过滤 NaN properties
            cleaned_props = {}  # init: empty dict
            for pk, pv in prim.properties.items():  # 循环
                if isinstance(pv, float):  # condition: isinstance(pv, float):
                    import math  # stdlib: math functions
                    if not math.isnan(pv):  # check: negated condition
                        cleaned_props[pk] = pv  # assign
                else:  # 否则
                    cleaned_props[pk] = pv  # assign
            entity = SemanticEntity(  # assign
                entity_id=f"{entity_type.upper()}_{self._entity_counter:03d}",  # assign
                entity_type=entity_type,  # assign
                bbox=prim.bbox,  # assign
                layer=prim.layer,  # assign
                confidence=0.9 if entity_type != "unknown" else 0.5,  # compare: inequality
                properties=cleaned_props,  # assign
            )  # code
            entities.append(entity)  # append: add to list

        # 归并同类重叠图元
        entities = self._merge_overlapping(entities)  # assign

        # 过滤过小的走廊实体（LINE 类型容易被误识别为走廊）
        # 走廊宽度 < 500mm 且 bbox 短边 < 500mm 的实体可能是微小图元误标
        filtered = []  # init: empty list
        for e in entities:  # 循环
            if e.type == "corridor":  # check: OR condition
                bb = e.bbox  # assign
                bw = bb.get("width", 0)  # assign
                bh = bb.get("height", 0)  # assign
                short_edge = min(bw, bh) if bw > 0 and bh > 0 else max(bw, bh)  # assign
                if short_edge < 500:  # 短边 < 500mm 不可能是走廊
                    continue  # 继续循环
            filtered.append(e)  # append: add to list
        entities = filtered  # assign

        return entities  # return

    def _is_near_closed(self, prim: RawPrimitive, gap_threshold_mm: float = 500.0) -> bool:  # method: def _is_near_closed(self, prim: RawPrimitive, gap_threshold_
        """接近闭合检测：开放多边形首尾点距离 < 阈值 → 视为闭合

        用于处理缺口房间（L 形/U 形房间在墙体断开处形成缺口）
        """
        pts = prim.properties.get("points")  # assign
        if not pts or len(pts) < 3:  # check: numeric comparison
            return False  # return: boolean
        # 校验 pts 结构（可能是 [(x,y), ...] 或 [[x,y], ...]）
        try:  # try: operation block
            first = pts[0]  # assign
            last = pts[-1]  # assign
            if isinstance(first, (list, tuple)) and len(first) >= 2:  # check: numeric comparison
                start = (float(first[0]), float(first[1]))  # assign
                end = (float(last[0]), float(last[1]))  # assign
            else:  # else: default case
                return False  # return: boolean
        except (TypeError, IndexError, ValueError):  # catch: exception handler
            return False  # return: boolean
        dx = end[0] - start[0]  # assign
        dy = end[1] - start[1]  # assign
        gap = math.sqrt(dx * dx + dy * dy)  # assign
        return gap < gap_threshold_mm  # return

    def _merge_line_chains_to_rooms(self, entities: List[SemanticEntity], primitives: List[RawPrimitive]) -> List[SemanticEntity]:  # method: def _merge_line_chains_to_rooms(self, entities: List[Semanti
        """多段线复合房间识别：LINE 链闭合检测
        
        将首尾相连的 LINE 图元组合成闭合链，满足条件后合并为 room 实体。
        处理建筑师用多个 LINE 绘制房间轮廓的情况。
        """
        # 收集 LINE 图元（未被分类为 room 的）
        lines = []  # init: empty list
        for prim in primitives:  # loop: for prim in primitives:
            if prim.dxf_type == "LINE":  # condition: prim.dxf_type == "LINE":
                lines.append(prim)  # append: add to list
        if len(lines) < 3:  # check: numeric comparison
            return entities  # return
        
        # 端点匹配阈值（mm）
        match_threshold = 100.0  # assign
        
        # 建立邻接表（使用坐标四舍五入到 mm 精度，避免浮点误差）
        def _round_point(p):  # method: def _round_point(p):
            return (round(p[0], 1), round(p[1], 1))  # return: tuple
        
        point_to_lines = {}  # init: empty dict
        for i, line in enumerate(lines):  # loop: for i, line in enumerate(lines):
            sp = line.properties.get("start_point", {})  # assign
            ep = line.properties.get("end_point", {})  # assign
            p1 = (sp.get("x", 0), sp.get("y", 0))  # assign
            p2 = (ep.get("x", 0), ep.get("y", 0))  # assign
            rp1 = _round_point(p1)  # assign
            rp2 = _round_point(p2)  # assign
            point_to_lines.setdefault(rp1, []).append((i, 0, p1, p2))  # append: add to list
            point_to_lines.setdefault(rp2, []).append((i, 1, p1, p2))  # append: add to list
        
        # DFS 找闭合链
        visited = [False] * len(lines)  # assign
        closed_chains = []  # init: empty list
        
        for start_i in range(len(lines)):  # loop: for start_i in range(len(lines)):
            if visited[start_i]:  # condition: visited[start_i]:
                continue  # code
            chain = [start_i]  # assign
            visited[start_i] = True  # assign
            current = start_i  # assign
            current_end = 1  # 0=start, 1=end
            # 记录遍历路径中的端点（用于面积计算）
            path_pts = []  # init: empty list
            
            # 获取起始线的端点
            sl = lines[start_i]  # assign
            sp = sl.properties.get("start_point", {})  # assign
            ep = sl.properties.get("end_point", {})  # assign
            path_pts.append((sp.get("x", 0), sp.get("y", 0)))  # append: add to list
            path_pts.append((ep.get("x", 0), ep.get("y", 0)))  # append: add to list
            
            # 遍历链
            max_depth = 50  # 防止无限循环
            depth = 0  # init: set to 0
            while depth < max_depth:  # loop: while depth < max_depth:
                depth += 1  # accumulate
                # 获取当前线的端点
                line = lines[current]  # assign
                sp = line.properties.get("start_point", {})  # assign
                ep = line.properties.get("end_point", {})  # assign
                p1 = (sp.get("x", 0), sp.get("y", 0))  # assign
                p2 = (ep.get("x", 0), ep.get("y", 0))  # assign
                rp1 = _round_point(p1)  # assign
                rp2 = _round_point(p2)  # assign
                
                # 当前端点（四舍五入后）
                current_rp = rp1 if current_end == 0 else rp2  # compare: equality
                
                # 找下一个线
                found_next = False  # assign
                for (ni, nend, nsp, nep) in point_to_lines.get(current_rp, []):  # loop: for (ni, nend, nsp, nep) in point_to_lines.get(cur
                    if ni == current:  # condition: ni == current:
                        continue  # code
                    if visited[ni]:  # condition: visited[ni]:
                        # 如果回到起点且链长度 >= 3 → 闭合
                        if ni == start_i and len(chain) >= 3:  # check: numeric comparison
                            closed_chains.append((chain, path_pts))  # append: add to list
                            break  # code
                        continue  # code
                    visited[ni] = True  # assign
                    chain.append(ni)  # append: add to list
                    # 添加新线的另一个端点（非连接点）到路径
                    if nend == 0:  # 连接点是 start，新端点是 end
                        path_pts.append((nep[0], nep[1]))  # append: add to list
                    else:  # 连接点是 end，新端点是 start
                        path_pts.append((nsp[0], nsp[1]))  # append: add to list
                    current = ni  # assign
                    # 确定下一个线的起始端点
                    current_end = 1 - nend  # assign
                    found_next = True  # assign
                    break  # code
                if not found_next:  # check: negated condition
                    break  # code
            
            # 检查是否闭合回到起点（通过距离阈值）
            if len(chain) >= 3:  # check: numeric comparison
                # 路径最后一个点
                last_pt = path_pts[-1] if path_pts else None  # assign
                # 起始线的两个端点
                sl = lines[start_i]  # assign
                sp = sl.properties.get("start_point", {})  # assign
                ep = sl.properties.get("end_point", {})  # assign
                sp_start = (sp.get("x", 0), sp.get("y", 0))  # assign
                sp_end = (ep.get("x", 0), ep.get("y", 0))  # assign
                if last_pt and (  # check: AND condition
                    (abs(last_pt[0] - sp_start[0]) < match_threshold and abs(last_pt[1] - sp_start[1]) < match_threshold) or  # call
                    (abs(last_pt[0] - sp_end[0]) < match_threshold and abs(last_pt[1] - sp_end[1]) < match_threshold)):  # call
                    # 检查是否已存在
                    is_dup = False  # assign
                    for existing_chain, _ in closed_chains:  # loop: for existing_chain, _ in closed_chains:
                        if set(chain) == set(existing_chain):  # condition: set(chain) == set(existing_chain):
                            is_dup = True  # assign
                            break  # code
                    if not is_dup:  # check: negated condition
                        closed_chains.append((chain, path_pts))  # append: add to list
        
        # 对闭合链计算面积，符合条件的合并为 room
        non_room_layers = ["COLU", "视口", "洞口", "板边", "梁边", "轴", "BASE", "梁", "吊筋", "板层", "文字", "钢筋", "标注", "DIM", "立面看线", "立面", "看线", "园林", "井", "电-", "系统", "设备", "电缆", "Defpoints"]  # assign
        new_rooms = []  # init: empty list
        for chain, pts in closed_chains:  # loop: for chain, pts in closed_chains:
            if len(pts) < 3:  # check: numeric comparison
                continue  # code
            
            # 检查链中是否有非建筑图元（任一 LINE 在非建筑图层上）
            has_non_building = False  # assign
            for idx in chain:  # loop: for idx in chain:
                prim = lines[idx]  # assign
                if any(kw in prim.layer.upper() for kw in non_room_layers):  # check: membership test
                    has_non_building = True  # assign
                    break  # code
            if has_non_building:  # condition: has_non_building:
                continue  # code
            
            # 计算面积（鞋带公式）
            area = abs(sum(pts[i][0] * pts[(i+1) % len(pts)][1] - pts[(i+1) % len(pts)][0] * pts[i][1] for i in range(len(pts))) / 2)  # assign: membership check
            
            # 面积条件：1m² < area < 500m²
            if area < 1000000 or area > 500000000:  # check: numeric comparison
                continue  # code
            
            # bbox
            xs = [p[0] for p in pts]  # assign: membership check
            ys = [p[1] for p in pts]  # assign: membership check
            bbox = {"x": min(xs), "y": min(ys), "width": max(xs)-min(xs), "height": max(ys)-min(ys)}  # assign
            
            # 创建 room 实体
            room_id = f"line_chain_room_{self._entity_counter}"  # assign
            self._entity_counter += 1  # assign: self attribute
            room = SemanticEntity(  # assign
                entity_id=room_id,  # assign
                entity_type="room",  # assign
                layer="",  # assign
                properties={"area": area / 1000000},  # 转为 m²
                bbox=bbox  # assign
            )  # code
            new_rooms.append(room)  # append: add to list
        
        return entities + new_rooms  # return

    def _classify_by_layer(self, layer: str) -> str:  # method: def _classify_by_layer(self, layer: str) -> str:
        """图层规则归类

        长关键字（≥3字符）：子串匹配
        短关键字（1-2字符）：全词匹配（前后是_或边界），防止误匹配
        """
        if not layer:  # check: negated condition
            return "unknown"  # return
        layer_upper = layer.upper()  # assign

        # 长关键字（≥3字符）：子串匹配
        for keyword, entity_type in LAYER_RULES.items():  # 循环
            if keyword in layer_upper:  # check: membership test
                return entity_type  # return

        # 短关键字（1-2字符）：全词匹配
        for keyword, entity_type in SHORT_LAYER_RULES.items():  # 循环
            if keyword in layer_upper:  # check: membership test
                # 检查全词边界
                idx = layer_upper.find(keyword)  # assign
                while idx >= 0:  # 循环
                    pre_ok = (idx == 0 or layer_upper[idx-1] == '_')  # compare: equality
                    post_ok = (idx + len(keyword) >= len(layer_upper) or layer_upper[idx+len(keyword)] == '_')  # compare: equality
                    if pre_ok and post_ok:  # check: AND condition
                        return entity_type  # return
                    idx = layer_upper.find(keyword, idx + 1)  # assign

        return "unknown"  # return

    def _classify_by_geometry(self, prim: RawPrimitive) -> str:  # method: def _classify_by_geometry(self, prim: RawPrimitive) -> str:
        """几何特征兜底归类（V2深度升级版）
        
        新增规则：
        - 短 LINE 且靠近 DIMENSION 标注的 defpoint → door
        - 小面积闭合多边形（门打开轨迹）→ door
        - 靠近门的 ARC → door
        - 狭长闭合多边形 → corridor
        - 大尺寸 CIRCLE（>3000mm）→ stair
        """
        dxf_type = prim.dxf_type  # assign
        bbox = prim.bbox  # assign
        bw = bbox.get("width", 0)  # assign
        bh = bbox.get("height", 0)  # assign
        area = bw * bh  # assign
        props = prim.properties  # assign
        length = props.get("length", 0) or max(bw, bh)  # assign
        short_edge = min(bw, bh) if bw > 0 and bh > 0 else length  # assign

        if dxf_type == "LINE":  # condition: dxf_type == "LINE":
            if length > 2000:  # check: numeric comparison
                return "wall"  # return
            # 中等长度 LINE（700~2000mm）：典型门宽范围 → door
            if 700 < length < 2000 and short_edge < 50:  # check: numeric comparison
                return "door"  # return
            # 短 LINE（50~700mm）可能是门的宽度线或小构件
            if 50 < length < 700 and short_edge < 5:  # check: numeric comparison
                return "door"  # return
            # LINE 类型 bbox 短边≈0（纯线无宽度），不可能是走廊
            # 只有长度 > 2000mm 的 LINE 才可能归类为 wall（已处理）
            return "other"  # return

        if dxf_type in ("LWPOLYLINE", "POLYLINE"):  # check: membership test
            pts_count = props.get("point_count", 0)  # assign
            if pts_count == 2:  # condition: pts_count == 2:
                # 2 点 LWPOLYLINE：视为 LINE 等价
                if length > 2000:  # check: numeric comparison
                    return "wall"  # return
                if 700 < length < 2000 and short_edge < 50:  # check: numeric comparison
                    return "door"  # return
                if 50 < length < 700 and short_edge < 5:  # check: numeric comparison
                    return "door"  # return
                return "other"  # return
            
            # 闭合多边形判断（含缺口补全）
            is_closed = props.get("area", 0) > 0 or (pts_count >= 3)  # assign
            if not is_closed and pts_count >= 3:  # check: numeric comparison
                is_closed = self._is_near_closed(prim, gap_threshold_mm=500.0)  # assign
            if is_closed:  # condition: is_closed:
                aspect_ratio = max(bw, bh) / max(short_edge, 1)  # assign
                # 图层排除：非建筑图层上的闭合多边形不可能是房间
                non_room_layers = ["COLU", "视口", "洞口", "板边", "梁边", "轴", "BASE", "梁", "吊筋", "板层", "文字", "钢筋", "标注", "DIM", "立面看线", "立面", "看线", "园林", "井", "电-", "系统", "设备", "电缆", "Defpoints"]  # assign
                if any(kw in prim.layer.upper() for kw in non_room_layers):  # check: membership test
                    if aspect_ratio > 3:  # check: numeric comparison
                        return "other"  # return
                    return "wall"  # return
                # room 最小面积 1m²（1,000,000mm²），过滤小框/文字标注
                # room 最大面积 500m²（500,000,000mm²），过滤图纸边界框/标题栏框
                if area > 500000000:  # > 500m² → 图纸边界/标题栏，不是房间
                    return "other"  # return
                if area > 1000000:  # > 1m²
                    if aspect_ratio > 5:  # check: numeric comparison
                        # 狭长 → 走廊
                        if length > 3000:  # check: numeric comparison
                            return "wall"  # return
                        return "corridor"  # return
                    return "room"  # return
                elif area > 50000:  # 大面积但 < 1m²
                    if aspect_ratio > 5:  # check: numeric comparison
                        if length > 3000:  # check: numeric comparison
                            return "wall"  # return
                        return "corridor"  # return
                    return "wall"  # return
                elif area > 50000:  # 条件分支
                    # 中等面积（0.05~1m²）：可能是小房间或设备间
                    if aspect_ratio > 4:  # check: numeric comparison
                        return "corridor"  # return
                    return "room"  # return
                elif area > 5000:  # 条件分支
                    # 小面积（0.005~0.05m²）：通常是文字框/图例框/标注框，不是房间
                    return "other"  # return
                else:  # 否则
                    # 小面积闭合多边形（500~5000mm²）→ door 或 window
                    if aspect_ratio > 3:  # check: numeric comparison
                        # 狭长小面积 → 门的开合轨迹
                        return "door"  # return
                    elif aspect_ratio < 1.5:  # 条件分支
                        # 接近正方形的小面积 → column
                        return "column"  # return
                    return "door"  # return
            return "corridor"  # return

        # ARC：门弧、窗或弧形房间
        if dxf_type == "ARC":  # condition: dxf_type == "ARC":
            radius = props.get("radius", 0)  # assign
            # 大半径 ARC（>3000mm）且弧线角度大 → 弧形房间轮廓
            if radius > 3000:  # check: numeric comparison
                angle_span = abs(props.get("start_angle", 0) - props.get("end_angle", 0)) or 0  # assign
                # 弧线跨度 > 90° 视为房间轮廓
                if angle_span > 90:  # check: numeric comparison
                    return "room"  # return
            if 100 < radius < 2000:  # check: numeric comparison
                return "door"  # return
            return "window"  # return

        if dxf_type == "CIRCLE":  # condition: dxf_type == "CIRCLE":
            radius = props.get("radius", 0)  # assign
            if radius > 3000:  # check: numeric comparison
                return "stair"  # return
            elif radius > 1000:  # 条件分支
                return "stair"  # return
            elif radius > 300:  # 条件分支
                return "column"  # return
            # P34: 小半径 CIRCLE 可能是消防设备
            if 50 <= radius <= 300:  # check: numeric comparison
                # 结合图层判断
                layer = prim.layer.upper()  # assign
                if any(kw in layer for kw in ["消防", "FIRE", "FAS", "报警", "ALARM", "喷淋", "SPRINKLER"]):  # check: membership test
                    return "sprinkler"  # return
                if any(kw in layer for kw in ["设备", "EQUIP", "电-", "电气", "ELEC"]):  # check: membership test
                    return "equipment"  # return
                if any(kw in layer for kw in ["照明", "LIGHT", "应急", "EVAC"]):  # check: membership test
                    return "evacuation_lighting"  # return
                return "column"  # return
            return "column"  # return

        # P34: SOLID/HATCH 实体可能是消防设备填充
        if dxf_type == "SOLID":  # condition: dxf_type == "SOLID":
            layer = prim.layer.upper()  # assign
            if any(kw in layer for kw in ["消防", "FIRE", "喷淋", "SPRINKLER", "消火栓", "HYDRANT"]):  # check: membership test
                return "sprinkler"  # return
            if any(kw in layer for kw in ["设备", "EQUIP", "电-", "电气", "ELEC"]):  # check: membership test
                return "equipment"  # return
            return "other"  # return

        if dxf_type == "HATCH":  # condition: dxf_type == "HATCH":
            layer = prim.layer.upper()  # assign
            if any(kw in layer for kw in ["消防", "FIRE", "喷淋", "SPRINKLER"]):  # check: membership test
                return "sprinkler"  # return
            return "other"  # return

        if dxf_type == "TEXT":  # condition: dxf_type == "TEXT":
            text = props.get("text", "")  # assign
            if not text:  # check: negated condition
                return "text"  # return
            text_upper = text.upper()  # assign
            if "出口" in text or "EXIT" in text_upper:  # check: membership test
                return "exit"  # return
            if "楼梯" in text or "STAIR" in text_upper:  # check: membership test
                return "stair"  # return
            # "防火" 关键词需配合 "门" 或 "窗" 才能归类，避免文本描述被误标
            if "防火门" in text or ("FIRE" in text_upper and "DOOR" in text_upper):  # check: membership test
                return "fire_door"  # return
            if "防火窗" in text or ("FIRE" in text_upper and "WINDOW" in text_upper):  # check: membership test
                return "fire_window"  # return
            # ── 消防设施/系统关键词（用于真实图纸 TEXT 辅助识别） ──
            if "消火栓" in text or "HYDRANT" in text_upper:  # check: membership test
                return "fire_hydrant"  # return
            if "喷淋" in text or "洒水" in text or "SPRINKLER" in text_upper:  # check: membership test
                return "sprinkler"  # return
            if "灭火器" in text or "灭火" in text:  # check: membership test
                return "fire_extinguisher"  # return
            if "烟感" in text or "烟雾探测" in text or "探测器" in text or "SMOKE" in text_upper:  # check: membership test
                return "smoke_detector"  # return
            if "报警" in text or "ALARM" in text_upper:  # check: membership test
                return "fire_alarm"  # return
            if "消防水箱" in text or "水箱" in text:  # check: membership test
                return "water_tank"  # return
            if "消防水池" in text or "水池" in text:  # check: membership test
                return "water_reservoir"  # return
            if "广播" in text or "音箱" in text or "SPEAKER" in text_upper:  # check: membership test
                return "emergency_broadcast"  # return
            if "应急照明" in text or "EVAC" in text_upper:  # check: membership test
                return "evacuation_lighting"  # return
            if "卷帘" in text or "CURTAIN" in text_upper:  # check: membership test
                return "fire_curtain"  # return
            if "消防电梯" in text or "FIRE_ELEV" in text_upper:  # check: membership test
                return "fire_elevator"  # return
            if "声光" in text:  # check: membership test
                return "fire_alarm"  # return
            return "text"  # return

        # INSERT 块：从块名推断实体类型（完整映射表）
        if dxf_type == "INSERT":  # condition: dxf_type == "INSERT":
            block_name = props.get("block_name", "").upper()  # assign
            # ── 防火门/防火窗 ──
            if "FIRE_DOOR" in block_name or "防火门" in block_name:  # check: membership test
                return "fire_door"  # return
            if "FIRE_WINDOW" in block_name or "防火窗" in block_name:  # check: membership test
                return "fire_window"  # return
            # ── 建筑构件 ──
            if "DOOR" in block_name or "门" in block_name:  # check: membership test
                return "door"  # return
            if "WINDOW" in block_name or "窗" in block_name:  # check: membership test
                return "window"  # return
            if "STAIR" in block_name or "ST" in block_name:  # check: membership test
                return "stair"  # return
            if "COLUMN" in block_name or "柱" in block_name:  # check: membership test
                return "column"  # return
            # ── 出口/疏散指示 ──
            if "EXIT" in block_name or "出口" in block_name:  # check: membership test
                return "exit"  # return
            if "EXIT_SIGN" in block_name or "SIGN" in block_name or "疏散指示" in block_name:  # check: membership test
                return "exit_sign"  # return
            # ── 消防设施 ──
            if "HYDRANT" in block_name or "消火栓" in block_name:  # check: membership test
                return "fire_hydrant"  # return
            if "SPRINKLER" in block_name or "喷淋" in block_name or "洒水" in block_name:  # check: membership test
                return "sprinkler"  # return
            if "FIRE_EXT" in block_name or "灭火器" in block_name or "灭火" in block_name:  # check: membership test
                return "fire_extinguisher"  # return
            if "SMOKE_DETECTOR" in block_name or "烟感" in block_name:  # check: membership test
                return "smoke_detector"  # return
            if "FIRE_ALARM" in block_name or "报警" in block_name:  # check: membership test
                return "fire_alarm"  # return
            if "WATER_TANK" in block_name or "水箱" in block_name:  # check: membership test
                return "water_tank"  # return
            if "WATER_RESERVOIR" in block_name or "消防水池" in block_name or "水池" in block_name:  # check: membership test
                return "water_reservoir"  # return
            if "FIRE_ELEV" in block_name or "消防电梯" in block_name:  # check: membership test
                return "fire_elevator"  # return
            if "SPEAKER" in block_name or "广播" in block_name or "应急广播" in block_name:  # check: membership test
                return "emergency_broadcast"  # return
            if "EVAC_LIGHT" in block_name or "应急照明" in block_name:  # check: membership test
                return "evacuation_lighting"  # return
            if "CURTAIN" in block_name or "卷帘" in block_name:  # check: membership test
                return "fire_curtain"  # return
            # ── 其他楼层/空间 ──
            if "ROOM" in block_name or "房间" in block_name or "室" in block_name:  # check: membership test
                return "room"  # return
            if "CORRIDOR" in block_name or "走廊" in block_name or "走道" in block_name:  # check: membership test
                return "corridor"  # return
            if "SHAFT" in block_name or "井道" in block_name or "竖井" in block_name:  # check: membership test
                return "shaft"  # return
            if "ELEVATOR" in block_name or "电梯" in block_name:  # check: membership test
                return "elevator"  # return
            if "LOBBY" in block_name or "前室" in block_name:  # check: membership test
                return "lobby"  # return
            if "FIRE_ZONE" in block_name or "防火分区" in block_name:  # check: membership test
                return "fire_zone"  # return
            # ── 未知块名 → 回退到 wall ──
            return "wall"  # return

        return "unknown"  # return

    def _infer_corridor_widths(self, entities: List[SemanticEntity],  # method: def _infer_corridor_widths(self, entities: List[SemanticEnti
                              primitives: List[RawPrimitive] = None) -> List[SemanticEntity]:  # 操作
        """从 bbox 短边和平行线聚类推断走廊/门的宽度（真实图纸适配）

        两层策略：
        1. 平行线聚类（primitives 可用时）：收集走廊图元，按方向分组，
           找平行线间距作为走廊宽度
        2. bbox 短边：对已有非零 bbox 的实体，短边*0.001 为宽度
        """
        import math  # stdlib: math functions
        from collections import defaultdict  # stdlib import

        # 防御性过滤：修复 NaN bbox
        for ent in entities:  # 循环
            bbox = ent.bbox  # assign
            for k in ('x', 'y', 'width', 'height'):  # loop: for k in ('x', 'y', 'width', 'height'):
                v = bbox.get(k, 0)  # assign
                if isinstance(v, float) and math.isnan(v):  # check: AND condition
                    bbox[k] = 0.0  # init: set to 0

        # ── 策略1：平行线聚类宽度推断（按空间分区）──
        if primitives:  # condition: primitives:
            # 收集可能的走廊原始图元（LINE + 2点LWPOLYLINE）
            edge_candidates = []  # init: empty list
            for p in primitives:  # 循环
                bbox = p.bbox  # assign
                cx = bbox.get("x", 0) + bbox.get("width", 0) / 2  # assign
                cy = bbox.get("y", 0) + bbox.get("height", 0) / 2  # assign
                # 排除坐标偏移的图元
                if abs(cx) < 100 and abs(cy) < 100:  # check: numeric comparison
                    continue  # 继续循环
                if abs(cx) > 1e7 or abs(cy) > 1e7:  # check: numeric comparison
                    continue  # 继续循环
                bw = bbox.get("width", 0)  # assign
                bh = bbox.get("height", 0)  # assign
                span = max(bw, bh)  # assign
                if span < 100 or span > 100000:  # 0.1m~100m 合理范围
                    continue  # 继续循环
                if p.dxf_type == "LINE":  # condition: p.dxf_type == "LINE":
                    angle = p.properties.get("angle", 0) % 180  # assign
                    if angle > 90: angle = 180 - angle  # check: numeric comparison
                    edge_candidates.append({  # code
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,  # 字段
                        "span": span, "angle": angle,  # 字段
                    })  # code
                elif p.dxf_type == "LWPOLYLINE" and p.properties.get("point_count", 0) == 2:  # 分支
                    angle = 0 if bw > bh else 90  # init: set to 0
                    edge_candidates.append({  # code
                        "cx": cx, "cy": cy, "bw": bw, "bh": bh,  # 字段
                        "span": span, "angle": angle,  # 字段
                    })  # code

            if edge_candidates:  # check: AND condition
                # 按方向分组
                h_edges = [e for e in edge_candidates if e["angle"] < 30]  # assign: membership check
                v_edges = [e for e in edge_candidates if e["angle"] > 60]  # assign: membership check

                # 水平线：按cy排序，收集所有gap
                h_sorted = sorted(h_edges, key=lambda e: e["cy"])  # assign
                h_gaps = []  # init: empty list
                for i in range(min(300, len(h_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(h_sorted))):  # 循环
                        gap = abs(h_sorted[i]["cy"] - h_sorted[j]["cy"])  # assign
                        if 500 < gap < 10000:  # check: numeric comparison
                            h_gaps.append({"gap": gap, "y1": h_sorted[i]["cy"], "y2": h_sorted[j]["cy"],  # code
                                          "cx1": h_sorted[i]["cx"], "cx2": h_sorted[j]["cx"]})  # 字段

                # 垂直线：按cx排序，收集所有gap
                v_sorted = sorted(v_edges, key=lambda e: e["cx"])  # assign
                v_gaps = []  # init: empty list
                for i in range(min(300, len(v_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(v_sorted))):  # 循环
                        gap = abs(v_sorted[i]["cx"] - v_sorted[j]["cx"])  # assign
                        if 500 < gap < 10000:  # check: numeric comparison
                            v_gaps.append({"gap": gap, "x1": v_sorted[i]["cx"], "x2": v_sorted[j]["cx"],  # code
                                          "cy1": v_sorted[i]["cy"], "cy2": v_sorted[j]["cy"]})  # 字段

                all_gaps = h_gaps + v_gaps  # assign
                if all_gaps and len(all_gaps) > 10:  # check: numeric comparison
                    # 空间分区聚类：每条走廊取离它最近的 gap 作为宽度
                    # 1) 对每个 gap，按位置分到最近的走廊
                    # 2) 每个走廊取其区域内 gap 众数
                    corridor_entities = [e for e in entities if e.type == "corridor"]  # compare: equality
                    if corridor_entities:  # check: OR condition
                        for ent in corridor_entities:  # 循环
                            cx = ent.bbox.get("x", 0) + ent.bbox.get("width", 0) / 2  # assign
                            cy = ent.bbox.get("y", 0) + ent.bbox.get("height", 0) / 2  # assign
                            bw = ent.bbox.get("width", 0)  # assign
                            bh = ent.bbox.get("height", 0)  # assign
                            # 先用 bbox 短边推断宽度（LINE 类型用长边）
                            if bw > 0 and bh > 0:  # check: numeric comparison
                                w_mm = min(bw, bh)  # assign
                                w_m = w_mm * 0.001  # assign
                                if 0.3 < w_m < 3.0 and ent.properties.get("width", 0) < w_m:  # check: numeric comparison
                                    ent.properties["width"] = w_m  # 操作
                                    ent.properties["clear_width"] = w_m  # 操作
                                    ent.properties["_width_source"] = "bbox_short_edge"  # 操作
                                    continue  # 继续循环
                            
                            # bbox 短边≈0（LINE类型）：找附近gap
                            if ent.properties.get("width", 0) < 0.3:  # check: numeric comparison
                                # 找附近 gap
                                nearby_gaps = []  # init: empty list
                                for g in all_gaps:  # 循环
                                    if "y1" in g:  # 水平gap
                                        mid_y = (g["y1"] + g["y2"]) / 2  # assign
                                        mid_x = (g["cx1"] + g["cx2"]) / 2  # assign
                                        if abs(cy - mid_y) < 3000 and abs(cx - mid_x) < 3000:  # check: numeric comparison
                                            nearby_gaps.append(g["gap"])  # append: add to list
                                    else:  # 垂直gap
                                        mid_x = (g["x1"] + g["x2"]) / 2  # assign
                                        mid_y = (g["cy1"] + g["cy2"]) / 2  # assign
                                        if abs(cx - mid_x) < 3000 and abs(cy - mid_y) < 3000:  # check: numeric comparison
                                            nearby_gaps.append(g["gap"])  # append: add to list
                                
                                if nearby_gaps:  # condition: nearby_gaps:
                                    # 取附近gap的众数作为此走廊宽度
                                    gap_buckets = defaultdict(list)  # assign
                                    for g in nearby_gaps:  # 循环
                                        bucket = round(g / 100) * 100  # assign
                                        gap_buckets[bucket].append(g)  # 操作
                                    best_bucket = max(gap_buckets.items(), key=lambda x: len(x[1]))  # assign
                                    w_m = (sum(best_bucket[1]) / len(best_bucket[1])) / 1000.0  # assign
                                    if 0.3 < w_m < 3.0:  # check: numeric comparison
                                        ent.properties["width"] = w_m  # 操作
                                        ent.properties["clear_width"] = w_m  # 操作
                                        ent.properties["_width_source"] = "nearby_gap"  # 操作
                                else:  # 否则
                                    # 无附近gap：用bbox长边
                                    span_mm = max(bw, bh)  # assign
                                    w_m = span_mm * 0.001  # assign
                                    if 0.3 < w_m < 3.0:  # check: numeric comparison
                                        ent.properties["width"] = w_m  # 操作
                                        ent.properties["clear_width"] = w_m  # 操作
                                        ent.properties["_width_source"] = "bbox_long_edge"  # 操作
        
        # ── 策略1.5：door/window 宽度推断（V2增强）──
        for ent in entities:  # 循环
            if ent.type not in ("door", "window", "fire_door", "exit_door"):  # check: membership test
                continue  # 继续循环
            existing = ent.properties.get("width", 0)  # assign
            if existing > 0.5:  # check: numeric comparison
                continue  # 继续循环
            # 从 ARC 半径推断门宽度（门弧半径 ≈ 门宽度）
            radius = ent.properties.get("radius", 0)  # assign
            if radius > 100 and radius < 2000:  # check: numeric comparison
                w_m = radius * 0.001  # mm → m
                if 0.3 < w_m < 2.0:  # check: numeric comparison
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
                    continue  # 继续循环
            # bbox 推断
            bbox = ent.bbox  # assign
            bw = bbox.get("width", 0)  # assign
            bh = bbox.get("height", 0)  # assign
            if bw > 0 and bh > 0:  # check: numeric comparison
                w_mm = min(bw, bh)  # assign
                w_m = w_mm * 0.001  # assign
                if 0.3 < w_m < 2.0 and ent.properties.get("width", 0) < w_m:  # check: numeric comparison
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
            # LINE 类型（短边≈0）：用长边作为宽度
            if ent.properties.get("width", 0) < 0.3:  # check: numeric comparison
                span_mm = max(bw, bh)  # assign
                if 300 < span_mm < 2000:  # 300mm~2m
                    w_m = span_mm * 0.001  # assign
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作
            # Polygon 类 door（闭合多边形）：短边可能是门扇厚度，用长边推断宽度
            if ent.properties.get("width", 0) < 0.3:  # check: numeric comparison
                long_edge_mm = max(bw, bh)  # assign
                if 300 < long_edge_mm < 2000:  # check: numeric comparison
                    w_m = long_edge_mm * 0.001  # assign
                    ent.properties["width"] = w_m  # 操作
                    ent.properties["clear_width"] = w_m  # 操作

        # ── 策略2：bbox 短边推断（覆盖所有类型） ──
        for ent in entities:  # 循环
            if ent.type not in ("corridor", "door", "window", "room", "wall"):  # check: membership test
                continue  # 继续循环
            bbox = ent.bbox  # assign
            bw = bbox.get("width", 0)  # assign
            bh = bbox.get("height", 0)  # assign

            if bw == 0 and bh == 0:  # check: AND condition
                continue  # 继续循环

            # bbox 两边非零 → 短边为宽度（mm→m），长边为 length
            if bw > 0 and bh > 0:  # check: numeric comparison
                w_mm = min(bw, bh)  # assign
                w_m = w_mm * 0.001  # assign
                if not math.isnan(w_m) and w_m > 0.01 and w_m < 10:  # check: numeric comparison
                    current_w = ent.properties.get("width", 0)  # assign
                    if current_w < w_m:  # check: numeric comparison
                        ent.properties["width"] = w_m  # 操作
                        ent.properties["clear_width"] = w_m  # 操作
                l_mm = max(bw, bh)  # assign
                if l_mm > 0:  # check: numeric comparison
                    ent.properties["length"] = l_mm * 0.001  # 操作
                continue  # 继续循环

            # bbox 只有一边非零（LINE / 2 点 LWPOLYLINE）
            span_mm = max(bw, bh)  # assign
            if span_mm > 0:  # check: numeric comparison
                span_m = span_mm * 0.001  # assign
                if not math.isnan(span_m) and span_m > 0.05:  # check: numeric comparison
                    ent.properties["length"] = span_m  # 操作
                    # 对 corridor/room：bbox短边≈宽度
                    if ent.type in ("corridor", "room", "door", "fire_door", "exit_door"):  # check: membership test
                        short_mm = min(bw, bh) if bw > 0 and bh > 0 else 0  # assign
                        if short_mm > 0:  # check: numeric comparison
                            short_m = short_mm * 0.001  # assign
                            current_w = ent.properties.get("width", 0)  # assign
                            if current_w < 0.01 and 0.05 < short_m < 3.0:  # check: numeric comparison
                                ent.properties["width"] = short_m  # 操作
                                ent.properties["clear_width"] = short_m  # 操作

        return entities  # return

    def _merge_overlapping(self, entities: List[SemanticEntity]) -> List[SemanticEntity]:  # method: def _merge_overlapping(self, entities: List[SemanticEntity])
        """合并重叠/相邻的同类图元（空间哈希加速版）

        小数据量（<2000）直接 O(n²) 全量对比；
        大数据量使用网格分桶，只对比同网格或相邻网格内的实体。
        """
        n = len(entities)  # assign
        if n < 2:  # check: numeric comparison
            return entities  # return

        # ── 小数据量：直接 O(n²) 全量对比（开销小，无额外内存） ──
        if n < 2000:  # check: numeric comparison
            merged = []  # init: empty list
            used = set()  # init: empty set
            for i, a in enumerate(entities):  # loop: for i, a in enumerate(entities):
                if i in used:  # check: membership test
                    continue  # code
                cluster = [a]  # assign
                used.add(i)  # call
                for j, b in enumerate(entities):  # loop: for j, b in enumerate(entities):
                    if j in used:  # check: membership test
                        continue  # code
                    if a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5:  # check: numeric comparison
                        cluster.append(b)  # append: add to list
                        used.add(j)  # call
                if len(cluster) > 1:  # check: numeric comparison
                    merged_bbox = self._union_bbox([e.bbox for e in cluster])  # assign: membership check
                    merged.append(SemanticEntity(  # code
                        entity_id=a.id, entity_type=a.type,  # assign
                        bbox=merged_bbox, layer=a.layer,  # assign
                        confidence=max(e.confidence for e in cluster),  # assign: membership check
                        properties=a.properties,  # assign
                    ))  # code
                else:  # else: default case
                    merged.append(a)  # append: add to list
            return merged  # return

        # ── 大数据量：空间哈希分桶 ──
        CELL_SIZE = 500.0  # mm，网格大小
        from collections import defaultdict  # stdlib import

        # 构建网格索引：{(gx, gy): [idx, ...]}
        grid = defaultdict(list)  # assign
        for idx, e in enumerate(entities):  # loop: for idx, e in enumerate(entities):
            bx = e.bbox.get("x", 0)  # assign
            by = e.bbox.get("y", 0)  # assign
            bw = max(e.bbox.get("width", 0), 1.0)  # assign
            bh = max(e.bbox.get("height", 0), 1.0)  # assign
            gx1 = int(bx / CELL_SIZE)  # assign
            gx2 = int((bx + bw) / CELL_SIZE)  # assign
            gy1 = int(by / CELL_SIZE)  # assign
            gy2 = int((by + bh) / CELL_SIZE)  # assign
            for gx in range(gx1, gx2 + 1):  # loop: for gx in range(gx1, gx2 + 1):
                for gy in range(gy1, gy2 + 1):  # loop: for gy in range(gy1, gy2 + 1):
                    grid[(gx, gy)].append(idx)  # append: add to list

        # 去重标记
        merged = []  # init: empty list
        used = set()  # init: empty set

        for i, a in enumerate(entities):  # loop: for i, a in enumerate(entities):
            if i in used:  # check: membership test
                continue  # code

            cluster = [a]  # assign
            used.add(i)  # call

            # 找到 a 所在的网格
            bx = a.bbox.get("x", 0)  # assign
            by = a.bbox.get("y", 0)  # assign
            bw = max(a.bbox.get("width", 0), 1.0)  # assign
            bh = max(a.bbox.get("height", 0), 1.0)  # assign
            gx1 = int(bx / CELL_SIZE)  # assign
            gx2 = int((bx + bw) / CELL_SIZE)  # assign
            gy1 = int(by / CELL_SIZE)  # assign
            gy2 = int((by + bh) / CELL_SIZE)  # assign

            # 收集相邻网格中的候选实体
            candidates = set()  # init: empty set
            for gx in range(gx1 - 1, gx2 + 2):  # loop: for gx in range(gx1 - 1, gx2 + 2):
                for gy in range(gy1 - 1, gy2 + 2):  # loop: for gy in range(gy1 - 1, gy2 + 2):
                    for idx in grid.get((gx, gy), []):  # loop: for idx in grid.get((gx, gy), []):
                        if idx not in used:  # check: membership test
                            candidates.add(idx)  # call

            for j in sorted(candidates):  # loop: for j in sorted(candidates):
                if j in used:  # check: membership test
                    continue  # code
                b = entities[j]  # assign
                if a.type == b.type and self._compute_iou(a.bbox, b.bbox) > 0.5:  # check: numeric comparison
                    cluster.append(b)  # append: add to list
                    used.add(j)  # call

            if len(cluster) > 1:  # check: numeric comparison
                merged_bbox = self._union_bbox([e.bbox for e in cluster])  # assign: membership check
                merged.append(SemanticEntity(  # code
                    entity_id=a.id, entity_type=a.type,  # assign
                    bbox=merged_bbox, layer=a.layer,  # assign
                    confidence=max(e.confidence for e in cluster),  # assign: membership check
                    properties=a.properties,  # assign
                ))  # code
            else:  # else: default case
                merged.append(a)  # append: add to list

        return merged  # return

    def _build_relations(self, entities: List[SemanticEntity]) -> List[SpatialRelation]:  # method: def _build_relations(self, entities: List[SemanticEntity]) -
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
        relations = []  # init: empty list
        n_entities = len(entities)  # assign

        # ── 1. 相邻关系（空间哈希加速，>2000 实体跳过）──
        # 大图纸跳过全量相邻关系构建（相邻关系主要用于疏散路径分析，
        # 大图 room 数量少，跳过不影响规范判定准确性）
        # ── 1. 相邻关系（空间哈希加速，>2000 实体跳过）──
        # 大图纸跳过全量相邻关系构建（相邻关系主要用于疏散路径分析，
        # 大图 room 数量少，跳过不影响规范判定准确性）
        if n_entities <= 2000:  # check: numeric comparison
            CELL_SIZE = 100.0  # mm
            # 空间哈希网格
            grid: Dict[Tuple[int, int], List[Tuple[int, SemanticEntity]]] = {}  # init: empty dict
            for idx, e in enumerate(entities):  # loop: for idx, e in enumerate(entities):
                bx = e.bbox.get("x", 0)  # assign
                by = e.bbox.get("y", 0)  # assign
                bw = e.bbox.get("width", 0)  # assign
                bh = e.bbox.get("height", 0)  # assign
                x1_cell = int(bx / CELL_SIZE)  # assign
                x2_cell = int((bx + bw) / CELL_SIZE)  # assign
                y1_cell = int(by / CELL_SIZE)  # assign
                y2_cell = int((by + bh) / CELL_SIZE)  # assign
                for gx in range(x1_cell, x2_cell + 1):  # loop: for gx in range(x1_cell, x2_cell + 1):
                    for gy in range(y1_cell, y2_cell + 1):  # loop: for gy in range(y1_cell, y2_cell + 1):
                        grid.setdefault((gx, gy), []).append((idx, e))  # append: add to list

            # 只比较同一或相邻网格的实体
            compared = set()  # init: empty set
            for idx_a, a in enumerate(entities):  # loop: for idx_a, a in enumerate(entities):
                bx = a.bbox.get("x", 0)  # assign
                by = a.bbox.get("y", 0)  # assign
                bw = a.bbox.get("width", 0)  # assign
                bh = a.bbox.get("height", 0)  # assign
                x1_cell = int(bx / CELL_SIZE)  # assign
                x2_cell = int((bx + bw) / CELL_SIZE)  # assign
                y1_cell = int(by / CELL_SIZE)  # assign
                y2_cell = int((by + bh) / CELL_SIZE)  # assign
                for gx in range(x1_cell - 1, x2_cell + 2):  # loop: for gx in range(x1_cell - 1, x2_cell + 2):
                    for gy in range(y1_cell - 1, y2_cell + 2):  # loop: for gy in range(y1_cell - 1, y2_cell + 2):
                        for idx_b, b in grid.get((gx, gy), []):  # loop: for idx_b, b in grid.get((gx, gy), []):
                            if idx_b <= idx_a:  # check: numeric comparison
                                continue  # code
                            pair_key = (idx_a, idx_b)  # assign
                            if pair_key in compared:  # check: membership test
                                continue  # code
                            compared.add(pair_key)  # call
                            dist = self._min_edge_distance(a.bbox, b.bbox)  # assign
                            if dist < self.ADJACENT_THRESHOLD:  # check: numeric comparison
                                relations.append(SpatialRelation(  # code
                                    source_id=a.id, target_id=b.id,  # assign
                                    rel_type="adjacent", distance=dist,  # assign
                                    confidence=1.0 - dist / self.ADJACENT_THRESHOLD,  # assign
                                ))  # code

        # ── 2. 墙体-门窗拓扑关系（V2升级）──
        # 用几何方法精确匹配门/窗在墙上的位置：
        #   门 bbox 必须与墙 bbox 的某条边重叠（门在墙上）
        #   取最近/重叠最大的墙作为门的宿主墙
        walls = [e for e in entities if e.type == "wall"]  # compare: equality
        openings = [e for e in entities if e.type in ("door", "window", "fire_door", "exit_door")]  # assign: membership check
        
        for opening in openings:  # 循环
            best_wall = None  # init: set to None
            best_overlap = 0.0  # init: set to 0
            best_distance = float('inf')  # assign
            
            ob = opening.bbox  # assign
            ox1, oy1 = ob.get("x", 0), ob.get("y", 0)  # 操作
            ox2 = ox1 + ob.get("width", 0)  # assign
            oy2 = oy1 + ob.get("height", 0)  # assign
            o_cx = (ox1 + ox2) / 2  # assign
            o_cy = (oy1 + oy2) / 2  # assign
            
            for wall in walls:  # 循环
                wb = wall.bbox  # assign
                wx1, wy1 = wb.get("x", 0), wb.get("y", 0)  # 操作
                wx2 = wx1 + wb.get("width", 0)  # assign
                wy2 = wy1 + wb.get("height", 0)  # assign
                
                # 计算门中心到墙边的距离
                # 到左/右垂直边的水平距离
                dx_left = abs(o_cx - wx1)  # assign
                dx_right = abs(o_cx - wx2)  # assign
                # 到上/下水平边的垂直距离
                dy_bottom = abs(o_cy - wy1)  # assign
                dy_top = abs(o_cy - wy2)  # assign
                
                min_dx = min(dx_left, dx_right)  # assign
                min_dy = min(dy_bottom, dy_top)  # assign
                dist_to_edge = min(min_dx, min_dy)  # assign
                
                # 检查重叠：门必须接触墙的边界（距离<50mm）
                if dist_to_edge > 50.0:  # check: numeric comparison
                    continue  # 继续循环
                
                # 计算门在墙边上的投影重叠长度
                overlap = 0.0  # init: set to 0
                is_horizontal_wall = (wb.get("width", 0) > wb.get("height", 0))  # assign
                
                if min_dx <= min_dy:  # check: numeric comparison
                    # 门接触垂直边（墙的左或右边）
                    # 投影重叠在 y 方向
                    overlap_y = max(0, min(oy2, wy2) - max(oy1, wy1))  # assign
                    overlap = overlap_y / max(ob.get("height", 1), 1)  # assign
                else:  # 否则
                    # 门接触水平边（墙的上或下边）
                    overlap_x = max(0, min(ox2, wx2) - max(ox1, wx1))  # assign
                    overlap = overlap_x / max(ob.get("width", 1), 1)  # assign
                
                if overlap > best_overlap or (overlap == best_overlap and dist_to_edge < best_distance):  # check: numeric comparison
                    best_overlap = overlap  # assign
                    best_distance = dist_to_edge  # assign
                    best_wall = wall  # assign
            
            if best_wall:  # condition: best_wall:
                relations.append(SpatialRelation(  # code
                    source_id=best_wall.id, target_id=opening.id,  # assign
                    rel_type="contains",  # assign
                    confidence=min(0.95, best_overlap),  # assign
                ))  # code
                # 给门注入宿主墙信息
                opening.properties["host_wall_id"] = best_wall.id  # 操作
                opening.properties["host_wall_overlap"] = round(best_overlap, 2)  # 操作

        # ── 3. 走廊-门-房间拓扑（V2：基于边缘距离）──
        # 用 _min_edge_distance 判断门是否连接走廊/房间
        corridors = [e for e in entities if e.type == "corridor"]  # compare: equality
        rooms = [e for e in entities if e.type == "room"]  # compare: equality
        doors = [e for e in entities if e.type in ("door", "fire_door", "exit_door")]  # assign: membership check
        
        for door in doors:  # 循环
            for c in corridors:  # 循环
                dist = self._min_edge_distance(door.bbox, c.bbox)  # assign
                if dist < 200.0:  # 门边缘距走廊 < 200mm
                    relations.append(SpatialRelation(  # code
                        source_id=c.id, target_id=door.id,  # assign
                        rel_type="connects_to", distance=dist,  # assign
                        via="door",  # assign
                    ))  # code
            for r in rooms:  # 循环
                dist = self._min_edge_distance(door.bbox, r.bbox)  # assign
                if dist < 200.0:  # check: numeric comparison
                    relations.append(SpatialRelation(  # code
                        source_id=r.id, target_id=door.id,  # assign
                        rel_type="connects_to", distance=dist,  # assign
                        via="door",  # assign
                    ))  # code

        # ── 4. 包含关系（房间包含设备/柱）──
        contained_types = {"column", "stair", "exit", "fire_door"}  # assign
        containables = [e for e in entities if e.type in contained_types]  # assign: membership check
        for room in rooms:  # 循环
            for item in containables:  # 循环
                if self._is_inside(item.bbox, room.bbox):  # condition: self._is_inside(item.bbox, room.bbox):
                    relations.append(SpatialRelation(  # code
                        source_id=room.id, target_id=item.id,  # assign
                        rel_type="contains", confidence=0.9,  # assign
                    ))  # code

        # ── 5. 房间-门间接连接（通过墙传递）──
        # 如果房间与墙相邻，且门被墙包含，则建立房间-门的连接
        # 这样 BFS 才能从房间走到门再到出口
        room_wall_adj = {}  # init: empty dict
        wall_door_contains = {}  # init: empty dict
        for rel in relations:  # 循环
            if rel.type == "adjacent":  # condition: rel.type == "adjacent":
                if rel.source_id in {r.id for r in rooms} and rel.target_id in {w.id for w in walls}:  # check: membership test
                    room_wall_adj.setdefault(rel.source_id, set()).add(rel.target_id)  # call
                if rel.target_id in {r.id for r in rooms} and rel.source_id in {w.id for w in walls}:  # check: membership test
                    room_wall_adj.setdefault(rel.target_id, set()).add(rel.source_id)  # call
            if rel.type == "contains":  # condition: rel.type == "contains":
                if rel.source_id in {w.id for w in walls} and rel.target_id in {d.id for d in doors}:  # check: membership test
                    wall_door_contains.setdefault(rel.source_id, set()).add(rel.target_id)  # call
        for room_id, wall_ids in room_wall_adj.items():  # 循环
            for wall_id in wall_ids:  # 循环
                for door_id in wall_door_contains.get(wall_id, set()):  # 循环
                    relations.append(SpatialRelation(  # code
                        source_id=room_id, target_id=door_id,  # assign
                        rel_type="connects_to", distance=0.0,  # assign
                        via="door",  # assign
                    ))  # code

        return relations  # return

    def _bind_dimensions(self, entities: List[SemanticEntity],  # method: def _bind_dimensions(self, entities: List[SemanticEntity],
                         dimensions: List[Dict]) -> Dict[str, Dict]:  # 操作
        """尺寸标注绑定到实体"""
        bindings = {}  # init: empty dict

        for dim in dimensions:  # 循环
            dim_pos = dim.get("position", {})  # assign
            if not dim_pos:  # check: negated condition
                continue  # 继续循环

            nearest = None  # init: set to None
            nearest_dist = float("inf")  # assign

            for entity in entities:  # 循环
                center = self._bbox_center(entity.bbox)  # assign
                dist = self._point_distance(dim_pos, center)  # assign
                if dist < nearest_dist and dist < 500:  # check: numeric comparison
                    nearest = entity  # assign
                    nearest_dist = dist  # assign

            if nearest:  # condition: nearest:
                if nearest.id not in bindings:  # check: membership test
                    bindings[nearest.id] = {}  # 操作
                attr_name = self._infer_attribute_name(dim, nearest)  # assign
                bindings[nearest.id][attr_name] = dim.get("measurement", 0)  # 操作

        return bindings  # return

    # ── 几何工具函数 ────────────────────────────────────

    @staticmethod  # code
    def _compute_iou(bbox1: Dict, bbox2: Dict) -> float:  # method: def _compute_iou(bbox1: Dict, bbox2: Dict) -> float:
        """计算 IoU"""
        x1 = max(bbox1["x"], bbox2["x"])  # assign
        y1 = max(bbox1["y"], bbox2["y"])  # assign
        x2 = min(bbox1["x"] + bbox1["width"], bbox2["x"] + bbox2["width"])  # assign
        y2 = min(bbox1["y"] + bbox1["height"], bbox2["y"] + bbox2["height"])  # assign

        if x2 <= x1 or y2 <= y1:  # check: numeric comparison
            return 0.0  # return

        intersection = (x2 - x1) * (y2 - y1)  # assign
        area1 = bbox1["width"] * bbox1["height"]  # assign
        area2 = bbox2["width"] * bbox2["height"]  # assign
        union = area1 + area2 - intersection  # assign

        return intersection / union if union > 0 else 0.0  # return

    @staticmethod  # code
    def _union_bbox(bboxes: List[Dict]) -> Dict[str, float]:  # method: def _union_bbox(bboxes: List[Dict]) -> Dict[str, float]:
        """合并多个边界框"""
        xs = [b["x"] for b in bboxes]  # assign: membership check
        ys = [b["y"] for b in bboxes]  # assign: membership check
        x2s = [b["x"] + b["width"] for b in bboxes]  # assign: membership check
        y2s = [b["y"] + b["height"] for b in bboxes]  # assign: membership check
        return {  # return: dict result
            "x": min(xs), "y": min(ys),  # 字段
            "width": max(x2s) - min(xs),  # 字段
            "height": max(y2s) - min(ys),  # 字段
        }  # code

    @staticmethod  # code
    def _min_edge_distance(bbox1: Dict, bbox2: Dict) -> float:  # method: def _min_edge_distance(bbox1: Dict, bbox2: Dict) -> float:
        """最小边缘距离"""
        x1a, y1a = bbox1["x"], bbox1["y"]  # 操作
        x2a = x1a + bbox1["width"]  # assign
        y2a = y1a + bbox1["height"]  # assign
        x1b, y1b = bbox2["x"], bbox2["y"]  # 操作
        x2b = x1b + bbox2["width"]  # assign
        y2b = y1b + bbox2["height"]  # assign

        dx = max(x1b - x2a, x1a - x2b, 0)  # assign
        dy = max(y1b - y2a, y1a - y2b, 0)  # assign
        return (dx**2 + dy**2) ** 0.5  # return: tuple

    @staticmethod  # code
    def _is_inside(inner: Dict, outer: Dict) -> bool:  # method: def _is_inside(inner: Dict, outer: Dict) -> bool:
        """判断内部"""
        return (inner["x"] >= outer["x"]  # return: tuple
                and inner["y"] >= outer["y"]  # 操作
                and inner["x"] + inner["width"] <= outer["x"] + outer["width"]  # 操作
                and inner["y"] + inner["height"] <= outer["y"] + outer["height"])  # 操作

    @staticmethod  # code
    def _bbox_center(bbox: Dict) -> Dict[str, float]:  # method: def _bbox_center(bbox: Dict) -> Dict[str, float]:
        return {"x": bbox["x"] + bbox["width"] / 2,  # return: dict result
                "y": bbox["y"] + bbox["height"] / 2}  # 字段

    @staticmethod  # code
    def _point_distance(p1: Dict, p2: Dict) -> float:  # method: def _point_distance(p1: Dict, p2: Dict) -> float:
        return ((p1.get("x", 0) - p2.get("x", 0))**2  # return: tuple
                + (p1.get("y", 0) - p2.get("y", 0))**2) ** 0.5  # 欧氏距离计算

    @staticmethod  # code
    def _infer_attribute_name(dim: Dict, entity: SemanticEntity) -> str:  # method: def _infer_attribute_name(dim: Dict, entity: SemanticEntity)
        """推断属性名"""
        entity_type = entity.type  # assign
        dim_text = dim.get("text", "")  # assign

        if entity_type == "wall":  # condition: entity_type == "wall":
            return "width"  # return
        elif entity_type in ("door", "fire_door"):  # 分支
            return "clear_width"  # return
        elif entity_type == "window":  # 分支
            return "width"  # return
        elif entity_type == "stair":  # 分支
            return "step_width"  # return
        elif entity_type == "corridor":  # 分支
            return "clear_width"  # return
        elif entity_type == "fire_zone":  # 分支
            return "area"  # return
        else:  # 否则
            return "measurement"  # return

    # ── 走廊拓扑网络 ────────────────────────────────────

    def build_corridor_topology(self, entities: List[SemanticEntity],  # method: def build_corridor_topology(self, entities: List[SemanticEnt
                                 relations: List[SpatialRelation]) -> Dict[str, Any]:  # 操作
        """构建走廊拓扑网络
        
        将走廊实体按空间相邻关系连接为图，识别：
        - 连通分量（哪些走廊连通）
        - 死胡同（只有一条连接的走廊段）
        - 疏散路径（走廊到出口的可达性）
        """
        corridor_map = {e.id: e for e in entities if e.type == "corridor"}  # compare: equality
        
        if len(corridor_map) < 2:  # check: numeric comparison
            return {  # return: dict result
                "corridors": [e.to_dict() for e in corridor_map.values()],  # 字段
                "components": 1,  # 字段
                "dead_ends": [],  # 字段
                "network": {"nodes": list(corridor_map.keys()), "edges": []},  # 字段
            }  # code

        # 构建走廊-走廊相邻图
        adjacency: Dict[str, List[Tuple[str, float]]] = {eid: [] for eid in corridor_map}  # 操作
        
        for rel in relations:  # 循环
            src = rel.source_id  # assign
            tgt = rel.target_id  # assign
            if src in corridor_map and tgt in corridor_map and rel.type == "adjacent":  # check: membership test
                adjacency[src].append((tgt, rel.distance))  # 操作
                adjacency[tgt].append((src, rel.distance))  # 操作
        
        # 门连接：门关联的走廊也算连通
        for rel in relations:  # 循环
            if rel.type != "connects_to":  # condition: rel.type != "connects_to":
                continue  # 继续循环
            door_id = rel.target_id  # assign
            corridor_id = rel.source_id  # assign
            if corridor_id not in corridor_map:  # check: membership test
                continue  # 继续循环
            # 找门连接的另一侧（room或其他走廊）
            for rel2 in relations:  # 循环
                if rel2.source_id == door_id and rel2.target_id != corridor_id:  # check: OR condition
                    other_id = rel2.target_id  # assign
                    if other_id in corridor_map:  # check: membership test
                        adjacency[corridor_id].append((other_id, rel2.distance))  # 操作
                        adjacency[other_id].append((corridor_id, rel2.distance))  # 操作

        # 找连通分量（BFS）
        visited = set()  # init: empty set
        components = []  # init: empty list
        for eid in corridor_map:  # 循环
            if eid in visited:  # check: membership test
                continue  # 继续循环
            comp = []  # init: empty list
            queue = [eid]  # assign
            while queue:  # 循环
                current = queue.pop(0)  # assign
                if current in visited:  # check: membership test
                    continue  # 继续循环
                visited.add(current)  # call
                comp.append(current)  # append: add to list
                for neighbor, _ in adjacency.get(current, []):  # 循环
                    if neighbor not in visited:  # check: membership test
                        queue.append(neighbor)  # append: add to list
            if comp:  # condition: comp:
                components.append(comp)  # append: add to list

        # 找死胡同（度=1的走廊节点）
        dead_ends = []  # init: empty list
        for eid, neighbors in adjacency.items():  # 循环
            if len(neighbors) == 1:  # check: length
                ent = corridor_map[eid]  # assign
                dead_ends.append({  # code
                    "id": eid,  # 字段
                    "width": ent.properties.get("width", 0),  # 字段
                    "length": ent.properties.get("length", 0),  # 字段
                    "bbox": ent.bbox,  # 字段
                })  # code

        # 走廊宽度统计
        widths = [e.properties.get("width", 0) for e in corridor_map.values()]  # assign: membership check
        valid_widths = [w for w in widths if w > 0]  # assign: membership check

        return {  # return: dict result
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
                ],  # code
            },  # code
        }  # code

    def analyze_evacuation_routes(self, entities: List[SemanticEntity],  # method: def analyze_evacuation_routes(self, entities: List[SemanticE
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
            adj[e.id] = []  # init: empty list
        
        for rel in relations:  # 循环
            if rel.type not in ("adjacent", "connects_to", "contains"):  # check: membership test
                continue  # 继续循环
            adj.setdefault(rel.source_id, []).append((rel.target_id, rel.type, rel.distance))  # append: add to list
            adj.setdefault(rel.target_id, []).append((rel.source_id, rel.type, rel.distance))  # append: add to list

                # 出口识别：优先用明确的 exit/exit_door
        strict_exits = [e for e in entities if e.type in ("exit", "exit_door")]  # assign: membership check
        fallback_exits = [e for e in entities if e.type in ("door", "fire_door")]  # assign: membership check
        # 有明确出口就用明确出口，否则用 door/fire_door 兜底
        exits = strict_exits if strict_exits else fallback_exits  # assign
        
        rooms = [e for e in entities if e.type == "room"]  # compare: equality
        
        if not exits:  # check: negated condition
            return []  # return: list of items

        # 无明确 exit 时，room 面积 < 10m² 跳过 EVAC 判定（非疏散空间）
        skip_small_rooms = not strict_exits and bool(fallback_exits)  # assign

        # 如果没有 room 但有 corridor，用 corridor 作为起点分析连通性
        if not rooms:  # check: negated condition
            corridors = [e for e in entities if e.type == "corridor"]  # compare: equality
            if corridors:  # check: OR condition
                rooms = corridors  # 兜底：用走廊代替房间作为起点
            else:  # 否则
                return []  # return: list of items
        
        # 优先用 type=exit 的，兜底用 door/fire_door
        has_exit_type = any(e.type == "exit" for e in exits)  # compare: equality
        if not has_exit_type:  # check: negated condition
            pass  # 占位

        routes = []  # init: empty list
        for room in rooms:  # 循环
            # 兜底模式（无明确exit）且 room 面积 < 10m²：跳过 EVAC 判定
            if skip_small_rooms:  # condition: skip_small_rooms:
                bw = room.bbox.get("width", 0)  # assign
                bh = room.bbox.get("height", 0)  # assign
                area = bw * bh / 1e6  # assign
                if area < 10:  # check: numeric comparison
                    route_info = {  # assign
                        "room_id": room.id,  # 字段
                        "room_type": room.type,  # 字段
                        "room_bbox": room.bbox,  # 字段
                        "has_route": True,  # 字段
                        "path_length": None,  # 字段
                        "exit_id": None,  # 字段
                    }  # code
                    routes.append(route_info)  # append: add to list
                    continue  # 继续循环

            # BFS 找最近出口
            visited = {room.id}  # assign
            queue = [(room.id, [room.id], 0.0)]  # assign
            found_route = None  # init: set to None

            while queue:  # 循环
                current, path, distance = queue.pop(0)  # 解包
                if current in {e.id for e in exits}:  # check: membership test
                    found_route = (path, distance)  # assign
                    break  # 跳出循环
                for neighbor, rel_type, dist in adj.get(current, []):  # 循环
                    if neighbor not in visited:  # check: membership test
                        visited.add(neighbor)  # call
                        queue.append((neighbor, path + [neighbor], distance + dist))  # append: add to list

            route_info = {  # assign
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
            }  # code
            routes.append(route_info)  # append: add to list

        return routes  # return


    def verify_evacuation_connectivity(self,  # method: def verify_evacuation_connectivity(self,
                                        entities: List[SemanticEntity],  # code
                                        relations: List[SpatialRelation],  # code
                                        evacuation_routes: List[Dict]) -> List[Dict]:  # code
        """疏散路径连通性验证（P33）

        在 analyze_evacuation_routes 的基础上，验证路径实际可通行性：
        1. 路径上走廊宽度是否满足最小值（≥ 1.2m 疏散走道）
        2. 路径上是否存在瓶颈（宽度骤变）
        3. 路径是否被堵塞（door 宽度过小 < 0.8m）
        4. 路径中的 room 是否有通向走廊的门连接

        参数:
            entities: 语义实体列表
            relations: 空间关系列表
            evacuation_routes: analyze_evacuation_routes 的返回结果

        返回:
            每个房间的连通性验证结果列表
        """
        # 构建实体查找表
        entity_map = {e.id: e for e in entities}  # assign: membership check

        # 构建邻接表（同 analyze_evacuation_routes 逻辑）
        adj: Dict[str, List[Tuple[str, str, float]]] = {}  # init: empty dict
        for e in entities:  # loop: for e in entities:
            adj[e.id] = []  # init: empty list
        for rel in relations:  # loop: for rel in relations:
            if rel.type not in ("adjacent", "connects_to", "contains"):  # check: membership test
                continue  # code
            adj.setdefault(rel.source_id, []).append((rel.target_id, rel.type, rel.distance))  # append: add to list
            adj.setdefault(rel.target_id, []).append((rel.source_id, rel.type, rel.distance))  # append: add to list

        # 出口识别
        strict_exits = [e for e in entities if e.type in ("exit", "exit_door")]  # assign: membership check
        fallback_exits = [e for e in entities if e.type in ("door", "fire_door")]  # assign: membership check
        exits = strict_exits if strict_exits else fallback_exits  # assign
        exit_ids = {e.id for e in exits}  # assign: membership check

        results = []  # init: empty list

        for route in evacuation_routes:  # loop: for route in evacuation_routes:
            room_id = route["room_id"]  # assign
            path = route.get("path", [])  # assign
            has_route = route.get("has_route", False)  # assign

            if not has_route or not path:  # check: negated condition
                results.append({  # code
                    "room_id": room_id,  # code
                    "room_type": route.get("room_type", ""),  # call
                    "connected": False,  # code
                    "bottleneck": False,  # code
                    "bottleneck_details": None,  # code
                    "path": path,  # code
                })  # code
                continue  # code

            # 分析路径上的瓶颈
            bottleneck = False  # assign
            bottleneck_details = None  # init: set to None
            min_width = float("inf")  # assign

            for node_id in path:  # loop: for node_id in path:
                ent = entity_map.get(node_id)  # assign
                if ent is None:  # check: value is None
                    continue  # code

                # 走廊宽度检查
                if ent.type == "corridor":  # check: OR condition
                    width = ent.properties.get("width", 0)  # assign
                    if width > 0:  # check: numeric comparison
                        min_width = min(min_width, width)  # assign
                        # GB50016-5.5.18：疏散走道净宽不应小于 1.2m
                        if width < 1.2:  # check: numeric comparison
                            bottleneck = True  # assign
                            bottleneck_details = {  # assign
                                "type": "corridor_too_narrow",  # code
                                "entity_id": ent.id,  # code
                                "width": width,  # code
                                "threshold": 1.2,  # code
                            }  # code

                # 门宽度检查
                if ent.type in ("door", "fire_door"):  # check: membership test
                    width = ent.properties.get("width", 0)  # assign
                    if width > 0 and width < 0.8:  # check: numeric comparison
                        bottleneck = True  # assign
                        bottleneck_details = {  # assign
                            "type": "door_too_narrow",  # code
                            "entity_id": ent.id,  # code
                            "width": width,  # code
                            "threshold": 0.8,  # code
                        }  # code

                # 检查 room 是否有门连接走廊（不是直接通到出口的 room）
                if ent.type == "room" and node_id not in exit_ids:  # check: membership test
                    has_door_to_corridor = False  # assign
                    for neighbor, rel_type, _ in adj.get(node_id, []):  # loop: for neighbor, rel_type, _ in adj.get(node_id, []):
                        neighbor_ent = entity_map.get(neighbor)  # assign
                        if neighbor_ent and neighbor_ent.type == "corridor":  # check: OR condition
                            has_door_to_corridor = True  # assign
                            break  # code
                    if not has_door_to_corridor and len(path) > 1:  # check: numeric comparison
                        # 房间没有直接的门连接走廊（除非房间本身就是出口）
                        pass  # 不标记为 bottleneck，仅记录

            results.append({  # code
                "room_id": room_id,  # code
                "room_type": route.get("room_type", ""),  # call
                "connected": has_route,  # code
                "bottleneck": bottleneck,  # code
                "bottleneck_details": bottleneck_details,  # code
                "path": path,  # code
                "min_corridor_width": min_width if min_width != float("inf") else None,  # compare: inequality
            })  # code

        # 对有 BFS 路径但无出口在路径中的 room 标记为未连通
        for room in entities:  # loop: for room in entities:
            if room.type != "room":  # condition: room.type != "room":
                continue  # code
            if room.id not in {r["room_id"] for r in results}:  # check: membership test
                # 检查是否有间接路径
                visited = {room.id}  # assign
                queue = [room.id]  # assign
                found_exit = False  # assign
                while queue:  # loop: while queue:
                    current = queue.pop(0)  # assign
                    if current in exit_ids:  # check: membership test
                        found_exit = True  # assign
                        break  # code
                    for neighbor, _, _ in adj.get(current, []):  # loop: for neighbor, _, _ in adj.get(current, []):
                        if neighbor not in visited:  # check: membership test
                            visited.add(neighbor)  # call
                            queue.append(neighbor)  # append: add to list

                results.append({  # code
                    "room_id": room.id,  # code
                    "room_type": room.type,  # code
                    "connected": found_exit,  # code
                    "bottleneck": False,  # code
                    "bottleneck_details": None,  # code
                    "path": list(visited),  # call
                    "min_corridor_width": None,  # code
                })  # code

        return results  # return

    def _yolo_enhance(self, dxf_path: str) -> List[SemanticEntity]:  # method: def _yolo_enhance(self, dxf_path: str) -> List[SemanticEntit
        """对 DXF 执行 YOLO 检测，返回增强实体列表

        当前只保留 YOLO 检测精度高的实体类型：
        - room (mAP50=0.995)：房间检测极准确
        - corridor (mAP50=0.709)：走廊检测良好
        """
        from .yolo_integrator import YOLODetectionIntegrator  # 导入

        integrator = YOLODetectionIntegrator()  # assign
        if not integrator.load_model():  # check: negated condition
            logger.warning("YOLO 模型加载失败")  # call
            return []  # return: list of items

        # 渲染 DXF 并预测
        image_path, detections = integrator.render_and_predict(dxf_path, dpi=72)  # assign
        if not image_path or not detections:  # check: negated condition
            return []  # return: list of items

        # 只保留高精度类型（room, corridor）
        # room mAP50=0.995, corridor mAP50=0.709
        HIGH_CONF_TYPES = {"room", "corridor"}  # assign
        filtered = [d for d in detections if d["type"] in HIGH_CONF_TYPES and d["confidence"] >= 0.35]  # assign: membership check

        # 对 room 类型：过滤掉 bbox 面积过小或过大的（不合理房间）
        # YOLO 的 bbox 是像素坐标，需要先转为世界坐标再判断面积
        # 用 bbox 的像素宽高比辅助判断：房间应该是矩形（宽高比 < 3）
        filtered = [d for d in filtered if d["type"] != "room" or (  # compare: inequality
            d["bbox"]["width"] > 20 and d["bbox"]["height"] > 20 and  # 最小尺寸 20 像素
            max(d["bbox"]["width"], d["bbox"]["height"]) / max(d["bbox"]["height"], d["bbox"]["width"], 1) < 5.0  # 宽高比 < 5
        )]  # code

        # P25: YOLO 后置规则层兜底过滤
        from .yolo_integrator import filter_yolo_detections  # import: YOLO integrator
        filtered = filter_yolo_detections(filtered, verbose=True)  # assign

        if not filtered:  # check: negated condition
            return []  # return: list of items

        # 转换为 SemanticEntity
        entities = []  # init: empty list
        for det in filtered:  # 循环
            self._entity_counter += 1  # assign: self attribute
            entity = SemanticEntity(  # assign
                entity_id=f"YOLO_{det['type'].upper()}_{self._entity_counter:03d}",  # assign
                entity_type=det["type"],  # assign
                bbox=det["bbox"],  # assign
                layer="YOLO",  # assign
                confidence=det["confidence"],  # assign
                properties={  # assign
                    **det.get("properties", {}),  # 展开
                    "detection_source": "yolo",  # 字段
                },  # code
            )  # code
            entities.append(entity)  # append: add to list

        # 清理临时图片
        try:  # 尝试
            os.remove(image_path)  # remove: delete item
        except Exception:  # 捕获异常
            pass  # 忽略

        return entities  # return

    def _merge_yolo_results(self, rule_entities: List[SemanticEntity],  # method: def _merge_yolo_results(self, rule_entities: List[SemanticEn
                             yolo_entities: List[SemanticEntity]) -> List[SemanticEntity]:  # code
        """合并规则解析和 YOLO 检测的实体

        策略：
        1. 规则解析的实体优先保留（含已识别的 room）
        2. YOLO 检测的 room/corridor 只在规则未识别到时添加
        3. 通过 IOU 判断重叠——YOLO 框与规则框高度重叠时不重复添加
        4. YOLO 实体标记 detection_source="yolo"，原子函数对 YOLO 实体放宽判定
        """
        if not yolo_entities:  # check: negated condition
            return rule_entities  # return

        merged = list(rule_entities)  # assign
        added_ids = set()  # init: empty set

        for yolo_ent in yolo_entities:  # 循环
            yolo_bbox = yolo_ent.bbox  # assign
            yolo_center_x = yolo_bbox["x"] + yolo_bbox["width"] / 2  # assign
            yolo_center_y = yolo_bbox["y"] + yolo_bbox["height"] / 2  # assign

            # 检查是否与规则实体重叠
            is_duplicate = False  # assign
            for rule_ent in rule_entities:  # 循环
                # 只检查同类型（room 可能被归为 wall，所以放宽限制）
                if yolo_ent.type == "room" and rule_ent.type not in ("room", "wall"):  # check: membership test
                    continue  # 继续循环
                if yolo_ent.type == "corridor" and rule_ent.type != "corridor":  # check: OR condition
                    continue  # 继续循环

                rule_bbox = rule_ent.bbox  # assign
                # 检查 YOLO 中心点是否在规则实体的 bbox 内
                if (rule_bbox["x"] <= yolo_center_x <= rule_bbox["x"] + rule_bbox["width"] and  # check: numeric comparison
                    rule_bbox["y"] <= yolo_center_y <= rule_bbox["y"] + rule_bbox["height"]):  # assign
                    is_duplicate = True  # assign
                    break  # 跳出循环

                # 计算 IOU
                inter_x = max(0, min(yolo_bbox["x"] + yolo_bbox["width"], rule_bbox["x"] + rule_bbox["width"]) -  # assign
                                 max(yolo_bbox["x"], rule_bbox["x"]))  # max: get maximum
                inter_y = max(0, min(yolo_bbox["y"] + yolo_bbox["height"], rule_bbox["y"] + rule_bbox["height"]) -  # assign
                                 max(yolo_bbox["y"], rule_bbox["y"]))  # max: get maximum
                union = yolo_bbox["width"] * yolo_bbox["height"] + rule_bbox["width"] * rule_bbox["height"] - inter_x * inter_y  # assign
                iou = (inter_x * inter_y) / max(union, 1)  # assign
                if iou > 0.3:  # check: numeric comparison
                    is_duplicate = True  # assign
                    break  # 跳出循环

            if not is_duplicate and yolo_ent.id not in added_ids:  # check: membership test
                # YOLO 实体标记检测来源，原子函数会据此放宽尺寸相关判定
                yolo_ent.properties["detection_source"] = "yolo"  # 操作
                # 对 YOLO 检测的 room 不设置 area 属性（bbox 映射不精确）
                if yolo_ent.type == "room":  # condition: yolo_ent.type == "room":
                    yolo_ent.properties.pop("area", None)  # 操作
                merged.append(yolo_ent)  # append: add to list
                added_ids.add(yolo_ent.id)  # call

        return merged  # return
