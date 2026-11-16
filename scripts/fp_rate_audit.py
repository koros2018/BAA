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
from src.api.review._shared import _dedupe_lobby_area_findings
from src.baa_engine.drawing_parser import DrawingParser
from src.baa_engine.evac_width import WidthContext
from src.baa_engine.review_scope import (
    filter_plan_only_func_ids,
    not_applicable_func_ids,
    PLAN_ONLY_REASON,
)
from src.baa_engine.scope_aggregator import aggregate_exist_in_scopes, build_scopes
from src.baa_engine.semantic_analyzer import SemanticAnalyzer

# 防火分区疏散宽度聚合（专家复核 2026-11-02）：DIM-006/DIM-113 的净宽要求
# 本质是「防火分区疏散总净宽」约束，实现见 src/baa_engine/evac_width.py。
_AGGREGATE_WIDTH_FUNCS = {"DIM-006", "DIM-113"}


REAL_DIR = PROJECT_ROOT / "data" / "drawings" / "real"
FILES_DIR = PROJECT_ROOT / "data" / "files"
REPORT_PATH = PROJECT_ROOT / "data" / "fp_rate_audit_report.json"

# 测试夹具不是真实图纸，不计入误报评估
FIXTURE_PREFIXES = ("test_",)


def _drawings(argv: list[str]) -> list[Path]:
    if argv:
        return [Path(p) for p in argv]
    drawings = []
    # DXF from real dir（递归含子目录：nasji/cype 等外部样本）
    for p in sorted(REAL_DIR.rglob("*.dxf")):
        if not p.name.startswith(FIXTURE_PREFIXES):
            drawings.append(p)
    # DWG from files dir（E6-T4 ezdwg 直读保留图层信息）
    for p in sorted(FILES_DIR.glob("*.dwg")):
        drawings.append(p)
    return drawings


def run_review(dxf_path: Path) -> dict:
    """生产等价判定：返回 findings 明细 + 实体分布。"""
    parser = DrawingParser()
    result = parser.parse(str(dxf_path), f"fp_audit_{dxf_path.stem}")
    if not result.success:
        return {"file": dxf_path.name, "success": False, "error": result.error}

    # ── 样本内容有效性门槛（P2-6）──
    # ezdxf 新建后未写入实体的空壳 DXF（如 data/drawings/real 下的 15KB 占位）
    # 解析出 0 图元。若不剔除，会以「0 实体 / 0 违规」混入基线统计，
    # 造成「图纸全部通过」的假象。
    primitive_count = len(result.primitives or [])
    if primitive_count == 0:
        file_size = dxf_path.stat().st_size if dxf_path.exists() else 0
        return {
            "file": dxf_path.name,
            "success": True,
            "valid": False,
            "content_validity": "empty_stub" if file_size < 65536 else "parse_failed",
            "file_size": file_size,
            "primitive_count": 0,
            "entity_count": 0,
            "scope_count": 0,
            "scope_mode": "invalid",
            "findings": [],
            "entity_types": {},
            "coverage": {
                "evaluated_rules": 0,
                "applicable_rules": 0,
                "ratio": 0.0,
                "unrecognized_types": [],
                "evaluated_func_ids": [],
                "applicable_func_ids": [],
            },
            "classification": {"counts": {}, "method": "invalid"},
        }

    # P130 图纸类型过滤：结构/电气/暖通图跳过原子函数（无疏散语义）
    drawing_type = getattr(result, "drawing_type", {})
    sheet_type = getattr(result, "sheet_type", {}) or {}
    if drawing_type.get("type") in ("结构", "电气", "暖通"):
        return {
            "file": dxf_path.name,
            "success": True,
            "valid": True,
            "skipped": True,
            "skip_reason": f"{drawing_type.get('type')}图无疏散语义，跳过审查",
            "entity_count": len(result.primitives or []),
            "scope_count": 0,
            "scope_mode": "skipped",
            "findings": [],
            "entity_types": {},
            "drawing_type": drawing_type,
            "sheet_type": sheet_type,
            "classification": {"counts": {}, "method": "skipped"},
            "coverage": {
                "evaluated_rules": 0,
                "applicable_rules": 0,
                "ratio": 0.0,
                "unrecognized_types": [],
                "evaluated_func_ids": [],
                "applicable_func_ids": [],
            },
        }

    # P121 图幅类型过滤：立面/剖面图、描线矢量化产物不进入审查范围，
    # 不出 findings，也不计入覆盖率分母（避免用平面图判据审查非平面图）。
    if sheet_type.get("scope_mode") == "non_plan":
        return {
            "file": dxf_path.name,
            "success": True,
            "valid": True,
            "skipped": True,
            "skip_reason": (
                f"图幅判定为「{sheet_type.get('label', '非平面图')}」"
                f"（{sheet_type.get('rule', '')}），非平面审查范围"
            ),
            "entity_count": len(result.primitives or []),
            "scope_count": 0,
            "scope_mode": "non_plan",
            "findings": [],
            "entity_types": {},
            "drawing_type": drawing_type,
            "sheet_type": sheet_type,
            "classification": {"counts": {}, "method": "non_plan"},
            "coverage": {
                "evaluated_rules": 0,
                "applicable_rules": 0,
                "ratio": 0.0,
                "unrecognized_types": [],
                "evaluated_func_ids": [],
                "applicable_func_ids": [],
            },
        }

    semantic = SemanticAnalyzer().analyze(result.primitives, result.dimensions)
    entities = [
        e if isinstance(e, dict) else getattr(e, "__dict__", {}) for e in semantic["entities"]
    ]
    # 未识别图元独立留存（T5 后续）：只做统计，不参与任何规则判定。
    unclassified_entities = semantic.get("unclassified_entities") or []
    unclassified_top = (semantic.get("classification_stats") or {}).get(
        "unclassified_layer_top", []
    )
    type_counts = Counter(e.get("type", "?") for e in entities)
    registry = FuncRegistry()
    funcs = registry.list_all()

    # A 类止血：非平面图幅（scope_mode != plan）不具备房间-门-出口拓扑，
    # EVAC-002/003/004 不进入执行，也不产生 finding。
    _scope_mode = sheet_type.get("scope_mode")
    local_ids = filter_plan_only_func_ids(
        [
            f.func_id
            for f in funcs
            if not getattr(f, "requires_global_context", False)
            and f.category.value != "exist"  # EXIST 缺失检查单独处理，不逐实体执行
        ],
        _scope_mode,
    )
    findings: list[dict] = []
    evaluated_ids: set[str] = set()  # P0-2: 实际产出判定结果的函数 id

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
                # 门窗符号尺寸（扇线长/弧半径）为近似值，finding 中可识别
                "approximate": bool((r.params or {}).get("approximate")),
                "width_basis": (r.params or {}).get("width_basis", ""),
            }
        )

    # ── 1. 逐实体本地函数（同 review_routes._do_clustering）──
    # 疏散宽度聚合上下文：按防火分区汇总疏散门净宽，并按疏散人数换算
    # 所需总净宽（GB50016-5.5.21），用于 DIM-006/DIM-113 的分区级判定。
    width_ctx = WidthContext(entities)

    # P121-V: 视图级 scope_mode 覆盖。混合图集（plan+section 共处一 DXF）中，
    # 非平面子视框内的派生实体（如看台踏步格间）不应进入逐实体判定。
    # 判定规则：实体 bbox 中心落在某个 non_plan 视框内 → 跳过本地函数。
    _view_frames = getattr(result, "view_frames", None) or []
    _non_plan_bands = [
        (vf.get("y_min", 0), vf.get("y_max", 0))
        for vf in _view_frames
        if vf.get("scope_mode") == "non_plan"
    ]

    def _in_non_plan_view(bb: dict) -> bool:
        if not _non_plan_bands:
            return False
        if not bb:
            return False
        cy = bb.get("y", 0) + bb.get("height", 0) / 2
        for lo, hi in _non_plan_bands:
            if lo <= cy <= hi:
                return True
        return False

    for e in entities:
        if _in_non_plan_view(e.get("bbox") or {}):
            continue  # P121-V: 非平面子视框内的实体不参与本地函数判定
        for fid, r in registry.execute_chained(local_ids, e).items():
            if r is None:
                continue
            evaluated_ids.add(fid)  # 有判定结果（PASS/FAIL）即视为可达
            if r.result == "PASS":
                continue
            func = registry.get(fid)
            if func is None:
                continue
            # 分区级疏散总净宽判定（专家复核 2026-11-02 根因 1）：
            # 同一防火分区内多扇疏散门宽度求和后与所需总净宽比较，
            # 替代逐门判定；无用途数据时回退单门阈值口径。
            if fid in _AGGREGATE_WIDTH_FUNCS and width_ctx.aggregate_pass(e, r.threshold):
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
        # 条件性规则：前置实体类型缺失时跳过（如 EXIST-067 需 fire_wall 存在才判定）
        prereqs = set(getattr(func, "prerequisite_types", []) or [])
        if prereqs and not prereqs.intersection(entity_types_in_drawing):
            continue
        severity = "critical"
        scope_info = ""
        if targets:
            agg = aggregate_exist_in_scopes(func.func_id, sorted(targets), entities, scopes)
            if agg["overall"] == "pass":
                evaluated_ids.add(func.func_id)  # 规则被判定且通过，计入可达
                continue
            if agg["overall"] == "partial":
                # T1: 区域级提示（同 review_routes 口径）——目标类型全图存在、
                # 但部分作用域未检出。计入 evaluated 并产 low finding，
                # 不再被「实体全局存在就 continue」吞掉。
                evaluated_ids.add(func.func_id)
                findings.append({
                    "func_id": func.func_id,
                    "clause_id": func.clause_id,
                    "func_name": func.name,
                    "category": func.category.value,
                    "entity_type": "missing",
                    "entity_id": "",
                    "actual": float(
                        len(agg["scope_results"]) - len(agg["missing_scopes"])
                    ),
                    "threshold": float(len(agg["scope_results"])),
                    "operator": ">=",
                    "severity": "low",
                    "confidence": 0.5,
                    "source": "exist_scope",
                    "explanation": (
                        f"区域级提示：目标类型在全图存在，但 {len(agg['missing_scopes'])}"
                        f"/{len(agg['scope_results'])} 个作用域未检出；分布不均，非确证违规"
                    )[:160],
                })
                continue
        r = registry.execute_with_timeout(func, None)
        if r is None:
            continue
        evaluated_ids.add(func.func_id)
        if r.result == "PASS":
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

    # ── T3: 前室类条款互斥（与 review_routes 同口径）──
    findings = _dedupe_lobby_area_findings(findings)

    # ── P0-2: 规则可达性（coverage）──
    # 与 review_routes 同口径：applicable = matches()（含类型别名归并）命中，
    # evaluated = 实际产出判定结果（PASS/FAIL 均计入）。
    entity_type_set = set(type_counts)
    applicable_ids: set[str] = set()
    referenced_types: set[str] = set()
    _not_applicable = set(not_applicable_func_ids(_scope_mode))
    for f in funcs:
        if getattr(f, "requires_global_context", False):
            continue
        # A 类止血：非平面图幅下不适用函数不进分母（与执行侧同口径）
        if f.func_id in _not_applicable:
            continue
        # T1: EXIST 条件规则的前置实体类型缺失 → 本图不适用，不计入分母
        # （执行侧在作用域聚合前就跳过这类规则）
        if f.category.value == "exist":
            prereqs = set(getattr(f, "prerequisite_types", []) or [])
            if prereqs and not prereqs.intersection(entity_type_set):
                continue
        targets = set(f.target_entities or [])
        if targets:
            referenced_types.update(targets)
            # P0-1: 用 matches() 而非裸类型匹配，与 execute_chained 判定口径一致
            if any(f.matches(e) for e in entities):
                applicable_ids.add(f.func_id)
        else:
            applicable_ids.add(f.func_id)
    evaluated_count = len(evaluated_ids)
    applicable_count = len(applicable_ids)
    # P2-1: 双口径分母。unsupported_2d 规则仍参与执行与分子计算，
    # 只在报告侧提供「可判定口径」的分母（剔除 2D 图纸无法提供判据的规则）。
    unsupported_ids = {
        f.func_id for f in funcs if getattr(f, "unsupported_2d", False)
    }
    applicable_unsupported = applicable_ids & unsupported_ids
    # P133: 实现门禁规则剔除出可判定分母（仍留在全规则口径分母）
    gate_ids = {
        f.func_id for f in funcs if getattr(f, "implementation_gate", False)
    }
    applicable_gated = applicable_ids & gate_ids
    judgeable_count = (
        applicable_count - len(applicable_unsupported) - len(applicable_gated)
    )
    coverage = {
        "evaluated_rules": evaluated_count,
        "applicable_rules": applicable_count,
        "ratio": round(evaluated_count / applicable_count, 3) if applicable_count else 0.0,
        "judgeable_rules": judgeable_count,
        "judgeable_ratio": (
            round(evaluated_count / judgeable_count, 3) if judgeable_count else 0.0
        ),
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

    # 内容指纹（解析后图元）：DWG/DXF 重复样本（同建筑不同版本）去重用。
    # 用前 200 图元 type+bbox 近似指纹，避免全量哈希开销。
    import hashlib
    _fp_parts = []
    for _pr in (result.primitives or [])[:200]:
        _fp_parts.append(f"{_pr.dxf_type}:{_pr.bbox}")
    content_fingerprint = hashlib.sha256("".join(_fp_parts).encode()).hexdigest()[:16]

    return {
        "file": dxf_path.name,
        "success": True,
        "valid": True,
        "content_fingerprint": content_fingerprint,
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
        # P2-6: 内容空壳（解析出 0 图元）不计入基线，避免「0 实体 = 0 违规」假通过
        if not rep.get("valid", True):
            print(
                f"[INVALID] {p.name}: 样本无效（{rep.get('content_validity')}，"
                f"{rep.get('file_size', 0)}B），已排除出基线统计",
                flush=True,
            )
            continue
        cls = rep["classification"]["counts"]
        total = len(rep["findings"])
        if rep.get("skipped"):
            print(
                f"[SKIP] {p.name}: {rep.get('skip_reason', '')}, "
                f"图幅={rep.get('sheet_type', {}).get('label', '')}"
                f"({rep.get('sheet_type', {}).get('rule', '')})",
                flush=True,
            )
            continue
        cov = rep.get("coverage", {})
        print(
            f"[OK] {p.name}: 实体={rep['entity_count']}+未识别={rep.get('unclassified_count', 0)}, "
            f"作用域={rep['scope_count']}"
            f"({rep['scope_mode']}), findings={total}, 分类={cls}, "
            f"可达={cov.get('evaluated_rules', 0)}/{cov.get('applicable_rules', 0)}"
            f"({cov.get('ratio', 0.0):.1%})"
            f"，可判定={cov.get('evaluated_rules', 0)}/{cov.get('judgeable_rules', 0)}"
            f"({cov.get('judgeable_ratio', 0.0):.1%})",
            flush=True,
        )
        by_func = Counter(f["func_id"] for f in rep["findings"])
        top = ", ".join(f"{k}={v}" for k, v in by_func.most_common(8))
        if top:
            print(f"     Top 函数: {top}", flush=True)

    # ── P2-7: 内容指纹去重（DWG/DXF 重复样本，同建筑不同版本）──
    # 同 content_fingerprint 只保留一张图纸，避免重复样本放大 finding 计数。
    # 保留首个（按 _drawings 顺序），后续重复样本标记 _dedup_fingerprint。
    _seen_fp: dict[str, str] = {}
    for rep in reports:
        fp = rep.get("content_fingerprint")
        if not fp:
            continue
        if fp in _seen_fp:
            rep["_dedup_fingerprint"] = _seen_fp[fp]
            print(
                f"[DEDUP-FP] {rep['file']}: 内容指纹 {fp} 与 {_seen_fp[fp]} 重复，"
                f"从基线排除（同建筑重复样本）",
                flush=True,
            )
        else:
            _seen_fp[fp] = rep["file"]

    valid_reports = [
        r
        for r in reports
        if r.get("success") and r.get("valid", True) and not r.get("skipped")
        and not r.get("_dedup_fingerprint")
    ]
    invalid_reports = [r for r in reports if r.get("success") and not r.get("valid", True)]
    skipped_reports = [r for r in reports if r.get("success") and r.get("skipped")]

    # ── P2-6: 样本库有效性 + P0-2: 跨图规则可达性（并集）──
    print("\n=== 样本有效性 ===")
    print(
        f"有效图纸: {len(valid_reports)} / {len(reports)}"
        f"（无效 {len(invalid_reports)}，跳过 {len(skipped_reports)}）",
        flush=True,
    )
    for r in invalid_reports:
        print(f"  [剔除] {r['file']}: {r.get('content_validity')}", flush=True)
    for r in skipped_reports:
        print(
            f"  [跳过] {r['file']}: {r.get('skip_reason', '')}（不计入覆盖率分母）",
            flush=True,
        )

    if valid_reports:
        all_funcs = FuncRegistry().list_all()
        total_funcs = len(all_funcs)
        unsupported_union = {
            f.func_id for f in all_funcs if getattr(f, "unsupported_2d", False)
        }
        gate_union = {
            f.func_id for f in all_funcs if getattr(f, "implementation_gate", False)
        }
        applicable_union: set[str] = set()
        evaluated_union: set[str] = set()
        for r in valid_reports:
            cov = r.get("coverage", {})
            applicable_union |= set(cov.get("applicable_func_ids", []))
            evaluated_union |= set(cov.get("evaluated_func_ids", []))
        # 严格口径：全局上下文规则（EXIST-083/093）会产出判定但不在适用集合内，
        # 分子分母必须同集合，否则覆盖率被虚增。
        strict_evaluated = evaluated_union & applicable_union
        judgeable_union = applicable_union - unsupported_union - gate_union
        judgeable_evaluated = strict_evaluated - unsupported_union - gate_union
        print("\n=== 规则可达性（有效图纸并集）===")
        print(
            f"适用规则(别名归并): {len(applicable_union)} / {total_funcs} "
            f"({len(applicable_union) / total_funcs:.1%})",
            flush=True,
        )
        print(
            f"实际判定可达: {len(evaluated_union)} / {len(applicable_union)} "
            f"({len(evaluated_union) / len(applicable_union):.1%})"
            f"（含全局上下文规则 {len(evaluated_union - applicable_union)} 条，不在适用集合内）",
            flush=True,
        )
        print(
            f"[严格口径] 实际判定: {len(strict_evaluated)} / {len(applicable_union)} "
            f"({len(strict_evaluated) / len(applicable_union):.1%})",
            flush=True,
        )
        print(
            f"[可判定口径] 实际判定: {len(judgeable_evaluated)} / {len(judgeable_union)} "
            f"({len(judgeable_evaluated) / len(judgeable_union):.1%})"
            f"（分母剔除 unsupported_2d {len(applicable_union & unsupported_union)} 条"
            f" + 实现门禁 {len(applicable_union & gate_union)} 条）",
            flush=True,
        )
        # 产品力评估口径：适用性可达 = 别名归并后能匹配到实体的规则占比
        # （前序 P0-1 报告 62.6% 即此口径；评估报告 40.8% 为裸类型匹配口径）
        print(
            f"[产品力口径] 适用性可达: {len(applicable_union) / total_funcs:.1%}",
            flush=True,
        )

    print("\n=== 汇总（去重前）===")
    all_findings = [f for r in valid_reports for f in r["findings"]]
    print(f"findings 总数: {len(all_findings)}", flush=True)

    # ── 跨图纸去重 + 规则合并 ──────────────────────────
    # 1. 同实体同规则跨文件去重：保留最高严重度
    sev_order = {"critical": 0, "major": 1, "minor": 2, "low": 3}

    deduped = {}
    for r in valid_reports:
        for f in r["findings"]:
            eid = f.get("entity_id", "")
            fid = f["func_id"]
            key = (eid, fid)
            sev = sev_order.get(f.get("severity", "minor"), 9)
            if key not in deduped or sev < sev_order.get(deduped[key]["_sev"], 9):
                deduped[key] = {**f, "_dedup_keys": [(r["file"], eid)], "_sev": sev}
            else:
                deduped[key]["_dedup_keys"].append((r["file"], eid))

    # 2. EVAC-002 + EVAC-003 合并（同房间疏散距离超标）
    evac_merge = {}
    merged_findings = []
    for key, f in deduped.items():
        eid, fid = key
        if fid in ("EVAC-002", "EVAC-003") and eid:
            grp = evac_merge.setdefault(eid, [])
            grp.append(f)
        else:
            merged_findings.append(f)
    for eid, items in evac_merge.items():
        worst = min(items, key=lambda x: x["_sev"])
        merged_findings.append({
            **worst,
            "func_id": "EVAC-002+003",
            "explanation": (worst.get("explanation", "") + " [EVAC-002+003 合并]")[:160],
            "_merged": ["EVAC-002", "EVAC-003"],
            "_dedup_keys": [k for x in items for k in x.get("_dedup_keys", [])],
        })

    # 3. AREA-018/019/021 同 ante chamber 去重：只保留最严重一条
    area_merge = {}
    final_findings = []
    for f in merged_findings:
        eid = f.get("entity_id", "")
        fid = f["func_id"]
        if fid in ("AREA-018", "AREA-019", "AREA-021") and eid and "ANTECHAMBER" in eid.upper():
            grp = area_merge.setdefault(eid, [])
            grp.append(f)
        else:
            final_findings.append(f)
    for eid, items in area_merge.items():
        worst = min(items, key=lambda x: x["_sev"])
        worst["_merged"] = [x["func_id"] for x in items]
        final_findings.append(worst)

    all_findings_deduped = final_findings
    print(f"\n=== 汇总（去重后）===")
    print(f"findings 总数: {len(all_findings_deduped)} (去重 {len(all_findings) - len(all_findings_deduped)} 条)", flush=True)
    print(
        "严重度分布: "
        + str(dict(Counter(f["severity"] for f in all_findings_deduped).most_common())),
        flush=True,
    )
    print("\n函数 FAIL 排行（去重后）:", flush=True)
    for fid, n in Counter(f["func_id"] for f in all_findings_deduped).most_common(15):
        print(f"  {fid:<18} {n}", flush=True)

    print("\n合并详情:", flush=True)
    for f in all_findings_deduped:
        merged = f.get("_merged")
        if merged:
            keys = ", ".join(f"{k[0][:25]}" for k in f.get("_dedup_keys", [])[:3])
            print(f"  {f['func_id']}: {merged} → {f['entity_id']} ({keys})", flush=True)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, ensure_ascii=False, indent=2)
    print(f"\n明细报告: {REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
