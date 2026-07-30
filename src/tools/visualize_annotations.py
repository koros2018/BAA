"""可视化 YOLO 标签，验证自动标注质量。
用法: python src/tools/visualize_annotations.py --sample <n>
"""
import argparse
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

YOLO_CLASSES = [
    'wall', 'door', 'window', 'staircase', 'corridor',
    'fire_door', 'exit', 'fire_lane', 'fire_zone', 'fire_window',
    'shaft', 'room', 'exit_sign', 'sprinkler_system', 'fire_alarm',
    'insulation', 'evacuation_lighting', 'refuge_floor',
]

# 类别颜色
CLASS_COLORS = [
    (200, 0, 0),    # wall - 红
    (0, 100, 200),  # door - 蓝
    (0, 200, 0),    # window - 绿
    (200, 200, 0),  # staircase - 黄
    (150, 0, 150),  # corridor - 紫
    (255, 80, 0),   # fire_door - 橙红
    (0, 0, 200),    # exit - 深蓝
    (255, 200, 0),  # fire_lane
    (100, 200, 100),# fire_zone
    (200, 100, 200),# fire_window
    (100, 100, 100),# shaft
    (200, 200, 200),# room - 浅灰
    (255, 255, 0),  # exit_sign
    (200, 0, 100),  # sprinkler_system
    (255, 150, 0),  # fire_alarm
    (100, 150, 200),# insulation
    (0, 255, 255),  # evacuation_lighting
    (255, 100, 100),# refuge_floor
]

def draw_annotations(img_path, label_path, output_path, scale=1.0):
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    if scale != 1.0:
        w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h))

    draw = ImageDraw.Draw(img)

    try:
        with open(label_path) as f:
            lines = [l.strip() for l in f if l.strip()]
    except FileNotFoundError:
        return

    with open(output_path, "w") as out:
        out.write(f"# {Path(img_path).stem}\n")
        out.write(f"# Image: {w}x{h}, Boxes: {len(lines)}\n\n")

    for line in lines:
        parts = line.split()
        if len(parts) != 5:
            continue
        cls_idx = int(parts[0])
        cx, cy, bw, bh = [float(x) for x in parts[1:]]
        if cls_idx >= len(YOLO_CLASSES):
            continue

        # YOLO 格式: cx, cy, w, h (归一化)
        x1 = int((cx - bw / 2) * w)
        y1 = int((cy - bh / 2) * h)
        x2 = int((cx + bw / 2) * w)
        y2 = int((cy + bh / 2) * h)

        color = CLASS_COLORS[cls_idx % len(CLASS_COLORS)]
        draw.rectangle([x1, y1, x2, y2], outline=color, width=2)

        # 只在 box > 20px 时显示标签
        if (x2 - x1) > 20 and (y2 - y1) > 20:
            cls_name = YOLO_CLASSES[cls_idx]
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            except:
                font = ImageFont.load_default()
            text = cls_name
            bbox = draw.textbbox((x1, y1), text, font=font)
            draw.rectangle([bbox[0]-1, bbox[1]-1, bbox[2]+1, bbox[3]+1], fill=color)
            draw.text((x1, y1 - 15), text, fill=(255, 255, 255), font=font)

        cls_name = YOLO_CLASSES[cls_idx]
        with open(output_path, "a") as out:
            out.write(f"  {cls_name}: [{x1},{y1},{x2},{y2}]\n")

    img.save(output_path.replace(".txt", ".png"))
    print(f"  {output_path.replace('.txt', '.png')}")


def find_image_path(label_path: Path, data_dir: Path) -> Path:
    """找到与 label 对应的 jpg（处理 # 等特殊字符问题）"""
    # label 文件名可能含 # 等字符，查找同名 .jpg
    stem = label_path.stem
    candidates = [
        data_dir / stem.replace(".txt", ""),  # 不会命中，占位
        data_dir / f"{stem}.jpg",              # 常规情况
    ]
    for c in candidates:
        if c.exists():
            return c
    # 暴力查找：label 不含 .txt 后缀的 jpg
    for j in sorted(data_dir.glob("*.jpg")):
        if j.stem.replace(".jpg", "") == stem:
            return j
    # 找不到则尝试前缀匹配
    for j in sorted(data_dir.glob("*.jpg")):
        if j.stem.startswith(stem[:10]) and stem.startswith(j.stem[:10]):
            return j
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="随机抽样 N 张")
    parser.add_argument("--output", default="data/real_annotated/viz")
    parser.add_argument("--scale", type=float, default=0.5)
    args = parser.parse_args()

    data_dir = Path(args.output).parent  # 标签所在目录
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = sorted(data_dir.glob("*.txt"))
    labels = [l for l in labels if "data.yaml" not in l.name]
    print(f"Total labels: {len(labels)}")

    if args.sample > 0 and args.sample < len(labels):
        import random
        random.seed(42)
        labels = random.sample(labels, args.sample)
        print(f"Sampling {args.sample} for visualization")

    for label_path in labels:
        img_path = find_image_path(label_path, data_dir)
        if img_path is None:
            print(f"  ⚠ Skipping {label_path}: no matching jpg")
            continue
        output_txt = out_dir / label_path.name
        draw_annotations(str(img_path), str(label_path), str(output_txt), args.scale)

    print(f"Done. Saved to {out_dir}")


if __name__ == "__main__":
    main()
