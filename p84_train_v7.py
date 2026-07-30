"""
P84 — YOLO 模型重训练（v7）
- 基于 baa_yolov8m_v6-2 继续训练（resuming from best.pt）
- class_weight 强化低召回类
- epochs=50（中期检查），后续可扩展至 100
"""
from ultralytics import YOLO

WEIGHTS = 'runs/detect/data/models/baa_yolov8m_v6-2/weights/best.pt'
DATA = 'data/coco_v2_aug/data.yaml'
PROJECT = 'runs/detect'
NAME = 'v7_v2_50epoch'
OUTPUT_DIR = f'{PROJECT}/{NAME}'

# ── 类别权重 ──────────────────────────────
# 按诊断结果加权：0% 召回类 3.0x，<35% 类 2.0x，<70% 类 1.5x
class_weights = {
    0:  1.0,   # wall
    1:  1.5,   # door
    2:  1.5,   # window
    3:  0.9,   # staircase
    4:  1.0,   # corridor
    5:  2.0,   # fire_door
    6:  1.5,   # exit
    7:  2.0,   # fire_lane
    8:  0.9,   # fire_zone
    9:  2.0,   # fire_window
    10: 3.0,   # shaft (0%)
    11: 0.8,   # room (over-detects)
    12: 3.0,   # exit_sign (0%)
    13: 2.0,   # sprinkler_system
    14: 1.5,   # fire_alarm
    15: 1.0,   # insulation
    16: 3.0,   # evacuation_lighting (0%)
    17: 3.0,   # refuge_floor
}

model = YOLO(WEIGHTS)
print(f'Loaded: {WEIGHTS}')
print(f'Total params: {sum(p.numel() for p in model.model.parameters()):,}')

model.train(
    data=DATA,
    epochs=50,
    batch=16,
    imgsz=640,
    device='cpu',
    optimizer='SGD',
    lr0=0.01,
    lrf=0.01,
    momentum=0.937,
    weight_decay=0.0005,
    warmup_epochs=3.0,
    patience=15,
    amp=False,
    save=True,
    save_period=5,
    save_json=True,
    project=PROJECT,
    name=NAME,
    box=1.75,
    cls=0.5,
    dfl=1.5,
    hsv_h=0.015,
    hsv_s=0.7,
    hsv_v=0.4,
    degrees=0.0,
    translate=0.1,
    scale=0.5,
    shear=0.0,
    perspective=0.0,
    flipud=0.0,
    fliplr=0.5,
    mosaic=1.0,
    mixup=0.15,
    copy_paste=0.0,
    auto_augment='randaugment',
    erasing=0.4,
)
print('Training complete')
