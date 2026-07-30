"""
P84 数据扩充 — 逐 Floor 渲染 + DXF 原生标注
==================================================

利用 DXF 的图层规则 + Y-gap 自动切分楼层，
每层独立渲染高分辨率图像，生成 YOLO 格式标注。

完全自动化，无需人工标注。
"""
import sys, os, shutil, math
from pathlib import Path
from collections import Counter
import numpy as np
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

# ── 配置 ──────────────────────────────────────────
INPUT_DXF = 'data/图纸/中原人工智能计算中心/20210409-3#泵房_t3.dxf'
OUTPUT_DIR = 'output/p84_floors'
MAX_IMG_SIZE = 1024       # 每层最大尺寸
DPI = 100
MIN_ENTITY_PX = 10        # bbox 至少 10px 才保留
Y_GAP_THRESHOLD = 2000    # Y 方向 gap 大于此值视为新楼层

# YOLO 类别 ID（与 YOLO_CLASSES 一致）
CLASS_ID_MAP = {
    'wall': 0, 'door': 1, 'window': 2, 'stair': 3,
    'staircase': 3, 'corridor': 4,
    'fire_door': 5, 'exit': 6, 'fire_lane': 7, 'fire_zone': 8,
    'fire_window': 9, 'shaft': 10, 'room': 11, 'exit_sign': 12,
    'sprinkler_system': 13, 'fire_alarm': 14, 'insulation': 15,
    'evacuation_lighting': 16, 'refuge_floor': 17,
}
YOLO_NAME_MAP = {v: k for k, v in CLASS_ID_MAP.items()}

# ── Floor 切分 ─────────────────────────────────────
def split_floors(primitives):
    """根据 bbox Y 坐标 gap 切分 floor"""
    bands = []
    for p in primitives:
        b = p.bbox
        if b and b.get('width', 0) > 10 and b.get('height', 0) > 10:
            y0 = b['y']
            y1 = b['y'] + b.get('height', 0)
            bands.append((y0, y1))
    bands.sort()
    floors = []
    current = None
    for y0, y1 in bands:
        if current is None:
            current = (y0, y1)
        elif y0 > current[1] + Y_GAP_THRESHOLD:
            floors.append(current)
            current = (y0, y1)
        else:
            current = (min(current[0], y0), max(current[1], y1))
    if current:
        floors.append(current)
    return floors


# ── 渲染 ────────────────────────────────────────────
def render_floor(dxf_path, floor_bbox, dpi=DPI, max_size=MAX_IMG_SIZE):
    """渲染单个 floor 区域为 JPEG"""
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    x_min, y_min = floor_bbox[0] - 200, floor_bbox[1] - 200
    x_max, y_max = floor_bbox[2] + 200, floor_bbox[3] + 200
    w_world = x_max - x_min
    h_world = y_max - y_min
    fig_w = w_world / 25.4 * dpi / dpi  # mm to inches at dpi
    fig_h = h_world / 25.4 * dpi / dpi
    # 缩放
    ratio = min(max_size / (fig_w * dpi), max_size / (fig_h * dpi), 1.0)
    fig_w *= ratio
    fig_h *= ratio
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal')
    ax.axis('off')
    for entity in msp:
        try:
            layer = entity.dxf.layer if hasattr(entity.dxf, 'layer') else ''
            if layer.upper() == 'META':
                continue
            t = entity.dxftype()
            if t == 'LINE':
                s, e = entity.dxf.start, entity.dxf.end
                ax.plot([s[0], e[0]], [s[1], e[1]], 'k-', linewidth=0.3)
            elif t == 'LWPOLYLINE':
                pts = [(v[0], v[1]) for v in entity.get_points()]
                xs, ys = zip(*pts)
                ax.plot(xs, ys, 'k-', linewidth=0.3)
            elif t == 'CIRCLE':
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.3))
            elif t == 'ARC':
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(plt.Arc((cx, cy), r*2, r*2, angle=0,
                    theta1=entity.dxf.start_angle, theta2=entity.dxf.end_angle,
                    color='k', linewidth=0.3))
        except Exception:
            continue
    tmp = os.path.join(OUTPUT_DIR, f'floor_{len(os.listdir(OUTPUT_DIR))%100}.jpg')
    plt.savefig(tmp, dpi=dpi, bbox_inches='tight', pad_inches=0.05, facecolor='white')
    plt.close(fig)
    w, h = Image.open(tmp).size
    return tmp, (w, h), (x_min, y_min, x_max, y_max)


# ── 主流程 ──────────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(f'{OUTPUT_DIR}/labels', exist_ok=True)
    print(f'Processing: {INPUT_DXF}')
    print(f'Output: {OUTPUT_DIR}')

    # 1. 解析
    from src.baa_engine.drawing_parser import DrawingParser
    parser = DrawingParser()
    result = parser.parse(INPUT_DXF, file_id='floor_test')
    print(f'Primitives: {len(result.primitives)}')

    # 2. 切分 floor
    floors = split_floors(result.primitives)
    print(f'Floors: {len(floors)}')
    for i, (y0, y1) in enumerate(floors):
        h = y1 - y0
        print(f'  Floor {i}: y=[{y0:.0f},{y1:.0f}] height={h:.0f}')

    # 3. 语义分析（全量一次）
    analyzer = SemanticAnalyzer()
    analysis = analyzer.analyze(result.primitives, dxf_path=INPUT_DXF)
    entities = analysis.get('entities', [])
    print(f'Entities: {len(entities)}')

    # 4. 逐 floor 处理
    img_paths = []
    label_paths = []
    all_type_counts = Counter()

    for i, (y0, y1) in enumerate(floors):
        x_min_all = min(p.bbox['x'] for p in result.primitives
                        if p.bbox and p.bbox.get('width', 0) > 10)
        x_max_all = max(p.bbox['x'] + p.bbox.get('width', 0)
                        for p in result.primitives
                        if p.bbox and p.bbox.get('width', 0) > 10)
        floor_bbox = (x_min_all, y0, x_max_all, y1)

        img_path, (w, h), (fx0, fy0, fx1, fy1) = render_floor(INPUT_DXF, floor_bbox)
        img_paths.append(img_path)

        # 计算像素映射
        px_scale_x = w / (fx1 - fx0)
        px_scale_y = h / (fy1 - fy0)

        # 筛选该 floor 的实体
        floor_ents = []
        for e in entities:
            b = e.get('bbox', {})
            et = e.get('type', '')
            if et not in CLASS_ID_MAP:
                continue
            if not b:
                continue
            bw, bh = b.get('width', 0), b.get('height', 0)
            if bw <= 0 or bh <= 0:
                continue
            bx0, bx1 = b['x'], b['x'] + bw
            by0, by1 = b['y'], b['y'] + bh
            # 判断实体是否主要位于此 floor
            if by0 < fy0 - 1000 and by1 < fy0 + 1000:
                continue
            if by1 > fy1 + 1000 and by0 > fy1 - 1000:
                continue
            floor_ents.append((e, b, bx0, by0, bw, bh))

        # 转 YOLO
        yolo_lines = []
        for e, b, bx0, by0, bw, bh in floor_ents:
            et = e.get('type', '')
            if et not in CLASS_ID_MAP:
                continue
            px_x = (bx0 - fx0) * px_scale_x
            px_y = (by0 - fy0) * px_scale_y
            px_w = bw * px_scale_x
            px_h = bh * px_scale_y
            if px_w < MIN_ENTITY_PX or px_h < MIN_ENTITY_PX:
                continue
            if px_w > w * 0.95 or px_h > h * 0.95:
                continue
            cx = (px_x + px_w / 2) / w
            cy = (px_y + px_h / 2) / h
            ww = px_w / w
            hh = px_h / h
            if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < ww <= 1 and 0 < hh <= 1):
                continue
            cid = CLASS_ID_MAP[et]
            yolo_lines.append(f'{cid} {cx:.6f} {cy:.6f} {ww:.6f} {hh:.6f}')
            all_type_counts[et] += 1

        if yolo_lines:
            label_path = f'{OUTPUT_DIR}/labels/floor_{i:03d}.txt'
            with open(label_path, 'w') as f:
                f.write('\n'.join(yolo_lines) + '\n')
            print(f'  Floor {i}: {w}x{h}, entities={len(floor_ents)}, yolo={len(yolo_lines)}')
            label_paths.append(label_path)
        else:
            print(f'  Floor {i}: {w}x{h}, entities={len(floor_ents)}, yolo=0 (all too small)')

    print(f'\nTotal images: {len(img_paths)}, labels: {len(label_paths)}')
    print('Type distribution:')
    for t, c in all_type_counts.most_common():
        print(f'  {t}: {c}')
    print(f'Total annotations: {sum(all_type_counts.values())}')


if __name__ == '__main__':
    main()
