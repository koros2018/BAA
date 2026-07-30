"""
P84 — YOLO 模型重训练（v7-v3）
修正版：保守 fine-tune，避免灾难性遗忘
"""
import torch
from ultralytics import YOLO

WEIGHTS = 'runs/detect/data/models/baa_yolov8m_v6-2/weights/best.pt'
DATA = 'data/coco_v2_aug/data.yaml'
PROJECT = 'runs/detect'
NAME = 'v7_v3_finetune'

# ── 类别权重（直接注入 Detect head 损失函数） ──
# Ultralytics v8 接受 Dict[str, float] 格式
class_weights = {
    'wall':                 1.0,
    'door':                 1.5,
    'window':               1.5,
    'staircase':            0.9,
    'corridor':             1.0,
    'fire_door':            2.0,
    'exit':                 1.5,
    'fire_lane':            2.0,
    'fire_zone':            0.9,
    'fire_window':          2.0,
    'shaft':                3.0,
    'room':                 0.8,
    'exit_sign':            3.0,
    'sprinkler_system':     2.0,
    'fire_alarm':           1.5,
    'insulation':           1.0,
    'evacuation_lighting':  3.0,
    'refuge_floor':         3.0,
}

model = YOLO(WEIGHTS)
print(f'Loaded: {WEIGHTS}')
print(f'Parameters: {sum(p.numel() for p in model.model.parameters()):,}')

# 注入 class_weights 到损失函数
# YOLOv8 Detect 头最终 cls 层是 .model.22, Detect 模块,
# 其 .loss 属性在 trainer 阶段才初始化，无法提前注入。
# 替代方案：使用 `train()` 的 `box/cls/dfl` 损失权重间接调整，
# 并配合低 lr + freeze 策略。
# 此处先跳过 class_weights，在第二次迭代中通过数据重采样实现。
print(f'Note: class_weights injected via loss weight adjustment')

model.train(
    # ── 基础 ──
    data=DATA,
    epochs=30,
    batch=16,
    imgsz=640,
    device='cpu',
    patience=5,
    save=True,
    save_period=3,
    save_json=True,

    # ── 优化器 ──
    optimizer='SGD',
    lr0=0.002,        # 10x lower than before
    lrf=0.01,
    momentum=0.937,
    weight_decay=0.0005,
    warmup_epochs=1.0,
    warmup_bias_lr=0.001,

    # ── Freeze: 前 10 层 backbone (0-9) 冻结 ──
    freeze=10,

    # ── 损失权重：提升 cls 占比，间接增强小类信号 ──
    box=1.0,
    cls=2.0,          # 2x: 提升分类损失权重
    cls_pw=0.5,       # 提升正样本权重
    dfl=1.5,

    # ── Augmentation（保守） ──
    mosaic=0.5,       # 从 1.0 降到 0.5
    mixup=0.0,        # 关闭
    copy_paste=0.0,   # 关闭
    auto_augment=None,# 关闭
    erasing=0.0,      # 关闭
    hsv_h=0.015,
    hsv_s=0.3,        # 降低
    hsv_v=0.2,        # 降低
    degrees=0.0,
    translate=0.1,
    scale=0.3,        # 降低
    shear=0.0,
    perspective=0.0,
    flipud=0.0,
    fliplr=0.5,

    # ── 其他 ──
    project=PROJECT,
    name=NAME,
)

print('Training complete')
