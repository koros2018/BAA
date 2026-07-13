#!/usr/bin/env python3
"""
真实图纸全量审计脚本
对每张真实 DXF 图纸执行：解析 → 语义分析 → 原子函数判定
输出：实体分布 + 违规详情 + 统计汇总
"""

import sys
import json
import functools
from pathlib import Path
from collections import Counter, defaultdict

# 强制 flush
print = functools.partial(print, flush=True)

# ── 项目根 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry

DATA_DIR = PROJECT_ROOT / "data"
REAL_DIR = DATA_DIR / "drawings" / "real"


def audit_drawing(dxf_path):
    """对单张 DXF 执行全流程审计"""
    parser = DrawingParser()
    analyzer = SemanticAnalyzer()
    registry = FuncRegistry()

    result = parser.parse(str(dxf_path), f"audit_{dxf_path.stem}")
    if not result.success:
        return {
            "file": dxf_path.name,
            "success": False,
            "error": result.error,
            "primitive_count": 0,
        }

    semantic = analyzer.analyze(result.primitives, result.dimensions)
    entities = semantic["entities"]

    type_counts = dict(Counter(e["type"] for e in entities).most_common())

    # 执行所有原子函数
    all_findings = []
    for e in entities:
        for func in registry.list_all():
            if func.matches(e):
                f = func.execute(e)
                if f:
                    d = f.__dict__ if hasattr(f, "__dict__") else f
                    all_findings.append(d)

    # 按 func_id 聚合
    func_results = defaultdict(list)
    for f in all_findings:
        fid = f.get("func_id", "unknown")
        func_results[fid].append(f)

    func_summary = {}
    for fid, findings in func_results.items():
        results = [f.get("result", "?") for f in findings]
        pass_count = results.count("PASS")
        fail_count = results.count("FAIL")
        func_summary[fid] = {
            "total": len(findings),
            "PASS": pass_count,
            "FAIL": fail_count,
        }

    return {
        "file": dxf_path.name,
        "success": True,
        "primitive_count": len(result.primitives),
        "entity_count": len(entities),
        "entity_types": type_counts,
        "func_summary": func_summary,
        "total_findings": len(all_findings),
    }


def collect_all_drawings():
    """收集所有可用的真实 DXF 图纸"""
    paths = []
    seen = set()

    for f in sorted(DATA_DIR.glob("*_t3.dxf")):
        paths.append(f)
        seen.add(f.name)

    dgt_dir = DATA_DIR / "1东莞通施工图-报审170823"
    if dgt_dir.exists():
        for f in sorted(dgt_dir.glob("*.dxf")):
            if f.name not in seen:
                paths.append(f)
                seen.add(f.name)

    if REAL_DIR.exists():
        for f in sorted(REAL_DIR.glob("*.dxf")):
            if f.name not in seen:
                paths.append(f)
                seen.add(f.name)

    return paths


def main():
    drawings = collect_all_drawings()
    print(f"=== 发现 {len(drawings)} 张真实图纸 ===")
    print()

    all_reports = []
    for i, dxf_path in enumerate(drawings, 1):
        print(f"[{i}/{len(drawings)}] 审计: {dxf_path.name}")
        report = audit_drawing(dxf_path)
        all_reports.append(report)

        if report["success"]:
            print(f"  图元: {report['primitive_count']}, 实体: {report['entity_count']}")
            print(f"  实体类型: {dict(list(report['entity_types'].items())[:15])}")
            print(f"  原子函数命中: {len(report['func_summary'])} 个")
            fails = []
            for fid, s in report["func_summary"].items():
                if s["FAIL"] > 0:
                    fails.append(f"{fid}(PASS={s['PASS']}, FAIL={s['FAIL']})")
            if fails:
                print(f"  FAIL 函数: {', '.join(fails)}")
            else:
                print(f"  全部 PASS")
        else:
            print(f"  ❌ 解析失败: {report['error']}")
        print()

    # 汇总统计
    print("=" * 60)
    print("=== 汇总统计 ===")
    print()

    success_count = sum(1 for r in all_reports if r["success"])
    fail_count = sum(1 for r in all_reports if not r["success"])
    print(f"解析成功: {success_count}/{len(drawings)}")
    print(f"解析失败: {fail_count}/{len(drawings)}")

    func_hit_count = defaultdict(int)
    func_fail_count = defaultdict(int)
    func_pass_count = defaultdict(int)

    for r in all_reports:
        if not r["success"]:
            continue
        for fid, s in r["func_summary"].items():
            func_hit_count[fid] += s["total"]
            func_fail_count[fid] += s["FAIL"]
            func_pass_count[fid] += s["PASS"]

    print()
    print("--- 原子函数命中统计（全部图纸汇总） ---")
    print(f"{'函数ID':<20} {'总命中':>8} {'PASS':>8} {'FAIL':>8} {'FAIL率':>8}")
    print("-" * 52)
    for fid in sorted(func_hit_count.keys(), key=lambda k: func_fail_count[k], reverse=True):
        total = func_hit_count[fid]
        fp = func_pass_count[fid]
        ff = func_fail_count[fid]
        rate = f"{ff/total*100:.1f}%" if total > 0 else "-"
        print(f"{fid:<20} {total:>8} {fp:>8} {ff:>8} {rate:>8}")

    output_path = PROJECT_ROOT / "data" / "real_drawing_audit_report.json"
    with open(output_path, "w") as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整报告已保存: {output_path}")


if __name__ == "__main__":
    main()