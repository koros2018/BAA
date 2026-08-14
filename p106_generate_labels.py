"""P106 YOLO 训练伪标签管线 v2 — 修复超时逻辑 + 单进程稳定运行。"""

import argparse
import os
import sys
import json
import time
import signal
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError()


# ── 18 类 YOLO 类别定义 ──
YOLO_CLASSES = [
    "wall", "door", "window", "staircase", "corridor", "fire_door",
    "exit", "fire_lane", "fire_zone", "fire_window", "shaft", "room",
    "exit_sign", "sprinkler_system", "fire_alarm", "insulation",
    "evacuation_lighting", "refuge_floor",
]
CLSID = {name: i for i, name in enumerate(YOLO_CLASSES)}

ENTITY_TO_YOLO = {
    "room": "room", "corridor": "corridor", "door": "door", "window": "window",
    "stair": "staircase", "staircase": "staircase", "fire_door": "fire_door",
    "fire_curtain": "fire_door", "exit": "exit", "exit_door": "exit",
    "fire_window": "fire_window", "rescue_window": "fire_window",
    "shaft": "shaft", "fire_zone": "fire_zone", "fire_lane": "fire_lane",
    "wall": "wall", "doorway": "door",
}
EXCLUDE_TYPES = {
    "dimension", "text", "other", "column", "pillar", "facade",
    "road", "floor", "parking_space", "water_pipe", "handrail",
    "antechamber", "elevator", "elevator_lobby", "entrance_hall",
    "anteroom", "lobby", "pump_room", "space", "staircase_lobby",
    "outdoor_area", "titleblock", "vegetation", "opening",
    "cable", "conduit", "wiring", "duct", "pipe", "equipment",
    "electrical", "grounding", "drain", "block", "footing",
}


def render_dxf_to_png(dxf_path, out_png, dpi=100):
    import ezdxf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
    except Exception:
        return None

    all_x, all_y = [], []
    for entity in msp:
        try:
            if entity.dxftype() == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                all_x.extend([s[0], e[0]])
                all_y.extend([s[1], e[1]])
            elif entity.dxftype() == "LWPOLYLINE":
                for v in entity.get_points():
                    all_x.append(v[0])
                    all_y.append(v[1])
            elif entity.dxftype() == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                all_x.extend([cx - r, cx + r])
                all_y.extend([cy - r, cy + r])
        except Exception:
            continue
    if not all_x:
        return None

    x_min, x_max = min(all_x) - 2, max(all_x) + 2
    y_min, y_max = min(all_y) - 2, max(all_y) + 2

    fig_w = max(x_max - x_min, 1) * 0.4
    fig_h = max(y_max - y_min, 1) * 0.4
    max_px = 512
    if fig_w * dpi > max_px or fig_h * dpi > max_px:
        scale = min(max_px / (fig_w * dpi), max_px / (fig_h * dpi))
        fig_w *= scale
        fig_h *= scale

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    for entity in msp:
        layer = getattr(entity.dxf, "layer", "")
        if layer and layer.upper() == "META":
            continue
        dt = entity.dxftype()
        try:
            if dt == "LINE":
                s, e = entity.dxf.start, entity.dxf.end
                ax.plot([s[0], e[0]], [s[1], e[1]], "k-", linewidth=0.3)
            elif dt == "LWPOLYLINE":
                pts = [(v[0], v[1]) for v in entity.get_points()]
                if pts:
                    xs, ys = zip(*pts)
                    ax.plot(xs, ys, "k-", linewidth=0.3)
            elif dt == "CIRCLE":
                cx, cy = entity.dxf.center[:2]
                r = entity.dxf.radius
                ax.add_patch(plt.Circle((cx, cy), r, fill=False, color="k", linewidth=0.3))
        except Exception:
            continue

    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)

    return {"world_x": x_min, "world_y": y_min,
            "world_w": x_max - x_min, "world_h": y_max - y_min,
            "img_w": int(fig_w * dpi), "img_h": int(fig_h * dpi)}


def world_to_yolo(bbox, params):
    x, y = bbox.get("x", 0), bbox.get("y", 0)
    w, h = bbox.get("width", 0), bbox.get("height", 0)
    if w <= 0 or h <= 0:
        return None
    px = (x - params["world_x"]) / params["world_w"]
    py = (y - params["world_y"]) / params["world_h"]
    pw, ph = w / params["world_w"], h / params["world_h"]
    if pw < 0.001 or ph < 0.001:
        return None
    xc, yc = px + pw / 2, py + ph / 2
    if not (0 <= xc <= 1 and 0 <= yc <= 1):
        return None
    return (xc, yc, pw, ph)


def process_one(dxf_path, out_dir, PER_FILE_TIMEOUT=30.0):
    """处理单个 DXF，超时返回 None。"""
    import signal as _signal
    from src.baa_engine.drawing_parser import DrawingParser
    from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

    old_handler = _signal.signal(_signal.SIGALRM, _timeout_handler)
    _signal.alarm(int(PER_FILE_TIMEOUT))
    try:
        return _process_inner(dxf_path, out_dir)
    except TimeoutError:
        return None
    except Exception:
        return None
    finally:
        _signal.alarm(0)
        _signal.signal(_signal.SIGALRM, old_handler)


def _process_inner(dxf_path, out_dir):
    fname = os.path.basename(dxf_path).replace(".dxf", "")
    lbl_dir = os.path.join(out_dir, "labels")
    txt_path = os.path.join(lbl_dir, f"{fname}.txt")
    if os.path.exists(txt_path):
        return "skip"

    img_dir = os.path.join(out_dir, "images")
    png_path = os.path.join(img_dir, f"{fname}.png")
    params = render_dxf_to_png(dxf_path, png_path)
    if params is None:
        return "fail"

    dp = DrawingParser()
    result = dp.parse(dxf_path, file_id=fname)
    sa = SemanticAnalyzer()
    primitives = result.primitives
    entities = sa._classify_entities(primitives)
    sweep = sa._sweep_line_detect_rooms(primitives)
    seen = {}
    for e in entities + sweep:
        seen[e.id] = e

    labels = []
    type_counts = Counter()
    for eid, ent in seen.items():
        etype = ent.type
        if etype in EXCLUDE_TYPES or etype not in ENTITY_TO_YOLO:
            continue
        yolo_cls = ENTITY_TO_YOLO[etype]
        if yolo_cls not in CLSID:
            continue
        yolo = world_to_yolo(ent.bbox, params)
        if yolo is None:
            continue
        labels.append((CLSID[yolo_cls], *yolo))
        type_counts[yolo_cls] += 1

    if not labels:
        return "no_labels"

    labels.sort(key=lambda l: l[0])
    with open(txt_path, "w") as f:
        for cls_id, xc, yc, w, h in labels:
            f.write(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

    return ("ok", type_counts, len(labels), fname)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/p106_yolo_dataset")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--time-budget", type=float, default=7200.0)
    args = ap.parse_args()

    TARGET_DIR = "/mnt/d/BaiduNetdiskDownload/测试图纸"
    all_dxf = []
    for dirpath, _, filenames in os.walk(TARGET_DIR):
        for fname in filenames:
            if fname.lower().endswith(".dxf"):
                all_dxf.append(os.path.join(dirpath, fname))
    all_dxf.sort()

    if args.limit:
        all_dxf = all_dxf[:args.limit]

    print(f"[P106] 扫描到 {len(all_dxf)} 个 DXF 文件", flush=True)

    os.makedirs(args.out, exist_ok=True)
    img_dir = os.path.join(args.out, "images")
    lbl_dir = os.path.join(args.out, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)

    start_time = time.time()
    agg_classes = Counter()
    stats = {"ok": 0, "fail": 0, "no_labels": 0, "skip": 0, "timeout": 0}

    for i, dxf_path in enumerate(all_dxf):
        if time.time() - start_time > args.time_budget:
            print(f"[P106] 时间预算 {args.time_budget}s 用尽，已处理 {i}/{len(all_dxf)}", flush=True)
            break

        result = process_one(dxf_path, args.out)
        if result is None:
            stats["timeout"] += 1
            print(f"[P106] TIMEOUT: {os.path.basename(dxf_path)}", flush=True)
        elif result == "skip":
            stats["skip"] += 1
        elif result == "fail":
            stats["fail"] += 1
            print(f"[P106] FAIL render: {os.path.basename(dxf_path)}", flush=True)
        elif result == "no_labels":
            stats["no_labels"] += 1
        elif result[0] == "ok":
            _, type_counts, nlabels, fname = result
            for k, v in type_counts.items():
                agg_classes[k] += v
            stats["ok"] += 1
            if i % 5 == 0:
                print(f"[P106] OK: {fname} ({nlabels} labels)", flush=True)

    elapsed = time.time() - start_time
    print(f"\n[P106] 结果: {stats['ok']} OK / {stats['fail']} FAIL / {stats['no_labels']} 无标签 / {stats['timeout']} 超时 / {stats['skip']} 跳过 / {elapsed:.0f}s", flush=True)
    print("[P106] 类别分布:", flush=True)
    for cls_name in YOLO_CLASSES:
        c = agg_classes.get(cls_name, 0)
        if c > 0:
            print(f"  {cls_name:25s} {c:5d}", flush=True)

    yaml_content = f"train: {img_dir}\nval: {img_dir}\nnc: {len(YOLO_CLASSES)}\nnames: " + json.dumps(YOLO_CLASSES, ensure_ascii=False) + "\n"
    with open(os.path.join(args.out, "data.yaml"), "w") as f:
        f.write(yaml_content)
    print(f"[P106] data.yaml 已写入 {args.out}/data.yaml", flush=True)

    import random
    random.seed(42)
    img_files = sorted(f for f in os.listdir(img_dir) if f.endswith(".png"))
    random.shuffle(img_files)
    split = int(len(img_files) * 0.8)
    train_files, val_files = img_files[:split], img_files[split:]
    with open(os.path.join(args.out, "train.txt"), "w") as f:
        for fn in train_files:
            f.write(os.path.join(args.out, "images", fn) + "\n")
    with open(os.path.join(args.out, "val.txt"), "w") as f:
        for fn in val_files:
            f.write(os.path.join(args.out, "images", fn) + "\n")
    print(f"[P106] split: {len(train_files)} train / {len(val_files)} val", flush=True)

    stats["agg_classes"] = dict(agg_classes.most_common())
    with open(os.path.join(args.out, "stats.json"), "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()