"""统计摘要页 — 概要表 + 违规条款分布 + 实体类型分布"""

from typing import Any, Dict, List

from .components import Paragraph, Spacer, make_table


def build_summary_page(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    filename: str,
    summary: Dict[str, Any],
    details: List[Dict[str, Any]],
    lang: str = "zh",
) -> None:
    """统计摘要页"""
    s = styles
    cw = page_w - 2 * margin

    buf.append(Paragraph("审查摘要", s["section-title"]))
    buf.append(Spacer(1, 6))

    # 概要表
    rows = [
        ["文件名", filename],
        ["建筑类型", "民用建筑" if summary.get("building_type", "civil") == "civil" else "工业建筑"],
        ["图元总数", str(summary.get("total_entities", 0))],
        ["检查项次", str(summary.get("total_checks", 0))],
        ["违规总数", str(summary.get("violations", 0))],
        ["涉及条款", str(len(summary.get("violation_by_clause", {})))],
        ["处理时间", f"{summary.get('processing_time_ms', 0)}ms"],
    ]
    buf.append(make_table(styles, rows, col_widths=[100, cw - 100]))
    buf.append(Spacer(1, 16))

    # 违规条款分布
    buf.append(Paragraph("违规条款分布", s["subsection-title"]))
    buf.append(Spacer(1, 6))
    violation_by_clause = summary.get("violation_by_clause", {})
    if violation_by_clause:
        rows = []
        for clause_id, count in sorted(violation_by_clause.items(), key=lambda x: -x[1]):
            title = ""
            for d in details:
                if d.get("clause_id") == clause_id:
                    title = d.get("clause_title", "")
                    break
            rows.append([clause_id, title[:50], str(count)])
        buf.append(make_table(styles, rows, col_widths=[70, cw - 130, 60],
                              headers=["条款ID", "条款名称", "违规数量"]))
    else:
        buf.append(Paragraph("无", s["body"]))
    buf.append(Spacer(1, 16))

    # 实体类型分布
    entity_types = summary.get("entity_types", {})
    if entity_types:
        buf.append(Paragraph("实体类型分布", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        rows = sorted(entity_types.items(), key=lambda x: -x[1])
        buf.append(make_table(styles, [list(r) for r in rows], col_widths=[cw - 80, 80],
                              headers=["实体类型", "数量"]))


def build_structured_summary_page(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    structured_summary: Dict[str, Any],
    lang: str = "zh",
) -> None:
    """P62/P69: 结构化摘要页 — TOP-5 违规 + 整改优先级"""
    s = styles
    cw = page_w - 2 * margin

    buf.append(Paragraph("整改优先级概览", s["section-title"]))
    buf.append(Spacer(1, 8))

    priority_dist = structured_summary.get("priority_distribution", {})
    p0 = priority_dist.get("P0", 0)
    p1 = priority_dist.get("P1", 0)
    p2 = priority_dist.get("P2", 0)
    card_w = (cw - 24) / 3
    from .components import C_DANGER, C_WARNING, C_PRIMARY, StatCard

    buf.append(StatCard("P0 紧急", str(p0), C_DANGER, card_w, 50))
    buf.append(Spacer(1, 6))
    buf.append(StatCard("P1 重要", str(p1), C_WARNING, card_w, 50))
    buf.append(Spacer(1, 6))
    buf.append(StatCard("P2 一般", str(p2), C_PRIMARY, card_w, 50))
    buf.append(Spacer(1, 16))

    # TOP-5 违规表
    top_violations = structured_summary.get("top_violations", [])
    if top_violations:
        buf.append(Paragraph("TOP-5 违规", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        rows = []
        for v in top_violations:
            rank = str(v.get("rank", ""))
            priority = v.get("priority", "P2")
            clause_id = v.get("clause_id", "")
            clause_title = (v.get("clause_title", "") or "")[:40]
            severity = v.get("severity", "")
            confidence = v.get("confidence", 0)
            conf_str = f"{int(confidence * 100)}%" if isinstance(confidence, (int, float)) else str(confidence)
            rows.append([rank, priority, clause_id, clause_title, severity, conf_str])
        buf.append(make_table(styles, rows, col_widths=[30, 35, 70, cw - 210, 50, 45],
                              headers=["排名", "优先级", "条款ID", "条款名称", "严重度", "置信度"]))
        buf.append(Spacer(1, 16))
    else:
        buf.append(Paragraph("暂无数据", s["body"]))
        buf.append(Spacer(1, 16))

    # 合规路径指引
    compliance_actions = structured_summary.get("compliance_actions", [])
    if compliance_actions:
        buf.append(Paragraph("合规路径指引", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        action_rows = []
        for act in compliance_actions:
            p_label = act.get("priority", "P2")
            p_name = act.get("priority_label", p_label)
            count = act.get("count", 0)
            description = (act.get("description", "") or "")[:50]
            paths = act.get("action_paths", [])
            path_str = "; ".join(paths[:3])[:60] if paths else ""
            action_rows.append([p_name, str(count), description, path_str])
        buf.append(make_table(styles, action_rows, col_widths=[80, 40, cw - 210, 90],
                              headers=["优先级", "数量", "说明", "合规路径"]))