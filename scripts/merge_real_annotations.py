#!/usr/bin/env python3
"""
BAA 真实标注数据整合脚本
=========================
将人工标注后的真实图纸数据整合到 YOLO 训练格式。

功能：
1. 读取 data/real_renderings/labels/ 下的标注文件
2. 按 80/20 划分 train/val
3. 复制到 YOLO 训练格式目录 data/real_train/
4. 生成 data.yaml

为什么需要这个脚本？
- 人工标注的输出目录（data/real_renderings/）是"平铺"的，所有图片和标注在同一个目录
- YOLO 训练需要 train/val 分离的目录结构
- 这个脚本负责转换目录结构并生成配置

用法:
    python scripts/merge_real_annotations.py
    python scripts/merge_real_annotations.py --input-dir data/real_renderings
    python scripts/merge_real_annotations.py --output-dir data/real_train --val-ratio 0.2
    python scripts/merge_real_annotations.py --dry-run   # 仅预览，不复制

输出:
    data/real_train/
    ├── data.yaml
    ├── train/
    │   ├── images/
    │   │   ├── *.jpg
    │   └── labels/
    │       └── *.txt
    └── val/
        ├── images/
        │   ├── *.jpg
        └── labels/
            └── *.txt
"""

import argparse
import logging
import os
import random
import shutil
import sys
from pathlib import Path
from collections import Counter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 项目根路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "real_renderings"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "real_train"

# YOLO 类别定义（与 yolo_integrator.YOLO_CLASSES 同步）
# 为什么手动维护？与渲染脚本一致，避免 import 链依赖问题
YOLO_CLASSES = [
    "wall",              # 0
    "door",              # 1
    "window",            # 2
    "staircase",         # 3
    "corridor",          # 4
    "fire_door",         # 5
    "exit",              # 6
    "fire_lane",         # 7
    "fire_zone",         # 8
    "fire_window",       # 9
    "shaft",             # 10
    "room",              # 11
    "exit_sign",         # 12
    "sprinkler_system",  # 13
    "fire_alarm",        # 14
    "insulation",        # 15
    "evacuation_lighting",  # 16
    "refuge_floor",      # 17
]


def scan_annotations(input_dir: Path) -> list:
    """
    扫描输入目录，收集所有已标注的样本。

    标注完成的判断条件：
    - 有对应的 .jpg 渲染图
    - 有对应的 .txt 标注文件
    - 标注文件非空（至少有一行有效标注数据）

    Returns:
        list[dict]: 每个元素包含 {"image_path", "label_path", "stem", "object_count"}
    """
    images_dir = input_dir
    labels_dir = input_dir / "labels"

    if not images_dir.exists():
        logger.error(f"输入目录不存在: {images_dir}")
        return []

    if not labels_dir.exists():
        logger.error(f"标注目录不存在: {labels_dir}")
        logger.error("请先运行 render_real_drawings.py 生成空白标注文件，然后人工标注")
        return []

    samples = []
    for img_path in sorted(images_dir.glob("*.jpg")):
        stem = img_path.stem
        label_path = labels_dir / f"{stem}.txt"

        if not label_path.exists():
            logger.warning(f"  跳过 {stem}: 无标注文件")
            continue

        # 统计标注数量
        obj_count = 0
        for line in open(label_path):
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                if len(parts) == 5:
                    obj_count += 1

        if obj_count == 0:
            logger.warning(f"  跳过 {stem}: 标注文件为空（未标注）")
            continue

        samples.append({
            "image_path": img_path,
            "label_path": label_path,
            "stem": stem,
            "object_count": obj_count,
        })

    return samples


def validate_labels(samples: list) -> dict:
    """
    验证标注文件的格式和类别正确性。

    检查项：
    1. 每行 5 个字段
    2. class_id 在 0~17 范围内
    3. 坐标值在 0~1 范围内
    4. 宽度和高度 > 0

    Returns:
        dict: 包含 {"errors": [...], "class_counts": Counter, "total_objects": int}
    """
    errors = []
    class_counts = Counter()
    total_objects = 0

    for sample in samples:
        with open(sample["label_path"]) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) != 5:
                    errors.append(
                        f"{sample['stem']}:{line_num} - 字段数应为 5，实际为 {len(parts)}"
                    )
                    continue

                try:
                    cls_id = int(parts[0])
                    xc, yc, bw, bh = map(float, parts[1:])
                except ValueError:
                    errors.append(f"{sample['stem']}:{line_num} - 数值格式错误")
                    continue

                if cls_id < 0 or cls_id >= len(YOLO_CLASSES):
                    errors.append(
                        f"{sample['stem']}:{line_num} - class_id={cls_id} 超出范围 [0, {len(YOLO_CLASSES)-1}]"
                    )
                    continue

                if not (0 <= xc <= 1 and 0 <= yc <= 1):
                    errors.append(
                        f"{sample['stem']}:{line_num} - 中心坐标超出 [0,1] 范围: ({xc}, {yc})"
                    )
                    continue

                if bw <= 0 or bh <= 0:
                    errors.append(
                        f"{sample['stem']}:{line_num} - 宽高必须 > 0: ({bw}, {bh})"
                    )
                    continue

                class_counts[cls_id] += 1
                total_objects += 1

    return {
        "errors": errors,
        "class_counts": class_counts,
        "total_objects": total_objects,
    }


def split_dataset(samples: list, val_ratio: float = 0.2, seed: int = 42) -> tuple:
    """
    按比例划分训练集和验证集。

    划分策略：
    - 随机打乱后按比例切分
    - 固定 seed 保证可复现

    为什么用随机划分而不是分层抽样？
    - 初始标注数量少（<50 张），分层抽样效果有限
    - 随机划分简单可靠，后续标注量增加后可改用分层抽样

    Returns:
        (train_samples, val_samples): 两个列表
    """
    random.seed(seed)
    shuffled = samples.copy()
    random.shuffle(shuffled)

    val_count = max(1, int(len(shuffled) * val_ratio))
    val_samples = shuffled[:val_count]
    train_samples = shuffled[val_count:]

    return train_samples, val_samples


def copy_dataset(samples: list, target_dir: Path, split_name: str):
    """
    将样本复制到目标目录。

    目录结构：
        <target_dir>/<split_name>/images/<stem>.jpg
        <target_dir>/<split_name>/labels/<stem>.txt
    """
    images_dir = target_dir / split_name / "images"
    labels_dir = target_dir / split_name / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    for sample in samples:
        # 复制图像
        shutil.copy2(str(sample["image_path"]), str(images_dir / sample["image_path"].name))
        # 复制标注
        shutil.copy2(str(sample["label_path"]), str(labels_dir / sample["label_path"].name))

    logger.info(f"  {split_name}: {len(samples)} 张图 → {images_dir}")


def generate_data_yaml(output_dir: Path, train_count: int, val_count: int):
    """
    生成 YOLO 训练所需的 data.yaml 文件。

    为什么叫 data.yaml 而不是 dataset.yaml？
    YOLOv8 的训练配置文件名约定为 data.yaml，Ultralytics 官方代码直接读取此文件名。
    """
    # 计算相对路径（从输出目录到 train/val 目录）
    # YOLO 的 data.yaml 使用相对路径，保证项目可移植
    data_yaml = {
        "train": "train/images",
        "val": "val/images",
        "nc": len(YOLO_CLASSES),
        "names": YOLO_CLASSES,
    }

    yaml_path = output_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        f.write(f"# BAA 真实图纸标注数据集\n")
        f.write(f"# 生成时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# 训练集: {train_count} 张, 验证集: {val_count} 张\n")
        f.write(f"# 类别数: {len(YOLO_CLASSES)}\n")
        f.write(f"\n")
        f.write(f"train: train/images\n")
        f.write(f"val: val/images\n")
        f.write(f"\n")
        f.write(f"nc: {len(YOLO_CLASSES)}\n")
        f.write(f"names:\n")
        for i, name in enumerate(YOLO_CLASSES):
            f.write(f"  {i}: {name}\n")

    logger.info(f"  data.yaml → {yaml_path}")
    return yaml_path


def main():
    parser = argparse.ArgumentParser(description="BAA 真实标注数据整合脚本")
    parser.add_argument("--input-dir", type=str, default=str(DEFAULT_INPUT_DIR),
                        help=f"渲染图输入目录（默认: {DEFAULT_INPUT_DIR})")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f"训练数据输出目录（默认: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--val-ratio", type=float, default=0.2,
                        help="验证集比例（默认: 0.2）")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子（默认: 42）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅预览，不复制")
    parser.add_argument("--min-objects", type=int, default=1,
                        help="最少标注数（标注数少于该值的样本将被跳过，默认: 1）")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    logger.info("=" * 50)
    logger.info("BAA 真实标注数据整合")
    logger.info("=" * 50)

    # 步骤 1：扫描标注
    logger.info("步骤 1: 扫描标注文件...")
    samples = scan_annotations(input_dir)

    if not samples:
        logger.error("未找到已标注的样本。请先完成标注。")
        logger.error(f"  预期位置: {input_dir}/labels/*.txt")
        sys.exit(1)

    logger.info(f"  找到 {len(samples)} 个已标注样本")

    # 过滤低标注数样本
    filtered = [s for s in samples if s["object_count"] >= args.min_objects]
    skipped = len(samples) - len(filtered)
    if skipped > 0:
        logger.info(f"  跳过 {skipped} 个标注数不足 {args.min_objects} 的样本")
    samples = filtered

    if not samples:
        logger.error("过滤后无可用样本")
        sys.exit(1)

    # 步骤 2：验证标注
    logger.info("步骤 2: 验证标注格式...")
    validation = validate_labels(samples)

    if validation["errors"]:
        logger.warning(f"  发现 {len(validation['errors'])} 个标注错误:")
        for err in validation["errors"][:10]:  # 最多显示 10 个
            logger.warning(f"    - {err}")
        if len(validation["errors"]) > 10:
            logger.warning(f"    ... 还有 {len(validation['errors']) - 10} 个错误")

    logger.info(f"  总标注对象数: {validation['total_objects']}")
    logger.info(f"  类别分布:")
    for cls_id in sorted(validation["class_counts"]):
        name = YOLO_CLASSES[cls_id]
        count = validation["class_counts"][cls_id]
        bar = "█" * min(count, 50)
        logger.info(f"    {cls_id:2d} {name:20s}: {count:4d} {bar}")

    # 步骤 3：划分 train/val
    logger.info(f"步骤 3: 按 {args.val_ratio:.0%}/{1-args.val_ratio:.0%} 划分 train/val...")
    train_samples, val_samples = split_dataset(samples, val_ratio=args.val_ratio, seed=args.seed)
    logger.info(f"  训练集: {len(train_samples)} 张")
    logger.info(f"  验证集: {len(val_samples)} 张")

    if args.dry_run:
        logger.info("【干运行模式】不执行复制操作")
        logger.info(f"  输出目录: {output_dir}")
        logger.info(f"  训练集: {len(train_samples)} 张")
        logger.info(f"  验证集: {len(val_samples)} 张")
        logger.info("=" * 50)
        return

    # 步骤 4：复制数据
    logger.info("步骤 4: 复制数据到训练目录...")
    if output_dir.exists():
        logger.info(f"  输出目录已存在: {output_dir}")
        logger.info("  将覆盖已有文件")

    copy_dataset(train_samples, output_dir, "train")
    copy_dataset(val_samples, output_dir, "val")

    # 步骤 5：生成 data.yaml
    logger.info("步骤 5: 生成 data.yaml...")
    yaml_path = generate_data_yaml(output_dir, len(train_samples), len(val_samples))

    # 步骤 6：输出汇总
    logger.info("=" * 50)
    logger.info("整合完成！")
    logger.info(f"  输出目录: {output_dir}")
    logger.info(f"  训练集: {len(train_samples)} 张图, {sum(s['object_count'] for s in train_samples)} 个标注")
    logger.info(f"  验证集: {len(val_samples)} 张图, {sum(s['object_count'] for s in val_samples)} 个标注")
    logger.info(f"  配置文件: {yaml_path}")
    logger.info("")
    logger.info("下一步:")
    logger.info(f"  cd {PROJECT_ROOT}")
    logger.info("  yolo train model=yolov8m.pt data=data/real_train/data.yaml epochs=100")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()