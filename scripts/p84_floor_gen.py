"""P84: DXF → YOLO floor annotations.
Steps: DXF read → Y-gap floor split → per floor SemanticAnalyzer → render + YOLO labels.
"""
import os, sys, uuid, glob, json
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw
import ezdxf

sys.path.insert(0, "/mnt/d/OpenClawData3workspace/Projects/BAA")
sys.path.insert(0, "/mnt/d/OpenClawData3workspace/Projects/BAA/src")
from baa_engine.drawing_parser import RawPrimitive
from baa_engine.semantic_analyzer.main import SemanticAnalyzer

GAP_THRESH = 2000.0
MAX_ENTITIES = 30000


def is_coord(v):
    """Accept tuple/list or Vec3-like (ezdxf.acc.vector.Vec3)."""
    if isinstance(v, (tuple, list)):
        return len(v) >= 2
    if hasattr(v, '__len__') and hasattr(v, '__iter__'):
        return len(v) >= 2
    return False


def to_point(v):
    """Convert a coord to (x, y, z) floats."""
    try:
        return (float(v[0]), float(v[1]), float(v[2]) if len(v) > 2 else 0.0)
    except Exception:
        return (0.0, 0.0, 0.0)

LABEL2CLASS = {
    "wall": 0, "door": 1, "window": 2, "stair": 3, "corridor": 4,
    "fire_door": 5, "exit": 6, "fire_lane": 7, "fire_zone": 8,
    "fire_window": 9, "shaft": 10, "room": 11, "exit_sign": 12,
    "sprinkler_system": 13, "fire_alarm": 14, "insulation": 15,
    "evacuation_lighting": 16, "refuge_floor": 17,
}

FOCUS = {"wall", "door", "window", "stair", "fire_door", "exit", "room", "corridor"}

OUT_DIR = Path("/mnt/d/OpenClawData3workspace/Projects/BAA/data/p84_floor_data")
IMG_DIR = OUT_DIR / "images"
TXT_DIR = OUT_DIR / "labels"
for d in [IMG_DIR, TXT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def get_dxf_attrs(e):
    """Safely extract geometric attributes from a DXF entity.
    Returns (points, extra_props)."""
    points = []
    props = {}
    dxf = e.dxf
    for attr in ("start", "end", "location", "center", "insert",
                 "insertion_point", "vertex"):
        if hasattr(dxf, attr):
            v = getattr(dxf, attr, None)
            if v and is_coord(v):
                points.append(to_point(v))
                props[attr] = v
    # control_points (for ARC, SPLINE, LWPOLYLINE vertexes)
    try:
        cp = dxf.control_points
        if cp:
            for p in cp:
                if is_coord(p):
                    points.append(to_point(p))
                props["control_points"] = cp
    except Exception:
        pass
    # vertexes (for POLYLINE)
    try:
        vs = dxf.vertexes
        if vs:
            for vv in vs:
                try:
                    p = vv.dxf.location
                    if is_coord(p):
                        points.append(to_point(p))
                except Exception:
                    pass
            props["vertexes"] = vs
    except Exception:
        pass
    try:
        v = dxf.text
        if v:
            props["text"] = str(v)
    except Exception:
        pass
    try:
        v = dxf.value
        if v:
            props["text"] = str(v)
    except Exception:
        pass
    for attr in ("radius", "height", "width"):
        try:
            v = getattr(dxf, attr, None)
            if v:
                props[attr] = float(v)
        except Exception:
            pass
    try:
        v = dxf.name
        if v:
            props["block_name"] = str(v)
    except Exception:
        pass
    return points, props


def collect_primitives(entities):
    primitives = []
    for e in entities[:MAX_ENTITIES]:
        try:
            points, props = get_dxf_attrs(e)
            if not points:
                continue
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            bbox = {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
            primitives.append(RawPrimitive(
                dxf_type=str(e.dxftype()),
                layer=str(e.dxf.layer) if e.dxf.layer else "",
                handle=uuid.uuid4().hex[:8],
                bbox=bbox,
                properties=props,
            ))
        except Exception:
            continue
    return primitives


def detect_floors(entities):
    ys = []
    for e in entities[:MAX_ENTITIES]:
        points, _ = get_dxf_attrs(e)
        for p in points:
            ys.append(p[1])
    if not ys:
        return None
    ys_sorted = sorted(set(ys))
    if len(ys_sorted) < 10:
        return [(min(ys_sorted), max(ys_sorted))]
    gaps = [(ys_sorted[i], ys_sorted[i + 1])
            for i in range(len(ys_sorted) - 1)
            if ys_sorted[i + 1] - ys_sorted[i] > GAP_THRESH]
    if not gaps:
        return [(min(ys_sorted), max(ys_sorted))]
    boundaries = [min(ys_sorted)] + [g[1] for g in gaps] + [max(ys_sorted)]
    floor_ranges = [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]
    floor_ranges = [f for f in floor_ranges if f[1] - f[0] > 500]
    if not floor_ranges:
        return [(min(ys_sorted), max(ys_sorted))]
    floor_ranges = sorted(floor_ranges, key=lambda f: f[1] - f[0], reverse=True)[:5]
    return sorted(floor_ranges)


def entities_in_range(entities, y0, y1, margin=1000):
    result = []
    for e in entities:
        points, _ = get_dxf_attrs(e)
        if not points:
            continue
        cy = sum(p[1] for p in points) / len(points)
        if y0 - margin <= cy <= y1 + margin:
            result.append(e)
    return result


def process_floor(fp, fi, y0, y1):
    doc = ezdxf.readfile(fp)
    entities = list(doc.modelspace())
    ents_in = entities_in_range(entities, y0, y1)
    if len(ents_in) < 20:
        return None

    # Get image bounds
    all_pts = []
    for e in ents_in:
        pts, _ = get_dxf_attrs(e)
        all_pts.extend(pts)
    if not all_pts:
        return None
    x0 = min(p[0] for p in all_pts)
    x1 = max(p[0] for p in all_pts)
    y0_ = min(p[1] for p in all_pts)
    y1_ = max(p[1] for p in all_pts)
    pad = max(200, (x1 - x0) * 0.1, (y1_ - y0_) * 0.1)
    x0 -= pad
    x1 += pad
    y0_ -= pad
    y1_ += pad

    primitives = collect_primitives(ents_in)
    if len(primitives) < 10:
        return None

    analyzer = SemanticAnalyzer()
    try:
        entities_out = analyzer._classify_entities(primitives)
    except Exception as ex:
        print(f"      classify error: {ex}")
        return None

    # Filter YOLO-able
    yolo_entities = [
        e for e in entities_out
        if e.type in LABEL2CLASS and e.bbox
        and (e.bbox.get("width", 0) > 0 or e.bbox.get("height", 0) > 0)
    ]
    if not yolo_entities:
        return None

    img_w_target = min(4096, max(100, int(x1 - x0)))
    img_h_target = min(4096, max(100, int(y1_ - y0_)))
    # Coordinate range (may be much larger than image; used for YOLO scaling)
    x0 = float(x0)
    x1 = float(x1)
    y0_ = float(y0_)
    y1_ = float(y1_)
    img_w = img_w_target
    img_h = img_h_target
    img = Image.new("RGB", (img_w, img_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for e in yolo_entities:
        bbox = e.bbox
        try:
            # Map world coords into target pixel space
            px0 = max(0, int((bbox["x"] - x0) / (x1 - x0) * img_w))
            py0 = max(0, int((bbox["y"] - y0_) / (y1_ - y0_) * img_h))
            px1 = min(img_w, int((bbox["x"] + bbox["width"] - x0) / (x1 - x0) * img_w))
            py1 = min(img_h, int((bbox["y"] + bbox["height"] - y0_) / (y1_ - y0_) * img_h))
            if px1 > px0 and py1 > py0:
                draw.rectangle([px0, py0, px1, py1], outline=(0, 0, 255), width=1)
        except Exception:
            pass

    # YOLO labels: YOLO expects normalized bbox in [0,1] of the rendered image.
    lines = []
    for e in yolo_entities:
        cls = LABEL2CLASS[e.type]
        bbox = e.bbox
        w_, h_ = bbox["width"], bbox["height"]
        if w_ <= 0 or h_ <= 0:
            continue
        xc = bbox["x"] + w_ / 2
        yc = bbox["y"] + h_ / 2
        cx_rel = (xc - x0) / (x1 - x0)
        cy_rel = (yc - y0_) / (y1_ - y0_)
        w_rel = w_ / (x1 - x0)
        h_rel = h_ / (y1_ - y0_)
        if not (0 <= cx_rel <= 1 and 0 <= cy_rel <= 1 and w_rel > 0 and h_rel > 0):
            continue
        lines.append(f"{cls} {cx_rel:.6f} {cy_rel:.6f} {w_rel:.6f} {h_rel:.6f}")

    if not lines:
        return None

    stem = Path(fp).stem
    img_path = IMG_DIR / f"{stem}_floor{fi}.png"
    txt_path = TXT_DIR / f"{stem}_floor{fi}.txt"
    img.save(img_path)
    with open(txt_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    return {
        "img": str(img_path),
        "labels": len(lines),
        "focus": sum(1 for e in yolo_entities if e.type in FOCUS),
        "total": len(entities_out),
        "types": dict(Counter(e.type for e in entities_out).most_common(10)),
        "size": f"{img_w}x{img_h}",
    }


def find_floor_plans():
    candidates = glob.glob(
        "/mnt/d/OpenClawData3workspace/Projects/BAA/data/图纸/**/*.dxf", recursive=True
    )
    skip_kw = [
        "系统图", "拓扑图", "配电系统", "原理图", "供电系统", "平均照度",
        "设计说明", "目录", "智能照明系统", "UPS", "母线", "变压器",
        "动照", "接地", "动环", "安防", "自控", "暖通", "通风",
        "给排水", "气灭", "气体灭火", "火灾", "报警", "应急广播", "极早期",
        "消防", "总图", "室外", "配电", "照明", "电源", "通信工艺", "电照",
        "电气", "油机", "气动", "空调",
    ]
    keep = []
    for c in candidates:
        if os.path.getsize(c) > 50_000_000:
            continue
        if any(kw in c for kw in skip_kw):
            continue
        keep.append(c)
    return sorted(keep)


def main():
    files = find_floor_plans()
    print(f"Files to process: {len(files)}")
    grand = 0
    for fp in files:
        fname = os.path.relpath(fp, "/mnt/d/OpenClawData3workspace/Projects/BAA")
        print(f"\n{fname}", flush=True)
        try:
            floors = detect_floors(list(ezdxf.readfile(fp).modelspace()))
        except Exception as e:
            print(f"  read error: {e}"); continue
        if not floors:
            print(f"  no floors detected")
            continue
        print(f"  {len(floors)} floors")
        for fi, (y0, y1) in enumerate(floors):
            try:
                r = process_floor(fp, fi, y0, y1)
                if r:
                    print(f"    F{fi}: {r['labels']} labels, {r['focus']} focus, types={r['types']}")
                    grand += r["labels"]
                else:
                    print(f"    F{fi}: empty")
            except Exception as e:
                import traceback; traceback.print_exc()
    img_n = len(list(IMG_DIR.glob("*.png")))
    txt_n = len(list(TXT_DIR.glob("*.txt")))
    print(f"\n=== DONE ===\nTotal labels: {grand}\nImages: {img_n}, Labels: {txt_n}\nOut: {OUT_DIR}")


if __name__ == "__main__":
    main()
