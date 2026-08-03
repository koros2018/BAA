"""
P84 — v7_v5: Resume v7_v4 with reduced batch/epochs to avoid SIGKILL.
"""
from ultralytics import YOLO

model = YOLO('runs/detect/runs/detect/v7_v4_finetune/weights/last.pt')

model.train(
    data='data/coco_v2_aug/data.yaml',
    epochs=10,
    batch=4,
    imgsz=640,
    device='cpu',
    workers=0,
    patience=3,
    save=True,
    save_period=2,
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

    project='runs/detect',
    name='v7_v5_finetune',
)
print('Training complete')
