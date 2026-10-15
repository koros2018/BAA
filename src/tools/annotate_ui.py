#!/usr/bin/env python3
"""
BAA 标注审核/修正 UI（Streamlit，P137 数据能力建设核心）

解决自动化标注后的 ground truth 缺口：
- 加载数据集（图像 + YOLO txt 标签）
- 画框叠加预览
- 逐框审核：删除误报、改类别、调整坐标
- 手动补漏检框
- 导出 YOLO txt（归一化格式）

依赖：streamlit (可选安装，pip install streamlit)、PIL
默认数据集：data/p84_yolo_dataset（4 类，p84_yolo_dataset/train/）

启动：
    cd Projects/BAA
    ./venv/bin/streamlit run src/tools/annotate_ui.py

WSL 注意：streamlit 默认绑 0.0.0.0:8501，浏览器访问 http://localhost:8501
若 WSL 端口未转发，可用 streamlit run ... --server.port 8501 并检查端口映射。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

# 仓库根目录：本文件位于 <repo>/src/tools/annotate_ui.py，向上 3 层
ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("缺少 Pillow: pip install Pillow")

try:
    import streamlit as st
except ImportError:
    sys.exit("缺少 streamlit: pip install streamlit")

try:
    import yaml
except ImportError:
    sys.exit("缺少 pyyaml: pip install pyyaml")

# 标准 18 类（与 src/baa_engine/yolo_integrator.py:24-43 一致）
STANDARD_CLASSES = [
    "wall",
    "door",
    "window",
    "staircase",
    "corridor",
    "fire_door",
    "exit",
    "fire_lane",
    "fire_zone",
    "fire_window",
    "shaft",
    "room",
    "exit_sign",
    "sprinkler_system",
    "fire_alarm",
    "insulation",
    "evacuation_lighting",
    "refuge_floor",
]

# 类→颜色（用于预览画框）
CLASS_COLORS = [
    "#FF6B6B",
    "#4ECDC4",
    "#45B7D1",
    "#96CEB4",
    "#FFEAA7",
    "#DDA0DD",
    "#98D8C8",
    "#F7DC6F",
    "#BB8FCE",
    "#85C1E9",
    "#F8C471",
    "#82E0AA",
    "#F1948A",
    "#AED6F1",
    "#A3E4D7",
    "#D7BDE2",
    "#F9E79F",
    "#F5CBA7",
]

DEFAULT_DATASETS = {
    "p84_yolo_dataset": {
        "root": "data/p84_yolo_dataset",
        "yaml": "data.yaml",
        "splits": ["train", "val"],
    },
    "p106_yolo_dataset/clean": {
        "root": "data/p106_yolo_dataset/clean",
        "yaml": "data.yaml",
        "splits": [],  # 平铺结构
    },
    "coco_v2_aug": {
        "root": "data/coco_v2_aug",
        "yaml": "data.yaml",
        "splits": ["train", "val"],
    },
}


def load_classes(dataset_cfg: dict) -> list:
    """从 data.yaml 读取类定义，回退到标准 18 类"""
    yaml_path = Path(dataset_cfg["root"]) / dataset_cfg["yaml"]
    if yaml_path.exists():
        try:
            cfg = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            names = cfg.get("names", [])
            if isinstance(names, list):
                return [str(n) for n in names]
            if isinstance(names, dict):
                return [str(names[k]) for k in sorted(names, key=lambda x: int(x))]
        except Exception:
            pass
    return STANDARD_CLASSES


def find_samples(dataset_cfg: dict, split: str) -> list:
    """返回 [(img_path, label_path), ...]，label_path 可能不存在（孤儿图像）"""
    root = Path(dataset_cfg["root"])
    base = root / split if split else root
    img_dir = base / "images"
    lab_dir = base / "labels"
    samples = []
    if not img_dir.is_dir():
        return samples
    for img in sorted(img_dir.glob("*")):
        if img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
            continue
        lab = lab_dir / (img.stem + ".txt")
        samples.append((img, lab))
    return samples


def diagnose_sample(img_path: Path, label_path: Path, classes: list, min_area: float = 0.0005):
    """诊断单个样本的标注质量问题，返回 (问题描述, 修正后 boxes, 是否变更)。

    检测：标签缺失、空标签、类 ID 越界、坐标越界、面积过小、重叠框。
    """
    issues = []
    boxes = read_labels(label_path)

    if not label_path.exists():
        return ["无标签文件（孤儿图像）"], [], False

    if not boxes:
        return ["空标签（0 个框）"], [], False

    valid_boxes = []
    for i, (cls, cx, cy, w, h) in enumerate(boxes):
        out = []
        if cls < 0 or cls >= len(classes):
            out.append(f"框{i+1} 类ID={cls} 越界")
            continue
        for val, name in ((cx, "cx"), (cy, "cy"), (w, "w"), (h, "h")):
            if val < 0 or val > 1:
                out.append(f"框{i+1} {name}={val:.4f} 越界")
        if out:
            issues.append("; ".join(out))
            continue
        if w * h < min_area:
            issues.append(f"框{i+1} {classes[cls]} 面积过小 ({w*h:.5f})")
            continue
        valid_boxes.append((cls, round(cx, 6), round(cy, 6), round(w, 6), round(h, 6)))

    # 重叠检测：两个框中心重合 + 宽高接近视为重复
    kept_boxes = []
    for i, box in enumerate(valid_boxes):
        is_duplicate = False
        for j, prev in enumerate(kept_boxes):
            if box[0] != prev[0]:
                continue
            dcx, dcy = abs(box[1] - prev[1]), abs(box[2] - prev[2])
            dw, dh = abs(box[3] - prev[3]), abs(box[4] - prev[4])
            if dcx < 0.005 and dcy < 0.005 and dw < 0.005 and dh < 0.005:
                issues.append(f"框{i+1} 与 框{j+1} 疑似重复")
                is_duplicate = True
                break
        if not is_duplicate:
            kept_boxes.append(box)

    return issues, kept_boxes, len(kept_boxes) != len(boxes)


def read_labels(label_path: Path) -> list:
    """读取 YOLO txt → [(class_id, cx, cy, w, h), ...]（归一化）"""
    if not label_path.exists():
        return []
    boxes = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            boxes.append((int(parts[0]),) + tuple(float(x) for x in parts[1:5]))
        except ValueError:
            continue
    return boxes


def write_labels(label_path: Path, boxes: list):
    """写 YOLO txt（归一化格式）"""
    label_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for cls, cx, cy, w, h in boxes:
        lines.append(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _goto(key: str, delta: int, total: int):
    """上一张/下一张：在 [0, total-1] 范围内移动样本索引。
    on_click 回调，在 rerun 前生效。
    """
    cur = st.session_state.get(key, 0)
    st.session_state[key] = max(0, min(total - 1, cur + delta))


def draw_preview(img_path: Path, boxes: list, classes: list, box_idx: int = -1) -> "Image.Image":
    """画框叠加预览，高亮第 box_idx 个框"""
    img = Image.open(img_path).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img)
    for i, (cls, cx, cy, bw, bh) in enumerate(boxes):
        if cls >= len(classes):
            continue
        x1 = max(0, int((cx - bw / 2) * w))
        y1 = max(0, int((cy - bh / 2) * h))
        x2 = min(w, int((cx + bw / 2) * w))
        y2 = min(h, int((cy + bh / 2) * h))
        if i == box_idx:
            color = "#FF0000"  # 高亮红色
            width = 4
        else:
            color = CLASS_COLORS[cls % len(CLASS_COLORS)]
            width = 2
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)
        if (x2 - x1) > 25 and (y2 - y1) > 18:
            label = f"{i+1}:{classes[cls]}"
            draw.text((x1 + 2, y1 + 1), label, fill=color)
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=None, choices=list(DEFAULT_DATASETS.keys()))
    parser.add_argument("--dataset-root", default=None, help="自定义数据集根目录（含 data.yaml）")
    parser.add_argument("--split", default="train")
    args = parser.parse_args()

    # 选择数据集
    if args.dataset:
        dataset_name = args.dataset
        dataset_cfg = dict(DEFAULT_DATASETS[dataset_name])
    elif args.dataset_root:
        dataset_name = Path(args.dataset_root).name
        dataset_cfg = {"root": args.dataset_root, "yaml": "data.yaml", "splits": []}
    else:
        dataset_name = "p84_yolo_dataset"
        dataset_cfg = dict(DEFAULT_DATASETS[dataset_name])

    st.set_page_config(page_title="BAA 标注审核", layout="wide", page_icon="🎯")
    st.title("🎯 BAA 标注审核 / 修正工具")
    st.caption("删除误报 · 修正类别 · 补漏检框 · 导出 YOLO txt")

    # 数据集选择（侧边栏）
    with st.sidebar:
        st.header("⚙️ 数据集")
        ds_choice = st.selectbox(
            "选择数据集",
            list(DEFAULT_DATASETS.keys()) + ["自定义..."],
            index=(
                list(DEFAULT_DATASETS.keys()).index(dataset_name)
                if dataset_name in DEFAULT_DATASETS
                else len(DEFAULT_DATASETS)
            ),
        )
        if ds_choice == "自定义...":
            custom_root = st.text_input("自定义根目录", dataset_cfg["root"])
            dataset_cfg = {"root": custom_root, "yaml": "data.yaml", "splits": []}
        else:
            dataset_cfg = dict(DEFAULT_DATASETS[ds_choice])
            dataset_name = ds_choice

        classes = load_classes(dataset_cfg)
        available_splits = dataset_cfg.get("splits", [])
        split = "train"
        if available_splits:
            split = st.selectbox("拆分", available_splits)
            if split not in available_splits:
                split = available_splits[0]
        elif args.split and args.split != "train":
            split = args.split
        st.write(f"类数: {len(classes)}")
        st.write(f"类: {', '.join(classes[:6])}{'...' if len(classes) > 6 else ''}")

    # 样本浏览
    samples = find_samples(dataset_cfg, split)
    if not samples:
        st.error(f"未找到样本。数据集: {dataset_cfg['root']}, 拆分: {split}")
        st.info("检查 data.yaml 是否存在、images/ 目录是否为空")
        return

    total = len(samples)
    st.write(f"📊 **{dataset_name}** / {split} — {total} 样本")

    # 批量清理：先统计影响面，确认后写入，写入前备份到 data/models/batch_clean/backups/
    with st.expander("🧹 批量清理（去噪框 / 越界框 / 重复框）"):
        batch_key = f"batch::{dataset_name}::{split}"
        if batch_key not in st.session_state:
            stats = {
                "clean": 0,
                "issue_samples": 0,
                "fix_samples": 0,
                "removed_boxes": 0,
                "missing_labels": 0,
            }
            for im, lb in samples:
                iss, fx, ch = diagnose_sample(im, lb, classes)
                if not lb.exists():
                    stats["missing_labels"] += 1
                    continue
                if ch:
                    stats["fix_samples"] += 1
                    stats["removed_boxes"] += max(0, len(read_labels(lb)) - len(fx))
                elif not iss:
                    stats["clean"] += 1
                else:
                    stats["issue_samples"] += 1
            st.session_state[batch_key] = stats
        bs = st.session_state[batch_key]
        st.write(
            f"共 {total} 样本：{bs['clean']} 干净 · {bs['fix_samples']} 可自动修复 · "
            f"{bs['issue_samples']} 仅提示 · {bs['missing_labels']} 无标签"
        )
        st.caption(
            f"预计移除 {bs['removed_boxes']} 个噪声/越界/重复框（阈值：面积 ≥ 0.0005，坐标∈[0,1]，去近重复）"
        )
        if bs["fix_samples"] > 0:
            if st.button(f"⚡ 备份并批量清理 {bs['fix_samples']} 个样本", type="primary"):
                ts = time.strftime("%Y%m%d_%H%M%S")
                backup_dir = (
                    ROOT
                    / "data"
                    / "models"
                    / "batch_clean"
                    / "backups"
                    / f"{dataset_name}_{split}_{ts}"
                )
                backup_dir.mkdir(parents=True, exist_ok=True)
                applied = 0
                for im, lb in samples:
                    if not lb.exists():
                        continue
                    iss, fx, ch = diagnose_sample(im, lb, classes)
                    if not ch:
                        continue
                    shutil.copy2(lb, backup_dir / lb.name)
                    write_labels(lb, fx)
                    applied += 1
                st.success(f"已清理 {applied} 个样本，备份: {backup_dir.relative_to(ROOT)}")
                st.session_state[batch_key] = {
                    "clean": bs["clean"] + bs["fix_samples"],
                    "issue_samples": bs["issue_samples"],
                    "fix_samples": 0,
                    "removed_boxes": 0,
                    "missing_labels": bs["missing_labels"],
                }
                st.rerun()

    # 样本索引持久化：key 绑定 session_state，dataset/split 切换时自动重置，
    # prev/next 通过 _goto 改同一个 key。
    _key = f"idx::{dataset_name}::{split}"
    idx = st.number_input(
        "样本序号",
        0,
        total - 1,
        key=_key,
        help="手动跳转会重置当前未保存的修改",
    )
    img_path, label_path = samples[idx]

    if not img_path.exists():
        st.error(f"图像不存在: {img_path}")
        return

    # 读取现有标注
    if "boxes" not in st.session_state:
        st.session_state["boxes"] = []
    if "dirty" not in st.session_state:
        st.session_state["dirty"] = False
    if "cur_idx" not in st.session_state:
        st.session_state["cur_idx"] = -1

    # 切换样本时重新加载
    if st.session_state.get("loaded_idx") != idx:
        st.session_state["boxes"] = read_labels(label_path)
        st.session_state["dirty"] = False
        st.session_state["loaded_idx"] = idx
        st.session_state["cur_idx"] = -1

    boxes = st.session_state["boxes"]

    # 问题诊断（自动检测标注质量）
    issues, fixed_boxes, changed = diagnose_sample(img_path, label_path, classes)
    diag_key = f"diag::{idx}::{dataset_name}"
    if diag_key not in st.session_state:
        st.session_state[diag_key] = (issues, changed)
    diag_issues, diag_changed = st.session_state[diag_key]

    col_img, col_edit = st.columns([2, 1])
    with col_img:
        st.subheader(f"🖼️ 样本 {idx+1}/{total}")
        preview = draw_preview(img_path, boxes, classes, box_idx=st.session_state["cur_idx"])
        st.image(preview, use_container_width=True)
        st.write(f"图像: {img_path.stat().st_size/1024:.1f} KB · 框: {len(boxes)}")

        # 一键应用修复
        if diag_changed:
            c1, c2 = st.columns(2)
            with c1:
                if st.button(f"⚡ 应用修复 ({len(boxes)}→{len(fixed_boxes)} 框)", type="primary"):
                    st.session_state["boxes"] = fixed_boxes
                    st.session_state["dirty"] = True
                    st.session_state["cur_idx"] = -1
                    st.session_state[diag_key] = ([], False)
                    st.rerun()
            with c2:
                st.caption(f"检出 {len(diag_issues)} 项问题")

    with col_edit:
        st.subheader("✏️ 标注编辑")
        if not boxes:
            st.info("无标注框。可手动添加。")
        else:
            # 框列表
            for i, (cls, cx, cy, w, h) in enumerate(boxes):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    label = st.text_input(
                        f"框 {i+1} 坐标 (class cx cy w h)",
                        value=f"{cls} {cx:.4f} {cy:.4f} {w:.4f} {h:.4f}",
                        key=f"box_{i}",
                    )
                with col_b:
                    if st.button("❌", key=f"del_{i}"):
                        boxes.pop(i)
                        st.session_state["dirty"] = True
                        st.session_state["cur_idx"] = -1
                        st.rerun()
            # 高亮选择
            if st.session_state["cur_idx"] >= 0 and st.session_state["cur_idx"] < len(boxes):
                st.write(f"**高亮**: 框 {st.session_state['cur_idx']+1}")

        # 新增框
        st.divider()
        st.write("➕ 添加新框（归一化坐标 0-1）")
        col_x, col_y = st.columns(2)
        with col_x:
            cx_new = st.number_input("cx", 0.0, 1.0, 0.5, step=0.01, key="new_cx")
            cy_new = st.number_input("cy", 0.0, 1.0, 0.5, step=0.01, key="new_cy")
        with col_y:
            w_new = st.number_input("w", 0.0, 1.0, 0.1, step=0.01, key="new_w")
            h_new = st.number_input("h", 0.0, 1.0, 0.1, step=0.01, key="new_h")
        cls_new = st.selectbox(
            "新框类别",
            list(range(len(classes))),
            format_func=lambda i: f"{i}: {classes[i]}",
            key="new_cls",
        )
        if st.button("➕ 添加", type="primary", key="add_box"):
            boxes.append((cls_new, cx_new, cy_new, w_new, h_new))
            st.session_state["dirty"] = True
            st.session_state["cur_idx"] = len(boxes) - 1
            st.rerun()

    # 工具栏
    st.divider()
    col_l, col_c, col_r = st.columns(3)
    with col_l:
        st.button(
            f"◀ 上一张 ({idx}→{max(0, idx-1)})",
            key="prev",
            on_click=lambda: _goto(_key, -1, total),
            disabled=idx == 0,
        )
    with col_c:
        dirty = st.session_state["dirty"]
        st.write(f"{'🔴 未保存修改' if dirty else '✅ 已保存'}")
        if st.button("💾 保存", type="primary", key="save"):
            write_labels(label_path, boxes)
            st.session_state["dirty"] = False
            st.success(f"已保存: {label_path}")
            st.rerun()
    with col_r:
        st.button(
            f"下一张 ({idx}→{min(total-1, idx+1)}) ▶",
            key="next",
            on_click=lambda: _goto(_key, 1, total),
            disabled=idx == total - 1,
        )


if __name__ == "__main__":
    main()
