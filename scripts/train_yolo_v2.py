#!/usr/bin/env python3
"""
BAA YOLOv8 图元检测训练 V2
============================
使用合成图纸V2 + 精确META标注训练YOLOv8n。
支持 CPU / XPU 两种设备。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import torch


def detect_device() -> str:
    """检测可用设备：优先XPU(Intel GPU)，然后CUDA，最后CPU"""
    # 尝试 Intel XPU (IPEX)
    try:
        import intel_extension_for_pytorch as ipex
        if torch.xpu.is_available():
            print(f"  ✅ 使用 Intel XPU: {torch.xpu.get_device_name(0)}")
            return "xpu"
    except ImportError:
        pass

    # 尝试 CUDA (NVIDIA)
    if torch.cuda.is_available():
        print(f"  ✅ 使用 CUDA: {torch.cuda.get_device_name(0)}")
        return "cuda"

    print(f"  ⚠️  无GPU可用，使用 CPU")
    print(f"  💡 如需GPU加速，可安装IPEX: pip install intel-extension-for-pytorch")
    return "cpu"


def train_base():
    """在合成图纸V2上训练基座模型"""
    print("=" * 50)
    print("BAA YOLOv8 基座训练 V2")
    print("=" * 50)

    from ultralytics import YOLO

    device = detect_device()
    yaml_path = PROJECT_ROOT / "data" / "models" / "baa_yolo_v2.yaml"

    if not yaml_path.exists():
        print(f"❌ 配置文件不存在: {yaml_path}")
        print(f"   请先运行: python3 scripts/prepare_training_data_v2.py")
        return

    # YOLOv8n - 轻量版
    model = YOLO("yolov8n.pt")

    # 训练参数
    train_kwargs = dict(
        data=str(yaml_path),
        epochs=50,
        imgsz=640,
        batch=8 if device == "cpu" else 16,
        device=device,
        workers=4,
        patience=20,
        project=str(PROJECT_ROOT / "data" / "models"),
        name="baa_yolov8n_v2",
        exist_ok=True,
        verbose=True,
        # 数据增强（合成图纸需要更多增强泛化）
        hsv_h=0.015,
        hsv_s=0.4,
        hsv_v=0.4,
        degrees=15.0,
        translate=0.2,
        scale=0.5,
        shear=5.0,
        flipud=0.1,
        fliplr=0.5,
        mosaic=0.8,
        mixup=0.2,
        copy_paste=0.1,
        # 学习率
        lr0=0.01,
        lrf=0.01,
        warmup_epochs=3,
        cos_lr=True,
    )

    results = model.train(**train_kwargs)

    best_pt = PROJECT_ROOT / "data" / "models" / "baa_yolov8n_v2" / "weights" / "best.pt"
    print(f"\n✅ 基座训练完成")
    print(f"   模型: {best_pt}")
    return model


def main():
    train_base()


if __name__ == "__main__":
    main()