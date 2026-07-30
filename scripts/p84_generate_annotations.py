"""
P84 数据扩充 — 从 DXF 生成 YOLO 训练标注（修正版）
"""
import sys, os, shutil, math, random
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.baa_engine.drawing_parser import DrawingParser, RawPrimitive
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer
from src.baa_engine.yolo_integrator import YOLOIntegrator
import ezdxf
from PIL import Image

# ── 配置 ──
FLOOR_PLAN_FILES = [
    'data/图纸/1东莞通施工图-报审170823/东莞通-建筑-外部参照（不打印）.dxf',
    'data/图纸/中原人工智能计算中心/20210409-3#泵房_t3.dxf',
    'data/图纸/中原人工智能计算中心/A1IDC及通信机楼结构平面图20161227z.dxf',
    'data/图纸/中原人工智能计算中心/A1云计算中心平面图0405_t3.dxf',
    'data/图纸/中原人工智能计算中心/ZY项目1#数据中心机房平立剖面图_t7_t3.dxf',
    'data/图纸/中原人工智能计算中心/中原人工智能计算中心总图-0409_t3.dxf',
    'data/图纸/中原人工智能计算中心/基础+2#,3#上部-202104.dxf',
    'data/图纸/爱特云翔大数据中心/20210927-山东斐讯云翔大数据中心二期项目图纸（打印版）/01电气/_建筑底图参照.dxf',
    'data/图纸/爱特云翔大数据中心/光纤直连项目/平面布置底图0712(1).dxf',
    'data/图纸/爱特云翔大数据中心/光纤直连项目/数据中心设备平面图.dxf',
    'data/图纸/红土深汕A1栋数据中心施工图220108/01-建筑/建筑.dxf',
    'data/图纸/红土深汕A1栋数据中心施工图220108/02-结构/结构.dxf',
    'data/图纸/红土深汕A1栋数据中心施工图220108/ECC-建筑_t3.dxf',
    'data/图纸/红土深汕A1栋数据中心施工图220108/ECC及室外-电气_t3.dxf',
]

# YOLO 类别 ID 映射（与 YOLO_CLASSES 一致）
CLASS_ID_MAP = {
    'wall': 0, 'door': 1, 'window': 2, 'staircase': 3, 'corridor': 4,
    'fire_door': 5, 'exit': 6, 'fire_lane': 7, 'fire_zone': 8,
    'fire_window': 9, 'shaft': 10, 'room': 11, 'exit_sign': 12,
    'sprinkler_system': 13, 'fire_alarm': 14, 'insulation': 15,
    'evacuation_lighting': 16, 'refuge_floor': 17,
}

# 仅保留训练集缺的 + 重点类
TARGET_CLASSES = {'shaft', 'exit_sign', 'evacuation_lighting', 'refuge_floor',
                  'fire_door', 'fire_lane', 'fire_window', 'sprinkler_system',
                  'room', 'door', 'window', 'staircase', 'exit', 'fire_alarm',
                  'wall', 'fire_zone', 'corridor', 'insulation'}

OUTPUT_IMG_DIR = 'output/p84_train_data/images'
OUTPUT_LABEL_DIR = 'output/p84_train_data/labels'


def world_bbox_from_primitives(primitives):
    """从 RawPrimitive 列表计算世界坐标边界"""
    all_x, all_y = [], []
    for p in primitives:
        b = p.bbox
        if b and b.get('width') and b.get('height'):
            all_x.extend([b['x'], b['x'] + b['width']])
            all_y.extend([b['y'], b['y'] + b['height']])
    if not all_x:
        return None
    margin = 2.0
    return {
        'x': min(all_x) - margin,
        'y': min(all_y) - margin,
        'width': (max(all_x) - min(all_x)) + 2*margin,
        'height': (max(all_y) - min(all_y)) + 2*margin,
    }


def process_drawing(dxf_path):
    base_name = Path(dxf_path).stem
    print(f'\n--- {base_name} ---')

    # 1. 渲染
    integrator = YOLOIntegrator()
    img_path = integrator._render_dxf_cropped(dxf_path, dpi=100)
    if img_path is None:
        print(f'  SKIP: render failed')
        return None

    out_img = os.path.join(OUTPUT_IMG_DIR, base_name + '.jpg')
    shutil.copy2(img_path, out_img)
    img_w, img_h = Image.open(out_img).size
    print(f'  Image: {img_w}x{img_h}')

    # 2. 解析
    parser = DrawingParser()
    result = parser.parse(dxf_path, file_id=base_name)
    if not result.success:
        print(f'  SKIP: parse failed: {result.error}')
        return None
    print(f'  Primitives: {len(result.primitives)}')

    # 3. 语义分析（采样控制防止 OOM）
    primitives = result.primitives
    if len(primitives) > 20000:
        random.seed(42)
        primitives = random.sample(primitives, 20000)
        print(f'  Sampled: {len(primitives)}')

    analyzer = SemanticAnalyzer()
    analysis = analyzer.analyze(primitives, dxf_path=dxf_path)
    entities = analysis.get('entities', [])
    print(f'  Entities: {len(entities)}')

    # 4. 世界坐标 → 像素坐标
    wb = world_bbox_from_primitives(result.primitives)
    if not wb:
        print(f'  SKIP: no world bbox')
        return None

    px_per_mm_x = img_w / wb['width']
    px_per_mm_y = img_h / wb['height']

    yolo_lines = []
    type_counts = Counter()
    for ent in entities:
        etype = ent.type if hasattr(ent, 'type') else ent.get('type', '')
        if etype not in TARGET_CLASSES or etype not in CLASS_ID_MAP:
            continue

        bbox = ent.bbox if hasattr(ent, 'bbox') else ent.get('bbox', {})
        if not bbox:
            continue
        x, y, w, h = bbox.get('x'), bbox.get('y'), bbox.get('width'), bbox.get('height')
        if x is None or y is None or w is None or h is None:
            continue
        if w <= 0 or h <= 0:
            continue

        px_x = (x - wb['x']) * px_per_mm_x
        px_y = (y - wb['y']) * px_per_mm_y
        px_w = w * px_per_mm_x
        px_h = h * px_per_mm_y

        cx = (px_x + px_w / 2) / img_w
        cy = (px_y + px_h / 2) / img_h
        ww = px_w / img_w
        hh = px_h / img_h

        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < ww <= 1 and 0 < hh <= 1):
            continue

        # 过滤明显过大的 bbox（如整张图的 90%+）
        if ww > 0.95 and hh > 0.95:
            continue

        cid = CLASS_ID_MAP[etype]
        yolo_lines.append(f'{cid} {cx:.6f} {cy:.6f} {ww:.6f} {hh:.6f}')
        type_counts[etype] += 1

    print(f'  YOLO labels: {len(yolo_lines)}')
    for t, c in type_counts.most_common(10):
        print(f'    {t}: {c}')

    if yolo_lines:
        out_label = os.path.join(OUTPUT_LABEL_DIR, base_name + '.txt')
        with open(out_label, 'w') as f:
            f.write('\n'.join(yolo_lines) + '\n')
        return {'name': base_name, 'labels': len(yolo_lines), 'types': dict(type_counts)}
    return None


def main():
    os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)
    os.makedirs(OUTPUT_LABEL_DIR, exist_ok=True)

    valid = [f for f in FLOOR_PLAN_FILES if os.path.exists(f)]
    print(f'Valid DXF: {len(valid)} / {len(FLOOR_PLAN_FILES)}')

    results = []
    for f in valid:
        r = process_drawing(f)
        if r:
            results.append(r)

    print(f'\n=== Summary ===')
    print(f'Processed: {len(results)} / {len(valid)}')
    all_types = Counter()
    for r in results:
        all_types.update(r['types'])
    print(f'Total annotations: {sum(all_types.values())}')
    for t, c in all_types.most_common():
        print(f'  {t}: {c}')


if __name__ == '__main__':
    main()
