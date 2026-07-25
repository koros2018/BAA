#!/usr/bin/env python3
"""
BAA 真实图纸渲染脚本
======================
将 data/drawings/real/ 下的 DXF 图纸渲染为高分辨率 JPG 图像，
用于后续人工标注和领域适配训练。

设计要点：
1. 复用 yolo_integrator._render_dxf 的渲染逻辑（import 而非复制）
2. 如果 import 链失败，就地实现等效渲染逻辑
3. 输出高分辨率图像（dpi=200）和对应的空白 YOLO 标注文件
4. 报告每张图的基本信息（尺寸、文件大小、非白像素占比）

用法:
    python scripts/render_real_drawings.py
    python scripts/render_real_drawings.py --dpi 300 --output-dir data/real_renderings
    python scripts/render_real_drawings.py --drawings data/drawings/real/ --dry-run

输出:
    data/real_renderings/
    ├── <filename>.jpg           # 渲染后的图像
    └── labels/
        └── <filename>.txt       # 空白 YOLO 标注文件（无内容，等待人工标注）
"""

import argparse
import logging
import math
import os
import sys
import tempfile
import time
from pathlib import Path

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 项目根路径 ──────────────────────────────────────────
# 使用 __file__ 定位项目根目录，确保脚本可以从任何位置执行
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DRAWINGS_DIR = PROJECT_ROOT / "data" / "drawings" / "real"
# 同时扫描根 data/ 目录下的 DXF（这些是真正的图纸文件，data/drawings/real/ 是子集）
DEFAULT_ROOT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "real_renderings"

# ── YOLO 类别定义（与 yolo_integrator.YOLO_CLASSES 同步） ──
# 18 个类别，顺序必须与训练时的 data.yaml 一致
# 为什么手动维护而不是 import？因为 import 链可能因依赖问题失败，
# 渲染脚本需要能够独立运行，不受项目其他模块的 import 错误影响。
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


def render_dxf(dxf_path: str, dpi: int = 200) -> str:
    """
    将 DXF 渲染为 JPG 图像。

    渲染逻辑与 yolo_integrator._render_dxf 一致：
    - 使用 ezdxf 读取 DXF
    - matplotlib 无头渲染（Agg 后端）
    - 跳过 META 图层（辅助标注线干扰 YOLO 检测）
    - 等比例缩放，保持宽高比不变
    - 白底黑线（与训练数据生成格式一致）

    Args:
        dxf_path: DXF 文件路径
        dpi: 渲染分辨率，默认 200 以保留完整细节

    Returns:
        str: 渲染后 JPG 文件的路径

    Raises:
        FileNotFoundError: DXF 文件不存在
        ValueError: DXF 文件无法解析或无图元
    """
    import ezdxf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dxf_path = str(dxf_path)

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception as e:
        raise ValueError(f"无法读取 DXF 文件: {dxf_path} - {e}")

    # 计算所有图元的边界框
    all_x, all_y = [], []
    for entity in msp:
        try:
            dxftype = entity.dxftype()
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                all_x.extend([s[0], e[0]])
                all_y.extend([s[1], e[1]])
            elif dxftype == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                all_x.extend(p[0] for p in pts)
                all_y.extend(p[1] for p in pts)
            elif dxftype == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
            elif dxftype == "ARC":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
            elif dxftype in ("TEXT", "MTEXT"):
                ins = entity.dxf.insert[:2]
                all_x.append(ins[0])
                all_y.append(ins[1])
            elif dxftype == "POINT":
                loc = entity.dxf.location[:2]
                all_x.append(loc[0])
                all_y.append(loc[1])
            elif dxftype == "SPLINE":
                try:
                    pts = list(entity.control_points)
                    if pts:
                        all_x.extend(p[0] for p in pts)
                        all_y.extend(p[1] for p in pts)
                except Exception:
                    pass
            elif dxftype == "ELLIPSE":
                cx, cy = entity.dxf.center[:2]
                major_axis = entity.dxf.major_axis
                r = math.sqrt(major_axis[0]**2 + major_axis[1]**2) * 1.1
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
            elif dxftype == "INSERT":
                ins = entity.dxf.insert[:2]
                all_x.append(ins[0])
                all_y.append(ins[1])
            elif dxftype == "DIMENSION":
                try:
                    def_pt = entity.dxf.defpoint[:2]
                    all_x.append(def_pt[0])
                    all_y.append(def_pt[1])
                    text_mid = entity.dxf.text_midpoint[:2]
                    all_x.append(text_mid[0])
                    all_y.append(text_mid[1])
                except Exception:
                    pass
            else:
                try:
                    bbox = entity.bbox()
                    all_x.extend([bbox.extmin[0], bbox.extmax[0]])
                    all_y.extend([bbox.extmin[1], bbox.extmax[1]])
                except Exception:
                    pass
        except Exception:
            continue

    if not all_x:
        raise ValueError("DXF 文件中没有可渲染的图元")

    margin = 2.0
    x_min, x_max = min(all_x) - margin, max(all_x) + margin
    y_min, y_max = min(all_y) - margin, max(all_y) + margin

    fig_w = max(x_max - x_min, 1) * 0.4
    fig_h = max(y_max - y_min, 1) * 0.4

    # 限制最大图像尺寸
    max_pixels = 4096
    if fig_w * dpi > max_pixels or fig_h * dpi > max_pixels:
        scale = min(max_pixels / (fig_w * dpi), max_pixels / (fig_h * dpi))
        fig_w *= scale
        fig_h *= scale
        logger.info(
            f"  图像尺寸超过 {max_pixels}px，等比例缩小至 "
            f"{fig_w*dpi:.0f}x{fig_h*dpi:.0f}px"
        )

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal")
    ax.axis("off")

    render_count = 0
    for entity in msp:
        layer = entity.dxf.layer if hasattr(entity.dxf, "layer") else ""
        if layer.upper() == "META":
            continue

        dxftype = entity.dxftype()
        try:
            if dxftype == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                ax.plot([s[0], e[0]], [s[1], e[1]], "k-", linewidth=0.3)
                render_count += 1
            elif dxftype == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                xs, ys = zip(*pts)
                ax.plot(xs, ys, "k-", linewidth=0.3)
                render_count += 1
            elif dxftype == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(plt.Circle((cx, cy), r, fill=False, color="k", linewidth=0.3))
                render_count += 1
            elif dxftype == "ARC":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(
                    plt.Arc(
                        (cx, cy), r * 2, r * 2, angle=0,
                        theta1=entity.dxf.start_angle, theta2=entity.dxf.end_angle,
                        color="k", linewidth=0.3,
                    )
                )
                render_count += 1
            elif dxftype == "TEXT":
                ins = entity.dxf.insert[:2]
                text = entity.dxf.text
                height = getattr(entity.dxf, "height", 1.0)
                ax.text(ins[0], ins[1], text, fontsize=height * 2, color="k")
                render_count += 1
            elif dxftype == "MTEXT":
                ins = entity.dxf.insert[:2]
                text = entity.text
                height = getattr(entity.dxf, "char_height", 1.0)
                ax.text(ins[0], ins[1], text, fontsize=height * 2, color="k")
                render_count += 1
            elif dxftype == "POINT":
                loc = entity.dxf.location[:2]
                ax.plot(loc[0], loc[1], "k.", markersize=1)
                render_count += 1
            elif dxftype == "SPLINE":
                pts = list(entity.control_points)
                if len(pts) >= 2:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    ax.plot(xs, ys, "k-", linewidth=0.3)
                    render_count += 1
            elif dxftype == "ELLIPSE":
                cx, cy = entity.dxf.center[:2]
                major = entity.dxf.major_axis
                ratio = entity.dxf.ratio
                r = math.sqrt(major[0]**2 + major[1]**2)
                ax.add_patch(
                    plt.Ellipse(
                        (cx, cy), r * 2, r * 2 * ratio,
                        angle=math.degrees(math.atan2(major[1], major[0])),
                        fill=False, color="k", linewidth=0.3,
                    )
                )
                render_count += 1
            elif dxftype == "HATCH":
                try:
                    for path in entity.paths:
                        if hasattr(path, "vertices"):
                            verts = list(path.vertices)
                            if len(verts) >= 2:
                                xs = [v[0] for v in verts]
                                ys = [v[1] for v in verts]
                                ax.plot(xs, ys, "k-", linewidth=0.3)
                                render_count += 1
                except Exception:
                    pass
            elif dxftype == "INSERT":
                try:
                    block = doc.blocks.get(entity.dxf.name)
                    if block:
                        ins_x, ins_y = entity.dxf.insert[:2]
                        for blk_entity in block:
                            blk_layer = blk_entity.dxf.layer if hasattr(blk_entity.dxf, "layer") else ""
                            if blk_layer.upper() == "META":
                                continue
                            blk_type = blk_entity.dxftype()
                            if blk_type == "LINE":
                                s = blk_entity.dxf.start
                                e = blk_entity.dxf.end
                                ax.plot(
                                    [ins_x + s[0], ins_x + e[0]],
                                    [ins_y + s[1], ins_y + e[1]],
                                    "k-", linewidth=0.3,
                                )
                                render_count += 1
                            elif blk_type == "LWPOLYLINE":
                                pts = [(ins_x + v[0], ins_y + v[1]) for v in blk_entity.get_points()]
                                xs, ys = zip(*pts)
                                ax.plot(xs, ys, "k-", linewidth=0.3)
                                render_count += 1
                except Exception:
                    pass
            elif dxftype == "DIMENSION":
                try:
                    def_pt = entity.dxf.defpoint[:2]
                    text_mid = entity.dxf.text_midpoint[:2]
                    ax.plot([def_pt[0], text_mid[0]], [def_pt[1], text_mid[1]], "k-", linewidth=0.2)
                    render_count += 1
                except Exception:
                    pass
        except Exception:
            continue

    logger.info(f"  渲染了 {render_count} 个图元")

    # 保存为 JPG（白底，紧凑裁剪）
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = tmp.name
    tmp.close()
    plt.savefig(
        tmp_path, dpi=dpi, bbox_inches="tight", pad_inches=0.05, facecolor="white"
    )
    plt.close(fig)
    return tmp_path


def compute_non_white_ratio(image_path: str) -> float:
    """
    计算图像中非白色像素的占比。
    用于评估渲染图的信息密度——建筑图纸通常信息密度极低，
    这是导致 YOLO 推理置信度集中在 0.05-0.20 的根本原因。

    Args:
        image_path: JPG 图像路径

    Returns:
        float: 非白色像素占比（0.0~1.0），例如 0.002 表示 0.2%
    """
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)
    # 非白色判断：RGB 三个通道中至少有一个 < 250
    # 为什么用 250 而不是 255？因为 JPG 压缩会导致纯白区域略微变色，
    # 取 250 阈值可以容忍 JPG 压缩带来的轻微色差。
    non_white = np.sum(np.any(arr < 250, axis=2))
    total = arr.shape[0] * arr.shape[1]
    return non_white / total if total > 0 else 0.0


def create_empty_label(output_path: str) -> None:
    """
    创建空的 YOLO 标注文件。
    文件内容为空，等待人工标注后填充。

    YOLO 格式说明：
    - 每行一个标注对象
    - 格式: <class_id> <x_center> <y_center> <width> <height>
    - 坐标值为归一化值（0~1），相对于图像宽高
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    open(output_path, "w").close()


def process_drawing(
    dxf_path: Path,
    output_dir: Path,
    dpi: int = 200,
    dry_run: bool = False,
) -> dict:
    """
    处理单张 DXF 图纸：渲染 + 创建空白标注。

    Args:
        dxf_path: DXF 文件路径
        output_dir: 输出目录
        dpi: 渲染分辨率
        dry_run: 仅检查不渲染

    Returns:
        dict: 图纸信息字典
    """
    info = {
        "file": dxf_path.name,
        "status": "ok",
        "error": None,
    }

    if dry_run:
        # 仅检查文件是否存在和大小
        info["file_size_kb"] = round(dxf_path.stat().st_size / 1024, 1)
        info["dry_run"] = True
        return info

    try:
        # 步骤 1：渲染 DXF 为 JPG
        t0 = time.time()
        tmp_path = render_dxf(str(dxf_path), dpi=dpi)
        render_time = time.time() - t0

        # 步骤 2：获取图像信息
        from PIL import Image
        img = Image.open(tmp_path)
        
        width, height = img.size
        file_size_kb = round(os.path.getsize(tmp_path) / 1024, 1)
        non_white_ratio = compute_non_white_ratio(tmp_path)

        # 复制到输出目录
        stem = dxf_path.stem
        out_jpg = output_dir / f"{stem}.jpg"
        output_dir.mkdir(parents=True, exist_ok=True)
        img.save(str(out_jpg), "JPEG", quality=95)

        # 删除临时文件
        os.unlink(tmp_path)

        # 创建空白标注文件
        label_path = output_dir / "labels" / f"{stem}.txt"
        create_empty_label(str(label_path))

        info.update({
            "width": width,
            "height": height,
            "file_size_kb": file_size_kb,
            "non_white_ratio": round(non_white_ratio, 6),
            "render_time_s": round(render_time, 2),
            "output_jpg": str(out_jpg),
            "output_label": str(label_path),
        })
    except Exception as e:
        info["status"] = "error"
        info["error"] = str(e)

    return info


def main():
    parser = argparse.ArgumentParser(description="BAA 真实图纸渲染脚本")
    parser.add_argument("--drawings", type=str, default=str(DEFAULT_DRAWINGS_DIR),
                        help=f"DXF 图纸目录（默认: {DEFAULT_DRAWINGS_DIR})")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR),
                        help=f"输出目录（默认: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--dpi", type=int, default=200,
                        help="渲染分辨率（默认: 200）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅检查不渲染")
    parser.add_argument("--single", type=str, default=None,
                        help="只处理单张图纸（文件名）")
    args = parser.parse_args()

    drawings_dir = Path(args.drawings)
    output_dir = Path(args.output_dir)

    if not drawings_dir.exists():
        logger.error(f"图纸目录不存在: {drawings_dir}")
        sys.exit(1)

    # 收集 DXF 文件
    # 优先从 data/drawings/real/ 收集，如果为空则从 data/ 根目录收集
    # 为什么这样做？data/drawings/real/ 是预期的标注目录，但部分 DXF 副本在根目录才有完整内容
    if args.single:
        dxf_files = [drawings_dir / args.single]
        if not dxf_files[0].exists():
            dxf_files = [drawings_dir / f"{args.single}.dxf"]
    else:
        dxf_files = sorted(drawings_dir.glob("*.dxf"))

    # 如果 data/drawings/real/ 下没有文件，从 data/ 根目录补
    if not dxf_files:
        root_data_dir = DEFAULT_ROOT_DATA_DIR
        dxf_files = sorted(root_data_dir.glob("*.dxf"))
        if dxf_files:
            logger.info(f"从 {root_data_dir}/ 找到 {len(dxf_files)} 个 DXF 文件（备用目录）")

    if not dxf_files:
        logger.warning(f"未找到 DXF 文件: {drawings_dir}")
        sys.exit(0)

    logger.info(f"找到 {len(dxf_files)} 个 DXF 文件")
    logger.info(f"输出目录: {output_dir}")
    if args.dry_run:
        logger.info("【干运行模式】仅检查不渲染")
    logger.info(f"渲染分辨率: {args.dpi} dpi")
    print()

    results = []
    success_count = 0
    error_count = 0

    for dxf_path in dxf_files:
        if not dxf_path.exists():
            logger.warning(f"  文件不存在: {dxf_path}")
            continue
        logger.info(f"  处理: {dxf_path.name}")
        info = process_drawing(dxf_path, output_dir, dpi=args.dpi, dry_run=args.dry_run)
        results.append(info)

        if info["status"] == "ok":
            success_count += 1
            if not args.dry_run:
                logger.info(f"    ├─ 尺寸: {info['width']}x{info['height']}px")
                logger.info(f"    ├─ 文件大小: {info['file_size_kb']} KB")
                logger.info(f"    ├─ 非白像素占比: {info['non_white_ratio']*100:.4f}%")
                logger.info(f"    ├─ 渲染耗时: {info['render_time_s']:.2f}s")
                logger.info(f"    ├─ 输出图像: {info['output_jpg']}")
                logger.info(f"    └─ 输出标注: {info['output_label']}")
            else:
                logger.info(f"    └─ 文件大小: {info['file_size_kb']} KB (干运行)")
        else:
            error_count += 1
            logger.error(f"    └─ 错误: {info['error']}")
        print()

    # 输出汇总
    logger.info("=" * 50)
    logger.info(f"处理完成: {success_count} 成功, {error_count} 失败, 共 {len(results)} 张")
    if not args.dry_run and success_count > 0:
        non_white_ratios = [r.get("non_white_ratio", 0) for r in results if r["status"] == "ok"]
        if non_white_ratios:
            avg_non_white = sum(non_white_ratios) / len(non_white_ratios)
            logger.info(f"平均非白像素占比: {avg_non_white*100:.4f}%")
            min_ratio = min(non_white_ratios)
            max_ratio = max(non_white_ratios)
            logger.info(f"非白像素占比范围: {min_ratio*100:.4f}% ~ {max_ratio*100:.4f}%")
        logger.info(f"标注文件目录: {output_dir / 'labels'}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
