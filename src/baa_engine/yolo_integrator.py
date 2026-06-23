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

YOLO_CLASSES = [
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
AREA_CLASSES = {"room", "fire_zone", "wall"}

# 哪些类别有宽度属性（门/窗/楼梯/走廊等）
WIDTH_CLASSES = {"door", "window", "fire_door", "fire_window", "staircase", "corridor", "fire_lane"}


class YOLODetectionIntegrator:
    """YOLO 图元检测集成器"""

    def __init__(self, model_path: Optional[str] = None):
        self._model = None
        self._model_path = model_path
        self._loaded = False

    def load_model(self, model_path: Optional[str] = None) -> bool:
        """加载 YOLO 模型"""
        if self._loaded:
            return True

        path = model_path or self._model_path
        if not path:
            # 默认路径：从项目目录找最新训练的best.pt
            project_root = Path(__file__).resolve().parent.parent.parent
            candidates = [
                project_root / "data" / "models" / "baa_yolov8n_v3" / "weights" / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n_v2" / "weights" / "best.pt",
                project_root / "runs" / "detect" / "data" / "models" / "baa_yolov8n_v2-3" / "weights" / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n" / "weights" / "best.pt",
            ]
            for c in candidates:
                if c.exists():
                    path = str(c)
                    break

        if not path or not os.path.exists(path):
            return False

        try:
            from ultralytics import YOLO
            self._model = YOLO(str(path))
            self._model_path = str(path)
            self._loaded = True
            return True
        except Exception:
            return False

    def is_loaded(self) -> bool:
        return self._loaded

    def predict(self, image_path: str, conf: float = 0.25, iou: float = 0.5) -> List[Dict[str, Any]]:
        """对单张图纸图像执行 YOLO 预测

        返回:
            List[Dict]: 每个检测结果包含
                - type: str (实体类型)
                - confidence: float
                - bbox: {"x", "y", "width", "height"} (像素坐标)
                - properties: dict (额外属性)
        """
        if not self._loaded:
            if not self.load_model():
                return []

        results = self._model.predict(
            source=image_path,
            conf=conf,
            iou=iou,
            verbose=False,
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                if cls_id >= len(YOLO_CLASSES):
                    continue
                confidence = box.conf[0].item()
                xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                x1, y1, x2, y2 = xyxy

                entity_type = YOLO_CLASSES[cls_id]
                bbox = {
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1,
                    "height": y2 - y1,
                }

                props = {"confidence": confidence}

                # 估算面积
                if entity_type in AREA_CLASSES:
                    props["area"] = bbox["width"] * bbox["height"]

                # 估算宽度（取短边作为"宽度"参考）
                if entity_type in WIDTH_CLASSES:
                    props["width"] = min(bbox["width"], bbox["height"])
                    props["clear_width"] = props["width"]

                detections.append({
                    "type": entity_type,
                    "confidence": confidence,
                    "bbox": bbox,
                    "properties": props,
                })

        return detections

    def render_and_predict(self, dxf_path: str, dpi: int = 100) -> Tuple[Optional[str], List[Dict]]:
        """渲染 DXF 为图像 → 执行 YOLO 预测

        返回:
            (image_path, detections)
        """
        image_path = self._render_dxf(dxf_path, dpi)
        if image_path is None:
            return None, []
        detections = self.predict(image_path)
        return image_path, detections

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
        img_w, img_h = image_size
        entities = []

        for det in detections:
            px = det["bbox"]["x"]
            py = det["bbox"]["y"]
            pw = det["bbox"]["width"]
            ph = det["bbox"]["height"]

            if world_bbox:
                # 像素坐标 → 世界坐标
                scale_x = world_bbox["width"] / img_w
                scale_y = world_bbox["height"] / img_h
                wx = world_bbox["x"] + px * scale_x
                wy = world_bbox["y"] + py * scale_y
                ww = pw * scale_x
                wh = ph * scale_y
            else:
                wx, wy, ww, wh = px, py, pw, ph

            entity = {
                "type": det["type"],
                "count": 1,
                "bbox": {"x": wx, "y": wy, "width": ww, "height": wh},
                "properties": {
                    **det["properties"],
                    "detection_source": "yolo",
                },
            }

            # 合并同名实体的计数
            existing = None
            for e in entities:
                if e["type"] == det["type"] and e.get("properties", {}).get("detection_source") == "yolo":
                    existing = e
                    break

            if existing:
                existing["count"] += 1
            else:
                entities.append(entity)

        return entities

    def _render_dxf(self, dxf_path: str, dpi: int = 100) -> Optional[str]:
        """将 DXF 渲染为 JPG 图像（同训练数据准备逻辑）"""
        import ezdxf
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import tempfile

        try:
            doc = ezdxf.readfile(dxf_path)
            msp = doc.modelspace()
        except Exception:
            return None

        # 计算边界
        all_x, all_y = [], []
        for entity in msp:
            try:
                if entity.dxftype() == "LINE":
                    s, e = entity.dxf.start, entity.dxf.end
                    all_x.extend([s[0], e[0]])
                    all_y.extend([s[1], e[1]])
                elif entity.dxftype() == "LWPOLYLINE":
                    pts = [(v[0], v[1]) for v in entity.get_points()]
                    all_x.extend(p[0] for p in pts)
                    all_y.extend(p[1] for p in pts)
                elif entity.dxftype() == "CIRCLE":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    all_x.extend([cx - r, cx + r])
                    all_y.extend([cy - r, cy + r])
                elif entity.dxftype() in ("TEXT", "MTEXT"):
                    ins = entity.dxf.insert[:2]
                    all_x.append(ins[0])
                    all_y.append(ins[1])
            except Exception:
                continue

        if not all_x:
            return None

        margin = 2.0
        x_min, x_max = min(all_x) - margin, max(all_x) + margin
        y_min, y_max = min(all_y) - margin, max(all_y) + margin

        fig_w = max(x_max - x_min, 1) * 0.4
        fig_h = max(y_max - y_min, 1) * 0.4
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect('equal')
        ax.axis('off')

        for entity in msp:
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''
            if layer.upper() == "META":
                continue
            dxftype = entity.dxftype()
            try:
                if dxftype == "LINE":
                    s, e = entity.dxf.start, entity.dxf.end
                    ax.plot([s[0], e[0]], [s[1], e[1]], 'k-', linewidth=0.3)
                elif dxftype == "LWPOLYLINE":
                    pts = [(v[0], v[1]) for v in entity.get_points()]
                    xs, ys = zip(*pts)
                    ax.plot(xs, ys, 'k-', linewidth=0.3)
                elif dxftype == "CIRCLE":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    ax.add_patch(plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.3))
                elif dxftype == "ARC":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    ax.add_patch(plt.Arc((cx, cy), r*2, r*2, angle=0,
                                          theta1=entity.dxf.start_angle,
                                          theta2=entity.dxf.end_angle,
                                          color='k', linewidth=0.3))
            except Exception:
                continue

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp_path = tmp.name
        tmp.close()
        plt.savefig(tmp_path, dpi=dpi, bbox_inches='tight', pad_inches=0.05, facecolor='white')
        plt.close(fig)
        return tmp_path
