#!/usr/bin/env python3
"""
BAA 真实图纸 Baseline 验证脚本 (P81)

用途:
  - 对 6 张固定真实图纸逐张解析 + 语义分析 + 原子函数判定
  - 将实际 entity 分布与 ENTITY_BASELINE 对比，超出 ±30% 则告警
  - 将实际 EXIST 函数结果与 EXIST_EXPECTED 对比，不符则告警
  - 输出 JSON 报告（CI 和人工审阅均可消费）
  - 输出 exit code: 0=全绿, 1=有基线漂移, 2=代码错误

用法:
  python scripts/validate_real_drawings_baseline.py              # 仅打印
  python scripts/validate_real_drawings_baseline.py --json out.json  # 写 JSON 报告
  python scripts/validate_real_drawings_baseline.py --update-baseline  # 覆盖基准线（危险！需人工确认）
"""

import sys
import os
import json
import time
import argparse
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from baa_engine.drawing_parser import DrawingParser
from baa_engine.semantic_analyzer import SemanticAnalyzer
from baa_engine.atomic_functions import FuncRegistry

# ── 基准线版本 ─────────────────────────────────────────
BASELINE_VERSION = "2026-07-29 v2.5.25"
TOLERANCE = 0.30  # ±30%

# ── 6 张固定真实图纸 ──────────────────────────────────
# 只测 parser/semantic/atomic 改动时稳定性最高的 6 张
FIXED_DRAWINGS = [
    "A1云计算中心平面图0405_t3",
    "20210409-3#泵房_t3",
    "202109409-2#配电房_t3",
    "6.火灾自动报警 （报审）_t3",
    "9.气体灭火（唯美图框）_t3",
    "A1云计算中心_水消防2017.03.31_t3",
]

# ── ENTITY_BASELINE（与 test_real_drawings.py 同步）────
ENTITY_BASELINE = {
    "A1云计算中心平面图0405_t3.dxf": {
        "wall": 2414,
        "door": 2268,
        "window": 773,
        "stair": 402,
        "column": 302,
        "room": 41,  # P83: 几何兜底恢复door/window后闭合区域room增多（30→41）
        "dimension": 1285,
        "text": 1257,
        "other": 336,
        "parking_space": 17,
        "handrail": 4,
        "fire_door": 11,
        "fire_elevator": 1,
        "exit": 1,
        "antechamber": 3,
        "control_room": 2,
        "pump_room": 1,
    },
    "20210409-3#泵房_t3.dxf": {
        "wall": 344,
        "door": 2,
        "window": 29,
        "stair": 45,
        "column": 143,
        "room": 6,
        "dimension": 362,
        "text": 362,
        "other": 92,
        "equipment": 5,
        "fire_zone": 4,
        "fire_door": 2,
        "ramp": 1,
        "exit": 1,
        "structure": 11,
        "pump_room": 6,
        "water_reservoir": 2,
        "fire_pump": 2,
    },
    "202109409-2#配电房_t3.dxf": {
        "wall": 278,
        "door": 7,
        "window": 80,
        "stair": 100,
        "column": 88,
        "room": 2,
        "dimension": 369,
        "text": 328,
        "other": 50,
        "equipment": 23,
        "fire_zone": 4,
        "fire_door": 2,
        "ramp": 1,
        "exit": 1,
        "structure": 11,
    },
    "6.火灾自动报警 （报审）_t3.dxf": {
        "wall": 719,
        "door": 232,
        "window": 84,
        "stair": 1,
        "column": 37,
        "room": 12,
        "dimension": 941,
        "text": 467,
        "other": 229,
        "equipment": 4659,
        "fire_hydrant": 68,
        "sprinkler": 12,
        "fire_extinguisher": 25,  # P83: 几何兜底恢复后+7
        "smoke_detector": 19,  # P83: 几何兜底恢复后+6
        "fire_alarm": 35,
        "fire_door": 10,
        "fire_equipment": 2,
        "alarm_device": 2,
        "cable": 630,
        "beam": 13,
        "control_room": 3,
    },
    "9.气体灭火（唯美图框）_t3.dxf": {
        "wall": 644,
        "door": 331,
        "window": 3,
        "stair": 0,
        "column": 283,
        "room": 0,
        "dimension": 627,
        "text": 1179,
        "other": 3490,
        "equipment": 2466,
        "fire_extinguisher": 278,
        "sprinkler": 265,
        "fire_door": 1,
        "fire_alarm": 2,
        "smoke_detector": 1,
        "pipe": 6,
        "exit": 1,
        "equipment_room": 1,
    },
    "A1云计算中心_水消防2017.03.31_t3.dxf": {
        "wall": 196,
        "door": 1065,
        "window": 290,
        "stair": 0,
        "column": 51,
        "room": 7,
        "dimension": 129,
        "text": 268,
        "other": 6918,
        "fire_hydrant": 9,
        "sprinkler": 77,
        "fire_extinguisher": 64,
        "fire_alarm": 1,
        "handrail": 3,
        "indoor_hydrant": 8,
        "sprinkler_head": 10,
        "pipe": 209,
        "water_pipe": 10,
        "check_valve": 6,
        "speaker": 1,
        "pump": 1,
    },
}

# ── EXIST 函数预期结果 ─────────────────────────────────
EXIST_EXPECTED = {
    "6.火灾自动报警 （报审）_t3.dxf": {
        "EXIST-005": "PASS",
        "EXIST-006": "PASS",
    },
    "9.气体灭火（唯美图框）_t3.dxf": {
        "EXIST-005": "PASS",
    },
    "A1云计算中心_水消防2017.03.31_t3.dxf": {
        "EXIST-005": "PASS",
        "EXIST-006": "PASS",
    },
}


def find_dxf(data_dir: Path, stem: str) -> Path | None:
    candidates = sorted(data_dir.rglob(f"{stem}.dxf"))
    if not candidates:
        return None
    # 优先 data/ 根目录下的文件，排除 drawings/real/ 副本
    non_real = [c for c in candidates if "drawings/real" not in str(c)]
    return non_real[0] if non_real else candidates[0]


def validate_one(data_dir: Path, stem: str) -> dict:
    dxf_name = f"{stem}.dxf"
    path = find_dxf(data_dir, stem)
    result = {
        "file": dxf_name,
        "status": "unknown",
        "entity_drift": [],
        "exist_failures": [],
        "parse_error": None,
    }

    if path is None:
        result["status"] = "error"
        result["parse_error"] = "文件未找到"
        return result

    t0 = time.time()
    try:
        parser = DrawingParser()
        data = parser.parse(str(path), f"baseline_{stem}")
        analyzer = SemanticAnalyzer()
        semantic = analyzer.analyze(data.primitives, data.dimensions or [])
        entities = semantic.get("entities", [])
        parse_ms = int((time.time() - t0) * 1000)
        result["parse_ms"] = parse_ms
        result["entity_count"] = len(entities)

        # Entity distribution check
        actual = Counter(e["type"] for e in entities)
        baseline = ENTITY_BASELINE.get(dxf_name, {})
        for etype, expected in baseline.items():
            got = actual.get(etype, 0)
            tol = max(int(expected * TOLERANCE), 1)
            if abs(got - expected) > tol:
                pct = ((got - expected) / expected * 100) if expected else None
                result["entity_drift"].append(
                    {
                        "type": etype,
                        "expected": expected,
                        "actual": got,
                        "delta": got - expected,
                        "tolerance": tol,
                        "percent": round(pct, 1) if pct is not None else None,
                    }
                )

        # EXIST function check
        registry = FuncRegistry()
        findings = []
        for e in entities:
            for func in registry.list_all():
                if func.matches(e):
                    f = func.execute(e)
                    if f:
                        findings.append(f.__dict__ if hasattr(f, "__dict__") else f)
        expected_exist = EXIST_EXPECTED.get(dxf_name, {})
        for fid, want in expected_exist.items():
            matches = [f for f in findings if f.get("func_id") == fid]
            passed = (
                any(f.get("result") == want for f in matches)
                if want == "PASS"
                else any(f.get("result") == "FAIL" for f in matches)
            )
            if not passed:
                result["exist_failures"].append(
                    {
                        "func_id": fid,
                        "expected": want,
                        "matches_found": len(matches),
                    }
                )

        result["status"] = (
            "ok" if not result["entity_drift"] and not result["exist_failures"] else "drift"
        )

    except Exception as e:
        result["status"] = "error"
        result["parse_error"] = f"{type(e).__name__}: {e}"

    return result


def print_report(results: list):
    print(f"\n{'='*70}")
    print(f"  BAA 真实图纸 Baseline 验证报告")
    print(f"  基准线版本: {BASELINE_VERSION} | 容忍度: ±{int(TOLERANCE*100)}%")
    print(f"{'='*70}\n")
    total_ok = 0
    total_drift = 0
    total_error = 0
    for r in results:
        status_icon = {"ok": "✅", "drift": "⚠️", "error": "❌"}.get(r["status"], "❓")
        if r["status"] == "ok":
            total_ok += 1
        elif r["status"] == "drift":
            total_drift += 1
        else:
            total_error += 1
        print(
            f"  {status_icon} {r['file']}  ({r.get('parse_ms',0)}ms, {r.get('entity_count','?')} entities)"
        )
        for d in r.get("entity_drift", []):
            print(
                f"     ⚠  {d['type']}: {d['expected']} ± {d['tolerance']} → {d['actual']} ({d['percent']}%)"
            )
        for e in r.get("exist_failures", []):
            print(
                f"     ⚠  {e['func_id']}: 预期 {e['expected']}, 未匹配 (matches={e['matches_found']})"
            )
        if r.get("parse_error"):
            print(f"     ❌ {r['parse_error']}")

    print(f"\n  合计: {len(results)} 张图纸  ✅ {total_ok}  ⚠️ {total_drift}  ❌ {total_error}")
    if total_drift + total_error == 0:
        print(f"  🎉 Baseline 全部通过，无漂移")
    else:
        print(f"  ⚠️  有 {total_drift + total_error} 张需要关注")
    print(f"{'='*70}\n")


def main():
    ap = argparse.ArgumentParser(description="BAA 真实图纸 Baseline 验证 (P81)")
    ap.add_argument("--json", "-j", help="输出 JSON 报告路径")
    ap.add_argument("--update-baseline", action="store_true", help="危险: 用当前数据覆盖基准线")
    args = ap.parse_args()

    data_dir = BASE_DIR / "data"

    print(f"  正在验证 {len(FIXED_DRAWINGS)} 张固定图纸...")
    results = []
    for stem in FIXED_DRAWINGS:
        print(f"  [{stem}] ", end="", flush=True)
        r = validate_one(data_dir, stem)
        print(f"{r['status']} ({r.get('parse_ms',0)}ms)")
        results.append(r)

    print_report(results)

    report = {
        "version": BASELINE_VERSION,
        "tolerance": TOLERANCE,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r["status"] == "ok"),
            "drift": sum(1 for r in results if r["status"] == "drift"),
            "error": sum(1 for r in results if r["status"] == "error"),
        },
    }

    if args.json:
        out = Path(args.json)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  报告已写入: {out}")

    if args.update_baseline:
        print(
            "  ⚠️  注意: --update-baseline 需要人工编辑 test_real_drawings.py，脚本不自动修改代码"
        )

    # Exit code
    if report["summary"]["error"] > 0:
        return 2
    if report["summary"]["drift"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
