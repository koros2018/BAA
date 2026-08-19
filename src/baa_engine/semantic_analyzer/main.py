"""BAA 语义识别引擎 — 语义分析主类"""

import os
import math
from collections import deque
from typing import List, Dict, Any, Optional, Tuple

from ..drawing_parser import RawPrimitive
import logging

logger = logging.getLogger(__name__)

from .models import SemanticEntity, SpatialRelation
from .layer_rules import LAYER_RULES, SHORT_LAYER_RULES
from .geometry import compute_iou, union_bbox, bbox_center, point_distance

from .classify import (
    _classify_entities,
    _classify_by_layer,
    _classify_by_geometry,
)
from .meta import _parse_meta_entities
from .room import _is_near_closed, _sweep_line_detect_rooms
from .merge import _merge_overlapping
from .relations import (
    _build_relations,
    _bind_dimensions,
    _infer_attribute_name,
)
from .room_type_infer import infer_room_type


class SemanticAnalyzer:
    ADJACENT_THRESHOLD = 50.0  # 相邻距离阈值(mm)

    def __init__(self):
        """初始化实例。"""
        self._entity_counter = 0  # assign: self attribute
        self._analyze_cache: Dict[str, Dict[str, Any]] = {}  # hash -> result
        self._cache_max = 50  # assign: self attribute

    def analyze(
        self,
        primitives: List[RawPrimitive],
        dimensions: List[Dict] = None,  # 操作
        max_entities: int = 10000,  # 性能优化后默认提升到 10000
        building_type: str = "civil",  # assign
        dxf_path: Optional[str] = None,
    ) -> Dict[str, Any]:  # init: set to None
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

            # 使用前100个图元的type+bbox近似指纹
            fingerprint_parts = []  # init: empty list
            for p in primitives[:100]:  # loop: for p in primitives[:100]:
                fingerprint_parts.append(f"{p.dxf_type}:{p.bbox}")  # append: add to list
            fingerprint = hashlib.sha256("".join(fingerprint_parts).encode()).hexdigest()[
                :32
            ]  # assign
            cached = self._analyze_cache.get(fingerprint)  # assign
            if cached is not None:  # check: value is not None
                return cached  # return
        except Exception:  # catch: exception handler
            fingerprint = None  # init: set to None

        # 采样限制，防止全量关系构建OOM
        # 保留原始 primitives 供扫线法使用（扫线只消费 LINE/LWPOLYLINE）
        full_primitives = primitives
        if len(primitives) > max_entities:  # check: numeric comparison
            import random  # stdlib import

            random.seed(42)  # call
            primitives = random.sample(primitives, max_entities)  # assign

        # Step 1: 图元分类归并
        entities = self._classify_entities(primitives)  # assign

        # Step 1.05: 楼层/区域检测（P35新增）
        floor_levels = self._detect_floor_levels(primitives)  # assign
        floor_assignments = self._assign_entities_to_floors(
            entities, primitives, floor_levels
        )  # assign

        # Step 1.1: YOLO 检测增强（可选，通过 dxf_path 触发）
        if dxf_path:  # condition: dxf_path:
            try:  # 尝试
                yolo_entities = self._yolo_enhance(dxf_path)  # assign
                if yolo_entities:  # condition: yolo_entities:
                    entities = self._merge_yolo_results(entities, yolo_entities)  # assign
                    logger.info(
                        f"YOLO 增强: 新增 {len(yolo_entities)} 个实体, 合并后共 {len(entities)} 个"
                    )  # len: get length
            except Exception as e:  # 捕获异常
                logger.warning(f"YOLO 增强失败: {e}")  # call

        # Step 1.4: 扫线法复合房间识别（LINE 闭合检测）
        # 使用全量原语，避免采样导致 wall 段不完整
        new_rooms = self._sweep_line_detect_rooms(full_primitives)  # assign
        if new_rooms:  # condition: new_rooms:
            entities = entities + new_rooms  # assign

        # Step 1.5: 走廊宽度推断（平行线聚类 + bbox 短边）
        entities = self._infer_corridor_widths(entities, primitives)  # assign

        # Step 1.6: door/fire_door 属性增强（宽度兜底 + 防火等级推断）
        for ent in entities:  # 循环
            if ent.type in ("door", "fire_door", "exit_door"):  # check: membership test
                # 宽度兜底：bbox长边优先推断（门扇的宽度是长边，短边是门扇厚度）
                if (
                    ent.properties.get("width", 0) < 0.3
                    and ent.properties.get("clear_width", 0) < 0.3
                ):  # check: numeric comparison
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
                        if (
                            short_edge > 0 and long_edge / short_edge >= 3.0
                        ):  # check: numeric comparison
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
                    existing_rating = ent.properties.get(
                        "fire_rating", ent.properties.get("rating", 0)
                    )  # assign
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

        # Step 2.1: P109 — 扫线法 room 属性推断（几何特征 + 文本关键词）
        entities = self._infer_room_types(entities, primitives, relations)  # assign

        # Step 3: 尺寸标注语义化
        attributes = self._bind_dimensions(entities, dimensions or [])  # assign

        # Step 4: 走廊拓扑网络（V2新增）
        corridor_topology = self.build_corridor_topology(entities, relations)  # assign

        # Step 5: 疏散路径分析（V2新增）
        evacuation_routes = self.analyze_evacuation_routes(entities, relations) or []  # assign

        # Step 5.3: 疏散路径连通性验证（P33新增）
        connectivity = self.verify_evacuation_connectivity(
            entities, relations, evacuation_routes
        )  # assign

        # Step 5.5: 疏散路径结果注入到实体属性（EVAC原子函数用）
        route_by_room = {}  # init: empty dict
        for route in evacuation_routes:  # 循环
            route_by_room[route["room_id"]] = route  # 操作
        dead_end_ids = set(
            d["id"] for d in corridor_topology.get("dead_ends", [])
        )  # assign: membership check
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
                if (
                    "has_evacuation_route" not in ent.properties and evacuation_routes
                ):  # check: membership test
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
                    ent.properties["evacuation_bottleneck_details"] = c[
                        "bottleneck_details"
                    ]  # assign

        result = {  # assign
            "entities": [e.to_dict() for e in entities],  # 字段
            "relations": [r.__dict__ if hasattr(r, "__dict__") else r for r in relations],  # 字段
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

    def _detect_floor_levels(self, primitives: List[RawPrimitive]) -> List[Dict]:
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
                    separators.append(
                        {  # code
                            "y": center_y,  # code
                            "width": bw,  # code
                            "layer": p.layer,  # code
                        }
                    )  # code

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
                    label = (
                        f"F{int(elevation) + 1}" if elevation >= 0 else f"B{abs(int(elevation))}"
                    )  # assign
                except ValueError as _e:  # catch: exception handler
                    logger.debug("[P120] 标高数值解析失败，跳过: %s", text)

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
                        label = (
                            f"F{int(level) + 1}" if level >= 0 else f"B{abs(int(level))}"
                        )  # assign
                    except ValueError as _e:  # catch: exception handler
                        logger.debug("[P120] 标高层数解析失败，跳过: %s", text)

            if level is not None:  # check: value is not None
                elevation_texts.append(
                    {  # code
                        "y": center_y,  # code
                        "level": level,  # code
                        "label": label,  # code
                        "text": text,  # code
                    }
                )  # code

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
                floor_levels.append(
                    {  # code
                        "level": i + 1,  # code
                        "label": f"F{i + 1}",  # code
                        "elevation": None,  # code
                        "y_range": [prev_y, sep["y"]],  # code
                        "source": "separator",  # code
                    }
                )  # code
                prev_y = sep["y"]  # assign
            # 添加最顶层边界
            floor_levels.append(
                {  # code
                    "level": len(sorted_seps) + 1,  # len: get length
                    "label": f"F{len(sorted_seps) + 1}",  # len: get length
                    "elevation": None,  # code
                    "y_range": [prev_y, max(all_y) if all_y else prev_y + 1],  # max: get maximum
                    "source": "separator",  # code
                }
            )  # code

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
                if (
                    abs(sorted_texts[i]["y"] - sorted_texts[i - 1]["y"]) < drawing_height * 0.1
                ):  # check: numeric comparison
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
                cluster_centers.append(
                    {"y": avg_y, "label": cluster[0]["label"], "level": cluster[0]["level"]}
                )  # append: add to list

            cluster_centers.sort(key=lambda c: c["y"])  # assign

            prev_y = min(all_y) if all_y else 0  # assign
            for i, cc in enumerate(
                cluster_centers
            ):  # loop: for i, cc in enumerate(cluster_centers):
                floor_levels.append(
                    {  # code
                        "level": i + 1,  # code
                        "label": cc["label"],  # code
                        "elevation": cc["level"],  # code
                        "y_range": [prev_y, cc["y"] + drawing_height * 0.05],  # code
                        "source": "text",  # code
                    }
                )  # code
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

    def _assign_entities_to_floors(
        self,
        entities: List[SemanticEntity],  # code
        primitives: List[RawPrimitive],  # code
        floor_levels: List[Dict],
    ) -> Dict[str, str]:  # code
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
                    closest = min(
                        floor_levels,
                        key=lambda f: abs((f["y_range"][0] + f["y_range"][1]) / 2 - center_y),
                    )  # assign
                    assignments[ent.id] = closest["label"]  # assign
                    ent.properties["floor"] = closest["label"]  # assign

        return assignments  # return

    def _infer_corridor_widths(
        self,
        entities: List[SemanticEntity],
        primitives: List[RawPrimitive] = None,
    ) -> List[SemanticEntity]:  # 操作
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
            for k in ("x", "y", "width", "height"):  # loop: for k in ('X', 'y', 'width', 'height'):
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
                    if angle > 90:
                        angle = 180 - angle  # check: numeric comparison
                    edge_candidates.append(
                        {  # code
                            "cx": cx,
                            "cy": cy,
                            "bw": bw,
                            "bh": bh,  # 字段
                            "span": span,
                            "angle": angle,  # 字段
                        }
                    )  # code
                elif p.dxf_type == "LWPOLYLINE" and p.properties.get("point_count", 0) == 2:  # 分支
                    angle = 0 if bw > bh else 90  # init: set to 0
                    edge_candidates.append(
                        {  # code
                            "cx": cx,
                            "cy": cy,
                            "bw": bw,
                            "bh": bh,  # 字段
                            "span": span,
                            "angle": angle,  # 字段
                        }
                    )  # code

            if edge_candidates:  # check: AND condition
                # 按方向分组
                h_edges = [
                    e for e in edge_candidates if e["angle"] < 30
                ]  # assign: membership check
                v_edges = [
                    e for e in edge_candidates if e["angle"] > 60
                ]  # assign: membership check

                # 水平线：按cy排序，收集所有gap
                h_sorted = sorted(h_edges, key=lambda e: e["cy"])  # assign
                h_gaps = []  # init: empty list
                for i in range(min(300, len(h_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(h_sorted))):  # 循环
                        gap = abs(h_sorted[i]["cy"] - h_sorted[j]["cy"])  # assign
                        if 500 < gap < 10000:  # check: numeric comparison
                            h_gaps.append(
                                {
                                    "gap": gap,
                                    "y1": h_sorted[i]["cy"],
                                    "y2": h_sorted[j]["cy"],  # code
                                    "cx1": h_sorted[i]["cx"],
                                    "cx2": h_sorted[j]["cx"],
                                }
                            )  # 字段

                # 垂直线：按cx排序，收集所有gap
                v_sorted = sorted(v_edges, key=lambda e: e["cx"])  # assign
                v_gaps = []  # init: empty list
                for i in range(min(300, len(v_sorted))):  # 循环
                    for j in range(i + 1, min(i + 100, len(v_sorted))):  # 循环
                        gap = abs(v_sorted[i]["cx"] - v_sorted[j]["cx"])  # assign
                        if 500 < gap < 10000:  # check: numeric comparison
                            v_gaps.append(
                                {
                                    "gap": gap,
                                    "x1": v_sorted[i]["cx"],
                                    "x2": v_sorted[j]["cx"],  # code
                                    "cy1": v_sorted[i]["cy"],
                                    "cy2": v_sorted[j]["cy"],
                                }
                            )  # 字段

                all_gaps = h_gaps + v_gaps  # assign
                if all_gaps and len(all_gaps) > 10:  # check: numeric comparison
                    # 空间分区聚类：每条走廊取离它最近的 gap 作为宽度
                    # 1) 对每个 gap，按位置分到最近的走廊
                    # 2) 每个走廊取其区域内 gap 众数
                    corridor_entities = [
                        e for e in entities if e.type == "corridor"
                    ]  # compare: equality
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
                                if (
                                    0.3 < w_m < 3.0 and ent.properties.get("width", 0) < w_m
                                ):  # check: numeric comparison
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
                                        if (
                                            abs(cy - mid_y) < 3000 and abs(cx - mid_x) < 3000
                                        ):  # check: numeric comparison
                                            nearby_gaps.append(g["gap"])  # append: add to list
                                    else:  # 垂直gap
                                        mid_x = (g["x1"] + g["x2"]) / 2  # assign
                                        mid_y = (g["cy1"] + g["cy2"]) / 2  # assign
                                        if (
                                            abs(cx - mid_x) < 3000 and abs(cy - mid_y) < 3000
                                        ):  # check: numeric comparison
                                            nearby_gaps.append(g["gap"])  # append: add to list

                                if nearby_gaps:  # condition: nearby_gaps:
                                    # 取附近gap的众数作为此走廊宽度
                                    gap_buckets = defaultdict(list)  # assign
                                    for g in nearby_gaps:  # 循环
                                        bucket = round(g / 100) * 100  # assign
                                        gap_buckets[bucket].append(g)  # 操作
                                    best_bucket = max(
                                        gap_buckets.items(), key=lambda x: len(x[1])
                                    )  # assign
                                    w_m = (
                                        sum(best_bucket[1]) / len(best_bucket[1])
                                    ) / 1000.0  # assign
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
            if ent.type not in (
                "door",
                "window",
                "fire_door",
                "exit_door",
            ):  # check: membership test
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
                if (
                    0.3 < w_m < 2.0 and ent.properties.get("width", 0) < w_m
                ):  # check: numeric comparison
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
            if ent.type not in (
                "corridor",
                "door",
                "window",
                "room",
                "wall",
            ):  # check: membership test
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
                    if ent.type in (
                        "corridor",
                        "room",
                        "door",
                        "fire_door",
                        "exit_door",
                    ):  # check: membership test
                        short_mm = min(bw, bh) if bw > 0 and bh > 0 else 0  # assign
                        if short_mm > 0:  # check: numeric comparison
                            short_m = short_mm * 0.001  # assign
                            current_w = ent.properties.get("width", 0)  # assign
                            if (
                                current_w < 0.01 and 0.05 < short_m < 3.0
                            ):  # check: numeric comparison
                                ent.properties["width"] = short_m  # 操作
                                ent.properties["clear_width"] = short_m  # 操作

        return entities  # return

    def build_corridor_topology(self, entities, relations):
        """构建走廊拓扑结构。"""
        from .evacuation import _build_corridor_topology_impl

        return _build_corridor_topology_impl(self, entities, relations)

    def analyze_evacuation_routes(self, entities, topology=None):
        """分析疏散路线。"""
        from .evacuation import _analyze_evacuation_routes_impl

        return _analyze_evacuation_routes_impl(self, entities, topology)

    def verify_evacuation_connectivity(self, entities, relations=None, evacuation_routes=None):
        """验证疏散连通性。"""
        from .evacuation import _verify_evacuation_connectivity_impl

        return _verify_evacuation_connectivity_impl(self, entities, relations, evacuation_routes)

    def _yolo_enhance(self, dxf_path):
        """使用YOLO模型增强检测结果。"""
        from .enhancement import _yolo_enhance_impl

        return _yolo_enhance_impl(self, dxf_path)

    def _merge_yolo_results(self, rule_entities, yolo_detections):
        """合并YOLO检测结果与规则检测实体。"""
        from .enhancement import _merge_yolo_results_impl

        return _merge_yolo_results_impl(self, rule_entities, yolo_detections)

    def _compute_iou(self, bbox1, bbox2):
        """计算两个边界框的IoU。"""
        return compute_iou(bbox1, bbox2)

    def _union_bbox(self, bboxes):
        """合并多个边界框为包围盒。"""
        return union_bbox(bboxes)

    def _bbox_center(self, bbox):
        """获取边界框中心点。"""
        return bbox_center(bbox)

    def _point_distance(self, p1, p2):
        """计算两点间欧氏距离。"""
        return point_distance(p1, p2)

    # ── 委派到子模块（向后兼容：测试/外部代码直接调用 analyzer._xxx） ──

    def _classify_entities(self, primitives, *args, **kwargs):
        """按图层和几何特征对实体进行分类。"""
        return _classify_entities(self, primitives, *args, **kwargs)

    def _classify_by_layer(self, layer):
        """根据图层名称分类实体。"""
        return _classify_by_layer(self, layer)

    def _classify_by_geometry(self, prim):
        """根据几何形状分类实体。"""
        return _classify_by_geometry(self, prim)

    def _parse_meta_entities(self, primitives):
        """解析元数据实体（标注、文字等）。"""
        return _parse_meta_entities(self, primitives)

    def _is_near_closed(self, prim, gap_threshold_mm=500.0):
        """判断线段是否接近闭合。"""
        return _is_near_closed(self, prim, gap_threshold_mm=gap_threshold_mm)

    def _sweep_line_detect_rooms(self, primitives):
        """用扫线法检测房间边界。"""
        return _sweep_line_detect_rooms(self, primitives)

    def _merge_line_chains_to_rooms(self, entities, primitives):
        # 兼容旧接口：测试中仍调用此方法名
        """将折线链合并为房间。"""
        return entities + self._sweep_line_detect_rooms(primitives)

    def _merge_overlapping(self, entities):
        """合并重叠的实体。"""
        return _merge_overlapping(self, entities)

    def _build_relations(self, entities):
        """构建实体间相邻关系。"""
        return _build_relations(self, entities)

    def _infer_room_types(
        self,
        entities: List[SemanticEntity],
        primitives: List[RawPrimitive],
        relations: List[SpatialRelation],
    ) -> List[SemanticEntity]:
        """P109: 对扫线法产生的 room 推断具体房间类型"""
        # 1. 收集附近 TEXT 实体（用于关键词匹配）
        text_primitives: List[RawPrimitive] = [
            p for p in primitives if p.dxf_type == "TEXT" and p.properties.get("text")
        ]

        # 2. 建立 room_id → 相邻 corridor/doorway 计数
        corridor_adj: Dict[str, int] = {}
        for rel in relations:
            if rel.type == "adjacent":
                src = [e for e in entities if e.id == rel.source_id]
                tgt = [e for e in entities if e.id == rel.target_id]
                src_types = {s.type for s in src}
                tgt_types = {t.type for t in tgt}
                if "room" in src_types and "corridor" in tgt_types:
                    corridor_adj[rel.source_id] = corridor_adj.get(rel.source_id, 0) + 1
                if "room" in tgt_types and "corridor" in src_types:
                    corridor_adj[rel.target_id] = corridor_adj.get(rel.target_id, 0) + 1

        # 3. 对每个扫线法 room 推断类型
        changed = 0
        for ent in entities:
            # 只对扫线法产生的 entity_type=="room" 且 subtype 为空的实体生效
            if ent.type != "room" or ent.subtype:
                continue

            area_m2 = ent.properties.get("area", 0)
            if area_m2 <= 0:
                continue

            bbox = ent.bbox
            bw = bbox.get("width", 0)
            bh = bbox.get("height", 0)
            if bw <= 0 or bh <= 0:
                continue
            aspect = max(bw, bh) / min(bw, bh)

            # 收集该 room 附近的 TEXT 文本（bbox 内及周围）
            rx, ry = bbox.get("x", 0), bbox.get("y", 0)
            rw, rh = bbox.get("width", 0), bbox.get("height", 0)
            pad = max(rw, rh) * 0.3  # 30% 外扩
            nearby_texts = []
            for tp in text_primitives:
                tb = tp.bbox or {}
                tx, ty = tb.get("x", 0), tb.get("y", 0)
                tw, th = tb.get("width", 0), tb.get("height", 0)
                # 检查是否在扩充 bbox 内
                if (
                    rx - pad <= tx <= rx + rw + pad
                    and ry - pad <= ty <= ry + rh + pad
                    and tx + tw <= rx + rw + pad
                    and ty + th <= ry + rh + pad
                ):
                    txt = (tp.properties.get("text") or "").strip()
                    if txt:
                        nearby_texts.append(txt)

            adj_count = corridor_adj.get(ent.id, 0)
            rtype, confidence, override = infer_room_type(
                area_m2=area_m2,
                aspect=aspect,
                corridor_adj_count=adj_count,
                nearby_texts=nearby_texts,
            )

            if rtype:
                ent.subtype = rtype
                ent.properties["inferred_type"] = rtype
                ent.properties["subtype_confidence"] = confidence

        if changed:
            logger.info(f"P109: {changed} 个 room 已推断类型")
        return entities

    def _bind_dimensions(self, entities, dimensions):
        """将尺寸标注绑定到对应实体。"""
        return _bind_dimensions(self, entities, dimensions)

    def _infer_attribute_name(self, dim, entity):
        """从尺寸标注推断实体属性名称。"""
        return _infer_attribute_name(dim, entity)
