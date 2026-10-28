#!/usr/bin/env python3
"""误报率评估：真实图纸 → 生产等价判定 → 逐条 finding 归因。

与 ``scripts/real_drawing_audit.py``（旧版逐实体盲跑）不同，本脚本复刻
``src/api/review/review_routes.py`` 主链路的判定语义：

1. ``requires_global_context=False`` 的函数：逐实体 ``execute_chained``；
2. ``requires_global_context=True`` / EXIST 缺失检查：作用域聚合
   （``scope_aggregator``），partial → low 区域提示，missing → critical。

输出逐条 finding（含实体类型/实测值/阈值/严重度），并按机械规则标注
误报类别，供 ``docs/benchmark/`` 报告引用。

用法::

    python scripts/fp_rate_audit.py                 # 默认扫 data/drawings/real
    python scripts/fp_rate_audit.py path/to/x.dxf   # 指定图纸
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baa_engine.atomic_functions import FuncRegistry
from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.scope_aggregator import aggregate_exist_in_scopes, build_scopes
from src.baa_engine.semantic_analyzer import SemanticAnalyzer

REAL_DIR = PROJECT_ROOT / "data" / "drawings" / "real"
REPORT_PATH = PROJECT_ROOT / "data" / "fp_rate_audit_report.json"

# 测试夹具不是真实图纸，不计入误报评估
FIXTURE_PREFIXES = ("test_",)


def _drawings(argv: list[str]) -> list[Path]:
    if argv:
        return [Path(p) for p in argv]
    return [
        p
        for p in sorted(REAL_DIR.glob("*.dxf"))
        if not p.name.startswith(FIXTURE_PREFIXES)
    ]


def run_review(dxf_path: Path) -> dict:
    """生产等价判定：返回 findings 明细 + 实体分布。"""
    parser = DrawingParser()
    result = parser.parse(str(dxf_path), f"fp_audit_{dxf_path.stem}")
    if not result.success:
        return {"file": dxf_path.name, "success": False, "error": result.error}

    semantic = SemanticAnalyzer().analyze(result.primitives, result.dimensions)
    entities = [
        e if isinstance(e, dict) else getattr(e, "__dict__", {}) for e in semantic["entities"]
    ]
    type_counts = Counter(e.get("type", "?") for e in entities)
    registry = FuncRegistry()
    funcs = registry.list_all()

    local_ids = [f.func_id for f in funcs if not getattr(f, "requires_global_context", False)]
    findings: list[dict] = []

    def _record(
        func,
        r,
        entity_type: str,
        entity_id: str,
        severity: str,
        explanation: str,
        finding_source: str,
    ) -> None:
        findings.append(
            {
                "func_id": func.func_id,
                "clause_id": func.clause_id,
                "func_name": func.name,
                "category": func.category.value,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "actual": r.actual,
                "threshold": r.threshold,
                "operator": r.operator,
                "severity": severity,
                "confidence": r.confidence,
                "source": finding_source,
                "explanation": explanation[:160],
            }
        )

    # ── 1. 逐实体本地函数（同 review_routes._do_clustering）──
    for e in entities:
        for fid, r in registry.execute_chained(local_ids, e).items():
            if r is None or r.result == "PASS":
                continue
            func = registry.get(fid)
            if func is None:
                continue
            _record(
                func,
                r,
                e.get("type", ""),
                e.get("id", ""),
                r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                "",
                "local",
            )

    # ── 2. 全局函数 + EXIST 缺失检查（同 review_routes 作用域聚合）──
    entity_types_in_drawing = {e.get("type", "") for e in entities}
    scopes = build_scopes(entities)
    for func in funcs:
        if func.category.value != "exist":
            continue
        targets = set(func.target_entities or [])
        if targets and not targets.intersection(entity_types_in_drawing):
            continue  # 目标类型在图中完全不存在 → 覆盖问题，不判违规
        severity = "critical"
        scope_info = ""
        if targets:
            agg = aggregate_exist_in_scopes(func.func_id, sorted(targets), entities, scopes)
            if agg["overall"] == "pass":
                continue
            if agg["overall"] == "partial":
                severity = "low"
                scope_info = (
                    f"；以下区域未检出({len(agg['missing_scopes'])}"
                    f"/{len(agg['scope_results'])} 个作用域)"
                )
        r = registry.execute_with_timeout(func, None)
        if r is None or r.result == "PASS":
            continue
        _record(
            func,
            r,
            "missing",
            "",
            severity,
            scope_info,
            "exist_scope",
        )

    return {
        "file": dxf_path.name,
        "success": True,
        "primitive_count": len(result.primitives),
        "entity_count": len(entities),
        "entity_types": dict(type_counts.most_common()),
        "scope_mode": scopes["mode"],
        "scope_count": len(scopes["scopes"]),
        "findings": findings,
    }


def classify(report: dict) -> dict:
    """按机械规则给成一条 finding 打误报标记（保守口径）。

    只有能「客观证明判定前提不成立」的才计为误报：
    1. ``exist_scope`` + ``missing`` 且目标类型在图中有实例 → 事实存在却判缺失；
    2. ``low`` 严重度 → 作用域分布提示，不是违规结论（单独统计）；
    3. 实测值为 0/缺失（DIM/ATTR）→ 无数据支撑的判定。
    """
    counts: dict[str, int] = defaultdict(int)
    labeled: list[dict] = []
    for f in report["findings"]:
        verdict = "unknown"
        if f["severity"] == "low":
            verdict = "scope_hint"
        elif f["source"] == "exist_scope" and f["entity_type"] == "missing":
            # 目标类型在整图有实例 → 不可能是「缺失」，判定前提不成立
            verdict = "false_missing" if f.get("_targets_present") else "unknown"
        elif f["category"] in ("dimension", "attribute") and not f["actual"]:
            verdict = "no_data"
        counts[verdict] += 1
        labeled.append({**f, "verdict": verdict})
    return {"counts": dict(counts), "labeled": labeled}


def audit_one(path: Path) -> dict:
    report = run_review(path)
    if not report["success"]:
        return report
    report = _annotate_false_missing(report)
    report["classification"] = classify(report)
    return report


def _annotate_false_missing(report: dict) -> dict:
    """为 exist_scope/missing finding 标记目标类型是否在图中存在。"""
    from src.baa_engine.atomic_functions import FuncRegistry

    registry = FuncRegistry()
    type_counts = report.get("entity_types") or {}
    for f in report["findings"]:
        if f["source"] != "exist_scope" or f["entity_type"] != "missing":
            continue
        func = registry.get(f["func_id"])
        targets = set(func.target_entities or []) if func else set()
        present = sum(n for t, n in type_counts.items() if t in targets)
        f["target_present_count"] = present
        # 供 classify 使用的机械标记
        f["_targets_present"] = present > 0
    return report


def main(argv: list[str]) -> int:
    paths = _drawings(argv)
    print(f"=== 误报率评估：{len(paths)} 张图纸（生产等价判定）===\n", flush=True)

    reports = []
    for p in paths:
        rep = audit_one(p)
        reports.append(rep)
        if not rep["success"]:
            print(f"[FAIL] {p.name}: {rep['error']}", flush=True)
            continue
        cls = rep["classification"]["counts"]
        total = len(rep["findings"])
        print(
            f"[OK] {p.name}: 实体={rep['entity_count']}, 作用域={rep['scope_count']}"
            f"({rep['scope_mode']}), findings={total}, 分类={cls}",
            flush=True,
        )
        by_func = Counter(f["func_id"] for f in rep["findings"])
        top = ", ".join(f"{k}={v}" for k, v in by_func.most_common(8))
        if top:
            print(f"     Top 函数: {top}", flush=True)

    print("\n=== 汇总 ===", flush=True)
    all_findings = [
        f for r in reports if r.get("success") for f in r["findings"]
    ]
    print(f"findings 总数: {len(all_findings)}", flush=True)
    print(
        "严重度分布: "
        + str(dict(Counter(f["severity"] for f in all_findings).most_common())),
        flush=True,
    )
    print(
        "来源分布: "
        + str(dict(Counter(f["source"] for f in all_findings).most_common())),
        flush=True,
    )
    print("\n函数 FAIL 排行:", flush=True)
    for fid, n in Counter(f["func_id"] for f in all_findings).most_common(15):
        print(f"  {fid:<14} {n}", flush=True)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, ensure_ascii=False, indent=2)
    print(f"\n明细报告: {REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
