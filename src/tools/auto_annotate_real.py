"""
P84 Phase 1: 真实图纸自动标注
复用 _render_dxf 渲染流程 + SemanticAnalyzer._classify_entities 分类，
把世界坐标 bbox 映射到像素坐标，生成 YOLO 标签。

用法:
    python src/tools/auto_annotate_real.py --dxf <path> [--output-dir ./annotations]
    python src/tools/auto_annotate_real.py --all
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path

# 确保 src 在 path 中
WORKSPACE = Path(__file__).resolve().parent.parent.parent
# src/tools/... → 项目根 = PROJECT/BAA
# 需要两个路径：一个是项目根（用于 import src.baa_engine...）
# 另一个是 src/ 本身（用于 from baa_engine import ...）
PROJECT_ROOT = WORKSPACE
src_path = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))  # for src.baa_engine 导入
sys.path.insert(0, str(src_path))       # for baa_engine 导入

import ezdxf
import numpy as np
from PIL import Image

# 延迟导入引擎，避免初始化开销
from baa_engine.drawing_parser import DrawingParser
from baa_engine.semantic_analyzer.main import SemanticAnalyzer

# ── YOLO 标签类别映射 ──────────────────────────────────
# 语义分析器产出的 type → YOLO class index
# 对应 baa_yolo_v2.yaml 的 names 列表
YOLO_CLASSES = [
    'wall', 'door', 'window', 'staircase', 'corridor',
    'fire_door', 'exit', 'fire_lane', 'fire_zone', 'fire_window',
    'shaft', 'room', 'exit_sign', 'sprinkler_system', 'fire_alarm',
    'insulation', 'evacuation_lighting', 'refuge_floor',
]

# 语义分析器的 type → YOLO 类别名映射
TYPE_TO_YOLO = {
    'wall': 'wall',
    'door': 'door',
    'window': 'window',
    'stair': 'staircase',        # 语义分析器用 stair，YOLO 用 staircase
    'staircase': 'staircase',
    'corridor': 'corridor',
    'fire_door': 'fire_door',
    'exit': 'exit',
    'fire_lane': 'fire_lane',
    'fire_zone': 'fire_zone',
    'fire_window': 'fire_window',
    'shaft': 'shaft',
    'room': 'room',
    'exit_sign': 'exit_sign',
    'sprinkler_system': 'sprinkler_system',
    'sprinkler': 'sprinkler_system',
    'fire_alarm': 'fire_alarm',
    'smoke_detector': 'fire_alarm',  # 烟雾探测器归入 fire_alarm
    'detector': 'fire_alarm',        # 探测器归入 fire_alarm
    'insulation': 'insulation',
    'evacuation_lighting': 'evacuation_lighting',
    'refuge_floor': 'refuge_floor',
    # 设备类 — 当前 YOLO 无对应类别，跳过
    'fire_hydrant': None,
    'fire_pump': None,
    'equipment': None,
    'titleblock': None,
    'fire_wall': 'wall',              # 防火墙归入 wall
    'fire_wall_line': 'wall',
    'unknown': None,
    'other': None,
}


def render_dxf_image(dxf_path: str, dpi: int = 100) -> tuple:
    """
    复用 _render_dxf 逻辑渲染 DXF 为图像。
    返回: (image_path, (x_min, x_max, y_min, y_max), (fig_w_inch, fig_h_inch))
    即世界坐标边界和图像尺寸（英寸），用于后续像素→世界坐标映射。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    all_x, all_y = [], []
    for entity in msp:
        try:
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
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
            elif entity.dxftype() in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                all_x.append(ins[0])
                all_y.append(ins[1])
        except Exception:
            continue

    if not all_x:
        return None, None, None

    margin = 2.0
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin

    fig_w = max(x_max - x_min, 1) * 0.4
    fig_h = max(y_max - y_min, 1) * 0.4

    max_pixels = 2048
    if fig_w * dpi > max_pixels or fig_h * dpi > max_pixels:
        scale = min(max_pixels / (fig_w * dpi), max_pixels / (fig_h * dpi))
        fig_w *= scale
        fig_h *= scale

    # 用临时文件渲染
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = tmp.name
    tmp.close()

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal")
    ax.axis("off")

    for entity in msp:
        layer = entity.dxf.layer if hasattr(entity.dxf, "layer") else ""
        if layer.upper() == "META":
            continue
        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                ax.plot([s[0], e[0]], [s[1], e[1]], "k-", linewidth=0.3)
            elif dxftype == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                xs, ys = zip(*pts)
                ax.plot(xs, ys, "k-", linewidth=0.3)
            elif dxftype == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(
                    plt.Circle((cx, cy), r, fill=False, color="k", linewidth=0.3)
                )
            elif dxftype == "ARC":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(
                    plt.Arc(
                        (cx, cy), r * 2, r * 2, angle=0,
                        theta1=entity.dxf.start_angle,
                        theta2=entity.dxf.end_angle,
                        color="k", linewidth=0.3,
                    )
                )
        except Exception:
            continue

    plt.savefig(tmp_path, dpi=dpi, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)

    # 获取实际保存后的图像尺寸（bbox_inches="tight" 会裁剪）
    img = Image.open(tmp_path)
    img_w, img_h = img.size
    img.close()

    return tmp_path, (x_min, x_max, y_min, y_max), (img_w, img_h)


def entities_to_yolo(
    entities,
    world_bbox,
    image_size,
    dpi: int = 100,
) -> tuple:
    """
    将语义分析器产出的实体列表转换为 YOLO 标签。
    
    坐标映射：世界坐标 → 像素坐标（考虑 bbox_inches='tight' 裁剪）。
    由于 bbox_inches='tight' 会实际裁剪掉空白边缘，世界坐标边界
    (x_min, x_max, y_min, y_max) 是渲染前的轴范围，图像实际尺寸
    (img_w, img_h) 是裁剪后的。
    
    简化假设：裁剪是均匀的（pad_inches 较小），直接用轴范围做线性映射。
    如果效果不好，后续可以用图像边缘检测重新校准。
    """
    x_min, x_max, y_min, y_max = world_bbox
    img_w, img_h = image_size

    world_w = x_max - x_min
    world_h = y_max - y_min

    if world_w <= 0 or world_h <= 0:
        return [], 0

    # 比例尺：每像素对应多少世界坐标单位
    px_per_unit_x = img_w / world_w
    px_per_unit_y = img_h / world_h

    yolo_lines = []
    skipped = 0

    for entity in entities:
        yolo_class = TYPE_TO_YOLO.get(entity["type"])
        if yolo_class is None or yolo_class not in YOLO_CLASSES:
            skipped += 1
            continue

        bb = entity.get("bbox", {})
        ex = bb.get("x", 0)
        ey = bb.get("y", 0)
        ew = bb.get("width", 0)
        eh = bb.get("height", 0)

        # 过滤零 bbox
        if ew <= 0 or eh <= 0:
            skipped += 1
            continue

        # 世界坐标 bbox 中心
        cx_world = ex + ew / 2
        cy_world = ey + eh / 2

        # 映射到像素
        cx_px = (cx_world - x_min) * px_per_unit_x
        cy_px = (cy_world - y_min) * px_per_unit_y
        w_px = ew * px_per_unit_x
        h_px = eh * px_per_unit_y

        # 归一化到 [0,1]
        cx_norm = cx_px / img_w
        cy_norm = cy_px / img_h
        w_norm = w_px / img_w
        h_norm = h_px / img_h

        # 过滤超出图像范围的框
        if cx_norm < 0 or cx_norm > 1 or cy_norm < 0 or cy_norm > 1:
            skipped += 1
            continue

        class_idx = YOLO_CLASSES.index(yolo_class)
        yolo_lines.append(f"{class_idx} {cx_norm:.6f} {cy_norm:.6f} {w_norm:.6f} {h_norm:.6f}")

    return yolo_lines, skipped


def annotate_single_dxf(dxf_path: str, output_dir: str, dpi: int = 100) -> dict:
    """对单个 DXF 执行：渲染 → 解析 → 标注 → 保存标签"""
    print(f"\n{'='*60}")
    print(f"Processing: {dxf_path}")

    # 1. 渲染
    print("  [1/3] Rendering...")
    img_path, world_bbox, image_size = render_dxf_image(dxf_path, dpi=dpi)
    if img_path is None:
        print("  ❌ Render failed (no valid primitives)")
        return {"status": "render_failed"}

    img_w, img_h = image_size
    print(f"  Rendered: {img_path} ({img_w}x{img_h})")

    # 2. 语义解析
    print("  [2/3] Semantic parsing...")
    dp = DrawingParser()
    res = dp.parse(dxf_path)
    if not res.success:
        print(f"  ❌ Parse failed: {res.error}")
        os.unlink(img_path)
        return {"status": "parse_failed", "error": res.error}

    sa = SemanticAnalyzer()
    result = sa.analyze(res.primitives, dxf_path=dxf_path)
    entities = result.get("entities", [])
    print(f"  Found {len(entities)} entities")

    # 3. 转 YOLO 标签
    print("  [3/3] Converting to YOLO format...")
    yolo_lines, skipped = entities_to_yolo(entities, world_bbox, image_size, dpi)
    print(f"  Wrote {len(yolo_lines)} boxes, skipped {skipped}")

    # 保存标签
    base = Path(dxf_path).stem
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    label_path = out_dir / f"{base}.txt"
    with open(label_path, "w") as f:
        for line in yolo_lines:
            f.write(line + "\n")
    print(f"  Label saved: {label_path}")

    # 复制渲染图 + padding 成正方形
    img_out = out_dir / f"{base}.jpg"
    import shutil
    shutil.copy2(img_path, img_out)
    os.unlink(img_path)

    # 把长图 pad 成正方形（白色填充），保持 aspect ratio 的同时让 YOLO 训练一致
    orig_img = Image.open(img_out).convert("RGB")
    orig_w, orig_h = orig_img.size
    max_dim = max(orig_w, orig_h)
    pad_x = (max_dim - orig_w) // 2
    pad_y = (max_dim - orig_h) // 2
    padded = Image.new("RGB", (max_dim, max_dim), "white")
    padded.paste(orig_img, (pad_x, pad_y))
    padded.save(img_out, quality=95)
    print(f"  Image saved (padded {max_dim}x{max_dim}): {img_out}")

    # 重映射 YOLO 坐标（考虑 padding 偏移）
    if orig_w != max_dim or orig_h != max_dim:
        remapped = []
        for line in yolo_lines:
            parts = line.split()
            cls_idx = int(parts[0])
            cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
            # 原来在 orig_w x orig_h 中，现在在 max_dim x max_dim 中
            remapped.append(
                f"{cls_idx} "
                f"{(pad_x + cx * orig_w) / max_dim:.6f} "
                f"{(pad_y + cy * orig_h) / max_dim:.6f} "
                f"{w * orig_w / max_dim:.6f} "
                f"{h * orig_h / max_dim:.6f}"
            )
        with open(label_path, "w") as f:
            for line in remapped:
                f.write(line + "\n")
        print(f"  Labels remapped to padded coordinates")

    # 输出类别分布
    class_dist = {}
    for e in entities:
        yc = TYPE_TO_YOLO.get(e["type"])
        if yc and yc in YOLO_CLASSES:
            class_dist[yc] = class_dist.get(yc, 0) + 1
    print(f"  Class distribution: {class_dist}")

    return {
        "status": "ok",
        "entities": len(entities),
        "boxes": len(yolo_lines),
        "skipped": skipped,
        "image": str(img_out),
        "label": str(label_path),
        "class_dist": class_dist,
    }


def find_dxf_files() -> list:
    """找到 data/ 目录下所有可用的 DXF（排除子目录中的和已知不可用的）"""
    dxf_files = []
    data_dir = WORKSPACE / "data"
    # 顶层 DXF
    for f in sorted(data_dir.glob("*.dxf")):
        dxf_files.append(str(f))
    return dxf_files


def main():
    parser = argparse.ArgumentParser(description="P84 真实图纸自动标注")
    parser.add_argument("--dxf", help="单个 DXF 文件路径")
    parser.add_argument("--all", action="store_true", help="标注 data/ 下所有 DXF")
    parser.add_argument("--output-dir", default="data/real_annotated",
                        help="输出目录")
    parser.add_argument("--dpi", type=int, default=100, help="渲染 DPI")
    args = parser.parse_args()

    os.chdir(WORKSPACE)

    if args.dxf:
        files = [args.dxf]
    elif args.all:
        files = find_dxf_files()
    else:
        parser.print_help()
        return

    if not files:
        print("No DXF files found.")
        return

    print(f"P84 自动标注 — {len(files)} files")
    print(f"Output: {args.output_dir}")
    print(f"DPI: {args.dpi}")

    results = []
    for f in files:
        try:
            r = annotate_single_dxf(f, args.output_dir, dpi=args.dpi)
            results.append((f, r))
        except Exception as e:
            print(f"  ❌ Exception: {e}")
            results.append((f, {"status": "error", "error": str(e)}))

    # 汇总
    ok = sum(1 for _, r in results if r.get("status") == "ok")
    print(f"\n{'='*60}")
    print(f"Done: {ok}/{len(results)} succeeded")
    total_boxes = sum(r.get("boxes", 0) for _, r in results if r.get("status") == "ok")
    print(f"Total YOLO boxes: {total_boxes}")

    # 生成 data.yaml
    out_dir = Path(args.output_dir)
    yaml_path = out_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        f.write(f"path: {out_dir.resolve()}\n")
        f.write("train: train_images\n")
        f.write("val: val_images\n")
        f.write(f"nc: {len(YOLO_CLASSES)}\n")
        f.write(f"names: {YOLO_CLASSES}\n")
    print(f"data.yaml: {yaml_path}")


if __name__ == "__main__":
    main()
