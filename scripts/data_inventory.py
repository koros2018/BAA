#!/usr/bin/env python3
"""
BAA YOLO 训练数据集资产盘点脚本（P137 前置）

扫描 data/ 下全部 YOLO 数据集目录，输出统一资产清单：
- 数据集规模（图像/标签数）
- 类别定义（nc+names）与是否与标准 18 类一致
- 异常检测：孤儿标签、孤儿图像、空标签、坐标越界
- 支持目录型（images/+labels/）与 txt 列表型（train.txt）
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("缺少 pyyaml，请先安装: pip install pyyaml")

# 标准 18 类（与 src/baa_engine/yolo_integrator.py:24-43 保持一致）
STANDARD_CLASSES = [
    "wall", "door", "window", "staircase", "corridor", "fire_door",
    "exit", "fire_lane", "fire_zone", "fire_window", "shaft", "room",
    "exit_sign", "sprinkler_system", "fire_alarm", "insulation",
    "evacuation_lighting", "refuge_floor",
]

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IGNORE = {"desktop.ini", ".ds_store", "thumbs.db"}


class Dataset:
    """单个数据集资产的盘点结果"""

    def __init__(self, name, root: Path, split: str = ""):
        self.name = name
        self.root = root
        self.split = split
        self.nc = 0
        self.names = []
        self.std_class_ids = []
        self.img_files = []
        self.label_files = []
        self.orphan_labels = []
        self.orphan_images = []
        self.nonempty_labels = 0
        self.empty_labels = 0
        self.bad_coords = []
        self.class_counts = defaultdict(int)  # 类名 -> 标签行数

    @property
    def n_images(self):
        return len(self.img_files)

    @property
    def n_labels(self):
        return len(self.label_files)

    def load_yaml(self, data_yaml: Path):
        try:
            cfg = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(cfg, dict):
            self.nc = cfg.get("nc", 0) or 0
            names = cfg.get("names", [])
            if isinstance(names, list):
                self.names = [str(n) for n in names]
            elif isinstance(names, dict):
                self.names = [str(names[k]) for k in sorted(names, key=lambda x: int(x))]
            self.std_class_ids = [
                STANDARD_CLASSES.index(n) if n in STANDARD_CLASSES else -1
                for n in self.names
            ]

    def scan_dir(self, img_dir: Path, label_dir: Path):
        stem2img = {}
        for f in img_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in IMG_EXT and f.name not in IGNORE:
                self.img_files.append(f)
                stem2img.setdefault(f.stem, f)
        stem2lab = {}
        for f in label_dir.rglob("*.txt"):
            if f.is_file() and f.name not in IGNORE:
                self.label_files.append(f)
                stem2lab.setdefault(f.stem, f)

        for stem, lab in stem2lab.items():
            if stem not in stem2img:
                self.orphan_labels.append(lab)
        for stem, img in stem2img.items():
            if stem not in stem2lab:
                self.orphan_images.append(img)

        for lab in self.label_files:
            content = lab.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                self.empty_labels += 1
                continue
            self.nonempty_labels += 1
            for ln in content.splitlines():
                parts = ln.split()
                if len(parts) >= 5:
                    try:
                        vals = [float(x) for x in parts[1:5]]
                    except ValueError:
                        self.bad_coords.append((str(lab), ln))
                        continue
                    if any(v < 0 or v > 1 for v in vals):
                        self.bad_coords.append((str(lab), ln))
                    # 类计数
                    cls_id = parts[0]
                    if self.names and cls_id.isdigit() and int(cls_id) < len(self.names):
                        self.class_counts[self.names[int(cls_id)]] += 1

    def scan_txt(self, txt_files):
        """扫描 txt 列表型数据集（支持 train.txt/val.txt 多个拆分列表）
        图像绝对路径来自多个 txt，伴侣标签按同名匹配（labels/ 或同目录）。
        """
        if isinstance(txt_files, (str, Path)):
            txt_files = [txt_files]
        seen = set()
        for txt in txt_files:
            for line in txt.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                img = Path(line)
                if img.suffix.lower() not in IMG_EXT:
                    continue
                k = str(img.resolve())
                if k in seen:
                    continue
                seen.add(k)
                self.img_files.append(img)
        for img in self.img_files:
            cands = [
                img.with_suffix(".txt"),
                img.parent.with_name("labels") / img.with_suffix(".txt").name,
            ]
            found = False
            for c in cands:
                if c.exists():
                    self.label_files.append(c)
                    found = True
                    break
            if not found:
                self.orphan_images.append(img)
        # txt 型 label 内容扫描
        for lab in self.label_files:
            content = lab.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                self.empty_labels += 1
                continue
            self.nonempty_labels += 1
            for ln in content.splitlines():
                parts = ln.split()
                if len(parts) >= 5:
                    try:
                        vals = [float(x) for x in parts[1:5]]
                    except ValueError:
                        self.bad_coords.append((str(lab), ln))
                        continue
                    if any(v < 0 or v > 1 for v in vals):
                        self.bad_coords.append((str(lab), ln))
                    cls_id = parts[0]
                    if self.names and cls_id.isdigit() and int(cls_id) < len(self.names):
                        self.class_counts[self.names[int(cls_id)]] += 1


def find_datasets(data_root: Path):
    """自动发现 data/ 下所有含 data*.yaml 或 images/+labels/ 的数据集

    解析优先级（同一目录只走一种解析，避免叠加重复计数）：
      1. 含 split 子目录（train/val/test/images+labels）：按子目录 scan_dir
      2. 平铺 images/+labels/ 且无 train.txt：scan_dir
      3. 含 train.txt（列表型，路径显式指向图像）：scan_txt，不做 scan_dir
    """
    datasets = {}

    # ── 第一步：先按 txt 列表型处理（train.txt + val.txt，自带路径，优先）
    for train_txt in sorted(data_root.rglob("train.txt")):
        root = train_txt.parent
        key = str(root)
        ds = datasets.get(key) or Dataset(
            root.relative_to(data_root).as_posix(), root
        )

        # 收集同一目录下所有拆分列表（train.txt/val.txt/test.txt）
        txt_lists = [train_txt]
        for tname in ("val.txt", "test.txt"):
            t = root / tname
            if t.exists():
                txt_lists.append(t)
        ds.scan_txt(txt_lists)
        datasets[key] = ds

        # 载入该目录 data.yaml 的类定义（若存在）
        for yaml_file in sorted(root.glob("data*.yaml")):
            ds.load_yaml(yaml_file)

    # ── 第二步：含 data*.yaml 的目录型（排除已被 train.txt 处理的）
    for yaml_file in sorted(data_root.rglob("data*.yaml")):
        root = yaml_file.parent
        key = str(root)
        ds = datasets.get(key) or Dataset(
            root.relative_to(data_root).as_posix(), root
        )
        ds.load_yaml(yaml_file)
        datasets[key] = ds

        has_split = any((root / s).is_dir() for s in ("train", "val", "test"))
        # 已有 train.txt 解析的记录，不再重复 scan_dir
        if has_split:
            for split_dir in ("train", "val", "test"):
                img_dir = root / split_dir / "images"
                lab_dir = root / split_dir / "labels"
                if img_dir.is_dir() and lab_dir.is_dir():
                    part = Dataset(
                        f"{ds.name}/{split_dir}", root, split_dir
                    )
                    part.load_yaml(yaml_file)
                    part.scan_dir(img_dir, lab_dir)
                    datasets[f"{root}/{split_dir}"] = part
        elif not datasets.get(key).img_files:  # 平铺且未被 train.txt 填充
            img_dir = root / "images"
            lab_dir = root / "labels"
            if img_dir.is_dir() and lab_dir.is_dir():
                ds.scan_dir(img_dir, lab_dir)

    # ── 第三步：平铺 images/+labels/ 无 yaml 且无 train.txt
    for img_dir in sorted(data_root.rglob("images")):
        lab_dir = img_dir.with_name("labels")
        key = str(img_dir.parent)
        if lab_dir.is_dir() and key not in datasets:
            ds = Dataset(
                img_dir.parent.relative_to(data_root).as_posix(),
                img_dir.parent,
            )
            ds.scan_dir(img_dir, lab_dir)
            datasets[key] = ds

    return datasets


def render_markdown(datasets: dict) -> str:
    lines = [
        "# BAA YOLO 数据集资产盘点",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "标准 18 类：`" + ", ".join(STANDARD_CLASSES) + "`",
        "",
        "| 数据集 | 拆分 | nc | 类一致 | 图像 | 标签 | 孤儿标签 | 孤儿图像 | 空标签 | 越界坐标 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    rows = sorted(datasets.values(), key=lambda d: d.name)
    for ds in rows:
        s = summarize(ds)
        lines.append(
            f"| {s['name']} | {ds.split or '-'} | {s['nc']} | "
            f"{'Y' if s['consistent'] else 'N'} | {s['n_images']} | {s['n_labels']} | "
            f"{s['orphan_labels']} | {s['orphan_images']} | {s['empty_labels']} | {s['bad_coords']} |"
        )
    lines.append("")
    lines.append("## 异常明细")
    for ds in rows:
        if ds.orphan_labels:
            lines.append(f"\n### {ds.name}: 孤儿标签 ({len(ds.orphan_labels)})")
            for f in ds.orphan_labels[:20]:
                lines.append(f"- `{f}`")
        if ds.orphan_images:
            lines.append(f"\n### {ds.name}: 孤儿图像 ({len(ds.orphan_images)})")
            for f in ds.orphan_images[:20]:
                lines.append(f"- `{f}`")
        if ds.bad_coords:
            lines.append(f"\n### {ds.name}: 坐标越界 ({len(ds.bad_coords)})")
            for f, ln in ds.bad_coords[:20]:
                lines.append(f"- `{f}`: `{ln}`")
    lines.append("\n## 各类别样本覆盖")
    lines.append("\n| 类 | id | 覆盖数据集 (行数) |")
    lines.append("|---|---|---|")
    for i, name in enumerate(STANDARD_CLASSES):
        cov = []
        for ds in rows:
            n = ds.class_counts.get(name, 0)
            if n > 0:
                cov.append(f"{ds.name}({n})")
        lines.append(f"| {name} | {i} | {', '.join(cov) or '无' if cov else '无'} |")
    return "\n".join(lines)


def summarize(ds: Dataset) -> dict:
    return {
        "name": ds.name, "nc": ds.nc,
        "consistent": ds.names == STANDARD_CLASSES,
        "n_images": ds.n_images, "n_labels": ds.n_labels,
        "orphan_labels": len(ds.orphan_labels),
        "orphan_images": len(ds.orphan_images),
        "empty_labels": ds.empty_labels, "bad_coords": len(ds.bad_coords),
    }


def main():
    parser = argparse.ArgumentParser(description="BAA YOLO 数据集资产盘点")
    parser.add_argument("--root", default="data", help="扫描根目录，默认 data/")
    parser.add_argument("--out", default=None, help="Markdown 报告输出路径")
    args = parser.parse_args()

    data_root = Path(args.root).resolve()
    if not data_root.is_dir():
        sys.exit(f"数据目录不存在: {data_root}")

    datasets = find_datasets(data_root)
    if not datasets:
        sys.exit("未发现任何数据集")

    rows = sorted(datasets.values(), key=lambda d: d.name)
    print(f"{'数据集':<42} {'拆':<5} {'nc':<4} {'一致':<4} {'图':<5} {'标':<5} "
          f"{'孤标':<4} {'孤图':<4} {'空':<4} {'越界':<5}")
    print("-" * 95)
    for ds in rows:
        s = summarize(ds)
        print(f"{s['name']:<42} {ds.split or '-':<5} {s['nc']:<4} "
              f"{'Y' if s['consistent'] else 'N':<4} {s['n_images']:<5} {s['n_labels']:<5} "
              f"{s['orphan_labels']:<4} {s['orphan_images']:<4} {s['empty_labels']:<4} {s['bad_coords']:<5}")
    total_imgs = sum(s.n_images for s in rows)
    total_labs = sum(s.n_labels for s in rows)
    print("-" * 95)
    print(f"合计: {len(rows)} 个数据集, {total_imgs} 图像, {total_labs} 标签")

    md = render_markdown(datasets)
    out_path = Path(args.out) if args.out else data_root / "models" / "dataset_inventory.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\nMarkdown 报告: {out_path}")


if __name__ == "__main__":
    main()
