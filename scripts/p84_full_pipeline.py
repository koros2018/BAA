"""
P84 A 管线：全量 DXF → floor 切分 → floor 渲染 → YOLO 标注
=============================================================
"""
import sys, os, shutil, math
from pathlib import Path
from collections import Counter
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT))

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

# ── 配置 ──────────────────────────────────────────
INPUT_FILES = [
    'data/图纸/1东莞通施工图-报审170823/东莞通-建筑-外部参照（不打印）.dxf',
    'data/图纸/中原人工智能计算中心/20210409-3#泵房_t3.dxf',
    'data/图纸/中原人工智能计算中心/A1云计算中心平面图0405_t3.dxf',
    'data/图纸/红土深汕A1栋数据中心施工图220108/01-建筑/建筑.dxf',
    'data/图纸/红土深汕A1栋数据中心施工图220108/02-结构/结构.dxf',
]

OUTPUT_DIR = 'output/p84_train_data'
MAX_IMG_SIZE = 1024
DPI = 100
MIN_ENTITY_PX = 10
Y_GAP_THRESHOLD = 2000

# ── Entity type → YOLO class mapping ──────────────
ENTITY_TO_YOLO = {
    'wall':              0,
    'door':              1,
    'window':            2,
    'stair':             3,
    'staircase':         3,
    'stairs':            3,
    'corridor':          4,
    'fire_door':         5,
    'exit':              6,
    'emergency_exit':    6,
    'safety_exit':       6,
    'fire_lane':         7,
    'fire_zone':         8,
    'fire_compartment':  8,
    'fire_window':       9,
    'shaft':             10,
    'vertical_shaft':    10,
    'cable_shaft':       10,
    'pipe_shaft':        10,
    'duct_shaft':        10,
    'room':              11,
    'exit_sign':         12,
    'evacuation_sign':   12,
    'directional_sign':  12,
    'sprinkler_system':  13,
    'sprinkler':         13,
    'sprinkler_head':    13,
    'fire_alarm':        14,
    'fire_detector':     14,
    'heat_detector':     14,
    'smoke_detector':    14,
    'manual_call_point': 14,
    'insulation':        15,
    'wall_insulation':   15,
    'evacuation_lighting': 16,
    'emergency_light':   16,
    'emergency_lighting':16,
    'evacuation_route':  16,
    'refuge_floor':      17,
    'refuge_area':       17,
    'refuge_room':       17,
    'shelter':           17,
}

YOLO_NAME = {
    0:'wall', 1:'door', 2:'window', 3:'staircase', 4:'corridor',
    5:'fire_door', 6:'exit', 7:'fire_lane', 8:'fire_zone', 9:'fire_window',
    10:'shaft', 11:'room', 12:'exit_sign', 13:'sprinkler_system',
    14:'fire_alarm', 15:'insulation', 16:'evacuation_lighting', 17:'refuge_floor',
}

# ── Floor 切分 ─────────────────────────────────────
def split_floors(primitives):
    bands = []
    for p in primitives:
        b = p.bbox
        if b and b.get('width', 0) > 10 and b.get('height', 0) > 10:
            y0, y1 = b['y'], b['y'] + b.get('height', 0)
            bands.append((y0, y1))
    bands.sort()
    floors = []
    cur = None
    for y0, y1 in bands:
        if cur is None:
            cur = (y0, y1)
        elif y0 > cur[1] + Y_GAP_THRESHOLD:
            floors.append(cur); cur = (y0, y1)
        else:
            cur = (min(cur[0], y0), max(cur[1], y1))
    if cur: floors.append(cur)
    return floors

# ── 渲染 ────────────────────────────────────────────
def render_floor(dxf_path, x_min, x_max, y_min, y_max):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    x_min -= 200; x_max += 200; y_min -= 200; y_max += 200
    ww, hh = x_max - x_min, y_max - y_min
    fw, fh = ww / 25.4, hh / 25.4
    ratio = min(MAX_IMG_SIZE / (fw * DPI), MAX_IMG_SIZE / (fh * DPI), 1.0)
    fw *= ratio; fh *= ratio
    fig, ax = plt.subplots(figsize=(fw, fh), dpi=DPI)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect('equal'); ax.axis('off')
    for entity in msp:
        try:
            if hasattr(entity.dxf, 'layer') and entity.dxf.layer.upper() == 'META':
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
                cx, cy = entity.dxf.center[:2]; r = entity.dxf.radius
                ax.add_patch(plt.Circle((cx, cy), r, fill=False, color='k', linewidth=0.3))
            elif t == 'ARC':
                cx, cy = entity.dxf.center[:2]; r = entity.dxf.radius
                ax.add_patch(plt.Arc((cx, cy), r*2, r*2, angle=0,
                    theta1=entity.dxf.start_angle, theta2=entity.dxf.end_angle,
                    color='k', linewidth=0.3))
        except: continue
    img = f'{OUTPUT_DIR}/images/f_{len(os.listdir(f"{OUTPUT_DIR}/images"))%1000}.jpg'
    plt.savefig(img, dpi=DPI, bbox_inches='tight', pad_inches=0.05, facecolor='white')
    plt.close(fig)
    w, h = Image.open(img).size
    return img, (w, h)

# ── 主流程 ──────────────────────────────────────────
def main():
    os.makedirs(f'{OUTPUT_DIR}/images', exist_ok=True)
    os.makedirs(f'{OUTPUT_DIR}/labels', exist_ok=True)

    parser = DrawingParser()
    analyzer = SemanticAnalyzer()
    grand_total = 0
    grand_type = Counter()
    img_count = 0

    for dxf_path in INPUT_FILES:
        if not os.path.exists(dxf_path):
            print(f'SKIP (missing): {os.path.basename(dxf_path)}'); continue
        print(f'\n=== {os.path.basename(dxf_path)} ===')
        result = parser.parse(dxf_path, file_id=os.path.basename(dxf_path))
        if not result.success:
            print(f'  SKIP: {result.error}'); continue

        floors = split_floors(result.primitives)
        print(f'  Primitives: {len(result.primitives)}, Floors: {len(floors)}')

        analysis = analyzer.analyze(result.primitives)
        entities = analysis.get('entities', [])

        for i, (y0, y1) in enumerate(floors):
            xs = [p.bbox['x'] for p in result.primitives if p.bbox]
            ys = [p.bbox['y'] for p in result.primitives if p.bbox]
            x_min, x_max = min(xs), max(p.bbox['x'] + p.bbox.get('width', 0)
                                        for p in result.primitives if p.bbox)
            img_path, (w, h) = render_floor(dxf_path, x_min, x_max, y0, y1)
            img_count += 1
            s_x = w / (x_max - x_min)
            s_y = h / (y1 - y0)
            lines = []
            type_ct = Counter()
            for e in entities:
                et = e.get('type', '')
                cid = ENTITY_TO_YOLO.get(et)
                if cid is None: continue
                b = e.get('bbox', {})
                bw, bh = b.get('width', 0), b.get('height', 0)
                if bw <= 0 or bh <= 0: continue
                by0 = b['y']
                # Floor membership: center in floor range
                if not (y0 - 2000 < by0 + bh/2 < y1 + 2000): continue
                px_x = (b['x'] - x_min) * s_x
                px_y = (by0 - y0) * s_y
                px_w = bw * s_x
                px_h = bh * s_y
                if px_w < MIN_ENTITY_PX or px_h < MIN_ENTITY_PX: continue
                if px_w > w * 0.95 or px_h > h * 0.95: continue
                cx, cy = (px_x + px_w/2) / w, (px_y + px_h/2) / h
                ww, hh = px_w / w, px_h / h
                if not (0 <= cx <= 1 and 0 <= cy <= 1): continue
                lines.append(f'{cid} {cx:.6f} {cy:.6f} {ww:.6f} {hh:.6f}')
                type_ct[YOLO_NAME[cid]] += 1
            if lines:
                label = f'{OUTPUT_DIR}/labels/img_{img_count-1:04d}.txt'
                with open(label, 'w') as f: f.write('\n'.join(lines) + '\n')
                grand_total += len(lines)
                grand_type.update(type_ct)
                print(f'  floor {i}: {w}x{h}  yolo={len(lines)}  {dict(type_ct.most_common(6))}')

    print(f'\n=== FINAL ===')
    print(f'Images: {img_count}, Labels: {len([f for f in os.listdir(f"{OUTPUT_DIR}/labels") if f.endswith(".txt")])}')
    print(f'Total annotations: {grand_total}')
    for t, c in grand_type.most_common():
        print(f'  {t}: {c}')

if __name__ == '__main__':
    main()
