#!/usr/bin/env python3
"""
YOLOv8 数据增强脚本（BAA 图元检测专用）
输出：aug/ 目录，包含旋转/缩放/亮度/Cutout/Mosaic 增强
用法：python3 scripts/prepare_yolo_augmented.py
"""
import os
import sys
import shutil
import random
import json
from pathlib import Path
from PIL import Image, ImageEnhance, ImageDraw
import numpy as np

# ── 配置 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
COCO_ROOT = PROJECT_ROOT / "data" / "coco_v2"
OUT_ROOT = PROJECT_ROOT / "data" / "coco_v2_aug"

# 增强配置
AUG_CONFIG = {
    "rotation": {"angle_range": (-15, 15), "probability": 0.5},
    "brightness": {"factor_range": (0.7, 1.3), "probability": 0.5},
    "contrast": {"factor_range": (0.8, 1.2), "probability": 0.4},
    "cutout": {"hole_size": (50, 150), "probability": 0.3},
    "mosaic": {"probability": 0.3},
    "scale": {"factor_range": (0.8, 1.2), "probability": 0.4},
}

# 每个原始图生成 3 张增强图
AUG_FACTOR = 3

# YOLO 类别顺序（与 baa_yolo_v2.yaml 一致）
CLASSES = [
    'wall', 'door', 'window', 'staircase', 'corridor',
    'fire_door', 'exit', 'fire_lane', 'fire_zone', 'fire_window',
    'shaft', 'room', 'exit_sign', 'sprinkler_system',
    'fire_alarm', 'insulation', 'evacuation_lighting', 'refuge_floor'
]


def load_coco_annotations(split):
    """加载 COCO 格式标注"""
    ann_path = COCO_ROOT / "labels" / f"{split}.json"
    if not ann_path.exists():
        print(f"[WARN] {split}.json 不存在，跳过")
        return []
    with open(ann_path) as f:
        return json.load(f)


def load_yolo_labels(split):
    """加载 YOLO 格式标注"""
    base = COCO_ROOT / "labels" / split
    if not base.exists():
        return {}
    labels = {}
    for fname in os.listdir(base):
        if fname.endswith('.txt'):
            img_name = fname.replace('.txt', '.jpg')
            with open(base / fname) as f:
                lines = f.read().strip().split('\n')
            boxes = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) == 5:
                    cls, x, y, w, h = map(float, parts)
                    boxes.append((int(cls), x, y, w, h))
            labels[img_name] = boxes
    return labels


def box_in_bounds(box, img_w, img_h):
    """检查边界框是否在图片范围内"""
    _, x, y, w, h = box
    x1 = (x - w / 2) * img_w
    y1 = (y - h / 2) * img_h
    x2 = (x + w / 2) * img_w
    y2 = (y + h / 2) * img_h
    return x1 > -10 and y1 > -10 and x2 < img_w + 10 and y2 < img_h + 10


def rotate_image(img, boxes, angle):
    """旋转图片并更新边界框"""
    img_rotated = img.rotate(angle, expand=True)
    new_boxes = []
    w, h = img.size
    new_w, new_h = img_rotated.size

    for cls, x, y, w_box, h_box in boxes:
        # 中心点转换
        cx = x * w
        cy = y * h
        # 旋转变换
        import math
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        new_cx = cx * cos_a - cy * sin_a
        new_cy = cx * sin_a + cy * cos_a
        # 归一化到新图片尺寸
        new_x = new_cx / new_w
        new_y = new_cy / new_h
        new_boxes.append((cls, new_x, new_y, w_box, h_box))
    return img_rotated, new_boxes


def random_brightness(img, factor_range):
    """随机亮度调整"""
    factor = random.uniform(*factor_range)
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(factor)


def random_contrast(img, factor_range):
    """随机对比度调整"""
    factor = random.uniform(*factor_range)
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(factor)


def cutout(img, holes=5):
    """Cutout 数据增强"""
    img_copy = img.copy()
    draw = ImageDraw.Draw(img_copy)
    w, h = img_copy.size
    for _ in range(holes):
        x1 = random.randint(0, w - 50)
        y1 = random.randint(0, h - 50)
        x2 = x1 + random.randint(50, min(150, w - x1))
        y2 = y1 + random.randint(50, min(150, h - y1))
        draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0))
    return img_copy


def mosaic(img, boxes, img_w, img_h, src_images, src_labels):
    """Mosaic 增强（4 张图拼接）"""
    half_w, half_h = img_w // 2, img_h // 2
    imgs = [img]
    labels = [boxes]
    
    # 从源数据随机选 3 张
    for _ in range(3):
        rand_key = random.choice(list(src_labels.keys()))
        rand_img = src_images.get(rand_key)
        rand_boxes = src_labels.get(rand_key, [])
        if rand_img:
            imgs.append(rand_img.resize((img_w, img_h), Image.Resampling.LANCZOS))
            labels.append(rand_boxes)
    
    # 拼接 4 张
    mosaic_img = Image.new('RGB', (img_w * 2, img_h * 2))
    positions = [(0, 0), (img_w, 0), (0, img_h), (img_w, img_h)]
    
    new_boxes = []
    for idx, ((pw, ph), img_src, src_boxes) in enumerate(zip(positions, imgs, labels)):
        mosaic_img.paste(img_src, (pw, ph))
        for cls, x, y, wb, hb in src_boxes:
            # 映射到拼接图
            new_x = (x * img_w + pw) / (img_w * 2)
            new_y = (y * img_h + ph) / (img_h * 2)
            new_w = wb / 2
            new_h = hb / 2
            new_boxes.append((cls, new_x, new_y, new_w, new_h))
    
    return mosaic_img, new_boxes


def augment_one(img_path, boxes, img_w, img_h, src_images, src_labels, aug_idx):
    """对一张图执行一组增强"""
    img = Image.open(img_path).convert('RGB')
    new_boxes = [b for b in boxes]
    
    # 随机选择增强组合
    for aug_type, cfg in AUG_CONFIG.items():
        if random.random() > cfg["probability"]:
            continue
        
        if aug_type == "rotation":
            angle = random.uniform(*cfg["angle_range"])
            img, new_boxes = rotate_image(img, new_boxes, angle)
        
        elif aug_type == "brightness":
            img = random_brightness(img, cfg["factor_range"])
        
        elif aug_type == "contrast":
            img = random_contrast(img, cfg["factor_range"])
        
        elif aug_type == "cutout":
            img = cutout(img)
        
        elif aug_type == "mosaic":
            img, new_boxes = mosaic(img, new_boxes, img_w, img_h, src_images, src_labels)
        
        elif aug_type == "scale":
            factor = random.uniform(*cfg["factor_range"])
            new_w, new_h = int(img_w * factor), int(img_h * factor)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            # 缩放边界框坐标
            new_boxes = [(cls, x / factor, y / factor, w_box, h_box) 
                        for cls, x, y, w_box, h_box in new_boxes]
    
    # 过滤出界框
    new_boxes = [b for b in new_boxes if box_in_bounds(b, img.width, img.height)]
    
    return img, new_boxes


def main():
    print("=" * 60)
    print("BAA YOLO 数据增强脚本")
    print("=" * 60)
    
    # 清空输出目录
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    
    for split in ["train", "val"]:
        print(f"\n处理 {split}...")
        src_labels = load_yolo_labels(split)
        print(f"  原始标注: {len(src_labels)} 张")
        
        if not src_labels:
            continue
        
        # 加载所有源图片
        src_images = {}
        for img_name, _ in src_labels.items():
            img_path = COCO_ROOT / split / "images" / img_name
            if img_path.exists():
                src_images[img_name] = Image.open(img_path).convert('RGB')
        
        out_images_dir = OUT_ROOT / split / "images"
        out_labels_dir = OUT_ROOT / split / "labels"
        out_images_dir.mkdir(parents=True, exist_ok=True)
        out_labels_dir.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for img_name, boxes in src_labels.items():
            img_path = COCO_ROOT / split / "images" / img_name
            if not img_path.exists():
                continue
            
            img = Image.open(img_path).convert('RGB')
            img_w, img_h = img.size
            
            # 原始图（归一化坐标到 [0,1]）
            norm_boxes = [(cls, x * img_w / img_w, y * img_h / img_h, w * img_w / img_w, h * img_h / img_h)
                         for cls, x, y, w, h in boxes]
            # 实际上 YOLO 格式已经是归一化的，直接用
            out_img = img.copy()
            out_labels_dir.mkdir(parents=True, exist_ok=True)
            with open(out_labels_dir / img_name.replace('.jpg', '.txt'), 'w') as f:
                for cls, x, y, wb, hb in boxes:
                    f.write(f"{cls} {x:.6f} {y:.6f} {wb:.6f} {hb:.6f}\n")
            out_img.save(out_images_dir / img_name)
            count += 1
            
            # 生成增强图
            for aug_i in range(AUG_FACTOR):
                aug_img, aug_boxes = augment_one(
                    img_path, boxes, img_w, img_h, src_images, src_labels, aug_i
                )
                aug_name = f"{Path(img_name).stem}_aug{aug_i+1}.jpg"
                aug_img.save(out_images_dir / aug_name)
                with open(out_labels_dir / aug_name.replace('.jpg', '.txt'), 'w') as f:
                    for cls, x, y, wb, hb in aug_boxes:
                        f.write(f"{cls} {x:.6f} {y:.6f} {wb:.6f} {hb:.6f}\n")
                count += 1
        
        print(f"  输出: {count} 张（原始 + 增强）")
    
    # 更新 data.yaml
    print("\n更新 data.yaml...")
    data_yaml = PROJECT_ROOT / "data" / "models" / "baa_yolo_v2.yaml"
    with open(data_yaml) as f:
        content = f.read()
    # 替换 path 为增强数据
    new_path = str(OUT_ROOT)
    new_yaml = content.replace(
        str(COCO_ROOT), new_path
    )
    with open(data_yaml, 'w') as f:
        f.write(new_yaml)
    print(f"  已更新: {data_yaml}")
    
    print("\n" + "=" * 60)
    print("增强完成！可用增强数据训练 YOLOv8")
    print("=" * 60)


if __name__ == "__main__":
    main()
