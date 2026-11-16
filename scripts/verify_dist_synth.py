"""验证 DIST-005/006/008 在合成图（exit=2）的判定。

用法：
    python scripts/verify_dist_synth.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fp_rate_audit import run_review

DIST_FUNCS = {"DIST-004", "DIST-005", "DIST-006", "DIST-007", "DIST-008", "DIST-009", "DIST-010"}


def main() -> int:
    synth = [
        Path("data/drawings/real/synth/synth_evac.dxf"),
        Path("data/drawings/real/synth/synth_office_compliant.dxf"),
        Path("data/drawings/real/synth/synth_fire_lane.dxf"),
    ]
    for p in synth:
        if not p.exists():
            continue
        rep = run_review(p)
        if not rep.get("success"):
            print(f"{p.name}: FAIL {rep.get('error')}")
            continue
        cov = rep.get("coverage", {})
        evals = set(cov.get("evaluated_func_ids", []))
        applics = set(cov.get("applicable_func_ids", []))
        print(f"\n{p.name}:")
        for fid in sorted(DIST_FUNCS):
            status = "适用" if fid in applics else "不适用"
            if fid in evals:
                status += " → 已判定"
            else:
                status += " → 未判定"
            print(f"  {fid}: {status}")
        # findings 明细
        for f in rep.get("findings", []):
            if f.get("func_id") in DIST_FUNCS:
                print(f"    finding: {f['func_id']} {f['entity_id']} actual={f['actual']} "
                      f"threshold={f['threshold']} {f['severity']} {f['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
