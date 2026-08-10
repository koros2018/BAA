#!/usr/bin/env python3
"""
P98: 跨图纸对比审计报告生成器

基于 real_drawing_audit.py 的 JSON 输出，生成结构化对比报告：
- 跨图纸实体分布对比
- 违规模式分析（按原子函数聚合跨图统计）
- 图纸质量排名（PASS率排序）
输出: data/cross_drawing_comparison_report.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_audit_report() -> list[dict]:
    path = PROJECT_ROOT / "data" / "real_drawing_audit_report.json"
    if not path.exists():
        print(f"审计报告不存在: {path}")
        return []
    with open(path) as f:
        return json.load(f)


def analyze_entity_distribution(reports: list[dict]) -> dict:
    drawing_entities: dict[str, dict[str, int]] = {}
    for r in reports:
        if r.get("success") and r.get("entity_count", 0) > 0:
            drawing_entities[r["file"]] = r.get("entity_types", {})
    all_types = defaultdict(int)
    for entities in drawing_entities.values():
        for t, c in entities.items():
            all_types[t] += c
    return {"per_drawing": drawing_entities, "aggregate": dict(sorted(all_types.items(), key=lambda x: -x[1]))}


def analyze_violation_patterns(reports: list[dict]) -> dict:
    func_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "PASS": 0, "FAIL": 0, "drawings_with_fail": 0})
    drawing_violations: dict[str, list[dict]] = {}
    for r in reports:
        if not r.get("success"):
            continue
        func_summary = r.get("func_summary", {})
        for fid, stats in func_summary.items():
            func_stats[fid]["total"] += stats.get("total", 0)
            func_stats[fid]["PASS"] += stats.get("PASS", 0)
            func_stats[fid]["FAIL"] += stats.get("FAIL", 0)
            if stats.get("FAIL", 0) > 0:
                func_stats[fid]["drawings_with_fail"] += 1
        if any(s.get("FAIL", 0) > 0 for s in func_summary.values()):
            drawing_violations[r["file"]] = [
                {"func_id": fid, **s}
                for fid, s in func_summary.items()
                if s.get("FAIL", 0) > 0
            ]
    ranked = sorted(func_stats.items(), key=lambda x: -x[1]["FAIL"])
    top_violations = [
        {"func_id": fid, **stats, "fail_rate": f"{stats['FAIL'] / max(stats['total'], 1) * 100:.1f}%"}
        for fid, stats in ranked
        if stats["FAIL"] > 0
    ]
    return {"top_violations": top_violations, "drawings_with_violations": dict(sorted(drawing_violations.items()))}


def compute_drawing_quality_ranking(reports: list[dict]) -> list[dict]:
    ranking = []
    for r in reports:
        if not r.get("success") or r.get("entity_count", 0) == 0:
            ranking.append({"file": r["file"], "entity_count": 0, "pass_rate": None, "total_findings": 0, "total_pass": 0, "total_fail": 0, "grade": "N/A", "note": "空图纸（xref 未解析）"})
            continue
        total_findings = sum(s.get("total", 0) for s in r.get("func_summary", {}).values())
        total_pass = sum(s.get("PASS", 0) for s in r.get("func_summary", {}).values())
        total_fail = sum(s.get("FAIL", 0) for s in r.get("func_summary", {}).values())
        pass_rate = total_pass / max(total_findings, 1)
        grade = "A" if pass_rate >= 0.95 else "B" if pass_rate >= 0.80 else "C" if pass_rate >= 0.60 else "D"
        ranking.append({"file": r["file"], "entity_count": r["entity_count"], "pass_rate": round(pass_rate, 4), "total_findings": total_findings, "total_pass": total_pass, "total_fail": total_fail, "grade": grade})
    ranking.sort(key=lambda x: x["pass_rate"] if x["pass_rate"] is not None else -1)
    return ranking


def build_text_report(entity_dist: dict, violation_patterns: dict, ranking: list[dict]) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("跨图纸对比审计报告")
    lines.append("=" * 70)
    lines.append("\n--- 图纸质量排名 ---")
    lines.append(f"{'排名':<4} {'图纸':<40} {'实体':>8} {'PASS率':>8} {'等级':>4}")
    lines.append("-" * 66)
    for i, r in enumerate(ranking, 1):
        rate_str = f"{r['pass_rate']*100:.1f}%" if r["pass_rate"] is not None else "N/A"
        lines.append(f"{i:<4} {r['file'][:38]:<40} {r['entity_count']:>8} {rate_str:>8} {r['grade']:>4}")
    lines.append("\n--- 跨图实体类型聚合 TOP-15 ---")
    lines.append(f"{'实体类型':<20} {'数量':>10}")
    lines.append("-" * 32)
    for t, c in list(entity_dist["aggregate"].items())[:15]:
        lines.append(f"{t:<20} {c:>10}")
    lines.append("\n--- 违规模式 TOP-15（跨图聚合） ---")
    lines.append(f"{'函数ID':<20} {'总命中':>8} {'FAIL':>8} {'FAIL率':>8} {'涉及图纸':>8}")
    lines.append("-" * 56)
    for v in violation_patterns["top_violations"][:15]:
        lines.append(f"{v['func_id']:<20} {v['total']:>8} {v['FAIL']:>8} {v['fail_rate']:>8} {v['drawings_with_fail']:>8}")
    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def main():
    reports = load_audit_report()
    if not reports:
        print("No audit report found. Run scripts/real_drawing_audit.py first.")
        return 1
    print(f"加载 {len(reports)} 张图纸审计报告")
    entity_dist = analyze_entity_distribution(reports)
    violation_patterns = analyze_violation_patterns(reports)
    ranking = compute_drawing_quality_ranking(reports)
    text_report = build_text_report(entity_dist, violation_patterns, ranking)
    print(text_report)
    output = {"entity_distribution": entity_dist, "violation_patterns": violation_patterns, "quality_ranking": ranking}
    out_path = PROJECT_ROOT / "data" / "cross_drawing_comparison_report.json"
    with open(out_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n对比报告已保存: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())