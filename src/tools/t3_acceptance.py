"""天正 T3 金标准 F1 验收工具（T-A3）。

对 src/tests/fixtures/t3_gold/*.json 三套人工审计金标准，比较两种管线：

- ``baseline``：现有图层/几何管线（剥离 T3 标记后的 SemanticAnalyzer 输出；
  墙为 WALL 图层原始双线图元），代表改造前行为；
- ``native``：门/窗取 ``parsers.t3_native`` 原生识别实例（DorLib 门、
  WINLIB/窗线簇）；柱/墙取**集成 analyze 输出**——带 T3 标记跑
  SemanticAnalyzer，柱为 ``_t3_native=column`` 覆盖实体、墙为
  ``_t3_wall_gid`` 合并实例（中心线+厚度），端到端验证生产链路。

点位构件（门/窗/柱）一对一最近邻贪心匹配（容差见 TOL_*），报告
precision/recall/F1；墙按中心线每 250mm 采样做覆盖率 F1（容差 200mm）。
同时输出未匹配实例（误报/漏报）作为逐类差距证据。

用法::

    python -m src.tools.t3_acceptance                 # 三图全跑（两模式）
    python -m src.tools.t3_acceptance --gold d1,d2    # 指定金标准
    python -m src.tools.t3_acceptance --json docs/t3_acceptance/t3_acceptance.json

图纸根目录取环境变量 BAA_TEST_DRAWING_ROOT，缺省 D:/BaiduNetdiskDownload/测试图纸。
"""

import argparse
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

from src.baa_engine.drawing_parser import DrawingParser, RawPrimitive
from src.baa_engine.parsers.t3_native import layer_tail
from src.baa_engine.semantic_analyzer.main import SemanticAnalyzer

GOLD_DIR = os.path.join("src", "tests", "fixtures", "t3_gold")
DEFAULT_ROOT = r"D:\BaiduNetdiskDownload\测试图纸"
WALL_SAMPLE_STEP = 250.0
WALL_TOL = 200.0

TOL = {"door": 600.0, "window": 800.0, "column": 350.0}
GATE_WALL_F1 = 0.80
GATE_OPENING_F1 = 0.75  # 门+窗合并 micro F1


# ── 匹配 ────────────────────────────────────────────────────


def match_points(gold: List[dict], pred: List[dict], tol: float) -> Tuple[List[dict], List[dict], List[dict]]:
    """一对一贪心最近邻；返回 (pairs, fp, fn)。"""
    pairs = []
    dists = []
    for gi, g in enumerate(gold):
        for pi, p in enumerate(pred):
            d = math.hypot(g["x"] - p["x"], g["y"] - p["y"])
            if d <= tol:
                dists.append((d, gi, pi))
    dists.sort()
    g_used, p_used = set(), set()
    for d, gi, pi in dists:
        if gi in g_used or pi in p_used:
            continue
        g_used.add(gi)
        p_used.add(pi)
        pairs.append({"gold": gold[gi], "pred": pred[pi], "dist": round(d, 1)})
    fp = [p for i, p in enumerate(pred) if i not in p_used]
    fn = [g for i, g in enumerate(gold) if i not in g_used]
    return pairs, fp, fn


def prf(n_gold: int, n_pred: int, n_tp: int) -> Dict[str, float]:
    precision = n_tp / n_pred if n_pred else 0.0
    recall = n_tp / n_gold if n_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "gold": n_gold,
        "pred": n_pred,
        "tp": n_tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _seg_samples(w: dict, step: float = WALL_SAMPLE_STEP) -> List[Tuple[float, float]]:
    out = []
    n = max(1, int(math.floor((w["end"] - w["start"]) / step)))
    for k in range(n + 1):
        t = k / n
        v = w["start"] + t * (w["end"] - w["start"])
        # h: pos=y 常量、start/end 为 x；v: pos=x 常量、start/end 为 y
        out.append((v, w["pos"]) if w["orientation"] == "h" else (w["pos"], v))
    return out


def _point_seg_dist(px, py, w) -> float:
    if w["orientation"] == "h":  # pos=y，start/end 为 x
        cx = min(max(px, w["start"]), w["end"])
        return math.hypot(px - cx, py - w["pos"])
    cy = min(max(py, w["start"]), w["end"])  # v: pos=x，start/end 为 y
    return math.hypot(px - w["pos"], py - cy)


def wall_metrics(gold_walls: List[dict], pred_walls: List[dict], tol: float = WALL_TOL) -> Dict:
    """双向采样覆盖率：金标准采样→预测（recall），预测采样→金标准（precision）。"""
    def _cover(src, dst):
        total = hit = 0
        miss_points = []
        for w in src:
            for px, py in _seg_samples(w):
                total += 1
                if all(_point_seg_dist(px, py, q) > tol for q in dst):
                    if len(miss_points) < 24:
                        miss_points.append([round(px, 1), round(py, 1)])
                else:
                    hit += 1
        return total, hit, miss_points

    g_total, g_hit, fn_points = _cover(gold_walls, pred_walls)
    p_total, p_hit, fp_points = _cover(pred_walls, gold_walls)
    recall = g_hit / g_total if g_total else 0.0
    precision = p_hit / p_total if p_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "gold_samples": g_total,
        "pred_samples": p_total,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fn_sample_points": fn_points,
        "fp_sample_points": fp_points,
    }


# ── 预测来源 ────────────────────────────────────────────────


def _in_box(x: float, y: float, box: List[float], pad: float = 300.0) -> bool:
    x0, y0, x1, y1 = box
    return x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad


def _clip_wall(w: dict, box: List[float]) -> Optional[dict]:
    x0, y0, x1, y1 = box
    ww = dict(w)
    if w["orientation"] == "h":
        if not (y0 <= w["pos"] <= y1):
            return None
        s, e = max(w["start"], x0), min(w["end"], x1)
    else:
        if not (x0 <= w["pos"] <= x1):
            return None
        s, e = max(w["start"], y0), min(w["end"], y1)
    if e - s < 300:
        return None
    ww["start"], ww["end"] = s, e
    return ww


def native_predictions(result, t3: dict, region_idx: int, box: List[float]) -> Dict[str, list]:
    """native 预测：门/窗取识别器实例；柱/墙取集成 analyze 输出（生产链路）。"""
    out = {"door": [], "window": [], "column": [], "wall": []}
    for d in t3.get("doors", []):
        if d.get("region") == region_idx and _in_box(d["x"], d["y"], box, pad=0):
            out["door"].append({"x": d["x"], "y": d["y"], "handle": d.get("handle")})
    for w in t3.get("windows", []):
        if w.get("region") == region_idx and _in_box(w["x"], w["y"], box, pad=0):
            out["window"].append({"x": w["x"], "y": w["y"], "source": w.get("source")})
    # 柱/墙：带 T3 标记跑完整 SemanticAnalyzer，验证 标记→分类覆盖 生产链路
    analyzed = SemanticAnalyzer().analyze(
        result.primitives, result.dimensions, block_refs=result.block_refs,
        max_entities=1000000,
    )
    for e in analyzed["entities"]:
        props = e.get("properties", {})
        bb = e["bbox"]
        if props.get("_t3_native") == "column":
            cx, cy = bb["x"] + bb["width"] / 2.0, bb["y"] + bb["height"] / 2.0
            if _in_box(cx, cy, box, pad=0):
                out["column"].append({"x": cx, "y": cy, "handle": props.get("handle", "")})
        seg = props.get("_t3_wall_seg")
        if seg and e.get("type") == "wall":
            ww = _clip_wall(seg, box)
            if ww:
                out["wall"].append(ww)
    return out


def baseline_predictions(result, box: List[float]) -> Dict[str, list]:
    """剥离 T3 标记后跑现有分类管线，得到改造前点位预测。"""
    stripped = []
    for q in result.primitives:
        props = {k: v for k, v in q.properties.items() if not str(k).startswith("_t3")}
        stripped.append(RawPrimitive(q.dxf_type, q.layer, q.handle, q.bbox, props))
    out = SemanticAnalyzer().analyze(
        stripped, result.dimensions, block_refs=result.block_refs, max_entities=1000000
    )
    preds = {"door": [], "window": [], "column": []}
    for e in out["entities"]:
        etype = e.get("type") or e.get("entity_type")
        if etype not in preds:
            continue
        bb = e["bbox"]
        cx, cy = bb["x"] + bb["width"] / 2.0, bb["y"] + bb["height"] / 2.0
        if _in_box(cx, cy, box, pad=300):
            preds[etype].append({"x": cx, "y": cy, "layer": e.get("layer", "")})
    # 墙：WALL 图层原始双线（旧管线按图层把每根线分为 wall）
    walls = []
    for q in result.primitives:
        if layer_tail(q.layer) != "WALL":
            continue
        bb = q.bbox
        cx, cy = bb["x"] + bb["width"] / 2.0, bb["y"] + bb["height"] / 2.0
        if not _in_box(cx, cy, box, pad=300):
            continue
        if q.dxf_type == "LINE" and (bb["width"] < 1.0 or bb["height"] < 1.0):
            if bb["width"] >= bb["height"]:
                ww = {"orientation": "h", "pos": cy,
                      "start": max(bb["x"], box[0]), "end": min(bb["x"] + bb["width"], box[2])}
            else:
                ww = {"orientation": "v", "pos": cx,
                      "start": max(bb["y"], box[1]), "end": min(bb["y"] + bb["height"], box[3])}
            if ww["end"] - ww["start"] >= 300:
                walls.append(ww)
    preds["wall"] = walls
    return preds


# ── 主流程 ──────────────────────────────────────────────────


def evaluate(gold_path: str, drawing_root: str, modes: Tuple[str, ...]) -> Dict:
    gold = json.load(open(gold_path, encoding="utf-8"))
    drawing = os.path.join(drawing_root, gold["drawing"])
    box = gold["audit_box"]
    region_idx = gold.get("region_index", 0)
    result = DrawingParser().parse(drawing)
    if result.error:
        raise RuntimeError(f"{gold['id']} 解析失败: {result.error}")

    gold_sets = {
        "door": [{"x": float(d["x"]), "y": float(d["y"])} for d in gold["doors"]],
        "window": [{"x": float(d["x"]), "y": float(d["y"])} for d in gold["windows"]],
        "column": [{"x": float(d["x"]), "y": float(d["y"])} for d in gold["columns"]],
        "wall": gold["walls"],
    }
    report = {"id": gold["id"], "drawing": gold["drawing"], "audit_box": box,
              "parse_status": result.parse_status, "modes": {}}

    preds_by_mode = {}
    if "native" in modes:
        preds_by_mode["native"] = native_predictions(result, result.t3_components, region_idx, box)
    if "baseline" in modes:
        preds_by_mode["baseline"] = baseline_predictions(result, box)

    for mode, preds in preds_by_mode.items():
        mode_report = {}
        for cls in ("door", "window", "column"):
            pairs, fp, fn = match_points(gold_sets[cls], preds[cls], TOL[cls])
            mode_report[cls] = {
                **prf(len(gold_sets[cls]), len(preds[cls]), len(pairs)),
                "false_positives": [{"x": round(p["x"], 1), "y": round(p["y"], 1),
                                     "layer": p.get("layer", ""), "source": p.get("source", "")}
                                    for p in fp],
                "false_negatives": [{"x": round(g["x"], 1), "y": round(g["y"], 1)} for g in fn],
            }
        mode_report["wall"] = wall_metrics(gold_sets["wall"], preds["wall"])
        # 门+窗合并 micro F1（验收门槛口径）
        otp = mode_report["door"]["tp"] + mode_report["window"]["tp"]
        ogold = mode_report["door"]["gold"] + mode_report["window"]["gold"]
        opred = mode_report["door"]["pred"] + mode_report["window"]["pred"]
        mode_report["opening_micro"] = prf(ogold, opred, otp)
        report["modes"][mode] = mode_report
    return report


def aggregate(reports: List[dict]) -> Dict[str, Dict[str, float]]:
    agg = {}
    for mode in ("baseline", "native"):
        if not any(mode in r["modes"] for r in reports):
            continue
        agg[mode] = {}
        for cls in ("door", "window", "column"):
            g = sum(r["modes"][mode][cls]["gold"] for r in reports if mode in r["modes"])
            p = sum(r["modes"][mode][cls]["pred"] for r in reports if mode in r["modes"])
            tp = sum(r["modes"][mode][cls]["tp"] for r in reports if mode in r["modes"])
            agg[mode][cls] = prf(g, p, tp)
        og = sum(r["modes"][mode]["opening_micro"]["gold"] for r in reports if mode in r["modes"])
        op = sum(r["modes"][mode]["opening_micro"]["pred"] for r in reports if mode in r["modes"])
        ot = sum(r["modes"][mode]["opening_micro"]["tp"] for r in reports if mode in r["modes"])
        agg[mode]["opening_micro"] = prf(og, op, ot)
        # 墙采样汇总
        gs = sum(r["modes"][mode]["wall"]["gold_samples"] for r in reports if mode in r["modes"])
        ps = sum(r["modes"][mode]["wall"]["pred_samples"] for r in reports if mode in r["modes"])
        gh = round(sum(
            r["modes"][mode]["wall"]["recall"] * r["modes"][mode]["wall"]["gold_samples"]
            for r in reports if mode in r["modes"]))
        ph = round(sum(
            r["modes"][mode]["wall"]["precision"] * r["modes"][mode]["wall"]["pred_samples"]
            for r in reports if mode in r["modes"]))
        agg[mode]["wall"] = prf(gs, ps, 0)  # placeholder, replaced below
        recall = gh / gs if gs else 0.0
        precision = ph / ps if ps else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        agg[mode]["wall"] = {"gold_samples": gs, "pred_samples": ps,
                             "precision": round(precision, 4), "recall": round(recall, 4),
                             "f1": round(f1, 4)}
    return agg


def main(argv=None):
    ap = argparse.ArgumentParser(description="T-A3 天正 T3 金标准 F1 验收")
    ap.add_argument("--gold", default="d1,d2,d3", help="逗号分隔金标准 id")
    ap.add_argument("--root", default=os.environ.get("BAA_TEST_DRAWING_ROOT", DEFAULT_ROOT))
    ap.add_argument("--modes", default="baseline,native")
    ap.add_argument("--json", default="docs/t3_acceptance/t3_acceptance.json")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"[skip] 真实图纸根目录不存在: {args.root}（设置 BAA_TEST_DRAWING_ROOT）")
        return 3

    modes = tuple(m.strip() for m in args.modes.split(",") if m.strip())
    reports = []
    for gid in [s.strip() for s in args.gold.split(",") if s.strip()]:
        gold_path = os.path.join(GOLD_DIR, f"{gid}.json")
        rep = evaluate(gold_path, args.root, modes)
        reports.append(rep)

    summary = aggregate(reports)
    out = {"tolerance": TOL, "wall": {"sample_step_mm": WALL_SAMPLE_STEP, "tol_mm": WALL_TOL},
           "gates": {"wall_f1>=": GATE_WALL_F1, "opening_micro_f1>=": GATE_OPENING_F1},
           "aggregate": summary, "drawings": reports}

    os.makedirs(os.path.dirname(args.json), exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    for mode, agg in summary.items():
        print(f"[{mode}] wall F1={agg['wall']['f1']}  door F1={agg['door']['f1']} "
              f"window F1={agg['window']['f1']} opening-micro F1={agg['opening_micro']['f1']} "
              f"column F1={agg['column']['f1']}")
    if "native" in summary:
        nat = summary["native"]
        ok = nat["wall"]["f1"] >= GATE_WALL_F1 and nat["opening_micro"]["f1"] >= GATE_OPENING_F1
        print("ACCEPT" if ok else "BELOW_GATE")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
