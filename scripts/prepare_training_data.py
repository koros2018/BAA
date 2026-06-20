"""
BAA 图元检测模型训练框架
YOLOv8 + Attention 架构
LoRA 微调支持

策略：
  1. 用合成图纸生成COCO格式训练数据
  2. 训练基座模型（合成数据）
  3. 真实图纸来了后 LoRA 微调
"""
import os
import json
import random
import math
from pathlib import Path

import numpy as np
import ezdxf

# ─── 配置 ─────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "data" / "models"
SYNTHETIC_DIR = DATA_DIR / "drawings" / "synthetic"
COCO_DIR = DATA_DIR / "coco"

# COCO 类别映射（BAA 图元类型）
COCO_CATEGORIES = [
    {"id": 1, "name": "wall", "supercategory": "building"},
    {"id": 2, "name": "door", "supercategory": "building"},
    {"id": 3, "name": "window", "supercategory": "building"},
    {"id": 4, "name": "stair", "supercategory": "building"},
    {"id": 5, "name": "corridor", "supercategory": "building"},
    {"id": 6, "name": "exit", "supercategory": "building"},
    {"id": 7, "name": "fire_door", "supercategory": "building"},
    {"id": 8, "name": "fire_zone", "supercategory": "building"},
    {"id": 9, "name": "dimension", "supercategory": "annotation"},
    {"id": 10, "name": "text", "supercategory": "annotation"},
]

CATEGORY_MAP = {c["name"]: c["id"] for c in COCO_CATEGORIES}


def _get_bbox(entity):
    """兼容ezdxf 1.4.3的bbox获取"""
    dxftype = entity.dxftype()
    try:
        # 部分实体支持 bbox()
        bbox = entity.bbox()
        return list(bbox.extmin), list(bbox.extmax)
    except AttributeError:
        pass
    # 手动计算顶点范围
    try:
        points = []
        if dxftype == "LWPOLYLINE":
            points = [(v[0], v[1]) for v in entity.get_points()]
        elif dxftype == "LINE":
            points = [entity.dxf.start[:2], entity.dxf.end[:2]]
        elif dxftype == "CIRCLE":
            cx, cy = entity.dxf.center[:2]
            r = entity.dxf.radius
            return [cx - r, cy - r], [cx + r, cy + r]
        elif dxftype == "ARC":
            cx, cy = entity.dxf.center[:2]
            r = entity.dxf.radius
            return [cx - r, cy - r], [cx + r, cy + r]
        elif dxftype in ("TEXT", "MTEXT"):
            ins = entity.dxf.insert[:2]
            h = getattr(entity.dxf, "height", 1.0)
            return [ins[0] - 0.1, ins[1] - 0.1], [ins[0] + h * 5, ins[1] + h]
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return [min(xs), min(ys)], [max(xs), max(ys)]
    except Exception:
        pass
    return None


def dxf_to_coco(dxf_path: str) -> dict | None:
    """将单张DXF转换为COCO标注格式"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()
    except Exception:
        return None

def dxf_to_coco(dxf_path: str) -> dict | None:
    """将单张DXF转换为COCO标注格式"""
    try:
        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()
    except Exception:
        return None

    primitives = []
    for entity in msp:
        dxftype = entity.dxftype()
        if dxftype not in ("LINE", "LWPOLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT"):
            continue
        bbox = _get_bbox(entity)
        if bbox is None:
            continue
        xmin, ymin = bbox[0]
        xmax, ymax = bbox[1]
        w = max(xmax - xmin, 0.01)
        h = max(ymax - ymin, 0.01)
        primitives.append({
            "type": dxftype,
            "bbox": [float(xmin), float(ymin), float(w), float(h)],
            "center": [float((xmin + xmax) / 2), float((ymin + ymax) / 2)],
        })

    if not primitives:
        return None

    # 简单语义分类（基于图层或几何特征）
    images = [{
        "id": 1,
        "file_name": dxf_path.name,
        "width": 1000,
        "height": 1000,
    }]
    annotations = []
    ann_id = 1

    for prim in primitives:
        # 启发式分类：基于dxf_type+图层+几何特征
        cat_name = classify_primitive(prim)
        cat_id = CATEGORY_MAP.get(cat_name, 10)  # 默认text
        annotations.append({
            "id": ann_id,
            "image_id": 1,
            "category_id": cat_id,
            "bbox": [round(v, 2) for v in prim["bbox"]],
            "area": round(prim["bbox"][2] * prim["bbox"][3], 2),
            "iscrowd": 0,
        })
        ann_id += 1

    return {
        "images": images,
        "annotations": annotations,
        "categories": COCO_CATEGORIES,
    }


def classify_primitive(prim: dict) -> str:
    """基于几何特征简单分类图元"""
    dxf_type = prim.get("type", "")
    bbox = prim["bbox"]
    w, h = bbox[2], bbox[3]
    ratio = max(w, h) / (min(w, h) + 0.001)
    area = w * h
    large = area > 100
    thin = ratio > 5

    if dxf_type == "CIRCLE":
        return "exit" if large else "stair"
    elif dxf_type == "ARC":
        return "door"
    elif dxf_type == "LWPOLYLINE":
        if thin and large:
            return "wall"
        elif large:
            return "corridor"
        else:
            return "fire_zone"
    elif dxf_type in ("TEXT", "MTEXT"):
        return "text"
    elif dxf_type == "LINE":
        if thin and large:
            return "wall"
        elif large:
            return "corridor"
        else:
            return "dimension"
    return "wall"


def dxf_to_image(dxf_path: str, out_path: str, img_size: tuple = (640, 640)) -> bool:
    """将DXF渲染为JPG图像"""
    try:
        import ezdxf
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        doc = ezdxf.readfile(str(dxf_path))
        msp = doc.modelspace()

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.set_xlim(-5, 25)
        ax.set_ylim(-5, 25)
        ax.set_aspect('equal')
        ax.axis('off')

        for entity in msp:
            dxftype = entity.dxftype()
            try:
                if dxftype == "LINE":
                    start = entity.dxf.start
                    end = entity.dxf.end
                    ax.plot([start[0], end[0]], [start[1], end[1]], 'k-', linewidth=0.5)
                elif dxftype == "LWPOLYLINE":
                    pts = [(v[0], v[1]) for v in entity.get_points()]
                    xs, ys = zip(*pts)
                    ax.plot(xs, ys, 'k-', linewidth=0.5)
                elif dxftype == "CIRCLE":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    circle = plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.5)
                    ax.add_patch(circle)
                elif dxftype == "ARC":
                    cx, cy = entity.dxf.center[:2]
                    r = entity.dxf.radius
                    start_angle = entity.dxf.start_angle
                    end_angle = entity.dxf.end_angle
                    arc = plt.Arc((cx, cy), r*2, r*2, angle=0,
                                  theta1=start_angle, theta2=end_angle,
                                  color='k', linewidth=0.5)
                    ax.add_patch(arc)
            except Exception:
                continue

        plt.savefig(out_path, dpi=80, bbox_inches='tight', pad_inches=0.1)
        plt.close(fig)
        return True
    except Exception as e:
        print(f"  ⚠️  渲染失败: {dxf_path.name} - {e}")
        return False


def generate_coco_dataset(split_ratio: float = 0.8):
    """生成COCO格式训练/验证集 + 渲染JPG"""
    if not SYNTHETIC_DIR.exists():
        print(f"❌ 合成图纸目录不存在: {SYNTHETIC_DIR}")
        return

    dxf_files = list(SYNTHETIC_DIR.glob("*.dxf"))
    if not dxf_files:
        print("❌ 没有DXF文件")
        return

    random.shuffle(dxf_files)
    split_idx = int(len(dxf_files) * split_ratio)
    train_files = dxf_files[:split_idx]
    val_files = dxf_files[split_idx:]

    (COCO_DIR / "train").mkdir(parents=True, exist_ok=True)
    (COCO_DIR / "val").mkdir(parents=True, exist_ok=True)

    def process_split(files, split_name):
        coco_data = {"images": [], "annotations": [], "categories": COCO_CATEGORIES}
        img_id = 0
        ann_id = 0
        converted = 0

        for dxf_path in files:
            # 渲染JPG
            jpg_path = COCO_DIR / split_name / dxf_path.name.replace(".dxf", ".jpg")
            if not jpg_path.exists():
                if not dxf_to_image(dxf_path, jpg_path):
                    continue

            # COCO标注
            result = dxf_to_coco(dxf_path)
            if result is None:
                continue
            result["images"][0]["id"] = img_id
            result["images"][0]["file_name"] = jpg_path.name
            for ann in result["annotations"]:
                ann["image_id"] = img_id
                ann["id"] = ann_id
                ann_id += 1
            coco_data["images"].append(result["images"][0])
            coco_data["annotations"].extend(result["annotations"])
            img_id += 1
            converted += 1

        json_path = COCO_DIR / split_name / "_annotations.coco.json"
        with open(json_path, "w") as f:
            json.dump(coco_data, f, ensure_ascii=False)

        print(f"  {split_name}: {converted}张图纸, {len(coco_data['annotations'])}个标注")
        return converted

    print(f"📦 生成COCO数据集（共{len(dxf_files)}张合成图纸）")
    train_count = process_split(train_files, "train")
    val_count = process_split(val_files, "val")
    print(f"✅ 完成: 训练{train_count} + 验证{val_count}")
    print(f"📁 输出目录: {COCO_DIR}")
    generate_yolo_format()


def generate_yolo_format():
    """生成YOLO格式标注文件（用于ultralytics）"""
    for split in ("train", "val"):
        json_path = COCO_DIR / split / "_annotations.coco.json"
        if not json_path.exists():
            continue
        with open(json_path) as f:
            data = json.load(f)

        # 建立 image_id -> file_name 映射
        img_map = {}
        for img in data["images"]:
            img_map[img["id"]] = {
                "file_name": img["file_name"].replace(".dxf", ".jpg"),
                "width": img["width"],
                "height": img["height"],
            }

        # 按 image_id 分组标注
        anns_by_img = {}
        for ann in data["annotations"]:
            img_id = ann["image_id"]
            if img_id not in anns_by_img:
                anns_by_img[img_id] = []
            anns_by_img[img_id].append(ann)

        for img_id, anns in anns_by_img.items():
            img_info = img_map.get(img_id)
            if not img_info:
                continue
            w, h = img_info["width"], img_info["height"]
            lines = []
            for ann in anns:
                x, y, bw, bh = ann["bbox"]
                # YOLO格式: class x_center y_center width height (归一化)
                cx = (x + bw / 2) / w
                cy = (y + bh / 2) / h
                nw = bw / w
                nh = bh / h
                lines.append(f"{ann['category_id'] - 1} {cx:.4f} {cy:.4f} {nw:.4f} {nh:.4f}")
            label_file = COCO_DIR / split / img_info["file_name"].replace(".jpg", ".txt")
            with open(label_file, "w") as f:
                f.write("\n".join(lines))

    print("  YOLO格式标签同步完成")


def create_yaml_config():
    """生成Ultralytics YOLO训练配置文件"""
    yaml_content = f"""
# BAA 图元检测 - YOLOv8 训练配置
path: {COCO_DIR}
train: train
val: val

# 类别
nc: 10
names: ['wall', 'door', 'window', 'stair', 'corridor', 'exit', 'fire_door', 'fire_zone', 'dimension', 'text']
"""
    yaml_path = MODELS_DIR / "baa_yolo.yaml"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w") as f:
        f.write(yaml_content.strip())
    print(f"  YOLO配置文件: {yaml_path}")


if __name__ == "__main__":
    print("=" * 50)
    print("BAA 训练数据准备")
    print("=" * 50)
    generate_coco_dataset()
    create_yaml_config()
    print(f"\n✅ 训练数据就绪")
    print(f"   下一步: cd {PROJECT_ROOT} && pip install ultralytics")
    print(f"           python3 scripts/train_yolo.py")
