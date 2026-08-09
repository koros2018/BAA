"""版本对比页 — v1 vs v2 变更概览与详情"""

from typing import Any, Dict, List

from .components import (
    Paragraph, Spacer, StatCard, make_table,
    C_DANGER, C_ACCENT, C_SECONDARY,
)


def build_diff_page(
    buf: List[Any],
    styles: Dict[str, Any],
    page_w: float,
    margin: float,
    diff_report: Dict[str, Any],
    lang: str = "zh",
) -> None:
    """版本对比报告页"""
    s = styles
    cw = page_w - 2 * margin

    v1_file = diff_report.get("v1_file", "")
    v2_file = diff_report.get("v2_file", "")
    title = f"版本对比：{v1_file} vs {v2_file}"
    buf.append(Paragraph(title, s["section-title"]))
    buf.append(Spacer(1, 8))

    summary = diff_report.get("summary", {})
    new_v = summary.get("new_violations", 0)
    fixed_v = summary.get("fixed_violations", 0)
    changed_v = summary.get("changed_violations", 0)
    card_w = (cw - 24) / 3

    buf.append(StatCard("新增", str(new_v), C_DANGER, card_w, 50))
    buf.append(Spacer(1, 6))
    buf.append(StatCard("已修复", str(fixed_v), C_ACCENT, card_w, 50))
    buf.append(Spacer(1, 6))
    buf.append(StatCard("已变更", str(changed_v), C_SECONDARY, card_w, 50))
    buf.append(Spacer(1, 16))

    items = diff_report.get("items", [])
    if items:
        buf.append(Paragraph("变更明细", s["subsection-title"]))
        buf.append(Spacer(1, 6))
        type_map = {"new": "新增", "fixed": "已修复", "changed": "已变更"}
        rows = []
        for item in items:
            diff_type = item.get("diff_type", "")
            type_label = type_map.get(diff_type, diff_type)
            clause_id = item.get("clause_id", "")
            entity_id = item.get("entity_id", "")
            rows.append([type_label, clause_id, entity_id])
        buf.append(make_table(styles, rows,
                              col_widths=[(cw - 200) / 2, cw - 200, (cw - 200) / 2],
                              headers=["变更类型", "条款ID", "实体ID"]))