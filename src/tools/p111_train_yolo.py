#!/usr/bin/env python3
"""
P111 YOLO 训练脚本 v1

训练策略：
1. 先训 yolov8n（8 个有标注类，300 epochs）
2. 验证 mAP50 达标后，再扩至 yolov8m（含 8 个缺失类需后续扩样）

当前数据：
- 111 张建筑平面图（88 train + 23 val）
- 8 类有标注：wall/door/window/staircase/corridor/shaft/room/fire_door
- 8 类缺失：fire_lane/fire_zone/exit_sign/sprinkler_system/fire_alarm/insulation/evacuation_lighting/refuge_floor

训练配置：
- model: yolov8n.pt
- epochs: 300
- imgsz: 512
- batch: 8
- device: cpu
"""

from ultralytics import YOLO
import os
import time
import json
from pathlib import Path
from datetime import datetime

BASE = Path("data/p106_yolo_dataset/clean")
DATA_YAML = str(BASE / "data.yaml")
OUTPUT_DIR = Path("runs/detect")
RUN_NAME = f"p111_yolov8n_v1_{datetime.now().strftime('%m%d_%H%M')}"

# 有标注的 8 类
LABELED_CLASSES = [
    "wall", "door", "window", "staircase", "corridor",
    "shaft", "room", "fire_door",
]

# 缺失 8 类（后续扩样时补充）
MISSING_CLASSES = [
    "fire_lane", "fire_zone", "exit_sign",
    "sprinkler_system", "fire_alarm", "insulation",
    "evacuation_lighting", "refuge_floor",
]


def generate_labeled_only_yaml():
    """生成只含 8 个有标注类的 data.yaml，避免训练浪费在空类上"""
    yaml_path = BASE / "data_labeled8.yaml"
    content = f"""# P111 Clean Dataset — Labeled 8 Classes Only
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
train: {BASE / 'images'}
val: {BASE / 'images'}

nc: 8
names:
  0: wall
  1: door
  2: window
  3: staircase
  4: corridor
  5: shaft
  6: room
  7: fire_door
"""
    yaml_path.write_text(content, encoding="utf-8")
    return str(yaml_path)


def train():
    yaml_path = generate_labeled_only_yaml()

    print("=" * 60)
    print(f"P111 YOLO Training — yolov8n")
    print(f"Data YAML: {yaml_path}")
    print(f"Classes: {LABELED_CLASSES}")
    print(f"Output: {OUTPUT_DIR / RUN_NAME}")
    print("=" * 60)

    # Load model
    model = YOLO("yolov8n.pt")

    # Train
    results = model.train(
        data=yaml_path,
        epochs=300,
        imgsz=512,
        batch=8,
        device="cpu",
        workers=4,
        name=RUN_NAME,
        patience=50,           # 提前停止耐心：50 epochs 无改善则停止
        save_period=50,         # 每 50 个 epoch 存一次
        verbose=True,
    )

    print("\nTraining complete.")
    print(f"Results saved to: {OUTPUT_DIR / RUN_NAME}")

    # Parse best metrics
    results_path = OUTPUT_DIR / RUN_NAME / "results.csv"
    if results_path.exists():
        print(f"\nResults CSV: {results_path}")
        # Read last line for final metrics
        with open(results_path) as f:
            lines = f.readlines()
            if len(lines) > 1:
                last = lines[-1].strip().split(",")
                if len(last) >= 10:
                    print(f"Last epoch metrics: {last[0]}")
                    for i, metric in enumerate(last[1:]):
                        try:
                            print(f"  {['epoch', 'train_box_loss', 'train_cls_loss', 'train_dfl_loss',
                                       'metrics/precision', 'metrics/recall', 'metrics/mAP50',
                                       'metrics/mAP50_95', 'val_box_loss', 'val_cls_loss', 'val_dfl_loss'][i]}: {float(metric):.4f}")
                        except (ValueError, IndexError):
                            pass


if __name__ == "__main__":
    train()