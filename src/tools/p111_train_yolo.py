#!/usr/bin/env python3
"""
P111 YOLO 训练脚本 v2

修正 v1 关键 bug：v1 的 labeled8 yaml 导致 class ID 错配
  - 原标签 11 (room) 被当作 7 (fire_door)
  - 所有训练结果无效

v2 策略：使用原始 18 类全量训练，不删减类
  - 8 类有标注：正常训练
  - 8 类无标注：loss 会高但不会崩，后续扩样后重训
  - data.yaml 使用原始 data_labeled8 的绝对路径 + 原始 18 类 schema
"""

from ultralytics import YOLO
from pathlib import Path
from datetime import datetime

BASE = Path("data/p106_yolo_dataset/clean")
RUN_NAME = f"p111_yolov8n_v2_{datetime.now().strftime('%m%d_%H%M')}"


def generate_full18_yaml():
    """生成 18 类全量 data.yaml，标签文件保持原始 class ID"""
    train_txt = str((BASE / "train.txt").resolve())
    val_txt = str((BASE / "val.txt").resolve())
    yaml_path = BASE / "data_full18.yaml"

    content = f"""# P111 Clean Dataset — Full 18 Classes
# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
train: {train_txt}
val: {val_txt}

nc: 18
names:
  0: wall
  1: door
  2: window
  3: staircase
  4: corridor
  5: fire_door
  6: exit
  7: fire_lane
  8: fire_zone
  9: fire_window
  10: shaft
  11: room
  12: exit_sign
  13: sprinkler_system
  14: fire_alarm
  15: insulation
  16: evacuation_lighting
  17: refuge_floor
"""
    yaml_path.write_text(content, encoding="utf-8")
    return str(yaml_path.resolve())


def train():
    yaml_path = generate_full18_yaml()

    print("=" * 60)
    print(f"P111 YOLO Training v2 — yolov8n (18 classes)")
    print(f"Data YAML: {yaml_path}")
    print(f"Note: 8 classes have labels, 8 classes empty (will be filled)")
    print(f"Output: runs/detect/{RUN_NAME}")
    print("=" * 60)

    model = YOLO("yolov8n.pt")

    results = model.train(
        data=yaml_path,
        epochs=300,
        imgsz=512,
        batch=8,
        device="cpu",
        workers=4,
        name=RUN_NAME,
        patience=50,
        save_period=50,
        verbose=True,
    )

    print(f"\nTraining complete. Results: runs/detect/{RUN_NAME}")


if __name__ == "__main__":
    train()
