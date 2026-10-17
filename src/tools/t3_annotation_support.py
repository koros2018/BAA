"""天正 T3 标注辅助工具（T-A3）。

用途：对真实 T3 DXF 运行生产识别器 ``parsers.t3_native``，在指定平面区域
（或自动选定的平面视图）上渲染带编号的审计图，并导出候选构件 JSON，供人工
核对后金标准落库（AutoLISP/pywin32 自动化 + 手动兜底流程中的"自动提候选"环节）。

用法::

    python -m src.tools.t3_annotation_support --drawing X.dxf --name d1 --out-dir docs/t3_acceptance/audit
    python -m src.tools.t3_annotation_support --drawing X.dxf --name d3 --region-index 0 \
        --crop 7030000,1357000,7065000,1372000 --out-dir docs/t3_acceptance/audit

输出：``{name}_audit.png``（人工核对）与 ``{name}_candidates.json``。
注意：候选 JSON 必须经人工对照审计图逐类核对后方可作为金标准。
"""

import argparse
import json
import os
import sys

import ezdxf

from src.baa_engine.parsers.t3_native import (
    DOOR_BLOCK_PREFIX,
    WINDOW_BLOCK_PREFIX,
    _segments_of,
    extract_t3,
    layer_tail,
)

RENDER_LAYERS = ("WALL", "WINDOW", "COLUMN", "AXIS")


def _setup_font():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        try:
            font_manager.fontManager.addfont(path)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=path).get_name()
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _filter_wall(w: dict, box, region_idx) -> bool:
    x0, y0, x1, y1 = box
    if w.get("region") != region_idx:
        return False
    if w["orientation"] == "h":
        return y0 <= w["pos"] <= y1 and not (w["end"] < x0 or w["start"] > x1)
    return x0 <= w["pos"] <= x1 and not (w["end"] < y0 or w["start"] > y1)


def render_audit(doc, t3, box, region_idx, out_png):
    plt = _setup_font()
    import matplotlib.pyplot as plt

    x0, y0, x1, y1 = box
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0

    def inside(x, y, pad=0.0):
        return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad

    doors = [d for d in t3["doors"] if inside(d["x"], d["y"])]
    wins = [w for w in t3["windows"] if inside(w["x"], w["y"])]
    cols = [c for c in t3["columns"] if inside(c["x"], c["y"])]
    walls = []
    for w in t3["walls"]:
        if not _filter_wall(w, box, region_idx):
            continue
        ww = dict(w)
        if w["orientation"] == "h":
            ww["start"] = max(w["start"], x0)
            ww["end"] = min(w["end"], x1)
        else:
            ww["start"] = max(w["start"], y0)
            ww["end"] = min(w["end"], y1)
        if ww["end"] - ww["start"] >= 300:
            walls.append(ww)

    span = max(x1 - x0, y1 - y0)
    fig, ax = plt.subplots(figsize=(18, 18 * (y1 - y0) / max(x1 - x0, 1e-6)))
    msp = doc.modelspace()
    for e in msp:
        t = e.dxftype()
        tail = layer_tail(getattr(e.dxf, "layer", ""))
        if t in ("LINE", "LWPOLYLINE", "POLYLINE"):
            if tail not in RENDER_LAYERS:
                continue
            color = {"WALL": "0.55", "WINDOW": "#1f77b4", "COLUMN": "#d62728", "AXIS": "#cccccc"}[tail]
            lw = 1.3 if tail == "WALL" else 0.8
            for sx1, sy1, sx2, sy2 in _segments_of(e):
                mx, my = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
                if not inside(mx, my, span * 0.02):
                    continue
                ax.plot([sx1, sx2], [sy1, sy2], color=color, lw=lw)
        elif t == "INSERT":
            p = e.dxf.insert
            if not inside(p.x, p.y, span * 0.01):
                continue
            bn = str(e.dxf.name or "").upper()
            if bn.startswith(DOOR_BLOCK_PREFIX):
                ax.plot(p.x, p.y, "x", color="#e377c2", ms=10, mew=2.2)
            elif bn.startswith(WINDOW_BLOCK_PREFIX):
                ax.plot(p.x, p.y, "s", mfc="none", mec="#2ca02c", ms=9, mew=1.6)
            elif tail == "COLUMN":
                ax.add_patch(
                    plt.Rectangle((p.x - 200, p.y - 200), 400, 400, fc="#d62728", ec="none", alpha=0.5)
                )

    for i, d in enumerate(doors):
        ax.annotate(f"D{i}", (d["x"], d["y"]), textcoords="offset points",
                    xytext=(7, 5), color="#c2185b", fontsize=11, weight="bold")
    for i, w in enumerate(wins):
        ax.annotate(f"W{i}", (w["x"], w["y"]), textcoords="offset points",
                    xytext=(7, -11), color="#2ca02c", fontsize=10)
    for i, c in enumerate(cols):
        ax.annotate(f"C{i}", (c["x"], c["y"]), textcoords="offset points",
                    xytext=(7, 5), color="#d62728", fontsize=10)
    for i, wl in enumerate(walls):
        if wl["orientation"] == "h":
            ax.annotate(str(i), ((wl["start"] + wl["end"]) / 2.0, wl["pos"]),
                        color="0.25", fontsize=7, ha="center", va="center")
        else:
            ax.annotate(str(i), (wl["pos"], (wl["start"] + wl["end"]) / 2.0),
                        color="0.25", fontsize=7, ha="center", va="center")

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.grid(True, color="#eeeeee", lw=0.5)
    ax.set_title(
        f"T3 audit region={region_idx} doors={len(doors)} windows={len(wins)} "
        f"columns={len(cols)} walls={len(walls)}"
    )
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    return {"doors": len(doors), "windows": len(wins), "columns": len(cols), "walls": len(walls)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="天正 T3 标注辅助：审计图 + 候选 JSON")
    ap.add_argument("--drawing", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--region-index", type=int, default=0, help="识别器平面区域序号")
    ap.add_argument("--crop", default=None, help="x0,y0,x1,y1；缺省用区域 bbox")
    args = ap.parse_args(argv)

    doc = ezdxf.readfile(args.drawing)
    t3 = extract_t3(doc)
    if not t3["regions"]:
        print(json.dumps(t3["status"], ensure_ascii=False, indent=2))
        print("未检测到平面区域", file=sys.stderr)
        return 2
    region = t3["regions"][args.region_index]
    box = tuple(float(v) for v in args.crop.split(",")) if args.crop else tuple(region["bbox"])

    os.makedirs(args.out_dir, exist_ok=True)
    png = os.path.join(args.out_dir, f"{args.name}_audit.png")
    stats = render_audit(doc, t3, box, args.region_index, png)

    x0, y0, x1, y1 = box
    candidates = {
        "drawing": os.path.abspath(args.drawing),
        "region_index": args.region_index,
        "region_bbox": list(region["bbox"]),
        "audit_box": list(box),
        "status": t3["status"],
        "counts": stats,
        "doors": [d for d in t3["doors"] if x0 <= d["x"] <= x1 and y0 <= d["y"] <= y1],
        "windows": [w for w in t3["windows"] if x0 <= w["x"] <= x1 and y0 <= w["y"] <= y1],
        "columns": [c for c in t3["columns"] if x0 <= c["x"] <= x1 and y0 <= c["y"] <= y1],
        "walls": [w for w in t3["walls"] if _filter_wall(w, box, args.region_index)],
    }
    json_path = os.path.join(args.out_dir, f"{args.name}_candidates.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=1)
    print(json.dumps({"png": png, "json": json_path, "counts": stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
