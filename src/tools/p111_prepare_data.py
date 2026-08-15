"""
P111 数据清洗脚本：生成干净训练集

步骤：
1. 按 stem 匹配图-标签对（修复 0 匹配的 bug）
2. 剔除非建筑平面图（系统图/计算表/目录等）
3. 剔除无标签图像
4. 生成新的 train.txt / val.txt
5. 统计清洗后类别分布
"""

import os
import shutil
from pathlib import Path
from collections import Counter

BASE = Path("data/p106_yolo_dataset")
IMG_DIR = BASE / "images"
LBL_DIR = BASE / "labels"
CLEAN_DIR = BASE / "clean" / "images"
CLEAN_LBL_DIR = BASE / "clean" / "labels"
CLEAN_DATA_YAML = BASE / "clean" / "data.yaml"

NON_FLOOR_KW = [
    "系统图", "系统拓扑", "系统原理", "系统", "计算", "参数表",
    "选型", "材料", "目录", "说明", "图例", "详图", "大样图",
    "剖面图", "立面图", "断面图", "原理图", "单线图", "拓扑图",
    "清单", "预算", "概算", "决算", "设备选型", "配电系统",
    "供电系统", "消防系统", "给排水系统", "弱电系统", "强电系统",
    "总体架构", "网络拓扑", "控制原理", "自控系统", "计算书",
    "照度计算", "热工计算", "负荷计算", "系统总体",
]

FLOOR_KW = ["平面", "层", "楼", "户型", "房间", "轴线", "轴网",
            "建筑", "结构", "装修", "顶板", "基础", "屋顶"]


def is_non_floor(name: str) -> bool:
    if any(kw in name for kw in FLOOR_KW):
        return False
    return any(kw in name for kw in NON_FLOOR_KW)


def get_stem(filename: str) -> str:
    """Extract stem: remove last extension"""
    parts = filename.rsplit(".", 1)
    return parts[0] if len(parts) == 2 else parts[0]


def prepare_dataset():
    img_files = os.listdir(IMG_DIR)
    lbl_files = os.listdir(LBL_DIR)

    # Build stem → filename maps
    img_by_stem = {get_stem(f): f for f in img_files}
    lbl_by_stem = {get_stem(f): f for f in lbl_files}

    # 1. Match by stem
    matched_stems = set(img_by_stem.keys()) & set(lbl_by_stem.keys())
    print(f"Total images: {len(img_files)}")
    print(f"Total labels: {len(lbl_files)}")
    print(f"Matched pairs (by stem): {len(matched_stems)}")

    # 2. Filter non-floor plans
    floor_stems = [s for s in matched_stems if not is_non_floor(s)]
    non_floor_stems = [s for s in matched_stems if is_non_floor(s)]
    print(f"Floor plan pairs: {len(floor_stems)}")
    print(f"Non-floor pairs (discarded): {len(non_floor_stems)}")

    # 3. Stats on discarded non-floor
    if non_floor_stems:
        print(f"\nSample discarded non-floor (first 15):")
        for s in sorted(non_floor_stems)[:15]:
            print(f"  {s}")

    # 4. Copy clean data
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_LBL_DIR.mkdir(parents=True, exist_ok=True)

    for s in floor_stems:
        src_img = IMG_DIR / img_by_stem[s]
        dst_img = CLEAN_DIR / img_by_stem[s]
        shutil.copy2(src_img, dst_img)

        src_lbl = LBL_DIR / lbl_by_stem[s]
        dst_lbl_name = str(lbl_by_stem[s]).rsplit(".", 1)[0] + ".txt"
        dst_lbl = CLEAN_LBL_DIR / dst_lbl_name
        shutil.copy2(src_lbl, dst_lbl)

    print(f"\nClean images: {len(os.listdir(CLEAN_DIR))}")
    print(f"Clean labels: {len(os.listdir(CLEAN_LBL_DIR))}")

    # 5. Class distribution on clean data
    class_counter = Counter()
    for lbl_file in sorted(os.listdir(CLEAN_LBL_DIR)):
        path = CLEAN_LBL_DIR / lbl_file
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    try:
                        cls = int(parts[0])
                        class_counter[cls] += 1
                    except ValueError:
                        pass

    print(f"\nClean class distribution:")
    YOLO_CLASSES = [
        "wall", "door", "window", "staircase", "corridor",
        "fire_door", "exit", "fire_lane", "fire_zone", "fire_window",
        "shaft", "room", "exit_sign", "sprinkler_system",
        "fire_alarm", "insulation", "evacuation_lighting", "refuge_floor",
    ]
    for i, name in enumerate(YOLO_CLASSES):
        cnt = class_counter.get(i, 0)
        bar = "█" * min(cnt // 100, 50)
        print(f"  {i:2d} {name:25s} {cnt:5d} {bar}")

    # 6. Generate train.txt / val.txt (80/20 split)
    import random
    random.seed(42)
    floor_list = sorted(floor_stems)
    random.shuffle(floor_list)
    split = int(len(floor_list) * 0.8)
    train_stems = floor_list[:split]
    val_stems = floor_list[split:]

    with open(CLEAN_DIR.parent / "train.txt", "w") as f:
        for s in train_stems:
            f.write(str((CLEAN_DIR / img_by_stem[s]).resolve()) + "\n")
    with open(CLEAN_DIR.parent / "val.txt", "w") as f:
        for s in val_stems:
            f.write(str((CLEAN_DIR / img_by_stem[s]).resolve()) + "\n")

    print(f"\nSplit: train={len(train_stems)}, val={len(val_stems)}")

    # 7. Generate clean data.yaml
    yaml_content = f"""# P111 Clean Dataset
# Generated: 2026-08-15
train: {CLEAN_DIR / 'images'}
val: {CLEAN_DIR / 'images'}

# 18 classes for BAA architectural entity detection
nc: 18
names:
  0: wall
  1: door
  2: window
  3: staircase
  4: corridor
  5: fire_door
  6: exit
  7: fire_lane
  8: fire_zone
  9: fire_window
  10: shaft
  11: room
  12: exit_sign
  13: sprinkler_system
  14: fire_alarm
  15: insulation
  16: evacuation_lighting
  17: refuge_floor
"""
    with open(CLEAN_DATA_YAML, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print(f"\nClean data.yaml written to: {CLEAN_DATA_YAML}")
    print(f"Train: {CLEAN_DIR.parent / 'train.txt'}")
    print(f"Val: {CLEAN_DIR.parent / 'val.txt'}")

    return {
        "total_imgs": len(img_files),
        "total_lbls": len(lbl_files),
        "matched": len(matched_stems),
        "floor_plans": len(floor_stems),
        "discarded_non_floor": len(non_floor_stems),
        "train": len(train_stems),
        "val": len(val_stems),
        "classes": dict(class_counter),
    }


if __name__ == "__main__":
    prepare_dataset()