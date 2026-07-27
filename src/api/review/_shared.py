"""
P78: review_routes.py 共享辅助函数
"""
from enum import Enum
from datetime import datetime, timedelta
from collections import Counter


class ConfidenceTier(str, Enum):
    """置信度语义分级（P61）"""

    CONFIRMED = "confirmed"  # ≥0.85，确认违规
    SUSPECTED = "suspected"  # 0.60~0.85，疑似违规
    NEEDS_REVIEW = "needs_review"  # <0.60，建议人工复核


def _confidence_tier(confidence: float) -> str:
    """将 0~1 置信度映射为语义分级标签。"""
    if confidence >= 0.85:
        return ConfidenceTier.CONFIRMED.value
    if confidence >= 0.60:
        return ConfidenceTier.SUSPECTED.value
    return ConfidenceTier.NEEDS_REVIEW.value


COMPLIANCE_GUIDE = {
    "critical": "必须整改，否则无法通过施工图审查，建议优先处理",
    "major": "建议整改，影响建筑性能或施工便利性",
    "minor": "可选择性优化，提升图纸质量",
}

COMPLIANCE_PATHS = {
    "dim": "按规范限值调整构件尺寸（宽度/高度/净距）",
    "exist": "补充缺失的消防/疏散设施实体",
    "dist": "调整构件间距以满足最小安全距离",
    "count": "增加设施数量满足最低配置要求",
    "area": "优化平面布局以满足面积/分区要求",
    "attr": "修正构件属性（材料/等级/标识）",
    "light": "补充/调整照明设施以满足照度要求",
    "vac": "优化疏散路径，确保连通性",
}


def _classify_priority(d: dict) -> str:
    """P62: severity + confidence → 整改优先级 P0/P1/P2。"""
    sev = d.get("severity", "minor")
    tier = d.get("confidence_tier", "")
    if tier == "confirmed" and sev == "critical":
        return "P0"
    if (tier == "confirmed" and sev == "major") or (tier == "suspected" and sev == "critical"):
        return "P1"
    return "P2"


def _derive_compliance_path(d: dict) -> str:
    """P62: 从 func_id/clause_id 推导整改路径指引。"""
    fid = (d.get("func_id") or d.get("clause_id") or "").lower()
    for prefix, guide in COMPLIANCE_PATHS.items():
        if prefix in fid:
            return guide
    return "参照对应规范条款，逐项整改"


def _build_structured_summary(details: list[dict]) -> dict:
    """P62: 从 details 生成结构化摘要。"""
    if not details:
        return {
            "top_violations": [],
            "priority_distribution": {"P0": 0, "P1": 0, "P2": 0},
            "category_distribution": {},
            "compliance_actions": [],
        }

    annotated = []
    for d in details:
        annotated.append(
            {
                **d,
                "priority": _classify_priority(d),
                "compliance_path": _derive_compliance_path(d),
            }
        )

    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    annotated.sort(
        key=lambda x: (priority_order.get(x["priority"], 9), -(x.get("confidence", 0.5)))
    )

    top_violations = annotated[:5]
    top_violations_out = []
    for i, v in enumerate(top_violations, 1):
        top_violations_out.append(
            {
                "rank": i,
                "priority": v["priority"],
                "severity": v.get("severity", "minor"),
                "confidence": v.get("confidence", 0.5),
                "confidence_tier": v.get("confidence_tier", ""),
                "clause_id": v.get("clause_id", ""),
                "clause_title": v.get("clause_title", ""),
                "func_id": v.get("func_id", ""),
                "explanation": v.get("explanation", ""),
            }
        )

    priority_dist = Counter(v["priority"] for v in annotated)
    category_dist = Counter(v.get("category", "unknown") for v in annotated)

    actions = {}
    for v in annotated:
        path = v["compliance_path"]
        if path not in actions:
            actions[path] = {"guide": path, "count": 0, "priorities": []}
        actions[path]["count"] += 1
        if v["priority"] not in actions[path]["priorities"]:
            actions[path]["priorities"].append(v["priority"])

    compliance_actions = sorted(
        actions.values(), key=lambda a: a["count"], reverse=True
    )

    return {
        "top_violations": top_violations_out,
        "priority_distribution": {
            "P0": priority_dist.get("P0", 0),
            "P1": priority_dist.get("P1", 0),
            "P2": priority_dist.get("P2", 0),
        },
        "category_distribution": dict(category_dist.most_common()),
        "compliance_actions": compliance_actions,
    }


# ── P45: 热工材料常量 ────────────────────────────────────
HI = 8.7
HO = 23.0

THERMAL_MATERIALS = {
    "rockwool": {"name": "岩棉", "lambda": 0.040},
    "glasswool": {"name": "玻璃棉", "lambda": 0.044},
    "eps": {"name": "膨胀聚苯板", "lambda": 0.041},
    "xps": {"name": "挤塑聚苯板", "lambda": 0.030},
    "urethane": {"name": "聚氨酯", "lambda": 0.024},
    "foamglass": {"name": "泡沫玻璃", "lambda": 0.060},
    "aerogel": {"name": "气凝胶", "lambda": 0.018},
}

THERMAL_THRESHOLDS = {
    "severe_cold": {
        "exterior_wall": 0.45,
        "roof": 0.45,
        "floor": 0.50,
        "window": 2.00,
        "door": 2.00,
    },
    "cold": {
        "exterior_wall": 0.50,
        "roof": 0.50,
        "floor": 0.55,
        "window": 2.50,
        "door": 2.50,
    },
    "hot_summer_cold_winter": {
        "exterior_wall": 1.00,
        "roof": 1.00,
        "floor": 0.55,
        "window": 3.00,
        "door": 3.00,
    },
    "hot_summer_warm_winter": {
        "exterior_wall": 1.50,
        "roof": 1.50,
        "floor": 0.60,
        "window": 3.50,
        "door": 3.50,
    },
    "mild": {
        "exterior_wall": 1.50,
        "roof": 1.50,
        "floor": 0.60,
        "window": 4.00,
        "door": 4.00,
    },
}


# ── P78: 审查共享逻辑（standard + multi_sheet 共用） ──────

def _build_findings(
    entities: list, registry_funcs: list, repo, get_strict_threshold, _get_fr, _get_aa, standard: str
) -> list[dict]:
    """对 entities 逐一跑原子函数，返回 details 列表 + clause_results Counter。

    供 standard review 和 multi-sheet review 复用。
    """
    from collections import Counter

    clause_results = Counter()
    details = []
    global_funcs = [
        f for f in registry_funcs if getattr(f, "requires_global_context", False)
    ]
    local_funcs = [
        f for f in registry_funcs if not getattr(f, "requires_global_context", False)
    ]

    for e in entities:
        for func in local_funcs:
            tv, u, op = get_strict_threshold(func.clause_id)
            func.threshold = tv
            func.unit = u
            func.operator = op
            r = _get_fr().execute_with_timeout(func, e)
            if r is None:
                continue
            clause_results[func.clause_id] += 1
            if r.result != "PASS":
                clause = {
                    "standard": standard,
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _get_aa().build_finding(r, clause, e, entities[:5])
                details.append(
                    {
                        "entity_id": e.get("id", e.get("type", "")),
                        "entity_type": e["type"],
                        "clause_id": func.clause_id,
                        "clause_title": func.name,
                        "func_id": func.func_id,
                        "result": f.judgement["result"],
                        "extracted_value": f.extracted_params["extracted_value"],
                        "required_value": f.extracted_params.get("required_value", 1.2),
                        "difference": f.extracted_params.get("difference", 0),
                        "severity": f.judgement.get("severity", "major"),
                        "explanation": f.explanation[:120],
                        "confidence": r.confidence,
                        "confidence_tier": _confidence_tier(r.confidence),
                    }
                )

    # 全局函数：仅 target_entities 缺失时告警
    entity_types_in_drawing = set(e.get("type", "") for e in entities)
    for func in registry_funcs:
        if func.category.value != "exist":
            continue
        func_targets = set(func.target_entities) if func.target_entities else set()
        if func_targets and not func_targets.intersection(entity_types_in_drawing):
            # 目标类型在图中完全没有 → 跳过（不是真违规，是识别问题）
            continue
        # target_entities 为空或已匹配部分 → 继续检查
        has_match = any(func.matches(e) for e in entities) if func_targets else True
        if not has_match:
            r = _get_fr().execute_with_timeout(func, None)
            if r is not None and r.result != "PASS":
                clause = {
                    "standard": standard,
                    "clause_id": func.clause_id,
                    "title": func.name,
                    "text": func.description,
                    "category": func.category.value,
                }
                f = _get_aa().build_finding(r, clause, {}, entities[:5])
                details.append(
                    {
                        "entity_id": "",
                        "entity_type": "missing",
                        "clause_id": f.clause.get("clause_id", ""),
                        "clause_title": f.clause.get("title", ""),
                        "func_id": f.clause.get("func_id", ""),
                        "result": f.judgement.get("result", "FAIL"),
                        "severity": f.judgement.get("severity", "critical"),
                        "extracted_value": f.extracted_params.get("extracted_value", 0.0),
                        "required_value": f.extracted_params.get("required_value", 1.0),
                        "difference": -(
                            f.extracted_params.get("required_value", 1.0) or 1.0
                        ),
                        "explanation": f.explanation[:120],
                        "confidence": r.confidence,
                        "confidence_tier": _confidence_tier(r.confidence),
                    }
                )

    return details, dict(clause_results)
