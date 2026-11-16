"""机电图设备规则适用性审计。

复用 fp_rate_audit 的核心逻辑，但移除机电图跳过（drawing_type 电气/暖通），
评估设备规则（EXIST-消防泵/水箱/探测器等）在机电图中的适用性。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from collections import Counter, defaultdict
from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.semantic_analyzer import SemanticAnalyzer
from src.baa_engine.atomic_functions import FuncRegistry
from scripts.fp_rate_audit import (
    _dedupe_lobby_area_findings,
    filter_plan_only_func_ids,
    not_applicable_func_ids,
    WidthContext,
    build_scopes,
    aggregate_exist_in_scopes,
    PLAN_ONLY_REASON,
    classify,
)

MEP_DIR = PROJECT_ROOT / "data" / "drawings" / "real" / "mep"


def run_mep_review(dxf_path: Path) -> dict:
    """机电图判定：同 run_review 但不跳过机电图。"""
    parser = DrawingParser()
    result = parser.parse(str(dxf_path), f"mep_audit_{dxf_path.stem}")
    if not result.success:
        return {"file": dxf_path.name, "success": False, "error": result.error}

    primitive_count = len(result.primitives or [])
    if primitive_count == 0:
        return {
            "file": dxf_path.name, "success": True, "valid": False,
            "content_validity": "empty_stub",
            "file_size": dxf_path.stat().st_size if dxf_path.exists() else 0,
            "primitive_count": 0, "entity_count": 0, "scope_count": 0,
            "scope_mode": "invalid", "findings": [], "entity_types": {},
            "coverage": {"evaluated_rules": 0, "applicable_rules": 0, "ratio": 0.0,
                         "unrecognized_types": [], "evaluated_func_ids": [],
                         "applicable_func_ids": []},
            "classification": {"counts": {}, "method": "invalid"},
        }

    drawing_type = getattr(result, "drawing_type", {})
    sheet_type = getattr(result, "sheet_type", {}) or {}

    semantic = SemanticAnalyzer().analyze(result.primitives, result.dimensions)
    entities = [
        e if isinstance(e, dict) else getattr(e, "__dict__", {})
        for e in semantic["entities"]
    ]
    unclassified_entities = semantic.get("unclassified_entities") or []
    unclassified_top = (semantic.get("classification_stats") or {}).get(
        "unclassified_layer_top", []
    )
    type_counts = Counter(e.get("type", "?") for e in entities)
    registry = FuncRegistry()
    funcs = registry.list_all()

    _scope_mode = sheet_type.get("scope_mode")
    local_ids = filter_plan_only_func_ids(
        [
            f.func_id
            for f in funcs
            if not getattr(f, "requires_global_context", False)
            and f.category.value != "exist"
        ],
        _scope_mode,
    )
    findings: list[dict] = []
    evaluated_ids: set[str] = set()

    def _record(func, r, entity_type, entity_id, severity, explanation, finding_source):
        findings.append({
            "func_id": func.func_id, "clause_id": func.clause_id,
            "func_name": func.name, "category": func.category.value,
            "entity_type": entity_type, "entity_id": entity_id,
            "actual": r.actual, "threshold": r.threshold,
            "operator": r.operator, "severity": severity,
            "confidence": r.confidence, "source": finding_source,
            "explanation": explanation[:160],
            "approximate": bool((r.params or {}).get("approximate")),
            "width_basis": (r.params or {}).get("width_basis", ""),
        })

    width_ctx = WidthContext(entities)
    _view_frames = getattr(result, "view_frames", None) or []
    _non_plan_bands = [
        (vf.get("y_min", 0), vf.get("y_max", 0))
        for vf in _view_frames if vf.get("scope_mode") == "non_plan"
    ]

    def _in_non_plan_view(bb):
        if not _non_plan_bands or not bb:
            return False
        cy = bb.get("y", 0) + bb.get("height", 0) / 2
        return any(lo <= cy <= hi for lo, hi in _non_plan_bands)

    for e in entities:
        if _in_non_plan_view(e.get("bbox") or {}):
            continue
        for fid, r in registry.execute_chained(local_ids, e).items():
            if r is None:
                continue
            evaluated_ids.add(fid)
            if r.result == "PASS":
                continue
            func = registry.get(fid)
            if func is None:
                continue
            if fid in _AGGREGATE_WIDTH_FUNCS and width_ctx.aggregate_pass(e, r.threshold):
                continue
            _record(func, r, e.get("type", ""), e.get("id", ""),
                    r.severity.value if hasattr(r.severity, "value") else str(r.severity),
                    "", "local")

    entity_types_in_drawing = {e.get("type", "") for e in entities}
    scopes = build_scopes(entities)
    for func in funcs:
        if func.category.value != "exist":
            continue
        targets = set(func.target_entities or [])
        if targets and not targets.intersection(entity_types_in_drawing):
            continue
        prereqs = set(getattr(func, "prerequisite_types", []) or [])
        if prereqs and not prereqs.intersection(entity_types_in_drawing):
            continue
        severity = "critical"
        scope_info = ""
        if targets:
            agg = aggregate_exist_in_scopes(func.func_id, sorted(targets), entities, scopes)
            if agg["overall"] == "pass":
                evaluated_ids.add(func.func_id)
                continue
            if agg["overall"] == "partial":
                evaluated_ids.add(func.func_id)
                findings.append({
                    "func_id": func.func_id, "clause_id": func.clause_id,
                    "func_name": func.name, "category": func.category.value,
                    "entity_type": "missing", "entity_id": "",
                    "actual": float(len(agg["scope_results"]) - len(agg["missing_scopes"])),
                    "threshold": float(len(agg["scope_results"])),
                    "operator": ">=", "severity": "low", "confidence": 0.5,
                    "source": "exist_scope",
                    "explanation": (
                        f"区域级提示：目标类型在全图存在，但 {len(agg['missing_scopes'])}"
                        f"/{len(agg['scope_results'])} 个作用域未检出"
                    )[:160],
                })
                continue
        r = registry.execute_with_timeout(func, None)
        if r is None:
            continue
        evaluated_ids.add(func.func_id)
        if r.result == "PASS":
            continue
        _record(func, r, "missing", "", severity, scope_info, "exist_scope")

    findings = _dedupe_lobby_area_findings(findings)

    entity_type_set = set(type_counts)
    applicable_ids: set[str] = set()
    referenced_types: set[str] = set()
    _not_applicable = set(not_applicable_func_ids(_scope_mode))
    for f in funcs:
        if getattr(f, "requires_global_context", False):
            continue
        if f.func_id in _not_applicable:
            continue
        if f.category.value == "exist":
            prereqs = set(getattr(f, "prerequisite_types", []) or [])
            if prereqs and not prereqs.intersection(entity_type_set):
                continue
        targets = set(f.target_entities or [])
        if targets:
            referenced_types.update(targets)
            if any(f.matches(e) for e in entities):
                applicable_ids.add(f.func_id)
        else:
            applicable_ids.add(f.func_id)

    evaluated_count = len(evaluated_ids)
    applicable_count = len(applicable_ids)
    unsupported_ids = {f.func_id for f in funcs if getattr(f, "unsupported_2d", False)}
    applicable_unsupported = applicable_ids & unsupported_ids
    gate_ids = {f.func_id for f in funcs if getattr(f, "implementation_gate", False)}
    applicable_gated = applicable_ids & gate_ids
    judgeable_count = applicable_count - len(applicable_unsupported) - len(applicable_gated)
    coverage = {
        "evaluated_rules": evaluated_count,
        "applicable_rules": applicable_count,
        "ratio": round(evaluated_count / applicable_count, 3) if applicable_count else 0.0,
        "judgeable_rules": judgeable_count,
        "judgeable_ratio": round(evaluated_count / judgeable_count, 3) if judgeable_count else 0.0,
        "unsupported_rules": len(applicable_unsupported),
        "unsupported_func_ids": sorted(applicable_unsupported),
        "implementation_gate_rules": len(applicable_gated),
        "implementation_gate_func_ids": sorted(applicable_gated),
        "unrecognized_types": sorted(entity_type_set - referenced_types),
        "evaluated_func_ids": sorted(evaluated_ids),
        "applicable_func_ids": sorted(applicable_ids),
        "not_applicable_func_ids": sorted(_not_applicable),
        "not_applicable_reason": PLAN_ONLY_REASON if _not_applicable else "",
    }

    return {
        "file": dxf_path.name, "success": True, "valid": True,
        "primitive_count": len(result.primitives),
        "entity_count": len(entities),
        "unclassified_count": len(unclassified_entities),
        "unclassified_layer_top": unclassified_top,
        "accounted_entity_count": len(entities) + len(unclassified_entities),
        "entity_types": dict(type_counts.most_common()),
        "evac_width_stats": width_ctx.stats,
        "scope_mode": scopes["mode"],
        "scope_count": len(scopes["scopes"]),
        "drawing_type": drawing_type,
        "sheet_type": sheet_type,
        "low_confidence": bool(sheet_type.get("low_confidence")),
        "coverage": coverage,
        "findings": findings,
    }


# 从 fp_rate_audit 导入聚合宽度函数集合
try:
    from scripts.fp_rate_audit import _AGGREGATE_WIDTH_FUNCS
except ImportError:
    _AGGREGATE_WIDTH_FUNCS = set()


def main():
    print(f"=== 机电图设备规则适用性审计：{len(list(MEP_DIR.glob('*.dxf')))} 张 ===")
    reports = []
    for p in sorted(MEP_DIR.glob("*.dxf")):
        rep = run_mep_review(p)
        reports.append(rep)
        if not rep["success"]:
            print(f"[FAIL] {p.name}: {rep['error']}")
            continue
        if not rep.get("valid", True):
            print(f"[INVALID] {p.name}: {rep.get('content_validity')}")
            continue
        cov = rep.get("coverage", {})
        cls = classify(rep)["counts"]
        print(f"[OK] {p.name}: 实体={rep['entity_count']}, "
              f"drawing_type={rep.get('drawing_type', {}).get('type', '?')}, "
              f"findings={len(rep['findings'])}, 分类={cls}, "
              f"可判定={cov.get('evaluated_rules', 0)}/{cov.get('judgeable_rules', 0)}"
              f"({cov.get('judgeable_ratio', 0.0):.1%})")
        # 设备规则适用性
        device_funcs = [f for f in rep["findings"] if f["category"] in ("exist", "attribute")]
        if device_funcs:
            from collections import Counter
            by_func = Counter(f["func_id"] for f in device_funcs)
            print(f"     设备规则 finding: {dict(by_func.most_common(10))}")


if __name__ == "__main__":
    main()