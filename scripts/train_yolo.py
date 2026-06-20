"""
BAA YOLOv8 图元检测训练
LoRA微调支持（等真实图纸后激活）

用法：
  python3 scripts/train_yolo.py          # 基座训练（合成图纸）
  python3 scripts/train_yolo.py --lora   # LoRA微调（需要真实图纸）
"""
import argparse
import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def train_base():
    """合成图纸上训练基座模型"""
    print("=" * 50)
    print("BAA YOLOv8 基座训练")
    print("=" * 50)

    from ultralytics import YOLO

    # YOLOv8n - 轻量版，适合单机训练
    model = YOLO("yolov8n.pt")

    yaml_path = PROJECT_ROOT / "data" / "models" / "baa_yolo.yaml"

    results = model.train(
        data=str(yaml_path),
        epochs=20,
        imgsz=640,
        batch=8,
        device="cpu",  # WSL2无GPU，用CPU
        workers=1,
        patience=15,
        project=str(PROJECT_ROOT / "data" / "models"),
        name="baa_yolov8n",
        exist_ok=True,
        verbose=True,
        # 合成图纸数据增强
        hsv_h=0.015,
        hsv_s=0.4,
        hsv_v=0.4,
        degrees=10.0,
        translate=0.1,
        scale=0.5,
        shear=2.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,
        mosaic=0.5,
        mixup=0.1,
    )

    print(f"\n✅ 基座训练完成")
    print(f"   模型: {PROJECT_ROOT / 'data' / 'models' / 'baa_yolov8n' / 'weights' / 'best.pt'}")
    return model


def train_lora():
    """LoRA微调（需要真实图纸）"""
    print("=" * 50)
    print("BAA LoRA 微调")
    print("=" * 50)

    # 检查是否有真实图纸
    real_dir = PROJECT_ROOT / "data" / "drawings" / "real"
    real_files = list(real_dir.glob("*.dxf"))
    if not real_files:
        print("⚠️  未检测到真实图纸，跳过LoRA微调")
        print(f"   请将真实DXF图纸放入: {real_dir}")
        print("   然后重新运行: python3 scripts/train_yolo.py --lora")
        return None

    print(f"   真实图纸: {len(real_files)} 张")

    # 将真实图纸转为COCO格式
    from scripts.prepare_training_data import dxf_to_coco, COCO_DIR, CATEGORY_MAP
    import json

    lora_dir = COCO_DIR / "lora"
    lora_dir.mkdir(parents=True, exist_ok=True)
    (lora_dir / "labels").mkdir(parents=True, exist_ok=True)

    coco_out = {"images": [], "annotations": [], "categories": []}
    from scripts.prepare_training_data import COCO_CATEGORIES
    coco_out["categories"] = COCO_CATEGORIES

    img_id = 0
    ann_id = 0
    for dxf_path in real_files:
        result = dxf_to_coco(dxf_path)
        if result is None:
            continue
        result["images"][0]["id"] = img_id
        for ann in result["annotations"]:
            ann["image_id"] = img_id
            ann["id"] = ann_id
            ann_id += 1
        coco_out["images"].append(result["images"][0])
        coco_out["annotations"].extend(result["annotations"])
        img_id += 1

    with open(lora_dir / "_annotations.coco.json", "w") as f:
        json.dump(coco_out, f, ensure_ascii=False)

    print(f"   LoRA数据: {len(coco_out['images'])}张, {len(coco_out['annotations'])}个标注")

    # LoRA微调
    from ultralytics import YOLO

    base_model = PROJECT_ROOT / "data" / "models" / "baa_yolov8n" / "weights" / "best.pt"
    if not base_model.exists():
        print(f"⚠️  基座模型不存在，请先运行 python3 scripts/train_yolo.py")
        return None

    model = YOLO(str(base_model))

    # LoRA微调参数：低学习率+冻结前层
    results = model.train(
        data=str(PROJECT_ROOT / "data" / "models" / "baa_yolo.yaml"),
        epochs=30,
        imgsz=640,
        batch=4,
        device="cpu",
        workers=1,
        lr0=0.0001,
        lrf=0.01,
        warmup_epochs=1,
        freeze=10,  # 冻结前10层
        project=str(PROJECT_ROOT / "data" / "models"),
        name="baa_lora",
        exist_ok=True,
        verbose=True,
    )

    print(f"\n✅ LoRA微调完成")
    return model


def main():
    parser = argparse.ArgumentParser(description="BAA YOLOv8训练")
    parser.add_argument("--lora", action="store_true", help="LoRA微调模式")
    args = parser.parse_args()

    if args.lora:
        train_lora()
    else:
        train_base()


if __name__ == "__main__":
    main()
