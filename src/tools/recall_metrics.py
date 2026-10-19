"""漏报率量化管线（Roadmap v4 T-B3 / 缺口 G12 收尾）。

对黄金标准标注集（src/tests/fixtures/t3_gold/*.json）运行语义分析，
逐类计算 FN/recall/precision/F1（复用 t3_acceptance.match_points/prf，
分母 = 黄金标准点数），并输出可复现 JSON 报表 + 历史追加记录。

漏报（false negative）口径：黄金标准中未被管线检出的标注点
（一对贪心最近邻匹配，容差 TOL 与 T3 验收一致）。

用法:
    python src/tools/recall_metrics.py --json out.json [--history docs/recall_metrics/history.jsonl]
    # CI gate: --gate-recall 0.75（低于基线即退出码 1，防回归不卡提升）
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser  # noqa: E402
from src.baa_engine.semantic_analyzer import SemanticAnalyzer  # noqa: E402
from src.tools.t3_acceptance import GOLD_DIR, TOL, match_points, prf  # noqa: E402

# 线元墙：采样覆盖式匹配（与 t3_acceptance 同口径）
from src.tools.t3_acceptance import wall_metrics  # noqa: E402

DRAWING_ROOT = os.environ.get("BAA_DRAWING_ROOT", r"D:\BaiduNetdiskDownload\测试图纸")


def _semantic_points(gold_path: str) -> dict:
    """当前语义分析管线对该图的逐类检出点（x/y + id）。"""
    gold = json.load(open(gold_path, encoding="utf-8"))
    drawing = os.path.join(DRAWING_ROOT, gold["drawing"])
    box = gold["audit_box"]
    region_idx = gold.get("region_index", 0)
    result = DrawingParser().parse(drawing)
    if result.error:
        raise RuntimeError(f"{gold.get('id', gold_path)} 解析失败: {result.error}")
    x0, y0, x1, y1 = box
    out = {"door": [], "window": [], "column": []}
    ents = SemanticAnalyzer().analyze(
        result.primitives, result.dimensions, block_refs=result.block_refs
    ).get("entities", [])
    for e in ents:
        et = e.get("type")
        if et not in out:
            continue
        b = e.get("bbox") or {}
        cx = (float(b.get("x", 0)) + float(b.get("width", 0)) / 2)
        cy = (float(b.get("y", 0)) + float(b.get("height", 0)) / 2)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            out[et].append({"x": cx, "y": cy, "id": e.get("id", "")})
    # 墙：T3 native 与 baseline 双源在 t3_acceptance 内实现，此处复用其
    # native_predictions（当前主干即 T3 native 覆盖式路径）
    from src.tools.t3_acceptance import native_predictions
    preds = native_predictions(result, result.t3_components, region_idx, box)
    out["wall"] = preds["wall"]
    return {"gold": gold, "preds": out}


def evaluate(gold_files, modes=("current",)) -> dict:
    files = [os.path.join(GOLD_DIR, f) for f in gold_files] if isinstance(gold_files, list) else None
    if files is None:
        files = sorted(
            str(p) for p in Path(GOLD_DIR).glob("*.json")
        )
    report = {"files": len(files), "per_drawing": [], "aggregate": {}}
    agg = {cls: {"gold": 0, "pred": 0, "tp": 0} for cls in ("door", "window", "column")}
    for fp in files:
        try:
            pack = _semantic_points(fp)
        except Exception as e:
            report["per_drawing"].append(
                {"file": Path(fp).name, "error": f"{type(e).__name__}: {e}"}
            )
            continue
        gold, preds = pack["gold"], pack["preds"]
        drep = {"id": gold.get("id"), "drawing": gold.get("drawing"), "types": {}}
        for cls in ("door", "window", "column"):
            gset = [{"x": float(d["x"]), "y": float(d["y"])} for d in gold.get(f"{cls}s", [])]
            pairs, fp_list, fn_list = match_points(gset, preds[cls], TOL[cls])
            m = prf(len(gset), len(preds[cls]), len(pairs))
            m["miss_rate"] = round(1 - m["recall"], 4) if m["gold"] else 0.0
            m["false_negatives"] = [{"x": round(g["x"], 1), "y": round(g["y"], 1)} for g in fn_list]
            drep["types"][cls] = m
            agg[cls]["gold"] += m["gold"]
            agg[cls]["pred"] += m["pred"]
            agg[cls]["tp"] += m["tp"]
        wg = gold.get("walls", [])
        if wg:
            drep["types"]["wall"] = wall_metrics(wg, preds["wall"])
        report["per_drawing"].append(drep)

    micro = {"gold": 0, "pred": 0, "tp": 0}
    for cls in ("door", "window", "column"):
        a = agg[cls]
        m = prf(a["gold"], a["pred"], a["tp"])
        m["miss_rate"] = round(1 - m["recall"], 4) if m["gold"] else 0.0
        report["aggregate"][cls] = m
        micro["gold"] += a["gold"]
        micro["pred"] += a["pred"]
        micro["tp"] += a["tp"]
    mm = prf(micro["gold"], micro["pred"], micro["tp"])
    mm["miss_rate"] = round(1 - mm["recall"], 4) if mm["gold"] else 0.0
    report["aggregate"]["opening_micro"] = mm
    report["aggregate"]["overall_gold"] = micro["gold"]
    report["aggregate"]["overall_miss"] = micro["gold"] - micro["tp"]
    return report


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(PROJECT_ROOT), text=True
        ).strip()
    except Exception:
        return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="漏报率量化管线（T-B3）")
    ap.add_argument("--json", default="", help="报表输出路径")
    ap.add_argument("--history", default="", help="历史 JSONL 追加路径（每行 timestamp+sha+aggregate）")
    ap.add_argument("--gate-recall", type=float, default=0.0,
                    help="CI 门槛：opening_micro recall 低于该值退出码 1（0=不启用）")
    args = ap.parse_args(argv)

    report = evaluate(None)
    report["tool"] = "src/tools/recall_metrics.py"
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    report["git_sha"] = _git_sha()

    micro = report["aggregate"]["opening_micro"]
    print(f"黄金标准 {report['files']} 张 | opening_micro recall={micro['recall']} "
          f"(gold={micro['gold']}, fn={micro['gold'] - micro['tp']}) miss_rate={micro['miss_rate']}")
    for cls in ("door", "window", "column", "wall"):
        m = report["aggregate"].get(cls) or {}
        if m:
            print(f"  {cls:8s} gold={m.get('gold', '-'):5} recall={m.get('recall', '-')}")

    rc = 0
    if args.gate_recall > 0 and micro["gold"] and micro["recall"] < args.gate_recall:
        print(f"GATE FAIL: recall {micro['recall']} < {args.gate_recall}")
        rc = 1

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"报表: {args.json}")
    if args.history:
        hp = Path(args.history)
        hp.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": report["generated_at"], "sha": report["git_sha"],
            "files": report["files"],
            "aggregate": {k: v for k, v in report["aggregate"].items()},
        }
        with open(hp, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"历史: {hp}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
