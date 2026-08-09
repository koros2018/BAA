"""
P84 YOLO 数据扩充脚本
=======================
从测试图纸目录扫描 DXF → 语义解析提取实体 → 渲染 PNG → 生成 YOLO 标签

数据飞轮：
1. 扫描测试图纸目录，筛选可解析 DXF
2. DrawingParser.parse → 获取 primitives
3. SemanticAnalyzer.analyze → 获取带 bbox 的语义实体
4. 渲染 DXF 为 PNG（复用 YOLODetectionIntegrator._render_dxf_cropped）
5. 将实体世界坐标 bbox 映射到像素坐标，写入 YOLO 格式标签
6. 统计并生成 dataset 报告

使用方式：
    python3 scripts/p84_augment.py
"""

import sys
import os
import json
import time
import logging
from pathlib import Path
from collections import Counter, defaultdict

BAA_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, BAA_ROOT)
sys.path.insert(0, os.path.join(BAA_ROOT, 'src'))
os.environ.setdefault('BAA_TEST_MODE', '1')
os.environ.setdefault('BAA_SKIP_YOLO', '1')  # 关键：跳过 YOLO，纯用规则解析

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('p84_augment')

# ── 配置 ─────────────────────────────────────────────────
SOURCE_DIR = Path('/mnt/d/BaiduNetdiskDownload/测试图纸')
BAA_DXF_DIR = Path('data/files')  # 已有 DXF
DATASET_DIR = Path('data/p84_yolo_dataset')
PROJECT_DIR = Path(BAA_ROOT)
DPI = 100

# YOLO 类别顺序（必须与 data.yaml 一致）
YOLO_CLASSES = ['wall', 'door', 'window', 'stair', 'shaft']
CLASH_MAP = {
    'wall': 0,
    'door': 1,
    'window': 2,
    'stair': 3,
    'staircase': 3,
    'shaft': 4,
    'corridor': 4,
}

# 层名 → 语义类型映射（与 semantic_analyzer/layer_rules.py 一致）
LINE_LAYER_MAP = {
    'WALL': 'wall',
    '墙体': 'wall',
    '墙': 'wall',
    'BEAM': 'wall',
    'COLUMN': 'wall',
    '梁': 'wall',
    '柱': 'wall',
    'PF': 'wall',  # G-BEAM-PF 等含 PF 的梁层
    'DOOR': 'door',
    '门': 'door',
    'SB': 'door',
    'WINDOW': 'window',
    '窗': 'window',
    'WIND': 'window',
    'STAIR': 'stair',
    '楼梯': 'stair',
    'STAIRS': 'stair',
    'FIRE_DOOR': 'door',
    '防火门': 'door',
}


def classify_line_by_layer(layer: str) -> str:
    """根据层名匹配语义类型"""
    if not layer:
        return ''
    layer_upper = layer.upper()
    # 先尝试精确匹配
    if layer_upper in LINE_LAYER_MAP:
        return LINE_LAYER_MAP[layer_upper]
    # 子串匹配（如 G-BEAM-PF → BEAM → wall）
    for key, typ in LINE_LAYER_MAP.items():
        if key.upper() in layer_upper:
            return typ
    return ''

MAX_FILES = 1000  # 单次最大处理文件数
MIN_LABELS = 10  # 最少标注数（过滤低质量图纸）


def count_entities(sem):
    """统计语义实体数量和类型分布"""
    if 'entities' not in sem:
        return 0, {}
    counter = Counter(e['type'] for e in sem['entities'])
    return len(sem['entities']), dict(counter)


def world_bbox_to_pixel(bbox, img_w, img_h, world_x, world_y, world_w, world_h, min_area=0.00002):
    """将世界坐标 bbox 转为像素坐标（含最小面积过滤，~30px²）"""
    if world_w <= 0 or world_h <= 0:
        return None
    px = bbox['x'] - world_x
    py = bbox['y'] - world_y
    pw = bbox.get('width', 0)
    ph = bbox.get('height', 0)
    x0 = px / world_w * img_w
    y0 = py / world_h * img_h
    x1 = (px + pw) / world_w * img_w
    y1 = (py + ph) / world_h * img_h
    x_min = min(x0, x1)
    x_max = max(x0, x1)
    y_min = min(y0, y1)
    y_max = max(y0, y1)
    w = x_max - x_min
    h = y_max - y_min
    # 跳过完全退化框（零长度线段两端点重合）
    if w <= 0 and h <= 0:
        return None
    # 线型实体（wall/door/window 在 DXF 中为 LINE，零厚度）
    # 渲染后仅有 1px 厚度，需要最小像素兜底以保证 YOLO 可检测
    # YOLOv8n anchor boxes 最小检测尺寸约 5-10px，3px 太小
    MIN_THICKNESS = 10  # 像素
    if w < MIN_THICKNESS:
        cx = (x_min + x_max) / 2
        x_min = cx - MIN_THICKNESS / 2
        x_max = cx + MIN_THICKNESS / 2
        w = MIN_THICKNESS
    if h < MIN_THICKNESS:
        cy = (y_min + y_max) / 2
        y_min = cy - MIN_THICKNESS / 2
        y_max = cy + MIN_THICKNESS / 2
        h = MIN_THICKNESS
    cx = (x_min + x_max) / 2 / img_w
    cy = (y_min + y_max) / 2 / img_h
    ww = w / img_w
    hh = h / img_h
    return {'cx': cx, 'cy': cy, 'ww': ww, 'hh': hh}


def render_dxf_cropped(dxf_path, dpi=DPI):
    """复用 YOLO 渲染管道"""
    from baa_engine.yolo_integrator import YOLODetectionIntegrator
    integrator = YOLODetectionIntegrator(str(PROJECT_DIR / 'data/models/baa_yolov8n_v3/weights/best.pt'))
    return integrator._render_dxf_cropped(str(dxf_path), dpi)


def get_image_size(image_path):
    from PIL import Image
    img = Image.open(image_path)
    return img.size


def get_world_bbox(entities, target_types):
    """仅从目标类型实体 bbox 计算世界坐标边界（去除 text/dimension 等噪声）"""
    xs, ys = [], []
    for e in entities:
        if e.get('type', '') not in target_types:
            continue
        bbox = e.get('bbox')
        if not bbox:
            continue
        w = bbox.get('width', 0)
        h = bbox.get('height', 0)
        if w <= 0 and h <= 0:
            continue  # skip zero-bbox entities
        x = bbox.get('x', 0)
        y = bbox.get('y', 0)
        xs.extend([x, x + w])
        ys.extend([y, y + h])
    if not xs or not ys:
        return None
    x_min = min(xs)
    y_min = min(ys)
    x_max = max(xs)
    y_max = max(ys)
    return {'x': x_min, 'y': y_min, 'width': x_max - x_min, 'height': y_max - y_min}


def augment_one_v2(dxf_path, output_dir):
    """v2 标签生成：直接走 raw DXF LINE/LWPOLYLINE 端点，绕过 semantic analyzer

    v1 问题：
      1. semantic analyzer 把 35 条 LINE 合并为 17 个 450×300 的大房间框
      2. LINE 零厚度（height=0）→ 归一化后 <1px → YOLO 学不到
      3. door/window/stair 类全为零（层名不匹配）

    v2 方案：
      1. 直接从 drawing_parser 的 primitives 读取 LINE/LWPOLYLINE
      2. 用层名规则（classify_line_by_layer）映射语义类型
      3. 像素坐标转换时给零厚度线段加 3px 最小厚度
      4. 跳过吊筋/文字/标注等非建筑元素层
    """
    from baa_engine.drawing_parser import DrawingParser

    dxf_path = Path(dxf_path)
    name = dxf_path.stem

    (output_dir / 'images').mkdir(parents=True, exist_ok=True)
    (output_dir / 'labels').mkdir(parents=True, exist_ok=True)

    dp = DrawingParser()
    try:
        result = dp.parse(str(dxf_path))
    except Exception as e:
        logger.warning(f'{name}: parse failed: {e}')
        return {'status': 'parse_fail', 'reason': str(e)[:80]}

    dims = result.dimensions

    # 跳过非建筑层
    SKIP_LAYERS = {'TEXT', 'MTEXT', 'DIM', '吊筋', '图框', '图签', '0-文字', '图框'}

    # 收集所有 LINE/LWPOLYLINE primitives
    line_prims = []
    for p in result.primitives:
        if p.dxf_type not in ('LINE', 'LWPOLYLINE'):
            continue
        if not p.layer or any(skip in p.layer.upper() for skip in SKIP_LAYERS):
            continue
        bbox = p.bbox
        if not bbox:
            continue
        # 跳过完全退化的框（w=0 且 h=0）
        if bbox.get('width', 0) <= 0 and bbox.get('height', 0) <= 0:
            continue
        typ = classify_line_by_layer(p.layer)
        if typ not in CLASH_MAP:
            continue
        line_prims.append({'bbox': bbox, 'type': typ, 'dxf_type': p.dxf_type, 'layer': p.layer})

    if len(line_prims) < MIN_LABELS:
        return {'status': 'low_labels', 'reason': f'{len(line_prims)} classified lines < {MIN_LABELS}'}

    # 渲染
    try:
        img_path = render_dxf_cropped(dxf_path)
    except Exception as e:
        logger.warning(f'{name}: render failed: {e}')
        return {'status': 'render_fail', 'reason': str(e)[:80]}

    if img_path is None:
        return {'status': 'render_none', 'reason': 'render returned None'}

    img_w, img_h = get_image_size(img_path)

    # 计算世界坐标（仅建筑层图元）
    pxs, pys = [], []
    for p in line_prims:
        b = p['bbox']
        pxs.extend([b['x'], b['x'] + b.get('width', 0)])
        pys.extend([b['y'], b['y'] + b.get('height', 0)])
    if not pxs:
        return {'status': 'no_bbox', 'reason': 'no classified primitive bbox'}
    wb = {'x': min(pxs), 'y': min(pys), 'width': max(pxs) - min(pxs), 'height': max(pys) - min(pys)}

    # 生成 YOLO 标签（含最小厚度兜底）
    label_lines = []
    type_counter = Counter()
    for p in line_prims:
        bbox = p['bbox']
        pb = world_bbox_to_pixel(bbox, img_w, img_h, wb['x'], wb['y'], wb['width'], wb['height'])
        if pb is None:
            continue
        cls_id = CLASH_MAP[p['type']]
        label_lines.append(f"{cls_id} {pb['cx']:.6f} {pb['cy']:.6f} {pb['ww']:.6f} {pb['hh']:.6f}")
        type_counter[p['type']] += 1

    # 保存
    import shutil
    img_dst = output_dir / 'images' / f'{name}.png'
    lbl_dst = output_dir / 'labels' / f'{name}.txt'

    shutil.copy2(img_path, img_dst)
    try:
        os.unlink(img_path)
    except:
        pass

    if label_lines:
        lbl_dst.write_text('\n'.join(label_lines) + '\n')

    return {
        'status': 'ok',
        'entities': len(line_prims),
        'labels': len(label_lines),
        'type_counter': dict(type_counter),
        'img_size': (img_w, img_h),
    }


def augment_one(dxf_path, output_dir):
    """处理单个 DXF 文件，生成 PNG + YOLO 标签"""
    from baa_engine.drawing_parser import DrawingParser
    from baa_engine.semantic_analyzer import SemanticAnalyzer

    dxf_path = Path(dxf_path)
    name = dxf_path.stem

    # 1. Parse
    dp = DrawingParser()
    try:
        result = dp.parse(str(dxf_path))
    except Exception as e:
        logger.warning(f'{name}: parse failed: {e}')
        return {'status': 'parse_fail', 'reason': str(e)[:80]}

    dims = result.dimensions

    # 2. Semantic analyze
    sa = SemanticAnalyzer()
    try:
        sem = sa.analyze(result.primitives, dims, building_type='civil')
    except Exception as e:
        logger.warning(f'{name}: semantic analyze failed: {e}')
        return {'status': 'semantic_fail', 'reason': str(e)[:80]}

    total_ent, type_counter = count_entities(sem)
    if total_ent == 0:
        return {'status': 'no_entities', 'reason': 'no entities found'}

    # 3. Pre-filter: count target entities with usable bbox BEFORE expensive render
    TARGET_TYPES = {'wall', 'door', 'window', 'stair', 'shaft', 'staircase', 'corridor'}
    usable_targets = [e for e in sem['entities'] if e.get('type', '') in TARGET_TYPES
                      and e.get('bbox')
                      and e['bbox'].get('width', 0) > 0
                      and e['bbox'].get('height', 0) > 0]
    # Estimate which would pass pixel filtering: need area > ~20x20 px
    # In world units: area > 100 (conservative for typical scales)
    usable_targets = [e for e in usable_targets if e['bbox']['width'] * e['bbox']['height'] > 100]
    if len(usable_targets) < MIN_LABELS:
        return {'status': 'low_labels', 'reason': f'{len(usable_targets)} usable target entities < {MIN_LABELS}'}

    # 4. Render (only after passing pre-filter)
    try:
        img_path = render_dxf_cropped(dxf_path)
    except Exception as e:
        logger.warning(f'{name}: render failed: {e}')
        return {'status': 'render_fail', 'reason': str(e)[:80]}

    if img_path is None:
        return {'status': 'render_none', 'reason': 'render returned None'}

    img_w, img_h = get_image_size(img_path)

    # 5. World bbox（仅几何 primitives，排除 text/dimension 噪声坐标）
    GEOM_TYPES = {'LINE', 'LWPOLYLINE', 'POLYLINE', 'CIRCLE', 'ARC'}
    pxs, pys = [], []
    for p in result.primitives:
        if p.dxf_type not in GEOM_TYPES:
            continue
        b = p.bbox
        if not b or (b.get('width', 0) <= 0 and b.get('height', 0) <= 0):
            continue
        pxs.extend([b['x'], b['x'] + b['width']])
        pys.extend([b['y'], b['y'] + b['height']])
    if not pxs:
        return {'status': 'no_bbox', 'reason': 'no geometry primitive bbox'}
    wb = {'x': min(pxs), 'y': min(pys), 'width': max(pxs) - min(pxs), 'height': max(pys) - min(pys)}

    # 6. Generate YOLO labels
    label_lines = []
    for e in sem['entities']:
        etype = e.get('type', '')
        if etype not in CLASH_MAP:
            continue
        cls_id = CLASH_MAP[etype]
        bbox = e.get('bbox')
        if not bbox:
            continue
        # 跳过零 bbox 实体
        if bbox.get('width', 0) <= 0 and bbox.get('height', 0) <= 0:
            continue
        pb = world_bbox_to_pixel(bbox, img_w, img_h, wb['x'], wb['y'], wb['width'], wb['height'])
        if pb is None:
            continue
        label_lines.append(f"{cls_id} {pb['cx']:.6f} {pb['cy']:.6f} {pb['ww']:.6f} {pb['hh']:.6f}")

    if not label_lines:
        try:
            os.unlink(img_path)
        except:
            pass
        return {'status': 'ok', 'entities': total_ent, 'labels': 0, 'type_counter': type_counter, 'img_size': (img_w, img_h)}

    # 7. Save image and labels
    img_dst = output_dir / 'images' / f'{name}.png'
    lbl_dst = output_dir / 'labels' / f'{name}.txt'

    import shutil
    shutil.copy2(img_path, img_dst)
    if label_lines:
        lbl_dst.write_text('\n'.join(label_lines) + '\n')

    # 8. Clean up temp render
    try:
        os.unlink(img_path)
    except:
        pass

    return {
        'status': 'ok',
        'entities': total_ent,
        'labels': len(label_lines),
        'type_counter': type_counter,
        'img_size': (img_w, img_h),
    }


def main():
    logger.info(f'Source: {SOURCE_DIR}')
    logger.info(f'BAA DXF: {BAA_DXF_DIR}')
    logger.info(f'Dataset: {DATASET_DIR}')

    # ── 收集 DXF 文件 ──
    dxf_files = []

    # 跳过非建筑目录（电气/暖通/结构/弱电等标注质量极低）
    SKIP_DIRS = {'电气', '暖通', '弱电', '给排水', '结构', '消防', '装修'}
    
    # BAA DXF 优先（真实建筑图，标注质量高）
    if BAA_DXF_DIR.exists():
        for p in sorted(BAA_DXF_DIR.glob('*.dxf')):
            if p.stat().st_size > 0:
                dxf_files.append(p)
        logger.info(f'BAA DXF: {len(dxf_files)}')

    # 测试图纸（只选建筑目录）
    if SOURCE_DIR.exists():
        for p in sorted(SOURCE_DIR.rglob('*.dxf')):
            if p.stat().st_size > 0:
                # 跳过非建筑子目录
                rel = p.relative_to(SOURCE_DIR)
                parts = rel.parts
                if len(parts) >= 2 and parts[1] in SKIP_DIRS:
                    continue
                if p not in dxf_files:
                    dxf_files.append(p)
        logger.info(f'Total with architectural test drawings: {len(dxf_files)}')

    # 限制数量
    dxf_files = dxf_files[:MAX_FILES]
    logger.info(f'Will process: {len(dxf_files)}')

    if not dxf_files:
        logger.error('No DXF files found')
        sys.exit(1)

    # ── 准备数据集目录 ──
    train_dir = DATASET_DIR / 'train'
    val_dir = DATASET_DIR / 'val'
    for subdir in ['images', 'labels']:
        (train_dir / subdir).mkdir(parents=True, exist_ok=True)
        (val_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 清除旧数据
    import shutil
    for f in (train_dir / 'images').glob('*'):
        f.unlink()
    for f in (train_dir / 'labels').glob('*'):
        f.unlink()
    for f in (val_dir / 'images').glob('*'):
        f.unlink()
    for f in (val_dir / 'labels').glob('*'):
        f.unlink()

    # ── 逐文件处理 ──
    results = []
    success_count = 0
    total_labels = 0

    for i, dxf in enumerate(dxf_files):
        t0 = time.time()

        # 80% train, 20% val
        if i % 5 == 0:
            output_dir = val_dir
        else:
            output_dir = train_dir

        # 优先用 v2（raw DXF LINE + 层名映射），回退 v1
        result = augment_one_v2(dxf, output_dir)
        if result['status'] in ('parse_fail', 'render_fail', 'render_none', 'no_bbox'):
            result = augment_one(dxf, output_dir)
        elapsed = time.time() - t0

        if result['status'] == 'ok':
            if result['labels'] < MIN_LABELS:
                # No usable labels after render → discard
                if i % 5 == 0:
                    (val_dir / 'images' / f'{dxf.name}.png').unlink(missing_ok=True)
                    (val_dir / 'labels' / f'{dxf.name}.txt').unlink(missing_ok=True)
                else:
                    (train_dir / 'images' / f'{dxf.name}.png').unlink(missing_ok=True)
                    (train_dir / 'labels' / f'{dxf.name}.txt').unlink(missing_ok=True)
                result['status'] = 'low_labels'
                logger.warning(f'  -> discarded: {result["labels"]} labels after render')
            else:
                success_count += 1
                total_labels += result['labels']
        logger.info(f'[{i+1}/{len(dxf_files)}] {dxf.name}: {result["status"]} '
                    f'({elapsed:.1f}s)' +
                    (f', {result["entities"]} entities, {result["labels"]} labels' if result['status'] == 'ok' else
                     f', {result.get("reason","")[:60]}'))
        results.append({'file': dxf.name, 'status': result['status'], **result})

    # ── 统计报告 ──
    print('\n' + '=' * 60)
    print(f'P84 Augmentation Report')
    print(f'{"=" * 60}')
    print(f'Total processed: {len(dxf_files)}')
    print(f'Success:         {success_count}')
    print(f'Failed:          {len(dxf_files) - success_count}')
    print(f'Total labels:    {total_labels}')
    print()

    # Status breakdown
    status_counter = Counter(r['status'] for r in results)
    print('Status breakdown:')
    for s, c in status_counter.most_common():
        print(f'  {s}: {c}')

    # Type breakdown
    print('\nEntity type distribution (success only):')
    all_types = Counter()
    for r in results:
        if r['status'] == 'ok':
            for t, c in r.get('type_counter', {}).items():
                all_types[t] += c
    for t, c in all_types.most_common(20):
        print(f'  {t}: {c}')

    # Data split
    train_imgs = len(list((train_dir / 'images').glob('*')))
    val_imgs = len(list((val_dir / 'images').glob('*')))
    print(f'\nTrain images: {train_imgs}')
    print(f'Val images:   {val_imgs}')

    # Save report
    report_path = DATASET_DIR / 'augment_report.json'
    with open(report_path, 'w') as f:
        json.dump({
            'total': len(dxf_files),
            'success': success_count,
            'labels': total_labels,
            'status_counter': dict(status_counter),
            'type_counter': dict(all_types),
            'train_images': train_imgs,
            'val_images': val_imgs,
        }, f, indent=2)
    print(f'\nReport: {report_path}')


if __name__ == '__main__':
    main()
