"""
BAA YOLO 图元检测集成器
=========================
将 YOLOv8 预测结果映射到 BAA 引擎的 SemanticEntity 格式。

设计原则：
1. YOLO 检测作为规则解析的增强，不替代
2. 检测框 + 类别 → 结构化实体（bbox/properties）
3. 支持渲染图像、运行预测、结果映射全链路
"""
import logging  # stdlib: logging
import math  # stdlib: math
import os  # stdlib: filesystem ops
import sys  # import
from pathlib import Path  # import: path utils
from typing import List, Dict, Any, Optional, Tuple  # typing: type hints

logger = logging.getLogger(__name__)  # function call

# ── 类别映射 ──────────────────────────────────────────────

YOLO_CLASSES = [  # assignment
    "wall",           # 0
    "door",           # 1
    "window",         # 2
    "staircase",      # 3
    "corridor",       # 4
    "fire_door",      # 5
    "exit",           # 6
    "fire_lane",      # 7
    "fire_zone",      # 8
    "fire_window",    # 9
    "shaft",          # 10
    "room",           # 11
    "exit_sign",      # 12
    "sprinkler_system", # 13
    "fire_alarm",     # 14
    "insulation",     # 15
    "evacuation_lighting", # 16
    "refuge_floor",   # 17
]  # code

# 哪些类别需要面积估算（基于bbox）
AREA_CLASSES = {"room", "fire_zone", "wall"}  # assignment

# 哪些类别有宽度属性（门/窗/楼梯/走廊等）
WIDTH_CLASSES = {"door", "window", "fire_door", "fire_window", "staircase", "corridor", "fire_lane"}  # assignment


class YOLODetectionIntegrator:  # class definition
    """YOLO 图元检测集成器"""

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):  # function: def __init__(self, model_path: Optional[str] = None, device:
        self._model = None  # assignment
        self._model_path = model_path  # assignment
        self._loaded = False  # assignment
        self._device = device  # cpu / xpu（Intel Arc GPU）

    def load_model(self, model_path: Optional[str] = None) -> bool:  # function: def load_model(self, model_path: Optional[str] = None) -> bo
        """加载 YOLO 模型"""
        # 条件分支：if self._loaded
        if self._loaded:  # condition: self._loaded:
            return True  # return: boolean

        path = model_path or self._model_path  # assignment
        # 条件分支：if not path
        if not path:  # check: negated condition
            # 默认路径：从项目目录找最新训练的best.pt
            project_root = Path(__file__).resolve().parent.parent.parent  # function call
            candidates = [  # assignment
                project_root / "data" / "models" / "baa_yolov8n_v3" / "weights" / "best.pt",  # 操作
                project_root / "data" / "models" / "baa_yolov8n_v2" / "weights" / "best.pt",  # 操作
                project_root / "runs" / "detect" / "data" / "models" / "baa_yolov8n_v2-3" / "weights" / "best.pt",  # 操作
                project_root / "data" / "models" / "baa_yolov8n" / "weights" / "best.pt",  # 操作
            ]  # code
            # 遍历处理
            for c in candidates:  # 循环
                # 条件分支：if c.exists()
                if c.exists():  # condition: c.exists():
                    path = str(c)  # function call
                    break  # 跳出循环

        # 条件分支：if not path or not os.path.exists(path)
        if not path or not os.path.exists(path):  # check: negated condition
            return False  # return: boolean

        # 异常保护
        try:  # 尝试
            from ultralytics import YOLO  # import
            os.environ['CUDA_VISIBLE_DEVICES'] = '-1'  # assignment
            self._model = YOLO(str(path), task='detect')  # function call
            self._model_path = str(path)  # function call
            self._loaded = True  # assignment
            return True  # return: boolean
        # 异常处理
        except Exception:  # 捕获异常
            return False  # return: boolean

    def is_loaded(self) -> bool:  # function: def is_loaded(self) -> bool:
        return self._loaded  # return: self

    def predict(self, image_path: str, conf: float = 0.25, iou: float = 0.5) -> List[Dict[str, Any]]:  # function: def predict(self, image_path: str, conf: float = 0.25, iou: 
        """对单张图纸图像执行 YOLO 预测

        返回:
            List[Dict]: 每个检测结果包含
                - type: str (实体类型)
                - confidence: float
                - bbox: {"x", "y", "width", "height"} (像素坐标)
                - properties: dict (额外属性)
        """
        # 条件分支：if not self._loaded
        if not self._loaded:  # check: negated condition
            # 条件分支：if not self.load_model()
            if not self.load_model():  # check: negated condition
                return []  # return: list

        results = self._model.predict(  # assignment
            source=image_path,  # assignment
            conf=conf,  # assignment
            iou=iou,  # assignment
            imgsz=640,  # 限制推理尺寸，防 OOM
            verbose=False,  # assignment
        )  # code

        detections = []  # assignment
        # 遍历处理
        for result in results:  # 循环
            # 条件分支：if result.boxes is None
            if result.boxes is None:  # check: value is None
                continue  # 继续循环
            # 遍历处理
            for box in result.boxes:  # 循环
                cls_id = int(box.cls[0].item())  # function call
                # 条件分支：if cls_id >= len(YOLO_CLASSES)
                if cls_id >= len(YOLO_CLASSES):  # check: numeric comparison
                    continue  # 继续循环
                confidence = box.conf[0].item()  # function call
                xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                x1, y1, x2, y2 = xyxy  # assignment

                entity_type = YOLO_CLASSES[cls_id]  # assignment
                bbox = {  # assignment
                    "x": x1,  # 字段
                    "y": y1,  # 字段
                    "width": x2 - x1,  # 字段
                    "height": y2 - y1,  # 字段
                }  # code

                props = {"confidence": confidence}  # assignment

                # 估算面积
                if entity_type in AREA_CLASSES:  # check: membership test
                    props["area"] = bbox["width"] * bbox["height"]  # 操作

                # 估算宽度（取短边作为"宽度"参考）
                if entity_type in WIDTH_CLASSES:  # check: membership test
                    props["width"] = min(bbox["width"], bbox["height"])  # 操作
                    props["clear_width"] = props["width"]  # 操作

                detections.append({  # code
                    "type": entity_type,  # 字段
                    "confidence": confidence,  # 字段
                    "bbox": bbox,  # 字段
                    "properties": props,  # 字段
                })  # code

        return detections  # return

    def render_and_predict(self, dxf_path: str, dpi: int = 100) -> Tuple[Optional[str], List[Dict]]:  # function: def render_and_predict(self, dxf_path: str, dpi: int = 100) 
        """渲染 DXF 为图像 → 执行 YOLO 预测

        返回:
            (image_path, detections)
        """
        image_path = self._render_dxf(dxf_path, dpi)  # function call
        # 条件分支：if image_path is None
        if image_path is None:  # check: value is None
            return None, []  # return
        detections = self.predict(image_path)  # function call
        return image_path, detections  # return

    def detections_to_entities(self, detections: List[Dict],  # function: def detections_to_entities(self, detections: List[Dict],
                                world_bbox: Optional[Dict] = None,  # 操作
                                image_size: Tuple[int, int] = (640, 640)) -> List[Dict]:  # 操作
        """将 YOLO 检测结果映射为引擎实体格式

        参数:
            detections: predict() 返回的检测列表
            world_bbox: DXF 的世界坐标边界 {"x","y","width","height"}
                        如果提供，将像素坐标映射回世界坐标
            image_size: 图像尺寸 (w, h)

        返回:
            List[Dict]: 与 deconstruct API 的 elements 格式一致
        """
        img_w, img_h = image_size  # assignment
        entities = []  # assignment

        # 遍历处理
        for det in detections:  # 循环
            px = det["bbox"]["x"]  # assignment
            py = det["bbox"]["y"]  # assignment
            pw = det["bbox"]["width"]  # assignment
            ph = det["bbox"]["height"]  # assignment

            # 条件分支：if world_bbox
            if world_bbox:  # check: OR condition
                # 像素坐标 → 世界坐标
                scale_x = world_bbox["width"] / img_w  # assignment
                scale_y = world_bbox["height"] / img_h  # assignment
                wx = world_bbox["x"] + px * scale_x  # assignment
                wy = world_bbox["y"] + py * scale_y  # assignment
                ww = pw * scale_x  # assignment
                wh = ph * scale_y  # assignment
            # 其他情况处理
            else:  # 否则
                wx, wy, ww, wh = px, py, pw, ph  # assignment

            entity = {  # assignment
                "type": det["type"],  # 字段
                "count": 1,  # 字段
                "bbox": {"x": wx, "y": wy, "width": ww, "height": wh},  # 字段
                "properties": {  # 字段
                    **det["properties"],  # 展开 YOLO 检测属性
                    "detection_source": "yolo",  # 字段
                },  # code
            }  # code

            # 合并同名实体的计数
            existing = None  # assignment
            for e in entities:  # 循环
                if e["type"] == det["type"] and e.get("properties", {}).get("detection_source") == "yolo":  # check: AND condition
                    existing = e  # assignment
                    break  # 跳出循环

            # 条件分支：if existing
            if existing:  # condition: existing:
                existing["count"] += 1  # 操作
            # 其他情况处理
            else:  # 否则
                entities.append(entity)  # append to list

        return entities  # return

    def _render_dxf(self, dxf_path: str, dpi: int = 100) -> Optional[str]:  # function: def _render_dxf(self, dxf_path: str, dpi: int = 100) -> Opti
        """将 DXF 渲染为 JPG 图像（同训练数据准备逻辑）"""
        import ezdxf  # import
        import matplotlib  # import
        matplotlib.use('Agg')  # function call
        import matplotlib.pyplot as plt  # import
        import tempfile  # stdlib: temp files

        # 异常保护
        try:  # 尝试
            doc = ezdxf.readfile(dxf_path)  # function call
            msp = doc.modelspace()  # function call
        # 异常处理
        except Exception:  # 捕获异常
            return None  # return: None

        # 计算边界
        all_x, all_y = [], []  # assignment
        for entity in msp:  # 循环
            try:  # 尝试
                if entity.dxftype() == "LINE":  # condition: entity.dxftype() == "LINE":
                    s, e = entity.dxf.start, entity.dxf.end  # assignment
                    all_x.extend([s[0], e[0]])  # extend list
                    all_y.extend([s[1], e[1]])  # extend list
                # 条件分支：elif entity.dxftype() == "LWPOLYLINE"
                elif entity.dxftype() == "LWPOLYLINE":  # 分支
                    pts = [(v[0], v[1]) for v in entity.get_points()]  # function call
                    all_x.extend(p[0] for p in pts)  # extend list
                    all_y.extend(p[1] for p in pts)  # extend list
                # 条件分支：elif entity.dxftype() == "CIRCLE"
                elif entity.dxftype() == "CIRCLE":  # 分支
                    cx, cy = entity.dxf.center[:2]  # assignment
                    r = entity.dxf.radius  # assignment
                    all_x.extend([cx - r, cx + r])  # extend list
                    all_y.extend([cy - r, cy + r])  # extend list
                # 条件分支：elif entity.dxftype() in ("TEXT", "MTEXT")
                elif entity.dxftype() in ("TEXT", "MTEXT"):  # 分支
                    ins = entity.dxf.insert[:2]  # assignment
                    all_x.append(ins[0])  # append to list
                    all_y.append(ins[1])  # append to list
            # 异常处理
            except Exception:  # 捕获异常
                continue  # 继续循环

        # 条件分支：if not all_x
        if not all_x:  # check: negated condition
            return None  # return: None

        margin = 2.0  # assignment
        x_min, x_max = min(all_x) - margin, max(all_x) + margin  # 解包
        y_min, y_max = min(all_y) - margin, max(all_y) + margin  # 解包

        fig_w = max(x_max - x_min, 1) * 0.4  # get maximum
        fig_h = max(y_max - y_min, 1) * 0.4  # get maximum
        # 限制最大图像尺寸，防止 OOM（max 2048px）
        max_pixels = 2048  # assignment
        if fig_w * dpi > max_pixels or fig_h * dpi > max_pixels:  # check: numeric comparison
            scale = min(max_pixels / (fig_w * dpi), max_pixels / (fig_h * dpi))  # get minimum
            fig_w *= scale  # multiply
            fig_h *= scale  # multiply
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)  # function call
        ax.set_xlim(x_min, x_max)  # function call
        ax.set_ylim(y_min, y_max)  # function call
        ax.set_aspect('equal')  # function call
        ax.axis('off')  # function call

        # 遍历处理
        for entity in msp:  # 循环
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''  # attribute check
            # 条件分支：if layer.upper() == "META"
            if layer.upper() == "META":  # condition: layer.upper() == "META":
                continue  # 继续循环
            dxftype = entity.dxftype()  # function call
            # 异常保护
            try:  # 尝试
                # 条件分支：if dxftype == "LINE"
                if dxftype == "LINE":  # condition: dxftype == "LINE":
                    s, e = entity.dxf.start, entity.dxf.end  # assignment
                    ax.plot([s[0], e[0]], [s[1], e[1]], 'k-', linewidth=0.3)  # function call
                # 条件分支：elif dxftype == "LWPOLYLINE"
                elif dxftype == "LWPOLYLINE":  # 分支
                    pts = [(v[0], v[1]) for v in entity.get_points()]  # function call
                    xs, ys = zip(*pts)  # function call
                    ax.plot(xs, ys, 'k-', linewidth=0.3)  # function call
                # 条件分支：elif dxftype == "CIRCLE"
                elif dxftype == "CIRCLE":  # 分支
                    cx, cy = entity.dxf.center[:2]  # assignment
                    r = entity.dxf.radius  # assignment
                    ax.add_patch(plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.3))  # function call
                # 条件分支：elif dxftype == "ARC"
                elif dxftype == "ARC":  # 分支
                    cx, cy = entity.dxf.center[:2]  # assignment
                    r = entity.dxf.radius  # assignment
                    ax.add_patch(plt.Arc((cx, cy), r*2, r*2, angle=0,  # function call
                                          theta1=entity.dxf.start_angle,  # assignment
                                          theta2=entity.dxf.end_angle,  # assignment
                                          color='k', linewidth=0.3))  # assignment
            # 异常处理
            except Exception:  # 捕获异常
                continue  # 继续循环

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)  # function call
        tmp_path = tmp.name  # assignment
        tmp.close()  # function call
        plt.savefig(tmp_path, dpi=dpi, bbox_inches='tight', pad_inches=0.05, facecolor='white')  # function call
        plt.close(fig)  # function call
        return tmp_path  # return


# ── YOLO 后置过滤 ──────────────────────────────────────────

def _compute_iou(a: Dict, b: Dict) -> float:  # function: def _compute_iou(a: Dict, b: Dict) -> float:
    """计算两个 bbox 的 IoU"""
    inter_x = max(0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))  # get maximum
    inter_y = max(0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))  # get maximum
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter_x * inter_y  # assignment
    return (inter_x * inter_y) / max(union, 1)  # return: tuple


def _compute_center(bbox: Dict) -> Tuple[float, float]:  # function: def _compute_center(bbox: Dict) -> Tuple[float, float]:
    """计算 bbox 中心点"""
    return bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2  # return


def _point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:  # function: def _point_to_segment_distance(px: float, py: float, x1: flo
    """点到线段的最短距离"""
    dx, dy = x2 - x1, y2 - y1  # assignment
    if dx == 0 and dy == 0:  # check: AND condition
        return math.hypot(px - x1, py - y1)  # return
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))  # get maximum
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))  # return


def filter_yolo_detections(detections: List[Dict], walls: Optional[List[Dict]] = None,  # function: def filter_yolo_detections(detections: List[Dict], walls: Op
                           min_corridor_width_m: float = 0.5, verbose: bool = False) -> List[Dict]:  # assignment
    """YOLO 检测结果规则层后置兜底过滤

    策略（P25）：
    1. corridor 宽度过滤：bbox 短边 < min_corridor_width_m → 跳过（已有兜底）
    2. door 方向校验：door 中心是否贴近某条 wall 线
       — 不贴墙可能也是误检
    3. window 墙体对齐：window 是否与 wall 重叠
    4. corridor 连续性：孤立 corridor（无相邻 door/room）标记低置信
    5. room 宽高比/面积合理性

    参数:
        detections: predict() 返回的检测列表
        walls: 可选的墙体线列表，每项为 {"x1","y1","x2","y2"}
        min_corridor_width_m: corridor 最小宽度阈值（米）
        verbose: 是否输出过滤日志

    返回:
        过滤后的检测列表，每条可能包含 added 或 suppressed 标记
    """
    if not detections:  # check: negated condition
        return []  # return: list

    # 收集所有横向/纵向墙体线段（用于贴近性校验）
    wall_segments: List[Dict] = []  # assignment
    if walls:  # condition: walls:
        wall_segments = walls  # assignment
    else:  # else: default case
        # 从检测结果中提取 wall 实体作为参考线
        wall_segments = [  # assignment
            {"x1": d["bbox"]["x"], "y1": d["bbox"]["y"],  # literal: collection
             "x2": d["bbox"]["x"] + d["bbox"]["width"],  # code
             "y2": d["bbox"]["y"] + d["bbox"]["height"]}  # code
            for d in detections if d["type"] == "wall"  # loop: iterate
        ]  # code

    filtered: List[Dict] = []  # assignment
    wall_bboxes = [d["bbox"] for d in detections if d["type"] == "wall"]  # equality check

    for det in detections:  # loop: iterate
        etype = det["type"]  # assignment
        bbox = det["bbox"]  # assignment
        w, h = bbox["width"], bbox["height"]  # assignment
        cx, cy = _compute_center(bbox)  # function call
        keep = True  # assignment
        suppression_reason = None  # assignment

        # ── 规则 1：走廊宽度过滤（已有兜底） ──
        if etype == "corridor":  # check: OR condition
            width_m = min(w, h)  # get minimum
            if width_m < min_corridor_width_m:  # check: numeric comparison
                keep = False  # assignment
                suppression_reason = f"corridor_width={width_m:.2f}<{min_corridor_width_m:.2f}"  # assignment

        # ── 规则 2：door 方向校验（是否贴墙） ──
        if etype in ("door", "fire_door") and keep:  # check: membership test
            # door 的较窄边应紧贴墙体
            door_long_side = max(w, h)  # get maximum
            door_short_side = min(w, h)  # get minimum

            # 贴近性：door 边框与任何 wall bbox 的最近距离
            if wall_bboxes:  # condition: wall_bboxes:
                min_dist = min(  # assignment
                    _point_to_segment_distance(  # code
                        cx, cy,  # code
                        wb["x"], wb["y"],  # code
                        wb["x"] + wb["width"], wb["y"] + wb["height"]  # code
                    )  # code
                    for wb in wall_bboxes  # loop: iterate
                )  # code
                # 如果 door 中心到最近墙体的距离 > door 长边的 2 倍，判定为误检
                if min_dist > max(door_long_side * 2.0, door_short_side * 3.0):  # check: numeric comparison
                    keep = False  # assignment
                    suppression_reason = f"door_wall_dist={min_dist:.1f}>threshold"  # assignment

        # ── 规则 3：window 墙体对齐 ──
        if etype == "window" and keep:  # check: AND condition
            if wall_bboxes:  # condition: wall_bboxes:
                # window 应至少有一条边与 wall 重叠
                # 简化：window 中心到最近 wall 的距离 < window 宽度的 1.5 倍
                window_long = max(w, h)  # get maximum
                min_dist = min(  # assignment
                    _point_to_segment_distance(  # code
                        cx, cy,  # code
                        wb["x"], wb["y"],  # code
                        wb["x"] + wb["width"], wb["y"] + wb["height"]  # code
                    )  # code
                    for wb in wall_bboxes  # loop: iterate
                )  # code
                if min_dist > window_long * 2.0:  # check: numeric comparison
                    keep = False  # assignment
                    suppression_reason = f"window_wall_dist={min_dist:.1f}>threshold"  # assignment

        # ── 规则 4：corridor 连续性 ──
        if etype == "corridor" and keep:  # check: OR condition
            # 检查 corridor 附近是否有 door/room 实体
            adjacent_found = False  # assignment
            for other in detections:  # loop: iterate
                if other["type"] in ("door", "room", "fire_door") and other is not det:  # check: membership test
                    ob = other["bbox"]  # assignment
                    ocx, ocy = _compute_center(ob)  # function call
                    dist = math.hypot(cx - ocx, cy - ocy)  # math operation
                    # corridor 中心到 door/room 中心的距离在合理范围内
                    if dist < max(w, h) * 3.0:  # check: numeric comparison
                        adjacent_found = True  # assignment
                        break  # code
            # 只标记低置信度，不直接过滤（保留给走廊推断逻辑处理）
            if not adjacent_found:  # check: negated condition
                det["properties"]["corridor_low_confidence"] = True  # assignment
                if verbose:  # condition: verbose:
                    logger.debug(f"corridor 孤立: {det.get('type')} @ ({cx:.1f},{cy:.1f})")  # function call

        # ── 规则 5：room 宽高比/面积合理性 ──
        if etype == "room" and keep:  # check: AND condition
            # 宽高比 > 5 的不合理房间
            aspect = max(w, h) / max(h, w, 1)  # get maximum
            if aspect > 5.0:  # check: numeric comparison
                keep = False  # assignment
                suppression_reason = f"room_aspect_ratio={aspect:.1f}>5"  # assignment
            elif aspect > 4.0:  # elif condition
                # 宽高比 4~5 的标记为低置信
                det["properties"]["room_low_confidence"] = True  # assignment
                if verbose:  # condition: verbose:
                    logger.debug(f"room 宽高比异常: {aspect:.1f} @ ({cx:.1f},{cy:.1f})")  # function call

        if keep:  # condition: keep:
            filtered.append(det)  # append to list
        elif verbose:  # elif condition
            logger.debug(f"YOLO 过滤: {det['type']} confidence={det['confidence']:.3f} reason={suppression_reason}")  # function call

    return filtered  # return
