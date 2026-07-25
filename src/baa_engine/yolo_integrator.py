"""
BAA YOLO 图元检测集成器
=========================
将 YOLOv8 预测结果映射到 BAA 引擎的 SemanticEntity 格式。

设计原则：
1. YOLO 检测作为规则解析的增强，不替代
2. 检测框 + 类别 → 结构化实体（bbox/properties）
3. 支持渲染图像、运行预测、结果映射全链路
"""

import logging
import math
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 类别映射 ──────────────────────────────────────────────

# YOLO 类别索引 → 语义类型名称
# 顺序必须与训练时的 data.yaml 一致，否则 cls_id 会映射到错误类型
YOLO_CLASSES = [
    "wall",  # 0
    "door",  # 1
    "window",  # 2
    "staircase",  # 3
    "corridor",  # 4
    "fire_door",  # 5
    "exit",  # 6
    "fire_lane",  # 7
    "fire_zone",  # 8
    "fire_window",  # 9
    "shaft",  # 10
    "room",  # 11
    "exit_sign",  # 12
    "sprinkler_system",  # 13
    "fire_alarm",  # 14
    "insulation",  # 15
    "evacuation_lighting",  # 16
    "refuge_floor",  # 17
]

# 需要面积估算的类别：这些实体的面积属性在后续消防规范校验中至关重要
# room：判定房间面积是否满足疏散要求
# fire_zone：防火分区面积上限校验
# wall：墙体面积辅助判断是否承重墙
AREA_CLASSES = {"room", "fire_zone", "wall"}  # AREA_CLASSES: 赋值

# 需要宽度属性的类别：这些实体的净宽是消防通道/疏散出口的核心参数
# 门/窗/楼梯/走廊/消防车道 的宽度直接影响《建筑设计防火规范》合规性
WIDTH_CLASSES = {
    "door",
    "window",
    "fire_door",
    "fire_window",
    "staircase",
    "corridor",
    "fire_lane",
}  # WIDTH_CLASSES: 赋值


class YOLODetectionIntegrator:
    """YOLO 图元检测集成器

    核心职责：
    1. 加载 YOLOv8 检测模型（ultralytics）
    2. 对渲染后的图纸图像执行推理
    3. 将检测结果映射为引擎可消费的实体格式
    4. 后置规则过滤（filter_yolo_detections）

    使用链路：
        load_model() → render_and_predict() → detections_to_entities()  # call: load_model()
    """

    def __init__(self, model_path: Optional[str] = None, device: str = "cpu"):
        """初始化 YOLO 集成器

        Args:
            model_path: YOLO 模型权重路径，为 None 时自动查找最新版本
            device: 推理设备，默认 cpu；预留 "xpu" 用于 Intel Arc GPU
        """
        self._model = None  # 模型实例初始化为 None
        self._model_path = model_path  # 保存传入的模型路径
        self._loaded = False  # 加载状态初始化为 False
        # device 参数预留用于 Intel Arc GPU（xpu）加速
        # 当前默认为 cpu 以避免 CUDA 环境依赖问题
        self._device = device  # _device: 赋值

    def load_model(self, model_path: Optional[str] = None) -> bool:
        """加载 YOLO 模型

        支持多个候选路径的原因是训练迭代过程中模型版本会递增，
        但调用方不需要关心具体版本号，自动查找最新的可用模型。
        """
        if self._loaded:
            return True  # return: True

        path = model_path or self._model_path  # path: 赋值
        if not path:  # check: if not path
            # 默认路径：从项目根目录按版本优先级查找 best.pt
            # 优先级：v6(m) > v4(n) > v3(n) > v2-3(n) > v2(n) > v1(n)
            # v6 为最新模型（YOLOv8m，800 样本增强，mAP50=0.572）
            project_root = Path(__file__).resolve().parent.parent.parent  # project_root: 赋值
            candidates = [
                project_root
                / "runs"
                / "detect"
                / "data"
                / "models"
                / "baa_yolov8m_v6-2"
                / "weights"
                / "best.pt",
                project_root
                / "runs"
                / "detect"
                / "runs"
                / "train"
                / "baa_yolov8n_v4"
                / "weights"
                / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n_v3" / "weights" / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n_v2" / "weights" / "best.pt",
                project_root
                / "runs"
                / "detect"
                / "data"
                / "models"
                / "baa_yolov8n_v2-3"
                / "weights"
                / "best.pt",
                project_root / "data" / "models" / "baa_yolov8n" / "weights" / "best.pt",
            ]
            for c in candidates:  # 遍历候选路径，取第一个存在的
                if c.exists():  # check: if c.exists()
                    path = str(c)  # path: 赋值
                    break

        if not path or not os.path.exists(path):  # 无可用模型文件
            return False  # return: False

        try:  # 延迟导入，避免启动时依赖失败
            from ultralytics import YOLO  # 延迟导入：只在需要时才加载 ultralytics

            # 禁用 CUDA：当前环境（WSL2）无物理 GPU 且 PyTorch CUDA 版本与 Intel Arc 不兼容
            # CUDA_VISIBLE_DEVICES='-1' 强制 YOLO 使用 CPU 推理，避免 CUDA OOM 或驱动错误
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # 强制 CPU 推理，避免 CUDA 兼容问题
            self._model = YOLO(str(path), task="detect")  # 创建 YOLO 模型实例
            self._model_path = str(path)  # 记录实际加载的路径
            self._loaded = True  # 标记加载成功
            return True  # return: True
        except Exception:  # 加载失败静默返回
            return False  # return: False

    def is_loaded(self) -> bool:
        """检查 YOLO 模型是否已成功加载

        调用 predict 前应检查此返回值，
        若为 False 则 predict 会返回空列表。
        """
        return self._loaded  # return: self._loaded

    def predict(
        self,
        image_path: str,
        conf: float = 0.15,
        iou: float = 0.5,  # self, image_path: str, conf: float: 赋值
    ) -> List[Dict[str, Any]]:
        """对单张图纸图像执行 YOLO 预测

        参数说明：
            conf=0.15：置信度阈值，低于此值的检测框被丢弃  # conf: 赋值
                      v6 模型（YOLOv8m，800 样本增强，mAP50=0.572）在真实图纸上
                      大量真实检测的置信度集中在 0.05-0.20 之间（训练图 640×640 满铺元素，
                      真实图纸渲染后仅 0.2% 非白像素，分布差异导致），
                      0.25 会严重漏检 door/window/staircase 等常见类别，
                      因此从 v6 开始默认降至 0.15，由后置规则过滤误检。
                      如果仍想保守过滤，可传 conf=0.25
            iou=0.5：NMS 的 IoU 阈值，用于抑制同一目标的重叠检测框  # iou: 赋值
                     0.5 是 YOLO 默认值，在建筑图纸上效果良好
            imgsz=640：推理图像尺寸，训练时也是 640x640  # imgsz: 赋值
                      更大的尺寸（如 1280）虽然可能提高小目标检测率，
                      但会大幅增加显存消耗和推理时间，在 CPU 推理场景下不可接受

        返回:
            List[Dict]: 每个检测结果包含
                - type: str (实体类型)  # call: - type: str ()
                - confidence: float
                - bbox: {"x", "y", "width", "height"} (像素坐标)  # call: - bbox: {"x", "y", "width", "height"} ()
                - properties: dict (额外属性)  # call: - properties: dict ()
        """
        if not self._loaded:  # 懒加载检查
            if not self.load_model():  # check: if not self.load_model()
                return []  # return: []

        results = self._model.predict(
            source=image_path,
            conf=conf,
            iou=iou,
            imgsz=640,  # 限制推理尺寸，防 OOM；CPU 推理 640x640 约 2-3 秒
            verbose=False,
        )

        detections = []  # 初始化检测结果列表
        for result in results:  # 遍历每个结果（通常只有一个）
            if result.boxes is None:  # check: if result.boxes is None
                continue
            for box in result.boxes:  # 遍历每个检测框
                cls_id = int(box.cls[0].item())  # 获取类别索引
                if cls_id >= len(YOLO_CLASSES):  # check: if cls_id >= len(YOLO_CLASSES)
                    # 忽略训练类别之外的意外输出，防止越界
                    continue
                confidence = box.conf[0].item()  # 获取置信度
                # xyxy 格式：[x1, y1, x2, y2]，像素坐标
                # 与 YOLO 训练时的标注格式一致，左上+右下角点
                xyxy = box.xyxy[0].tolist()  # 提取坐标列表
                x1, y1, x2, y2 = xyxy  # x1, y1, x2, y2: 赋值

                entity_type = YOLO_CLASSES[cls_id]  # 类别索引→语义类型
                bbox = {
                    "x": x1,
                    "y": y1,
                    "width": x2 - x1,  # 计算 bbox 宽度
                    "height": y2 - y1,  # 计算 bbox 高度
                }

                props = {"confidence": confidence}
                # 需要面积估算的类别
                # 面积估算：bbox 像素面积，后续映射到世界坐标后缩放
                # 用于 room/fire_zone 的面积合规性判断
                if entity_type in AREA_CLASSES:  # check: if entity_type in AREA_CLASSES
                    props["area"] = bbox["width"] * bbox["height"]  # props["area"]: 赋值

                # 宽度估算：取短边作为"宽度"参考
                # 因为建筑图纸中门/窗的 bbox 短边通常对应实际宽度，
                # 长边对应高度/长度。后续 DIMENSION 解析会修正精确值
                if entity_type in WIDTH_CLASSES:  # check: if entity_type in WIDTH_CLASSES
                    props["width"] = min(bbox["width"], bbox["height"])  # props["width"]: 赋值
                    props["clear_width"] = props["width"]  # props["clear_width"]: 赋值

                detections.append(
                    {
                        "type": entity_type,
                        "confidence": confidence,
                        "bbox": bbox,
                        "properties": props,
                    }
                )

        return detections  # return: detections

    def render_and_predict(self, dxf_path: str, dpi: int = 100) -> Tuple[Optional[str], List[Dict]]:
        """渲染 DXF 为图像 -> 执行 YOLO 预测

        dpi=100 是与训练数据生成一致的参数。  # dpi: 赋值
        太低（<72）会导致图纸线条模糊，影响小目标检测；
        太高（>200）会生成超大图像，显著增加推理时间。

        返回:
            (image_path, detections)  # call: ()
        """
        # 使用裁剪渲染：去除大面积空白背景，提升 YOLO 检测效果
        # v6 模型（mAP50=0.572）在裁剪后图像上置信度显著回升，无需继续降低 conf 阈值
        image_path = self._render_dxf_cropped(dxf_path, dpi)  # 裁剪渲染 DXF → YOLO 推理
        if image_path is None:
            return None, []  # 渲染失败则返回空
        detections = self.predict(image_path)  # YOLO 推理
        return image_path, detections  # return: image_path, detections

    def detections_to_entities(
        self,
        detections: List[Dict],
        world_bbox: Optional[Dict] = None,
        image_size: Tuple[int, int] = (640, 640),
    ) -> List[Dict]:
        """将 YOLO 检测结果映射为引擎实体格式

        像素坐标到世界坐标的映射原理：
        - YOLO 检测结果是在渲染图像（如 640x640）上的像素坐标
        - DXF 有真实的世界坐标系（如图纸上的 mm 或 m）
        - 通过 world_bbox（DXF 的渲染范围）和 image_size（图像尺寸），
          按比例将像素 bbox 线性映射回世界坐标
        - 这种线性映射的前提假设是渲染时保持了等比例缩放（aspect='equal'），  # - 这种线性映射的前提假设是渲染时保持了等比例缩放（aspect: 赋值
          否则需要额外的畸变校正

        参数:
            detections: predict() 返回的检测列表  # call: detections: predict()
            world_bbox: DXF 的世界坐标边界 {"x","y","width","height"}
                        如果提供，将像素坐标映射回世界坐标
            image_size: 图像尺寸 (w, h)  # call: image_size: 图像尺寸 ()

        返回:
            List[Dict]: 与 deconstruct API 的 elements 格式一致
        """
        img_w, img_h = image_size  # 图像尺寸
        entities = []  # 初始化输出实体列表

        for det in detections:  # loop: for det in detections
            px = det["bbox"]["x"]  # 像素坐标 x
            py = det["bbox"]["y"]  # 像素坐标 y
            pw = det["bbox"]["width"]  # 像素宽度
            ph = det["bbox"]["height"]  # 像素高度

            if world_bbox:  # check: if world_bbox
                # 线性映射：像素到世界坐标
                # scale_x/scale_y 是每像素对应的世界坐标单位数
                # 注意：如果渲染时 DXF 的 aspect ratio 与图像尺寸不成比例，
                # 这种映射会在 X/Y 方向产生不同的缩放比例，需要后续验证
                scale_x = world_bbox["width"] / img_w  # X 方向缩放比
                scale_y = world_bbox["height"] / img_h  # Y 方向缩放比
                wx = world_bbox["x"] + px * scale_x  # 世界坐标 x
                wy = world_bbox["y"] + py * scale_y  # 世界坐标 y
                ww = pw * scale_x  # 世界坐标宽度
                wh = ph * scale_y  # 世界坐标高度
            else:  # 无 world_bbox 时直接使用像素坐标
                wx, wy, ww, wh = px, py, pw, ph  # wx, wy, ww, wh: 赋值

            entity = {
                "type": det["type"],
                "count": 1,
                "bbox": {"x": wx, "y": wy, "width": ww, "height": wh},
                "properties": {
                    **det["properties"],
                    "detection_source": "yolo",  # 标记来源，供后续 DIMENSION 注入时判断是否覆盖
                },
            }

            # 合并同名实体的计数
            # 如果有多个同类型 YOLO 检测结果，合并 count 而非重复添加
            # 这样前端可以展示"3 个 door"而不是三个独立的 door 条目
            existing = None
            for e in entities:  # loop: for e in entities
                if (  # check: if (
                    e["type"] == det["type"]  # e["type"]: 赋值
                    and e.get("properties", {}).get("detection_source") == "yolo"  # get: 赋值
                ):
                    existing = e  # 同类型累加计数
                    break
            # 新类型追加到列表
            if existing:  # check: if existing
                existing["count"] += 1
            else:  # check: else
                entities.append(entity)  # call: append()

        return entities  # return: entities

    def _render_dxf(self, dxf_path: str, dpi: int = 100) -> Optional[str]:
        """将 DXF 渲染为 JPG 图像（同训练数据准备逻辑）

        使用 matplotlib 渲染而非 CAD 引擎是因为：
        1. 无需依赖 AutoCAD 或其他商业软件
        2. 与训练数据生成逻辑一致，保证推理时看到的图像分布与训练一致
        3. 支持 headless 渲染（matplotlib.use('Agg')），适合服务器环境  # call: use()

        跳过 META 图层：META 图层包含辅助标注信息（如尺寸标注的虚拟辅助线），
        渲染这些信息会引入图像噪声，干扰 YOLO 对实体轮廓的识别。
        """
        import ezdxf  # 延迟导入：只在渲染时才加载 ezdxf
        import matplotlib  # 延迟导入：避免 matplotlib 启动开销

        matplotlib.use("Agg")  # 设置无头渲染后端
        import matplotlib.pyplot as plt
        import tempfile

        try:  # 读取 DXF 文档
            doc = ezdxf.readfile(dxf_path)  # 获取模型空间
            msp = doc.modelspace()  # msp: 赋值
        except Exception:
            # DXF 损坏或非 DXF 文件：直接返回 None 交由上层处理
            return None  # return: None

        # 计算所有图元的最小外接矩形作为渲染边界
        # 不直接使用 DXF 的 extents 是因为有些图纸没有正确设置该属性
        all_x, all_y = [], []  # 遍历所有图元计算边界
        for entity in msp:  # loop: for entity in msp
            try:  # LINE 提取起点终点
                if entity.dxftype() == "LINE":  # check: if entity.dxftype() == "LINE"
                    s, e = entity.dxf.start, entity.dxf.end  # s, e: 赋值
                    all_x.extend([s[0], e[0]])  # call: extend()
                    all_y.extend([s[1], e[1]])  # LWPOLYLINE 提取所有顶点
                elif (
                    entity.dxftype() == "LWPOLYLINE"
                ):  # check: elif entity.dxftype() == "LWPOLYLINE"
                    pts = [(v[0], v[1]) for v in entity.get_points()]  # pts: 赋值
                    all_x.extend(p[0] for p in pts)  # call: extend()
                    all_y.extend(p[1] for p in pts)  # CIRCLE 用直径范围覆盖
                elif entity.dxftype() == "CIRCLE":  # check: elif entity.dxftype() == "CIRCLE"
                    cx, cy = entity.dxf.center[:2]  # cx, cy: 赋值
                    r = entity.dxf.radius
                    all_x.extend([cx - r, cx + r])  # call: extend()
                    all_y.extend([cy - r, cy + r])  # TEXT/MTEXT 仅插入点
                elif entity.dxftype() in (
                    "TEXT",
                    "MTEXT",
                ):  # check: elif entity.dxftype() in ("TEXT", "MTEXT")
                    ins = entity.dxf.insert[:2]  # ins: 赋值
                    all_x.append(ins[0])  # call: append()
                    all_y.append(ins[1])  # call: append()
            except Exception:
                continue
        # 无支持图元无法渲染
        if not all_x:  # check: if not all_x
            # 所有图元都被跳过（无支持类型的图元），无法计算渲染边界
            return None  # return: None
        # 添加边距避免贴边
        # 添加 2 单位边距，避免图元紧贴图像边缘导致 YOLO 检测框不完整
        margin = 2.0  # margin: 赋值
        x_min, x_max = min(all_x) - margin, max(all_x) + margin  # x_min, x_max: 赋值
        y_min, y_max = min(all_y) - margin, max(all_y) + margin  # y_min, y_max: 赋值

        fig_w = max(x_max - x_min, 1) * 0.4  # mm 转英寸
        fig_h = max(y_max - y_min, 1) * 0.4
        # 限制最大图像尺寸，防止 OOM（max 2048px）
        # CPU 推理大图会显著增加耗时，2048px 是经验平衡值
        max_pixels = 2048  # 限制最大像素防 OOM
        if (
            fig_w * dpi > max_pixels or fig_h * dpi > max_pixels
        ):  # check: if fig_w * dpi > max_pixels or fig_h * dpi > max_pixels
            scale = min(max_pixels / (fig_w * dpi), max_pixels / (fig_h * dpi))  # scale: 赋值
            fig_w *= scale  # 等比例缩小
            fig_h *= scale  # fig_h *: 赋值
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)  # 创建 matplotlib 图形
        ax.set_xlim(x_min, x_max)  # call: set_xlim()
        ax.set_ylim(y_min, y_max)  # call: set_ylim()
        ax.set_aspect("equal")  # 等比例：保证 YOLO bbox 形状在像素空间不失真
        ax.axis("off")  # 关闭坐标轴

        for entity in msp:  # 遍历图元渲染
            layer = entity.dxf.layer if hasattr(entity.dxf, "layer") else ""  # 获取图层名
            # 跳过 META 图层：该层包含尺寸辅助线等对 YOLO 检测无意义的元素
            if layer.upper() == "META":  # META 层辅助线干扰 YOLO
                continue
            dxftype = entity.dxftype()  # dxftype: 赋值
            try:
                if dxftype == "LINE":  # check: if dxftype == "LINE"
                    s, e = entity.dxf.start, entity.dxf.end  # s, e: 赋值
                    ax.plot([s[0], e[0]], [s[1], e[1]], "k-", linewidth=0.3)  # plot: 赋值
                elif dxftype == "LWPOLYLINE":  # check: elif dxftype == "LWPOLYLINE"
                    pts = [(v[0], v[1]) for v in entity.get_points()]  # pts: 赋值
                    xs, ys = zip(*pts)  # xs, ys: 赋值
                    ax.plot(xs, ys, "k-", linewidth=0.3)  # plot: 赋值
                elif dxftype == "CIRCLE":  # check: elif dxftype == "CIRCLE"
                    cx, cy = entity.dxf.center[:2]  # cx, cy: 赋值
                    r = entity.dxf.radius
                    ax.add_patch(
                        plt.Circle((cx, cy), r, fill=False, color="k", linewidth=0.3)
                    )  # Circle: 赋值
                elif dxftype == "ARC":  # check: elif dxftype == "ARC"
                    cx, cy = entity.dxf.center[:2]  # cx, cy: 赋值
                    r = entity.dxf.radius
                    ax.add_patch(
                        plt.Arc(
                            (cx, cy),  # call: ()
                            r * 2,
                            r * 2,
                            angle=0,
                            theta1=entity.dxf.start_angle,
                            theta2=entity.dxf.end_angle,
                            color="k",
                            linewidth=0.3,
                        )
                    )
            except Exception:
                # 单个图元渲染失败不影响整体：跳过该图元继续
                continue

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)  # 临时文件
        tmp_path = tmp.name  # 获取临时文件路径
        tmp.close()  # 关闭文件句柄，保存时可重新写入
        # bbox_inches="tight" + facecolor="white"：白底去除多余空白边距
        plt.savefig(
            tmp_path, dpi=dpi, bbox_inches="tight", pad_inches=0.05, facecolor="white"
        )  # savefig: 赋值
        plt.close(fig)  # call: close()
        return tmp_path  # return: tmp_path

    def _render_dxf_cropped(self, dxf_path: str, dpi: int = 100) -> Optional[str]:
        """渲染 DXF → 裁剪非空白区域 → 保存

        与 _render_dxf 相同流程，但额外对渲染后的图像做非空白像素裁剪，
        去除大面积的纯白背景，使 YOLO 推理时图像内容占比更高，
        有助于提升真实图纸（非白像素占比极低）的检测效果。
        """
        import numpy as np
        from PIL import Image

        # 先走标准渲染流程
        tmp_path = self._render_dxf(dxf_path, dpi)
        if tmp_path is None:
            return None

        try:
            img = Image.open(tmp_path).convert("RGB")
            arr = np.array(img)

            # 检测非白像素区域（RGB 三个通道不全为 255 的像素）
            # 容忍 250 阈值，避免抗锯齿边缘被误判为内容
            non_white = np.any(arr < 250, axis=-1)
            if not np.any(non_white):
                # 全白图像，无法裁剪，返回原图
                return tmp_path

            # 找到非白像素的行列范围
            rows = np.any(non_white, axis=1)
            cols = np.any(non_white, axis=0)
            y_min, y_max = np.where(rows)[0][[0, -1]]
            x_min, x_max = np.where(cols)[0][[0, -1]]

            # 裁剪到非白区域（加 2px 边距，避免线条贴边）
            margin = 2
            y_min = max(0, y_min - margin)
            y_max = min(img.height - 1, y_max + margin)
            x_min = max(0, x_min - margin)
            x_max = min(img.width - 1, x_max + margin)

            cropped = img.crop((x_min, y_min, x_max + 1, y_max + 1))

            # 保存到新临时文件
            tmp2 = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            cropped_path = tmp2.name
            tmp2.close()
            cropped.save(cropped_path, quality=95)

            # 删除原始未裁剪文件
            os.unlink(tmp_path)

            return cropped_path
        except Exception:
            # 裁剪失败时回退到原始渲染结果
            return tmp_path


# ── YOLO 后置过滤 ──────────────────────────────────────────


def _compute_iou(a: Dict, b: Dict) -> float:
    """计算两个 bbox 的 IoU（交并比）

      IoU 用于判断 YOLO 检测框之间的重叠程度，
      后续可用于 NMS 后处理或合并高度重叠的同类型检测框。  # 计算 X 轴重叠长度
    # 计算 Y 轴重叠长度
      返回值范围 [0, 1]，1 表示完全重合，0 表示无重叠。  # 计算并集面积
    """
    inter_x = max(
        0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"])
    )  # X 轴重叠长度
    inter_y = max(
        0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"])
    )  # Y 轴重叠长度
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter_x * inter_y  # 并集面积
    # 分母加 1 避免零除：当两个 bbox 完全不相交时 union 仍可能为 0（极端 case）
    return (inter_x * inter_y) / max(union, 1)  # return: (inter_x * inter_y) / max(union, 1)


def _compute_center(bbox: Dict) -> Tuple[float, float]:
    """计算 bbox 中心点坐标
    # 返回中心点坐标
      用于距离计算和贴近性校验，比直接用角点更稳定。
      返回 (cx, cy)。  # call: 返回 ()
    """
    return bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2  # 返回 (cx, cy)


def _point_to_segment_distance(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """点到线段的最短距离

    使用向量投影法计算，比点到直线距离更精确：
    当垂足在线段外时，返回点到最近端点的距离。
    用于判断 door/window 中心到墙体的贴近程度。

    参数说明：
        (px, py): 目标点坐标（如门/窗中心）  # call: ()
        (x1,y1)-(x2,y2): 线段端点坐标（如墙体线段）  # call: ()
    """
    dx, dy = x2 - x1, y2 - y1  # 计算线段向量
    if dx == 0 and dy == 0:  # 线段退化为点
        return math.hypot(px - x1, py - y1)  # 返回点到点距离
    # 投影参数 t：限制在 [0,1] 确保垂足落在线段内
    # 若投影落在端点外，直接返回端点距离（点到线段 vs 点到直线）
    t = max(
        0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy))
    )  # 投影参数，限制在 [0,1]
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))  # 返回点到线段最短距离


def filter_yolo_detections(
    detections: List[Dict],
    walls: Optional[List[Dict]] = None,
    min_corridor_width_m: float = 0.5,
    verbose: bool = False,
) -> List[Dict]:
    """YOLO 检测结果规则层后置兜底过滤

    策略（P25）：基于建筑规范常识的 5 条规则
    - 规则 1 corridor 宽度过滤：净宽 < 0.5m 不构成走廊（《建规》第 5.5 条）
    - 规则 2 door 方向校验：门必须贴墙安装，不贴墙的 door 检测框是误检
    - 规则 3 window 墙体对齐：窗必须在墙体开口处，远离墙体的 window 是误检
    - 规则 4 corridor 连续性：孤立走廊（无 door/room 相邻）标记为低置信度
    - 规则 5 room 宽高比合理性：宽高比 > 5 的房间在建筑设计中罕见，可能是 YOLO 将多个房间合并检测

    参数:
        detections: predict() 返回的检测列表  # call: detections: predict()
        walls: 可选的墙体线列表，每项为 {"x1","y1","x2","y2"}
        min_corridor_width_m: corridor 最小宽度阈值（米）
        verbose: 是否输出过滤日志  # 空输入直接返回

    返回:
        过滤后的检测列表，每条可能包含 added 或 suppressed 标记
    """
    if not detections:  # 使用传入的墙体线段
        return []  # return: []

    # 提取墙体 bbox 列表
    wall_bboxes = [d["bbox"] for d in detections if d["type"] == "wall"]  # 提取墙体 bbox 列表
    # 过滤原因（调试用）
    filtered: List[Dict] = []  # 过滤后结果列表

    for det in detections:  # loop: for det in detections
        etype = det["type"]  # etype: 赋值
        bbox = det["bbox"]  # bbox: 赋值
        w, h = bbox["width"], bbox["height"]  # 获取宽高
        cx, cy = _compute_center(bbox)  # 计算中心点
        keep = True  # 默认保留该检测
        suppression_reason = None  # 过滤原因（调试用）

        # ── 规则 1：走廊宽度过滤 ──
        # 建筑规范要求走廊净宽 >= 0.9m（居住建筑）或 >= 1.2m（公共建筑）
        # 这里用 0.5m 作为兜底下限，小于此值不可能是走廊
        # 取 min(w, h) 是因为 YOLO bbox 可能长宽颠倒（取决于渲染方向）
        if etype == "corridor":  # check: if etype == "corridor"
            width_m = min(w, h)  # width_m: 赋值
            if width_m < min_corridor_width_m:  # check: if width_m < min_corridor_width_m
                keep = False  # keep: 赋值
                suppression_reason = f"corridor_width={width_m:.2f}<{min_corridor_width_m:.2f}"
        # 规则 2：door 贴墙校验
        # ── 规则 2：door 方向校验（是否贴墙） ──
        # 门必须安装在墙体开口处，不贴墙的 door 检测框几乎可以肯定是 YOLO 误检
        # 阈值取 door_long_side * 2.0 和 door_short_side * 3.0 的较大值
        # 前者保证门的长边方向至少有一半与墙体重叠
        # 后者对窄门（如 600mm 宽的卫生间门）使用更宽松的距离判断
        if (
            etype in ("door", "fire_door") and keep
        ):  # check: if etype in ("door", "fire_door") and keep
            door_long_side = max(w, h)  # door_long_side: 赋值
            door_short_side = min(w, h)  # door_short_side: 赋值

            if wall_bboxes:  # 有墙体数据时才校验
                min_dist = min(
                    _point_to_segment_distance(
                        cx, cy, wb["x"], wb["y"], wb["x"] + wb["width"], wb["y"] + wb["height"]
                    )
                    for wb in wall_bboxes  # loop: for wb in wall_bboxes
                )  # 取到所有墙体的最短距离
                if min_dist > max(  # check: if min_dist > max(
                    door_long_side * 2.0, door_short_side * 3.0
                ):  # 门中心离墙体太远 → 误检
                    keep = False  # keep: 赋值
                    suppression_reason = (
                        f"door_wall_dist={min_dist:.1f}>threshold"  # suppression_reason: 赋值
                    )

        # ── 规则 3：window 墙体对齐 ──
        # 窗必须在墙体上开口，远离墙体的 window 检测是误检
        # 阈值取 window_long * 2.0：允许窗的中心在墙体两侧一个窗宽的范围内
        if etype == "window" and keep:  # check: if etype == "window" and keep
            if wall_bboxes:  # check: if wall_bboxes
                window_long = max(w, h)  # window_long: 赋值
                min_dist = min(
                    _point_to_segment_distance(
                        cx, cy, wb["x"], wb["y"], wb["x"] + wb["width"], wb["y"] + wb["height"]
                    )
                    for wb in wall_bboxes  # loop: for wb in wall_bboxes
                )
                if min_dist > window_long * 2.0:  # 规则 4：corridor 连续性
                    keep = False  # keep: 赋值
                    suppression_reason = (
                        f"window_wall_dist={min_dist:.1f}>threshold"  # suppression_reason: 赋值
                    )

        # ── 规则 4：corridor 连续性 ──
        # 走廊必须有 door/room 与之相邻，否则可能是楼梯间或其他非走廊空间
        # 只标记低置信度不直接过滤，保留给走廊推断逻辑做最终判断
        if etype == "corridor" and keep:  # check: if etype == "corridor" and keep
            adjacent_found = False  # 距离阈值 corridor 长边 3 倍
            for other in detections:  # loop: for other in detections
                if (
                    other["type"] in ("door", "room", "fire_door") and other is not det
                ):  # check: if other["type"] in ("door", "room", "fire_door") and o
                    ob = other["bbox"]  # ob: 赋值
                    ocx, ocy = _compute_center(ob)  # ocx, ocy: 赋值
                    dist = math.hypot(cx - ocx, cy - ocy)
                    # 距离阈值取 corridor 长边的 3 倍，确保覆盖相邻房间的距离范围
                    if dist < max(w, h) * 3.0:  # check: if dist < max(w, h) * 3.0
                        adjacent_found = True  # adjacent_found: 赋值
                        break
            if not adjacent_found:  # check: if not adjacent_found
                det["properties"]["corridor_low_confidence"] = True  # 规则 5：room 宽高比合理性
                if verbose:  # 宽高比 > 5 硬过滤
                    logger.debug(
                        f"corridor 孤立: {det.get("type")} @ ({cx:.1f},{cy:.1f})"
                    )  # call: debug()

        # ── 规则 5：room 宽高比/面积合理性 ──
        # 建筑设计中房间宽高比通常不超过 4:1（走廊除外，但走廊有独立类别）
        # 宽高比 > 5 通常是 YOLO 将多个房间合并为一个大 bbox 的结果
        # ── 规则 5：room 宽高比/面积合理性 ──
        # 建筑设计中房间宽高比通常不超过 4:1（走廊除外，但走廊有独立类别）
        # 宽高比 > 5 通常是 YOLO 将多个房间合并为一个大 bbox 的结果
        # 硬过滤 5:1，软标记 4:1，兼顾召回率与精确率
        if etype == "room" and keep:  # check: if etype == "room" and keep
            aspect = max(w, h) / max(h, w, 1)  # 保留通过过滤的检测
            if aspect > 5.0:  # check: if aspect > 5.0
                keep = False  # keep: 赋值
                suppression_reason = f"room_aspect_ratio={aspect:.1f}>5"  # suppression_reason: 赋值
            elif aspect > 4.0:  # check: elif aspect > 4.0
                # 宽高比 4~5 的标记为低置信，不做硬过滤
                det["properties"][
                    "room_low_confidence"
                ] = True  # det["properties"]["room_low_confidence"]: 赋值
                if verbose:  # check: if verbose
                    logger.debug(
                        f"room 宽高比异常: {aspect:.1f} @ ({cx:.1f},{cy:.1f})"
                    )  # call: debug()

        if keep:  # 保留通过过滤的检测
            filtered.append(det)  # call: append()
        elif verbose:  # check: elif verbose
            logger.debug(
                f"YOLO 过滤: {det["type"]} confidence={det["confidence"]:.3f} reason={suppression_reason}"  # f"YOLO 过滤: {det["type"]} confidence: 赋值
            )

    return filtered  # return: filtered
