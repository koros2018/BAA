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

    compliance_actions = sorted(actions.values(), key=lambda a: a["count"], reverse=True)

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
#   _build_findings 已删除（P0-4，2026-11-04）：
#   该函数是为 review_routes.py 抽取的共享执行循环，但实际实现时
#   _do_clustering_with_timeout 以闭环形式写入了 review_routes.py，
#   _build_findings 从未被调用（grep 确认仅定义、无调用点）。
#
#   当前三条规则执行路径的职责划分：
#   1. baa_api.py::_do_deconstruct_step3
#      用途：/deconstruct 端点，输出 attribution findings（含归属分析）
#      特点：execute_with_timeout 单层，无 chaining，无集群计数
#   2. review_routes.py::_do_clustering_with_timeout
#      用途：/review 端点（主路径），输出 clause_results + details
#      特点：execute_chained 支持依赖链，超时控制，线程安全结果收集
#   3. batch_routes.py::_run_exist_scope_batch + 内联执行循环
#      用途：/batch-review / /review/project/summary
#      特点：复用 _shared 常量，有自己的阈值预计算 (_func_specs)
#
#   三套实现各有独立职责，统一为单一 rule_runner 属于架构重构，
#   留待 P1 专项处理（评估报告 §5 P1-4）。

