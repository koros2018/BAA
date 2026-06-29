"""
BAA YOLO 图元检测集成器
=========================
将 YOLOv8 预测结果映射到 BAA 引擎的 SemanticEntity 格式。

设计原则：
1. YOLO 检测作为规则解析的增强，不替代
2. 检测框 + 类别 → 结构化实体（bbox/properties）
3. 支持渲染图像、运行预测、结果映射全链路
"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# ── 类别映射 ──────────────────────────────────────────────

YOLO_CLASSES = [  # 赋值
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
]

# 哪些类别需要面积估算（基于bbox）
AREA_CLASSES = {"room", "fire_zone", "wall"}  # 赋值

# 哪些类别有宽度属性（门/窗/楼梯/走廊等）
WIDTH_CLASSES = {"door", "window", "fire_door", "fire_window", "staircase", "corridor", "fire_lane"}  # 赋值


class YOLODetectionIntegrator:
    """YOLO 图元检测集成器"""

    def __init__(self, model_path: Optional[str] = None):
        self._model = None  # 赋值
        self._model_path = model_path  # 赋值
        self._loaded = False  # 赋值

    def load_model(self, model_path: Optional[str] = None) -> bool:
        """加载 YOLO 模型"""
        if self._loaded:  # 条件判断
            return True  # 返回

        path = model_path or self._model_path  # 赋值
        if not path:  # 条件判断
            # 默认路径：从项目目录找最新训练的best.pt
            project_root = Path(__file__).resolve().parent.parent.parent  # 赋值
            candidates = [  # 赋值
                project_root / "data" / "models" / "baa_yolov8n_v3" / "weights" / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n_v2" / "weights" / "best.pt",
                project_root / "runs" / "detect" / "data" / "models" / "baa_yolov8n_v2-3" / "weights" / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n" / "weights" / "best.pt",
            ]
            for c in candidates:  # 循环
                if c.exists():  # 条件判断
                    path = str(c)  # 赋值
                    break  # 跳出循环

        if not path or not os.path.exists(path):  # 条件判断
            return False  # 返回

        try:  # 尝试
            from ultralytics import YOLO
            self._model = YOLO(str(path))  # 赋值
            self._model_path = str(path)  # 赋值
            self._loaded = True  # 赋值
            return True  # 返回
        except Exception:  # 捕获异常
            return False  # 返回

    def is_loaded(self) -> bool:
        return self._loaded  # 返回

    def predict(self, image_path: str, conf: float = 0.25, iou: float = 0.5) -> List[Dict[str, Any]]:
        """对单张图纸图像执行 YOLO 预测

        返回:
            List[Dict]: 每个检测结果包含
                - type: str (实体类型)
                - confidence: float
                - bbox: {"x", "y", "width", "height"} (像素坐标)
                - properties: dict (额外属性)
        """
        if not self._loaded:  # 条件判断
            if not self.load_model():  # 条件判断
                return []  # 返回

        results = self._model.predict(  # 赋值
            source=image_path,  # 赋值
            conf=conf,  # 赋值
            iou=iou,  # 赋值
            verbose=False,  # 赋值
        )

        detections = []  # 赋值
        for result in results:  # 循环
            if result.boxes is None:  # 条件判断
                continue  # 继续循环
            for box in result.boxes:  # 循环
                cls_id = int(box.cls[0].item())  # 赋值
                if cls_id >= len(YOLO_CLASSES):  # 条件判断
                    continue  # 继续循环
                confidence = box.conf[0].item()  # 赋值
                xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                x1, y1, x2, y2 = xyxy  # 赋值

                entity_type = YOLO_CLASSES[cls_id]  # 赋值
                bbox = {  # 赋值
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1,
                    "height": y2 - y1,
                }

                props = {"confidence": confidence}  # 赋值

                # 估算面积
                if entity_type in AREA_CLASSES:  # 条件判断
                    props["area"] = bbox["width"] * bbox["height"]

                # 估算宽度（取短边作为"宽度"参考）
                if entity_type in WIDTH_CLASSES:  # 条件判断
                    props["width"] = min(bbox["width"], bbox["height"])
                    props["clear_width"] = props["width"]

                detections.append({  # 调用
                    "type": entity_type,
                    "confidence": confidence,
                    "bbox": bbox,
                    "properties": props,
                })

        return detections  # 返回

    def render_and_predict(self, dxf_path: str, dpi: int = 100) -> Tuple[Optional[str], List[Dict]]:
        """渲染 DXF 为图像 → 执行 YOLO 预测

        返回:
            (image_path, detections)
        """
        image_path = self._render_dxf(dxf_path, dpi)  # 赋值
        if image_path is None:  # 条件判断
            return None, []  # 返回
        detections = self.predict(image_path)  # 赋值
        return image_path, detections  # 返回

    def detections_to_entities(self, detections: List[Dict],
                                world_bbox: Optional[Dict] = None,
                                image_size: Tuple[int, int] = (640, 640)) -> List[Dict]:
        """将 YOLO 检测结果映射为引擎实体格式

        参数:
            detections: predict() 返回的检测列表
            world_bbox: DXF 的世界坐标边界 {"x","y","width","height"}
                        如果提供，将像素坐标映射回世界坐标
            image_size: 图像尺寸 (w, h)

        返回:
            List[Dict]: 与 deconstruct API 的 elements 格式一致
        """
        img_w, img_h = image_size  # 赋值
        entities = []  # 赋值

        for det in detections:  # 循环
            px = det["bbox"]["x"]  # 赋值
            py = det["bbox"]["y"]  # 赋值
            pw = det["bbox"]["width"]  # 赋值
            ph = det["bbox"]["height"]  # 赋值

            if world_bbox:  # 条件判断
                # 像素坐标 → 世界坐标
                scale_x = world_bbox["width"] / img_w  # 赋值
                scale_y = world_bbox["height"] / img_h  # 赋值
                wx = world_bbox["x"] + px * scale_x  # 赋值
                wy = world_bbox["y"] + py * scale_y  # 赋值
                ww = pw * scale_x  # 赋值
                wh = ph * scale_y  # 赋值
            else:  # 否则
                wx, wy, ww, wh = px, py, pw, ph  # 赋值

            entity = {  # 赋值
                "type": det["type"],
                "count": 1,
                "bbox": {"x": wx, "y": wy, "width": ww, "height": wh},
                "properties": {
                    **det["properties"],
                    "detection_source": "yolo",
                },
            }

            # 合并同名实体的计数
            existing = None  # 赋值
            for e in entities:  # 循环
                if e["type"] == det["type"] and e.get("properties", {}).get("detection_source") == "yolo":  # 条件判断
                    existing = e  # 赋值
                    break  # 跳出循环

            if existing:  # 条件判断
                existing["count"] += 1
            else:  # 否则
                entities.append(entity)  # 调用

        return entities  # 返回

    def _render_dxf(self, dxf_path: str, dpi: int = 100) -> Optional[str]:
        """将 DXF 渲染为 JPG 图像（同训练数据准备逻辑）"""
        import ezdxf
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import tempfile

        try:  # 尝试
            doc = ezdxf.readfile(dxf_path)  # 赋值
            msp = doc.modelspace()  # 赋值
        except Exception:  # 捕获异常
            return None  # 返回

        # 计算边界
        all_x, all_y = [], []  # 赋值
        for entity in msp:  # 循环
            try:  # 尝试
                if entity.dxftype() == "LINE":  # 条件判断
                    s, e = entity.dxf.start, entity.dxf.end  # 赋值
                    all_x.extend([s[0], e[0]])  # 调用
                    all_y.extend([s[1], e[1]])  # 调用
                elif entity.dxftype() == "LWPOLYLINE":  # 分支
                    pts = [(v[0], v[1]) for v in entity.get_points()]  # 赋值
                    all_x.extend(p[0] for p in pts)  # 调用
                    all_y.extend(p[1] for p in pts)  # 调用
                elif entity.dxftype() == "CIRCLE":  # 分支
                    cx, cy = entity.dxf.center[:2]  # 赋值
                    r = entity.dxf.radius  # 赋值
                    all_x.extend([cx - r, cx + r])  # 调用
                    all_y.extend([cy - r, cy + r])  # 调用
                elif entity.dxftype() in ("TEXT", "MTEXT"):  # 分支
                    ins = entity.dxf.insert[:2]  # 赋值
                    all_x.append(ins[0])  # 调用
                    all_y.append(ins[1])  # 调用
            except Exception:  # 捕获异常
                continue  # 继续循环

        if not all_x:  # 条件判断
            return None  # 返回

        margin = 2.0  # 赋值
        x_min, x_max = min(all_x) - margin, max(all_x) + margin  # 解包
        y_min, y_max = min(all_y) - margin, max(all_y) + margin  # 解包

        fig_w = max(x_max - x_min, 1) * 0.4  # 赋值
        fig_h = max(y_max - y_min, 1) * 0.4  # 赋值
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)  # 赋值
        ax.set_xlim(x_min, x_max)  # 调用
        ax.set_ylim(y_min, y_max)  # 调用
        ax.set_aspect('equal')
        ax.axis('off')

        for entity in msp:  # 循环
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''  # 赋值
            if layer.upper() == "META":  # 条件判断
                continue  # 继续循环
            dxftype = entity.dxftype()  # 赋值
            try:  # 尝试
                if dxftype == "LINE":  # 条件判断
                    s, e = entity.dxf.start, entity.dxf.end  # 赋值
                    ax.plot([s[0], e[0]], [s[1], e[1]], 'k-', linewidth=0.3)  # 调用
                elif dxftype == "LWPOLYLINE":  # 分支
                    pts = [(v[0], v[1]) for v in entity.get_points()]  # 赋值
                    xs, ys = zip(*pts)  # 赋值
                    ax.plot(xs, ys, 'k-', linewidth=0.3)  # 调用
                elif dxftype == "CIRCLE":  # 分支
                    cx, cy = entity.dxf.center[:2]  # 赋值
                    r = entity.dxf.radius  # 赋值
                    ax.add_patch(plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.3))  # 调用
                elif dxftype == "ARC":  # 分支
                    cx, cy = entity.dxf.center[:2]  # 赋值
                    r = entity.dxf.radius  # 赋值
                    ax.add_patch(plt.Arc((cx, cy), r*2, r*2, angle=0,  # 赋值
                                          theta1=entity.dxf.start_angle,  # 赋值
                                          theta2=entity.dxf.end_angle,  # 赋值
                                          color='k', linewidth=0.3))  # 赋值
            except Exception:  # 捕获异常
                continue  # 继续循环

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)  # 赋值
        tmp_path = tmp.name  # 赋值
        tmp.close()  # 调用
        plt.savefig(tmp_path, dpi=dpi, bbox_inches='tight', pad_inches=0.05, facecolor='white')  # 调用
        plt.close(fig)  # 调用
        return tmp_path  # 返回
