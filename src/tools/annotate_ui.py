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
import sys
from pathlib import Path

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
    "wall", "door", "window", "staircase", "corridor", "fire_door",
    "exit", "fire_lane", "fire_zone", "fire_window", "shaft", "room",
    "exit_sign", "sprinkler_system", "fire_alarm", "insulation",
    "evacuation_lighting", "refuge_floor",
]

# 类→颜色（用于预览画框）
CLASS_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD",
    "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9", "#F8C471", "#82E0AA",
    "#F1948A", "#AED6F1", "#A3E4D7", "#D7BDE2", "#F9E79F", "#F5CBA7",
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
            index=list(DEFAULT_DATASETS.keys()).index(dataset_name)
            if dataset_name in DEFAULT_DATASETS else len(DEFAULT_DATASETS),
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

    # 样本索引持久化：key 绑定 session_state，dataset/split 切换时自动重置，
    # prev/next 通过 _goto 改同一个 key。
    _key = f"idx::{dataset_name}::{split}"
    idx = st.number_input(
        "样本序号", 0, total - 1, key=_key,
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

    # 主视图：图像 + 高亮框
    col_img, col_edit = st.columns([2, 1])
    with col_img:
        st.subheader(f"🖼️ 样本 {idx+1}/{total}")
        preview = draw_preview(img_path, boxes, classes, box_idx=st.session_state["cur_idx"])
        st.image(preview, use_container_width=True)
        st.write(f"图像尺寸: {img_path.stat().st_size/1024:.1f} KB · 标注框: {len(boxes)}")

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
        cls_new = st.selectbox("新框类别", list(range(len(classes))),
                                format_func=lambda i: f"{i}: {classes[i]}", key="new_cls")
        if st.button("➕ 添加", type="primary", key="add_box"):
            boxes.append((cls_new, cx_new, cy_new, w_new, h_new))
            st.session_state["dirty"] = True
            st.session_state["cur_idx"] = len(boxes) - 1
            st.rerun()

    # 工具栏
    st.divider()
    col_l, col_c, col_r = st.columns(3)
    with col_l:
        st.button(f"◀ 上一张 ({idx}→{max(0, idx-1)})", key="prev",
                  on_click=lambda: _goto(_key, -1, total), disabled=idx == 0)
    with col_c:
        dirty = st.session_state["dirty"]
        st.write(f"{'🔴 未保存修改' if dirty else '✅ 已保存'}")
        if st.button("💾 保存", type="primary", key="save"):
            write_labels(label_path, boxes)
            st.session_state["dirty"] = False
            st.success(f"已保存: {label_path}")
            st.rerun()
    with col_r:
        st.button(f"下一张 ({idx}→{min(total-1, idx+1)}) ▶", key="next",
                  on_click=lambda: _goto(_key, 1, total), disabled=idx == total - 1)


if __name__ == "__main__":
    main()
