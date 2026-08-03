"""
P84 — YOLO 模型重训练（v7-v4）
基于 v7_v3 保守 fine-tune + P81/P82/P83 LAYER_RULES 改进
核心：
  - lr0=0.002 (10x 降低)
  - freeze 前 10 层 backbone
  - mosaic=0.5, 关闭 mixup/copy_paste/erasing
  - cls=2.0 提升分类权重
  - batch=8 加速反馈
"""
from ultralytics import YOLO

WEIGHTS = 'runs/detect/data/models/baa_yolov8m_v6-2/weights/best.pt'
DATA = 'data/coco_v2_aug/data.yaml'
PROJECT = 'runs/detect'
NAME = 'v7_v4_finetune'

model = YOLO(WEIGHTS)
print(f'Loaded: {WEIGHTS}')
print(f'Parameters: {sum(p.numel() for p in model.model.parameters()):,}')

model.train(
    data=DATA,
    epochs=20,
    batch=8,
    imgsz=640,
    device='cpu',
    patience=5,
    save=True,
    save_period=3,
    save_json=True,

    optimizer='SGD',
    lr0=0.002,
    lrf=0.01,
    momentum=0.937,
    weight_decay=0.0005,
    warmup_epochs=1.0,
    warmup_bias_lr=0.001,

    freeze=10,

    box=1.0,
    cls=2.0,
    cls_pw=0.5,
    dfl=1.5,

    mosaic=0.5,
    mixup=0.0,
    copy_paste=0.0,
    auto_augment=None,
    erasing=0.0,
    hsv_h=0.015,
    hsv_s=0.3,
    hsv_v=0.2,
    degrees=0.0,
    translate=0.1,
    scale=0.3,
    shear=0.0,
    perspective=0.0,
    flipud=0.0,
    fliplr=0.5,

    project=PROJECT,
    name=NAME,
)
print('Training complete')
