#!/usr/bin/env python3
"""
BAA 训练数据准备 V2
======================
使用合成图纸V2（synthetic_v2）生成精确标注的训练数据。
关键改进：
1. 从META图层读取精确的结构化实体元数据，而非靠几何启发式分类
2. 更新YOLO类别为与原子函数对齐的11类
3. 渲染JPG用更高dpi+更精确的边界
"""
import json
import random
import os
import sys
import math
from pathlib import Path

import ezdxf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(os.path.dirname(__file__)).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from baa_engine.semantic_analyzer import SemanticAnalyzer
from baa_engine.drawing_parser import DrawingParser

DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = DATA_DIR / "models"
COCO_DIR = DATA_DIR / "coco_v2"

# ── YOLO 类别定义 ────────────────────────────────────────
# 与原子函数的 target_entities 对齐
YOLO_CLASSES = [
    "wall",           # 0
    "door",           # 1
    "window",         # 2
    "staircase",      # 3 (原stair)
    "corridor",       # 4
    "fire_door",      # 5
    "exit",           # 6
    "fire_lane",      # 7
    "fire_zone",      # 8
    "fire_window",    # 9
    "shaft",          # 10
    "room",           # 11
    "exit_sign",      # 12
    "sprinkler_system", # 13
    "fire_alarm",     # 14
    "insulation",     # 15
    "evacuation_lighting", # 16
    "refuge_floor",   # 17
]
NC = len(YOLO_CLASSES)
CLASS_TO_ID = {name: i for i, name in enumerate(YOLO_CLASSES)}


def parse_meta_entities_from_dxf(dxf_path: str) -> list:
    """从DXF的META图层解析结构化实体（同语义分析器的逻辑）"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()
    except Exception as e:
        print(f"  ⚠️  DXF读取失败: {dxf_path.name} - {e}")
        return []

    entities = []
    for entity in msp:
        if entity.dxftype() != "TEXT":
            continue
        layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''
        if layer.upper() != "META":
            continue
        text = entity.dxf.text if hasattr(entity.dxf, 'text') else ''
        if not text.startswith("ENTITY:"):
            continue

        parts = text.split("|")
        if len(parts) < 5:
            continue

        etype = parts[0].replace("ENTITY:", "").strip()
        props = {}
        bbox = {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}

        for part in parts[1:]:
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k == "x":
                bbox["x"] = float(v)
            elif k == "y":
                bbox["y"] = float(v)
            elif k == "w":
                bbox["width"] = float(v)
            elif k == "h":
                bbox["height"] = float(v)
            else:
                try:
                    props[k] = float(v)
                except ValueError:
                    props[k] = v

        entities.append({
            "type": etype,
            "bbox": bbox,
            "properties": props,
        })

    return entities


def render_dxf_to_jpg(dxf_path: str, jpg_path: str, dpi: int = 100) -> bool:
    """将DXF渲染为JPG图像，自适应边界"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        # 计算所有图元的边界
        all_x, all_y = [], []
        for entity in msp:
            try:
                if entity.dxftype() == "LINE":
                    s = entity.dxf.start
                    e = entity.dxf.end
                    all_x.extend([s[0], e[0]])
                    all_y.extend([s[1], e[1]])
                elif entity.dxftype() == "LWPOLYLINE":
                    pts = [(v[0], v[1]) for v in entity.get_points()]
                    all_x.extend(p[0] for p in pts)
                    all_y.extend(p[1] for p in pts)
                elif entity.dxftype() == "CIRCLE":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    all_x.extend([cx - r, cx + r])
                    all_y.extend([cy - r, cy + r])
                elif entity.dxftype() == "ARC":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    all_x.extend([cx - r, cx + r])
                    all_y.extend([cy - r, cy + r])
                elif entity.dxftype() == "TEXT":
                    ins = entity.dxf.insert[:2]
                    all_x.append(ins[0])
                    all_y.append(ins[1])
            except Exception:
                continue

        if not all_x:
            return False

        margin = 2.0
        x_min, x_max = min(all_x) - margin, max(all_x) + margin
        y_min, y_max = min(all_y) - margin, max(all_y) + margin

        fig_w = max(x_max - x_min, 1) * 0.4
        fig_h = max(y_max - y_min, 1) * 0.4
        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_aspect('equal')
        ax.axis('off')

        for entity in msp:
            # 跳过META图层（标注数据不渲染）
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''
            if layer.upper() == "META":
                continue

            dxftype = entity.dxftype()
            try:
                if dxftype == "LINE":
                    s = entity.dxf.start
                    e = entity.dxf.end
                    ax.plot([s[0], e[0]], [s[1], e[1]], 'k-', linewidth=0.3)
                elif dxftype == "LWPOLYLINE":
                    pts = [(v[0], v[1]) for v in entity.get_points()]
                    xs, ys = zip(*pts)
                    ax.plot(xs, ys, 'k-', linewidth=0.3)
                elif dxftype == "CIRCLE":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    circle = plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.3)
                    ax.add_patch(circle)
                elif dxftype == "ARC":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    sa = entity.dxf.start_angle
                    ea = entity.dxf.end_angle
                    arc = plt.Arc((cx, cy), r*2, r*2, angle=0,
                                  theta1=sa, theta2=ea, color='k', linewidth=0.3)
                    ax.add_patch(arc)
                elif dxftype in ("TEXT", "MTEXT"):
                    ins = entity.dxf.insert[:2]
                    text = entity.dxf.text if hasattr(entity.dxf, 'text') else ''
                    if len(text) > 30:
                        text = text[:30]
                    ax.text(ins[0], ins[1], text, fontsize=3, ha='left', va='bottom')
            except Exception:
                continue

        plt.savefig(str(jpg_path), dpi=dpi, bbox_inches='tight',
                    pad_inches=0.05, facecolor='white')
        plt.close(fig)
        return True
    except Exception as e:
        print(f"  ⚠️  渲染失败: {dxf_path.name} - {e}")
        return False


def entities_to_yolo_annotations(entities: list, img_width_px: int, img_height_px: int,
                                  world_x_min: float, world_y_min: float,
                                  world_w: float, world_h: float) -> list:
    """
    将实体元数据转换为YOLO格式标注。
    需要将世界坐标映射到图像像素坐标。
    """
    annotations = []
    scale_x = img_width_px / max(world_w, 0.1)
    scale_y = img_height_px / max(world_h, 0.1)

    for ent in entities:
        etype = ent["type"]
        eb = ent["bbox"]

        # 映射到像素坐标
        px = (eb["x"] - world_x_min) * scale_x
        py = (eb["y"] - world_y_min) * scale_y
        pw = eb["width"] * scale_x
        ph = eb["height"] * scale_y

        # 过滤太小或无效的bbox（2px最低可见阈值）
        if pw < 2 or ph < 2:
            continue

        # YOLO格式: class_id x_center y_center width height (归一化)
        cx = (px + pw / 2) / img_width_px
        cy = (py + ph / 2) / img_height_px
        nw = pw / img_width_px
        nh = ph / img_height_px

        # 裁剪到[0,1]
        cx = max(0.001, min(0.999, cx))
        cy = max(0.001, min(0.999, cy))
        nw = max(0.001, min(0.999, nw))
        nh = max(0.001, min(0.999, nh))

        class_id = CLASS_TO_ID.get(etype)
        if class_id is None:
            continue

        annotations.append(f"{class_id} {cx:.4f} {cy:.4f} {nw:.4f} {nh:.4f}")

    return annotations


def prepare_dataset(dxf_dir: Path, split_name: str, img_size: tuple = (640, 640)):
    """为指定分片准备训练数据"""
    dxf_files = sorted(dxf_dir.glob("*.dxf"))
    if not dxf_files:
        print(f"  ⚠️  {dxf_dir} 中没有DXF文件")
        return 0, 0

    out_dir = COCO_DIR / split_name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "labels").mkdir(parents=True, exist_ok=True)

    converted = 0
    total_anns = 0

    for dxf_path in dxf_files:
        # 解析META实体
        entities = parse_meta_entities_from_dxf(dxf_path)
        if not entities:
            continue

        # 计算世界坐标边界
        xs = [e["bbox"]["x"] for e in entities]
        ys = [e["bbox"]["y"] for e in entities]
        x2s = [e["bbox"]["x"] + e["bbox"]["width"] for e in entities]
        y2s = [e["bbox"]["y"] + e["bbox"]["height"] for e in entities]

        margin = 2.0
        world_x_min = min(xs) - margin
        world_y_min = min(ys) - margin
        world_w = max(x2s) - world_x_min + margin
        world_h = max(y2s) - world_y_min + margin

        # 渲染JPG
        jpg_path = out_dir / dxf_path.name.replace(".dxf", ".jpg")
        if not jpg_path.exists():
            if not render_dxf_to_jpg(dxf_path, jpg_path):
                continue

        # 获取JPG实际尺寸
        from PIL import Image
        with Image.open(jpg_path) as img:
            img_w, img_h = img.size

        # 生成YOLO标注
        annotations = entities_to_yolo_annotations(
            entities, img_w, img_h,
            world_x_min, world_y_min, world_w, world_h
        )

        if not annotations:
            continue

        label_path = out_dir / "labels" / dxf_path.name.replace(".dxf", ".txt")
        with open(label_path, "w") as f:
            f.write("\n".join(annotations))

        converted += 1
        total_anns += len(annotations)

    return converted, total_anns


def create_yaml_config():
    """生成Ultralytics YOLO训练配置文件"""
    yaml_content = f"""# BAA 图元检测 - YOLOv8 训练配置 (V2)
path: {COCO_DIR}
train: train
val: val

# 类别
nc: {NC}
names: {YOLO_CLASSES}
"""
    yaml_path = MODELS_DIR / "baa_yolo_v2.yaml"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w") as f:
        f.write(yaml_content.strip())
    print(f"  YOLO配置文件: {yaml_path}")
    return yaml_path


def main():
    print("=" * 50)
    print("BAA 训练数据准备 V2")
    print("=" * 50)

    # 使用合成图纸V2
    synthetic_dir = DATA_DIR / "drawings" / "synthetic_v2"
    if not synthetic_dir.exists():
        print(f"❌ 合成图纸目录不存在: {synthetic_dir}")
        print(f"   请先运行: python3 scripts/generate_synthetic_v2.py")
        return

    dxf_files = list(synthetic_dir.glob("*.dxf"))
    if not dxf_files:
        print(f"❌ 没有DXF文件: {synthetic_dir}")
        return

    print(f"\n📦 共 {len(dxf_files)} 张合成图纸")
    print(f"   类别数: {NC}")
    print(f"   类别: {YOLO_CLASSES}")

    # 8:2 训练验证分割
    random.seed(42)
    random.shuffle(dxf_files)
    split_idx = int(len(dxf_files) * 0.8)
    train_files = dxf_files[:split_idx]
    val_files = dxf_files[split_idx:]

    # 写文件列表（用于prepare_dataset的独立处理）
    train_dir = COCO_DIR / "train_files"
    val_dir = COCO_DIR / "val_files"
    train_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)
    for f in train_files:
        (train_dir / f.name).symlink_to(f.resolve())
    for f in val_files:
        (val_dir / f.name).symlink_to(f.resolve())

    print(f"\n🔄 生成训练数据...")
    train_count, train_anns = prepare_dataset(train_dir, "train")
    print(f"  train: {train_count}张, {train_anns}个标注")

    val_count, val_anns = prepare_dataset(val_dir, "val")
    print(f"  val:   {val_count}张, {val_anns}个标注")

    yaml_path = create_yaml_config()

    # 清理临时符号链接
    import shutil
    shutil.rmtree(train_dir, ignore_errors=True)
    shutil.rmtree(val_dir, ignore_errors=True)

    print(f"\n✅ 训练数据就绪")
    print(f"   训练: {train_count}张 / 验证: {val_count}张")
    print(f"   总标注: {train_anns + val_anns}个")
    print(f"   配置: {yaml_path}")
    print(f"   目录: {COCO_DIR}")
    print()
    print(f"   下一步: python3 scripts/train_yolo_v2.py")


if __name__ == "__main__":
    main()
