#!/usr/bin/env python3
"""
P84 真实图纸 YOLO 推理基线
============================
用当前最佳模型对 11 张渲染后的真实图纸跑推理，
统计每类实体的检出数量，为后续重训练提供对比基线。

用法:
    python scripts/p84_baseline_inference.py
"""

import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

YOLO_CLASSES = [
    "wall", "door", "window", "staircase", "corridor",
    "fire_door", "exit", "fire_lane", "fire_zone", "fire_window",
    "shaft", "room", "exit_sign", "sprinkler_system",
    "fire_alarm", "insulation", "evacuation_lighting", "refuge_floor",
]

RENDER_DIR = PROJECT_ROOT / "data" / "real_renderings"


def find_best_model():
    """查找优先级最高的可用模型"""
    candidates = [
        PROJECT_ROOT / "runs" / "detect" / "data" / "models" / "baa_yolov8m_v6-2" / "weights" / "best.pt",
        PROJECT_ROOT / "runs" / "detect" / "runs" / "train" / "baa_yolov8n_v4" / "weights" / "best.pt",
        PROJECT_ROOT / "data" / "models" / "baa_yolov8n_v3" / "weights" / "best.pt",
        PROJECT_ROOT / "data" / "models" / "baa_yolov8n_v2" / "weights" / "best.pt",
        PROJECT_ROOT / "data" / "models" / "baa_yolov8n" / "weights" / "best.pt",
    ]
    for c in candidates:
        if c.exists():
            return c
    logger.error("未找到可用模型")
    sys.exit(1)


def run_baseline():
    model_path = find_best_model()
    logger.info(f"使用模型: {model_path.name}")

    from ultralytics import YOLO
    model = YOLO(str(model_path), task="detect")

    images = sorted(RENDER_DIR.glob("*.jpg"))
    logger.info(f"找到 {len(images)} 张渲染图")
    logger.info("")

    # 整体统计：按类别汇总
    total_by_class = defaultdict(int)
    # 逐图统计
    per_image = []

    for img_path in images:
        results = model.predict(
            str(img_path),
            conf=0.15,
            iou=0.45,
            imgsz=640,
            verbose=False,
        )
        by_class = defaultdict(int)
        total = 0
        for r in results:
            for cls_id in r.boxes.cls.int().tolist():
                if cls_id < len(YOLO_CLASSES):
                    by_class[YOLO_CLASSES[cls_id]] += 1
                    total += 1

        total_by_class.update(by_class)
        per_image.append({
            "file": img_path.name,
            "total": total,
            "by_class": dict(by_class),
        })

    # 输出逐图结果
    logger.info("=" * 70)
    logger.info(f"{'文件':<40} {'总数':>6}  检出类别")
    logger.info("-" * 70)
    for entry in per_image:
        cls_str = ", ".join(f"{k}:{v}" for k, v in sorted(entry["by_class"].items(), key=lambda x: -x[1]))
        logger.info(f"{entry['file']:<40} {entry['total']:>6}  {cls_str}")

    # 输出汇总
    logger.info("")
    logger.info("=" * 70)
    logger.info("汇总 (按类别, conf=0.15)")
    logger.info("-" * 70)
    total_all = sum(total_by_class.values())
    logger.info(f"{'类别':<25} {'数量':>8}")
    for cls in YOLO_CLASSES:
        n = total_by_class.get(cls, 0)
        if n > 0:
            logger.info(f"{cls:<25} {n:>8}")
    logger.info(f"{'总计':<25} {total_all:>8}")
    logger.info(f"模型: {model_path}")
    logger.info("=" * 70)

    return per_image, dict(total_by_class), str(model_path)


if __name__ == "__main__":
    run_baseline()
