"""深挖 DIST/COUNT 判定状态（生产等价 run_review 路径）。

分析真实建筑图样本中：
1. DIST 规则（DIST-004~010）是否被判定（evaluated），实体对距离是否可计算
2. COUNT 规则（COUNT-001~026）是否被判定，容器（fire_zone/floor）是否识别

用法：
    python scripts/audit_dist_count_status.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fp_rate_audit import run_review, _drawings

DIST_FUNCS = {"DIST-004", "DIST-005", "DIST-006", "DIST-007", "DIST-008", "DIST-009", "DIST-010"}
COUNT_FUNCS = {
    "COUNT-001", "COUNT-002", "COUNT-003", "COUNT-004", "COUNT-013", "COUNT-014",
    "COUNT-015", "COUNT-016", "COUNT-017", "COUNT-019", "COUNT-020", "COUNT-021",
    "COUNT-022", "COUNT-023", "COUNT-024", "COUNT-025", "COUNT-026",
}


def main() -> int:
    paths = _drawings([])
    # 限制为前 20 张有效图纸，加速审计
    paths = paths[:20]
    print(f"=== DIST/COUNT 判定状态审计：{len(paths)} 张图纸（前20） ===\n")

    dist_eval = Counter()   # func_id -> 被判定次数
    dist_applic = Counter() # func_id -> 适用次数
    count_eval = Counter()
    count_applic = Counter()
    type_present = Counter()  # 关键类型出现次数
    zone_drawings = 0

    for p in paths:
        rep = run_review(p)
        if not rep.get("success") or not rep.get("valid", True) or rep.get("skipped"):
            continue
        cov = rep.get("coverage", {})
        evals = set(cov.get("evaluated_func_ids", []))
        applics = set(cov.get("applicable_func_ids", []))
        types = rep.get("entity_types") or {}
        for fid in DIST_FUNCS:
            if fid in applics:
                dist_applic[fid] += 1
            if fid in evals:
                dist_eval[fid] += 1
        for fid in COUNT_FUNCS:
            if fid in applics:
                count_applic[fid] += 1
            if fid in evals:
                count_eval[fid] += 1
        for t in ("fire_zone", "fire_compartment", "exit", "exit_door", "floor", "room", "hydrant", "fire_hydrant"):
            if types.get(t, 0):
                type_present[t] += 1
        if types.get("fire_zone") or types.get("fire_compartment"):
            zone_drawings += 1

    print("── DIST 规则 ──")
    for fid in sorted(DIST_FUNCS):
        print(f"  {fid}: 适用={dist_applic[fid]} 图, 判定={dist_eval[fid]} 图")
    print("\n── COUNT 规则 ──")
    for fid in sorted(COUNT_FUNCS):
        print(f"  {fid}: 适用={count_applic[fid]} 图, 判定={count_eval[fid]} 图")
    print("\n── 关键类型出现图纸数 ──")
    for t, n in type_present.most_common():
        print(f"  {t}: {n} 图")
    print(f"\n  fire_zone/fire_compartment 出现图纸: {zone_drawings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
